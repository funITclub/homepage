# config/settings_dev.py — ローカル開発用

import os
import sys

from .settings_common import *

# ローカルの秘密情報（メールのアプリパスワードなど）は .env から読む。
# .env は .gitignore 済みで、リポジトリにも zip デプロイにも入らない。
# 既に環境変数がある場合はそちらを優先する（setdefault）。
_env_file = BASE_DIR / '.env'
if _env_file.exists():
    for _line in _env_file.read_text(encoding='utf-8').splitlines():
        _line = _line.strip()
        if not _line or _line.startswith('#') or '=' not in _line:
            continue
        _key, _value = _line.split('=', 1)
        os.environ.setdefault(_key.strip(), _value.strip().strip('\'"'))

SECRET_KEY = 'django-insecure-funitclub-local-development-key'

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
_extra_hosts = os.environ.get('EXTRA_ALLOWED_HOSTS', '').strip()
if _extra_hosts:
    ALLOWED_HOSTS += [h.strip() for h in _extra_hosts.split(',') if h.strip()]

CSRF_TRUSTED_ORIGINS = []
_csrf = os.environ.get('CSRF_TRUSTED_ORIGINS', '').strip()
if _csrf:
    CSRF_TRUSTED_ORIGINS += [o.strip() for o in _csrf.split(',') if o.strip()]

# DB は既定で SQLite（settings_common）。お知らせ（news アプリ）はここに保存される。
# 環境変数 DB_HOST が渡されたときだけ PostgreSQL に切り替える。
# ※ hirahira-db は公開アクセス無効（VNet 内からのみ）なので、手元から直接は繋がらない。
if os.environ.get('DB_HOST'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME'),
            'USER': os.environ.get('DB_USER'),
            'PASSWORD': os.environ.get('DB_PASSWORD'),
            'HOST': os.environ.get('DB_HOST'),
        }
    }

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'home': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'dev',
        },
    },
    'formatters': {
        'dev': {
            'format': '\t'.join([
                '%(asctime)s',
                '[%(levelname)s]',
                '%(pathname)s(Line:%(lineno)d)',
                '%(message)s',
            ])
        },
    },
}

# 送信メール。参加フォーム（/join/）の動作をローカルでも本番と同じ経路で確かめられるよう、
# 認証情報があれば実際に Azure Communication Services の SMTP で送る。
#
# 認証情報は .env に置くか、環境変数で渡す。
#   .env の例:
#     EMAIL_HOST_USER=no-reply@funitclub.org        # ACS の SMTP ユーザー名
#     EMAIL_HOST_PASSWORD=<Entra アプリのクライアント シークレット>
#
# ※ 実際に送るので、フォームに入れたアドレスと事務局アドレスに本物のメールが届く。
#    テストのつもりで他人のアドレスを入れないこと。
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.azurecomm.net')
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_TIMEOUT = 20
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')

if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    # 認証情報が無いときは送れないので、コンソールに出して確認する
    # （メール本文は runserver のログにそのまま出る）。
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    if 'runserver' in sys.argv:
        print('[dev] EMAIL_HOST_USER / EMAIL_HOST_PASSWORD が未設定のため、'
              'メールは送信せずコンソールに出力します（.env を参照）。')
