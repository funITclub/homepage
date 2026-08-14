# config/settings_dev.py — ローカル開発用

import os

from .settings_common import *

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

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
