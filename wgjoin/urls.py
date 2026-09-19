# wgjoin/urls.py
#
# コールバックの URL は Google Cloud と GitHub App に登録する（WG ごとには変えない）。
#   /wg/join/google/callback/
#   /wg/join/github/callback/

from django.urls import path

from . import views

app_name = 'wgjoin'

urlpatterns = [
    path('<int:pk>/join/', views.start, name='start'),
    path('<int:pk>/join/google/', views.google_start, name='google_start'),
    path('<int:pk>/join/github/', views.github_step, name='github_step'),
    path('<int:pk>/join/github/start/', views.github_start, name='github_start'),
    path('join/google/callback/', views.google_callback, name='google_callback'),
    path('join/github/callback/', views.github_callback, name='github_callback'),
]
