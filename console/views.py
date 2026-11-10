# console/views.py

from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.utils import timezone
from django.views.generic import TemplateView

from .models import PageView


class ConsoleMixin(LoginRequiredMixin):
    """コンソールのビュー共通。ログイン必須＋ナビの現在地。"""

    login_url = 'console:login'

    #: base.html のナビで現在地を示す識別子
    section = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['section'] = self.section
        return context


class IndexView(ConsoleMixin, TemplateView):
    """コンソールのメニュー。"""

    template_name = 'console/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        context['today_views'] = (
            PageView.objects.filter(date=today).aggregate(n=Sum('count'))['n'] or 0
        )
        return context


class PageViewsView(ConsoleMixin, TemplateView):
    """ページビュー数。期間の合計・日ごとの推移・ページごとの順位を出す。"""

    template_name = 'console/pageviews.html'
    section = 'pageviews'

    #: 選べる期間（日数）。先頭が既定。
    PERIODS = (30, 7, 90, 365)

    #: 順位表に出すページの数
    RANKING_LIMIT = 50

    def get_days(self):
        try:
            days = int(self.request.GET.get('days', ''))
        except ValueError:
            return self.PERIODS[0]
        return days if days in self.PERIODS else self.PERIODS[0]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        days = self.get_days()
        end = timezone.localdate()
        start = end - timedelta(days=days - 1)
        rows = PageView.objects.filter(date__range=(start, end))

        per_day = dict(rows.values('date').annotate(n=Sum('count')).values_list('date', 'n'))
        peak = max(per_day.values(), default=0)
        daily = []
        for offset in range(days):
            day = end - timedelta(days=offset)
            count = per_day.get(day, 0)
            daily.append({
                'date': day,
                'count': count,
                'percent': round(count * 100 / peak) if peak else 0,
            })

        ranking = list(
            rows.values('path').annotate(n=Sum('count')).order_by('-n', 'path')[:self.RANKING_LIMIT]
        )
        top = ranking[0]['n'] if ranking else 0
        for row in ranking:
            row['percent'] = round(row['n'] * 100 / top) if top else 0

        context.update({
            'days': days,
            'periods': self.PERIODS,
            'start': start,
            'end': end,
            'total': sum(per_day.values()),
            'today': per_day.get(end, 0),
            'average': round(sum(per_day.values()) / days, 1),
            'daily': daily,
            'ranking': ranking,
            'page_count': rows.values('path').distinct().count(),
        })
        return context
