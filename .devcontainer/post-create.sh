#!/bin/bash
# Dev Container を作ったときに一度だけ走る（devcontainer.json の postCreateCommand）。
# 何度流しても壊れないように書いてある。requirements.txt を変えたときは
# コンテナを作り直すか、このスクリプトを手で流し直す。
set -euo pipefail

pip install --disable-pip-version-check -r requirements.txt

# ローカルの秘密情報のひな形。中身が空なら、メールは送らずコンソールに出る。
if [ ! -f .env ]; then
    cp .env.example .env
fi

python manage.py migrate --noinput
python manage.py createcachetable

echo
echo "準備ができました。編集画面（/edit/）を使うなら、ログイン用のアカウントを作ってください:"
echo "  python manage.py createsuperuser"
