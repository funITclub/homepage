# 技術設計：メール送信・参加の申し込み・WG への参加

公開サイトのうち、外部のサービス（Azure Communication Services・Google・GitHub）とつながる
3 つの仕組みの設計をまとめる。どう組み立ててあるか・なぜそうしたか・失敗したらどうなるかを書く。

- 作り方・設定の手順は [deploy.txt](../deploy.txt)、画面ごとの説明と決まりごとは [README.md](../README.md)
- 2026-10-21 時点のコードから書いた。コードと食い違ったらコードが正しい。直したらこの文書も直す

3 つに共通する方針は次のとおり。

| 方針 | 中身 |
|---|---|
| 会員の情報を持たない | 名簿は Classroom のクラブのクラス、WG の参加状態は GitHub のチームと Chat スペースのメンバー。サイトの DB・セッション・ログにアドレスを残さない |
| 運営に介入しない | 自動で済むときは運営に何も知らせない。手作業が要るとき（失敗したとき）だけ知らせる |
| 付加機能で本筋を止めない | 数える・遮断する・通知するといった機能が壊れても、申し込みと表示は通す（fail open） |
| 第三者に文章を届けさせない | 入力はメールアドレスだけ。メールの本文に入力された文字を載せない |

---

## 1. メール送信の仕組み

### 1-1. 経路

```
Django（EmailMessage）
  │  SMTP backend（django.core.mail.backends.smtp）
  │  smtp.azurecomm.net:587 / STARTTLS / タイムアウト 20 秒
  ▼
Azure Communication Services（funitclub-comm）── リンク済みドメイン funitclub.org
  │  SMTP 認証：ユーザー名＝ACS の SMTP ユーザー名（Entra アプリ funitclub-smtp に紐づく）
  │            パスワード＝その Entra アプリのクライアント シークレット
  ▼
受信者（差出人 fun IT club <no-reply@funitclub.org>。SPF・DKIM・DMARC が通る）
```

| 部品 | 設計 |
|---|---|
| 差出人 | `settings.DEFAULT_FROM_EMAIL`＝`fun IT club <no-reply@funitclub.org>`（`JOIN_FROM_EMAIL` で変えられる）。500 の通知（`SERVER_EMAIL`）も同じ |
| SMTP の認証 | `EMAIL_HOST_USER`（SMTP ユーザー名）と `EMAIL_HOST_PASSWORD`（シークレット）。**差出人アドレスとは別物**。シークレットは Key Vault（`funitclub-kv`）に置き、App Service の設定から参照する。読めるのは App Service のマネージド ID だけ |
| Entra アプリの権限 | カスタムロール「funITclub Email Sender」。ACS のメール送信に要る 3 操作だけで、組み込みの所有者ロールは外してある |
| ドメインの認証 | SPF（`include:spf.protection.outlook.com -all`）・DKIM（selector1/2 の CNAME）・DMARC（`p=none`、レポートは contact@） |
| 受信 | ACS は送信専用。公開の問い合わせ先 `contact@funitclub.org` は、MX をメール転送サービスに向けて運営の受信箱へ転送する |

**大学のアカウント（bukkyo-u.ac.jp）からは送らない。** 大学の Google Workspace は 2 段階認証を
許可しておらず、アプリ パスワードを作れない。Google は 2 段階認証なしの SMTP 認証を廃止したので、
大学のアドレスから SMTP で送る経路がない。受信には問題がないので、返信先（Reply-To）と通知先は
大学のアドレスのままにしている。

### 1-2. サイトが送るメール

| メール | 宛先 | Reply-To | 送るところ | 送るとき |
|---|---|---|---|---|
| 参加の申し込みの控え | 申込者 | 公開の問い合わせ先 | `home/forms.py` `JoinForm.send_email` | クラスに招待できなかった・招待を使っていない・もうクラスにいる。**招待できたときは送らない** |
| 参加の申し込みの通知 | 運営 | 申込者 | 同上 | 招待できなかった・招待を使っていない・お知らせの Chat スペースに追加できなかった（手作業が要る）ときだけ |
| WG への参加の確認 | 入力されたアドレス | 公開の問い合わせ先 | `wgjoin/mail.py` `send_link` | 名簿にいた |
| WG への参加の「確認できませんでした」 | 入力されたアドレス | 公開の問い合わせ先 | `wgjoin/mail.py` `send_not_member` | 名簿にいなかった |
| Chat スペースに追加できなかった | 運営 | — | `wgjoin/mail.py` `send_chat_failed` | Chat への追加に失敗したときだけ。アドレスはこのメールにだけ載せる |
| IP を遮断した | 運営 | — | `home/notifications.py` | 遮断のたび（1 時間に 5 通まで） |
| ログインの失敗が続いた | 運営 | — | `edit/signals.py` | 同じ IP で 10 分に 5 回を超えたとき 1 回（`LOGIN_FAILURE_RULE`）。**IP は遮断しない**（正規の運営が打ち間違えて締め出されると、復旧の手段を失うため。判断は人に任せる） |
| エラー（500・ERROR のログ） | 運営 | — | `edit/log_handlers.py` | 本番だけ。1 時間に 10 通まで |
| SMTP のシークレットの期限 | 運営 | — | `edit/checks.py` | 30・14・7・1 日前と失効後に 1 回ずつ |
| countdown の確認・解除・毎日の通知 | 登録したアドレス | — | `works/countdown/notify.py` | 本人が登録を頼んだとき・毎日 0 時 |

サイトからは送らないが、手続きの中で届くメールもある。Classroom の招待（Google が送る）と
GitHub の org への招待（GitHub が送る）。

### 1-3. 宛先の決め方

運営の連絡先は**管理者テーブル（`edit.Administrator`）にだけ**置き、設定ファイルやテンプレートには書かない。

| 用途 | 関数 | 引くもの | テーブルを読めないとき |
|---|---|---|---|
| 運営への通知 | `edit.models.notification_emails()` | 有効かつ「通知を受け取る」の全員 | `JOIN_NOTIFY_EMAIL`（未設定なら `PUBLIC_CONTACT_EMAIL`） |
| 公開する問い合わせ先・Reply-To | `edit.models.public_contact_email()` | 「公開ページの問い合わせ先にする」の先頭 1 件 | `PUBLIC_CONTACT_EMAIL`（`contact@funitclub.org`） |

- 管理者テーブルの編集は admin（`/admin/` → 管理者）から。最初の 1 件（公開の問い合わせ先）は
  マイグレーション（`edit/migrations/0002_seed_administrator.py`）で入る。
- テンプレートからは `{{ public_contact }}` で参照する（`edit/context_processors.py`）。アドレスを HTML に
  書かないので、担当者が代わってもテーブルを直すだけで全ページに反映される。
- 公開の問い合わせ先（役割アドレス）は転送で運営の受信箱に届くので、通知の宛先には入れない
  （同じ受信箱に二重に届くため）。

公開側の予備を `JOIN_NOTIFY_EMAIL` に**倒さない**のが要点。運営の受信箱は個人の大学アドレスで、
ローカル部が学籍番号なので、障害のときに公開ページへ出てはいけない。

### 1-4. シークレットの期限

SMTP の認証に使う Entra アプリのクライアント シークレットには期限がある（いまは 2028-08-19）。
切れると申し込みの控えも運営への通知も止まるが、「申し込みが来ない」状態と区別がつかず気づけない。
そこで期限日を `EMAIL_SECRET_EXPIRES_ON` に持ち、30・14・7・1 日前と失効後に運営へ知らせる。

- 点検は 1 日 1 回、その日の最初のリクエストのついでに走る（`config.middleware.DailyCheckMiddleware` →
  `edit/checks.py`）。App Service に常設のスケジューラがないため。手で流すなら `manage.py check_secret_expiry`。
- 通知の本文に更新の手順を書いてあるので、受け取った人はそれを読めば対応できる。
- **シークレットを更新したら `EMAIL_SECRET_EXPIRES_ON` も必ず直す。** 忘れると通知が嘘になる。
- この仕組みはメールが送れる状態でしか働かない。

### 1-5. 失敗したとき

| 場面 | 振る舞い |
|---|---|
| 申し込み・WG への参加でメールを送れない | 500 にしない。申し込みはフォームにエラーを出して送り直してもらう。WG への参加はエラーの画面（502）を出す。ログには例外の種類だけを残す（例外の文言に宛先が入ることがあるため） |
| 運営への通知を送れない | `edit.notify.notify_admins` が例外を握り、ログだけ残す。呼び出し元は止めない |
| 通知が続く | 種類ごとに 1 時間あたりの通数を数え（DB キャッシュ）、超えたら送らない。数えられないときは送る（異常のときに黙るより、うるさいほうがよい） |
| ERROR のログ | 本番ではルートのロガーに `DbAdminEmailHandler` を付けてあり、どのアプリ（`works/` の成果物や取り込んだ WG のアプリも）の ERROR も運営に届く。アプリを足しても設定は要らない。この仕組みが「失敗したら運営に知らせる」の土台 |
| ACS が止まる・シークレットが切れる | メールで知らせる仕組みは全部止まる。ACS の障害は検知しない（Azure Monitor は使っていない） |

### 1-6. 開発環境とテスト

- `config/settings_dev.py` は、`.env` に `EMAIL_HOST_USER` と `EMAIL_HOST_PASSWORD` があれば本番と同じ ACS から
  **本当に送る**。なければ console backend（runserver のログに出す）。
- テスト（`manage.py test`）は Django がメモリの backend に差し替えるので、送られない。

---

## 2. 参加の申し込みの仕組み（クラブへの入会）

### 2-1. 流れ

```
/join/（案内）→ /join/apply/（フォーム：大学のアドレスだけ）
  │ POST
  ▼
JoinApplyView.form_valid
  1. 連続送信を数える（同じ IP が多すぎたら、その IP を遮断する）
  2. クラブのクラスに招待する（設定がそろっているとき）
       名簿にいる？ ── いる → MEMBER
                    └ いない → invitations.create（生徒）→ INVITED（もう招待済みの 409 も INVITED）
       通信・権限の失敗 → 'failed'（ERROR を記録 → 運営に通知）
  3. お知らせの Chat スペースに追加する（CLUB_CHAT_SPACE があるとき。招待の結果によらず試す）
       spaces.members.create（もういる 409 も成功）。失敗 → ERROR を記録 → 運営に通知
  4. メールを送る（申込者には INVITED のときは送らない。運営には手作業が要るときだけ）
  5. /join/apply/done/ へリダイレクト（フォームを置かない完了ページ）
```

### 2-2. 部品

| 部品 | 設計 |
|---|---|
| `home.forms.JoinForm` | 項目は `email` だけ。`@bukkyo-u.ac.jp` 以外は弾く（`JOIN_ALLOWED_EMAIL_DOMAIN`）。モデルを持たず、DB に書かない |
| `home.views.JoinApplyView` | 上の 1〜4。申し込みの結果（招待できたか）は画面に出さず、メールで本人にだけ伝える |
| `home.views.JoinDoneView` | 完了ページ。**フォームも申し込みページへのリンクも置かない**（押し直して連続送信の遮断に当たらないように）。直接開かれても同じ内容 |
| `wgjoin.google.invite_to_club` | Classroom への招待。WG への参加と同じ運営の許可を使う（3-4） |
| `wgjoin.config.can_invite_to_club` | `CLUB_CLASSROOM_COURSE` と `GOOGLE_OAUTH_*` の 3 つがそろっていれば招待する。欠けていれば招待せず、運営が手作業で案内する |
| `wgjoin.config.can_add_to_club_chat` | `CLUB_CHAT_SPACE`（お知らせのスペース）と `GOOGLE_OAUTH_*` の 3 つがそろっていれば追加する。追加は WG と同じ `wgjoin.google.add_to_chat_space` |

### 2-3. 招待の結果ごとの振る舞い

| 結果 | 申込者に届くもの | 運営への通知 | ログ |
|---|---|---|---|
| INVITED（招待した・もう招待済み） | Google の招待メールだけ | なし | INFO |
| MEMBER（もうクラスにいる） | 控え（「すでに登録されています」とクラスのリンク） | なし | INFO |
| failed（通信・権限の失敗） | 控え（「担当者から 7 日以内に」） | 申し込みの通知と ERROR の通知 | ERROR |
| 招待を使っていない（設定が欠けている） | 控え（「担当者から 7 日以内に」） | 申し込みの通知 | INFO |

お知らせの Chat スペースへの追加は、上とは別に結果を見る。追加できたときは何も足さない。失敗したときは、
運営への申し込みの通知に「Chat スペースに追加できませんでした」の行を足す（招待の失敗と重なれば 1 通にまとめる）。
申込者に送るものは招待の結果だけで決まる。

本人の確認はしない（アドレスの持ち主か確かめない）。他人のアドレスを入れられても、クラスには招待が届くだけで、
本人が Classroom で「参加」を押さない限りクラスには入らない。招待がないと WG への参加の名簿確認（3 章）も
通らないので、なりすましはそこで止まる。

お知らせの Chat スペースは招待ではなく、その場でメンバーにする（大学の Workspace の中の人なので）。
他人のアドレスを入れると、その人がお知らせのスペースに入る。お知らせには運営・各 WG・メンバーの投稿が
並ぶが、スペースは Workspace の中に公開してあり（大学の人なら誰でも入れる）、見えるものは変わらない。
本人はいつでも抜けられる。入れられる数は連続送信の遮断（2-4）で
抑えている。

### 2-4. 悪用への備え（連続送信と IP の遮断）

| 部品 | 設計 |
|---|---|
| 数え方 | `detect_and_block_burst_submissions`。IP ごとに `(件数, 窓の開始時刻)` を DB キャッシュ（`funitclub_cache`）に置き、`JOIN_BURST_RULES`＝10 分に 3 件／1 時間に 10 件を超えたら遮断する。worker をまたいで数えるため、ローカルメモリではなく DB に置く。超えた送信そのものは受け付ける |
| 遮断 | `home.BlockedIp` に記録する。期間は 24 時間 → 7 日 → 恒久（`IP_BLOCK_DURATIONS`）。期限が切れた行も消さず、次に遮断したとき回数を引き継ぐ |
| 止める場所 | `config.middleware.BlockedIpMiddleware` が全リクエストを 403 にする（公開ページ・編集画面・静的ファイルも）。403 の画面（`home/templates/home/blocked.html`）は連絡先と「共有回線では他の方の操作が原因の場合がある」旨を出し、CSS を埋め込んだ 1 枚で返す（静的ファイルも 403 になるため。外部ファイルを読ませないこと）。遮断リストは 60 秒キャッシュするので、解除の反映は最大 60 秒遅れる |
| IP の取り方 | `home.netutils.client_ip`。`X-Forwarded-For` の**右端**（Azure の front end が付けた値）。左端は詐称できるので信じない |
| 期間を延ばしていく理由 | IP は個人の持ち物ではない。構内の回線や携帯の CGNAT では多数の人が同じ IP を使い、動的な IP は時間とともに別の人に渡る。初回から恒久にすると無関係な人を締め出し続け、しかもこちらは気づけない（遮断された人は問い合わせフォームにも来られない）。まず短く切って自動で解き、繰り返す相手だけ恒久にする |
| 解除 | admin（`/admin/` → 遮断IP → 「今すぐ解除する」） |
| 逃げ道 | 自分の IP を遮断すると admin にも入れなくなる。`IP_BLOCK_EXEMPT`（除外。遮断リストより優先）と `IP_BLOCK_ENABLED=False`（止める）を用意し、どちらも App Service の設定だけで DB を触らずに戻せる |
| 知らせ | 遮断したら運営に通知する（遮断された人は問い合わせフォームにも来られないため）。IP を変えながら来られても溢れないよう、1 時間に 5 通まで（`IP_BLOCK_NOTIFY_MAX_PER_HOUR`） |
| 掲示 | 申し込みページに、入力内容の扱いとアクセス制限の**方針だけ**を出す。閾値や期間の数値は出さない（ぎりぎりを狙われるため）。仕組みを伏せて守る設計ではないので、方針を出しても強さは変わらず、共有回線での巻き添えに前もって触れておくと問い合わせが早くなる |
| 壊れたとき | キャッシュや DB を読めなければ数えず・止めずに通す |

### 2-5. 持つもの・持たないもの

申し込みは DB に残らない。アドレスはメールの宛先（と運営への通知の本文）に使うだけで、ログには出さない。
サイトが持つのは、遮断した IP（`home.BlockedIp`）と、連続送信の件数（キャッシュ、窓が過ぎれば消える）だけ。

---

## 3. WG への参加の仕組み

### 3-1. 流れ

```
WG 一覧「WG に参加」
  │
  ▼ /wg/<id>/join/（start）大学のアドレスを入れる
  │   ・送りすぎの歯止め（同じ IP 1 時間 10 件・同じアドレス 1 時間 3 件。超えたら 429）
  │   ・Classroom の名簿を引く（生徒 → 先生の順に、アドレスで 1 人ずつ）
  │       メンバー     → 確認のメール（リンク付き）
  │       メンバーでない → 「確認できませんでした」のメール
  │   ・どちらでも /wg/<id>/join/sent/ へ（画面は同じ）
  ▼
確認のメールのリンク /wg/join/verify/<token>/（verify）
  │   GET  … リンクを確かめて、確かめの画面（ボタン）を出すだけ
  │   POST … Chat スペースに追加（WG にスペースが登録されているとき）
  │          session に「どの WG の手続きか」を置き、アドレスを暗号化して Cookie に預ける
  ▼
/wg/<id>/join/github/start/（github_start）
  │   OAuth の state を作り、GitHub のログインへ
  ▼
GitHub でログイン（アカウントがなければその場で作る）
  ▼
/wg/join/github/callback/（github_callback）
  │   state を照合 → 期限と使用済みを確かめる → code をトークンに替える
  │   → ユーザー名を読む → トークンを取り消す → WG のチームに追加
  │   → リンクを使用済みにする
  ▼
結果の画面（「Chat を開く」は申請したアカウントで開く）。Cookie を消す
```

### 3-2. 手続きの状態をどこに置くか

アドレスを DB に持たずに、ブラウザをまたいだ手続きをつなぐのがこの設計の中心。

| 情報 | 置き場所 | 中身と期限 |
|---|---|---|
| 確認のリンク | メール（URL） | `django.core.signing` で署名した `{wg, n（使い捨ての番号）, e（暗号化したアドレス）}`。`e` は Chat スペースのある WG のときだけ入れる。期限 1 時間（`WG_JOIN_LINK_MAX_AGE`） |
| 手続きの途中 | session（`wgjoin`） | WG の pk・名簿を確かめた時刻・使い捨ての番号・Chat に追加できたか・GitHub の state。アドレスは置かない。猶予 1 時間（`WG_JOIN_STEP_TIMEOUT`） |
| 「Chat を開く」に使うアドレス | 申請者のブラウザの Cookie（`wgjoin_address`） | 暗号化したアドレス。path `/wg/`・HttpOnly・SameSite=Lax・本番は Secure・1 時間。結果の画面を出したら消す |
| 使用済みのリンク | DB キャッシュ（`wgjoin-used:<番号>`） | 登録を終えたリンクの番号。リンクの期限まで |
| 送りすぎの件数 | DB キャッシュ | IP ごと・アドレスごとの `(件数, 窓の開始時刻)`。アドレスは `SECRET_KEY` の鍵付きハッシュ（HMAC-SHA256）にして数える |

暗号は `cryptography` の Fernet。鍵は `SECRET_KEY` に用途ごとの salt を付けた SHA-256 から作る
（`wgjoin/verify.py`。countdown の通知先の暗号化と同じ作り）。`MultiFernet` で `SECRET_KEY_FALLBACKS` の鍵も
試す（鍵を替えるときの注意は README の「環境変数（本番）」）。

### 3-3. 各段の設計の理由

| 段 | 設計 | 理由 |
|---|---|---|
| start | メンバーでもそうでなくても、画面は「メールを送りました」で同じ | 他人のアドレスを入れて、その人がメンバーか探れないように |
| start | 名簿は `students/<アドレス>`・`teachers/<アドレス>` を 1 人ずつ引く。一覧は取らない | 名簿をサイトに持ち込まない。Classroom の招待を受けただけ（未参加）の人はメンバーにしない |
| start | 送りすぎは数えて断るだけで、IP は遮断しない | 構内の回線は共有なので、遮断すると巻き添えが出る |
| verify | GET では何もせず、POST で追加する | メールのリンクを開いて確かめる仕組み（メールのセキュリティ製品がリンクを先に開くことがある）が、本人の代わりに参加させないように |
| verify | リンクが届いた＝アドレスの持ち主、として扱う | 大学のメールに届いたリンクを開けるのは本人だけ、という前提で本人確認をする |
| github_callback | GitHub の `state` を session と照合する | 他人の手続きにログインを差し込ませない（CSRF） |
| github_callback | ユーザー名を読んだら、本人のトークンをすぐ取り消す | 本人の GitHub の権限をサイトに残さない。ユーザー名もログに出さない |
| github_callback | チームはまず GET で確かめ、いなければ PUT（role: member） | PUT は役割を上書きするので、リーダー（maintainer）が押し直すと member に下がるため |
| github_callback | 登録を終えたらリンクを使用済みにする | 転送されたリンクで、別の人が同じ手続きを使えないように |
| 結果 | 「Chat を開く」の URL に `authuser=<アドレス>` を付ける | ブラウザに私用の Google アカウントが先にログインしていても、申請した大学のアカウントで開くように |

### 3-4. 外部サービスと権限

| サービス | 認証 | 権限 | 使う API |
|---|---|---|---|
| Google（Classroom・Chat） | 運営（クラブのクラスの先生）のリフレッシュトークンから、呼ぶたびにアクセストークンをもらう。許可は `manage.py wgjoin_google_authorize`（デスクトップ アプリの OAuth クライアント・PKCE・`access_type=offline`） | `classroom.rosters`（名簿を見る・招待する）、`chat.memberships`（Chat のメンバーを管理する）。許可を取るとき、両方がそろっていなければトークンを受け取らない | `courses.students.get`・`courses.teachers.get`・`invitations.create`・`spaces.members.create` |
| GitHub（本人の確認） | GitHub App `funitclub-wg-join` のユーザー認可（OAuth）。`allow_signup=true` | 本人のユーザー名を読むだけ | `GET /user`、トークンの取り消し |
| GitHub（チームへの追加） | 同じ App の秘密鍵で JWT を作り、org のインストール トークンをもらう | Organization の Members: Read and write | `teams/<チーム>/memberships/<ユーザー>` の GET・PUT |
| GitHub（活動ページのチケット） | 同じ App。WG の活動ページ（`wg/<WG>_activity/github.py`）が、`repositories` と `permissions` を指定して絞ったインストール トークンをもらう | その WG のリポジトリの Issues: Read、Organization の Projects: Read | GraphQL（Issue と Project の項目）。5 分キャッシュ |

- 外部の API は `wgjoin/http.py` の `call` で呼ぶ（標準ライブラリだけ・タイムアウト 15 秒）。4xx/5xx は例外にせず
  ステータスを返し、呼ぶ側で判断する。例外の文言にはホスト名だけを出す（パスにユーザー名が入る API があるため）。
- GitHub App は org 全体のメンバーを変えられるので、追加できるチームを `^wg-[a-z0-9]+(-[a-z0-9]+)*$` に限る
  （`wgjoin/links.py`）。WG 紹介の登録を間違えても、運営のチームには人を入れられない。
- Chat への追加の失敗は、Google が返した `status` と `reason`（決まった値）だけを通知に載せる。
  `message` にはアドレスが入ることがあるので載せない。

### 3-5. 失敗したときの振る舞い

| 失敗 | 画面 | 運営への知らせ |
|---|---|---|
| 名簿を引けない（許可が切れた・先生でなくなった） | 「手続きの途中で失敗しました」（502）。**メンバーでない扱いにはしない** | ERROR の通知 |
| 確認のメールを送れない | 「手続きの途中で失敗しました」（502） | ERROR の通知 |
| Chat スペースに追加できない | 手続きは続ける。結果の画面でスペースのリンクから入るよう案内する | 「追加できませんでした」のメール（アドレス入り）と ERROR の通知 |
| GitHub のトークン交換・チームへの追加に失敗 | 「手続きの途中で失敗しました」（502） | WARNING のログだけ（通知はしない） |
| GitHub のログインをやめた | 「手続きを中止しました」 | なし |
| リンクが壊れている・期限切れ・使用済み | 「このリンクは使えません」（400） | なし |
| 手続きの猶予（1 時間）を過ぎた | 「時間が経ったため、手続きをやり直してください」 | なし |
| 同じリンクで先に別のブラウザが登録した | 「このリンクではもう登録されています」 | なし |

### 3-6. 「WG に参加」を出す条件

1. 8 つの設定がそろっている（`wgjoin.config.is_enabled`）：`CLUB_CLASSROOM_COURSE`、`GOOGLE_OAUTH_CLIENT_ID` /
   `_CLIENT_SECRET` / `_REFRESH_TOKEN`、`GITHUB_APP_ID` / `_CLIENT_ID` / `_CLIENT_SECRET` / `_PRIVATE_KEY`
2. WG 紹介の「GitHub のチーム」が `wg-` の形で入っている（`Wg.accepts_join`）

Chat スペースは任意。登録がない WG では Chat には追加せず、クラスの「授業」のリンクから本人が入る。
どちらかが欠けていれば、ボタンを出さず、URL を直接開いても 404 にする。

### 3-7. 持つもの・持たないもの

サイトはアドレス・GitHub のユーザー名・トークンを保存しない。アドレスが一時的に置かれるのは、
確認のリンク（暗号化）・申請者のブラウザの Cookie（暗号化・1 時間）・運営への「追加できませんでした」の
メールの本文だけ。WG に誰がいるかは、GitHub のチームと Chat スペースのメンバーで分かる。
