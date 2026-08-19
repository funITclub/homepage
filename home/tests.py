from django.core import mail
from django.test import TestCase
from django.urls import reverse

from catalog.models import Wg


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

        # 申込者あての控え
        self.assertEqual(auto_reply.to, ['bu0000000000@bukkyo-u.ac.jp'])
        self.assertIn('受け付けました', auto_reply.subject)

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

    def test_draft_wg_is_not_selectable(self):
        draft = Wg.objects.create(code='WG-99', name='下書きWG', description='説明',
                                  is_published=False)
        response = self.post(wg=draft.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotContains(response, '下書きWG')
