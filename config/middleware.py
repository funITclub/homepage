# config/middleware.py

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponsePermanentRedirect


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
