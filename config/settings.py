# config/settings.py — 本番（Azure App Service）用

import os

from .settings_common import *

# 既定は False。切り分けが必要なときだけ App Service のアプリケーション設定に
# DEBUG=True を足して一時的に有効化し、済んだら必ず戻す（hirahira-room と同じ運用）。
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# WhiteNoise で静的ファイルを配信する
INSTALLED_APPS.insert(0, 'whitenoise.runserver_nostatic')
idx = MIDDLEWARE.index('django.middleware.security.SecurityMiddleware')
MIDDLEWARE.insert(idx + 1, 'whitenoise.middleware.WhiteNoiseMiddleware')

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

ALLOWED_HOSTS = ['*']
CSRF_TRUSTED_ORIGINS = []

# Azure App Service 用の設定
if 'WEBSITE_HOSTNAME' in os.environ:
    _origin = f"https://{os.environ['WEBSITE_HOSTNAME']}"
    if _origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_origin)

# Azure はフロントで HTTPS を終端し X-Forwarded-Proto で転送する
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# 編集画面のログインセッションを HTTPS 限定にする
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# DB。PostgreSQL サーバーは hirahira_room と同じものを使うが、
# データベースは funITclub 専用のものを分けて用意する（DB_NAME で指定）。
# hirahira_room の共有DBには触らないので、こちらは自由に migrate してよい。
# 接続情報はリポジトリに持たず、すべて App Service のアプリケーション設定から読む。
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
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}
