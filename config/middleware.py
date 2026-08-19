# config/middleware.py

import logging

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponseForbidden, HttpResponsePermanentRedirect
from django.template.loader import render_to_string

from home.models import BlockedIp
from home.netutils import client_ip

logger = logging.getLogger(__name__)


class CanonicalHostMiddleware:
    """`www.` 付きのアクセスを正規ホスト（apex）へ 301 で寄せる。

    Django には www を外す設定が無い（PREPEND_WWW は付ける方向）ため自前で持つ。
    settings.CANONICAL_HOST が未設定なら何もしない（開発環境では無効）。
    """

    def __init__(self, get_response):
        self.canonical_host = getattr(settings, 'CANONICAL_HOST', '')
        if not self.canonical_host:
            raise MiddlewareNotUsed
        self.www_host = f'www.{self.canonical_host}'
        self.get_response = get_response

    def __call__(self, request):
        if request.get_host() == self.www_host:
            return HttpResponsePermanentRedirect(
                f'{request.scheme}://{self.canonical_host}{request.get_full_path()}'
            )
        return self.get_response(request)


class BlockedIpMiddleware:
    """遮断リスト（home.BlockedIp）にある IP からのアクセスを 403 で止める。

    参加フォームの連続送信を検知したときに登録される。期間は繰り返すほど延び、
    3回目以降は恒久（settings.IP_BLOCK_DURATIONS）。解除は admin（/admin/）から。

    ロックアウトの逃げ道を2つ用意してある。自分の IP を誤って遮断すると admin にも
    入れなくなり、DB を直接触るしかなくなるため。
      - IP_BLOCK_ENABLED=False  … 遮断そのものを止める
      - IP_BLOCK_EXEMPT=<IP,IP> … 個別に除外する（遮断リストより優先）
    どちらも App Service のアプリケーション設定から変えられる。

    DB やキャッシュが落ちているときは通す（fail open）。遮断は付加機能であって、
    そのためにサイト全体を落とさない。
    """

    #: 遮断リストをキャッシュする秒数（毎リクエスト DB を引かないため）
    CACHE_SECONDS = 60

    CACHE_KEY = 'blocked-ips'

    def __init__(self, get_response):
        if not getattr(settings, 'IP_BLOCK_ENABLED', True):
            raise MiddlewareNotUsed
        self.get_response = get_response

    def __call__(self, request):
        ip = client_ip(request)
        if ip and ip not in settings.IP_BLOCK_EXEMPT:
            blocked = self.blocked_ips()
            if ip in blocked:
                logger.warning('遮断中の IP からのアクセスを拒否しました: IP=%s', ip)
                # 遮断中は静的ファイルも返さないので、CSS を埋め込んだ1枚で返す
                return HttpResponseForbidden(render_to_string('home/blocked.html', {
                    'contact': settings.JOIN_NOTIFY_EMAIL,
                    'expires_at': blocked[ip],
                }))
        return self.get_response(request)

    @classmethod
    def blocked_ips(cls):
        """遮断中の IP と解除予定（恒久なら None）の対応。失敗したら空（＝通す）。

        キャッシュも DB も落ちうるので、まとめて握る。ここで例外を漏らすと
        全リクエストが 500 になり、遮断機能のせいでサイトが落ちる。

        期限切れは最大 CACHE_SECONDS 秒だけ反映が遅れる。
        """
        try:
            ips = cache.get(cls.CACHE_KEY)
            if ips is None:
                ips = dict(
                    BlockedIp.objects.active().values_list('ip', 'expires_at')
                )
                cache.set(cls.CACHE_KEY, ips, cls.CACHE_SECONDS)
            return ips
        except Exception:
            logger.exception('遮断リストの取得に失敗しました')
            return {}

    @classmethod
    def forget_cache(cls):
        """遮断リストを足したとき、次のリクエストから効かせる。"""
        try:
            cache.delete(cls.CACHE_KEY)
        except Exception:
            logger.debug('遮断リストのキャッシュ削除に失敗しました', exc_info=True)

