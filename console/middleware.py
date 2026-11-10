# console/middleware.py

import logging
import re

from django.utils import timezone

from .models import PageView

logger = logging.getLogger(__name__)


class PageViewMiddleware:
    """公開ページが表示された回数を、日ごと・パスごとに数える。

    数えるのは「人が公開ページを開いた」ときだけ。
      - GET で、200 を返し、HTML のもの（リダイレクト・エラー・CSS・画像・JSON は数えない）
      - 編集画面・コンソール・admin・静的ファイルは数えない
      - ログイン中の運営の閲覧は数えない（確認のたびに増えると数字が読めなくなる）
      - 検索エンジンなどのクローラーと、ブラウザの先読みは数えない

    IP や User-Agent は記録しない（判定に使うだけ）。記録に失敗してもページは返す。
    """

    EXCLUDED_PREFIXES = ('/edit/', '/console/', '/admin/', '/static/', '/media/')

    BOT_PATTERN = re.compile(
        r'bot|crawl|spider|slurp|preview|monitor|curl|wget|python-requests|headless',
        re.IGNORECASE,
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if self.should_count(request, response):
            try:
                PageView.record(timezone.localdate(), request.path[:255])
            except Exception:
                logger.exception('ページビューの記録に失敗しました')
        return response

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
