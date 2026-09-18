#!/bin/bash
# App Service（funITclub）の起動コマンド。App Service の「スタートアップ コマンド」に
# `bash startup.sh` を設定してあり、コンテナが起動するたびに走る。
# デプロイのたびにコンテナは作り直されるので、デプロイ後の migrate もここで済む。
#
# migrate を GitHub Actions でやらないのは、DB（hirahira-db）が VNet の中にあり
# ランナーからは届かないため。VNet 統合されたアプリのコンテナからなら届く。
#
# Oryx が展開先（/tmp/<hash>）に cd し、antenv を PYTHONPATH に入れてから呼ぶ。
# ここで cd しないこと（/home/site/wwwroot にはソースが無い）。
#
# migrate が失敗したらアプリを起動しない。起動に失敗するとデプロイ（az webapp deploy）が
# 失敗扱いになり、GitHub Actions が赤くなって気づける。テーブルが足りないまま
# 動かして一部のページだけ 500 になるより、そのほうが見つけやすい。
# ※ インスタンスを2つ以上に増やすと migrate が同時に走る。増やすときは見直すこと。
set -euo pipefail

echo "startup.sh: migrate を実行する"
python manage.py migrate --noinput

# 参加フォームの連続送信の検知に使うキャッシュ用テーブル。既にあれば何もしない。
python manage.py createcachetable

echo "startup.sh: gunicorn を起動する"
# 以前 Oryx が自動生成していた起動と同じ設定（sync ワーカー1つ・タイムアウト600秒・アクセスログあり）。
exec python -m gunicorn --bind=0.0.0.0:"${PORT:-8000}" --timeout 600 \
  --access-logfile '-' --error-logfile '-' config.wsgi
