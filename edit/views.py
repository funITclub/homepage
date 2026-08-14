# edit/views.py
#
# 編集画面の共通部分。ログイン必須で、公開サイトとは相互にリンクしない。
# 各編集画面（news / catalog）はここの EditorMixin と base.html を使う。

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from catalog.models import Wg, Work
from news.models import News


class EditorMixin(LoginRequiredMixin):
    """編集画面のビュー共通。ログイン必須＋ナビの現在地。"""

    #: base.html のナビで現在地を示す識別子（news / wg / works）
    section = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['section'] = self.section
        return context


class IndexView(EditorMixin, TemplateView):
    """編集のメニュー。各項目の登録件数を出す。"""

    template_name = 'edit/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['news_count'] = News.objects.count()
        context['wg_count'] = Wg.objects.count()
        context['work_count'] = Work.objects.count()
        return context
