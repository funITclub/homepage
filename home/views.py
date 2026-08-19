# home/views.py
#
# 認証なしの公開サイト。掲載内容は編集画面（/edit/）で編集し、
# ここでは DB から読んで表示するだけ。各WGのサブアプリはまだ無いため、
# リンク先が未設定のものは「作成中」ページへ集約する。
#
# LoginRequiredMiddleware で全ビューが既定ログイン必須になっているため、
# このファイルのビューだけ login_not_required で公開している。

import logging
import smtplib

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView

from catalog.models import Wg, Work
from news.models import News

from .forms import JoinForm

logger = logging.getLogger(__name__)


class NavMixin:
    """テンプレートでナビの現在地を判定するための識別子を渡す。"""

    nav = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['nav'] = self.nav
        return context


@method_decorator(login_not_required, name='dispatch')
class IndexView(NavMixin, TemplateView):
    """TOP。ヒーロー・活動サマリ・お知らせ。

    活動サマリの件数は、公開中のWG（活動中のみ）と成果物の登録数に連動する。
    """

    #: TOP に載せるお知らせの件数
    news_limit = 5

    template_name = 'home/index.html'
    nav = 'top'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['news_list'] = News.objects.published()[:self.news_limit]
        context['active_wg_count'] = Wg.objects.published().filter(status=Wg.ACTIVE).count()
        context['work_count'] = Work.objects.published().count()
        return context


@method_decorator(login_not_required, name='dispatch')
class WgListView(NavMixin, TemplateView):
    """WG一覧。"""

    template_name = 'home/wg_list.html'
    nav = 'wg'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['wg_list'] = Wg.objects.published()
        return context


@method_decorator(login_not_required, name='dispatch')
class WorkListView(NavMixin, TemplateView):
    """成果物一覧。"""

    template_name = 'home/work_list.html'
    nav = 'works'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['work_list'] = Work.objects.published()
        return context


@method_decorator(login_not_required, name='dispatch')
class JoinView(NavMixin, FormView):
    """参加する。申し込みフォームから参加申請を受け取る。

    申し込みは DB に残さず、事務局（settings.JOIN_NOTIFY_EMAIL）へのメールと
    申込者への自動返信で完結する（hirahira_room のお問い合わせと同じ作り）。
    """

    template_name = 'home/join.html'
    nav = 'join'
    form_class = JoinForm
    success_url = reverse_lazy('home:join')

    def form_valid(self, form):
        try:
            form.send_email()
        except (smtplib.SMTPException, OSError):
            # SMTP の設定漏れや送信障害で 500 にせず、フォームに戻して知らせる。
            logger.exception('参加フォームのメール送信に失敗しました')
            form.add_error(None, 'メールの送信に失敗しました。'
                                 'お手数ですが時間をおいて再度お試しください。')
            return self.form_invalid(form)

        messages.success(self.request, '参加の申し込みを受け付けました。'
                                       '確認のメールをお送りしましたのでご確認ください。')
        logger.info('参加申し込みを受け付けました')
        return super().form_valid(form)


@method_decorator(login_not_required, name='dispatch')
class ComingSoonView(NavMixin, TemplateView):
    """サブアプリ（WGごとのWebアプリ・成果物ページ）の作成中プレースホルダ。"""

    template_name = 'home/coming_soon.html'
    nav = ''
