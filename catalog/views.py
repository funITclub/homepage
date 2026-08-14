# catalog/views.py
#
# WG紹介・成果物紹介の編集。編集画面（/edit/）の一部でログイン必須。

from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from edit.views import EditorMixin

from .forms import WgForm, WorkForm
from .models import Wg, Work

WG_URL = reverse_lazy('edit:catalog:wg_list')
WORK_URL = reverse_lazy('edit:catalog:work_list')


# ---------- WG ----------

class WgListView(EditorMixin, ListView):
    """WGの一覧（下書きも含めて全件）。"""

    model = Wg
    template_name = 'catalog/wg_list.html'
    context_object_name = 'wg_list'
    section = 'wg'


class WgCreateView(EditorMixin, CreateView):
    """WGを追加する。"""

    model = Wg
    form_class = WgForm
    template_name = 'catalog/wg_form.html'
    success_url = WG_URL
    section = 'wg'
    extra_context = {'heading': 'WGを追加', 'submit_label': '追加する'}

    def form_valid(self, form):
        messages.success(self.request, 'WGを追加しました。')
        return super().form_valid(form)


class WgUpdateView(EditorMixin, UpdateView):
    """WGを編集する。"""

    model = Wg
    form_class = WgForm
    template_name = 'catalog/wg_form.html'
    success_url = WG_URL
    section = 'wg'
    extra_context = {'heading': 'WGを編集', 'submit_label': '保存する'}

    def form_valid(self, form):
        messages.success(self.request, 'WGを保存しました。')
        return super().form_valid(form)


class WgDeleteView(EditorMixin, DeleteView):
    """WGを削除する（確認ページを挟む）。"""

    model = Wg
    template_name = 'catalog/wg_confirm_delete.html'
    success_url = WG_URL
    section = 'wg'

    def form_valid(self, form):
        messages.success(self.request, 'WGを削除しました。')
        return super().form_valid(form)


# ---------- 成果物 ----------

class WorkListView(EditorMixin, ListView):
    """成果物の一覧（下書きも含めて全件）。"""

    model = Work
    template_name = 'catalog/work_list.html'
    context_object_name = 'work_list'
    section = 'works'


class WorkCreateView(EditorMixin, CreateView):
    """成果物を追加する。"""

    model = Work
    form_class = WorkForm
    template_name = 'catalog/work_form.html'
    success_url = WORK_URL
    section = 'works'
    extra_context = {'heading': '成果物を追加', 'submit_label': '追加する'}

    def form_valid(self, form):
        messages.success(self.request, '成果物を追加しました。')
        return super().form_valid(form)


class WorkUpdateView(EditorMixin, UpdateView):
    """成果物を編集する。"""

    model = Work
    form_class = WorkForm
    template_name = 'catalog/work_form.html'
    success_url = WORK_URL
    section = 'works'
    extra_context = {'heading': '成果物を編集', 'submit_label': '保存する'}

    def form_valid(self, form):
        messages.success(self.request, '成果物を保存しました。')
        return super().form_valid(form)


class WorkDeleteView(EditorMixin, DeleteView):
    """成果物を削除する（確認ページを挟む）。"""

    model = Work
    template_name = 'catalog/work_confirm_delete.html'
    success_url = WORK_URL
    section = 'works'

    def form_valid(self, form):
        messages.success(self.request, '成果物を削除しました。')
        return super().form_valid(form)
