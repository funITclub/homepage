# console/suspicious.py
#
# 不審なアクセスを記録する（運営コンソールの「不審なアクセス」）。種類は SuspiciousAccess.KINDS。
#
#   攻撃用のパスを探る      … /wp-login.php・/.env など、このサイトに無い攻撃用の場所を開こうとした
#   人のふりをしたロボット  … ブラウザを名乗ってページを取ったのに、知らせ（JavaScript）が来なかった
#   名乗っているスキャナー  … User-Agent でスキャナー・チェッカー・道具を名乗っている（検索エンジンは除く）
#   遮断中の IP             … 遮断リスト（home.BlockedIp）の IP からのアクセス
#   参加フォームの連続送信  … 参加フォームの連続送信で遮断した
#
# 「個人情報をシステムに持たない」方針の例外として、不審なものだけ IP・User-Agent・パス・日時を残し、
# SuspiciousAccess.KEEP_DAYS で消す。ログイン中の運営のアクセスは残さない。
# 記録に失敗してもページは返す。同じ IP・同じ種類は1日 DAILY_LIMIT 件までにする（表が埋まらないように）。

import logging
import re
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from home.netutils import client_ip

from .models import PendingView, SuspiciousAccess

logger = logging.getLogger(__name__)

#: 同じ IP・同じ種類を1日に残す件数
DAILY_LIMIT = 50

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
    """1件残す。ログイン中の運営と、1日の上限を超えた分は残さない。"""
    if is_staff(request):
        return
    ip = ip or client_ip(request) or None
    try:
        key = f'suspicious:{timezone.localdate()}:{kind}:{ip}'
        if cache.get(key, 0) >= DAILY_LIMIT:
            return
        cache.set(key, cache.get(key, 0) + 1, 24 * 60 * 60)
        SuspiciousAccess.objects.create(
            created_at=timezone.now(), kind=kind, ip=ip, user_agent=_agent(request),
            method=request.method[:10], path=(path or request.path)[:255])
    except Exception:
        logger.exception('不審なアクセスの記録に失敗しました')


def check_request(request):
    """パスと User-Agent から、攻撃用のパス探し・スキャナーを見つけて残す。"""
    if request.path.startswith('/static/') or is_staff(request):
        return
    if PROBE_PATTERN.search(request.path):
        record(request, SuspiciousAccess.PROBE)
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
    return len(rows)


def purge_old(now=None):
    """KEEP_DAYS より古い記録を消す（毎日の点検から呼ぶ）。"""
    now = now or timezone.now()
    deleted, _ = SuspiciousAccess.objects.filter(
        created_at__lt=now - timedelta(days=SuspiciousAccess.KEEP_DAYS)).delete()
    return deleted
