import base64
import re
from datetime import timedelta

from django.conf import settings
from django.core import mail
from django.db import connection
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import notify
from .models import Board, CountEvent


class CountEventTests(TestCase):
    """日数の数え方（hirahira_room から移植したロジック）。"""

    def setUp(self):
        self.today = timezone.localdate()

    def test_upcoming_counts_down(self):
        event = CountEvent(name='発表会', date=self.today + timedelta(days=10))
        self.assertTrue(event.is_upcoming)
        self.assertEqual(event.count_days, 10)
        self.assertEqual(event.count_label, '残り')
        self.assertEqual(event.weeks_and_days, (1, 3))

    def test_past_counts_up(self):
        event = CountEvent(name='設立', date=self.today - timedelta(days=400))
        self.assertTrue(event.is_past)
        self.assertEqual(event.count_days, 400)
        self.assertEqual(event.count_label, '経過')
        self.assertEqual(event.years_passed, 1)

    def test_today(self):
        event = CountEvent(name='当日', date=self.today)
        self.assertTrue(event.is_today)
        self.assertEqual(event.count_days, 0)
        self.assertEqual(event.count_label, '当日')

    def test_years_passed_is_zero_for_future(self):
        self.assertEqual(
            CountEvent(name='未来', date=self.today + timedelta(days=400)).years_passed, 0)


class CountdownViewTests(TestCase):
    """ログイン不要の公開ボードとして動く。"""

    def test_all_pages_open_without_login(self):
        event = CountEvent.objects.create(name='部会', date=timezone.localdate())

        for url in [
            reverse('countdown:index'),
            reverse('countdown:enter'),
            reverse('countdown:event_list'),
            reverse('countdown:event_create'),
            reverse('countdown:event_update', args=[event.pk]),
            reverse('countdown:event_delete', args=[event.pk]),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_create_without_login(self):
        response = self.client.post(reverse('countdown:event_create'), {
            'name': 'テスト予定',
            'date': (timezone.localdate() + timedelta(days=3)).isoformat(),
            'memo': 'メモ',
        })
        self.assertRedirects(response, reverse('countdown:event_list'))
        self.assertContains(self.client.get(reverse('countdown:event_list')), 'テスト予定')

    def test_delete_without_login(self):
        event = CountEvent.objects.create(name='消す', date=timezone.localdate())
        self.client.post(reverse('countdown:event_delete', args=[event.pk]))
        self.assertFalse(CountEvent.objects.filter(pk=event.pk).exists())

    def test_list_splits_upcoming_and_past(self):
        today = timezone.localdate()
        CountEvent.objects.create(name='未来', date=today + timedelta(days=1))
        CountEvent.objects.create(name='過去', date=today - timedelta(days=1))
        CountEvent.objects.create(name='当日', date=today)

        context = self.client.get(reverse('countdown:event_list')).context
        self.assertEqual([e.name for e in context['upcoming_events']], ['当日', '未来'])
        self.assertEqual([e.name for e in context['past_events']], ['過去'])

    def test_does_not_link_to_public_site(self):
        """公開サイトとは相互にリンクしない。"""
        html = self.client.get(reverse('countdown:index')).content.decode()
        for name in ['home:index', 'home:wg_list', 'home:work_list', 'home:join']:
            with self.subTest(name=name):
                self.assertNotIn(f'href="{reverse(name)}"', html)


class BoardTests(TestCase):
    """ID ごとに分けて持つ。ID を使わない共有ボードとは混ざらない。"""

    def setUp(self):
        self.today = timezone.localdate()
        self.board = Board.objects.create(code='taro')
        self.mine = CountEvent.objects.create(board=self.board, name='自分の予定', date=self.today)
        self.shared = CountEvent.objects.create(name='共有の予定', date=self.today)

    def enter(self, code, action):
        return self.client.post(reverse('countdown:enter'), {'code': code, 'action': action})

    def test_create_id(self):
        response = self.enter('Hanako', 'create')
        self.assertRedirects(response, reverse('countdown:board_list', args=['hanako']))
        self.assertTrue(Board.objects.filter(code='hanako').exists())

    def test_create_rejects_taken_reserved_and_malformed(self):
        for code in ['taro', 'events', 'enter', 'notify', 'ab', '日本語']:
            with self.subTest(code=code):
                self.assertEqual(self.enter(code, 'create').status_code, 200)
        self.assertEqual(Board.objects.count(), 1)

    def test_enter_existing_id(self):
        self.assertRedirects(
            self.enter('TARO', 'enter'), reverse('countdown:board_list', args=['taro']))

    def test_enter_does_not_create(self):
        self.assertEqual(self.enter('typo', 'enter').status_code, 200)
        self.assertFalse(Board.objects.filter(code='typo').exists())

    def test_lists_are_separate(self):
        board = self.client.get(reverse('countdown:board_list', args=['taro']))
        self.assertContains(board, '自分の予定')
        self.assertNotContains(board, '共有の予定')

        shared = self.client.get(reverse('countdown:event_list'))
        self.assertContains(shared, '共有の予定')
        self.assertNotContains(shared, '自分の予定')

    def test_unknown_id_is_404(self):
        self.assertEqual(
            self.client.get(reverse('countdown:board_list', args=['nobody'])).status_code, 404)

    def test_create_event_goes_to_the_board(self):
        response = self.client.post(reverse('countdown:board_create', args=['taro']), {
            'name': '発表会', 'date': self.today.isoformat(), 'memo': '',
        })
        self.assertRedirects(response, reverse('countdown:board_list', args=['taro']))
        self.assertEqual(CountEvent.objects.get(name='発表会').board, self.board)

    def test_events_cannot_be_reached_from_another_board(self):
        """番号を言い当てても、ほかの ID や共有ボードからは編集・削除できない。"""
        Board.objects.create(code='jiro')
        for url in [
            reverse('countdown:event_update', args=[self.mine.pk]),
            reverse('countdown:event_delete', args=[self.mine.pk]),
            reverse('countdown:board_update', args=['jiro', self.mine.pk]),
            reverse('countdown:board_delete', args=['jiro', self.mine.pk]),
            reverse('countdown:board_update', args=['taro', self.shared.pk]),
            reverse('countdown:board_delete', args=['taro', self.shared.pk]),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(CountEvent.objects.count(), 2)

    def test_update_and_delete_on_own_board(self):
        url = reverse('countdown:board_update', args=['taro', self.mine.pk])
        response = self.client.post(url, {'name': '直した', 'date': self.today.isoformat()})
        self.assertRedirects(response, reverse('countdown:board_list', args=['taro']))
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.name, '直した')

        self.client.post(reverse('countdown:board_delete', args=['taro', self.mine.pk]))
        self.assertFalse(CountEvent.objects.filter(pk=self.mine.pk).exists())


class NotifyTests(TestCase):
    """メール通知。通知先は ID ごとに1つで、確認のメールを経たアドレスだけを持つ。"""

    ADDRESS = 'taro@example.com'

    def setUp(self):
        cache.clear()
        self.today = timezone.localdate()
        self.board = Board.objects.create(code='taro')
        self.mail_url = reverse('countdown:board_mail', args=['taro'])

    def event(self, name, days, notify=True, board='own'):
        return CountEvent.objects.create(
            board=self.board if board == 'own' else board, name=name,
            date=self.today + timedelta(days=days), notify=notify)

    def link_in_mail(self, index=-1):
        return re.search(r'http\S+/countdown/notify/\S+', mail.outbox[index].body).group(0)

    def register(self):
        self.client.post(self.mail_url, {'email': self.ADDRESS})
        self.client.post(self.link_in_mail())
        self.board.refresh_from_db()

    # ---- 通知先の登録 ----

    def test_address_is_saved_only_after_confirmation(self):
        response = self.client.post(self.mail_url, {'email': 'Taro@Example.com'})
        self.assertRedirects(response, self.mail_url)
        self.assertEqual(mail.outbox[0].to, [self.ADDRESS])
        self.board.refresh_from_db()
        self.assertEqual(self.board.notify_email, '')

        link = self.link_in_mail()
        # リンクにアドレスは入れない
        self.assertNotIn('taro@', link)
        # 登録する前に、解除はメールからしかできないことを伝える
        self.assertIn('メールのリンクからしか解除できません', mail.outbox[0].body)
        self.assertContains(self.client.get(self.mail_url), 'メールのリンクからしか解除できません')
        # 開いただけでは登録しない（メールの検査で自動的に開かれることがある）
        page = self.client.get(link)
        self.assertContains(page, '受け取る')
        self.assertContains(page, 'メールのリンクからしか解除できません')
        self.board.refresh_from_db()
        self.assertEqual(self.board.notify_email, '')

        self.assertRedirects(self.client.post(link), self.mail_url)
        self.board.refresh_from_db()
        self.assertEqual(self.board.notify_email, self.ADDRESS)
        # 同じリンクは二度使えない
        self.assertEqual(self.client.post(link).status_code, 400)

    def test_address_is_stored_encrypted(self):
        """DB にもキャッシュにも、アドレスをそのままの形では置かない。"""
        self.client.post(self.mail_url, {'email': self.ADDRESS})
        with connection.cursor() as cursor:
            cursor.execute('SELECT value FROM funitclub_cache')
            cached = [row[0] for row in cursor.fetchall()]
        self.assertTrue(cached)
        for value in cached:
            self.assertNotIn(b'taro@', base64.b64decode(value))

        self.client.post(self.link_in_mail())
        with connection.cursor() as cursor:
            cursor.execute('SELECT notify_email_enc FROM funitclub_countboard')
            stored = cursor.fetchone()[0]
        self.assertTrue(stored)
        self.assertNotIn('taro', stored)
        self.assertNotIn('example.com', stored)
        self.board.refresh_from_db()
        self.assertEqual(self.board.notify_email, self.ADDRESS)

    def test_address_survives_key_rotation_with_fallback(self):
        self.register()
        with override_settings(SECRET_KEY='new-key', SECRET_KEY_FALLBACKS=[settings.SECRET_KEY]):
            self.assertEqual(Board.objects.get(pk=self.board.pk).notify_email, self.ADDRESS)
        # 前の鍵を残さずに替えると読めない。未登録として扱い、送らない
        self.event('発表会', 1)
        mail.outbox.clear()
        with override_settings(SECRET_KEY='new-key'):
            self.assertEqual(Board.objects.get(pk=self.board.pk).notify_email, '')
            self.assertEqual(notify.send_daily(), 0)
        self.assertEqual(mail.outbox, [])

    def test_broken_link_is_rejected(self):
        url = reverse('countdown:notify_confirm', args=['broken'])
        self.assertEqual(self.client.get(url).status_code, 400)
        self.assertEqual(self.client.post(url).status_code, 400)

    def test_confirmation_mails_are_limited(self):
        with override_settings(COUNTDOWN_CONFIRM_SEND_LIMITS=((10, 3600), (2, 3600))):
            for _ in range(2):
                self.assertEqual(
                    self.client.post(self.mail_url, {'email': self.ADDRESS}).status_code, 302)
            self.assertEqual(
                self.client.post(self.mail_url, {'email': self.ADDRESS}).status_code, 429)
        self.assertEqual(len(mail.outbox), 2)

    def test_settings_page_says_the_address_is_encrypted(self):
        self.assertContains(self.client.get(self.mail_url), '暗号化して保存')

    def test_address_is_masked_on_screen(self):
        self.register()
        html = self.client.get(self.mail_url).content.decode()
        self.assertIn('t***@example.com', html)
        self.assertNotIn(self.ADDRESS, html)
        self.assertNotIn(
            self.ADDRESS, self.client.get(reverse('countdown:board_list', args=['taro'])).content.decode())

    def test_registered_address_cannot_be_changed_or_removed_on_screen(self):
        """ID を知っている人が、止めたり自分のアドレスに差し替えたりできない。"""
        self.register()
        mail.outbox.clear()

        html = self.client.get(self.mail_url).content.decode()
        self.assertNotIn('name="email"', html)

        self.assertEqual(
            self.client.post(self.mail_url, {'email': 'jiro@example.com'}).status_code, 409)
        self.client.post(self.mail_url, {'action': 'remove'})
        self.assertEqual(mail.outbox, [])
        self.board.refresh_from_db()
        self.assertEqual(self.board.notify_email, self.ADDRESS)

    def test_confirm_link_issued_before_registration_cannot_replace(self):
        self.client.post(self.mail_url, {'email': 'jiro@example.com'})
        jiro_link = self.link_in_mail()
        self.register()

        self.assertEqual(self.client.post(jiro_link).status_code, 400)
        self.board.refresh_from_db()
        self.assertEqual(self.board.notify_email, self.ADDRESS)

    def test_stop_mail_goes_to_the_registered_address(self):
        self.register()
        mail.outbox.clear()

        self.assertRedirects(self.client.post(self.mail_url, {'action': 'stop'}), self.mail_url)
        self.assertEqual(mail.outbox[0].to, [self.ADDRESS])
        # 送っただけでは解除されない
        self.board.refresh_from_db()
        self.assertEqual(self.board.notify_email, self.ADDRESS)

        self.client.post(self.link_in_mail())
        self.board.refresh_from_db()
        self.assertEqual(self.board.notify_email, '')
        # 解除したあとは、別のアドレスを登録できる
        self.assertEqual(
            self.client.post(self.mail_url, {'email': 'jiro@example.com'}).status_code, 302)

    def test_stop_mails_are_limited(self):
        self.register()
        with override_settings(COUNTDOWN_CONFIRM_SEND_LIMITS=((10, 3600), (1, 3600))):
            self.assertEqual(self.client.post(self.mail_url, {'action': 'stop'}).status_code, 429)

    def test_stop_without_address_sends_nothing(self):
        self.client.post(self.mail_url, {'action': 'stop'})
        self.assertEqual(mail.outbox, [])

    def test_shared_board_has_no_mail_settings(self):
        self.assertEqual(self.client.get('/countdown/events/mail/').status_code, 404)
        self.assertNotContains(self.client.get(reverse('countdown:event_create')), 'name="notify"')
        self.assertContains(
            self.client.get(reverse('countdown:board_create', args=['taro'])), 'name="notify"')

    def test_notify_flag_is_set_per_event(self):
        self.client.post(reverse('countdown:board_create', args=['taro']), {
            'name': '知らせる', 'date': self.today.isoformat(), 'notify': 'on'})
        self.client.post(reverse('countdown:board_create', args=['taro']), {
            'name': '知らせない', 'date': self.today.isoformat()})
        self.assertTrue(CountEvent.objects.get(name='知らせる').notify)
        self.assertFalse(CountEvent.objects.get(name='知らせない').notify)

    # ---- 毎日の送信 ----

    def test_daily_mail_gathers_marked_countdowns_only(self):
        self.register()
        mail.outbox.clear()
        self.event('発表会', 10)
        self.event('当日の予定', 0)
        self.event('印なし', 5, notify=False)
        self.event('過ぎた出来事', -3)
        self.event('共有ボードの予定', 4, board=None)

        self.assertEqual(notify.send_daily(), 1)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.ADDRESS])
        self.assertIn('発表会', message.body)
        self.assertIn('残り10日', message.body)
        self.assertIn('当日の予定', message.body)
        self.assertIn('本日', message.body)
        for name in ['印なし', '過ぎた出来事', '共有ボードの予定']:
            self.assertNotIn(name, message.body)
        self.assertIn('/countdown/taro/', message.body)

    def test_one_mail_a_day(self):
        self.register()
        mail.outbox.clear()
        self.event('発表会', 1)

        self.assertEqual(notify.send_daily(), 1)
        self.assertEqual(notify.send_daily(), 0)
        self.assertEqual(notify.send_daily(self.today + timedelta(days=1)), 1)
        # 当日を過ぎたら送らない
        self.assertEqual(notify.send_daily(self.today + timedelta(days=2)), 0)
        self.assertEqual(len(mail.outbox), 2)

    def test_nothing_is_sent_without_address_or_marked_events(self):
        self.event('アドレスなし', 3)
        self.assertEqual(notify.send_daily(), 0)

        self.register()
        mail.outbox.clear()
        CountEvent.objects.update(notify=False)
        self.assertEqual(notify.send_daily(), 0)
        self.assertEqual(mail.outbox, [])

    def test_stop_link_in_the_mail_clears_the_address(self):
        self.register()
        self.event('発表会', 1)
        notify.send_daily()
        link = self.link_in_mail()

        self.assertContains(self.client.get(link), '通知を止める')
        self.board.refresh_from_db()
        self.assertEqual(self.board.notify_email, self.ADDRESS)

        self.assertRedirects(self.client.post(link), self.mail_url)
        self.board.refresh_from_db()
        self.assertEqual(self.board.notify_email, '')
        # 止めたあとは、同じリンクは使えない
        self.assertEqual(self.client.get(link).status_code, 400)

    def test_stop_link_for_a_previous_address_does_not_work(self):
        self.register()
        token = notify.make_stop_token(self.board)
        self.board.set_notify_email('jiro@example.com')
        self.assertEqual(
            self.client.post(reverse('countdown:notify_stop', args=[token])).status_code, 400)

    # ---- 送信を起こす入口 ----

    def test_run_requires_the_token(self):
        self.register()
        mail.outbox.clear()
        self.event('発表会', 1)
        url = reverse('countdown:notify_run')

        # 合言葉が未設定なら、入口ごと閉じる
        self.assertEqual(self.client.post(url, headers={'authorization': 'Bearer '}).status_code, 404)
        with override_settings(COUNTDOWN_NOTIFY_TOKEN='secret'):
            self.assertEqual(self.client.post(url).status_code, 404)
            self.assertEqual(
                self.client.post(url, headers={'authorization': 'Bearer wrong'}).status_code, 404)
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(mail.outbox, [])

            response = self.client.post(url, headers={'authorization': 'Bearer secret'})
            self.assertEqual(response.json(), {'sent': 1})
        self.assertEqual(len(mail.outbox), 1)
