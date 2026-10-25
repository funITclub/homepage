import time
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django import forms
from django.conf import settings
from django.core import mail
from django.templatetags.static import static
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from catalog.models import Wg, Work
from config.middleware import BlockedIpMiddleware
from edit.models import Administrator
from news.models import News

from wgjoin import google

from .models import BlockedIp

# 手元の .env に Google の設定が入っていても、テストでは本物のクラスに招待しない（Chat にも追加しない）
NO_INVITE = dict(CLUB_CLASSROOM_COURSE='', CLUB_CHAT_SPACE='')
INVITE = dict(
    CLUB_CLASSROOM_COURSE='987654321098', CLUB_CHAT_SPACE='', GOOGLE_OAUTH_CLIENT_ID='google-client',
    GOOGLE_OAUTH_CLIENT_SECRET='google-secret', GOOGLE_OAUTH_REFRESH_TOKEN='staff-refresh')
CLUB_CHAT = dict(INVITE, CLUB_CHAT_SPACE='https://chat.google.com/room/AAQAjW7PaRU?cls=7')


@override_settings(**NO_INVITE)
class JoinFormTests(TestCase):
    """参加フォーム（/join/）。佛教大学のアドレスからだけ受け付ける。"""

    def setUp(self):
        self.url = reverse('home:join_apply')
        self.done_url = reverse('home:join_apply_done')

    def post(self, **overrides):
        data = {
            'email': 'bu0000000000@bukkyo-u.ac.jp',
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_page_opens_without_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '大学のメールアドレス')

    @override_settings(JOIN_NOTIFY_EMAIL='staff-inbox@example.com')
    def test_public_pages_show_the_role_address_only(self):
        """公開ページに出すのは役割アドレスだけ。通知先の受信箱は出さない。

        通知先には個人の大学アカウント（学籍番号を含む）を設定するため、
        公開ページに出ると恒久的に晒される。
        """
        Administrator.objects.create(email='staff-inbox@example.com',
                                     is_public_contact=False, sort_order=5)

        for url in [reverse('home:index'), reverse('home:join'), self.url, self.done_url]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, settings.PUBLIC_CONTACT_EMAIL)
                self.assertNotContains(response, 'staff-inbox@example.com')

    def test_guide_page_invites_contact(self):
        """問い合わせの案内は案内ページに置く（フォームのページには置かない）。"""
        guide = self.client.get(reverse('home:join'))
        self.assertContains(guide, 'ご質問は')
        self.assertContains(guide, 'mailto:contact@funitclub.org')

        apply_page = self.client.get(self.url)
        self.assertNotContains(apply_page, 'ご質問は')

    def test_apply_page_states_how_the_input_is_handled(self):
        """個人情報の扱いとアクセス制限の方針を掲示する（具体的な閾値は書かない）。"""
        response = self.client.get(self.url)

        self.assertContains(response, 'データベースに保存せず')
        self.assertContains(response, 'アクセスを一時的に制限')
        self.assertContains(response, '共有の回線')
        # 閾値を書くとギリギリを狙われるので出さない
        self.assertNotContains(response, '10分')

    def test_guide_page_offers_a_contact_for_non_students(self):
        """フォームを使えない人（大学のアドレスが無い人）の連絡先を案内する。"""
        response = self.client.get(reverse('home:join'))

        self.assertContains(response, 'お問い合わせ')
        self.assertContains(response, '大学のメールアドレスをお持ちの方が対象')
        self.assertContains(response, 'contact@funitclub.org')

    def test_guide_page_explains_the_tools(self):
        """活動ツールは Classroom を起点に説明する。"""
        response = self.client.get(reverse('home:join'))

        self.assertContains(response, 'Google Classroom')
        self.assertContains(response, 'GitHub だけは別途登録')

    def test_guide_page_has_no_form_and_links_to_it(self):
        """案内（/join/）とフォーム（/join/apply/）は別ページ。"""
        response = self.client.get(reverse('home:join'))

        self.assertNotContains(response, '<form')
        self.assertContains(response, f'href="{self.url}"')

    def test_valid_post_sends_two_mails_and_redirects_to_done_page(self):
        response = self.post()
        self.assertRedirects(response, self.done_url)

        self.assertEqual(len(mail.outbox), 2)
        notification, auto_reply = mail.outbox

        # 差出人は funitclub.org。大学アカウントでは SMTP 送信できないため、
        # 送信は独自ドメイン、返信だけ大学アドレスに向ける。
        self.assertEqual(notification.from_email, 'fun IT club <no-reply@funitclub.org>')
        self.assertEqual(auto_reply.from_email, 'fun IT club <no-reply@funitclub.org>')

        # 事務局あて。返信するとそのまま申込者に届く。
        self.assertEqual(notification.to, [settings.JOIN_NOTIFY_EMAIL])
        self.assertEqual(notification.reply_to, ['bu0000000000@bukkyo-u.ac.jp'])
        self.assertIn('bu0000000000@bukkyo-u.ac.jp', notification.body)

        # 申込者あての控え。第三者にも届きうるので、心当たりがない場合の案内を必ず入れる。
        self.assertEqual(auto_reply.to, ['bu0000000000@bukkyo-u.ac.jp'])
        self.assertIn('受け付けました', auto_reply.subject)
        self.assertIn('心当たりがない場合', auto_reply.body)
        # いつまで待てばいいか分からないと、待てない人が再送に向かう
        self.assertIn('7日以内', auto_reply.body)
        # 申込者に見えるのは役割アドレスだけ
        self.assertIn(settings.PUBLIC_CONTACT_EMAIL, auto_reply.body)

    def test_done_page_opens_without_login(self):
        response = self.client.get(self.done_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '受け付けました')

    def test_done_page_has_no_form_and_no_way_back_to_it(self):
        """完了ページから再送できないようにする。

        送れたか分からず押し直した人が連続送信とみなされ、IP ごと遮断されるのを
        防ぐためのページなので、フォームも申し込みページへのリンクも置かない。
        """
        response = self.client.get(self.done_url)

        self.assertNotContains(response, '<form')
        self.assertNotContains(response, f'href="{self.url}"')

    def test_done_page_states_the_reply_window(self):
        """いつまで待てばいいかを画面にも書く（自動返信が届かない場合の受け皿）。"""
        response = self.client.get(self.done_url)

        self.assertContains(response, '7日以内')
        self.assertContains(response, '迷惑メール')

    def test_form_has_no_free_text_field(self):
        """自由記述は持たせない。

        入力されたアドレスの持ち主を確認していないため、自由記述があると
        第三者あての自動返信に任意の文章を載せられてしまう（踏み台化）。
        項目を足すときはこの制約を壊していないか確認すること。
        """
        form = self.client.get(self.url).context['form']

        self.assertEqual(list(form.fields), ['email'])
        for name, field in form.fields.items():
            with self.subTest(field=name):
                self.assertNotIsInstance(field.widget, forms.Textarea)

    def test_extra_post_data_is_ignored(self):
        """フォームに無い項目を POST されても、メール本文には入らない。"""
        self.client.post(self.url, {
            'email': 'bu0000000000@bukkyo-u.ac.jp',
            'name': 'https://example.com/phishing',
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

    def test_email_is_not_written_to_log(self):
        """申込者のメールアドレスをログに残さない。"""
        with self.assertLogs('home.views', level='INFO') as logs:
            self.post()

        self.assertNotIn('bu0000000000@bukkyo-u.ac.jp', '\n'.join(logs.output))


@override_settings(**INVITE)
class ClassroomInviteTests(TestCase):
    """申し込みの時点で、運営の権限でクラブの Classroom のクラスに招待する。"""

    EMAIL = 'bu0000000000@bukkyo-u.ac.jp'

    def setUp(self):
        cache.clear()
        self.url = reverse('home:join_apply')

    def post(self, **invite):
        with mock.patch.object(google, 'invite_to_club', **invite) as invite_mock:
            response = self.client.post(self.url, {'email': self.EMAIL})
        self.assertRedirects(response, reverse('home:join_apply_done'))
        return invite_mock

    def test_invites_to_the_club_class(self):
        with self.assertLogs('home', level='INFO') as logs:
            invite = self.post(return_value=google.INVITED)
        invite.assert_called_once_with(self.EMAIL, '987654321098')
        # 招待できたらサイトからは何も送らない。事務局にも知らせない（会の運営に介入しない）。
        # 申請者には Google の招待メール（クラスの「参加」ボタン付き）だけが届く
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotIn('bu0000000000', '\n'.join(logs.output))

    def test_someone_already_in_the_class_is_told_so(self):
        self.post(return_value=google.MEMBER)
        [auto_reply] = mail.outbox
        self.assertIn('すでに', auto_reply.body)
        self.assertIn('https://classroom.google.com/c/OTg3NjU0MzIxMDk4', auto_reply.body)
        self.assertIn('WG に参加', auto_reply.body)

    def test_failure_still_accepts_and_falls_back_to_the_staff(self):
        from wgjoin.http import ServiceError
        with self.assertLogs('home', level='ERROR') as logs:
            self.post(side_effect=ServiceError('403'))
        # 手作業が要るので、このときだけ事務局に知らせる
        notification, auto_reply = mail.outbox
        self.assertEqual(notification.to, [settings.JOIN_NOTIFY_EMAIL])
        self.assertIn('手作業で招待してください', notification.body)
        self.assertIn('7日以内', auto_reply.body)
        self.assertIn('招待できませんでした', '\n'.join(logs.output))
        self.assertNotIn('bu0000000000', '\n'.join(logs.output))

    def test_pages_say_the_address_is_used_for_the_invitation(self):
        self.assertContains(self.client.get(self.url), 'クラスへの招待を送るために使います')
        done = self.client.get(reverse('home:join_apply_done'))
        self.assertContains(done, 'クラブのクラスへの招待</strong>が届きます')
        self.assertContains(done, '7日以内')
        self.assertContains(done, '迷惑メール')
        # 画面にはクラスのリンクを出さない
        self.assertNotContains(done, 'classroom.google.com')
        self.assertNotContains(done, '控えのメールをお送りしました')

    def test_no_invitation_without_the_settings(self):
        with self.settings(**NO_INVITE):
            invite = self.post()
            invite.assert_not_called()
            self.assertIn('自動の招待は使っていません', mail.outbox[0].body)
            self.assertNotContains(self.client.get(self.url), 'クラスへの招待を送るために使います')


@override_settings(**CLUB_CHAT)
class ClubChatTests(TestCase):
    """申し込みの時点で、運営の権限でクラブのお知らせの Chat スペースに追加する。"""

    EMAIL = 'bu0000000000@bukkyo-u.ac.jp'

    def setUp(self):
        cache.clear()
        self.url = reverse('home:join_apply')

    def post(self, invite=google.INVITED, **chat):
        with mock.patch.object(google, 'invite_to_club', return_value=invite), \
                mock.patch.object(google, 'add_to_chat_space', **chat) as chat_mock:
            response = self.client.post(self.url, {'email': self.EMAIL})
        self.assertRedirects(response, reverse('home:join_apply_done'))
        return chat_mock

    def test_adds_the_applicant_to_the_club_space(self):
        with self.assertLogs('home', level='INFO') as logs:
            chat = self.post()
        # URL で設定しても spaces/<ID> にして渡す
        chat.assert_called_once_with('spaces/AAQAjW7PaRU', self.EMAIL)
        # 追加できたら何も送らない（招待できたときと同じ）
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn('Chat スペースに追加しました', '\n'.join(logs.output))
        self.assertNotIn('bu0000000000', '\n'.join(logs.output))

    def test_someone_already_in_the_class_is_added_too(self):
        chat = self.post(invite=google.MEMBER)
        chat.assert_called_once()
        [auto_reply] = mail.outbox
        self.assertIn('すでに', auto_reply.body)

    def test_failure_tells_only_the_staff(self):
        from wgjoin.http import ServiceError
        with self.assertLogs('home', level='ERROR') as logs:
            self.post(side_effect=ServiceError('403'))
        # 招待はできているので、申込者には送らない。手作業が要るので事務局にだけ知らせる
        [notification] = mail.outbox
        self.assertEqual(notification.to, [settings.JOIN_NOTIFY_EMAIL])
        self.assertIn(self.EMAIL, notification.body)
        self.assertIn('Chat スペースに追加できませんでした', notification.body)
        self.assertNotIn('Classroom', notification.body)
        self.assertIn('追加できませんでした', '\n'.join(logs.output))
        self.assertNotIn('bu0000000000', '\n'.join(logs.output))

    def test_both_failures_go_into_one_notification(self):
        from wgjoin.http import ServiceError
        with self.assertLogs('home', level='ERROR'):
            self.post(invite='failed', side_effect=ServiceError('403'))
        notification, auto_reply = mail.outbox
        self.assertIn('手作業で招待してください', notification.body)
        self.assertIn('手作業で追加してください', notification.body)
        self.assertIn('7日以内', auto_reply.body)

    def test_pages_say_the_address_is_added_to_the_space(self):
        self.assertContains(self.client.get(self.url), 'お知らせの Google Chat')
        self.assertContains(self.client.get(reverse('home:join_apply_done')), 'お知らせの Chat を確認する')

    def test_done_page_recommends_apps_and_notifications(self):
        """連絡はほぼ Classroom と Chat だけなので、アプリと通知の設定を勧める。"""
        done = self.client.get(reverse('home:join_apply_done'))
        self.assertContains(done, 'お知らせを見逃さないために')
        self.assertContains(done, '「Google Classroom」と「Google Chat」のアプリ')
        # 私用のアカウントでは見えないので、大学のアカウントでと明示する
        self.assertContains(done, '大学のアカウントでログインする')
        self.assertContains(done, 'Chat のお知らせのスペースの通知')
        # 招待を使っていなくても（手作業で案内する人にも）出す。Chat の通知はスペースがあるときだけ
        with self.settings(**NO_INVITE):
            done = self.client.get(reverse('home:join_apply_done'))
            self.assertContains(done, 'お知らせを見逃さないために')
            self.assertNotContains(done, 'Chat のお知らせのスペースの通知')

    def test_not_added_without_the_space(self):
        with self.settings(CLUB_CHAT_SPACE=''):
            chat = self.post()
            chat.assert_not_called()
            self.assertNotContains(self.client.get(self.url), 'お知らせの Google Chat')
            self.assertNotContains(self.client.get(reverse('home:join_apply_done')), 'お知らせの Chat')


@override_settings(**NO_INVITE)
@override_settings(JOIN_BURST_RULES=[(3, 600)])
class BurstDetectionTests(TestCase):
    """連続送信の検知と遮断。"""

    def setUp(self):
        cache.clear()
        self.url = reverse('home:join_apply')

    def post(self, **extra):
        return self.client.post(self.url, {
            'email': 'bu0000000000@bukkyo-u.ac.jp',
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

        self.assertContains(response, settings.PUBLIC_CONTACT_EMAIL, status_code=403)
        self.assertContains(response, '心当たりがない場合', status_code=403)
        self.assertContains(response, '同じ回線を共有', status_code=403)
        # 遮断中は静的ファイルも 403 なので、外部 CSS を読ませない
        self.assertNotContains(response, '/static/', status_code=403)

    def test_admin_is_notified(self):
        for _ in range(4):
            self.post()

        notice, = [m for m in mail.outbox if 'IP を遮断しました' in m.subject]
        self.assertEqual(notice.to, [settings.JOIN_NOTIFY_EMAIL])
        self.assertIn('127.0.0.1', notice.body)
        self.assertIn('1回目', notice.body)
        self.assertIn('巻き添え', notice.body)
        self.assertIn('IP_BLOCK_EXEMPT', notice.body)

    @override_settings(IP_BLOCK_NOTIFY_MAX_PER_HOUR=1)
    def test_notification_is_capped_per_hour(self):
        """IP を変えながら攻撃されても通知で溢れさせない。"""
        for i in range(3):
            for _ in range(4):
                self.post(HTTP_X_FORWARDED_FOR=f'203.0.113.{i}:40000')

        self.assertEqual(BlockedIp.objects.count(), 3)
        notices = [m for m in mail.outbox if 'IP を遮断しました' in m.subject]
        self.assertEqual(len(notices), 1)

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

        self.assertRedirects(response, reverse('home:join_apply_done'))
        self.assertEqual(len(mail.outbox), 2)


class NewsListTests(TestCase):
    """お知らせ一覧（/news/）。TOP の「すべて見る」の行き先。"""

    def setUp(self):
        self.url = reverse('home:news_list')
        today = timezone.localdate()
        self.published = [
            News.objects.create(published_on=today - timedelta(days=i), text=f'お知らせ{i}')
            for i in range(6)
        ]
        self.draft = News.objects.create(text='下書き', is_published=False)
        self.scheduled = News.objects.create(
            published_on=today + timedelta(days=1), text='掲載日が未来')

    def test_top_links_to_the_list(self):
        """TOP の「すべて見る」は「作成中」ではなく一覧に行く。"""
        response = self.client.get(reverse('home:index'))

        self.assertContains(response, f'href="{self.url}"')
        self.assertNotContains(response, reverse('home:coming_soon'))

    def test_shows_all_published_news(self):
        """TOP は5件までだが、一覧は公開中を全件出す。"""
        response = self.client.get(self.url)

        self.assertEqual(list(response.context['news_list']), self.published)
        self.assertContains(response, 'お知らせ5')

    def test_hides_drafts_and_future_news(self):
        response = self.client.get(self.url)

        self.assertNotContains(response, '下書き')
        self.assertNotContains(response, '掲載日が未来')

    def test_opens_without_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_says_so_when_empty(self):
        News.objects.all().delete()

        self.assertContains(self.client.get(self.url), 'お知らせはまだありません。')


class ComingSoonTests(TestCase):
    """「作成中」ページ（/coming-soon/）。一覧から別タブで開かれ、閉じて戻る。"""

    def setUp(self):
        self.url = reverse('home:coming_soon')

    def test_message_for_list_it_came_from(self):
        """WGのWebアプリと成果物とで説明文を分ける。"""
        for value, message, nav in [('wg', 'このWGのWebアプリは準備中です。', 'wg'),
                                    ('works', 'この成果物のページは準備中です。', 'works')]:
            with self.subTest(value=value):
                response = self.client.get(self.url, {'from': value})

                self.assertContains(response, message)
                self.assertEqual(response.context['nav'], nav)

    def test_neutral_message_by_default(self):
        """直接開かれたときや想定外の値のときは、どちらでもない文にする。"""
        for params in [{}, {'from': 'https://example.com'}, {'from': 'news'}]:
            with self.subTest(params=params):
                response = self.client.get(self.url, params)

                self.assertContains(response, 'リンク先のページは準備中です。')
                self.assertEqual(response.context['nav'], '')

    def test_close_button_instead_of_back_link(self):
        response = self.client.get(self.url, {'from': 'wg'})

        self.assertContains(response, 'このタブを閉じる')
        self.assertNotContains(response, '戻る')


class ExternalLinkTests(TestCase):
    """一覧カードのリンク。外部サイトも「作成中」も別タブ。"""

    def test_wg_links(self):
        Wg.objects.create(code='WG-01', name='外部あり', description='説明',
                          app_url='https://example.com/app',
                          link_label='GitHub', link_url='https://example.com/repo')
        Wg.objects.create(code='WG-02', name='外部なし', description='説明')

        html = self.client.get(reverse('home:wg_list')).content.decode()

        self.assertIn('href="https://example.com/app" target="_blank" rel="noopener noreferrer"', html)
        self.assertIn('href="https://example.com/repo" target="_blank" rel="noopener noreferrer"', html)
        self.assertIn('?from=wg" target="_blank" rel="noopener noreferrer"', html)

    def test_work_link(self):
        Work.objects.create(category='Web App', title='外部あり', description='説明',
                            url='https://example.com/work')
        Work.objects.create(category='Notebook', title='外部なし', description='説明')

        html = self.client.get(reverse('home:work_list')).content.decode()

        self.assertIn('href="https://example.com/work" target="_blank" rel="noopener noreferrer"', html)
        self.assertIn('?from=works" target="_blank" rel="noopener noreferrer"', html)


class GuideTests(TestCase):
    """WG 立ち上げガイド（/guide/）。参加の完了画面とメールからの案内先。"""

    def setUp(self):
        self.url = reverse('home:guide')

    def test_opens_without_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_links_to_every_document(self):
        response = self.client.get(self.url)
        for name in ['00_概要', '01_リポジトリの作り方と運用',
                     '02_パソコンの準備', '03_開発の進め方',
                     '04_アプリケーション構成']:
            with self.subTest(name=name):
                self.assertContains(response, static(f'guide/{name}.pptx'))

    def test_documents_are_saved_under_their_own_names(self):
        """本番では URL にハッシュが入るので、保存名を download で指定しておく。"""
        response = self.client.get(self.url)
        for name in ['00_概要', '01_リポジトリの作り方と運用',
                     '02_パソコンの準備', '03_開発の進め方',
                     '04_アプリケーション構成']:
            with self.subTest(name=name):
                self.assertContains(response, f'download="{name}.pptx"')

    def test_documents_are_in_place(self):
        """テンプレートのリンク先が実際にあること（資料を移動したら気づけるように）。"""
        for path in settings.STATICFILES_DIRS:
            for name in ['00_概要', '01_リポジトリの作り方と運用',
                         '02_パソコンの準備', '03_開発の進め方',
                         '04_アプリケーション構成']:
                with self.subTest(name=name):
                    self.assertTrue((Path(path) / 'guide' / f'{name}.pptx').exists())

    def test_not_in_the_nav(self):
        """メンバー向けのページなので、初めて来た人に見せるナビには出さない。"""
        self.assertNotContains(self.client.get(reverse('home:index')), self.url)


@override_settings(SITE_URL='https://funitclub.org', ALLOWED_HOSTS=['*'])
class SearchEngineTests(TestCase):
    """Google などに載せるための robots.txt・サイトマップ・canonical。"""

    def test_robots_txt_hides_private_paths_and_points_to_sitemap(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        body = response.content.decode()
        for path in ['/edit/', '/admin/', '/join/apply/', '/wg/*/join/']:
            self.assertIn(f'Disallow: {path}\n', body)
        for prefix in settings.GATE_BACK:
            self.assertIn(f'Disallow: {prefix}\n', body)
        # WG一覧そのものは巡回させる
        self.assertNotIn('Disallow: /wg/\n', body)
        self.assertIn('Sitemap: https://funitclub.org/sitemap.xml', body)

    def test_sitemap_lists_public_pages(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for path in ['/', '/news/', '/wg/', '/works/', '/join/']:
            self.assertIn(f'<loc>https://funitclub.org{path}</loc>', body)
        self.assertNotIn('/edit/', body)

    def test_canonical_uses_site_url_whatever_host(self):
        response = self.client.get('/wg/', HTTP_HOST='funitclub.azurewebsites.net')
        self.assertContains(response, '<link rel="canonical" href="https://funitclub.org/wg/">')

    def test_placeholder_pages_are_noindex(self):
        self.assertContains(self.client.get(reverse('home:coming_soon')),
                            '<meta name="robots" content="noindex">')
        self.assertNotContains(self.client.get(reverse('home:index')), 'name="robots"')
