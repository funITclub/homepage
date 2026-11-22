# console/suspicious.py
#
# 不審なアクセスを記録する（運営コンソールの「不審なアクセス」）。種類は SuspiciousAccess.KINDS。
#
#   攻撃用のパスを探る      … /wp-login.php・/.env など、このサイトに無い攻撃用の場所を開こうとした
#   人のふりをしたロボット  … ブラウザを名乗ってページを取ったのに、知らせ（JavaScript）が来なかった
#   名乗っているスキャナー  … User-Agent でスキャナー・チェッカー・道具を名乗っている（検索エンジンは除く）
#   遮断中の IP             … 遮断リスト（home.BlockedIp）の IP からのアクセス
#   参加フォームの連続送信  … 参加フォームの連続送信で遮断した
#   執拗なので自動で遮断    … 攻撃用のパス・人のふりが同じ IP から続いたので遮断した（スキャナーは数えない）
#
# 執拗な IP は settings.SUSPICIOUS_BLOCK_RULES で自動で遮断する（home.BlockedIp。期間・解除・除外は
# 参加フォームの遮断と同じ）。手作業は要らないので、事務局にメールは送らない。
#
# 「個人情報をシステムに持たない」方針の例外として、不審なものだけ IP・User-Agent・パス・日時を残し、
# SuspiciousAccess.KEEP_DAYS で消す。ログイン中の運営のアクセスは残さない。
# 記録に失敗してもページは返す。回数に上限はなく、不審なアクセスはすべて残す。

import ipaddress
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from home.netutils import client_ip

from .models import PendingView, SuspiciousAccess

logger = logging.getLogger(__name__)

#: 知らせを待つ時間（秒）。これを過ぎても知らせが無ければ「人のふりをしたロボット」とする
PENDING_SECONDS = 30 * 60

#: 知らせ待ちの見直しをする間隔（秒）
SWEEP_INTERVAL = 5 * 60

PROBE_PATTERN = re.compile(
    r'\.(php\d?|aspx?|jsp|cgi|env|git|svn|ds_store|bak|sql|ini|cfg|yml|yaml|log)(/|$)|'
    r'/(wp-|wordpress|xmlrpc|phpmyadmin|pma/|myadmin|cgi-bin|vendor/|'
    r'actuator|server-status|boaform|hnap1|owa/|autodiscover|solr/|jenkins|manager/html|'
    r'telescope|_ignition|containers/json|api/v1/pods|config\.json|\.aws|\.ssh)',
    re.IGNORECASE,
)

SCANNER_PATTERN = re.compile(
    r'scan|checker|dataprovider|zgrab|masscan|nmap|nikto|sqlmap|nuclei|httpx|'
    r'python-requests|python-urllib|aiohttp|go-http-client|curl|wget|libwww|okhttp|java/|'
    r'admake|censys|shodan|expanse|internet-?measurement|l9explore|leakix',
    re.IGNORECASE,
)

#: 名乗っている検索エンジン。スキャナーには数えない
SEARCH_ENGINES = re.compile(
    r'googlebot|bingbot|applebot|duckduckbot|yandex|baiduspider|slurp|google-inspectiontool',
    re.IGNORECASE,
)


def is_staff(request):
    user = getattr(request, 'user', None)
    return user is not None and user.is_authenticated


def _agent(request):
    return request.headers.get('User-Agent', '')[:255]


def record(request, kind, ip=None, path=None):
    """1件残す。ログイン中の運営は残さない。回数に上限は設けない。"""
    if is_staff(request):
        return
    ip = ip or client_ip(request) or None
    try:
        SuspiciousAccess.objects.create(
            created_at=timezone.now(), kind=kind, ip=ip, user_agent=_agent(request),
            method=request.method[:10], path=(path or request.path)[:255])
    except Exception:
        logger.exception('不審なアクセスの記録に失敗しました')
        return
    if kind in SuspiciousAccess.WATCHED:
        block_if_persistent(ip)


def is_internal(ip):
    """Azure の内側（死活監視・ウォームアップ）や手元からのアクセス。自動遮断しない。"""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return address.is_private or address.is_loopback or address.is_link_local


def block_if_persistent(ip):
    """同じ IP の不審なアクセスが SUSPICIOUS_BLOCK_RULES に達していたら遮断する。遮断したら True。

    件数は、その IP のいちばん新しい記録から数えて (秒) さかのぼった分。人のふりをしたロボットは
    30 分遅れて記録されるので、今の時刻からではなく記録の時刻で数える。
    """
    if not ip or not settings.IP_BLOCK_ENABLED or ip in settings.IP_BLOCK_EXEMPT or is_internal(ip):
        return False
    from home.models import BlockedIp
    from home.views import block_ip  # home.views がこのモジュールを読むので、ここで読む
    try:
        if BlockedIp.objects.active().filter(ip=ip).exists():
            return False
        rows = SuspiciousAccess.objects.filter(ip=ip, kind__in=SuspiciousAccess.WATCHED)
        latest = rows.order_by('-created_at').values_list('created_at', flat=True).first()
        if latest is None:
            return False
        for limit, seconds in settings.SUSPICIOUS_BLOCK_RULES:
            count = rows.filter(created_at__gt=latest - timedelta(seconds=seconds)).count()
            if count >= limit:
                span = f'{seconds // 60}分' if seconds < 3600 else f'{seconds // 3600}時間'
                block_ip(ip, f'執拗な不審なアクセス（{span}に{count}件）', notify=False)
                SuspiciousAccess.objects.create(created_at=timezone.now(), kind=SuspiciousAccess.AUTO_BLOCK,
                                                ip=ip, path=f'{span}に{count}件')
                return True
    except Exception:
        logger.exception('執拗な IP の遮断に失敗しました: IP=%s', ip)
    return False


#: 自分たちの GitHub Actions が合言葉付きで呼ぶ定期実行の入口。合言葉が通った（200 を返した）ときは残さない。
#: 合言葉が違えば 403・404 になるので、これまでどおり残る
OWN_TASK_PATHS = ('/fe/tasks/send-mails/', '/countdown/notify/run/')

#: 自分たちの GitHub Actions が名乗る User-Agent の頭（.github/workflows の curl に -A で付ける）。
#: 攻撃用のパスでなければ、スキャナーには数えない（名乗りは誰でも付けられるので、パス探しは見逃さない）
OWN_AGENT_PREFIX = 'funitclub-actions/'


def is_own_automation(request, response=None):
    """自分たちの GitHub Actions（定期実行・デプロイ後の確認）からのアクセスか。"""
    if (response is not None and response.status_code == 200
            and request.method == 'POST' and request.path in OWN_TASK_PATHS):
        return True
    return _agent(request).startswith(OWN_AGENT_PREFIX)


def check_request(request, response=None):
    """パスと User-Agent から、攻撃用のパス探し・スキャナーを見つけて残す。"""
    if request.path.startswith('/static/') or is_staff(request):
        return
    if PROBE_PATTERN.search(request.path):
        record(request, SuspiciousAccess.PROBE)
        return
    if is_own_automation(request, response):
        return
    agent = _agent(request)
    if SCANNER_PATTERN.search(agent) and not SEARCH_ENGINES.search(agent):
        record(request, SuspiciousAccess.SCANNER)


def wait_for_beacon(request, nonce):
    """知らせを待つページとして控える。来なければ sweep_pending が「人のふりをしたロボット」にする。"""
    try:
        PendingView.objects.create(created_at=timezone.now(), nonce=nonce, ip=client_ip(request) or None,
                                   user_agent=_agent(request), path=request.path[:255])
        if cache.add('suspicious-sweep', True, SWEEP_INTERVAL):
            sweep_pending()
    except Exception:
        logger.exception('知らせ待ちの控えに失敗しました')


def beacon_arrived(nonce):
    """知らせが来た＝人。控えを消す（IP などはもう残らない）。"""
    if nonce:
        PendingView.objects.filter(nonce=nonce).delete()


def sweep_pending(now=None):
    """PENDING_SECONDS を過ぎても知らせが来なかった控えを、「人のふりをしたロボット」に移す。"""
    now = now or timezone.now()
    stale = PendingView.objects.filter(created_at__lt=now - timedelta(seconds=PENDING_SECONDS))
    rows = list(stale.values('created_at', 'ip', 'user_agent', 'path'))
    SuspiciousAccess.objects.bulk_create([
        SuspiciousAccess(kind=SuspiciousAccess.FAKE_BROWSER, method='GET', **row) for row in rows
    ])
    stale.delete()
    for ip in {row['ip'] for row in rows if row['ip']}:
        block_if_persistent(ip)
    return len(rows)


def purge_old(now=None):
    """KEEP_DAYS より古い記録を消す（毎日の点検から呼ぶ）。"""
    now = now or timezone.now()
    deleted, _ = SuspiciousAccess.objects.filter(
        created_at__lt=now - timedelta(days=SuspiciousAccess.KEEP_DAYS)).delete()
    return deleted
