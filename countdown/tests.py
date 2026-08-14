from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CountEvent


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
