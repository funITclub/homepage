# news/urls.py
#
# edit/urls.py から include される（URL 名は edit:news:... になる）。

from django.urls import path

from . import views

app_name = 'news'

urlpatterns = [
    path('', views.EditorListView.as_view(), name='editor_list'),
    path('new/', views.EditorCreateView.as_view(), name='editor_create'),
    path('<int:pk>/edit/', views.EditorUpdateView.as_view(), name='editor_update'),
    path('<int:pk>/delete/', views.EditorDeleteView.as_view(), name='editor_delete'),
]
