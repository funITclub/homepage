# catalog/urls.py
#
# edit/urls.py から include される（URL 名は edit:catalog:... になる）。

from django.urls import path

from . import views

app_name = 'catalog'

urlpatterns = [
    path('wg/', views.WgListView.as_view(), name='wg_list'),
    path('wg/new/', views.WgCreateView.as_view(), name='wg_create'),
    path('wg/<int:pk>/edit/', views.WgUpdateView.as_view(), name='wg_update'),
    path('wg/<int:pk>/delete/', views.WgDeleteView.as_view(), name='wg_delete'),

    path('works/', views.WorkListView.as_view(), name='work_list'),
    path('works/new/', views.WorkCreateView.as_view(), name='work_create'),
    path('works/<int:pk>/edit/', views.WorkUpdateView.as_view(), name='work_update'),
    path('works/<int:pk>/delete/', views.WorkDeleteView.as_view(), name='work_delete'),
]
