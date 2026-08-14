from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import include, path, reverse
from django.utils import timezone

from catalog.models import Wg, Work
from news.models import News


def bare_view(request):
    """login_not_required を付けていないビュー（DefaultProtectionTests 用）。"""
    return HttpResponse('ok')


#: DefaultProtectionTests が override_settings(ROOT_URLCONF=...) で使う URL 定義。
urlpatterns = [
    path('bare/', bare_view),
    path('edit/', include('edit.urls', namespace='edit')),
]


@override_settings(ROOT_URLCONF='edit.tests')
class DefaultProtectionTests(TestCase):
    """LoginRequiredMiddleware で、除外していないビューは既定でログイン必須になる。"""

    def test_view_without_exemption_redirects_to_login(self):
        response = self.client.get('/bare/')
        self.assertRedirects(
            response,
            f"{reverse('edit:login')}?next=/bare/",
            fetch_redirect_response=False,
        )

    def test_logged_in_user_can_open_it(self):
        User.objects.create_user('editor', password='funitclub-test-pass')
        self.client.force_login(User.objects.get(username='editor'))
        self.assertEqual(self.client.get('/bare/').status_code, 200)


class AccessTests(TestCase):
    """編集画面はログイン必須。公開ページはログイン不要。"""

    def setUp(self):
        self.news = News.objects.create(published_on=timezone.localdate(), text='お知らせ')
        self.wg = Wg.objects.create(code='WG-01', name='WG', description='説明')
        self.work = Work.objects.create(category='Web App', title='成果物', description='説明')

    def edit_urls(self):
        return [
            reverse('edit:index'),
            reverse('edit:news:editor_list'),
            reverse('edit:news:editor_create'),
            reverse('edit:news:editor_update', args=[self.news.pk]),
            reverse('edit:news:editor_delete', args=[self.news.pk]),
            reverse('edit:catalog:wg_list'),
            reverse('edit:catalog:wg_create'),
            reverse('edit:catalog:wg_update', args=[self.wg.pk]),
            reverse('edit:catalog:wg_delete', args=[self.wg.pk]),
            reverse('edit:catalog:work_list'),
            reverse('edit:catalog:work_create'),
            reverse('edit:catalog:work_update', args=[self.work.pk]),
            reverse('edit:catalog:work_delete', args=[self.work.pk]),
        ]

    def test_all_edit_urls_redirect_anonymous_to_login(self):
        login_url = reverse('edit:login')

        for url in self.edit_urls():
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f'{login_url}?next={url}')

    def test_anonymous_post_cannot_delete(self):
        for url, model, pk in [
            (reverse('edit:news:editor_delete', args=[self.news.pk]), News, self.news.pk),
            (reverse('edit:catalog:wg_delete', args=[self.wg.pk]), Wg, self.wg.pk),
            (reverse('edit:catalog:work_delete', args=[self.work.pk]), Work, self.work.pk),
        ]:
            with self.subTest(url=url):
                self.client.post(url)
                self.assertTrue(model.objects.filter(pk=pk).exists())

    def test_public_pages_need_no_login(self):
        for name in ['home:index', 'home:wg_list', 'home:work_list',
                     'home:join', 'home:coming_soon']:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_public_pages_do_not_link_to_edit(self):
        """公開サイトと編集画面は相互にリンクしない。"""
        for name in ['home:index', 'home:wg_list', 'home:work_list', 'home:join']:
            with self.subTest(name=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertNotIn('/edit/', html)


class AdminTests(TestCase):
    """管理画面（テーブル表示用）。未ログインでは中身を見せない。"""

    def setUp(self):
        self.staff = User.objects.create_superuser('admin-user', password='funitclub-test-pass')

    def test_anonymous_redirects_to_admin_login(self):
        # admin の URL には login_url が仕込まれているため、LoginRequiredMiddleware は
        # /edit/login/ ではなく admin 自身のログイン画面へ回す（Django の仕様）。
        response = self.client.get('/admin/')
        self.assertRedirects(
            response,
            '/admin/login/?next=/admin/',
            fetch_redirect_response=False,
        )

    def test_login_on_edit_screen_also_opens_admin(self):
        """セッションは共通なので、編集画面でログインすれば admin も開ける。"""
        self.client.post(reverse('edit:login'), {
            'username': 'admin-user',
            'password': 'funitclub-test-pass',
        })
        self.assertEqual(self.client.get('/admin/').status_code, 200)

    def test_staff_can_list_each_model(self):
        self.client.force_login(self.staff)

        for url in ['/admin/', '/admin/news/news/',
                    '/admin/catalog/wg/', '/admin/catalog/work/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class LoginTests(TestCase):

    def setUp(self):
        User.objects.create_user('editor', password='funitclub-test-pass')

    def test_login_form_reaches_menu(self):
        response = self.client.post(reverse('edit:login'), {
            'username': 'editor',
            'password': 'funitclub-test-pass',
        })
        self.assertRedirects(response, reverse('edit:index'))

    def test_menu_does_not_link_to_public_site(self):
        """編集画面から公開ページへのリンクは持たない。"""
        self.client.force_login(User.objects.get(username='editor'))
        html = self.client.get(reverse('edit:index')).content.decode()

        for name in ['home:index', 'home:wg_list', 'home:work_list', 'home:join']:
            with self.subTest(name=name):
                self.assertNotIn(f'href="{reverse(name)}"', html)
