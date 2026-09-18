# 開発環境と手順（VS Code ＋ Dev Container）

funITclub のリポジトリ（この homepage と、各 WG のリポジトリ）で共通の開発環境と手順。
**全員が同じ環境で開発する**ために、Python や必要なパッケージは各自の PC に入れず、
リポジトリに入っている定義（`.devcontainer/`）からコンテナを立てて、その中で作業する。

- Python のバージョンが本番（3.11）と同じになる。「自分の PC では動いた」が起きにくい
- Windows と Mac の違い（コマンド・改行コード・文字コード）を気にしなくてよい
- 壊れたらコンテナを作り直せば戻る。PC 本体は汚れない

WG のリポジトリは [funITclub/wg-template](https://github.com/funITclub/wg-template) から作る。
中身の作りは homepage と同じなので、この手順がそのまま使える。WG 固有の進め方（ブランチと
プルリクエスト）は wg-template の README にある。

## 1. 開き方を選ぶ

どちらでも同じ環境になる。**迷ったら A**。

| | A. Codespaces | B. 手元の VS Code ＋ Docker |
|---|---|---|
| 動く場所 | GitHub のクラウド | 自分の PC |
| PC に入れるもの | なし（ブラウザだけ）。VS Code から開くこともできる | VS Code・Docker Desktop・Git |
| PC の性能 | 問わない | メモリ 8GB 以上が目安 |
| 費用 | 月ごとの無料枠の中なら無料 | 無料 |
| ネットが切れたら | 作業できない | 作業できる |

> **Codespaces の無料枠。** 個人アカウントごとに毎月の無料枠がある（通常 120 コア時間。
> 既定の 2 コアのマシンなら月 60 時間）。学生は GitHub Education に申請すると GitHub Pro
> 相当になり、枠が増える。**使い終わったら止める**（止めないと 30 分放置で自動停止するまで
> 枠を使う）。最新の条件は GitHub の料金ページで確認すること。

## 2. 最初に一度だけやること

### 共通

1. GitHub のアカウントを作り、運営に伝えて **org（funITclub）に招待してもらう**。
   届いた招待メールから参加する。
2. GitHub にコミットするときの名前とメールアドレスは、GitHub の設定で
   「Keep my email addresses private」をオンにしておく（大学のアドレス＝学籍番号を
   公開リポジトリの履歴に残さないため）。

### A. Codespaces を使う場合

準備は不要。「3. リポジトリを開く」へ。

### B. 手元の VS Code ＋ Docker を使う場合

1. [VS Code](https://code.visualstudio.com/) を入れる。
2. [Docker Desktop](https://www.docker.com/products/docker-desktop/) を入れて起動する。
   - **Windows**：インストーラーの指示に従って WSL 2 を有効にする（再起動を求められる）。
   - **Mac**：Apple シリコン（M1 以降）か Intel かに合ったものを選ぶ。
3. [Git](https://git-scm.com/) を入れる（Mac はターミナルで `git --version` を打つと
   入れるよう案内が出る）。
4. VS Code の拡張機能から **Dev Containers**（`ms-vscode-remote.remote-containers`）を入れる。
   日本語にするなら **Japanese Language Pack** も入れる。

## 3. リポジトリを開く

### A. Codespaces

1. GitHub でリポジトリのページを開く。
2. 緑の「**Code**」→「**Codespaces**」タブ →「**Create codespace on main**」。
3. ブラウザの中で VS Code が開く。**初回は準備に数分かかる**（下のターミナルに
   `準備ができました` と出たら完了）。

2 回目以降は「Code」→「Codespaces」の一覧から、前に作ったものを開く（毎回作らない）。

### B. 手元の VS Code

1. Docker Desktop を起動しておく。
2. VS Code でコマンドパレット（Windows: `Ctrl+Shift+P` / Mac: `Cmd+Shift+P`）を開き、
   「**Dev Containers: Clone Repository in Container Volume...**」を選ぶ。
3. リポジトリの URL（例：`https://github.com/funITclub/homepage`）を入れる。
4. **初回は準備に数分かかる**（ターミナルに `準備ができました` と出たら完了）。

2 回目以降は VS Code の「ファイル → 最近使用した項目」から開く。

> ソースはコンテナ用の領域（Docker のボリューム）に置かれ、PC のフォルダーには出てこない。
> Windows でもファイルの読み書きが速く、改行コードの問題も起きないため、こちらを標準にしている。
> すでに PC に clone してあるリポジトリなら、フォルダーを開いて右下の通知（または
> コマンドパレットの「**Dev Containers: Reopen in Container**」）からコンテナで開き直してもよい。

## 4. 毎日の作業

開いたあとの操作は A・B とも同じ。コマンドは VS Code の中のターミナル（メニューの
「表示 → ターミナル」）で打つ。コンテナの中なので Windows でも同じコマンドでよい。

### サイトを起動する

**`F5`**（または「実行とデバッグ」→「**サイトを起動（runserver）**」）。

- 右下に「ポート 8000 で…」と出るので「ブラウザーで開く」を押す。
- 止めるときは上に出る ■ ボタン（または `Shift+F5`）。
- コードを保存すると自動で再読み込みされる。
- 行番号の左をクリックして赤丸（ブレークポイント）を付けると、そこで止めて変数の中身を見られる。

ターミナルから起動してもよい（こちらはデバッガーが付かない）。

```bash
python manage.py runserver
```

### テストを流す

**push する前に必ず流す。** コマンドパレット →「タスク: テスト タスクの実行」、
またはターミナルで:

```bash
python manage.py test
```

### よく使うコマンド

コンテナの中では開発用の設定（`config.settings_dev`）が既定になっているので、
`--settings=...` は付けなくてよい。

| やりたいこと | コマンド |
|---|---|
| モデルを変えた後、マイグレーションを作る | `python manage.py makemigrations` |
| DB に反映する | `python manage.py migrate` |
| 編集画面・admin に入るアカウントを作る | `python manage.py createsuperuser` |
| パッケージを足す | `requirements.txt` に `パッケージ名==バージョン` を書き、`pip install -r requirements.txt` |

`makemigrations` / `migrate` / `createsuperuser` / テストは、コマンドパレットの
「タスク: タスクの実行」からも選べる。

### Git で変更を届ける

VS Code 左の「ソース管理」から、変更の確認 → メッセージを書いてコミット → 同期（push）が
できる。コミットメッセージは日本語で、**何をなぜ変えたか**を書く。

- **homepage**：`main` に push すると、そのまま本番（funitclub.org）にデプロイされる。
  テストを通してから push すること。
- **WG**：`main` には直接 push せず、ブランチを切ってプルリクエストを出す
  （wg-template の README を参照）。

## 5. 秘密情報の扱い

- パスワードや API キーは **コードに書かない・コミットしない**。リポジトリは公開なので、
  一度 push すると消しても履歴やフォークに残る。
- 手元で使う値は `.env` に書く（`.gitignore` 済み）。ひな形は `.env.example`。
  コンテナを作ったときに `.env` が無ければ `.env.example` からコピーされる。
- Codespaces で使う値は、GitHub の「Settings → Codespaces → Secrets」に登録すると
  環境変数として渡る（`.env` に書かなくてよい）。
- 個人の大学アドレス（学籍番号）も書かない（README の「管理者と通知」を参照）。

## 6. 困ったとき

| 症状 | 対処 |
|---|---|
| `requirements.txt` が変わったのに import できない | `pip install -r requirements.txt`。直らなければコマンドパレット →「Dev Containers: Rebuild Container」（Codespaces は「Codespaces: Rebuild Container」） |
| `no such table` と出る | `python manage.py migrate` |
| 環境がおかしくなった | 「Rebuild Container」で作り直す。ソースと DB（`db.sqlite3`）はそのまま残る |
| B で「Docker が起動していない」と出る | Docker Desktop を起動してから開き直す |
| ブラウザで開くと `DisallowedHost` / `CSRF` のエラー | ポート 8000 以外で起動していないか確認。Codespaces では `config/settings_dev.py` が転送先のホスト名を許可している |
| ポート 8000 が開かない | VS Code 下部の「ポート」タブで 8000 が転送されているか確認する |
| Codespaces の無料枠が減っている | 使わないときは停止する。GitHub の「Your codespaces」で不要なものは削除する |

## 7. 設定ファイルの一覧（運営向け）

| ファイル | 役割 |
|---|---|
| `.devcontainer/devcontainer.json` | コンテナの定義。Python のバージョン（本番に合わせる）・入れる拡張機能・転送するポート |
| `.devcontainer/post-create.sh` | コンテナを作ったときに一度だけ走る（パッケージ・`.env`・migrate） |
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
