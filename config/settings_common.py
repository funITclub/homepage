# config/settings_common.py

import os
from pathlib import Path

from . import subapps

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-me-in-production')
# SECRET_KEY を替えるときは、前の値をここに残す（カンマ区切り）。署名（確認のリンク・
# セッション）と暗号化（WG への参加のアドレス・countdown の通知先）が前の鍵でも読める。
# 残さずに替えると、countdown の通知先が読めなくなり全員が未登録の扱いになる。
SECRET_KEY_FALLBACKS = [
    key.strip() for key in os.getenv('SECRET_KEY_FALLBACKS', '').split(',') if key.strip()
]
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
    'wgjoin',      # WG への参加（Classroom と GitHub への登録。会員の情報は持たない）
]

# サブアプリは置かれているフォルダーから自動で足す（config/subapps.py）。
#   works/ … 公表した成果物（countdown・fe）
#   wg/    … WG が作っている途中のもの。デプロイのときだけ取り込まれる
INSTALLED_APPS += subapps.installed(BASE_DIR)

MIDDLEWARE = [
    # 遮断リストの IP を最初に弾く。静的ファイルも含めて何も返さないよう先頭に置く。
    'config.middleware.BlockedIpMiddleware',
    # 1日1回の定期点検（SMTP のシークレット期限）。遮断済みの相手では動かさない。
    'config.middleware.DailyCheckMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    # 既定で全ビューをログイン必須にする。公開ページ側に
    # django.contrib.auth.decorators.login_not_required を付けて除外する
    # （編集画面に画面を足したときの付け忘れを防ぐため）。
    'django.contrib.auth.middleware.LoginRequiredMiddleware',
    # サブアプリ（works/・wg/ 配下）を、ホームページの一覧から辿ったときだけ開けるようにする。
    'config.gate.GateMiddleware',
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
                # 問い合わせ先（管理者テーブル）をどのページからも参照できるようにする
                'edit.context_processors.public_contact',
                # 正規の URL の頭（canonical・OGP 用）
                'home.context_processors.site_url',
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

# サブアプリへの導線（config/gate.py）
#
# 一覧のリンクに通行証を付け、URL を直に開いた人は一覧へ送り返す。
# 左が通行証の要る URL（config/urls.py で割り当てたもの）、右が送り返す先。
# 公表した成果物（works/ 配下）は成果物一覧へ、作っている途中（wg/ 配下）は WG一覧へ。
GATE_BACK = subapps.gate_back(BASE_DIR)
# 通行証の要らない入口。それぞれ別の鍵（メールの署名付きリンク・呼び出しトークン・
# 編集画面のログイン）で守られているところだけを並べる。ここは守りを緩めるための
# 一覧ではないので、増やすときは「別の鍵があるか」を確かめること。
GATE_EXEMPT = ['/countdown/notify/', '/fe/console/', '/fe/mail/confirm/', '/fe/mail/stop/', '/fe/tasks/']
# 一覧を開いてからアプリに入るまでの猶予
GATE_MAX_AGE = 10 * 60

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# FE 対策アプリ（/fe/）の問題 JSON の上限。fe.forms がここを見る。
# 技術解説を含めると 1MB を超える（小分類 96 本ぶんの解説と問題 200 問で 1.1MB の実測）。
# これを受け取れる大きさにし、取り違えを疑う線として上限も置く。
FE_MAX_UPLOAD_BYTES = 8 * 1024 * 1024

# ファイル本体は multipart で送られ、この値の対象外になる（Django の仕様）。
# 効くのは取り込みの確認画面で、内容を hidden の欄に載せて送り直すとき。
# 上の上限と食い違わないよう合わせておく。
DATA_UPLOAD_MAX_MEMORY_SIZE = FE_MAX_UPLOAD_BYTES + 1024 * 1024

# FE の技術解説の読み上げ音声（manage.py make_note_audio で作る）
FE_AUDIO_ROOT = BASE_DIR / 'media' / 'fe_audio'

# サイト共通の表示情報（テンプレートから参照）
SITE_NAME = 'fun IT club'
SITE_TAGLINE = '佛教大学 通信教育課程 課外活動団体'

# 参加フォーム（/join/apply/）
# 申し込みは大学から発行されたメールアドレスからのみ受け付ける。活動ツールが
# 大学の Google Workspace 前提なので、私用アドレスでは先に進めないため。
JOIN_ALLOWED_EMAIL_DOMAIN = 'bukkyo-u.ac.jp'

# 公開する問い合わせ先。自分たちのドメインの役割アドレスを使い、転送で受け取る。
#
# 個人の大学アカウント（学籍番号がローカル部になっている）は、公開ページにも
# **このリポジトリにも**書かない。リポジトリは公開なので、コードに残せば検索でき、
# フォークやアーカイブにも残る。役割アドレスなら転送先を変えるだけで引き継げる。
PUBLIC_CONTACT_EMAIL = os.getenv('PUBLIC_CONTACT_EMAIL', 'contact@funitclub.org')

# 通知の宛先。運営が実際に読む受信箱を、App Service のアプリケーション設定で指定する。
# 未設定なら役割アドレスに送る（転送されて同じ受信箱に届く）。
JOIN_NOTIFY_EMAIL = os.getenv('JOIN_NOTIFY_EMAIL', PUBLIC_CONTACT_EMAIL)

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

# 管理者への通知（edit.notify）。種類ごとに1時間あたりの通数を制限する。
# 通知が溢れると読まれなくなるため。
ADMIN_NOTIFY_MAX_PER_HOUR = 10

# 未処理の例外（500）や ERROR ログの通知の上限（1時間あたり）。
# DB やキャッシュが落ちるとリクエストのたびに ERROR が出るため、必ず頭を打たせる。
ERROR_NOTIFY_MAX_PER_HOUR = 10

# 遮断したときに管理者へ送る通知の上限（1時間あたり）。
# IP を変えながら攻撃されると通知が大量に届くため、頭を打たせる。
IP_BLOCK_NOTIFY_MAX_PER_HOUR = 5

# ログイン失敗の監視（edit.signals）。(回数, 秒) に達したら管理者に通知する。
# ※ 遮断はしない。正規の運営が打ち間違えて締め出されると復旧できなくなるため。
LOGIN_FAILURE_RULE = (5, 600)

# メール送信に使う Entra アプリのクライアント シークレットの期限（YYYY-MM-DD）。
# 30日前・14日前・7日前・前日と失効後に、管理者へ通知する（edit.checks）。
# **シークレットを更新したらこの値も必ず更新すること。**
EMAIL_SECRET_EXPIRES_ON = os.getenv('EMAIL_SECRET_EXPIRES_ON', '2028-08-19')

# 差出人。大学のドメイン（bukkyo-u.ac.jp）は2段階認証が許可されておらず、アプリ
# パスワードを発行できないため、大学アカウントの SMTP では送れない。送信は Azure
# Communication Services を使い、独自ドメイン funitclub.org の差出人で出す。
# 返信は問い合わせ先に向ける（home/forms.py で Reply-To を付けている）。
JOIN_FROM_EMAIL = os.getenv('JOIN_FROM_EMAIL', 'no-reply@funitclub.org')

DEFAULT_FROM_EMAIL = f'{SITE_NAME} <{JOIN_FROM_EMAIL}>'
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# WG への参加（wgjoin）。WG 一覧の「WG に参加」で大学のアドレスを入れてもらい、運営の権限で
# Classroom のクラブのクラスの名簿を引いてメンバーか確かめる。メンバーなら確認のメールの
# リンクから、WG の Chat スペースに追加し（WG紹介に Chat スペースがある WG だけ。運営の権限）、
# GitHub の WG のチームに登録する。Chat スペースのない WG では、クラスの授業にあるリンクから本人が入る。
# 会員の情報はサイトに持たない（名簿は Classroom）。値はすべて環境変数から読み、
# どれかが欠けていれば「WG に参加」を出さない（wgjoin.config.is_enabled）。
#
#   CLUB_CLASSROOM_COURSE      … クラブの Classroom のクラス（URL か ID）。ここにいる人をメンバーとみなす
#   CLUB_CHAT_SPACE            … 任意。クラブのお知らせの Chat スペース（URL か spaces/<ID>）。
#                                参加の申し込みの時点で申込者を追加する（home/views.py）。空なら追加しない
#   GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET
#                              … Google Cloud の OAuth クライアント（デスクトップ アプリ）
#   GOOGLE_OAUTH_REFRESH_TOKEN … クラスの先生（運営）が名簿の管理と Chat のメンバーの管理を許可したもの
#                                （参加の申し込みでのクラブのクラスへの招待にも使う。home/views.py）
#                                （manage.py wgjoin_google_authorize で受け取る）
#   GITHUB_APP_ID / GITHUB_APP_CLIENT_ID / GITHUB_APP_CLIENT_SECRET / GITHUB_APP_PRIVATE_KEY
#                              … funITclub の GitHub App（org の Members を読み書きできるもの）。
#                                WG の活動ページ（wg/<WG>_activity）も、同じ App でチケット（Issues と
#                                Projects）を読む。トークンはその WG の読み取りだけに絞って取る
GITHUB_ORG = os.getenv('GITHUB_ORG', 'funITclub')
CLUB_CLASSROOM_COURSE = os.getenv('CLUB_CLASSROOM_COURSE', '')
CLUB_CHAT_SPACE = os.getenv('CLUB_CHAT_SPACE', '')
GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '')
GOOGLE_OAUTH_REFRESH_TOKEN = os.getenv('GOOGLE_OAUTH_REFRESH_TOKEN', '')
GITHUB_APP_ID = os.getenv('GITHUB_APP_ID', '')
GITHUB_APP_CLIENT_ID = os.getenv('GITHUB_APP_CLIENT_ID', '')
GITHUB_APP_CLIENT_SECRET = os.getenv('GITHUB_APP_CLIENT_SECRET', '')
# 秘密鍵（PEM）。.env では1行に書けるよう、\n と書いた改行を戻す。
GITHUB_APP_PRIVATE_KEY = os.getenv('GITHUB_APP_PRIVATE_KEY', '').replace('\\n', '\n')

# ---- カウントアップ＆ダウンのメール通知（countdown/notify.py） ----
# メールに書くリンクの頭。通知はリクエストの外から送るので、設定で持つ。
SITE_URL = os.getenv('SITE_URL', 'http://localhost:8010')
# 毎日0時の送信を起こす呼び出し（/countdown/notify/run/）の合言葉。
# 空のときは入口を閉じる。GitHub の Actions のシークレットと同じ値を入れる。
COUNTDOWN_NOTIFY_TOKEN = os.getenv('COUNTDOWN_NOTIFY_TOKEN', '')
# 通知先の確認のメールのリンクの有効期限（秒）。
COUNTDOWN_CONFIRM_MAX_AGE = 60 * 60
# 確認のメールを送りすぎないための上限。((件数, 秒) 同じ IP, (件数, 秒) 同じアドレス)。
COUNTDOWN_CONFIRM_SEND_LIMITS = ((10, 60 * 60), (3, 60 * 60))

# ---- FE 対策アプリの問題メール（works/fe/mail.py） ----
# リンクの頭は上の SITE_URL を使う。
# 毎日0時の送信を起こす呼び出し（/fe/tasks/send-mails/）の合言葉。
# 空のときは入口を閉じる（503）。GitHub の Actions のシークレットと同じ値を入れる。
FE_MAIL_TOKEN = os.getenv('FE_MAIL_TOKEN', '')
# 確認のメールのリンクの有効期限（秒）
FE_MAIL_CONFIRM_MAX_AGE = 60 * 60
# 確認・解除のメールを、同じ ID から続けて送らせない間隔（秒）
FE_MAIL_LINK_INTERVAL = 5 * 60

# ---- FE 対策アプリの X 投稿（works/fe/x_post.py） ----
# hirahira_room から取り込んだ仕組み。funitclub では投稿しない（トークンを入れないので
# /fe/tasks/post-x/ は 503 を返し、FE_X_DRY_RUN も True のまま）。
# 解答ページのリンクの頭は上の SITE_URL を使う。
FE_X_TOKEN = os.getenv('FE_X_TOKEN', '')
# X API のキー（OAuth 1.0a のユーザーコンテキスト）
X_API_KEY = os.getenv('X_API_KEY', '')
X_API_SECRET = os.getenv('X_API_SECRET', '')
X_ACCESS_TOKEN = os.getenv('X_ACCESS_TOKEN', '')
X_ACCESS_SECRET = os.getenv('X_ACCESS_SECRET', '')
# True なら X に投稿せず、文面をログに出すだけにする。
FE_X_DRY_RUN = os.getenv('FE_X_DRY_RUN', 'True') == 'True'
# 解答ページを出しておく日数。過ぎたら投稿の記録を行ごと消し、案内ページにする。
FE_X_KEEP_DAYS = 30

# 確認のメールのリンクの有効期限（秒）。
WG_JOIN_LINK_MAX_AGE = 60 * 60

# リンクを開いてから GitHub の手続きを終えるまでの猶予（秒）。GitHub アカウントを
# その場で作る人がいるので、長めに取る。
WG_JOIN_STEP_TIMEOUT = 60 * 60

# 確認のメールを送りすぎないための上限。((件数, 秒) 同じ IP, (件数, 秒) 同じアドレス)。
# 超えたら送らずに「時間をおいて」と出すだけで、IP の遮断はしない（構内の回線は共有のため）。
WG_JOIN_SEND_LIMITS = ((10, 60 * 60), (3, 60 * 60))
