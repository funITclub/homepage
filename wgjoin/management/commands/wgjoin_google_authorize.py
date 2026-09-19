# 運営が一度だけ流す。クラブの Classroom のクラスの先生のアカウントで「名簿を見る」を許可し、
# サイトが使うリフレッシュトークンを受け取る。
#
#   python manage.py wgjoin_google_authorize
#       … トークンを画面に出す（本番の Key Vault に入れるとき）
#   python manage.py wgjoin_google_authorize --client-json <ダウンロードした JSON> --save
#       … クライアント ID・シークレット・トークンを画面に出さずに .env に書く（手元で試すとき）
#
# 手元で流す（ブラウザが開く）。トークンは運営のアカウントの鍵なので、チャットや
# リポジトリに貼らないこと。運営が替わったとき・許可を取り消したときは、流し直して入れ替える。

import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from wgjoin import google
from wgjoin.http import ServiceError


def save_to_env(values, env_file=None):
    """.env の該当行を書き換える（なければ足す）。値は画面に出さない。"""
    env_file = Path(env_file or settings.BASE_DIR / '.env')
    lines = env_file.read_text(encoding='utf-8').splitlines() if env_file.exists() else []
    remaining = dict(values)
    for i, line in enumerate(lines):
        key = line.split('=', 1)[0].strip()
        if '=' in line and key in remaining:
            lines[i] = f'{key}={remaining.pop(key)}'
    lines += [f'{key}={value}' for key, value in remaining.items()]
    env_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    env_file.chmod(0o600)


class Command(BaseCommand):
    help = 'クラブのクラスの先生のアカウントで Classroom の名簿の読み取りを許可し、リフレッシュトークンを受け取る'

    def add_arguments(self, parser):
        parser.add_argument('--port', type=int, default=8765,
                            help='許可の結果を受け取る手元のポート（既定 8765）')
        parser.add_argument('--client-json',
                            help='Google Cloud でダウンロードした OAuth クライアント（デスクトップ アプリ）の JSON。'
                                 'ID とシークレットを .env に書いて使う')
        parser.add_argument('--save', action='store_true',
                            help='トークンを画面に出さず、.env の GOOGLE_OAUTH_REFRESH_TOKEN に書く')

    def handle(self, *args, port, client_json, save, **options):
        if client_json:
            self._use_client_json(client_json)
        if not (settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET):
            raise CommandError('GOOGLE_OAUTH_CLIENT_ID と GOOGLE_OAUTH_CLIENT_SECRET を先に設定するか、'
                               '--client-json を付けてください')

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
                self.wfile.write('受け取りました。このタブは閉じてかまいません。'.encode())

            def log_message(self, *args):
                pass

        server = HTTPServer(('127.0.0.1', port), Handler)
        url = google.authorize_url(state, challenge, redirect_uri)
        self.stdout.write('ブラウザで次の URL を開き、クラブのクラスの先生のアカウントで許可してください。\n')
        self.stdout.write(url + '\n')
        self.stdout.flush()
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

        if save:
            save_to_env({'GOOGLE_OAUTH_REFRESH_TOKEN': token})
            self.stdout.write('\n許可を受け取り、.env の GOOGLE_OAUTH_REFRESH_TOKEN に書きました。\n')
        else:
            self.stdout.write('\nGOOGLE_OAUTH_REFRESH_TOKEN に次の値を入れてください（本番は Key Vault）。\n')
            self.stdout.write(token + '\n')

    def _use_client_json(self, path):
        try:
            data = json.loads(Path(path).expanduser().read_text(encoding='utf-8'))
            client = data.get('installed') or data['web']
            client_id, client_secret = client['client_id'], client['client_secret']
        except (OSError, ValueError, KeyError) as e:
            raise CommandError(f'クライアントの JSON を読めませんでした: {path}') from e
        save_to_env({'GOOGLE_OAUTH_CLIENT_ID': client_id, 'GOOGLE_OAUTH_CLIENT_SECRET': client_secret})
        settings.GOOGLE_OAUTH_CLIENT_ID = client_id
        settings.GOOGLE_OAUTH_CLIENT_SECRET = client_secret
        self.stdout.write('クライアント ID とシークレットを .env に書きました。\n')
