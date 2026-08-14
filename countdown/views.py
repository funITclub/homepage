# countdown/views.py
#
# 誰でも読み書きできる公開ボード。会員登録もログインも持たないため、
# LoginRequiredMiddleware の対象から login_not_required で外している。
# 公開サイト（/）とは相互にリンクせず、成果物ページに URL を載せて辿る想定。

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import generic

from .forms import CountEventForm
from .models import CountEvent

EVENT_LIST_URL = reverse_lazy('countdown:event_list')


@method_decorator(login_not_required, name='dispatch')
class IndexView(generic.TemplateView):
    """アプリの紹介ページ。"""

    template_name = 'countdown/index.html'
    extra_context = {'nav': 'index'}


@method_decorator(login_not_required, name='dispatch')
class EventListView(generic.ListView):
    """登録された出来事・予定の一覧。未来はカウントダウン、過去はカウントアップ。"""

    model = CountEvent
    template_name = 'countdown/event_list.html'
    context_object_name = 'events'
    extra_context = {'nav': 'list'}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        events = list(context['events'])
        today = timezone.localdate()

        # 予定（当日を含む未来）は近い順、出来事（過去）は新しい順に並べる
        context['upcoming_events'] = sorted(
            [e for e in events if e.date >= today], key=lambda e: e.date
        )
        context['past_events'] = sorted(
            [e for e in events if e.date < today], key=lambda e: e.date, reverse=True
        )
        context['today'] = today
        return context


@method_decorator(login_not_required, name='dispatch')
class EventCreateView(generic.CreateView):
    """出来事・予定を登録する。"""

    model = CountEvent
    form_class = CountEventForm
    template_name = 'countdown/event_form.html'
    success_url = EVENT_LIST_URL
    extra_context = {'nav': 'create', 'heading': '出来事・予定を登録', 'submit_label': '登録する'}

    def form_valid(self, form):
        messages.success(self.request, f'「{form.instance.name}」を登録しました。')
        return super().form_valid(form)


@method_decorator(login_not_required, name='dispatch')
class EventUpdateView(generic.UpdateView):
    """出来事・予定を編集する。"""

    model = CountEvent
    form_class = CountEventForm
    template_name = 'countdown/event_form.html'
    success_url = EVENT_LIST_URL
    extra_context = {'nav': 'list', 'heading': '出来事・予定を編集', 'submit_label': '保存する'}

    def form_valid(self, form):
        messages.success(self.request, f'「{form.instance.name}」を保存しました。')
        return super().form_valid(form)


@method_decorator(login_not_required, name='dispatch')
class EventDeleteView(generic.DeleteView):
    """出来事・予定を削除する（確認ページを挟む）。"""

    model = CountEvent
    template_name = 'countdown/event_confirm_delete.html'
    extra_context = {'nav': 'list'}
    success_url = EVENT_LIST_URL

    def form_valid(self, form):
        messages.success(self.request, f'「{self.object.name}」を削除しました。')
        return super().form_valid(form)
