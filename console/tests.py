from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import ActionCount, PageView


def views_of(path):
    return sum(PageView.objects.filter(path=path).values_list('count', flat=True))


class PageViewCountingTests(TestCase):
    """公開ページを人が開いたときだけ数える。"""

    BROWSER = 'Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/130 Safari/537.36'

    def get(self, path, **headers):
        return self.client.get(path, headers={'User-Agent': self.BROWSER, **headers})

    def test_public_page_is_counted_per_day_and_path(self):
        self.get('/')
        self.get('/')
        self.get('/news/')

        today = timezone.localdate()
        self.assertEqual(PageView.objects.get(date=today, path='/').count, 2)
        self.assertEqual(PageView.objects.get(date=today, path='/news/').count, 1)

    def test_query_string_is_not_part_of_the_path(self):
        self.get('/?utm_source=x')
        self.assertEqual(views_of('/'), 1)

    def test_errors_and_redirects_are_not_counted(self):
        self.get('/no-such-page/')
        self.get('/edit/')  # ログイン画面へのリダイレクト
        self.assertFalse(PageView.objects.exists())

    def test_non_html_is_not_counted(self):
        self.get('/robots.txt')
        self.assertFalse(PageView.objects.exists())

    def test_staff_screens_are_not_counted(self):
        self.get('/edit/login/')
        self.get('/console/login/')
        self.assertFalse(PageView.objects.exists())

    def test_logged_in_staff_is_not_counted(self):
        user = User.objects.create_user('staff', password='pw-for-tests-only')
        self.client.force_login(user)
        self.get('/')
        self.assertFalse(PageView.objects.exists())

    def test_crawlers_and_prefetch_are_not_counted(self):
        self.client.get('/', headers={'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1)'})
        self.get('/', **{'Sec-Purpose': 'prefetch'})
        self.assertFalse(PageView.objects.exists())

    def test_head_is_not_counted(self):
        self.client.head('/', headers={'User-Agent': self.BROWSER})
        self.assertFalse(PageView.objects.exists())

    def test_page_title_is_kept(self):
        self.get('/join/')
        self.assertEqual(PageView.objects.get(path='/join/').title, '参加する — fun IT club')

    def test_nothing_about_the_visitor_is_stored(self):
        """個人情報を持たない。数えるのは日付・パス・ページの題名・回数だけ。"""
        fields = {f.name for f in PageView._meta.get_fields()}
        self.assertEqual(fields, {'id', 'date', 'path', 'title', 'count'})
        fields = {f.name for f in ActionCount._meta.get_fields()}
        self.assertEqual(fields, {'id', 'date', 'name', 'count'})

    def test_join_apply_button_is_counted(self):
        self.client.post('/join/apply/', {}, headers={'User-Agent': self.BROWSER})
        self.client.post('/join/apply/', {}, headers={'User-Agent': self.BROWSER})
        self.assertEqual(ActionCount.objects.get(name='join_apply').count, 2)


class ConsoleAccessTests(TestCase):
    """アカウントは /edit/ と共通。ログインしないと開けない。"""

    def setUp(self):
        self.user = User.objects.create_user('funitclub', password='pw-for-tests-only')

    def test_requires_login_and_uses_console_login(self):
        for name in ('console:index', 'console:pageviews'):
            url = reverse(name)
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('console:login')}?next={url}",
                                 fetch_redirect_response=False)

    def test_edit_account_can_log_in(self):
        response = self.client.post(reverse('console:login'), {
            'username': 'funitclub', 'password': 'pw-for-tests-only',
        })
        self.assertRedirects(response, reverse('console:index'), fetch_redirect_response=False)

    def test_session_is_shared_with_edit(self):
        self.client.post(reverse('edit:login'), {
            'username': 'funitclub', 'password': 'pw-for-tests-only',
        })
        self.assertEqual(self.client.get(reverse('console:pageviews')).status_code, 200)

    def test_logout_returns_to_console_login(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('console:logout'))
        self.assertRedirects(response, reverse('console:login'), fetch_redirect_response=False)


class PageViewsPageTests(TestCase):
    """今日の分だけを、ページの名前で出す。"""

    def setUp(self):
        self.client.force_login(User.objects.create_user('funitclub', password='x'))
        self.today = timezone.localdate()
        PageView.objects.create(date=self.today, path='/', title='fun IT club — 佛教大学', count=5)
        PageView.objects.create(date=self.today, path='/news/', title='お知らせ — fun IT club', count=2)
        PageView.objects.create(date=self.today, path='/join/', title='参加する — fun IT club', count=3)
        PageView.objects.create(date=self.today, path='/join/apply/', count=1)
        PageView.objects.create(date=self.today - timedelta(days=1), path='/', count=40)
        ActionCount.objects.create(date=self.today, name='join_apply', count=1)
        ActionCount.objects.create(date=self.today - timedelta(days=1), name='join_apply', count=9)

    def context(self):
        return self.client.get(reverse('console:pageviews')).context

    def test_only_today_is_counted(self):
        self.assertEqual(self.context()['total'], 11)

    def test_join_pages_and_apply_button(self):
        context = self.context()
        self.assertEqual([(p['name'], p['n']) for p in context['join_pages']],
                         [('参加案内（参加する）', 3), ('申し込みページ', 1), ('受付完了ページ', 0)])
        self.assertEqual(context['join_applied'], 1)

    def test_other_pages_are_shown_by_name(self):
        self.assertEqual([(p['name'], p['n']) for p in self.context()['site_pages']],
                         [('トップページ', 5), ('お知らせ', 2)])

    def test_no_period_or_trend(self):
        response = self.client.get(reverse('console:pageviews'))
        self.assertNotContains(response, '経過')
        self.assertNotContains(response, '?days=')

    def test_index_shows_todays_views(self):
        response = self.client.get(reverse('console:index'))
        self.assertEqual(response.context['today_views'], 11)


class WgJoinTests(TestCase):
    """WG ごとに、参加ページの表示と参加のボタンの回数を出す。"""

    def setUp(self):
        from catalog.models import Wg
        self.client.force_login(User.objects.create_user('funitclub', password='x'))
        today = timezone.localdate()
        self.wg = Wg.objects.create(code='WG-04', name='カウントダウン', description='x',
                                    status=Wg.ACTIVE, github_team='wg-countdown')
        Wg.objects.create(code='WG-09', name='受付なし', description='x', status=Wg.ACTIVE)
        pk = self.wg.pk
        PageView.objects.create(date=today, path=f'/wg/{pk}/join/', title='カウントダウン に参加 — fun IT club', count=6)
        PageView.objects.create(date=today, path='/wg/join/verify/abc/', title='カウントダウン に参加 — fun IT club', count=2)
        PageView.objects.create(date=today, path='/wg/', title='WG一覧 — fun IT club', count=3)
        ActionCount.objects.create(date=today, name=f'wg_join_send:{pk}', count=4)
        ActionCount.objects.create(date=today, name=f'wg_join_confirm:{pk}', count=1)
        ActionCount.objects.create(date=today - timedelta(days=1), name=f'wg_join_send:{pk}', count=9)

    def test_join_counts_per_wg(self):
        context = self.client.get(reverse('console:pageviews')).context
        groups = {g['title']: g for g in context['apps']['wg']}
        self.assertNotIn('WG-09 受付なし', groups)  # 参加を受け付けていない WG は出さない
        self.assertEqual([(r['name'], r['n']) for r in groups['WG-04 カウントダウン']['join']], [
            ('参加ページ（アドレスの入力）', 6),
            ('「確認のメールを送る」ボタン', 4),
            ('「GitHub でログインして登録する」ボタン', 1),
        ])
        self.assertEqual(groups['WG-04 カウントダウン']['n'], 6)  # 参加ページの表示も WG の回数に入れる

    def test_join_rows_are_shown(self):
        response = self.client.get(reverse('console:pageviews'))
        self.assertContains(response, 'WG-04 カウントダウン')
        self.assertContains(response, '参加：「確認のメールを送る」ボタン')

    def test_join_screens_are_not_in_other_pages(self):
        context = self.client.get(reverse('console:pageviews')).context
        self.assertEqual([(p['name'], p['n']) for p in context['site_pages']], [('WG一覧', 3)])


class PageNameTests(TestCase):

    def test_site_name_after_the_separator_is_dropped(self):
        from .views import page_name
        self.assertEqual(page_name('/news/', 'お知らせ — fun IT club'), 'お知らせ')
        self.assertEqual(page_name('/fe/x/', '問題メール | FE 基本情報対策 | fun IT club'), '問題メール')
        self.assertEqual(page_name('/x/', 'JSONを取り込む - FE 基本情報対策 | fun IT club'), 'JSONを取り込む')
        self.assertEqual(page_name('/', 'fun IT club — 佛教大学'), 'トップページ')
        self.assertEqual(page_name('/old/', ''), '/old/')


class ViewsByAppTests(TestCase):
    """WG・成果物ごとに、ページの名前ごとの回数をまとめる。"""

    APPS = [
        ('wg', 'welfare', 'welfare'),
        ('wg', 'welfare_activity', 'welfare/activity'),
        ('wg', 'protein_activity', 'protein/activity'),
        ('works', 'countdown', 'countdown'),
        ('works', 'fe', 'fe'),
    ]

    def setUp(self):
        from unittest import mock

        from catalog.models import Wg, Work
        from works.fe.models import PageViewCount

        patcher = mock.patch('console.views.installed_apps', return_value=self.APPS)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.client.force_login(User.objects.create_user('funitclub', password='x'))
        today = timezone.localdate()
        for path, title, count in [
            ('/', '', 3),
            ('/welfare/', '福祉 WG', 2),
            ('/welfare/activity/', 'トップ — 福祉 WG', 4),
            ('/welfare/activity/tickets/', 'チケット — 福祉 WG', 1),
            ('/countdown/abc/', '一覧 — カウントアップ＆ダウン', 6),
            ('/countdown/xyz/', '一覧 — カウントアップ＆ダウン', 1),
            ('/countdown/', 'カウントアップ＆ダウン — fun IT club', 2),
            ('/fe/', 'FE 基本情報対策 | fun IT club', 10),  # React の画面は fe が自分で数えた数を使う
            ('/fe-other/', 'ほか', 7),  # /fe/ ではない
        ]:
            PageView.objects.create(date=today, path=path, title=title, count=count)
        PageView.objects.create(date=today - timedelta(days=1), path='/countdown/', count=50)
        PageViewCount.objects.create(date=today, page='quiz', with_id=True, count=4)
        PageViewCount.objects.create(date=today, page='quiz', with_id=False, count=1)
        PageViewCount.objects.create(date=today - timedelta(days=1), page='stats', with_id=True, count=8)

        Wg.objects.create(code='WG-05', name='福祉', description='x',
                          app_url='https://example.com/welfare/activity/')
        Work.objects.create(category='Web App', title='FE 対策', description='x',
                            url='https://example.com/fe/')

    def groups(self):
        return self.client.get(reverse('console:pageviews')).context['apps']

    def test_apps_of_one_wg_are_put_together(self):
        wg = self.groups()['wg']
        self.assertEqual([(g['title'], g['n']) for g in wg],
                         [('WG-05 福祉', 7), ('protein_activity', 0)])
        self.assertEqual(
            [(app['prefix'], [(p['name'], p['n']) for p in app['pages']]) for app in wg[0]['apps']],
            [('/welfare/', [('福祉 WG', 2)]),
             ('/welfare/activity/', [('トップ', 4), ('チケット', 1)])])

    def test_pages_seen_before_are_listed_with_zero(self):
        PageView.objects.create(date=timezone.localdate() - timedelta(days=3),
                                path='/welfare/activity/members/', title='メンバー — 福祉 WG', count=2)
        wg = self.groups()['wg'][0]
        pages = [(p['name'], p['n']) for p in wg['apps'][1]['pages']]
        self.assertEqual(pages, [('トップ', 4), ('チケット', 1), ('メンバー', 0)])
        self.assertEqual(wg['n'], 7)
        # そのほかのページには、今日見られたものしか出さない
        PageView.objects.create(date=timezone.localdate() - timedelta(days=3), path='/old/', count=1)
        context = self.client.get(reverse('console:pageviews')).context
        self.assertNotIn('/old/', [p['name'] for p in context['site_pages']])

    def test_pages_of_a_work_are_counted_by_name(self):
        works = {g['title']: g for g in self.groups()['works']}
        countdown = works['countdown']['apps'][0]['pages']
        self.assertEqual([(p['name'], p['n']) for p in countdown],
                         [('一覧', 7), ('カウントアップ＆ダウン', 2)])

    def test_an_app_that_counts_its_own_screens_uses_them(self):
        fe = {g['title']: g for g in self.groups()['works']}['FE 対策']
        pages = dict((p['name'], p['n']) for p in fe['apps'][0]['pages'])
        self.assertEqual(pages['1問1答'], 5)
        self.assertEqual(pages['分野別正答率'], 0)  # 昨日の分は入れない
        self.assertEqual(fe['n'], 5)

    def test_page_shows_names_not_urls(self):
        response = self.client.get(reverse('console:pageviews'))
        self.assertContains(response, 'WG-05 福祉')
        self.assertContains(response, 'チケット')
        self.assertContains(response, '1問1答')
        self.assertNotContains(response, '/welfare/activity/tickets/')
