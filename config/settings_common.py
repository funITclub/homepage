# config/settings_common.py

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-me-in-production')
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    # Django 本体
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Bootstrap 5（hirahira_room と同じ構成。フォームのレンダリング用タグを使う）
    'django_bootstrap5',

    # 自作アプリ
    'home',        # 公開サイト
    'news',        # お知らせ
    'catalog',     # WG紹介・成果物紹介
    'edit',        # 編集画面（ログイン・メニュー・共通レイアウト）
    'countdown',   # サブアプリ「カウントアップ＆ダウン」（ログイン不要の公開ボード）
]

MIDDLEWARE = [
    # 遮断リストの IP を最初に弾く。静的ファイルも含めて何も返さないよう先頭に置く。
    'config.middleware.BlockedIpMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # 既定で全ビューをログイン必須にする。公開ページ側に
    # django.contrib.auth.decorators.login_not_required を付けて除外する
    # （編集画面に画面を足したときの付け忘れを防ぐため）。
    'django.contrib.auth.middleware.LoginRequiredMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# 本サイトは静的ページのみでモデルを持たず、DB を参照しない。
# Django が DATABASES を要求するため、ローカル用に SQLite を既定にしておく
# （本番は settings.py 側で hirahira_db に上書き）。
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# キャッシュ。参加フォームの連続送信を数えるのに使う。
# ローカルメモリだと worker ごとに別勘定になり、再起動でも消えて検知漏れするため、
# DB に置いて全プロセスで共有する。テーブルは初回に createcachetable で作る
# （テーブル名は他と同じく funitclub_ 接頭辞で固定）。
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'funitclub_cache',
    }
}

# 認証は編集画面（/edit/）専用。
# 一般向けの会員登録は無く、アカウントは manage.py createsuperuser で作る。
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# 編集画面は公開サイトと行き来しないので、ログアウト後もログイン画面に戻す。
LOGIN_URL = 'edit:login'
LOGIN_REDIRECT_URL = 'edit:index'
LOGOUT_REDIRECT_URL = 'edit:login'

LANGUAGE_CODE = 'ja'
TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# サイト共通の表示情報（テンプレートから参照）
SITE_NAME = 'fun IT club'
SITE_TAGLINE = '佛教大学 通信教育課程 課外活動団体'

# 参加フォーム（/join/）
# 申し込みは大学から発行されたメールアドレスからのみ受け付ける。活動ツールが
# 大学の Google Workspace 前提なので、私用アドレスでは先に進めないため。
JOIN_ALLOWED_EMAIL_DOMAIN = 'bukkyo-u.ac.jp'

# 申し込みの通知先。大学アカウントで受け取る（受信は制限されていない）。
JOIN_NOTIFY_EMAIL = os.getenv('JOIN_NOTIFY_EMAIL', 'contact@funitclub.org')

# 参加フォームの連続送信とみなす条件。(件数, 秒) を超えた IP を遮断する。
# 同一IPからの申し込みを数える。問い合わせフォームとして一般的な水準にしてある
# （通常の申込者は1回送れば済むので、正規の利用がここに触れることはまずない）。
#   10分に3件  … ボットの連投・短時間のバースト
#   1時間に10件 … 間隔を空けた継続的な連投
JOIN_BURST_RULES = [(3, 600), (10, 3600)]

# 検知した IP の遮断（config.middleware.BlockedIpMiddleware）。
#
# 自分の IP を誤って遮断すると admin にも入れなくなるため、逃げ道を2つ用意してある。
# どちらも App Service のアプリケーション設定から変えられる（DB を触らずに復旧できる）。
#   IP_BLOCK_ENABLED=False   … 遮断そのものを止める
#   IP_BLOCK_EXEMPT=1.2.3.4,5.6.7.8 … 個別に除外する（遮断リストより優先）
IP_BLOCK_ENABLED = os.getenv('IP_BLOCK_ENABLED', 'True') == 'True'
IP_BLOCK_EXEMPT = [
    ip.strip() for ip in os.getenv('IP_BLOCK_EXEMPT', '').split(',') if ip.strip()
]

# 遮断期間（秒）。繰り返すほど延び、最後の値に達したらそれ以降は同じ。
# None は恒久（解除するまで）。
#   1回目 … 24時間、2回目 … 7日間、3回目以降 … 恒久
#
# 初回から恒久にしない理由。IP は個人の持ち物ではなく貸出品で、大学の構内ネットワークや
# 携帯のCGNATでは多数の人が同じIPを共有する。1人の乱用で無関係な人を永久に締め出しても
# こちらは気づけない（遮断された側は問い合わせフォームにも辿り着けない）。
# まず短く切って自動で解けるようにし、本当に繰り返す相手だけ恒久に落とす。
IP_BLOCK_DURATIONS = [24 * 60 * 60, 7 * 24 * 60 * 60, None]

# 差出人。bukkyo-u.ac.jp は2段階認証が許可されておらず、アプリ パスワードを発行できない
# ため、大学アカウントの SMTP では送れない。送信は Azure Communication Services を使い、
# 独自ドメイン funitclub.org の差出人で出す。返信は JOIN_NOTIFY_EMAIL に向ける
# （home/forms.py で Reply-To を付けている）ので、大学アドレスで受け取れる。
JOIN_FROM_EMAIL = os.getenv('JOIN_FROM_EMAIL', 'no-reply@funitclub.org')

DEFAULT_FROM_EMAIL = f'{SITE_NAME} <{JOIN_FROM_EMAIL}>'
SERVER_EMAIL = DEFAULT_FROM_EMAIL
