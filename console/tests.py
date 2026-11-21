import json
import re
import time
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ActionCount, DailyVisitors, PageView


def views_of(path):
    return sum(PageView.objects.filter(path=path).values_list('count', flat=True))


TOKEN_IN_PAGE = re.compile(r'URLSearchParams\(\{t:("[^"]+")\}\)')


class PageViewCountingTests(TestCase):
    """公開ページを人が開いたときだけ数える。

    ページを取りに来ただけでは数えず、ブラウザが差し込んだスクリプトを動かして知らせてきたら数える。
    get() はブラウザの代わりに、ページを開いてスクリプトの知らせまで送る。
    """

    BROWSER = 'Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/130 Safari/537.36'

    def get(self, path, **headers):
        headers = {'User-Agent': self.BROWSER, **headers}
        response = self.client.get(path, headers=headers)
        match = TOKEN_IN_PAGE.search(response.content.decode('utf-8', errors='replace'))
        if match:
            self.client.post(reverse('console:beacon'), {'t': json.loads(match.group(1))}, headers=headers)
        return response

    def test_fetching_the_page_alone_is_not_counted(self):
        """JavaScript を動かさない巡回ロボット（人のふりをしたものも）は数えない。"""
        response = self.client.get('/', headers={'User-Agent': self.BROWSER})
        self.assertContains(response, reverse('console:beacon'))
        self.assertFalse(PageView.objects.exists())
        self.assertFalse(DailyVisitors.objects.exists())

    def test_script_is_put_just_before_the_end_of_body(self):
        content = self.client.get('/', headers={'User-Agent': self.BROWSER}).content
        self.assertTrue(content.rstrip().endswith(b'</script></body>\n</html>')
                        or b'</script></body>' in content)

    def test_forged_or_old_notice_is_not_counted(self):
        from django.core import signing
        self.client.post(reverse('console:beacon'), {'t': 'forged'}, headers={'User-Agent': self.BROWSER})
        self.client.post(reverse('console:beacon'), {'t': signing.dumps({'p': '/x/', 't': ''})},
                         headers={'User-Agent': self.BROWSER})  # salt が違う（サイトが出したものでない）
        self.assertFalse(PageView.objects.exists())
        with mock.patch('django.core.signing.time.time', return_value=time.time() - 7 * 3600):
            response = self.client.get('/', headers={'User-Agent': self.BROWSER})
        token = json.loads(TOKEN_IN_PAGE.search(response.content.decode()).group(1))
        self.client.post(reverse('console:beacon'), {'t': token}, headers={'User-Agent': self.BROWSER})
        self.assertFalse(PageView.objects.exists())

    def test_beacon_answers_the_same_either_way(self):
        response = self.client.post(reverse('console:beacon'), {'t': 'forged'})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get(reverse('console:beacon')).status_code, 405)

    def test_disguised_scanners_get_no_script(self):
        for agent in ('Mozilla/5.0 (compatible; Dataprovider.com)',
                      'Mozilla/5.0 (compatible; AdmakeChecker/2pass-dyn; +https://example.com)',
                      'visionheight.com/scan Mozilla/5.0 (Macintosh) Chrome/126.0.0.0 Safari/537.36',
                      'python-requests/2.32.3'):
            response = self.client.get('/', headers={'User-Agent': agent})
            self.assertNotContains(response, reverse('console:beacon'), msg_prefix=agent)

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

    def test_visitor_is_counted_once_a_day_per_browser(self):
        self.get('/')
        self.get('/news/')
        self.get('/')
        today = timezone.localdate()
        self.assertEqual(DailyVisitors.on(today), 1)
        self.assertEqual(self.client.cookies['fic_visited'].value, today.isoformat())
        # 別のブラウザ
        self.client.cookies.clear()
        self.get('/')
        self.assertEqual(DailyVisitors.on(today), 2)
        # 前の日の印は数え直す
        self.client.cookies['fic_visited'] = (today - timedelta(days=1)).isoformat()
        self.get('/')
        self.assertEqual(DailyVisitors.on(today), 3)

    def test_notice_from_logged_in_staff_is_not_counted(self):
        response = self.client.get('/', headers={'User-Agent': self.BROWSER})
        token = json.loads(TOKEN_IN_PAGE.search(response.content.decode()).group(1))
        self.client.force_login(User.objects.create_user('staff', password='pw-for-tests-only'))
        self.client.post(reverse('console:beacon'), {'t': token}, headers={'User-Agent': self.BROWSER})
        self.assertFalse(PageView.objects.exists())

    def test_visitor_is_not_counted_for_staff_crawlers_or_errors(self):
        self.client.get('/', headers={'User-Agent': 'Googlebot/2.1'})
        self.get('/no-such-page/')
        self.get('/console/login/')
        self.client.force_login(User.objects.create_user('staff', password='pw-for-tests-only'))
        self.get('/')
        self.assertFalse(DailyVisitors.objects.exists())

    def test_page_title_is_kept(self):
        self.get('/join/')
        self.assertEqual(PageView.objects.get(path='/join/').title, '参加する — fun IT club')

    def test_nothing_about_the_visitor_is_stored(self):
        """個人情報を持たない。数えるのは日付・パス・ページの題名・回数だけ。"""
        fields = {f.name for f in PageView._meta.get_fields()}
        self.assertEqual(fields, {'id', 'date', 'path', 'title', 'count'})
        fields = {f.name for f in ActionCount._meta.get_fields()}
        self.assertEqual(fields, {'id', 'date', 'name', 'count'})
        fields = {f.name for f in DailyVisitors._meta.get_fields()}
        self.assertEqual(fields, {'id', 'date', 'count'})

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

    def test_total_is_only_the_pages_in_the_table(self):
        # 今日の /join/ 3 と /join/apply/ 1。トップ・お知らせ（表に出さない）と昨日の分は入れない
        self.assertEqual(self.context()['total'], 4)

    def test_join_pages_and_apply_button(self):
        context = self.context()
        self.assertEqual([(p['name'], p['n']) for p in context['join_pages']],
                         [('参加案内（参加する）', 3), ('申し込みページ', 1), ('受付完了ページ', 0)])
        self.assertEqual(context['join_applied'], 1)

    def test_other_pages_are_not_listed(self):
        response = self.client.get(reverse('console:pageviews'))
        self.assertNotContains(response, 'そのほかのページ')
        self.assertNotContains(response, 'お知らせ')

    def test_no_period_or_trend(self):
        response = self.client.get(reverse('console:pageviews'))
        self.assertNotContains(response, '経過')
        self.assertNotContains(response, '?days=')

    def test_index_shows_visitors_and_members(self):
        from unittest import mock
        DailyVisitors.objects.create(date=self.today, count=3)
        with mock.patch('console.members.summary', return_value={'configured': True, 'total': 42}):
            response = self.client.get(reverse('console:index'))
        self.assertEqual(response.context['today_visitors'], 3)
        self.assertContains(response, '今日の訪問者数')
        self.assertContains(response, 'visitors-hero')
        self.assertContains(response, '会員数')
        self.assertContains(response, '42')
        self.assertNotContains(response, '推移')


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
        self.assertEqual(context['total'], 6)  # ボタンの回数・参加の確認の画面・WG一覧は入れない

    def test_join_rows_are_shown(self):
        response = self.client.get(reverse('console:pageviews'))
        self.assertContains(response, 'WG-04 カウントダウン')
        self.assertContains(response, '参加：「確認のメールを送る」ボタン')


class PageNameTests(TestCase):

    def test_site_name_after_the_separator_is_dropped(self):
        from .views import page_name
        self.assertEqual(page_name('/news/', 'お知らせ — fun IT club'), 'お知らせ')
        self.assertEqual(page_name('/fe/x/', '問題メール | FE 基本情報対策 | fun IT club'), '問題メール')
        self.assertEqual(page_name('/x/', 'JSONを取り込む - FE 基本情報対策 | fun IT club'), 'JSONを取り込む')
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


GOOGLE = dict(
    CLUB_CLASSROOM_COURSE='987654321098',
    GOOGLE_OAUTH_CLIENT_ID='google-client', GOOGLE_OAUTH_CLIENT_SECRET='google-secret',
    GOOGLE_OAUTH_REFRESH_TOKEN='staff-refresh',
)


class MembersTests(TestCase):
    """会員数は Google に人数だけを聞く。名簿は持たない。"""

    def setUp(self):
        from django.core.cache import cache

        from catalog.models import Wg
        cache.clear()
        self.client.force_login(User.objects.create_user('funitclub', password='x'))
        Wg.objects.create(code='WG-04', name='カウントダウン', description='x', status=Wg.ACTIVE,
                          chat_space='spaces/AAAA1234')
        Wg.objects.create(code='WG-05', name='Chat なし', description='x', status=Wg.ACTIVE)

    def patched(self, **counts):
        from unittest import mock

        from wgjoin import google
        return mock.patch.multiple(google, **{
            'count_club_students': mock.Mock(return_value=counts.get('students', 40)),
            'count_club_teachers': mock.Mock(return_value=counts.get('teachers', 2)),
            'count_club_invitations': mock.Mock(return_value=counts.get('invited', 3)),
            'count_chat_members': counts.get('chat', mock.Mock(return_value=7)),
        })

    @override_settings(**GOOGLE)
    def test_counts_from_google(self):
        with self.patched():
            response = self.client.get(reverse('console:members'))
        members = response.context['members']
        self.assertEqual((members['students'], members['teachers'], members['invited']), (40, 2, 3))
        self.assertEqual(members['total'], 42)  # 先生も会員に数える
        self.assertEqual(members['wgs'], [{'title': 'WG-04 カウントダウン', 'chat': 7}])
        self.assertContains(response, 'WG-04 カウントダウン')
        self.assertNotContains(response, 'Chat なし')

    @override_settings(**GOOGLE)
    def test_counts_are_cached_and_can_be_refreshed(self):
        with self.patched(students=40):
            self.client.get(reverse('console:members'))
        with self.patched(students=41):
            self.assertEqual(self.client.get(reverse('console:members')).context['members']['students'], 40)
            response = self.client.get(reverse('console:members'), {'refresh': 1})
        self.assertEqual(response.context['members']['students'], 41)

    @override_settings(**GOOGLE)
    def test_failure_is_shown_without_breaking_the_page(self):
        from unittest import mock

        from wgjoin.http import ServiceError
        with self.patched(chat=mock.Mock(side_effect=ServiceError('403'))):
            response = self.client.get(reverse('console:members'))
        self.assertContains(response, '取得できませんでした')
        self.assertContains(response, '42')

    @override_settings(GOOGLE_OAUTH_REFRESH_TOKEN='')
    def test_without_google_settings(self):
        response = self.client.get(reverse('console:members'))
        self.assertContains(response, '数えられません')
        self.assertContains(self.client.get(reverse('console:index')), '—')


class SuspiciousAccessTests(TestCase):
    """不審なアクセスだけ、IP・User-Agent・パス・日時を残す。人のアクセスは残さない。"""

    BROWSER = PageViewCountingTests.BROWSER

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def kinds(self):
        from .models import SuspiciousAccess
        return list(SuspiciousAccess.objects.order_by('created_at').values_list('kind', 'ip', 'path'))

    def test_probing_attack_paths(self):
        for path in ('/wp-login.php', '/.env', '/xmlrpc.php', '/phpmyadmin/', '/cgi-bin/x'):
            self.client.get(path, headers={'User-Agent': self.BROWSER})
        self.assertEqual([k[0] for k in self.kinds()], ['probe'] * 5)
        self.assertEqual(self.kinds()[0][1:], ('127.0.0.1', '/wp-login.php'))

    def test_ordinary_pages_are_not_probes(self):
        for path in ('/', '/news/', '/join/', '/no-such-page/', '/countdown/myboard/', '/robots.txt'):
            self.client.get(path, headers={'User-Agent': self.BROWSER})
        self.assertNotIn('probe', [k[0] for k in self.kinds()])

    def test_named_scanners_but_not_search_engines(self):
        self.client.get('/', headers={'User-Agent': 'Mozilla/5.0 (compatible; Dataprovider.com)'})
        self.client.get('/', headers={'User-Agent': 'python-requests/2.32.3'})
        self.client.get('/', headers={'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1)'})
        self.assertEqual([k[0] for k in self.kinds()], ['scanner', 'scanner'])

    def test_person_with_a_browser_leaves_nothing(self):
        from .models import PendingView
        PageViewCountingTests.get(self, '/')
        PageViewCountingTests.get(self, '/news/')
        self.assertEqual(self.kinds(), [])
        self.assertFalse(PendingView.objects.exists())

    def test_fake_browser_without_the_notice(self):
        from datetime import timedelta as td

        from . import suspicious
        from .models import PendingView
        self.client.get('/news/', headers={'User-Agent': self.BROWSER})
        self.assertEqual(PendingView.objects.count(), 1)
        self.assertEqual(suspicious.sweep_pending(), 0)  # まだ待つ
        self.assertEqual(suspicious.sweep_pending(timezone.now() + td(minutes=31)), 1)
        self.assertEqual(self.kinds(), [('fake_browser', '127.0.0.1', '/news/')])
        self.assertFalse(PendingView.objects.exists())

    def test_staff_is_not_recorded(self):
        self.client.force_login(User.objects.create_user('staff', password='pw-for-tests-only'))
        self.client.get('/wp-login.php', headers={'User-Agent': 'python-requests/2.32.3'})
        self.assertEqual(self.kinds(), [])

    def test_blocked_ip(self):
        from config.middleware import BlockedIpMiddleware
        from home.models import BlockedIp
        BlockedIp.objects.create(ip='127.0.0.1', reason='手動')
        BlockedIpMiddleware.forget_cache()
        self.client.get('/news/', headers={'User-Agent': self.BROWSER})
        self.assertEqual(self.kinds(), [('blocked', '127.0.0.1', '/news/')])

    def test_every_access_is_recorded_no_matter_how_many(self):
        for _ in range(60):
            self.client.get('/wp-login.php')
        self.assertEqual(len(self.kinds()), 60)

    def test_old_records_are_purged(self):
        from datetime import timedelta as td

        from . import suspicious
        from .models import SuspiciousAccess
        SuspiciousAccess.objects.create(created_at=timezone.now() - td(days=31), kind='probe', ip='1.2.3.4')
        SuspiciousAccess.objects.create(created_at=timezone.now() - td(days=29), kind='probe', ip='1.2.3.5')
        self.assertEqual(suspicious.purge_old(), 1)
        self.assertEqual(list(SuspiciousAccess.objects.values_list('ip', flat=True)), ['1.2.3.5'])

    def test_console_card_and_list(self):
        from .models import SuspiciousAccess
        self.client.get('/wp-login.php', headers={'User-Agent': 'zgrab/0.x'})
        SuspiciousAccess.objects.create(created_at=timezone.now(), kind='scanner', ip='203.0.113.9',
                                        path='/', user_agent='Dataprovider')
        self.client.force_login(User.objects.create_user('funitclub', password='x'))
        with mock.patch('console.members.summary', return_value={'configured': False}):
            index = self.client.get(reverse('console:index'))
        self.assertEqual(index.context['suspicious_today'], 2)
        self.assertContains(index, '不審なアクセス（今日）')

        response = self.client.get(reverse('console:suspicious'))
        self.assertContains(response, '203.0.113.9')
        self.assertContains(response, '/wp-login.php')
        self.assertContains(response, 'zgrab/0.x')
        response = self.client.get(reverse('console:suspicious'), {'ip': '203.0.113.9'})
        self.assertEqual(response.context['page'].paginator.count, 1)
        response = self.client.get(reverse('console:suspicious'), {'kind': 'probe'})
        self.assertEqual([r.path for r in response.context['page'].object_list], ['/wp-login.php'])

    def test_list_shows_everything_across_pages(self):
        from .models import SuspiciousAccess
        from .views import SuspiciousView
        SuspiciousAccess.objects.bulk_create([
            SuspiciousAccess(created_at=timezone.now(), kind='probe', ip='20.30.40.60', path=f'/x{i}.php')
            for i in range(SuspiciousView.PER_PAGE + 5)])
        self.client.force_login(User.objects.create_user('funitclub', password='x'))
        first = self.client.get(reverse('console:suspicious'))
        self.assertEqual(len(first.context['page'].object_list), SuspiciousView.PER_PAGE)
        self.assertContains(first, '古い 200 件')
        second = self.client.get(reverse('console:suspicious'), {'page': 2})
        self.assertEqual(len(second.context['page'].object_list), 5)


@override_settings(SUSPICIOUS_BLOCK_RULES=[(3, 600), (5, 86400)])
class AutoBlockTests(TestCase):
    """執拗な不審なアクセスは自動で遮断する。メールは送らない。"""

    def setUp(self):
        from django.core.cache import cache

        from config.middleware import BlockedIpMiddleware
        cache.clear()
        BlockedIpMiddleware.forget_cache()
        self.client.defaults['REMOTE_ADDR'] = '20.30.40.50'

    def blocked(self):
        from home.models import BlockedIp
        return list(BlockedIp.objects.active().values_list('ip', flat=True))

    def test_persistent_probing_is_blocked_without_mail(self):
        from django.core import mail

        from .models import SuspiciousAccess
        for _ in range(2):
            self.client.get('/wp-login.php')
        self.assertEqual(self.blocked(), [])
        self.client.get('/.env')
        self.assertEqual(self.blocked(), ['20.30.40.50'])
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(SuspiciousAccess.objects.filter(kind='auto_block', ip='20.30.40.50').exists())
        # 遮断が効く（次から 403）
        self.assertEqual(self.client.get('/').status_code, 403)

    def test_fake_browsers_count_too(self):
        from datetime import timedelta as td

        from . import suspicious
        for path in ('/', '/news/', '/join/'):
            self.client.get(path, headers={'User-Agent': PageViewCountingTests.BROWSER})
        self.assertEqual(self.blocked(), [])
        suspicious.sweep_pending(timezone.now() + td(minutes=31))
        self.assertEqual(self.blocked(), ['20.30.40.50'])

    def test_slow_but_steady_is_blocked_by_the_daily_rule(self):
        from datetime import timedelta as td

        from . import suspicious
        from .models import SuspiciousAccess
        now = timezone.now()
        for hours in (9, 7, 5, 3):
            SuspiciousAccess.objects.create(created_at=now - td(hours=hours), kind='scanner', ip='20.30.40.51')
        self.assertFalse(suspicious.block_if_persistent('20.30.40.51'))
        SuspiciousAccess.objects.create(created_at=now, kind='probe', ip='20.30.40.51')
        self.assertTrue(suspicious.block_if_persistent('20.30.40.51'))

    def test_other_kinds_do_not_count(self):
        from . import suspicious
        from .models import SuspiciousAccess
        for _ in range(6):
            SuspiciousAccess.objects.create(created_at=timezone.now(), kind='blocked', ip='20.30.40.52')
        self.assertFalse(suspicious.block_if_persistent('20.30.40.52'))

    @override_settings(IP_BLOCK_EXEMPT=['20.30.40.50'])
    def test_exempt_ip_is_not_blocked(self):
        for _ in range(4):
            self.client.get('/wp-login.php')
        self.assertEqual(self.blocked(), [])

    def test_internal_addresses_are_never_blocked(self):
        """Azure の内側（169.254.x の死活監視など）と手元は遮断しない。"""
        from . import suspicious
        from .models import SuspiciousAccess
        for ip in ('169.254.130.1', '10.0.0.4', '127.0.0.1'):
            for _ in range(6):
                SuspiciousAccess.objects.create(created_at=timezone.now(), kind='probe', ip=ip)
            self.assertFalse(suspicious.block_if_persistent(ip), ip)

    def test_staff_never_triggers_it(self):
        self.client.force_login(User.objects.create_user('staff', password='pw-for-tests-only'))
        for _ in range(4):
            self.client.get('/wp-login.php')
        self.assertEqual(self.blocked(), [])


class SuspiciousCoverageTests(TestCase):
    """取りこぼし・入れすぎを防ぐ。"""

    BROWSER = PageViewCountingTests.BROWSER

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_probe_is_recorded_even_when_another_middleware_answers_first(self):
        from .models import SuspiciousAccess
        # /countdown/ の下はゲート（config.gate）が一覧へ送り返す。それでも残す
        response = self.client.get('/countdown/wp-login.php', headers={'User-Agent': self.BROWSER})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SuspiciousAccess.objects.filter(kind='probe', path='/countdown/wp-login.php').exists())

    def test_azure_warmup_and_health_checks_are_not_pending(self):
        from .models import PendingView
        for agent in ('SiteWarmup', 'HealthCheck/1.0', 'AlwaysOn'):
            self.client.get('/', headers={'User-Agent': agent})
        self.assertFalse(PendingView.objects.exists())

    def test_pending_count_is_shown(self):
        self.client.get('/news/', headers={'User-Agent': self.BROWSER})
        self.client.force_login(User.objects.create_user('funitclub', password='x'))
        response = self.client.get(reverse('console:suspicious'))
        self.assertEqual(response.context['pending_count'], 1)
        self.assertContains(response, '判定待ち')


class OwnAutomationTests(TestCase):
    """自分たちの GitHub Actions（定期実行・デプロイ後の確認）は不審に数えない。"""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def kinds(self):
        from .models import SuspiciousAccess
        return list(SuspiciousAccess.objects.values_list('kind', 'path'))

    @override_settings(FE_MAIL_TOKEN='fe-secret')
    def test_fe_mail_task_with_the_right_token_is_not_suspicious(self):
        with mock.patch('works.fe.mail.send_slot', return_value={'sent': 0}):
            ok = self.client.post('/fe/tasks/send-mails/', {'slot': 'h09'},
                                  headers={'User-Agent': 'curl/8.18.0', 'X-Fe-Mail-Token': 'fe-secret'})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.kinds(), [])
        # 合言葉が違えば、これまでどおり残す
        self.client.post('/fe/tasks/send-mails/', {'slot': 'h09'},
                         headers={'User-Agent': 'curl/8.18.0', 'X-Fe-Mail-Token': 'wrong'})
        self.assertEqual(self.kinds(), [('scanner', '/fe/tasks/send-mails/')])

    @override_settings(COUNTDOWN_NOTIFY_TOKEN='cd-secret')
    def test_countdown_notify_with_the_right_token_is_not_suspicious(self):
        with mock.patch('works.countdown.notify.send_daily', return_value=0):
            ok = self.client.post('/countdown/notify/run/',
                                  headers={'User-Agent': 'curl/8.18.0', 'Authorization': 'Bearer cd-secret'})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.kinds(), [])

    def test_deploy_check_is_neither_scanner_nor_pending(self):
        from .models import PendingView
        self.client.get('/', headers={'User-Agent': 'funitclub-actions/deploy-check'})
        self.assertEqual(self.kinds(), [])
        self.assertFalse(PendingView.objects.exists())

    def test_the_name_does_not_hide_probes(self):
        self.client.get('/.env', headers={'User-Agent': 'funitclub-actions/deploy-check'})
        self.assertEqual(self.kinds(), [('probe', '/.env')])
