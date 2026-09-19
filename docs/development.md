# 開発環境と手順（VS Code ＋ Docker Desktop）

funITclub のリポジトリ（この homepage と、各 WG のリポジトリ）で共通の開発環境と手順。
アプリのインストールに慣れていない人でも進められるように、クリックする場所まで書いてある。

## しくみ（最初に読む）

PC に入れるのは **VS Code・Git・Docker Desktop の 3 つだけ**。Python や Django は PC に
入れない。VS Code がリポジトリの中の設定（`.devcontainer/`）を読んで、Docker の
「コンテナ」という小さな作業部屋を作り、その中に Python などを自動で用意する。

- 全員が同じ環境になる（Windows と Mac の違いも、Python のバージョンの違いも出ない）
- 壊れたら作業部屋を作り直せば戻る。PC 本体は汚れない

| 入れるもの | 役割 |
|---|---|
| VS Code | コードを書くエディタ。操作はすべてここから |
| Git | 変更の記録と、GitHub とのやりとり |
| Docker Desktop | コンテナ（作業部屋）を動かす。起動しておくだけで触らない |

WG のリポジトリは [funITclub/wg-template](https://github.com/funITclub/wg-template) から作る。
中身の作りは homepage と同じなので、この手順がそのまま使える。

## 0. 始める前に確かめること

| 項目 | 必要なもの |
|---|---|
| OS | Windows 10（22H2）/ Windows 11 の 64 ビット、または macOS（最新から 3 つ前まで） |
| メモリ | 8GB 以上（4GB だと動くが遅い） |
| ディスクの空き | 20GB 以上 |
| ネット | 初回は 1〜2GB ほどダウンロードする。できれば自宅の回線で |
| GitHub | アカウント（下の手順 1 で作る） |

> **Mac のチップを確かめる：** 画面左上の Apple メニュー →「この Mac について」。
> 「チップ」に **Apple M1 / M2 / M3 …** とあれば Apple シリコン、「プロセッサ」に
> **Intel** とあれば Intel。Docker Desktop のダウンロードで使う。

> **会社や学校から借りている PC** は、インストールが禁止されていることがある。
> 自分の PC を使うこと。

## 1. GitHub の準備（初回だけ）

1. [github.com](https://github.com/) を開き、右上の「**Sign up**」からアカウントを作る。
   - ユーザー名は公開される。本名でもよい（使いたくなければ別の名前でよい）。
     **学籍番号は入れない**（大学のメールアドレスと同じなので、誰のアドレスか分かってしまう）。
2. 運営に **GitHub のユーザー名と自分の名前** を伝える（誰のアカウントか運営が分かるように）。
3. 数日以内に「funITclub への招待」メールが届く。メールの「**Join @funITclub**」を押して参加する。
4. **メールアドレスを非公開にする。** GitHub 右上の自分のアイコン →「**Settings**」→
   左の「**Emails**」→「**Keep my email addresses private**」にチェック。
   - その下に `12345678+ユーザー名@users.noreply.github.com` という形のアドレスが出る。
     **手順 3 で使うのでコピーしておく。**
   - 大学のアドレス（学籍番号）がコミットの履歴に残って公開されるのを防ぐため。

## 2. VS Code を入れる（初回だけ）

1. [code.visualstudio.com](https://code.visualstudio.com/) を開き、「**Download**」を押す。

**Windows**

2. ダウンロードした `VSCodeUserSetup-….exe` をダブルクリック。
3. 「同意する」→ そのまま「次へ」を押していく。「追加タスクの選択」では
   「**PATH への追加**」にチェックが入っていることを確かめる（最初から入っている）。
4. 「インストール」→「完了」。

**Mac**

2. ダウンロードした zip を開くと「**Visual Studio Code**」が出てくる。
3. それを「**アプリケーション**」フォルダーにドラッグする。
4. アプリケーションから開く。「インターネットからダウンロードされた…」と出たら「開く」。

**日本語にする（Windows・Mac 共通）**

5. VS Code の左端にある四角が4つのアイコン（**拡張機能**）を押す。
6. 検索欄に `Japanese` と入れ、「**Japanese Language Pack for Visual Studio Code**」
   （Microsoft）の「**Install**」を押す。
7. 右下に出る「**Change Language and Restart**」を押す。再起動すると日本語になる。

## 3. Git を入れて、名前を登録する（初回だけ）

**Windows**

1. [git-scm.com](https://git-scm.com/) →「**Download for Windows**」→
   「**Click here to download**」。
2. ダウンロードした `Git-….exe` をダブルクリック。**画面がたくさん出るが、すべて何も変えずに
   「Next」**、最後に「Install」→「Finish」。

**Mac**

1. 「アプリケーション → ユーティリティ → **ターミナル**」を開く。
2. `git --version` と入力して Enter。
3. 「コマンドライン・デベロッパツールをインストールしますか？」と出たら「**インストール**」。
   （バージョンが表示されたら、もう入っている）

**名前とメールアドレスを登録する（Windows・Mac 共通）**

4. **VS Code を一度閉じて開き直す**（Git を見つけさせるため）。
5. メニューの「**ターミナル**」→「**新しいターミナル**」。下に黒い（または白い）欄が開く。
6. 次の 2 行を 1 行ずつ入力して Enter。`"…"` の中は自分のものに変える。
   メールアドレスは手順 1 でコピーした **noreply のアドレス**（大学のアドレスではない）。

```bash
git config --global user.name "GitHubのユーザー名"
git config --global user.email "12345678+ユーザー名@users.noreply.github.com"
```

7. 何も表示されなければ成功。

## 4. Docker Desktop を入れる（初回だけ）

**Windows**

1. [Docker Desktop のページ](https://www.docker.com/products/docker-desktop/) →
   「**Download Docker Desktop**」→「**Download for Windows - AMD64**」。
   （Surface Pro X などの ARM 版 Windows は「ARM64」）
2. ダウンロードした `Docker Desktop Installer.exe` をダブルクリック。
3. 「**Use WSL 2 instead of Hyper-V**」にチェックが入ったまま「OK」。
4. 終わったら「**Close and restart**」。**PC が再起動する。**
5. 再起動後に Docker Desktop が開く。利用規約は「**Accept**」。
   サインインを求められたら「**Skip**」（または「Continue without signing in」）でよい。
   アンケートも「Skip」でよい。
6. 左下のクジラのマークが緑（「Engine running」）になれば完了。

> 途中で「WSL のアップデートが必要」と出たら、スタートメニューで「PowerShell」を
> 右クリック →「管理者として実行」→ `wsl --update` と入力して Enter。終わったら再起動。
> 「仮想化が無効」と出たら、PC の設定（BIOS）の変更が要るので運営に相談する。

**Mac**

1. [Docker Desktop のページ](https://www.docker.com/products/docker-desktop/) →
   「**Download Docker Desktop**」→ 手順 0 で確かめたチップに合わせて
   「**Mac - Apple Silicon**」または「**Mac - Intel Chip**」。
2. ダウンロードした `Docker.dmg` を開き、クジラのアイコンを「**Applications**」へドラッグ。
3. アプリケーションから「**Docker**」を開く。利用規約は「**Accept**」。
   設定は「**Use recommended settings**」のまま「Finish」。Mac のパスワードを求められたら入れる。
4. サインインを求められたら「**Skip**」でよい。
5. 画面上のメニューバーにクジラのマークが出て、Docker Desktop の左下が緑（「Engine running」）
   になれば完了。

> Docker Desktop は個人・教育目的なら無料で使える。

## 5. VS Code に Dev Containers を入れる（初回だけ）

1. VS Code の **拡張機能**（左端の四角 4 つのアイコン）を押す。
2. 検索欄に `Dev Containers` と入れる。
3. 「**Dev Containers**」（**Microsoft**、青いチェックマーク付き）の「**インストール**」を押す。
4. 左下に「><」のような青いマークが出れば完了。

## 6. リポジトリを開く（初回だけ）

1. **Docker Desktop を起動しておく**（クジラが緑になっていること）。
2. VS Code でコマンド パレットを開く：メニューの「**表示**」→「**コマンド パレット**」
   （Windows は `Ctrl + Shift + P`、Mac は `Cmd + Shift + P`）。
3. 上に出た入力欄に `Clone Repository in Container Volume` と入力し、出てきた
   「**開発コンテナー: コンテナー ボリュームにリポジトリを複製...**」
   （英語表示なら「Dev Containers: Clone Repository in Container Volume...」）を選ぶ。
4. リポジトリの URL を貼り付けて Enter。
   - WG のリポジトリ：`https://github.com/funITclub/wg-<WG の名前>`
   - homepage：`https://github.com/funITclub/homepage`
5. 「開発コンテナー内のリポジトリを複製すると、任意のコードが実行される場合があります」と
   出たら、URL が **funITclub のリポジトリ** であることを確かめてから先へ進む。
   （知らない人のリポジトリでは進まないこと）
6. 右下に「開発コンテナーの作成 (ログの表示)」と出る。**初回は 5〜10 分かかる。**
   「ログの表示」を押すと進み具合が見える。
7. 下のターミナルに **`準備ができました。`** と出たら完了。
   左下の青いところに「**開発コンテナー: funITclub …**」と出ていれば、作業部屋の中にいる。

> ソースは PC のフォルダーではなく、Docker の中に置かれる（エクスプローラーや Finder には
> 出てこない）。こうすると Windows でも速く、改行コードの問題も起きない。

## 7. サイトを起動して確かめる

1. **`F5` キー** を押す（Mac のノートは `fn + F5`）。
   またはメニューの「**実行**」→「**デバッグの開始**」。
2. 下のターミナルに `Starting development server at http://127.0.0.1:8000/` と出る。
3. 右下に「ポート 8000 で実行されているアプリケーションは使用可能です」と出たら「**ブラウザーで開く**」。
   出なければ、ブラウザで `http://localhost:8000/` を開く。
4. サイトが表示されたら成功。止めるときは上に出る **■（停止）** ボタン、または `Shift + F5`。

これで準備は終わり。

## 8. 毎日の始め方・終わり方

**始めるとき**

1. **Docker Desktop を起動する**（クジラが緑になるまで待つ）。
2. VS Code を開く。前回のリポジトリが自動で開くことが多い。開かなければ
   「**ファイル**」→「**最近使用した項目を開く**」→「**[開発コンテナー]**」と付いたものを選ぶ。
3. 左下に「開発コンテナー: …」と出ていることを確かめる。
4. **最新の状態にする**：左の「**ソース管理**」（枝分かれのアイコン）→ 上の「…」→「**プル**」。

**終わるとき**

1. 変更をコミットして push しておく（下の「変更を届ける」）。
2. VS Code を閉じる。
3. Docker Desktop も終了してよい（メモリを使うため）。Windows は右下の通知領域、Mac は
   メニューバーのクジラ →「**Quit Docker Desktop**」。

## 9. よく使う操作

| やりたいこと | やり方 |
|---|---|
| サイトを起動する | `F5` |
| テストを流す（push の前に必ず） | コマンド パレット →「タスク: テスト タスクの実行」。またはターミナルで `python manage.py test` |
| モデルを変えた | ターミナルで `python manage.py makemigrations` → `python manage.py migrate` |
| 管理画面に入るアカウントを作る | ターミナルで `python manage.py createsuperuser` |
| ターミナルを開く | メニューの「ターミナル」→「新しいターミナル」 |

ターミナルのコマンドは Windows でも Mac でも同じ（作業部屋の中は Linux のため）。

## 10. 変更を届ける（Git）

VS Code の左の「**ソース管理**」から操作する。

- **WG のリポジトリ**：`main` には直接 push できない（ルールで止めてある）。
  ブランチを切ってプルリクエストを出す。手順は
  [wg-template の README](https://github.com/funITclub/wg-template#開発の流れ) の「開発の流れ」。
- **homepage**：`main` に push すると、そのまま本番（funitclub.org）に出る。テストを通してから push する。

初めて push するときは「GitHub にサインイン」を求められる。「**許可**」→ ブラウザで
「**Authorize**」を押す。

## 11. 秘密情報の扱い

- パスワードや API キーは **コードに書かない・コミットしない**。リポジトリは公開なので、
  一度 push すると消しても履歴やフォークに残る。
- 手元で使う値は `.env` に書く（Git には入らない）。ひな形は `.env.example`。
  作業部屋を作ったときに `.env` が無ければ自動でコピーされる。
- 個人の大学アドレス（学籍番号）も書かない（README の「管理者と通知」を参照）。

## 12. 困ったとき

| 症状 | 対処 |
|---|---|
| 「Docker が起動していない」「Docker デーモンに接続できない」 | Docker Desktop を起動し、クジラが緑になってから開き直す |
| 左下に「開発コンテナー」と出ていない | 左下の青いマーク →「**コンテナーで再度開く**」 |
| `F5` で何も起きない | 左下が「開発コンテナー」になっているか確かめる。拡張機能の読み込みに少し時間がかかることもある |
| ブラウザで開けない | VS Code 下部の「**ポート**」タブに 8000 があるか確かめる。無ければ「ポートの転送」で 8000 を足す |
| `no such table` と出る | ターミナルで `python manage.py migrate` |
| `requirements.txt` が変わったのに import できない | ターミナルで `pip install -r requirements.txt` |
| 環境がおかしくなった | コマンド パレット →「**開発コンテナー: コンテナーのリビルド**」。ソースと DB（`db.sqlite3`）は残る |
| PC が重い | 使わないときは Docker Desktop を終了する |
| push できない（403） | org の招待を受けたか、WG のチームに入っているか、運営に確かめる |

どうしても進まないときは、**画面のスクリーンショット**と、**どの手順の何番で止まったか**を
添えて運営に聞く。

## 13. 設定ファイルの一覧（運営向け）

| ファイル | 役割 |
|---|---|
| `.devcontainer/devcontainer.json` | 作業部屋（コンテナ）の定義。Python のバージョン（本番に合わせる）・入れる拡張機能・転送するポート |
| `.devcontainer/post-create.sh` | 作業部屋を作ったときに一度だけ走る（パッケージ・`.env`・migrate） |
| `.vscode/settings.json` | エディタの共通設定（LF・UTF-8・インデント 4・テンプレートの色分け） |
| `.vscode/launch.json` | `F5` の起動構成（サイト・テスト） |
| `.vscode/tasks.json` | よく使う manage.py のコマンド |
| `.vscode/extensions.json` | おすすめの拡張機能 |
| `.gitattributes` | 改行コードを LF に固定する（Windows で clone しても CRLF にしない） |

`.vscode/` はこの 4 ファイルだけを共有する（`.gitignore` で他は無視）。個人の設定は
VS Code のユーザー設定に置く。

**標準を変えるときは homepage と wg-template の両方を直す。** 既存の WG リポジトリには
自動では反映されないので、必要なら各 WG に知らせる。本番の Python を上げたときは
`devcontainer.json` のイメージ（`python:1-3.11-...`）と wg-template の CI も合わせる。
