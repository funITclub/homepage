# home/urls.py

from django.urls import path

from . import views

app_name = 'home'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('wg/', views.WgListView.as_view(), name='wg_list'),
    path('works/', views.WorkListView.as_view(), name='work_list'),
    path('join/', views.JoinView.as_view(), name='join'),

    # サブアプリ未実装のためのプレースホルダ
    path('coming-soon/', views.ComingSoonView.as_view(), name='coming_soon'),
]
