# funITclub

佛教大学 通信教育課程 課外活動団体「fun IT club」の公開サイト（Django）。

- **公開ページは認証なし**（会員登録・allauth は入っていない）
- **編集画面（`/edit/`）だけログイン必須**。公開サイトとは別レイアウトで、相互にリンクしない
- 掲載内容（お知らせ・WG紹介・成果物紹介）はモデル化済みで、編集画面から編集する
- **参加の申し込みフォーム（`/join/apply/`）**。大学のメールアドレス（`@bukkyo-u.ac.jp`）のみ受け付ける。申し込みの時点でクラブの Classroom のクラスに招待する
- **サブアプリ**。公表した成果物は `works/`（countdown・fe）、WG が作っている途中のアプリと活動ページは、デプロイのときに WG のリポジトリから `wg/` に取り込む（「[サブアプリ](#サブアプリworkswg)」）。URL 未設定のリンクは「作成中」ページ（`/coming-soon/`）へ流す
- **FE 基本情報技術者試験 対策（`/fe/`）**。ログインなしで誰でも使える公開アプリ。成績はアプリの中の ID ごとに持つ（ID を登録しなくても使える）。問題集の管理（`/fe/manage/`）だけは編集画面のログインが要る。詳しくは [works/fe/README.md](works/fe/README.md)
- **WG への参加（`/wg/<id>/join/`）**。クラブのメンバー（Classroom のクラブのクラスにいる人）だけが、大学のアドレスの確認を経て、自分で WG の Chat スペースと GitHub の WG のチームに入れる。会員の情報はサイトに持たない
- **技術設計**（メール送信・参加の申し込み・WG への参加の仕組み）は [docs/design.md](docs/design.md)
- デザインはネイビー #001E3C ＋ アクセント #5BB8FF、Consolas ＋ Meiryo（元にした `ホームページのイメージ案.pptx` はリポジトリに入れていない。定義は `static/css/funitclub.css`）

## 構成

```
config/                設定（common / 本番 settings.py / 開発 settings_dev.py）
.env.example           ローカルの秘密情報のひな形（.env にコピーして使う。.env は git に入らない）
home/                  公開サイトの6ページ＋作成中ページ（モデルは持たず、表示だけ）
  forms.py             参加フォーム（/join/apply/）。入力内容をメールで送るだけで DB には残さない（クラスへの招待は views.py）
  templates/home/      index / news_list / wg_list / work_list / join / join_apply / join_done / guide / coming_soon / blocked（403）
news/                  お知らせ（モデル＋編集画面＋admin 登録）
catalog/               WG紹介・成果物紹介（モデル＋編集画面＋admin 登録）
wgjoin/                WG への参加（/wg/<id>/join/）。Classroom でメンバーか確かめ、Chat スペースに追加して GitHub のチームに登録する。参加の申し込みでのクラスへの招待もここ（google.py）
wg-apps.yml            デプロイのときに取り込む WG のアプリの一覧（ソースはこのリポジトリに入れない）
works/                 公表した成果物のアプリ。フォルダー名は URL に出さない（config/subapps.py が自動で組み込む）
  countdown/           サブアプリ「カウントアップ＆ダウン」（/countdown/）。ログイン不要
  fe/                  サブアプリ「FE 基本情報技術者試験 対策」（/fe/）。hirahira_room からの移植。ログイン不要
wg/                    WG が作っている途中のアプリ。デプロイのときだけ取り込まれる（手元では空）
edit/                  編集画面の枠（ログイン・メニュー・共通レイアウト）＋運営まわり
  models.py            管理者（連絡先）。通知の宛先と公開の問い合わせ先はここだけを見る
  notify.py            管理者への通知メールの共通部分
  signals.py           ログイン失敗の監視
  checks.py            定期点検（SMTP のシークレット期限、FE 対策アプリの一時的な記録の掃除、countdown の通知メール）
  templates/edit/      base（共通レイアウト）/ login / index（メニュー）
templates/base.html    公開サイトのヘッダー・ナビ・フッター（編集画面では使わない）
static/css/funitclub.css   デザイン一式（公開サイト・編集画面とも）
static/guide/          WG 立ち上げガイドの資料（pptx 5 本）。/guide/ から配る
deploy.txt             Azure へのデプロイ・本番環境の作成手順（az コマンド一式）
startup.sh             App Service の起動コマンド（migrate → gunicorn）
.github/workflows/     main への push で App Service にデプロイする（GitHub Actions）
docs/                  補足資料（開発の手順・技術設計・セキュリティ対応一覧など）。デプロイの zip からは除外する
  deck/                WG 立ち上げガイド（static/guide/*.pptx）を直すための道具と決まりごと
.devcontainer/         開発環境（VS Code の Dev Container）の定義。デプロイの zip からは除外する
.vscode/               VS Code の共通設定（起動構成・タスク）。デプロイの zip からは除外する
```

公開ページの掲載内容はすべて DB から読む。HTML を編集する必要はない。

| URL | 内容 |
|---|---|
| `/` | TOP（ヒーロー・活動サマリ・お知らせ） |
| `/news/` | お知らせ一覧 |
| `/wg/` | WG一覧 |
| `/works/` | 成果物 |
| `/join/` | 参加する（活動の案内） |
| `/join/apply/` | 参加を申し込む（フォーム） |
| `/join/apply/done/` | 申し込みの完了ページ（送信後の行き先） |
| `/coming-soon/` | 作成中プレースホルダ |
| `/wg/<id>/join/` | WG に参加（大学のアドレスの確認メール → GitHub のログインで進む。設定がそろったときだけ出る） |
| `/guide/` | WG 立ち上げガイド（資料 00〜04 の置き場）。ナビには出さず、参加の完了画面と確認のメールから案内する |
| `/robots.txt`・`/sitemap.xml` | 検索エンジン向け。サイトマップにはナビの公開ページだけを載せ、編集画面・申し込みの途中・サブアプリは巡回から外す（`home/views.py`） |

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

参加ページ（`/join/`）は活動の案内だけを載せ、**申し込みフォームは別ページ**に置く。ログイン不要。
入力は大学のメールアドレスだけで（`@bukkyo-u.ac.jp` 以外は弾く。活動ツールが大学の Google Workspace
前提のため）、申し込みは DB に残らない。設定がそろっていれば、申し込みの時点でクラブの Classroom の
クラスに招待する（運営の承認は挟まない）。招待できたときはサイトからはメールを送らず、Google の
招待メールだけが届く。事務局に知らせるのは手作業が要るとき（招待できなかったとき）だけ。

仕組み（招待の結果ごとの振る舞い・メールの経路・連続送信の検知と IP の遮断）は
[docs/design.md](docs/design.md) の 1・2 章。

### 変えてはいけないこと

| 決まり | 理由 | 守っているテスト |
|---|---|---|
| **自由記述（メッセージ欄）を持たない。復活させない** | 入力されたアドレスの持ち主を確かめていないので、本文に任意の文章を載せて第三者に届ける、フィッシングの配送路になる（差出人の `funitclub.org` は SPF・DKIM・DMARC が通るので、受信側の認証はすべて成功する）。聞きたいことは、控えのメールに返信すれば事務局に届く | `home/tests.py` の `test_form_has_no_free_text_field` |
| 氏名など、自由に書ける欄も持たない（2026-10-20 に外した） | 同じ理由。名前はクラスに参加すれば Classroom の名簿に出る | 同上 |
| **完了ページ（`/join/apply/done/`）にフォームも申し込みページへのリンクも置かない** | 送れたか分からず押し直した人が連続送信の遮断（既定で 10 分に 3 件）に当たる。構内の回線は IP を共有しているので、同じ回線の他の人まで 403 になる | `test_done_page_has_no_form_and_no_way_back_to_it` |
| 控えのメールに「このメールに心当たりがない場合」の案内を必ず入れる | 他人のアドレスを入れられても、控えはその人に届くため | — |
| 「担当者から7日以内」は、完了ページと控えの本文（`home/templates/home/join_done.html` と `home/forms.py`）の両方に書いてある。**片方だけ直さない** | 案内が食い違うため | — |
| 申し込みページの「お預かりする情報について」に、アドレスを招待にも使うことと、アクセス制限の方針を出す。**閾値や期間の数値は出さない** | ぎりぎりを狙われるため | — |

## WG への参加（`/wg/<id>/join/`）

WG 一覧の各カードの「WG に参加」から、**クラブのメンバー**（Classroom のクラブのクラスにいる人）だけが、
自分で WG の Chat スペースと GitHub の WG のチームに入れる。運営の手作業は要らない。大学のアドレスを
入れる → 確認のメールのリンクを開く → ボタンを押して Chat スペースに追加 → GitHub でログインして
チームに追加、の順に進む。会員の情報はサイトに持たない（名簿は Classroom、WG の参加状態は GitHub の
チームと Chat スペースのメンバーで分かる）。

仕組み（流れ・アドレスの持ち方・Google と GitHub の権限・失敗したときの振る舞い）は
[docs/design.md](docs/design.md) の 3 章。

参加したところが、メンバーが**開発の手順に初めて触れる**ところになる。確認のメールと結果の画面の
両方から `/guide/`（WG 立ち上げガイド）へ案内し、「次はパソコンの準備（資料 02）」と書いておく。
資料は `static/guide/` にあり、直し方は [docs/deck/README.md](docs/deck/README.md)。

### 表示の条件

「WG に参加」は、次の両方がそろったカードにだけ出る。どちらかが欠けていれば、これまでどおり
（準備中の WG は「参加する」＝クラブの参加案内）。

1. 8 つの設定がすべて入っている（`wgjoin.config.is_enabled`。一覧は「[環境変数（本番）](#環境変数本番)」）
2. WG 紹介の「GitHub のチーム」に `wg-<名前>` が入っている（編集画面の WG紹介）

WG 紹介の「Chat スペース」は任意。入っている WG だけ、参加の手続きでそのスペースに本人を追加する。
空欄なら、クラブのクラスの「授業」にあるリンクから本人が入る。

### 準備

- 最初に一度だけ：Google Cloud の OAuth クライアント・運営（クラスの先生）の許可・GitHub App を作る。
  手順は [deploy.txt](deploy.txt) の「WG への参加」の「初回のみ」。
- WG ごと：チーム `wg-<名前>` を作って WG のリポジトリに Write で付け（WG 立ち上げガイドの資料 01）、
  Chat スペースを作って、WG 紹介に両方を入れる。手順は deploy.txt の「Chat スペースの準備」。
  人をチームとスペースに入れるのはこの仕組みが行う。
- 手元で試すときは、設定を `.env` に書く（鍵は1行にして改行を `\n` と書く）。確認のメールは、メールの
  認証情報がなければ runserver のログに出る（リンクもそこに出る）。

## 編集画面（`/edit/`）

掲載内容を編集する画面。**ログイン必須**。未ログインで URL を直接叩くと
`/edit/login/?next=...` に飛ばされる。公開サイトとは別レイアウト
（`edit/base.html`）で、公開ナビも持たず、公開ページとの相互リンクもない。

保護は hirahira_room と同じ二段構え。

1. `LoginRequiredMiddleware`（`config/settings_common.py`）で**全ビューを既定ログイン必須**にする。
   公開ページ（`home/views.py`）・WG への参加（`wgjoin/views.py`）・ログイン不要のサブアプリ
   （`works/countdown`・`works/fe`）のビューだけ `login_not_required` を付けて除外している。
   新しい編集画面を足したときに保護を書き忘れても、素通りにはならない。
2. 各編集ビューは `edit.views.EditorMixin`（＝`LoginRequiredMixin`）も継承している。

静的ファイルは保護の対象外（本番は WhiteNoise が認証より前に配信し、開発は runserver が
ミドルウェアを通さずに返す）。公開ページの見た目は未ログインでも崩れない。

編集した内容がそのまま公開ページに出る。反映のされ方は次のとおり。

| 編集対象 | モデル | 公開側の出かた |
|---|---|---|
| お知らせ | `news.News` | TOP に公開中の新しい順で5件（件数は `home.views.IndexView.news_limit`）、`/news/` に全件。掲載日が未来のものは出ないので予約投稿にできる |
| WG紹介 | `catalog.Wg` | `/wg/` に表示順で並ぶ。「準備中」のカードは参加ボタンだけを出す |
| 成果物紹介 | `catalog.Work` | `/works/` に表示順で並ぶ |

TOP の活動サマリの件数も連動する。

- 「活動中のWG」＝ 公開中かつ状態が「活動中」の WG の数
- 「公開済み成果物」＝ 公開中の成果物の数
- 「CC BY 成果物ライセンス」は固定表示（テンプレート直書き）

いずれも `is_published` を外すと下書き扱いになり、一覧にも件数にも出ない。
WG の「Webアプリの URL」や成果物の「公開先の URL」が空欄なら `/coming-soon/` に繋ぐ。

編集する項目を増やすときは、`catalog` と同じ作りでモデル・フォーム・画面を足し、
`edit/templates/edit/base.html` のナビにリンクを追加する。

アカウントは会員登録のような入口を持たず、`createsuperuser` で作る。

```bash
python manage.py createsuperuser --settings=config.settings_dev
```

## 管理者と通知

**運営の連絡先は `edit.Administrator`（管理者テーブル）にだけ置く。** 設定ファイルにもテンプレートにも
書かない。担当者が代わったときに追いきれなくなるうえ、HTML に個人のアカウントが残るため。
編集は admin（`/admin/` → 管理者）から。

**個人の大学アカウントは、公開ページにも、このリポジトリにも書かない。** ローカル部が学籍番号
そのもので、公開すると特定の学生の学籍番号が恒久的に晒される。**リポジトリは公開なので、コードや
テストに書けば検索でき、フォークやアーカイブにも残る。** 実際の受信箱は App Service の設定
（`JOIN_NOTIFY_EMAIL`）と管理者テーブルで持ち、コードには役割アドレス（`contact@funitclub.org`）だけを置く。

> **転送の設定が前提。** `contact@funitclub.org` はメール転送サービス（ImprovMX など）に MX レコードを
> 向けて受け取る。設定しないと届かないので、公開前に必ず疎通を確かめること。手順は
> [deploy.txt](deploy.txt) の「メール送信」の「問い合わせ先（受信）の設定」。

運営に届く通知（IP の遮断・ログイン失敗・エラー・シークレットの期限など）の一覧、宛先の決め方と
予備、通数の上限は [docs/design.md](docs/design.md) の 1-2〜1-4。

> **SMTP のシークレットを更新したら `EMAIL_SECRET_EXPIRES_ON` も必ず直すこと。** 忘れると期限の通知が
> 嘘になる。手順は deploy.txt の「メール送信」。

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

## サブアプリ（`works/`・`wg/`）

ホームページの中で動く小さなアプリ。成果物紹介・WG 紹介のリンクから辿る。

| 置き場所 | 中身 | 通行証が無いときに送り返す先 |
|---|---|---|
| `works/<名前>/` | 公表した成果物（[countdown](works/countdown/README.md)・[fe](works/fe/README.md)）。このリポジトリに入っている | `/works/` |
| `wg/<名前>/` | WG が作っている途中のアプリと活動ページ。デプロイのときだけ WG のリポジトリから取り込む（手元では空） | `/wg/` |

### 組み込み方

- `config/subapps.py` が置かれているフォルダーを見つけ、`INSTALLED_APPS`・URL・`GATE_BACK` に
  自動で組み込む。**フォルダー名がそのまま URL と名前空間**（`works/countdown` → `/countdown/`、
  `wg/protein` → `/protein/`）で、アプリの `urls.py` の `app_name` も同じ名前にする。
  `config/urls.py` や設定ファイルに手で足す必要はない。
- URL を入れ子にしたいときは、アプリの中に `.url`（1 行）を置く。WG のアプリは `wg-apps.yml` の
  `take` に `{app, url}` と書けば取り込みのときに置かれる（`{app: welfare_activity, url: welfare/activity}`
  → `/welfare/activity/`）。
- **フォルダー名は Django のアプリ名になるので、WG をまたいで重ねない。** 同じ名前のアプリが 2 つ
  あると、テンプレートと URL の名前空間がぶつかる。
- 公表できる形になったら `wg/` から `works/` へ移す（URL は変わらない）。移すときは `apps.py` に
  `label` を明示しておく。アプリの呼び名が変わらないので、マイグレーションも DB もそのまま使える。
- 一覧から辿れるようにするには、編集画面の WG 紹介・成果物紹介にアプリの URL を入れる
  （テンプレートの修正は不要。空欄のあいだは `/coming-soon/` に流れる）。

### WG のアプリの取り込み

**WG のアプリは、このリポジトリに入れない。** WG のリポジトリ（非公開）のまま置いておき、
デプロイのときだけ取り込んで App Service に載せる（`wg-apps.yml` と `.github/workflows/deploy.yml`）。
このリポジトリは公開なので、この形でないと WG のソースが公開されてしまう。

- 取り込むのはアプリのフォルダーだけで、WG 側の `config/` や `manage.py` は入れない。1 つの
  リポジトリに複数のアプリがあるときは `take` に並べる（並べなかったものは本番に載らない）。
- WG の活動ページ（紹介・構想資料・チケットの一覧）は `<WG>_activity` を `/<WG>/activity/` に置く
  （[funITclub/claude-plugins](https://github.com/funITclub/claude-plugins) の wg-activity スキル）。
  チケットは会員が WG のリポジトリの Issue（と org の Project）に GitHub で直接書き、活動ページは
  それを GitHub App（funitclub-wg-join、Issues と Projects の読み取り）で読んで出すだけ。題名と
  本文は一般公開する（担当者・コメント・画像は出さない）。手順は [deploy.txt](deploy.txt) の
  「WG の活動ページのチケット」。
  WG 一覧のカードには、編集画面で追加リンク「活動ページ」として登録する。`/<WG>/` は WG が作る
  Web アプリのために空けておく。
- WG が `requirements.txt` に足したものは本番の分に合流する。同じパッケージを両方が指定していたら
  **本番（homepage）の版を使う**（`.github/merge-requirements.py`）。1 つのアプリとして動かすので、
  WG ごとに違う版は入れられない。
- 読み取りは GitHub App（Contents: Read）の短命トークン。`wg-apps.yml` が空なら取り込みごと
  飛ばすので、App が無くてもデプロイできる。
- zip デプロイは丸ごと置き換えなので、**どこから起動されても全部を組み立て直す**。WG のリポジトリの
  main が更新されたら、そちらの Actions から `repository_dispatch`（`wg-app-updated`）でこのデプロイを呼ぶ。

載せる手順（GitHub App の作り方・`wg-apps.yml` の書き方・確認）は [deploy.txt](deploy.txt) の
「WG のアプリを載せる」。

### 通行証（一覧から辿ったときだけ開く）

サブアプリは、**ホームページの一覧から辿ったときだけ開く**（`config/gate.py`）。一覧のリンクに
期限つきの通行証（署名、既定 10 分）を付け、アプリの入口で検証したらセッションに印を付けて、
通行証を落とした URL へ転送する。印も通行証も無ければ一覧へ送り返す。Referer は見ない
（消される・偽装できるため）。守りではなく導線の仕掛けで、一度入った人のその後は縛らない。

- 通行証は上の段で 1 枚取れば下の段も通る（`/welfare/` の通行証で `/welfare/activity/` も開ける）。
- `GATE_BACK`（通行証の要る URL → 送り返す先）は `config/subapps.py` が作る。`GATE_EXEMPT`（素通し）は
  `config/settings_common.py` に手で並べる。
- 素通しに並べてよいのは、**別の鍵で守られている入口だけ**（メールの署名付きリンク、
  `COUNTDOWN_NOTIFY_TOKEN`、編集画面のログイン）。素通しでは印を付けないので、メールのリンクから
  アプリ全体に入ることはできない。
- サブアプリ自身のテストでは、`setUpModule` で `GATE_BACK={}` にして外す。

## セットアップ

**開発環境は VS Code ＋ Docker Desktop（Dev Container）で揃える。** 手順は
[docs/development.md](docs/development.md)。コンテナを作ると、パッケージの導入・`.env` の用意・`migrate`・
`createcachetable` まで済む。

コンテナを使わずに手元の Python（リポジトリ直下の `venv`）で動かす手順、メールを実際に送って確かめる
手順、運営が手元に入れるもの（Azure CLI・GitHub CLI・資料の道具・Claude Code）は、同じ文書の
「14. 運営の作業に使うものを入れる」。

## 開発と本番の切り替え

hirahira_room と同じ構成。設定を3ファイルに分け、**既定は本番**。

| | 開発（ローカル） | 本番（Azure App Service） |
|---|---|---|
| 設定モジュール | `config.settings_dev` | `config.settings`（既定） |
| 指定方法 | 毎回 `--settings=config.settings_dev` を付ける（Dev Container の中では不要） | 指定不要（`manage.py` と `wsgi.py` の既定） |
| DEBUG | `True` | 既定 `False`。環境変数 `DEBUG=True` で一時的に有効化できる |
| DB | SQLite（`DB_HOST` を渡したときだけ PostgreSQL） | PostgreSQL（funITclub 専用DB） |
| 静的ファイル | runserver が配信 | WhiteNoise（圧縮＋ハッシュ付き） |
| メール | ACS の SMTP リレー（`smtp.azurecomm.net`。`.env` の `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD`）。未設定ならコンソール出力 | ACS の SMTP リレー（`smtp.azurecomm.net`。パスワードは Key Vault 参照） |
| Cookie | 通常 | `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` が True |
| ログ | DEBUG レベル・詳細フォーマット | INFO レベル |

共通の設定は `config/settings_common.py` に置き、両方がこれを読み込む。

**`--settings` を付け忘れると本番設定（PostgreSQL）で動いて DB 接続に失敗する。**
ローカルで `manage.py` を叩くときは毎回付けること。

**main に push すると自動でデプロイされる**（[.github/workflows/deploy.yml](.github/workflows/deploy.yml)）。
本番の `migrate` と `createcachetable` はアプリの起動時に [startup.sh](startup.sh) が流す。
migrate が失敗するとアプリは起動せず、デプロイも失敗扱いになる。
デプロイと本番環境の作成手順は [deploy.txt](deploy.txt) にまとめてある。

壊れたまま本番に出さないよう、デプロイは 2 段で確かめる（App Service は B1 で検証スロットが使えないため）。

- **出す前**：`.github/workflows/test.yml` がテストと、使い捨ての PostgreSQL への `migrate` を流す
  （起動時に落ちる失敗をここで捕まえる）。WG のアプリを取り込んだあとも、`check`・homepage のテスト・
  PostgreSQL への `migrate` をもう一度流す。**WG のアプリ自身のテストはここでは流さない**（WG の
  リポジトリでは単独のサイトとして書かれていて、通行証やログイン必須を前提にしていないため落ちる）。
  中身の確認は WG のリポジトリの CI の仕事。
- **出した後**：`https://funitclub.org/` の応答を確かめ、返らなければ**直前に通った zip に戻す**
  （成果物 `funitclub-deploy` として 30 日残している）。

## データベース

PostgreSQL サーバーは hirahira_room と同じものを使うが、**データベースは funITclub 専用のものを
分ける**（`DB_NAME` で指定）。hirahira_room の共有DBには一切触らないので、こちらは自由に
`migrate` してよい。接続情報はリポジトリに持たず、すべて環境変数（App Service のアプリケーション
設定）から読む。既定値は持たないので、未設定なら接続しない。

例外は1つだけ。運営が手で流す `manage.py fe_pull_learner` は、hirahira_room のデータベースを
**読み取り専用で**開き、運営の ID の FE の成績を読む（`works/fe/README.md` の「hirahira_room から
運営の成績を持ってくる」）。書き込みはしない。

ローカル（`config/settings_dev.py`）は SQLite。`DB_HOST` を渡したときだけ PostgreSQL に切り替わる。
ただし hirahira-db は公開アクセスが無効（VNet 内からのみ）なので、手元から直接は繋がらない。

> **注意: hirahira_room の共有DBに対して `migrate` を実行しないこと。**
> `DB_NAME` が funITclub 専用DBを指していることを確認してから実行する。
> なおテーブル名はすべて `funitclub_` で始まる名前に固定してあり（`funitclub_news`・
> `funitclub_wg`・`funitclub_fe_question` など。各モデルの `db_table`）、万一DBを取り違えても
> 既存テーブルとは衝突しないようにしてある。サブアプリのモデルを足すときも同じようにする。

本番DBの初期化（専用DBの作成 → 環境変数 → migrate）は [deploy.txt](deploy.txt) の
「初回のみ」を参照。

## 環境変数（本番）

Azure App Service（`funITclub`）のアプリケーション設定。hirahira-room と同じ構成。
「設定済み」は 2026-10-21 に App Service の設定名を一覧して確かめたもの（値は見ていない）。
「Key Vault」は値を `@Microsoft.KeyVault(...)` の参照で入れているもの（`funitclub-kv`）。

| 変数 | 本番 | 用途 |
|---|---|---|
| `SECRET_KEY` | 設定済み | 本番の秘密鍵。確認のリンクの暗号化と countdown の通知先の暗号化の鍵もここから作る |
| `SECRET_KEY_FALLBACKS` | 未設定 | 任意。`SECRET_KEY` を替えるとき、前の値を入れる（カンマ区切り）。下の注意を参照 |
| `DB_NAME` | 設定済み | funITclub 専用データベース名（`funitclub`）。hirahira_room の共有DBを指さないこと |
| `DB_USER` / `DB_PASSWORD` / `DB_HOST` | 設定済み | PostgreSQL の接続情報（hirahira-room と同じ値） |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | 設定済み | `True`。デプロイ時に pip install と collectstatic を走らせる |
| `WEBSITE_HOSTNAME` | Azure が自動 | CSRF_TRUSTED_ORIGINS に反映 |
| `WEBSITE_HTTPLOGGING_RETENTION_DAYS` | 設定済み | App Service の HTTP ログを残す日数（Azure の設定。コードは読まない） |
| `EMAIL_HOST_USER` | 設定済み | ACS の SMTP ユーザー名。未設定だと送信できない |
| `EMAIL_HOST_PASSWORD` | Key Vault | 紐づけた Entra アプリのクライアント シークレット |
| `EMAIL_HOST` | 未設定（既定） | 任意。SMTP サーバー。既定は `smtp.azurecomm.net` |
| `EMAIL_SECRET_EXPIRES_ON` | 設定済み | シークレットの期限（`YYYY-MM-DD`）。更新時に必ず直す |
| `JOIN_FROM_EMAIL` | 未設定（既定） | 任意。差出人アドレス。既定は `no-reply@funitclub.org` |
| `JOIN_NOTIFY_EMAIL` | 設定済み | 管理者テーブルが空のときの予備の宛先（通知用） |
| `PUBLIC_CONTACT_EMAIL` | 未設定（既定） | 任意。同じく予備の公開問い合わせ先。既定は `contact@funitclub.org` |
| `CLUB_CLASSROOM_COURSE` | 設定済み | クラブの Classroom のクラス。ここにいる人をメンバーとみなす |
| `GOOGLE_OAUTH_CLIENT_ID` | 設定済み | Google の OAuth クライアント |
| `GOOGLE_OAUTH_CLIENT_SECRET` / `GOOGLE_OAUTH_REFRESH_TOKEN` | Key Vault | OAuth クライアントのシークレットと、運営（クラスの先生）の許可 |
| `GITHUB_APP_ID` / `GITHUB_APP_CLIENT_ID` | 設定済み | GitHub App（funitclub-wg-join）。WG への参加と、WG の活動ページのチケットの読み取り |
| `GITHUB_APP_CLIENT_SECRET` / `GITHUB_APP_PRIVATE_KEY` | Key Vault | 同じ App の Client secret と秘密鍵 |
| `GITHUB_ORG` | 未設定（既定） | 任意。既定は `funITclub` |
| `COUNTDOWN_NOTIFY_TOKEN` | 設定済み | countdown の毎日0時の送信の合言葉。GitHub の環境 production のシークレットと同じ値（[deploy.txt](deploy.txt) の「カウントダウンのメール通知」） |
| `IP_BLOCK_ENABLED` / `IP_BLOCK_EXEMPT` | 未設定 | 任意。IP遮断の停止・除外（ロックアウトからの復旧用。済んだら消す） |
| `DEBUG` | 未設定 | 任意。`True` のときだけ本番でも DEBUG が有効になる。切り分け用で、常設しないこと |
| `FE_SOURCE_DB` | 未設定 | 任意。`fe_pull_learner` の `--source-db` を省くときの hirahira_room の DB 名。SSH で流すときにその場で渡してもよい |

WG への参加の 8 つ（`CLUB_CLASSROOM_COURSE`・`GOOGLE_OAUTH_*`・`GITHUB_APP_*`）がそろうまで、「WG に参加」は
出ない（作り方は「[WG への参加](#wg-への参加wgidjoin)」の準備）。

次の変数は**開発（`config/settings_dev.py`）だけ**が読む。本番では入れても効かない。

| 変数 | 用途 |
|---|---|
| `EXTRA_ALLOWED_HOSTS` | 手元のサーバーを別の名前で開くとき（カンマ区切り） |
| `CSRF_TRUSTED_ORIGINS` | 同じく、フォームを送るときに信頼するオリジン |
| `SITE_URL` | countdown のメールに書くリンクの頭。既定は `http://localhost:8010`。本番は `https://funitclub.org` に固定 |

> **`SECRET_KEY` を替えるときは、前の値を `SECRET_KEY_FALLBACKS` に入れてから替える。**
> 署名（確認のリンク・セッション）と暗号化（WG への参加のアドレス・countdown の通知先）は、
> 前の鍵でも読める。入れずに替えると countdown の通知先が読めなくなり、全員が未登録の扱いになる。
> 通知先は読み直しても暗号化し直さないので、`SECRET_KEY_FALLBACKS` は**消さずに残しておく**
> （確認のリンクやセッションだけなら 1 時間〜2 週間で前の鍵は要らなくなる）。

設定の一覧（名前と Key Vault 参照かどうか。値は出さない）は次で見られる。

```bash
az webapp config appsettings list --name funITclub \
  --query "[].{name:name, keyVault:starts_with(value || '', '@Microsoft.KeyVault')}" -o table
```

`DJANGO_SETTINGS_MODULE` は不要（`manage.py` と `wsgi.py` の既定が `config.settings`）。

## 今後

### WG への参加：保留中のアイデア

2026-09-19 に検討して保留にしたもの。始めるときはここから。
（同じときに保留にした「Chat スペースへの自動登録」は 2026-10-20 に入れた。）

**WG ごとに Classroom でも分ける**
いまは WG をクラブのクラスの「授業」のトピックにしていて、クラスの全員に見える。
WG のメンバーだけに見せたいときの案。

- (a) WG ごとに別のクラスを作り、「WG に参加」のときにクラスコードで本人をそのクラスに登録する
  （本人の権限で `courses.students.create` に `enrollmentCode` を付ける方法。一度作りかけて外した）
- (b) クラブのクラスのまま、投稿ごとに対象の生徒を選ぶ。人が入るたびに直す必要があり、自動化は難しい

### WG のアプリを別に動かすとき

WG の成果物は Web ページ（動いているアプリ）だけで、ソースコードは成果物に含めない。
WG のリポジトリは完成後も非公開のまま。WG のアプリを App Service の外で動かす仕組み
（Container Apps と ghcr.io の構成案）を作るときは、非公開のリポジトリから作った
**非公開のイメージ**を Azure 側で取り出せるようにする（イメージを取るための認証が要る）。

### セキュリティの設定

`manage.py check --deploy` は `SECURE_HSTS_SECONDS` と `SECURE_SSL_REDIRECT` の未設定を
警告する（着手前からの状態）。ログイン機能が入ったので、いずれ対応しておきたい。
