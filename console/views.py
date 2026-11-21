# console/views.py

from datetime import date, timedelta
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
    """ページビュー数。その日の詳細（WG と成果物ごと・ページごと）を主に、下に日ごとの経過を出す。

    その日は既定で今日。?date=YYYY-MM-DD で経過の範囲内の別の日を見られる（経過の表の日付から飛ぶ）。
    """

    template_name = 'console/pageviews.html'
    section = 'pageviews'

    #: 経過で選べる期間（日数）。ボタンはこの順（少ない順）に並ぶ。
    PERIODS = (7, 30, 90, 365)

    #: 経過の既定の期間（日数）
    DEFAULT_DAYS = 30

    #: 順位表に出すページの数
    RANKING_LIMIT = 50

    def get_days(self):
        try:
            days = int(self.request.GET.get('days', ''))
        except ValueError:
            return self.DEFAULT_DAYS
        return days if days in self.PERIODS else self.DEFAULT_DAYS

    def get_day(self, today):
        """詳細を出す日。今日から PERIODS の最大日数までさかのぼれる。それ以外は今日。"""
        try:
            day = date.fromisoformat(self.request.GET.get('date', ''))
        except ValueError:
            return today
        earliest = today - timedelta(days=max(self.PERIODS) - 1)
        return day if earliest <= day <= today else today

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        end = timezone.localdate()

        # その日の詳細
        day = self.get_day(end)
        per_path = dict(
            PageView.objects.filter(date=day)
            .values('path').annotate(n=Sum('count')).values_list('path', 'n'))
        ranking = [
            {'path': path, 'n': n}
            for path, n in sorted(per_path.items(), key=lambda item: (-item[1], item[0]))
        ][:self.RANKING_LIMIT]
        top = ranking[0]['n'] if ranking else 0
        for row in ranking:
            row['percent'] = round(row['n'] * 100 / top) if top else 0
        apps = views_by_app(per_path)
        previous_day = day - timedelta(days=1)
        previous = PageView.objects.filter(date=previous_day).aggregate(n=Sum('count'))['n'] or 0

        # 経過（日ごと）
        days = self.get_days()
        start = end - timedelta(days=days - 1)
        per_day = dict(
            PageView.objects.filter(date__range=(start, end))
            .values('date').annotate(n=Sum('count')).values_list('date', 'n'))
        peak = max(per_day.values(), default=0)
        daily = []
        for offset in range(days):
            d = end - timedelta(days=offset)
            count = per_day.get(d, 0)
            daily.append({
                'date': d,
                'count': count,
                'percent': round(count * 100 / peak) if peak else 0,
            })

        context.update({
            'day': day,
            'is_today': day == end,
            'day_total': sum(per_path.values()),
            'previous_day': previous_day,
            'previous': previous,
            'page_count': len(per_path),
            'ranking': ranking,
            'apps': apps,
            'app_groups': [('WG（作っている途中）', apps['wg']), ('成果物（公表したもの）', apps['works'])],
            'days': days,
            'periods': self.PERIODS,
            'start': start,
            'end': end,
            'total': sum(per_day.values()),
            'average': round(sum(per_day.values()) / days, 1),
            'daily': daily,
        })
        return context
