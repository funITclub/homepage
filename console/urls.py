# console/urls.py
#
# 運営コンソール（/console/）。掲載内容を書き換える /edit/ とは分けて、サイトの様子を見る画面を置く。
# アカウントは /edit/ と共通（同じユーザー・同じパスワード）。

from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.urls import path

from . import views

app_name = 'console'


def protected(view):
    # LoginRequiredMiddleware は view の login_url を見る。付けないと /edit/login/ に飛ぶ。
    return login_required(view, login_url='console:login')


urlpatterns = [
    path('', protected(views.IndexView.as_view()), name='index'),
    path('pageviews/', protected(views.PageViewsView.as_view()), name='pageviews'),

    path('login/', auth_views.LoginView.as_view(
        template_name='console/login.html',
        redirect_authenticated_user=True,
        next_page='console:index',
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='console:login'), name='logout'),
]
