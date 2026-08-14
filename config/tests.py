from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from .middleware import CanonicalHostMiddleware


def dummy_response(request):
    return HttpResponse('ok')


@override_settings(CANONICAL_HOST='funitclub.org', ALLOWED_HOSTS=['*'])
class CanonicalHostMiddlewareTests(TestCase):
    """www 付きのアクセスを apex へ 301 で寄せる。"""

    def setUp(self):
        self.middleware = CanonicalHostMiddleware(dummy_response)
        self.factory = RequestFactory()

    def test_www_redirects_to_apex_keeping_path_and_query(self):
        request = self.factory.get('/wg/?q=1', headers={'host': 'www.funitclub.org'})
        response = self.middleware(request)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'http://funitclub.org/wg/?q=1')

    def test_apex_passes_through(self):
        request = self.factory.get('/wg/', headers={'host': 'funitclub.org'})
        self.assertEqual(self.middleware(request).status_code, 200)

    def test_azure_default_hostname_passes_through(self):
        request = self.factory.get(
            '/', headers={'host': 'funitclub-bhfefqgjgyeua0hj.japanwest-01.azurewebsites.net'})
        self.assertEqual(self.middleware(request).status_code, 200)


class CanonicalHostDisabledTests(TestCase):
    """CANONICAL_HOST が無い開発環境では、そもそも組み込まれない。"""

    @override_settings(CANONICAL_HOST='')
    def test_not_used_without_canonical_host(self):
        with self.assertRaises(MiddlewareNotUsed):
            CanonicalHostMiddleware(dummy_response)
