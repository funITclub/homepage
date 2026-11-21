# console/middleware.py

import html
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import DailyVisitors, PageView

logger = logging.getLogger(__name__)


class PageViewMiddleware:
    """公開ページが表示された回数を、日ごと・パスごとに数える。

    数えるのは「人が公開ページを開いた」ときだけ。
      - GET で、200 を返し、HTML のもの（リダイレクト・エラー・CSS・画像・JSON は数えない）
      - 編集画面・コンソール・admin・静的ファイルは数えない
      - ログイン中の運営の閲覧は数えない（確認のたびに増えると数字が読めなくなる）
      - 検索エンジンなどのクローラーと、ブラウザの先読みは数えない

    IP や User-Agent は記録しない（判定に使うだけ）。記録に失敗してもページは返す。

    訪問者数（DailyVisitors）も同じ条件で数える。同じブラウザはその日1人とし、数えたことは
    Cookie（VISITOR_COOKIE。中身はその日の日付だけ）で覚える。
    """

    VISITOR_COOKIE = 'fic_visited'

    EXCLUDED_PREFIXES = ('/edit/', '/console/', '/admin/', '/static/', '/media/')

    BOT_PATTERN = re.compile(
        r'bot|crawl|spider|slurp|preview|monitor|curl|wget|python-requests|headless',
        re.IGNORECASE,
    )

    TITLE_PATTERN = re.compile(rb'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if self.should_count(request, response):
            today = timezone.localdate()
            try:
                PageView.record(today, request.path[:255], self.title_of(response))
            except Exception:
                logger.exception('ページビューの記録に失敗しました')
            self.count_visitor(request, response, today)
        return response

    def count_visitor(self, request, response, today):
        """このブラウザが今日まだ数えられていなければ、訪問者を1人足して印の Cookie を置く。"""
        if request.COOKIES.get(self.VISITOR_COOKIE) == today.isoformat():
            return
        try:
            DailyVisitors.record(today)
        except Exception:
            logger.exception('訪問者数の記録に失敗しました')
            return
        # その日の終わりまで有効にする（日付が変わったら、また1人と数える）
        now = timezone.localtime()
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        response.set_cookie(self.VISITOR_COOKIE, today.isoformat(),
                            max_age=int((midnight - now).total_seconds()) + 1,
                            secure=settings.SESSION_COOKIE_SECURE, httponly=True, samesite='Lax')

    def title_of(self, response):
        """HTML の <title>。コンソールでページ名にする。取れなければ空。"""
        if getattr(response, 'streaming', False):
            return ''
        match = self.TITLE_PATTERN.search(response.content[:20000])
        if not match:
            return ''
        text = match.group(1).decode(response.charset or 'utf-8', errors='replace')
        return ' '.join(html.unescape(text).split())

    def should_count(self, request, response):
        if request.method != 'GET' or response.status_code != 200:
            return False
        if not response.get('Content-Type', '').startswith('text/html'):
            return False
        if request.path.startswith(self.EXCLUDED_PREFIXES):
            return False
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            return False
        if self.BOT_PATTERN.search(request.headers.get('User-Agent', '')):
            return False
        if 'prefetch' in request.headers.get('Sec-Purpose', '') or \
                request.headers.get('Purpose', '') == 'prefetch':
            return False
        return True
