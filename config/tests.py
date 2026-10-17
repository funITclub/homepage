import tempfile
from pathlib import Path

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from catalog.models import Wg, Work

from . import gate, subapps
from .middleware import CanonicalHostMiddleware


def dummy_response(request):
    return HttpResponse('ok')


@override_settings(CANONICAL_HOST='funitclub.org', ALLOWED_HOSTS=['*'])
class CanonicalHostMiddlewareTests(TestCase):
    """www 付きのアクセスを apex へ 301 で寄せる。"""

    def setUp(self):
        self.middleware = CanonicalHostMiddleware(dummy_response)
        self.factory = RequestFactory()

    def test_www_redirects_to_apex_keeping_path_and_query(self):
        request = self.factory.get('/wg/?q=1', headers={'host': 'www.funitclub.org'})
        response = self.middleware(request)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'http://funitclub.org/wg/?q=1')

    def test_apex_passes_through(self):
        request = self.factory.get('/wg/', headers={'host': 'funitclub.org'})
        self.assertEqual(self.middleware(request).status_code, 200)

    def test_azure_default_hostname_passes_through(self):
        request = self.factory.get(
            '/', headers={'host': 'funitclub-bhfefqgjgyeua0hj.japanwest-01.azurewebsites.net'})
        self.assertEqual(self.middleware(request).status_code, 200)


class CanonicalHostDisabledTests(TestCase):
    """CANONICAL_HOST が無い開発環境では、そもそも組み込まれない。"""

    @override_settings(CANONICAL_HOST='')
    def test_not_used_without_canonical_host(self):
        with self.assertRaises(MiddlewareNotUsed):
            CanonicalHostMiddleware(dummy_response)


class GateTests(TestCase):
    """公表した成果物（works/ 配下）は、成果物一覧から辿ったときだけ開く。"""

    def setUp(self):
        self.work = Work.objects.create(category='Web App', title='カウントダウン',
                                        description='説明', url='https://funitclub.org/countdown/')
        self.list_url = reverse('home:work_list')

    def link_in_list(self):
        """成果物一覧に出ている、そのアプリへのリンク。"""
        html = self.client.get(self.list_url).content.decode()
        start = html.index('https://funitclub.org/countdown/')
        return html[start:html.index('"', start)].replace('&amp;', '&')

    def test_direct_access_goes_back_to_the_list(self):
        self.assertRedirects(self.client.get('/countdown/'), self.list_url)

    def test_link_from_the_list_opens_the_app(self):
        link = self.link_in_list()
        self.assertIn(f'{gate.PARAM}=', link)

        # 通行証つきで入ると、通行証を落とした URL へ送られる
        path = link.replace('https://funitclub.org', '')
        self.assertRedirects(self.client.get(path), '/countdown/')
        self.assertEqual(self.client.get('/countdown/').status_code, 200)

    def test_once_inside_the_app_keeps_working(self):
        self.client.get(self.link_in_list().replace('https://funitclub.org', ''))
        self.client.get('/countdown/')
        self.assertEqual(self.client.get('/countdown/events/').status_code, 200)

    def test_another_browser_cannot_use_the_same_link_forever(self):
        """通行証は URL に残らないので、アドレス欄をコピーして渡しても一覧に戻される。"""
        self.client.get(self.link_in_list().replace('https://funitclub.org', ''))
        self.client.cookies.clear()
        self.assertRedirects(self.client.get('/countdown/'), self.list_url)

    def test_expired_pass_is_refused(self):
        token = gate.make_token('/countdown/')
        with self.settings(GATE_MAX_AGE=-1):
            self.assertRedirects(self.client.get(f'/countdown/?{gate.PARAM}={token}'), self.list_url)

    def test_a_pass_is_only_for_its_own_app(self):
        token = gate.make_token('/countdown/')
        self.assertRedirects(self.client.get(f'/fe/?{gate.PARAM}={token}'), self.list_url)

    def test_mail_links_stay_open_without_a_pass(self):
        """別の鍵（メールの署名付きリンク）で守られている入口は素通し。"""
        response = self.client.get('/countdown/notify/confirm/not-a-real-token/')
        self.assertNotEqual(response.status_code, 302)

    def test_an_exempt_entrance_does_not_open_the_whole_app(self):
        """素通しの入口を開いても、印は付かない。"""
        self.client.get('/countdown/notify/confirm/not-a-real-token/')
        self.assertRedirects(self.client.get('/countdown/'), self.list_url)

    def test_the_daily_run_is_still_reachable(self):
        """GitHub Actions からの呼び出しは、通行証ではなくトークンで通す。"""
        self.assertEqual(self.client.post('/countdown/notify/run/').status_code, 404)

    def test_outside_links_are_left_alone(self):
        self.assertEqual(gate.link('https://example.com/app/', settings), 'https://example.com/app/')


@override_settings(GATE_BACK={'/protein/': 'home:wg_list'})
class WgGateTests(TestCase):
    """作っている途中のアプリ（wg/ 配下）は、WG一覧へ送り返す。"""

    def setUp(self):
        self.wg = Wg.objects.create(code='WG-09', name='タンパク質', description='説明',
                                    status=Wg.ACTIVE, app_url='https://funitclub.org/protein/')
        self.list_url = reverse('home:wg_list')

    def test_direct_access_goes_back_to_the_wg_list(self):
        """送り返す先は、そのアプリが載っている一覧（成果物一覧ではない）。"""
        self.assertRedirects(self.client.get('/protein/'), self.list_url,
                             fetch_redirect_response=False)

    def test_the_wg_list_hands_out_a_pass(self):
        html = self.client.get(self.list_url).content.decode()
        self.assertIn(f'/protein/?{gate.PARAM}=', html.replace('&amp;', '&'))


class SubAppDiscoveryTests(TestCase):
    """サブアプリは、置かれているフォルダーから自動で組み込む（config/subapps.py）。"""

    def make(self, tmp, folder, name, *, urls=True):
        app = tmp / folder / name
        app.mkdir(parents=True)
        (app / '__init__.py').touch()
        if urls:
            (app / 'urls.py').touch()

    def test_finds_apps_in_both_folders(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self.make(tmp, 'wg', 'protein')
            self.make(tmp, 'works', 'countdown')

            self.assertEqual(subapps.discover(tmp), [('wg', 'protein'), ('works', 'countdown')])
            self.assertEqual(subapps.installed(tmp), ['wg.protein', 'works.countdown'])

    def test_sends_each_back_to_its_own_list(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self.make(tmp, 'wg', 'protein')
            self.make(tmp, 'works', 'countdown')

            self.assertEqual(subapps.gate_back(tmp), {'/protein/': 'home:wg_list',
                                                      '/countdown/': 'home:work_list'})

    def test_half_finished_folders_are_skipped(self):
        """取り込みが途中で壊れたものを読み込まない。"""
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self.make(tmp, 'wg', 'broken', urls=False)
            (tmp / 'wg' / '__pycache__').mkdir()

            self.assertEqual(subapps.discover(tmp), [])

    def test_nothing_to_find_is_fine(self):
        """手元のリポジトリには wg/ のアプリが無い（デプロイのときだけ入る）。"""
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(subapps.discover(Path(d)), [])

    def test_the_site_mounts_what_is_there(self):
        """いま置かれているものが、実際に URL になっている。

        中の URL の名前はアプリに任せるので、名前空間が登録されているかだけを見る。
        """
        from django.urls import get_resolver

        mounted = get_resolver().namespace_dict
        for folder, name in subapps.discover(settings.BASE_DIR):
            with self.subTest(app=name):
                self.assertIn(name, mounted)
                self.assertEqual(mounted[name][0], f'{name}/')
