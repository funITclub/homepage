# countdown/urls.py

from django.urls import path

from . import views

app_name = 'countdown'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    # ID で入る、または新しく作る
    path('enter/', views.EnterView.as_view(), name='enter'),

    # メール通知。確認・解除はメールのリンクから、送信は毎日0時に GitHub Actions から
    path('notify/confirm/<str:token>/', views.NotifyConfirmView.as_view(), name='notify_confirm'),
    path('notify/stop/<str:token>/', views.NotifyStopView.as_view(), name='notify_stop'),
    path('notify/run/', views.NotifyRunView.as_view(), name='notify_run'),

    # ID を使わない共有ボード
    path('events/', views.EventListView.as_view(), name='event_list'),
    path('events/create/', views.EventCreateView.as_view(), name='event_create'),
    path('events/<int:pk>/update/', views.EventUpdateView.as_view(), name='event_update'),
    path('events/<int:pk>/delete/', views.EventDeleteView.as_view(), name='event_delete'),

    # ID ごとの一覧。ほかの画面の URL と重ならないよう最後に置く
    path('<str:code>/', views.EventListView.as_view(), name='board_list'),
    path('<str:code>/mail/', views.MailSettingsView.as_view(), name='board_mail'),
    path('<str:code>/create/', views.EventCreateView.as_view(), name='board_create'),
    path('<str:code>/<int:pk>/update/', views.EventUpdateView.as_view(), name='board_update'),
    path('<str:code>/<int:pk>/delete/', views.EventDeleteView.as_view(), name='board_delete'),
]
