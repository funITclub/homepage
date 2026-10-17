from django.conf import settings
from django.contrib import admin
from django.urls import path, include

from . import subapps

urlpatterns = [
    # 管理画面。テーブルの中身を一覧・検索するために使う（編集の主導線は /edit/）。
    # LoginRequiredMiddleware があるので、未ログインだと /edit/login/ に飛ぶ。
    path('admin/', admin.site.urls),

    # 公開サイト（認証なし）
    path('', include('home.urls', namespace='home')),

    # WG への参加（認証なし。本人の Google・GitHub のログインで確かめる）。
    # /wg/ 自体は home の WG 一覧で、この下の /wg/<id>/join/ などを持つ。
    path('wg/', include('wgjoin.urls', namespace='wgjoin')),

    # 編集画面（ログイン必須）。公開サイトからはリンクせず、この URL を直接開いて使う。
    # お知らせ・WG紹介・成果物紹介の編集はすべてこの下にある。
    path('edit/', include('edit.urls', namespace='edit')),

]

# サブアプリ（works/ と wg/ の配下）は、置かれているものを自動で足す（config/subapps.py）。
# フォルダー名がそのまま URL と名前空間になる（works/countdown → /countdown/）。
# 公開サイトとは相互にリンクせず、一覧に登録した URL から辿る（config/gate.py）。
urlpatterns += [
    path(f'{name}/', include(f'{folder}.{name}.urls', namespace=name))
    for folder, name in subapps.discover(settings.BASE_DIR)
]
