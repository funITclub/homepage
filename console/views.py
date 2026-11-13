# console/views.py

from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.utils import timezone
from django.views.generic import TemplateView

from catalog.models import Wg, Work
from config import subapps

from .models import PageView


def installed_apps():
    """いま載っているサブアプリ。[(フォルダー, アプリ名, URL), …]（config/subapps.py）。"""
    return subapps.discover(settings.BASE_DIR)


def catalog_titles():
    """URL のパス → WG・成果物の名前。一覧に登録した URL から、アプリに名前を付けるのに使う。"""
    titles = []
    for wg in Wg.objects.all():
        titles += [(wg.app_url, f'{wg.code} {wg.name}'), (wg.link_url, f'{wg.code} {wg.name}')]
    titles += [(work.url, work.title) for work in Work.objects.all()]
    return [(urlsplit(url).path, title) for url, title in titles if url]


def views_by_app(per_path):
    """パスごとの回数を、サブアプリ（wg/・works/ の配下）ごとにまとめる。

    入れ子のとき（/welfare/ と /welfare/activity/）は、長いほうの URL に数える。
    期間中に1回も見られていないアプリも 0 回として出す。
    戻り値は {'wg': [行, …], 'works': [行, …]}。行は回数の多い順。
    """
    apps = [
        {'folder': folder, 'name': name, 'prefix': f'/{url}/', 'n': 0, 'pages': 0}
        for folder, name, url in installed_apps()
    ]
    # 長い URL から当てる
    by_length = sorted(apps, key=lambda app: len(app['prefix']), reverse=True)
    for path, n in per_path.items():
        for app in by_length:
            if path.startswith(app['prefix']):
                app['n'] += n
                app['pages'] += 1
                break

    titles = catalog_titles()
    grouped = {folder: [] for folder in subapps.FOLDERS}
    for app in apps:
        app['title'] = next(
            (title for path, title in titles if path.startswith(app['prefix'])), '')
        grouped[app['folder']].append(app)
    for rows in grouped.values():
        rows.sort(key=lambda app: (-app['n'], app['prefix']))
        top = rows[0]['n'] if rows else 0
        for app in rows:
            app['percent'] = round(app['n'] * 100 / top) if top else 0
    return grouped


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
    """ページビュー数。期間の合計・WG と成果物ごと・ページごとの順位・日ごとの推移を出す。"""

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

        per_path = dict(rows.values('path').annotate(n=Sum('count')).values_list('path', 'n'))
        ranking = [
            {'path': path, 'n': n}
            for path, n in sorted(per_path.items(), key=lambda item: (-item[1], item[0]))
        ][:self.RANKING_LIMIT]
        top = ranking[0]['n'] if ranking else 0
        apps = views_by_app(per_path)
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
            'page_count': len(per_path),
            'apps': apps,
            'app_groups': [('WG（作っている途中）', apps['wg']), ('成果物（公表したもの）', apps['works'])],
        })
        return context
