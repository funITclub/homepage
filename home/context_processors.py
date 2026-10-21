# home/context_processors.py
#
# 公開サイトの <link rel="canonical"> と OGP に使う、正規の URL の頭。
# 既定のホスト名（*.azurewebsites.net）で開かれても、検索結果は funitclub.org に寄せる。

from django.conf import settings


def site_url(request):
    """{{ site_url }} で正規の URL の頭（末尾のスラッシュなし）を参照できるようにする。"""
    return {'site_url': settings.SITE_URL.rstrip('/')}
