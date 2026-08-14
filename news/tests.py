from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import News


class NewsQuerySetTests(TestCase):

    def test_published_excludes_draft_and_future(self):
        today = timezone.localdate()
        visible = News.objects.create(published_on=today, text='公開中')
        News.objects.create(published_on=today, text='下書き', is_published=False)
        News.objects.create(published_on=today + timedelta(days=1), text='予約投稿')

        self.assertQuerySetEqual(News.objects.published(), [visible])


class NewsEditorViewTests(TestCase):

    def setUp(self):
        User.objects.create_user('editor', password='funitclub-test-pass')
        self.client.force_login(User.objects.get(username='editor'))

    def test_create_then_show_on_index(self):
        response = self.client.post(reverse('edit:news:editor_create'), {
            'published_on': timezone.localdate().isoformat(),
            'text': 'テスト投稿',
            'badge': 'イベント',
            'is_published': 'on',
        })
        self.assertRedirects(response, reverse('edit:news:editor_list'))
        self.assertContains(self.client.get(reverse('home:index')), 'テスト投稿')

    def test_delete(self):
        news = News.objects.create(published_on=timezone.localdate(), text='消す')
        self.client.post(reverse('edit:news:editor_delete', args=[news.pk]))
        self.assertFalse(News.objects.filter(pk=news.pk).exists())
