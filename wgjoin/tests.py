import time
from unittest import mock
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core import mail as outbox
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from catalog.forms import WgForm
from catalog.models import Wg

from . import github, google
from .http import ServiceError, call
from .config import club_classroom_url
from .links import decode_course_id, is_wg_team
from .verify import make_link_token
from .views import SESSION_KEY

ENABLED = dict(
    CLUB_CLASSROOM_COURSE='https://classroom.google.com/c/OTg3NjU0MzIxMDk4',  # 987654321098
    GOOGLE_OAUTH_CLIENT_ID='google-client', GOOGLE_OAUTH_CLIENT_SECRET='google-secret',
    GOOGLE_OAUTH_REFRESH_TOKEN='staff-refresh',
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


MEMBER = 'bu1111111111@bukkyo-u.ac.jp'


@override_settings(**ENABLED)
class JoinFlowTests(TestCase):

    def setUp(self):
        cache.clear()
        self.wg = Wg.objects.create(code='WG-04', name='カウントダウン', description='説明',
                                    status=Wg.ACTIVE, github_team='wg-countdown')
        self.start_url = reverse('wgjoin:start', args=[self.wg.pk])

    def submit(self, email=MEMBER, member=True):
        with mock.patch.object(google, 'is_club_member', return_value=member) as check:
            response = self.client.post(self.start_url, {'email': email})
        return response, check

    def link_in_mail(self):
        body = outbox.outbox[-1].body
        return next(line for line in body.splitlines() if '/wg/join/verify/' in line)

    def test_start_page_explains_the_steps(self):
        response = self.client.get(self.start_url)
        self.assertContains(response, '大学のメールアドレス')
        self.assertContains(response, 'GitHub でログイン')
        self.assertContains(response, 'Chat スペースのリンク')

    def test_only_university_addresses(self):
        response, check = self.submit(email='someone@gmail.com')
        self.assertContains(response, '大学から発行されたメールアドレス')
        check.assert_not_called()
        self.assertEqual(len(outbox.outbox), 0)

    def test_member_gets_a_link_by_mail(self):
        response, check = self.submit()
        self.assertRedirects(response, reverse('wgjoin:sent', args=[self.wg.pk]))
        check.assert_called_once_with(MEMBER, '987654321098')
        self.assertEqual(outbox.outbox[0].to, [MEMBER])
        self.assertIn('http://testserver/wg/join/verify/', self.link_in_mail())
        # リンクにアドレスは入れない
        self.assertNotIn('bu1111111111', self.link_in_mail())

    def test_non_member_gets_a_notice_but_the_screen_is_the_same(self):
        """他人のアドレスを入れて、その人がメンバーかを画面から探れない。"""
        member_response, _ = self.submit()
        other_response, _ = self.submit(email='bu2222222222@bukkyo-u.ac.jp', member=False)
        self.assertEqual(member_response['Location'], other_response['Location'])
        notice = outbox.outbox[-1]
        self.assertIn('確認できませんでした', notice.body)
        self.assertNotIn('/wg/join/verify/', notice.body)

    def test_address_is_not_logged(self):
        with self.assertLogs('wgjoin', level='INFO') as logs:
            self.submit()
        self.assertNotIn('bu1111111111', '\n'.join(logs.output))

    def test_roster_failure_is_reported_without_sending(self):
        with mock.patch.object(google, 'is_club_member', side_effect=ServiceError('403')):
            response = self.client.post(self.start_url, {'email': MEMBER})
        self.assertContains(response, '手続きの途中で失敗しました', status_code=502)
        self.assertEqual(len(outbox.outbox), 0)

    @override_settings(WG_JOIN_SEND_LIMITS=((10, 3600), (2, 3600)))
    def test_too_many_mails_to_the_same_address_are_refused(self):
        self.submit()
        self.submit()
        response, check = self.submit()
        self.assertEqual(response.status_code, 429)
        check.assert_not_called()
        self.assertEqual(len(outbox.outbox), 2)

    def test_link_opens_the_github_step(self):
        self.submit()
        response = self.client.get(self.link_in_mail())
        self.assertRedirects(response, reverse('wgjoin:github_step', args=[self.wg.pk]))
        self.assertContains(self.client.get(response['Location']), 'GitHub でログインして登録する')
        self.assertEqual(set(self.client.session[SESSION_KEY]), {'wg', 'member_at', 'nonce'})

    def test_broken_or_expired_link_is_refused(self):
        self.assertEqual(self.client.get(reverse('wgjoin:verify', args=['broken'])).status_code, 400)
        token = make_link_token(self.wg.pk)
        with override_settings(WG_JOIN_LINK_MAX_AGE=-1):
            self.assertEqual(self.client.get(reverse('wgjoin:verify', args=[token])).status_code, 400)

    def test_github_step_needs_the_link(self):
        self.assertRedirects(self.client.get(reverse('wgjoin:github_step', args=[self.wg.pk])), self.start_url)
        other = Wg.objects.create(code='WG-05', name='別', description='説明', status=Wg.ACTIVE,
                                  github_team='wg-other')
        self.client.get(reverse('wgjoin:verify', args=[make_link_token(self.wg.pk)]))
        self.assertRedirects(self.client.get(reverse('wgjoin:github_start', args=[other.pk])),
                             reverse('wgjoin:start', args=[other.pk]))

    def open_link_and_begin_github(self, token=None):
        self.client.get(reverse('wgjoin:verify', args=[token or make_link_token(self.wg.pk)]))
        response = self.client.get(reverse('wgjoin:github_start', args=[self.wg.pk]))
        return parse_qs(urlparse(response['Location']).query)['state'][0]

    def finish_github(self, state):
        return self.client.get(reverse('wgjoin:github_callback'), {'state': state, 'code': 'c'})

    @mock.patch.object(github, 'add_to_team', return_value=github.PENDING)
    @mock.patch.object(github, 'revoke_user_token')
    @mock.patch.object(github, 'login_name', return_value='octo-student')
    @mock.patch.object(github, 'exchange_code', return_value='gh-token')
    def test_github_account_is_added_to_the_wg_team(self, exchange, login, revoke, add):
        state = self.open_link_and_begin_github()
        with self.assertLogs('wgjoin', level='INFO') as logs:
            response = self.finish_github(state)

        add.assert_called_once_with('wg-countdown', 'octo-student')
        revoke.assert_called_once_with('gh-token')
        self.assertContains(response, 'カウントダウン に参加しました')
        self.assertContains(response, 'funITclub への招待')
        # Chat には本人が入る。クラブのクラスへ案内する
        self.assertContains(response, 'https://classroom.google.com/c/OTg3NjU0MzIxMDk4')
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertNotIn('octo-student', '\n'.join(logs.output))

    @mock.patch.object(github, 'add_to_team', return_value=github.ACTIVE)
    @mock.patch.object(github, 'revoke_user_token')
    @mock.patch.object(github, 'login_name', return_value='octo-student')
    @mock.patch.object(github, 'exchange_code', return_value='gh-token')
    def test_a_link_registers_only_once(self, *mocks):
        """転送されたリンクで、別の人の GitHub アカウントを後から足せない。"""
        token = make_link_token(self.wg.pk)
        self.finish_github(self.open_link_and_begin_github(token))
        self.client.logout()
        self.assertEqual(self.client.get(reverse('wgjoin:verify', args=[token])).status_code, 400)

    @mock.patch.object(github, 'add_to_team')
    def test_github_after_the_time_limit_is_refused(self, add):
        state = self.open_link_and_begin_github()
        session = self.client.session
        session[SESSION_KEY]['member_at'] = time.time() - 2 * 60 * 60
        session.save()
        response = self.finish_github(state)
        self.assertContains(response, 'やり直してください')
        add.assert_not_called()


class GoogleClientTests(SimpleTestCase):

    @override_settings(**ENABLED)
    @mock.patch.object(google, '_access_token', return_value='staff-token')
    def test_checks_students_then_teachers_by_address(self, _):
        with mock.patch.object(google, 'call', side_effect=[(404, {}), (200, {})]) as call_mock:
            self.assertTrue(google.is_club_member(MEMBER, '987654321098'))
        urls = [c.args[1] for c in call_mock.call_args_list]
        self.assertTrue(urls[0].endswith('/courses/987654321098/students/bu1111111111%40bukkyo-u.ac.jp'))
        self.assertTrue(urls[1].endswith('/courses/987654321098/teachers/bu1111111111%40bukkyo-u.ac.jp'))

        with mock.patch.object(google, 'call', side_effect=[(404, {}), (404, {})]):
            self.assertFalse(google.is_club_member(MEMBER, '987654321098'))

    @override_settings(**ENABLED)
    @mock.patch.object(google, '_access_token', return_value='staff-token')
    def test_no_permission_is_an_error_not_a_non_member(self, _):
        """運営がクラスの先生でなくなったら、全員を「メンバーでない」にしないで止める。"""
        with mock.patch.object(google, 'call', return_value=(403, {})):
            with self.assertRaises(ServiceError):
                google.is_club_member(MEMBER, '987654321098')

    def test_asks_only_to_read_the_roster(self):
        self.assertEqual(google.SCOPES, ['https://www.googleapis.com/auth/classroom.rosters.readonly'])


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


class SaveToEnvTests(SimpleTestCase):

    def test_replaces_existing_keys_and_appends_new_ones(self):
        import tempfile
        from pathlib import Path

        from .management.commands.wgjoin_google_authorize import save_to_env

        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / '.env'
            env.write_text('# コメント\nEMAIL_HOST_USER=keep\nGOOGLE_OAUTH_CLIENT_ID=old\n', encoding='utf-8')
            save_to_env({'GOOGLE_OAUTH_CLIENT_ID': 'new', 'GOOGLE_OAUTH_REFRESH_TOKEN': 'token'}, env)
            self.assertEqual(env.read_text(encoding='utf-8').splitlines(), [
                '# コメント', 'EMAIL_HOST_USER=keep', 'GOOGLE_OAUTH_CLIENT_ID=new', 'GOOGLE_OAUTH_REFRESH_TOKEN=token'])
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)
