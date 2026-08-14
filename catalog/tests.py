from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Wg, Work


class PublishedQuerySetTests(TestCase):

    def test_published_excludes_draft(self):
        visible = Wg.objects.create(code='WG-01', name='公開中', description='説明')
        Wg.objects.create(code='WG-02', name='下書き', description='説明', is_published=False)
        self.assertQuerySetEqual(Wg.objects.published(), [visible])

        shown = Work.objects.create(category='Web App', title='公開中', description='説明')
        Work.objects.create(category='Web App', title='下書き', description='説明',
                            is_published=False)
        self.assertQuerySetEqual(Work.objects.published(), [shown])


class TopCountTests(TestCase):
    """TOP の活動サマリは公開中のWG（活動中）と成果物の件数に連動する。"""

    def test_counts_follow_published_records(self):
        Wg.objects.create(code='WG-01', name='活動中', description='説明')
        Wg.objects.create(code='WG-02', name='準備中', description='説明', status=Wg.IDLE)
        Wg.objects.create(code='WG-03', name='下書き', description='説明', is_published=False)
        Work.objects.create(category='Web App', title='成果物1', description='説明')
        Work.objects.create(category='Notebook', title='成果物2', description='説明')
        Work.objects.create(category='Notebook', title='下書き', description='説明',
                            is_published=False)

        context = self.client.get(reverse('home:index')).context
        self.assertEqual(context['active_wg_count'], 1)
        self.assertEqual(context['work_count'], 2)

    def test_zero_when_empty(self):
        context = self.client.get(reverse('home:index')).context
        self.assertEqual(context['active_wg_count'], 0)
        self.assertEqual(context['work_count'], 0)


class CatalogEditorTests(TestCase):

    def setUp(self):
        User.objects.create_user('editor', password='funitclub-test-pass')
        self.client.force_login(User.objects.get(username='editor'))

    def test_create_wg_then_show_on_public_page(self):
        response = self.client.post(reverse('edit:catalog:wg_create'), {
            'code': 'WG-09',
            'name': 'テストWG',
            'description': '説明文',
            'status': Wg.ACTIVE,
            'app_url': '',
            'link_label': '',
            'link_url': '',
            'sort_order': 0,
            'is_published': 'on',
        })
        self.assertRedirects(response, reverse('edit:catalog:wg_list'))

        page = self.client.get(reverse('home:wg_list'))
        self.assertContains(page, 'テストWG')
        self.assertContains(page, 'WG-09')

    def test_draft_wg_is_hidden_from_public_page(self):
        self.client.post(reverse('edit:catalog:wg_create'), {
            'code': 'WG-10',
            'name': '下書きWG',
            'description': '説明文',
            'status': Wg.ACTIVE,
            'sort_order': 0,
        })
        self.assertNotContains(self.client.get(reverse('home:wg_list')), '下書きWG')

    def test_create_work_then_show_on_public_page(self):
        response = self.client.post(reverse('edit:catalog:work_create'), {
            'category': 'Web App',
            'title': 'テスト成果物',
            'description': '説明文',
            'license': 'MIT',
            'url': 'https://example.com/',
            'sort_order': 0,
            'is_published': 'on',
        })
        self.assertRedirects(response, reverse('edit:catalog:work_list'))

        page = self.client.get(reverse('home:work_list'))
        self.assertContains(page, 'テスト成果物')
        self.assertContains(page, 'https://example.com/')

    def test_delete(self):
        wg = Wg.objects.create(code='WG-11', name='消すWG', description='説明')
        work = Work.objects.create(category='Notebook', title='消す成果物', description='説明')

        self.client.post(reverse('edit:catalog:wg_delete', args=[wg.pk]))
        self.client.post(reverse('edit:catalog:work_delete', args=[work.pk]))

        self.assertFalse(Wg.objects.filter(pk=wg.pk).exists())
        self.assertFalse(Work.objects.filter(pk=work.pk).exists())
