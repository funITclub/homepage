import time
from datetime import timedelta
from unittest import mock

from django import forms
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from catalog.models import Wg
from config.middleware import BlockedIpMiddleware

from .models import BlockedIp


class JoinFormTests(TestCase):
    """参加フォーム（/join/）。佛教大学のアドレスからだけ受け付ける。"""

    def setUp(self):
        self.url = reverse('home:join')
        self.wg = Wg.objects.create(code='WG-01', name='データ分析', description='説明')

    def post(self, **overrides):
        data = {
            'name': '佛教 太郎',
            'email': 'bu0000000000@bukkyo-u.ac.jp',
            'wg': self.wg.pk,
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_page_opens_without_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '大学のメールアドレス')

    def test_valid_post_sends_two_mails_and_redirects(self):
        response = self.post()
        self.assertRedirects(response, self.url)

        self.assertEqual(len(mail.outbox), 2)
        notification, auto_reply = mail.outbox

        # 差出人は funitclub.org。大学アカウントでは SMTP 送信できないため、
        # 送信は独自ドメイン、返信だけ大学アドレスに向ける。
        self.assertEqual(notification.from_email, 'fun IT club <no-reply@funitclub.org>')
        self.assertEqual(auto_reply.from_email, 'fun IT club <no-reply@funitclub.org>')

        # 事務局あて。返信するとそのまま申込者に届く。
        self.assertEqual(notification.to, ['contact@funitclub.org'])
        self.assertEqual(notification.reply_to, ['bu0000000000@bukkyo-u.ac.jp'])
        self.assertIn('佛教 太郎', notification.body)
        self.assertIn('WG-01 データ分析', notification.body)

        # 申込者あての控え。第三者にも届きうるので、心当たりがない場合の案内を必ず入れる。
        self.assertEqual(auto_reply.to, ['bu0000000000@bukkyo-u.ac.jp'])
        self.assertIn('受け付けました', auto_reply.subject)
        self.assertIn('心当たりがない場合', auto_reply.body)
        self.assertIn('contact@funitclub.org', auto_reply.body)

    def test_form_has_no_free_text_field(self):
        """自由記述は持たせない。

        入力されたアドレスの持ち主を確認していないため、自由記述があると
        第三者あての自動返信に任意の文章を載せられてしまう（踏み台化）。
        項目を足すときはこの制約を壊していないか確認すること。
        """
        form = self.client.get(self.url).context['form']

        self.assertEqual(list(form.fields), ['name', 'email', 'wg'])
        for name, field in form.fields.items():
            with self.subTest(field=name):
                self.assertNotIsInstance(field.widget, forms.Textarea)

    def test_extra_post_data_is_ignored(self):
        """フォームに無い項目を POST されても、メール本文には入らない。"""
        self.client.post(self.url, {
            'name': '佛教 太郎',
            'email': 'bu0000000000@bukkyo-u.ac.jp',
            'wg': '',
            'message': 'https://example.com/phishing',
        })

        for m in mail.outbox:
            with self.subTest(to=m.to):
                self.assertNotIn('example.com', m.body)

    def test_other_domain_is_rejected(self):
        response = self.post(email='taro@gmail.com')

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'email',
                             '大学から発行されたメールアドレス（@bukkyo-u.ac.jp）を入力してください。')
        self.assertEqual(len(mail.outbox), 0)

    def test_similar_domain_is_rejected(self):
        """紛らわしいドメイン（部分一致）は通さない。"""
        for email in ['taro@notbukkyo-u.ac.jp', 'taro@bukkyo-u.ac.jp.example.com']:
            with self.subTest(email=email):
                self.post(email=email)
                self.assertEqual(len(mail.outbox), 0)

    def test_domain_is_case_insensitive(self):
        self.post(email='bu0000000000@Bukkyo-U.ac.jp')
        self.assertEqual(len(mail.outbox), 2)

    def test_wg_is_optional(self):
        self.post(wg='')
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('未定', mail.outbox[0].body)

    def test_newline_in_name_does_not_500(self):
        """氏名に改行を入れてもヘッダは汚染されず、500 にもならない。"""
        response = self.post(name='X\nBcc: attacker@example.com')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(response, 'メールの送信に失敗しました')

    def test_email_is_not_written_to_log(self):
        """申込者のメールアドレスをログに残さない。"""
        with self.assertLogs('home.views', level='INFO') as logs:
            self.post()

        self.assertNotIn('bu0000000000@bukkyo-u.ac.jp', '\n'.join(logs.output))

    def test_url_in_name_is_rejected(self):
        """氏名に URL は入れさせない（自動返信で第三者に読まれるため）。"""
        for name in ['https://bit.ly/abc', 'www.example.com', '至急 http://x.jp', 'ftp://x']:
            with self.subTest(name=name):
                response = self.post(name=name)
                self.assertFormError(response.context['form'], 'name',
                                     'お名前に URL は入力できません。')
                self.assertEqual(len(mail.outbox), 0)

    def test_draft_wg_is_not_selectable(self):
        draft = Wg.objects.create(code='WG-99', name='下書きWG', description='説明',
                                  is_published=False)
        response = self.post(wg=draft.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotContains(response, '下書きWG')


@override_settings(JOIN_BURST_RULES=[(3, 600)])
class BurstDetectionTests(TestCase):
    """連続送信の検知と遮断。"""

    def setUp(self):
        cache.clear()
        self.url = reverse('home:join')

    def post(self, **extra):
        return self.client.post(self.url, {
            'name': '佛教 太郎',
            'email': 'bu0000000000@bukkyo-u.ac.jp',
            'wg': '',
        }, **extra)

    def test_blocks_after_exceeding_the_limit(self):
        with self.assertLogs('home.views', level='WARNING') as logs:
            for _ in range(4):
                self.post()

        output = '\n'.join(logs.output)
        self.assertIn('10分間に4件（上限3件）', output)
        self.assertIn('IP を遮断しました', output)

        blocked = BlockedIp.objects.get()
        self.assertEqual(blocked.ip, '127.0.0.1')
        self.assertIn('連続送信', blocked.reason)

        # 1回目は24時間で自動的に解ける（巻き添えを永久に残さない）
        self.assertEqual(blocked.block_count, 1)
        self.assertFalse(blocked.is_permanent)
        self.assertAlmostEqual(
            (blocked.expires_at - timezone.now()).total_seconds(), 24 * 3600, delta=60)

    def test_repeat_offender_is_escalated_to_permanent(self):
        """繰り返すほど重くなる: 24時間 → 7日間 → 恒久。"""
        expected = [24 * 3600, 7 * 24 * 3600, None, None]

        for round_number, seconds in enumerate(expected, start=1):
            cache.clear()  # 前回の連続送信カウントを持ち越さない
            with mock.patch('home.views.timezone.now', return_value=timezone.now()):
                for _ in range(4):
                    self.post()

            blocked = BlockedIp.objects.get()
            with self.subTest(round=round_number):
                self.assertEqual(blocked.block_count, round_number)
                if seconds is None:
                    self.assertTrue(blocked.is_permanent)
                else:
                    self.assertAlmostEqual(
                        (blocked.expires_at - timezone.now()).total_seconds(),
                        seconds, delta=60)

            # 次のラウンドのために遮断を解いておく（期限切れの再現）
            BlockedIp.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
            BlockedIpMiddleware.forget_cache()

    def test_expired_block_lets_access_through(self):
        for _ in range(4):
            self.post()
        self.assertEqual(self.client.get(reverse('home:index')).status_code, 403)

        BlockedIp.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        BlockedIpMiddleware.forget_cache()

        self.assertEqual(self.client.get(reverse('home:index')).status_code, 200)
        # 行は残す（再犯したときに回数を引き継ぐため）
        self.assertEqual(BlockedIp.objects.count(), 1)

    def test_403_page_shows_contact_and_reason(self):
        for _ in range(4):
            self.post()

        response = self.client.get(reverse('home:index'))

        self.assertContains(response, 'contact@funitclub.org', status_code=403)
        self.assertContains(response, '心当たりがない場合', status_code=403)
        self.assertContains(response, '同じ回線を共有', status_code=403)
        # 遮断中は静的ファイルも 403 なので、外部 CSS を読ませない
        self.assertNotContains(response, '/static/', status_code=403)

    def test_blocked_ip_cannot_access_anything(self):
        for _ in range(4):
            self.post()

        for url in [reverse('home:index'), self.url, reverse('edit:login')]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_block_is_released_from_admin(self):
        for _ in range(4):
            self.post()
        self.assertEqual(self.client.get(reverse('home:index')).status_code, 403)

        BlockedIp.objects.all().delete()
        BlockedIpMiddleware.forget_cache()

        self.assertEqual(self.client.get(reverse('home:index')).status_code, 200)

    @override_settings(IP_BLOCK_EXEMPT=['127.0.0.1'])
    def test_exempt_ip_is_not_blocked_even_if_listed(self):
        BlockedIp.objects.create(ip='127.0.0.1', reason='手動')
        BlockedIpMiddleware.forget_cache()

        self.assertEqual(self.client.get(reverse('home:index')).status_code, 200)

    def test_site_stays_up_when_the_block_list_cannot_be_read(self):
        """遮断リストを読めなくてもサイトは開く（fail open）。"""
        BlockedIp.objects.create(ip='127.0.0.1', reason='手動')
        BlockedIpMiddleware.forget_cache()

        with mock.patch('config.middleware.cache.get', side_effect=RuntimeError('boom')):
            with self.assertLogs('config.middleware', level='ERROR'):
                response = self.client.get(reverse('home:index'))

        self.assertEqual(response.status_code, 200)

    def test_no_warning_within_the_limit(self):
        with self.assertNoLogs('home.views', level='WARNING'):
            for _ in range(3):
                self.post()

    def test_email_address_is_not_in_the_warning(self):
        with self.assertLogs('home.views', level='WARNING') as logs:
            for _ in range(4):
                self.post()

        self.assertNotIn('bu0000000000@bukkyo-u.ac.jp', '\n'.join(logs.output))

    def test_uses_the_rightmost_forwarded_ip(self):
        """X-Forwarded-For の左端は詐称できるので、右端（Azure が付けた値）を見る。

        左端を信じると、攻撃者が他人の IP を名乗って第三者を遮断させられる。
        """
        for _ in range(4):
            self.post(HTTP_X_FORWARDED_FOR='203.0.113.99, 198.51.100.5:41000')

        self.assertEqual([b.ip for b in BlockedIp.objects.all()], ['198.51.100.5'])

    def test_counter_resets_after_the_window(self):
        for _ in range(3):
            self.post()

        # 窓（600秒）を過ぎた時刻から数え直す
        with mock.patch('home.views.time.time', return_value=time.time() + 601):
            with self.assertNoLogs('home.views', level='WARNING'):
                self.post()

    def test_counted_per_ip(self):
        for _ in range(3):
            self.post(HTTP_X_FORWARDED_FOR='203.0.113.10:51000')

        # 別IPは別勘定なので警告は出ない
        with self.assertNoLogs('home.views', level='WARNING'):
            self.post(HTTP_X_FORWARDED_FOR='203.0.113.11:51000')

        # 同じIPで続けると遮断される
        with self.assertLogs('home.views', level='WARNING') as logs:
            self.post(HTTP_X_FORWARDED_FOR='203.0.113.10:51000')
        self.assertIn('IP=203.0.113.10', logs.output[0])
        self.assertEqual([b.ip for b in BlockedIp.objects.all()], ['203.0.113.10'])

    def test_survives_cache_failure(self):
        """キャッシュが使えなくても申し込みは通す。"""
        with mock.patch('home.views.cache.get', side_effect=RuntimeError('boom')):
            response = self.post()

        self.assertRedirects(response, self.url)
        self.assertEqual(len(mail.outbox), 2)
