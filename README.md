# funITclub

佛教大学 通信教育課程 課外活動団体「fun IT club」の公開サイト（Django）。

- **公開ページは認証なし**（会員登録・allauth は入っていない）
- **編集画面（`/edit/`）だけログイン必須**。公開サイトとは別レイアウトで、相互にリンクしない
- 掲載内容（お知らせ・WG紹介・成果物紹介）はモデル化済みで、編集画面から編集する
- **参加の申し込みフォーム（`/join/apply/`）**。大学のメールアドレス（`@bukkyo-u.ac.jp`）のみ受け付ける
- **サブアプリ（WGごとのWebアプリ）は未実装**。URL 未設定のリンクは「作成中」ページ（`/coming-soon/`）へ流す
- デザインは `ホームページのイメージ案.pptx` に準拠（ネイビー #001E3C ＋ アクセント #5BB8FF、Consolas ＋ Meiryo）

## 構成

```
config/                設定（common / 本番 settings.py / 開発 settings_dev.py）
.env.example           ローカルの秘密情報のひな形（.env にコピーして使う。.env は git に入らない）
home/                  公開サイトの4ページ＋作成中ページ（モデルは持たず、表示だけ）
  forms.py             参加フォーム（/join/apply/）。入力内容をメールで送るだけで DB には残さない
  templates/home/      index / wg_list / work_list / join / join_apply / coming_soon
news/                  お知らせ（モデル＋編集画面＋admin 登録）
catalog/               WG紹介・成果物紹介（モデル＋編集画面＋admin 登録）
edit/                  編集画面の枠（ログイン・メニュー・共通レイアウト）＋運営まわり
  models.py            管理者（連絡先）。通知の宛先と公開の問い合わせ先はここだけを見る
  notify.py            管理者への通知メールの共通部分
  signals.py           ログイン失敗の監視
  checks.py            定期点検（SMTP のシークレット期限）
  templates/edit/      base（共通レイアウト）/ login / index（メニュー）
templates/base.html    公開サイトのヘッダー・ナビ・フッター（編集画面では使わない）
static/css/funitclub.css   デザイン一式（公開サイト・編集画面とも）
deploy.txt             Azure へのデプロイ・本番環境の作成手順（az コマンド一式）
docs/                  補足資料（セキュリティ対応一覧など）。デプロイの zip からは除外する
```

公開ページの掲載内容はすべて DB から読む。HTML を編集する必要はない。

| URL | 内容 |
|---|---|
| `/` | TOP（ヒーロー・活動サマリ・お知らせ） |
| `/wg/` | WG一覧 |
| `/works/` | 成果物 |
| `/join/` | 参加する（活動の案内） |
| `/join/apply/` | 参加を申し込む（フォーム） |
| `/join/apply/done/` | 申し込みの完了ページ（送信後の行き先） |
| `/coming-soon/` | 作成中プレースホルダ |

ここまでがログイン不要の公開ページ。以下はログイン必須。

| URL | 内容 |
|---|---|
| `/edit/` | 編集のメニュー |
| `/edit/login/` | ログイン |
| `/edit/news/` | お知らせの編集 |
| `/edit/wg/` | WG紹介の編集 |
| `/edit/works/` | 成果物紹介の編集 |
| `/admin/` | 管理画面（テーブルの中身を一覧・検索する。遮断IPの解除もここ） |

## 参加フォーム（`/join/apply/`）

参加ページ（`/join/`）は活動の案内だけを載せ、**申し込みフォームは別ページ**に置いている。
**ログイン不要**。hirahira_room のお問い合わせフォームと同じ作りで、モデルを持たず、
入力内容をメールで送るだけ（`home/forms.py` の `JoinForm`）。申し込みは DB に残らない。

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

1. 事務局（`JOIN_NOTIFY_EMAIL`）あての通知。
   `Reply-To` が申込者なので、そのまま返信すれば本人に届く。
2. 申込者あての控え（自動返信）。`Reply-To` は事務局の大学アドレス。
   第三者のアドレスが入力された場合にもこのメールは届くので、
   **「このメールに心当たりがない場合」の案内を必ず入れてある**。

どちらも差出人は `fun IT club <no-reply@funitclub.org>`。

送信後は申し込みページに戻さず、**完了ページ（`/join/apply/done/`）へリダイレクトする**。
このページに**フォームと申し込みページへのリンクを置かないこと**。以前は送信後に
申し込みページ自身へ戻していたが、完了メッセージの下に空のフォームと「申し込む」ボタンが
並ぶため、送れたか分からず押し直した人が連続送信（`JOIN_BURST_RULES`、既定で10分に3件）で
遮断されうる。大学の構内ネットワークは出口IPを共有しているので、巻き添えで同じ回線の
他の人まで 403 になる。`home/tests.py` の
`test_done_page_has_no_form_and_no_way_back_to_it` がこの制約を守っている。

**担当者からの返信は7日以内**。この期限は完了ページと自動返信の本文の両方に書いてある
（`home/templates/home/join_done.html` と `home/forms.py`）。片方だけ直さないこと。

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
| `JOIN_NOTIFY_EMAIL` | 通知先（未設定なら公開の問い合わせ先に送る） |

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
python manage.py sendtestemail <確認用のアドレス> --settings=config.settings_dev
```

認証情報が空のときは送信せず、メールの内容を runserver のログに出力する
（起動時にその旨を表示する）。**送信できる状態で試すと本物のメールが届く**ので、
フォームには自分のアドレスを入れること。なおテスト（`manage.py test`）は Django が
送信をメモリ上に差し替えるため、実際には送られない。

送信に失敗したときは 500 にせず、フォームにエラーを出して再送を促す（ログには
スタックトレースを残す）。

### 悪用への備え

入力されたアドレスの持ち主を確認していない以上、第三者あてに自動返信を送らせる余地は
残る。文章を載せられないようにしたうえで、異常な件数を検知できるようにしてある。

| 対策 | 内容 |
|---|---|
| 自由記述を持たない | メッセージ欄なし。攻撃者が第三者に読ませる文章を作れない |
| 氏名の URL を弾く | 30文字あれば短縮URLが収まるため、`http` / `www.` / `://` を含む氏名は拒否 |
| 心当たりがない場合の案内 | 自動返信に明記。受け取った人が破棄すれば手続きは進まないと伝える |
| 方針の掲示 | 申し込みページに、入力内容の扱いとアクセス制限の方針を出す |
| 連続送信の遮断 | 同一IPで **10分に3件** / **1時間に10件** を超えたら、そのIPを**恒久的に遮断**する |

掲示は**方針だけを書き、閾値や遮断期間の数値は出さない**（ギリギリを狙われるため）。
仕組みを伏せることで守る設計にはしていないので、方針の公開そのものは強度を下げない。
むしろ、共有回線での巻き添えに事前に触れておくと、起きたときの問い合わせが早くなる。

### IP の遮断

連続送信を検知すると `home.BlockedIp` にそのIPを登録し、以降のアクセスは
`config.middleware.BlockedIpMiddleware` が **403 で止める**（公開ページ・編集画面・
静的ファイルを含めてすべて）。閾値は `settings.JOIN_BURST_RULES` で調整する。

遮断期間は繰り返すほど延びる（`settings.IP_BLOCK_DURATIONS`）。

| 回数 | 期間 |
|---|---|
| 1回目 | 24時間 |
| 2回目 | 7日間 |
| 3回目以降 | 恒久（解除するまで） |

> **初回から恒久にしない理由。** IP は個人の持ち物ではなく貸出品で、大学の構内
> ネットワークや携帯キャリアの CGNAT では多数の人が同じIPを共有する。1人の乱用で
> 無関係な人を永久に締め出しても、**こちらは気づけない**（遮断された側は問い合わせ
> フォームにも辿り着けない）。さらに動的IPは時間とともに別人へ再割り当てされるため、
> 恒久遮断は放置するほど無関係な人を巻き込む。まず短く切って自動で解け、本当に
> 繰り返す相手だけ恒久に落とす。

期限切れの行は消さずに残す（再犯したときに回数を引き継ぐため）。手動の解除は
admin（`/admin/` → 遮断IP → 「今すぐ解除する」）。反映は最大60秒
（`BlockedIpMiddleware.CACHE_SECONDS`）。

遮断すると**運営に通知メールが届く**（`home/notifications.py`）。遮断された側は
問い合わせフォームにも辿り着けないため、こちらから気づく手段がこれしかない。
IPを変えながら攻撃されたときに通知で溢れないよう、1時間あたりの上限を設けてある
（`settings.IP_BLOCK_NOTIFY_MAX_PER_HOUR`）。

403 の画面（`home/templates/home/blocked.html`）には連絡先と「共有回線では他の方の
操作が原因の場合がある」旨を出す。**遮断中は静的ファイルも 403 になるため、この1枚に
CSS を埋め込んで自己完結させてある**（外部ファイルを読ませないこと）。

**自分のIPを遮断してしまうと admin にも入れなくなる**ので、逃げ道を2つ用意してある。
どちらも App Service のアプリケーション設定から変えられ、DB を触らずに復旧できる。

| 環境変数 | 効果 |
|---|---|
| `IP_BLOCK_ENABLED=False` | 遮断そのものを止める（ミドルウェアを組み込まない） |
| `IP_BLOCK_EXEMPT=1.2.3.4,5.6.7.8` | 指定IPを除外する。遮断リストより優先される |

遮断の判定に使うIPは `X-Forwarded-For` の**右端**（Azure の front end が付けた値）。
左端はクライアントが自由に詐称できるため、そちらを信じると**攻撃者が他人のIPを名乗って
無関係な人を遮断させられる**。DB やキャッシュを読めないときは通す（fail open）。
遮断機能のためにサイト全体を落とさない。

数える土台に DB キャッシュ（テーブル `funitclub_cache`）を使う。ローカルメモリだと
worker ごとに別勘定になり、再起動でも消えて検知漏れするため。**初回だけ
`createcachetable` が必要**。テーブルが無くても申し込み自体は通る（検知だけ働かない）。

```bash
python manage.py createcachetable --settings=config.settings_dev
```

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

## 管理者と通知

**運営の連絡先は `edit.Administrator`（管理者テーブル）にだけ置く。** 設定ファイルにも
テンプレートにも書かない。担当者が代わったときに追いきれなくなるうえ、HTML に個人の
アカウントが残るため。編集は admin（`/admin/` → 管理者）から。

| 用途 | 参照するもの |
|---|---|
| 参加申し込みの通知先 | 有効かつ「通知を受け取る」の全員 |
| 自動返信の `Reply-To` | 「公開ページの問い合わせ先にする」の先頭1件 |
| フッター・申し込みページ・403画面の連絡先 | 同上 |
| IP遮断・ログイン失敗・500エラーの通知先 | 有効かつ「通知を受け取る」の全員 |

### 受け取る宛先と、公開する宛先を分ける

| 種別 | アドレス | 用途 |
|---|---|---|
| 通知の宛先 | 環境変数 `JOIN_NOTIFY_EMAIL` | 運営が実際に読む受信箱。**公開しない** |
| 公開の問い合わせ先 | `contact@funitclub.org` | サイトに出す。転送で上記に届く |

**個人の大学アカウントは、公開ページにも、このリポジトリにも書かない。** ローカル部が
学籍番号そのもので、公開すると特定の学生の学籍番号が恒久的に晒される。**リポジトリは
公開なので、コードやテストに書けば検索でき、フォークやアーカイブにも残る。** 実際の
受信箱は App Service のアプリケーション設定（`JOIN_NOTIFY_EMAIL`）と管理者テーブルで
持ち、コードには役割アドレスだけを置く。

テーブルを読めないときの予備も、公開側は `settings.PUBLIC_CONTACT_EMAIL` に落とす
（`JOIN_NOTIFY_EMAIL` に倒すと、障害時に学籍番号が公開ページへ出てしまう）。

役割アドレスは**転送で受け取るので、通知は送らない**（同じ受信箱に二重で届くため）。

テンプレートからは `{{ public_contact }}` で参照する（`edit/context_processors.py`）。
アドレスを HTML に書かないので、担当者が代わってもテーブルを直すだけで全ページに反映される。

> **転送の設定が前提。** `contact@funitclub.org` はメール転送サービス（ImprovMX など）に
> MX レコードを向けて実現する。設定しないと届かないので、公開前に必ず疎通を確認すること。
> 手順は [deploy.txt](deploy.txt) の「メール送信」を参照。

テーブルが空、または DB を読めないときは `settings.JOIN_NOTIFY_EMAIL` に落とす。
宛先が無いせいで異常に気づけない事態を避けるための保険。

初期データはマイグレーション（`edit/migrations/0002_seed_administrator.py`）で登録済み。

### 通知される事象

| 事象 | 通知 | 補足 |
|---|---|---|
| IP を遮断した | 都度 | 1時間5通まで |
| ログイン失敗が続いた | 上限到達時に1回 | 既定は10分に5回。**遮断はしない** |
| 未処理の例外（500） | 都度 | `edit.log_handlers.DbAdminEmailHandler`。本番のみ |
| SMTP シークレットの期限接近 | 30日前・14日前・7日前・前日・失効後 | 各1回 |

通知は種類ごとに1時間あたりの通数を制限する（`settings.ADMIN_NOTIFY_MAX_PER_HOUR`）。
溢れると読まれなくなるため。

**ログイン失敗ではIPを遮断しない。** 正規の運営が打ち間違えて締め出されると、復旧の
手段を失うため。通知だけ出して、判断は人に委ねる。

### シークレットの期限通知

メール送信に使う Entra アプリのクライアント シークレットは**2028年8月19日**に失効する。
失効すると参加フォームの送信が止まるが、「申し込みが来ない」状態と区別がつかず気づけない。
そこで期限日を `settings.EMAIL_SECRET_EXPIRES_ON` に持ち、近づいたら通知する。

点検は1日1回、リクエストのついでに走る（`config.middleware.DailyCheckMiddleware`）。
App Service に常設のスケジューラが無いため。手元やスケジューラから明示的に叩くなら:

```bash
python manage.py check_secret_expiry --settings=config.settings_dev
```

> **シークレットを更新したら `EMAIL_SECRET_EXPIRES_ON` も必ず更新すること。**
> 忘れると通知が嘘になる。通知メールの本文に更新手順を書いてあるので、2年後に
> 受け取った人はそれを読めば対応できる。

なお、この仕組みは**メールが送れる状態でしか機能しない**。ACS 側の障害や送信停止には
気づけないので、そこまで見たい場合は Azure Monitor のアラートが必要になる。

## 管理画面（`/admin/`）

テーブルの中身を一覧・検索するための画面。hirahira_room と同じ構成で、素の Django admin を
そのまま使う（`config/urls.py` に `admin.site.urls`、登録は各アプリの `admin.py`）。
**編集の主導線は `/edit/` 側**で、admin は全カラムを見たいときや絞り込み検索に使う。

- 一覧に出す列・絞り込み・検索対象は各アプリの `admin.py` の `ModelAdmin` で決める。
- 管理者（`edit`）と遮断IP（`home`）もここから編集する。
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
python manage.py createcachetable --settings=config.settings_dev
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
| `JOIN_NOTIFY_EMAIL` | 任意。管理者テーブルが空のときの予備の宛先（通知用） |
| `PUBLIC_CONTACT_EMAIL` | 任意。同じく予備の公開問い合わせ先。既定は `contact@funitclub.org` |
| `EMAIL_SECRET_EXPIRES_ON` | シークレットの期限（`YYYY-MM-DD`）。更新時に必ず直す |
| `IP_BLOCK_ENABLED` / `IP_BLOCK_EXEMPT` | 任意。IP遮断の停止・除外（ロックアウトからの復旧用） |
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
