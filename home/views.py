# home/views.py
#
# 認証なしの公開サイト。掲載内容は編集画面（/edit/）で編集し、
# ここでは DB から読んで表示するだけ。各WGのサブアプリはまだ無いため、
# リンク先が未設定のものは「作成中」ページへ集約する。
#
# LoginRequiredMiddleware で全ビューが既定ログイン必須になっているため、
# このファイルのビューだけ login_not_required で公開している。

from django.contrib.auth.decorators import login_not_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from catalog.models import Wg, Work
from news.models import News


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
    news_limit = 3

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
class JoinView(NavMixin, TemplateView):
    """参加する。"""

    template_name = 'home/join.html'
    nav = 'join'


@method_decorator(login_not_required, name='dispatch')
class ComingSoonView(NavMixin, TemplateView):
    """サブアプリ（WGごとのWebアプリ・成果物ページ）の作成中プレースホルダ。"""

    template_name = 'home/coming_soon.html'
    nav = ''
