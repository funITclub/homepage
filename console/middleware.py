# console/middleware.py

import html
import json
import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils import timezone

from . import suspicious
from .models import DailyVisitors, PageView

logger = logging.getLogger(__name__)

#: 知らせ（beacon）の合言葉に使う salt。ページと知らせの組を、サイトが出したものに限るため
BEACON_SALT = 'console.pageview'

#: 知らせを受け付ける時間（秒）。ページを出してからこれより後の知らせは数えない
BEACON_MAX_AGE = 6 * 60 * 60

#: 訪問者を数えたことを覚える Cookie。中身はその日の日付だけ
VISITOR_COOKIE = 'fic_visited'

BOT_PATTERN = re.compile(
    r'bot|crawl|spider|slurp|preview|monitor|curl|wget|python|headless|scan|checker|dataprovider|'
    r'warmup|healthcheck|alwayson|compatible;(?! ?MSIE)',
    re.IGNORECASE,
)

TITLE_PATTERN = re.compile(rb'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)

# 画面が見えたときに1回だけ知らせる。自動で動かしているブラウザ（navigator.webdriver）は知らせない。
# JavaScript を動かさない巡回ロボットは、そもそもここまで来ない。
BEACON_SCRIPT = '''<script>(function(){if(navigator.webdriver)return;var done=false;function send(){if(done||document.visibilityState!=="visible")return;done=true;try{fetch(%(url)s,{method:"POST",body:new URLSearchParams({t:%(token)s}),credentials:"same-origin",keepalive:true}).catch(function(){})}catch(e){}}send();document.addEventListener("visibilitychange",send)})();</script>'''


def is_bot(request):
    return bool(BOT_PATTERN.search(request.headers.get('User-Agent', '')))


def is_staff(request):
    user = getattr(request, 'user', None)
    return user is not None and user.is_authenticated


class SuspiciousAccessMiddleware:
    """攻撃用のパス探し・名乗っているスキャナーを残す（console.suspicious.check_request）。

    ほかのミドルウェアが途中で返したもの（リダイレクト・ゲートで送り返したものなど）も取りこぼさない
    よう、遮断の次（いちばん外側に近いところ）に置く。ログイン中かどうかは、応答を作り終えた後に
    request.user で見る（認証はこれより内側で付くため）。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            suspicious.check_request(request)
        except Exception:
            logger.exception('不審なアクセスの確認に失敗しました')
        return response


class PageViewMiddleware:
    """公開ページが人に表示された回数を、日ごと・パスごとに数える。

    サーバーにページを取りに来ただけでは数えない（人のふりをした巡回ロボットが多いため）。
    数える候補のページの終わりに小さなスクリプトを差し込み、ブラウザがそれを動かして、
    画面が見えたときに知らせてきた（console.views.beacon）ときだけ数える。

    数える候補は「人が公開ページを開いた」ように見えるものだけ。
      - GET で、200 を返し、HTML のもの（リダイレクト・エラー・CSS・画像・JSON は数えない）
      - 編集画面・コンソール・admin・静的ファイルは数えない
      - ログイン中の運営の閲覧は数えない（確認のたびに増えると数字が読めなくなる）
      - 名乗っている巡回ロボット・スキャナーと、ブラウザの先読みは数えない

    知らせにはサイトが署名した合言葉（パスと題名）を付けるので、出していないページは数えられない。
    IP や User-Agent は記録しない（判定に使うだけ）。
    """

    EXCLUDED_PREFIXES = ('/edit/', '/console/', '/admin/', '/static/', '/media/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if self.should_count(request, response):
            try:
                self.add_beacon(request, response)
            except Exception:
                logger.exception('ページビューの知らせを差し込めませんでした')
        return response

    def add_beacon(self, request, response):
        body = response.content
        end = body.lower().rfind(b'</body>')
        if end < 0:
            return
        nonce = secrets.token_hex(16)
        token = signing.dumps({'p': request.path[:255], 't': self.title_of(response), 'n': nonce},
                              salt=BEACON_SALT, compress=True)
        script = BEACON_SCRIPT % {'url': json.dumps(reverse('console:beacon')), 'token': json.dumps(token)}
        response.content = body[:end] + script.encode() + body[end:]
        if response.has_header('Content-Length'):
            response['Content-Length'] = str(len(response.content))
        # 知らせが来なければ「人のふりをしたロボット」として残す（console.suspicious）
        suspicious.wait_for_beacon(request, nonce)

    def title_of(self, response):
        """HTML の <title>。コンソールでページ名にする。取れなければ空。"""
        match = TITLE_PATTERN.search(response.content[:20000])
        if not match:
            return ''
        text = match.group(1).decode(response.charset or 'utf-8', errors='replace')
        return ' '.join(html.unescape(text).split())[:255]

    def should_count(self, request, response):
        if request.method != 'GET' or response.status_code != 200:
            return False
        if getattr(response, 'streaming', False):
            return False
        if not response.get('Content-Type', '').startswith('text/html'):
            return False
        if request.path.startswith(self.EXCLUDED_PREFIXES):
            return False
        if is_staff(request) or is_bot(request):
            return False
        if 'prefetch' in request.headers.get('Sec-Purpose', '') or \
                request.headers.get('Purpose', '') == 'prefetch':
            return False
        return True


def record_beacon(request, response):
    """ブラウザからの知らせ（POST の t）を確かめて数える。数えたら True。

    訪問者数（DailyVisitors）も同じときに数える。同じブラウザはその日1人とし、数えたことは
    Cookie（VISITOR_COOKIE。中身はその日の日付だけ）で覚える。
    """
    try:
        page = signing.loads(request.POST.get('t', ''), salt=BEACON_SALT, max_age=BEACON_MAX_AGE)
    except signing.BadSignature:
        return False
    try:
        suspicious.beacon_arrived(page.get('n'))
    except Exception:
        logger.exception('知らせ待ちの控えを消せませんでした')
    if is_staff(request) or is_bot(request):
        return False
    today = timezone.localdate()
    try:
        PageView.record(today, page['p'], page.get('t', ''))
    except Exception:
        logger.exception('ページビューの記録に失敗しました')
        return False
    count_visitor(request, response, today)
    return True


def count_visitor(request, response, today):
    """このブラウザが今日まだ数えられていなければ、訪問者を1人足して印の Cookie を置く。"""
    if request.COOKIES.get(VISITOR_COOKIE) == today.isoformat():
        return
    try:
        DailyVisitors.record(today)
    except Exception:
        logger.exception('訪問者数の記録に失敗しました')
        return
    # その日の終わりまで有効にする（日付が変わったら、また1人と数える）
    now = timezone.localtime()
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    response.set_cookie(VISITOR_COOKIE, today.isoformat(),
                        max_age=int((midnight - now).total_seconds()) + 1,
                        secure=settings.SESSION_COOKIE_SECURE, httponly=True, samesite='Lax')
