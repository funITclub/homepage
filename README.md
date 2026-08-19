# funITclub

佛教大学 通信教育課程 課外活動団体「fun IT club」の公開サイト（Django）。

- **公開ページは認証なし**（会員登録・allauth は入っていない）
- **編集画面（`/edit/`）だけログイン必須**。公開サイトとは別レイアウトで、相互にリンクしない
- 掲載内容（お知らせ・WG紹介・成果物紹介）はモデル化済みで、編集画面から編集する
- **参加ページ（`/join/`）に申し込みフォーム**。大学のメールアドレス（`@bukkyo-u.ac.jp`）のみ受け付ける
- **サブアプリ（WGごとのWebアプリ）は未実装**。URL 未設定のリンクは「作成中」ページ（`/coming-soon/`）へ流す
- デザインは `ホームページのイメージ案.pptx` に準拠（ネイビー #001E3C ＋ アクセント #5BB8FF、Consolas ＋ Meiryo）

## 構成

```
config/                設定（common / 本番 settings.py / 開発 settings_dev.py）
.env.example           ローカルの秘密情報のひな形（.env にコピーして使う。.env は git に入らない）
home/                  公開サイトの4ページ＋作成中ページ（モデルは持たず、表示だけ）
  forms.py             参加フォーム（/join/）。入力内容をメールで送るだけで DB には残さない
  templates/home/      index / wg_list / work_list / join / coming_soon
news/                  お知らせ（モデル＋編集画面＋admin 登録）
catalog/               WG紹介・成果物紹介（モデル＋編集画面＋admin 登録）
edit/                  編集画面の枠（ログイン・メニュー・共通レイアウト。モデルなし）
  templates/edit/      base（共通レイアウト）/ login / index（メニュー）
templates/base.html    公開サイトのヘッダー・ナビ・フッター（編集画面では使わない）
static/css/funitclub.css   デザイン一式（公開サイト・編集画面とも）
deploy.txt             Azure へのデプロイ・本番環境の作成手順（az コマンド一式）
```

公開ページの掲載内容はすべて DB から読む。HTML を編集する必要はない。

| URL | 内容 |
|---|---|
| `/` | TOP（ヒーロー・活動サマリ・お知らせ） |
| `/wg/` | WG一覧 |
| `/works/` | 成果物 |
| `/join/` | 参加する（申し込みフォーム） |
| `/coming-soon/` | 作成中プレースホルダ |

ここまでがログイン不要の公開ページ。以下はログイン必須。

| URL | 内容 |
|---|---|
| `/edit/` | 編集のメニュー |
| `/edit/login/` | ログイン |
| `/edit/news/` | お知らせの編集 |
| `/edit/wg/` | WG紹介の編集 |
| `/edit/works/` | 成果物紹介の編集 |
| `/admin/` | 管理画面（テーブルの中身を一覧・検索する） |

## 参加フォーム（`/join/`）

参加ページの右カラムに申し込みフォームを置いている。**ログイン不要**。hirahira_room の
お問い合わせフォームと同じ作りで、モデルを持たず、入力内容をメールで送るだけ
（`home/forms.py` の `JoinForm`）。申し込みは DB に残らない。

| 項目 | 必須 | 備考 |
|---|---|---|
| お名前 | ○ | |
| 大学のメールアドレス | ○ | `@bukkyo-u.ac.jp` 以外は弾く（`JOIN_ALLOWED_EMAIL_DOMAIN`） |
| 興味のあるWG | | 公開中の WG から選ぶ。空欄（まだ決めていない）でよい |

**自由記述（メッセージ欄）は意図的に持たせていない。復活させないこと。** 入力された
アドレスが本人のものか確認していないため、第三者のアドレスを入れれば自動返信をその人に
届けられる。自由記述があると、その本文に任意の文章を載せてフィッシングの配送路に使える
（差出人は SPF/DKIM/DMARC が通った `funitclub.org` なので、受信側の認証チェックはすべて
成功してしまう）。聞きたいことは、届いた自動返信に返信すれば事務局に届く。
`home/tests.py` の `test_form_has_no_free_text_field` がこの制約を守っている。

活動ツールが大学の Google Workspace 前提なので、**私用アドレスでは受け付けない**。
送信すると2通のメールが出る。

1. 事務局（`JOIN_NOTIFY_EMAIL` ＝ `contact@funitclub.org`）あての通知。
   `Reply-To` が申込者なので、そのまま返信すれば本人に届く。
2. 申込者あての控え（自動返信）。`Reply-To` は事務局の大学アドレス。
   第三者のアドレスが入力された場合にもこのメールは届くので、
   **「このメールに心当たりがない場合」の案内を必ず入れてある**。

どちらも差出人は `fun IT club <no-reply@funitclub.org>`。

送信は **Azure Communication Services（ACS）の SMTP リレー**（`smtp.azurecomm.net:587` / TLS）を
使い、独自ドメインの `no-reply@funitclub.org` から出す。

> **大学アカウントからは送れない。** `bukkyo-u.ac.jp` は Google Workspace 側で2段階認証が
> 許可されておらず、アプリ パスワードを発行できない。Google は2段階認証なしの SMTP 認証を
> 廃止済みなので、大学アドレスでの SMTP 送信は経路がない。**受信は問題ない**ため、通知先と
> Reply-To は大学アドレスのままにしてある。申込者が控えのメールに返信すれば大学アドレスに届く。

認証情報はリポジトリに持たず、環境変数から読む。**差出人アドレスと SMTP ユーザー名は別物**
なので混同しないこと。

| 設定 | 中身 |
|---|---|
| `EMAIL_HOST_USER` | ACS の「SMTP ユーザー名」。Entra アプリに紐づく認証用の名前 |
| `EMAIL_HOST_PASSWORD` | 紐づけた Microsoft Entra アプリのクライアント シークレット |
| `JOIN_FROM_EMAIL` | 差出人アドレス（既定 `no-reply@funitclub.org`） |
| `JOIN_NOTIFY_EMAIL` | 通知先（既定 `contact@funitclub.org`） |

本番のシークレットは App Service に平文で置かず、**Azure Key Vault**（`funitclub-kv`）に入れて
アプリケーション設定から参照している。取り出せるのは App Service のマネージド ID だけで、
権限は `Key Vault Secrets User`（読み取りのみ）。Entra アプリ側もカスタムロール
`funITclub Email Sender`（ACS のメール送信に必要な3操作のみ）に絞ってある。

なりすまし対策として SPF・DKIM に加えて **DMARC**（`p=none`）を設定済み。レポートを見て
問題がなければ `p=quarantine` → `p=reject` と強められる。

ACS のリソース作成・独自ドメインの DNS 検証・Entra アプリの手順は
[deploy.txt](deploy.txt) の「メール送信」を参照。

**ローカルでも本番と同じ経路で実際に送信する**。認証情報は `.env` に置く
（`.gitignore` 済み。`config/settings_dev.py` が起動時に読む）。

```bash
cp .env.example .env
# .env に EMAIL_HOST_USER と EMAIL_HOST_PASSWORD を入れて runserver を再起動する
```

`.env` を編集したら runserver を再起動する（起動時に一度だけ読むため）。設定できたか
どうかは、フォームを使わずに確かめられる。

```bash
python manage.py sendtestemail contact@funitclub.org --settings=config.settings_dev
```

認証情報が空のときは送信せず、メールの内容を runserver のログに出力する
（起動時にその旨を表示する）。**送信できる状態で試すと本物のメールが届く**ので、
フォームには自分のアドレスを入れること。なおテスト（`manage.py test`）は Django が
送信をメモリ上に差し替えるため、実際には送られない。

送信に失敗したときは 500 にせず、フォームにエラーを出して再送を促す（ログには
スタックトレースを残す）。

## 編集画面（`/edit/`）

掲載内容を編集する画面。**ログイン必須**。未ログインで URL を直接叩くと
`/edit/login/?next=...` に飛ばされる。公開サイトとは別レイアウト
（`edit/base.html`）で、公開ナビも持たず、公開ページとの相互リンクもない。

保護は hirahira_room と同じ二段構え。

1. `LoginRequiredMiddleware`（`config/settings_common.py`）で**全ビューを既定ログイン必須**にする。
   公開ページ（`home/views.py`）だけ `login_not_required` を付けて除外している。
   新しい編集画面を足したときに保護を書き忘れても、素通りにはならない。
2. 各編集ビューは `edit.views.EditorMixin`（＝`LoginRequiredMixin`）も継承している。

静的ファイルは保護の対象外（本番は WhiteNoise が認証より前に配信し、開発は runserver が
ミドルウェアを通さずに返す）。公開ページの見た目は未ログインでも崩れない。

編集した内容がそのまま公開ページに出る。反映のされ方は次のとおり。

| 編集対象 | モデル | 公開側の出かた |
|---|---|---|
| お知らせ | `news.News` | TOP に公開中の新しい順で3件（件数は `home.views.IndexView.news_limit`）。掲載日が未来のものは出ないので予約投稿にできる |
| WG紹介 | `catalog.Wg` | `/wg/` に表示順で並ぶ。「準備中」のカードは参加ボタンだけを出す |
| 成果物紹介 | `catalog.Work` | `/works/` に表示順で並ぶ |

TOP の活動サマリの件数も連動する。

- 「活動中のWG」＝ 公開中かつ状態が「活動中」の WG の数
- 「公開済み成果物」＝ 公開中の成果物の数
- 「CC BY 成果物ライセンス」は固定表示（テンプレート直書き）

いずれも `is_published` を外すと下書き扱いになり、一覧にも件数にも出ない。
WG の「Webアプリの URL」や成果物の「公開先の URL」が空欄なら `/coming-soon/` に繋ぐ。

アカウントは会員登録のような入口を持たず、`createsuperuser` で作る。

```bash
python manage.py createsuperuser --settings=config.settings_dev
```

## 管理画面（`/admin/`）

テーブルの中身を一覧・検索するための画面。hirahira_room と同じ構成で、素の Django admin を
そのまま使う（`config/urls.py` に `admin.site.urls`、登録は各アプリの `admin.py`）。
**編集の主導線は `/edit/` 側**で、admin は全カラムを見たいときや絞り込み検索に使う。

- 一覧に出す列・絞り込み・検索対象は `news/admin.py` と `catalog/admin.py` の `ModelAdmin` で決める。
- `created_at` / `updated_at` は読み取り専用。
- ログイン画面は admin 自身のもの（`/admin/login/`）。Django が admin の URL に `login_url` を
  仕込んでいるため、`LoginRequiredMiddleware` も `/edit/login/` ではなくそちらへ回す。
  セッションは共通なので、`/edit/login/` でログイン済みならそのまま開ける（`is_staff` が必要）。
- アカウントの追加・パスワード変更は admin の「認証と認可」からでも、コマンド
  （`createsuperuser` / `changepassword`）からでもよい。

## セットアップ

hirahira_room と同じく、リポジトリ直下の `venv` を使う（`.claude/launch.json` も
`venv/bin/python` を呼ぶ）。

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py runserver --settings=config.settings_dev
```

お知らせ用のテーブルがあるので、初回は migrate が必要。編集画面を触るなら
ログイン用のアカウントも作る。

```bash
python manage.py migrate --settings=config.settings_dev
python manage.py createsuperuser --settings=config.settings_dev
```

参加フォームのメールを実際に送るなら、ACS の認証情報を `.env` に入れる
（詳しくは[参加フォーム](#参加フォームjoin)）。入れなければコンソール出力で動く。

```bash
cp .env.example .env
```

## 開発と本番の切り替え

hirahira_room と同じ構成。設定を3ファイルに分け、**既定は本番**。

| | 開発（ローカル） | 本番（Azure App Service） |
|---|---|---|
| 設定モジュール | `config.settings_dev` | `config.settings`（既定） |
| 指定方法 | 毎回 `--settings=config.settings_dev` を付ける | 指定不要（`manage.py` と `wsgi.py` の既定） |
| DEBUG | `True` | 既定 `False`。環境変数 `DEBUG=True` で一時的に有効化できる |
| DB | SQLite（`DB_HOST` を渡したときだけ PostgreSQL） | PostgreSQL（funITclub 専用DB） |
| 静的ファイル | runserver が配信 | WhiteNoise（圧縮＋ハッシュ付き） |
| メール | 大学アカウントの SMTP（`.env` の `EMAIL_HOST_PASSWORD`）。未設定ならコンソール出力 | 大学アカウントの SMTP（smtp.gmail.com） |
| Cookie | 通常 | `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` が True |
| ログ | DEBUG レベル・詳細フォーマット | INFO レベル |

共通の設定は `config/settings_common.py` に置き、両方がこれを読み込む。

**`--settings` を付け忘れると本番設定（PostgreSQL）で動いて DB 接続に失敗する。**
ローカルで `manage.py` を叩くときは毎回付けること。

デプロイと本番環境の作成手順は [deploy.txt](deploy.txt) にまとめてある。

## データベース

PostgreSQL サーバーは hirahira_room と同じものを使うが、**データベースは funITclub 専用のものを
分ける**（`DB_NAME` で指定）。hirahira_room の共有DBには一切触らないので、こちらは自由に
`migrate` してよい。接続情報はリポジトリに持たず、すべて環境変数（App Service のアプリケーション
設定）から読む。既定値は持たないので、未設定なら接続しない。

ローカル（`config/settings_dev.py`）は SQLite。`DB_HOST` を渡したときだけ PostgreSQL に切り替わる。
ただし hirahira-db は公開アクセスが無効（VNet 内からのみ）なので、手元から直接は繋がらない。

> **注意: hirahira_room の共有DBに対して `migrate` を実行しないこと。**
> `DB_NAME` が funITclub 専用DBを指していることを確認してから実行する。
> なおテーブル名は `funitclub_news` / `funitclub_wg` / `funitclub_work` に固定してあり
> （各モデルの `db_table`）、万一DBを取り違えても既存テーブルとは衝突しないようにしてある。

本番DBの初期化（専用DBの作成 → 環境変数 → migrate）は [deploy.txt](deploy.txt) の
「初回のみ」を参照。

## 環境変数（本番）

Azure App Service（`funITclub`）のアプリケーション設定。hirahira-room と同じ構成。

| 変数 | 用途 |
|---|---|
| `SECRET_KEY` | 本番の秘密鍵 |
| `DB_NAME` | funITclub 専用データベース名（`funitclub`）。hirahira_room の共有DBを指さないこと |
| `DB_USER` / `DB_PASSWORD` / `DB_HOST` | PostgreSQL の接続情報（hirahira-room と同じ値） |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `True`。デプロイ時に pip install と collectstatic を走らせる |
| `WEBSITE_HOSTNAME` | Azure が自動設定。CSRF_TRUSTED_ORIGINS に反映 |
| `EMAIL_HOST_USER` | ACS の SMTP ユーザー名。未設定だと送信できない |
| `EMAIL_HOST_PASSWORD` | 紐づけた Entra アプリのクライアント シークレット。本番は Key Vault 参照（`@Microsoft.KeyVault(...)`）で入れている |
| `JOIN_FROM_EMAIL` | 任意。差出人アドレス。既定は `no-reply@funitclub.org` |
| `JOIN_NOTIFY_EMAIL` | 任意。参加申し込みの通知先。既定は大学のアドレス |
| `DEBUG` | 任意。`True` のときだけ本番でも DEBUG が有効になる。切り分け用で、常設しないこと |

`DJANGO_SETTINGS_MODULE` は不要（`manage.py` と `wsgi.py` の既定が `config.settings`）。

## 今後

- 各WGのサブアプリを追加したら、編集画面でそのWG・成果物に URL を入れる
  （テンプレートの修正は不要。空欄のあいだは `/coming-soon/` に流れる）。
- 編集する項目を増やすときは、`catalog` と同じ作りでモデル・フォーム・画面を足し、
  `edit/templates/edit/base.html` のナビにリンクを追加する。
- TOP の「すべて見る →」はまだ `/coming-soon/` を指している。お知らせの一覧ページを
  作ったら差し替える。
- 「CC BY 成果物ライセンス」のタイルだけは `home/templates/home/index.html` の直書き。
- `manage.py check --deploy` は SECURE_HSTS_SECONDS と SECURE_SSL_REDIRECT の未設定を
  警告する（着手前からの状態）。ログイン機能が入ったので、いずれ対応しておきたい。
