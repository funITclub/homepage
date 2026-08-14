from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # 管理画面。テーブルの中身を一覧・検索するために使う（編集の主導線は /edit/）。
    # LoginRequiredMiddleware があるので、未ログインだと /edit/login/ に飛ぶ。
    path('admin/', admin.site.urls),

    # 公開サイト（認証なし）
    path('', include('home.urls', namespace='home')),

    # 編集画面（ログイン必須）。公開サイトからはリンクせず、この URL を直接開いて使う。
    # お知らせ・WG紹介・成果物紹介の編集はすべてこの下にある。
    path('edit/', include('edit.urls', namespace='edit')),
]
