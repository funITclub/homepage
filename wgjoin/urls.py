# wgjoin/urls.py
#
# GitHub App に登録するコールバックの URL は /wg/join/github/callback/（WG ごとには変えない）。

from django.urls import path

from . import views

app_name = 'wgjoin'

urlpatterns = [
    path('<int:pk>/join/', views.start, name='start'),
    path('<int:pk>/join/sent/', views.sent, name='sent'),
    path('join/verify/<str:token>/', views.verify, name='verify'),
    path('<int:pk>/join/github/', views.github_step, name='github_step'),
    path('<int:pk>/join/github/start/', views.github_start, name='github_start'),
    path('join/github/callback/', views.github_callback, name='github_callback'),
]
