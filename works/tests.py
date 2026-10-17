# works/tests.py
#
# 成果物のアプリへの導線（works/gate.py）。ホームページの一覧から辿ったときだけ
# 開けること、別の鍵で守られた入口は素通しのままであることを確かめる。

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from catalog.models import Work

from . import gate


class WorksGateTests(TestCase):

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
        with self.settings(WORKS_GATE_MAX_AGE=-1):
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
