# 運営が一度だけ流す。クラブの Classroom のクラスの先生のアカウントで「名簿を見る」を許可し、
# サイトが使うリフレッシュトークンを受け取る。
#
#   python manage.py wgjoin_google_authorize
#
# 手元で流す（ブラウザが開く）。出てきたトークンは GOOGLE_OAUTH_REFRESH_TOKEN に入れる
# （本番は Key Vault）。運営のアカウントの鍵なので、チャットやリポジトリに貼らないこと。
# 運営が替わったとき・許可を取り消したときは、流し直して入れ替える。

import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from wgjoin import google
from wgjoin.http import ServiceError


class Command(BaseCommand):
    help = 'クラブのクラスの先生のアカウントで Classroom の名簿の読み取りを許可し、リフレッシュトークンを表示する'

    def add_arguments(self, parser):
        parser.add_argument('--port', type=int, default=8765,
                            help='許可の結果を受け取る手元のポート（既定 8765）')

    def handle(self, *args, port, **options):
        if not (settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET):
            raise CommandError('GOOGLE_OAUTH_CLIENT_ID と GOOGLE_OAUTH_CLIENT_SECRET を先に設定してください')

        redirect_uri = f'http://127.0.0.1:{port}/'
        state = secrets.token_urlsafe(24)
        verifier, challenge = google.new_pkce()
        received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = parse_qs(urlparse(self.path).query)
                if 'state' in query:
                    received.update({key: values[0] for key, values in query.items()})
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write('受け取りました。ターミナルに戻ってください。'.encode())

            def log_message(self, *args):
                pass

        server = HTTPServer(('127.0.0.1', port), Handler)
        url = google.authorize_url(state, challenge, redirect_uri)
        self.stdout.write('ブラウザで次の URL を開き、クラブのクラスの先生のアカウントで許可してください。\n')
        self.stdout.write(url + '\n')
        webbrowser.open(url)
        try:
            while not received:
                server.handle_request()
        finally:
            server.server_close()

        if not secrets.compare_digest(received.get('state', ''), state):
            raise CommandError('受け取った state が一致しません。もう一度流してください')
        if 'code' not in received:
            raise CommandError(f'許可されませんでした（{received.get("error", "")}）')
        try:
            token = google.exchange_for_refresh_token(received['code'], verifier, redirect_uri)
        except ServiceError as e:
            raise CommandError(str(e)) from e

        self.stdout.write('\nGOOGLE_OAUTH_REFRESH_TOKEN に次の値を入れてください（本番は Key Vault）。\n')
        self.stdout.write(token + '\n')
