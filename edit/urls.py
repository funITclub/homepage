# edit/urls.py

from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views

app_name = 'edit'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),

    path('login/', auth_views.LoginView.as_view(
        template_name='edit/login.html',
        redirect_authenticated_user=True,
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # 各コンテンツの編集画面
    path('news/', include('news.urls', namespace='news')),
    path('', include('catalog.urls', namespace='catalog')),
]
