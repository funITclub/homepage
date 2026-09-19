import json
import time
from unittest import mock
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from catalog.forms import WgForm
from catalog.models import Wg

from . import github, google
from .http import ServiceError, call
from .config import club_classroom_url
from .links import decode_course_id, is_wg_team
from .views import SESSION_KEY

ENABLED = dict(
    CLUB_CLASSROOM_COURSE='https://classroom.google.com/c/OTg3NjU0MzIxMDk4',  # 987654321098
    GOOGLE_OAUTH_CLIENT_ID='google-client', GOOGLE_OAUTH_CLIENT_SECRET='google-secret',
    GITHUB_APP_ID='1', GITHUB_APP_CLIENT_ID='gh-client', GITHUB_APP_CLIENT_SECRET='gh-secret',
    GITHUB_APP_PRIVATE_KEY='dummy',
)


class LinkTests(SimpleTestCase):

    def test_reads_class_id_from_url_or_number(self):
        # クラスの URL の /c/ の後ろは、クラスの ID を base64 にしたもの
        self.assertEqual(decode_course_id('https://classroom.google.com/c/OTg3NjU0MzIxMDk4'), '987654321098')
        self.assertEqual(decode_course_id('https://classroom.google.com/u/1/c/OTg3NjU0MzIxMDk4/t/all'),
                         '987654321098')
        self.assertEqual(decode_course_id('987654321098'), '987654321098')
        self.assertIsNone(decode_course_id('https://classroom.google.com/c/not-an-id'))
        self.assertIsNone(decode_course_id(''))

    @override_settings(CLUB_CLASSROOM_COURSE='987654321098')
    def test_club_class_url_opens_the_class(self):
        self.assertEqual(club_classroom_url(), 'https://classroom.google.com/c/OTg3NjU0MzIxMDk4')

    def test_only_wg_teams_are_allowed(self):
        self.assertTrue(is_wg_team('wg-countdown'))
        for team in ['owners', 'wg-', 'WG-Countdown', 'wg-../owners', '']:
            with self.subTest(team=team):
                self.assertFalse(is_wg_team(team))


class WgFormTests(TestCase):

    def data(self, **overrides):
        data = {'code': 'WG-04', 'name': 'カウントダウン', 'description': '説明', 'status': Wg.IDLE,
                'sort_order': 0, 'is_published': True, 'github_team': 'wg-countdown'}
        data.update(overrides)
        return data

    def test_wg_team_or_empty(self):
        self.assertTrue(WgForm(self.data()).is_valid())
        self.assertTrue(WgForm(self.data(github_team='')).is_valid())

    def test_rejects_teams_other_than_wg(self):
        form = WgForm(self.data(github_team='owners'))
        self.assertFalse(form.is_valid())
        self.assertIn('github_team', form.errors)


class WgListButtonTests(TestCase):

    def setUp(self):
        self.url = reverse('home:wg_list')
        self.joinable = Wg.objects.create(code='WG-01', name='参加できる', description='説明',
                                          status=Wg.ACTIVE, github_team='wg-one')
        self.idle = Wg.objects.create(code='WG-02', name='準備中', description='説明', status=Wg.IDLE)

    @override_settings(**ENABLED)
    def test_join_button_only_for_wgs_with_a_team(self):
        response = self.client.get(self.url)
        self.assertContains(response, reverse('wgjoin:start', args=[self.joinable.pk]))
        self.assertNotContains(response, reverse('wgjoin:start', args=[self.idle.pk]))
        # 登録のない準備中の WG は、これまでどおりクラブの参加案内へ
        self.assertContains(response, reverse('home:join'))

    @override_settings(GOOGLE_OAUTH_CLIENT_ID='')
    def test_no_join_button_until_settings_are_complete(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, 'WG に参加')
        self.assertEqual(self.client.get(reverse('wgjoin:start', args=[self.joinable.pk])).status_code, 404)


@override_settings(**ENABLED)
class JoinFlowTests(TestCase):

    def setUp(self):
        self.wg = Wg.objects.create(code='WG-04', name='カウントダウン', description='説明',
                                    status=Wg.ACTIVE, github_team='wg-countdown')

    def begin_google(self):
        response = self.client.get(reverse('wgjoin:google_start', args=[self.wg.pk]))
        return parse_qs(urlparse(response['Location']).query)

    def google_callback(self, **params):
        return self.client.get(reverse('wgjoin:google_callback'), params)

    def test_start_page_explains_the_two_steps(self):
        response = self.client.get(reverse('wgjoin:start', args=[self.wg.pk]))
        self.assertContains(response, '大学の Google アカウントで始める')
        self.assertContains(response, 'GitHub でログイン')
        self.assertContains(response, 'Chat スペースのリンク')

    def test_google_login_asks_only_to_see_classes_with_pkce(self):
        query = self.begin_google()
        self.assertEqual(query['scope'][0].split(), google.SCOPES)
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['hd'], ['bukkyo-u.ac.jp'])
        self.assertEqual(query['state'][0], self.client.session[SESSION_KEY]['google_state'])

    def test_wrong_state_is_rejected(self):
        self.begin_google()
        with mock.patch.object(google, 'exchange_code') as exchange:
            response = self.google_callback(state='forged', code='c')
        self.assertRedirects(response, reverse('home:wg_list'))
        exchange.assert_not_called()

    @mock.patch.object(google, 'revoke')
    @mock.patch.object(google, 'is_club_member', return_value=False)
    @mock.patch.object(google, 'exchange_code', return_value='google-token')
    def test_non_member_stops_before_github(self, exchange, member, revoke):
        state = self.begin_google()['state'][0]
        response = self.google_callback(state=state, code='c')

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'メンバーとして確認できませんでした', status_code=403)
        member.assert_called_once_with('google-token', '987654321098')
        revoke.assert_called_once_with('google-token')
        self.assertNotIn(SESSION_KEY, self.client.session)
        # GitHub の手続きには進めない
        self.assertRedirects(self.client.get(reverse('wgjoin:github_step', args=[self.wg.pk])),
                             reverse('wgjoin:start', args=[self.wg.pk]))

    @mock.patch.object(google, 'revoke')
    @mock.patch.object(google, 'is_club_member', return_value=True)
    @mock.patch.object(google, 'exchange_code', return_value='google-token')
    def test_member_moves_on_to_github(self, exchange, member, revoke):
        state = self.begin_google()['state'][0]
        response = self.google_callback(state=state, code='c')

        self.assertRedirects(response, reverse('wgjoin:github_step', args=[self.wg.pk]))
        revoke.assert_called_once_with('google-token')
        # session に残すのは手続きの印だけ。トークンや個人の情報は持たない
        flow = self.client.session[SESSION_KEY]
        self.assertEqual(set(flow), {'wg', 'member_at'})
        self.assertNotIn('google-token', json.dumps(flow))

    @mock.patch.object(google, 'revoke')
    @mock.patch.object(google, 'is_club_member', side_effect=ServiceError('down'))
    @mock.patch.object(google, 'exchange_code', return_value='google-token')
    def test_classroom_failure_is_reported(self, exchange, member, revoke):
        state = self.begin_google()['state'][0]
        response = self.google_callback(state=state, code='c')
        self.assertContains(response, '手続きの途中で失敗しました', status_code=502)
        revoke.assert_called_once_with('google-token')

    def test_cancelled_google_login(self):
        state = self.begin_google()['state'][0]
        response = self.google_callback(state=state, error='access_denied')
        self.assertContains(response, '手続きを中止しました')

    def pass_google_check(self, checked_at=None):
        session = self.client.session
        session[SESSION_KEY] = {'wg': self.wg.pk, 'member_at': checked_at or time.time()}
        session.save()

    def begin_github(self):
        response = self.client.get(reverse('wgjoin:github_start', args=[self.wg.pk]))
        return parse_qs(urlparse(response['Location']).query)['state'][0]

    @mock.patch.object(github, 'add_to_team', return_value=github.PENDING)
    @mock.patch.object(github, 'revoke_user_token')
    @mock.patch.object(github, 'login_name', return_value='octo-student')
    @mock.patch.object(github, 'exchange_code', return_value='gh-token')
    def test_member_is_added_to_the_wg_team(self, exchange, login, revoke, add):
        self.pass_google_check()
        state = self.begin_github()
        with self.assertLogs('wgjoin', level='INFO') as logs:
            response = self.client.get(reverse('wgjoin:github_callback'), {'state': state, 'code': 'c'})

        add.assert_called_once_with('wg-countdown', 'octo-student')
        revoke.assert_called_once_with('gh-token')
        self.assertContains(response, 'カウントダウン に参加しました')
        self.assertContains(response, 'funITclub への招待')
        # Chat には本人が入る。クラブのクラスへ案内する
        self.assertContains(response, 'https://classroom.google.com/c/OTg3NjU0MzIxMDk4')
        self.assertNotIn(SESSION_KEY, self.client.session)
        # ユーザー名はログに出さない
        self.assertNotIn('octo-student', '\n'.join(logs.output))

    def test_github_step_needs_the_google_check_of_the_same_wg(self):
        other = Wg.objects.create(code='WG-05', name='別', description='説明', status=Wg.ACTIVE,
                                  github_team='wg-other')
        self.pass_google_check()
        self.assertRedirects(self.client.get(reverse('wgjoin:github_start', args=[other.pk])),
                             reverse('wgjoin:start', args=[other.pk]))

    @mock.patch.object(github, 'add_to_team')
    def test_expired_google_check_does_not_reach_github(self, add):
        self.pass_google_check()
        state = self.begin_github()
        session = self.client.session
        session[SESSION_KEY]['member_at'] = time.time() - 2 * 60 * 60
        session.save()
        response = self.client.get(reverse('wgjoin:github_callback'), {'state': state, 'code': 'c'})
        self.assertContains(response, 'やり直してください')
        add.assert_not_called()


def _rsa_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return key, pem


class GitHubClientTests(SimpleTestCase):

    def test_app_jwt_is_signed_with_the_app_key(self):
        key, pem = _rsa_key()
        with override_settings(GITHUB_APP_ID='12345', GITHUB_APP_PRIVATE_KEY=pem):
            token = github._app_jwt()
        claims = jwt.decode(token, key.public_key(), algorithms=['RS256'])
        self.assertEqual(claims['iss'], '12345')
        self.assertLess(claims['exp'] - claims['iat'], 11 * 60)

    def test_refuses_teams_other_than_wg(self):
        with self.assertRaises(ValueError):
            github.add_to_team('owners', 'someone')

    @mock.patch.object(github, '_installation_token', return_value='inst')
    @mock.patch.object(github, 'call', return_value=(200, {'state': 'active', 'role': 'maintainer'}))
    def test_existing_member_is_left_as_is(self, call_mock, _):
        """リーダー（maintainer）が押し直しても、役割を member に下げない。"""
        self.assertEqual(github.add_to_team('wg-countdown', 'leader'), github.ACTIVE)
        self.assertEqual([c.args[0] for c in call_mock.call_args_list], ['GET'])

    @mock.patch.object(github, '_installation_token', return_value='inst')
    @mock.patch.object(github, 'call', side_effect=[(404, {}), (200, {'state': 'pending'})])
    def test_new_person_is_invited_through_the_team(self, call_mock, _):
        self.assertEqual(github.add_to_team('wg-countdown', 'newbie'), github.PENDING)
        method, url = call_mock.call_args_list[1].args
        self.assertEqual(method, 'PUT')
        self.assertTrue(url.endswith('/orgs/funITclub/teams/wg-countdown/memberships/newbie'))
        self.assertEqual(call_mock.call_args_list[1].kwargs['json_body'], {'role': 'member'})


class HttpTests(SimpleTestCase):

    @mock.patch('wgjoin.http.urlopen', side_effect=URLError('down'))
    def test_error_message_does_not_include_the_path(self, _):
        """パスにユーザー名が入る API があるので、ログに出る文言はホスト名まで。"""
        with self.assertRaises(ServiceError) as ctx:
            call('GET', 'https://api.github.com/orgs/funITclub/teams/wg-x/memberships/octo-student')
        self.assertIn('api.github.com', str(ctx.exception))
        self.assertNotIn('octo-student', str(ctx.exception))
