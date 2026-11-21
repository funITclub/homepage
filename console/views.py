# console/views.py

import importlib
import importlib.util
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from catalog.models import Wg, Work
from config import subapps

from . import members
from .middleware import record_beacon
from .models import ActionCount, DailyVisitors, PageView


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


#: クラブへの参加（/join/）のページ。並びは画面の並び
JOIN_PAGES = (
    ('/join/', '参加案内（参加する）'),
    ('/join/apply/', '申し込みページ'),
    ('/join/apply/done/', '受付完了ページ'),
)


def page_name(path, title):
    """ページの名前。<title> の「 — fun IT club」などの後ろを落としたもの。題名が無ければパス。"""
    for separator in (' — ', ' | ', ' - '):
        title = title.split(separator)[0]
    return title.strip() or path


def count_by_name(rows):
    """[(パス, 題名, 回数), …] を、ページの名前ごとに足して回数の多い順に並べる。"""
    counts = {}
    for path, title, n in rows:
        name = page_name(path, title)
        counts[name] = counts.get(name, 0) + n
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def with_percent(pages):
    """[(名前, 回数), …] → 表の行。棒の長さはいちばん多いページを 100 とする。"""
    top = max((n for _name, n in pages), default=0)
    return [{'name': name, 'n': n, 'percent': round(n * 100 / top) if top else 0}
            for name, n in pages]


def app_counter(folder, name):
    """アプリが自分で数えている画面ごとの回数（<アプリ>/pageviews.py の console_counts）。

    React などで画面がブラウザの中で切りかわるアプリは、パスごとの記録では数えきれないので、
    これがあればそちらを使う。無ければ None。
    """
    module_name = f'{folder}.{name}.pageviews'
    try:
        if importlib.util.find_spec(module_name) is None:
            return None
    except ModuleNotFoundError:
        return None
    return getattr(importlib.import_module(module_name), 'console_counts', None)


def known_titles(prefixes):
    """prefixes の下で、これまでに1回でも見られた（題名の分かる）ページ。{パス: いちばん新しい題名}。"""
    query = Q()
    for prefix in prefixes:
        query |= Q(path__startswith=prefix)
    if not prefixes:
        return {}
    # 題名を残す前の記録（題名が空）は使わない。パスに ID などが入っていることがあり、
    # 名前の無いページを URL のまま並べたくないため
    titles = {}
    rows = PageView.objects.filter(query).exclude(title='').order_by('date')
    for path, title in rows.values_list('path', 'title'):
        titles[path] = title
    return titles


def views_by_app(day, rows):
    """その日の回数を、サブアプリ（wg/・works/ の配下）ごと・ページの名前ごとにまとめる。

    rows は [(パス, 題名, 回数), …]。アプリのページは、今日見られていなくても、これまでに
    見られたことがあれば 0 回として出す（ページごとの回数を一覧で見られるように）。入れ子のとき（/welfare/ と /welfare/activity/）は、
    長いほうの URL に数える。同じ WG・成果物のアプリ（一覧に登録した名前が同じもの）は1つにまとめる。

    戻り値は {'wg': [WG, …], 'works': [成果物, …]}。どのアプリにも入らないページは捨てる。
    WG・成果物は {'title', 'n', 'apps': [{'name', 'prefix', 'n', 'pages'}, …]} で、回数の多い順。
    """
    apps = [
        {'folder': folder, 'name': name, 'prefix': f'/{url}/', 'rows': []}
        for folder, name, url in installed_apps()
    ]
    by_length = sorted(apps, key=lambda app: len(app['prefix']), reverse=True)
    today = {row[0] for row in rows}
    rows = list(rows) + [
        (path, title, 0)
        for path, title in known_titles([app['prefix'] for app in apps]).items()
        if path not in today
    ]
    for row in rows:
        app = next((app for app in by_length if row[0].startswith(app['prefix'])), None)
        if app:
            app['rows'].append(row)

    titles = catalog_titles()
    grouped = {folder: {} for folder in subapps.FOLDERS}
    for app in apps:
        counter = app_counter(app['folder'], app['name'])
        pages = counter(day) if counter else count_by_name(app.pop('rows'))
        app.pop('rows', None)
        app['n'] = sum(n for _name, n in pages)
        app['pages'] = with_percent(pages)
        title = next(
            (title for path, title in titles if path.startswith(app['prefix'])), app['name'])
        group = grouped[app['folder']].setdefault(
            title, {'title': title, 'n': 0, 'page_count': 0, 'apps': []})
        group['n'] += app['n']
        group['page_count'] += len(app['pages'])
        group['apps'].append(app)

    result = {}
    for folder, groups in grouped.items():
        for group in groups.values():
            group['apps'].sort(key=lambda app: app['prefix'])
        result[folder] = sorted(groups.values(), key=lambda group: (-group['n'], group['title']))
    return result


def add_wg_join(groups, per_path, actions):
    """WG の並び（views_by_app の 'wg'）に、WG ごとの参加の回数（join）を足す。

    参加を受け付けている WG はアプリが無くても並べる。join は
    [{'name', 'n'}, …]（参加ページの表示・「確認のメールを送る」・「GitHub でログインして登録する」）。
    """
    by_title = {group['title']: group for group in groups}
    for wg in Wg.objects.published().order_by('code'):
        if not wg.accepts_join:
            continue
        title = f'{wg.code} {wg.name}'
        group = by_title.get(title)
        if group is None:
            group = {'title': title, 'n': 0, 'page_count': 0, 'apps': []}
            by_title[title] = group
            groups.append(group)
        views = per_path.get(f'/wg/{wg.pk}/join/', 0)
        group['n'] += views
        group['join'] = [{'name': '参加ページ（アドレスの入力）', 'n': views}] + [
            {'name': label, 'n': actions.get(f'{key}:{wg.pk}', 0)}
            for key, label in ActionCount.WG_JOIN_ACTIONS.items()
        ]
    groups.sort(key=lambda group: (-group['n'], group['title']))


class ConsoleMixin(LoginRequiredMixin):
    """コンソールのビュー共通。ログイン必須＋ナビの現在地。"""

    login_url = 'console:login'

    #: base.html のナビで現在地を示す識別子
    section = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['section'] = self.section
        return context


def today_summary(day):
    """その日の、クラブへの参加・WG・成果物の回数。コンソールのトップとページビューの画面で使う。

    total は表に出すページの表示回数の合計（ボタンの回数は入れない）。トップ・お知らせなど
    表に出さないページは入れない（表の数字と合うように）。
    """
    rows = list(PageView.objects.filter(date=day).values_list('path', 'title', 'count'))
    per_path = {path: n for path, _title, n in rows}

    apps = views_by_app(day, rows)
    actions = dict(ActionCount.objects.filter(date=day).values_list('name', 'count'))
    add_wg_join(apps['wg'], per_path, actions)
    join_pages = [{'name': label, 'n': per_path.get(path, 0)} for path, label in JOIN_PAGES]

    total = (sum(page['n'] for page in join_pages)
             + sum(group['n'] for groups in apps.values() for group in groups))
    return {
        'day': day,
        'total': total,
        'join_pages': join_pages,
        'join_applied': actions.get('join_apply', 0),
        'apps': apps,
        'app_groups': [('WG（作っている途中）', apps['wg']), ('成果物（公表したもの）', apps['works'])],
    }


class IndexView(ConsoleMixin, TemplateView):
    """コンソールのメニュー。"""

    template_name = 'console/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['today_visitors'] = DailyVisitors.on(timezone.localdate())
        context['members'] = members.summary()
        return context


class PageViewsView(ConsoleMixin, TemplateView):
    """今日のページビュー。クラブへの参加・WG ごと・成果物ごとに、ページの名前で出す。"""

    template_name = 'console/pageviews.html'
    section = 'pageviews'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        day = timezone.localdate()
        context.update(today_summary(day))
        context['visitors'] = DailyVisitors.on(day)
        return context


class MembersView(ConsoleMixin, TemplateView):
    """会員数。クラブのクラスの生徒・招待中と、WG ごとの Chat スペースの人数（数だけ）。"""

    template_name = 'console/members.html'
    section = 'members'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['members'] = members.summary(refresh='refresh' in self.request.GET)
        return context


@login_not_required
@csrf_exempt
@require_POST
def beacon(request):
    """公開ページを開いたブラウザからの知らせ（console.middleware の差し込んだスクリプト）。

    サイトが署名した合言葉が付いていれば、そのページのページビューと訪問者を数える。
    中身を返す必要はないので、いつも 204 を返す（数えたかどうかも教えない）。
    """
    response = HttpResponse(status=204)
    record_beacon(request, response)
    return response
