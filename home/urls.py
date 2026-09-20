# home/urls.py

from django.urls import path

from . import views

app_name = 'home'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('news/', views.NewsListView.as_view(), name='news_list'),
    path('wg/', views.WgListView.as_view(), name='wg_list'),
    path('works/', views.WorkListView.as_view(), name='work_list'),
    path('join/', views.JoinView.as_view(), name='join'),
    path('join/apply/', views.JoinApplyView.as_view(), name='join_apply'),
    path('join/apply/done/', views.JoinDoneView.as_view(), name='join_apply_done'),

    # WG 立ち上げガイド（資料）。ナビには置かず、参加の完了画面とメールから案内する。
    path('guide/', views.GuideView.as_view(), name='guide'),

    # サブアプリ未実装のためのプレースホルダ
    path('coming-soon/', views.ComingSoonView.as_view(), name='coming_soon'),
]
