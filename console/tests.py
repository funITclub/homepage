from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import PageView


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

    def test_nothing_about_the_visitor_is_stored(self):
        """個人情報を持たない。数えるのは日付・パス・回数だけ。"""
        fields = {f.name for f in PageView._meta.get_fields()}
        self.assertEqual(fields, {'id', 'date', 'path', 'count'})


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

    def setUp(self):
        self.client.force_login(User.objects.create_user('funitclub', password='x'))
        self.today = timezone.localdate()
        PageView.objects.create(date=self.today, path='/', count=5)
        PageView.objects.create(date=self.today, path='/news/', count=2)
        PageView.objects.create(date=self.today - timedelta(days=3), path='/', count=4)
        PageView.objects.create(date=self.today - timedelta(days=40), path='/old/', count=99)

    def test_totals_for_the_default_period(self):
        context = self.client.get(reverse('console:pageviews')).context
        self.assertEqual(context['days'], 30)
        self.assertEqual(context['total'], 11)
        self.assertEqual(context['today'], 7)
        self.assertEqual(context['page_count'], 2)
        self.assertEqual(len(context['daily']), 30)
        self.assertEqual([(r['path'], r['n']) for r in context['ranking']],
                         [('/', 9), ('/news/', 2)])

    def test_period_can_be_changed(self):
        context = self.client.get(reverse('console:pageviews'), {'days': 90}).context
        self.assertEqual(context['total'], 110)

    def test_unknown_period_falls_back_to_default(self):
        context = self.client.get(reverse('console:pageviews'), {'days': 'abc'}).context
        self.assertEqual(context['days'], 30)
        context = self.client.get(reverse('console:pageviews'), {'days': 9999}).context
        self.assertEqual(context['days'], 30)

    def test_index_shows_todays_views(self):
        response = self.client.get(reverse('console:index'))
        self.assertEqual(response.context['today_views'], 7)
