from datetime import date, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .checks import run_daily_checks, warn_if_secret_expiring
from .models import Administrator, notification_emails, public_contact_email


class AdministratorTests(TestCase):
    """管理者情報はこのテーブルだけを見る。設定やテンプレートには書かない。"""

    def test_current_account_is_registered_by_migration(self):
        admin = Administrator.objects.get()
        self.assertEqual(admin.email, 'contact@funitclub.org')
        self.assertEqual(admin.name, '事務局')

    def test_notification_goes_to_every_active_administrator(self):
        Administrator.objects.create(email='second@example.com', sort_order=1)
        Administrator.objects.create(email='muted@example.com', sort_order=2,
                                     receives_notifications=False)
        Administrator.objects.create(email='retired@example.com', sort_order=3,
                                     is_active=False)

        self.assertEqual(notification_emails(),
                         ['contact@funitclub.org', 'second@example.com'])

    def test_public_contact_is_the_first_one(self):
        Administrator.objects.create(email='front@example.com', sort_order=-1)
        self.assertEqual(public_contact_email(), 'front@example.com')

    def test_public_contact_skips_non_public(self):
        Administrator.objects.all().update(is_public_contact=False)
        Administrator.objects.create(email='window@example.com', sort_order=1)

        self.assertEqual(public_contact_email(), 'window@example.com')

    def test_falls_back_when_the_table_is_empty(self):
        """宛先が無いせいで異常に気づけない、という事態を避ける。"""
        Administrator.objects.all().delete()

        self.assertEqual(notification_emails(), ['contact@funitclub.org'])
        self.assertEqual(public_contact_email(), 'contact@funitclub.org')

    def test_falls_back_when_the_table_cannot_be_read(self):
        with mock.patch('edit.models.Administrator.objects') as objects:
            objects.notified.side_effect = RuntimeError('boom')
            objects.public_contacts.side_effect = RuntimeError('boom')

            self.assertEqual(notification_emails(), ['contact@funitclub.org'])
            self.assertEqual(public_contact_email(), 'contact@funitclub.org')


class JoinMailRecipientTests(TestCase):
    """参加フォームの宛先も管理者テーブルから取る。"""

    def test_notification_is_sent_to_all_administrators(self):
        Administrator.objects.create(email='second@example.com', sort_order=1)

        self.client.post(reverse('home:join_apply'), {
            'name': '佛教 太郎',
            'email': 'bu0000000000@bukkyo-u.ac.jp',
            'wg': '',
        })

        notification, auto_reply = mail.outbox
        self.assertEqual(notification.to,
                         ['contact@funitclub.org', 'second@example.com'])
        # 自動返信の返信先は公開用の問い合わせ先
        self.assertEqual(auto_reply.reply_to, ['contact@funitclub.org'])


@override_settings(LOGIN_FAILURE_RULE=(3, 600))
class LoginFailureTests(TestCase):
    """編集画面へのログイン失敗を監視する。遮断はしない。"""

    def setUp(self):
        cache.clear()
        User.objects.create_user('editor', password='funitclub-test-pass')
        self.url = reverse('edit:login')

    def fail_login(self, **extra):
        return self.client.post(self.url, {
            'username': 'editor', 'password': 'wrong-password'}, **extra)

    def test_notifies_when_failures_reach_the_limit(self):
        for _ in range(2):
            self.fail_login()
        self.assertEqual(len(mail.outbox), 0)

        self.fail_login()

        notice, = mail.outbox
        self.assertIn('ログイン失敗が続いています', notice.subject)
        self.assertEqual(notice.to, ['contact@funitclub.org'])
        self.assertIn('10分間に3回', notice.body)
        self.assertIn('changepassword', notice.body)

    def test_notifies_only_once(self):
        for _ in range(6):
            self.fail_login()

        self.assertEqual(len(mail.outbox), 1)

    def test_username_is_not_included(self):
        """打ち間違いで本物のIDが漏れないよう、入力値は載せない。"""
        for _ in range(3):
            self.client.post(self.url, {
                'username': 'secret-account-name', 'password': 'x'})

        self.assertNotIn('secret-account-name', mail.outbox[0].body)

    def test_successful_login_is_not_counted(self):
        for _ in range(2):
            self.fail_login()
        self.client.post(self.url, {
            'username': 'editor', 'password': 'funitclub-test-pass'})
        self.fail_login()

        self.assertEqual(len(mail.outbox), 0)

    def test_does_not_block_the_ip(self):
        """締め出すと運営自身が復旧できなくなるため、遮断はしない。"""
        from home.models import BlockedIp

        for _ in range(6):
            self.fail_login()

        self.assertFalse(BlockedIp.objects.exists())
        self.assertEqual(self.client.get(reverse('home:index')).status_code, 200)


@override_settings(EMAIL_SECRET_EXPIRES_ON='2028-08-19')
class SecretExpiryTests(TestCase):
    """SMTP のシークレット期限を切れる前に知らせる。"""

    def setUp(self):
        cache.clear()
        self.expires_on = date(2028, 8, 19)

    def test_no_warning_while_far_from_expiry(self):
        warn_if_secret_expiring(today=self.expires_on - timedelta(days=31))
        self.assertEqual(len(mail.outbox), 0)

    def test_warns_at_each_stage(self):
        for days, expected in [(30, '残り30日'), (14, '残り14日'),
                               (7, '残り7日'), (1, '残り1日')]:
            with self.subTest(days=days):
                warn_if_secret_expiring(today=self.expires_on - timedelta(days=days))
                self.assertIn(expected, mail.outbox[-1].subject)

        self.assertEqual(len(mail.outbox), 4)

    def test_warns_once_per_stage(self):
        for _ in range(3):
            warn_if_secret_expiring(today=self.expires_on - timedelta(days=7))

        self.assertEqual(len(mail.outbox), 1)

    def test_warns_after_expiry(self):
        warn_if_secret_expiring(today=self.expires_on + timedelta(days=1))

        self.assertIn('失効しています', mail.outbox[0].subject)
        self.assertIn('az ad app credential reset', mail.outbox[0].body)

    def test_body_explains_how_to_renew(self):
        warn_if_secret_expiring(today=self.expires_on - timedelta(days=7))

        body = mail.outbox[0].body
        self.assertIn('az keyvault secret set', body)
        self.assertIn('EMAIL_SECRET_EXPIRES_ON', body)

    @override_settings(EMAIL_SECRET_EXPIRES_ON='')
    def test_does_nothing_when_not_configured(self):
        warn_if_secret_expiring(today=self.expires_on)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_SECRET_EXPIRES_ON='not-a-date')
    def test_warns_in_the_log_when_the_date_is_broken(self):
        with self.assertLogs('edit.checks', level='WARNING'):
            warn_if_secret_expiring(today=self.expires_on)
        self.assertEqual(len(mail.outbox), 0)


class DailyCheckTests(TestCase):
    """点検は1日1回だけ走らせる。"""

    def setUp(self):
        cache.clear()

    def test_runs_once_a_day(self):
        with mock.patch('edit.checks.warn_if_secret_expiring') as check:
            self.assertTrue(run_daily_checks())
            self.assertFalse(run_daily_checks())

        self.assertEqual(check.call_count, 1)

    def test_request_triggers_the_check(self):
        with mock.patch('edit.checks.warn_if_secret_expiring') as check:
            self.client.get(reverse('home:index'))

        check.assert_called_once()

    def test_failure_does_not_break_the_request(self):
        with mock.patch('edit.checks.warn_if_secret_expiring',
                        side_effect=RuntimeError('boom')):
            with self.assertLogs('edit.checks', level='ERROR'):
                response = self.client.get(reverse('home:index'))

        self.assertEqual(response.status_code, 200)


class ErrorNotificationTests(TestCase):
    """500 エラーの通知先も管理者テーブルから取る（settings.ADMINS は使わない）。"""

    def setUp(self):
        cache.clear()

    def test_handler_sends_to_administrators(self):
        import logging

        from .log_handlers import DbAdminEmailHandler

        Administrator.objects.create(email='second@example.com', sort_order=1)
        handler = DbAdminEmailHandler()
        handler.emit(logging.LogRecord(
            name='django.request', level=logging.ERROR, pathname=__file__, lineno=1,
            msg='Internal Server Error: /boom', args=(), exc_info=None,
        ))

        notice, = mail.outbox
        self.assertEqual(notice.to,
                         ['contact@funitclub.org', 'second@example.com'])
        self.assertIn('Internal Server Error', notice.subject)

    def test_error_notifications_are_capped(self):
        """DB障害などで ERROR が連続しても、受信箱を埋めない。"""
        import logging

        from .log_handlers import DbAdminEmailHandler

        handler = DbAdminEmailHandler()
        for _ in range(20):
            handler.emit(logging.LogRecord(
                name='config.middleware', level=logging.ERROR, pathname=__file__,
                lineno=1, msg='遮断リストの取得に失敗しました', args=(), exc_info=None))

        from django.conf import settings
        self.assertEqual(len(mail.outbox), settings.ERROR_NOTIFY_MAX_PER_HOUR)

    def test_capping_does_not_notify_about_itself(self):
        """抑制のログは warning 止まり。error にすると通知が堂々巡りになる。"""
        from .notify import allow_notification

        with self.assertLogs('edit.notify', level='WARNING') as logs:
            for _ in range(12):
                allow_notification('error', max_per_hour=10)

        for line in logs.output:
            self.assertTrue(line.startswith('WARNING'), line)

    def test_admins_setting_is_not_used(self):
        from django.conf import settings

        self.assertFalse(getattr(settings, 'ADMINS', []))
