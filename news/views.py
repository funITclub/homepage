# news/views.py
#
# お知らせの編集。編集画面（/edit/）の一部でログイン必須。

from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from edit.views import EditorMixin

from .forms import NewsForm
from .models import News

EDITOR_URL = reverse_lazy('edit:news:editor_list')


class EditorListView(EditorMixin, ListView):
    """お知らせの一覧（下書きも含めて全件）。"""

    model = News
    template_name = 'news/editor_list.html'
    context_object_name = 'news_list'
    section = 'news'


class EditorCreateView(EditorMixin, CreateView):
    """お知らせを追加する。"""

    model = News
    form_class = NewsForm
    template_name = 'news/editor_form.html'
    success_url = EDITOR_URL
    section = 'news'
    extra_context = {'heading': 'お知らせを追加', 'submit_label': '追加する'}

    def form_valid(self, form):
        messages.success(self.request, 'お知らせを追加しました。')
        return super().form_valid(form)


class EditorUpdateView(EditorMixin, UpdateView):
    """お知らせを編集する。"""

    model = News
    form_class = NewsForm
    template_name = 'news/editor_form.html'
    success_url = EDITOR_URL
    section = 'news'
    extra_context = {'heading': 'お知らせを編集', 'submit_label': '保存する'}

    def form_valid(self, form):
        messages.success(self.request, 'お知らせを保存しました。')
        return super().form_valid(form)


class EditorDeleteView(EditorMixin, DeleteView):
    """お知らせを削除する（確認ページを挟む）。"""

    model = News
    template_name = 'news/editor_confirm_delete.html'
    success_url = EDITOR_URL
    section = 'news'

    def form_valid(self, form):
        messages.success(self.request, 'お知らせを削除しました。')
        return super().form_valid(form)
