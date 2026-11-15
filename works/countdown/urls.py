# countdown/urls.py

from django.urls import path

from . import api, views

app_name = 'countdown'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    # ID で入る、または新しく作る
    path('enter/', views.EnterView.as_view(), name='enter'),

    # メール通知。確認・解除はメールのリンクから、送信は毎日0時に GitHub Actions から
    path('notify/confirm/<str:token>/', views.NotifyConfirmView.as_view(), name='notify_confirm'),
    path('notify/stop/<str:token>/', views.NotifyStopView.as_view(), name='notify_stop'),
    path('notify/run/', views.NotifyRunView.as_view(), name='notify_run'),

    # ID を使わない共有ボード。画面は React で、URL は React にする前と同じ。
    # どれも同じ入れ物を返し、何を描くかは React（frontend/countdown/src/EventsPage.tsx）が
    # アドレスを見て決める。データは api/ から読み書きする（countdown/api.py）
    path('events/', views.AppView.as_view(), name='event_list'),
    path('events/create/', views.AppView.as_view(), name='event_create'),
    path('events/<int:pk>/update/', views.AppView.as_view(), name='event_update'),
    path('events/<int:pk>/delete/', views.AppView.as_view(), name='event_delete'),
    path('events/api/', api.EventsAPI.as_view(), name='event_api'),
    path('events/api/<int:pk>/', api.EventAPI.as_view(), name='event_api_item'),

    # ID ごとの一覧。ほかの画面の URL と重ならないよう最後に置く
    path('<str:code>/', views.AppView.as_view(), name='board_list'),
    path('<str:code>/mail/', views.MailSettingsView.as_view(), name='board_mail'),
    path('<str:code>/create/', views.AppView.as_view(), name='board_create'),
    path('<str:code>/<int:pk>/update/', views.AppView.as_view(), name='board_update'),
    path('<str:code>/<int:pk>/delete/', views.AppView.as_view(), name='board_delete'),
    path('<str:code>/api/', api.EventsAPI.as_view(), name='board_api'),
    path('<str:code>/api/<int:pk>/', api.EventAPI.as_view(), name='board_api_item'),
]
