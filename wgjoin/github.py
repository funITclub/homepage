# wgjoin/github.py
#
# GitHub のチームへの登録。funITclub の GitHub App を2つの役で使う。
#
#   本人のログイン … 「GitHub でログイン」でユーザー名を確かめる（アカウントがなければ
#                    その画面で作れる）。受け取ったトークンは使い終わったら取り消す。
#   チームへの追加 … App として org の Members を操作する。まだ org にいない人は
#                    チームに追加した時点で、そのアカウントあてに org への招待が届く。
#
# App の権限は org 全体に及ぶので、追加できるチームは wg- で始まるものに絞る
# （wgjoin.links.is_wg_team）。ユーザー名はログにもどこにも残さない。

import base64
import time
from urllib.parse import quote, urlencode

import jwt
from django.conf import settings

from .http import ServiceError, call
from .links import is_wg_team

AUTHORIZE_URL = 'https://github.com/login/oauth/authorize'
TOKEN_URL = 'https://github.com/login/oauth/access_token'
API = 'https://api.github.com'
API_HEADERS = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}

# チームへの追加の結果（GitHub の membership.state）
ACTIVE = 'active'    # チームに入った（もう org のメンバーだった）
PENDING = 'pending'  # org への招待を送った。本人が受け入れるとチームに入る


def authorize_url(state, redirect_uri):
    params = {
        'client_id': settings.GITHUB_APP_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'state': state,
        'allow_signup': 'true',
    }
    return f'{AUTHORIZE_URL}?{urlencode(params)}'


def exchange_code(code, redirect_uri):
    status, body = call('POST', TOKEN_URL, form={
        'client_id': settings.GITHUB_APP_CLIENT_ID,
        'client_secret': settings.GITHUB_APP_CLIENT_SECRET,
        'code': code,
        'redirect_uri': redirect_uri,
    })
    token = body.get('access_token')
    if status != 200 or not token:
        raise ServiceError(f'GitHub のトークンを受け取れませんでした（{status} {body.get("error", "")}）')
    return token


def login_name(token):
    """ログインした本人の GitHub ユーザー名。"""
    status, body = call('GET', f'{API}/user', headers={**API_HEADERS, 'Authorization': f'Bearer {token}'})
    if status != 200 or not body.get('login'):
        raise ServiceError(f'GitHub のユーザーを確かめられませんでした（{status}）')
    return body['login']


def revoke_user_token(token):
    """本人のトークンを取り消す。失敗しても処理は止めない（8時間で失効する）。"""
    basic = base64.b64encode(
        f'{settings.GITHUB_APP_CLIENT_ID}:{settings.GITHUB_APP_CLIENT_SECRET}'.encode()).decode()
    try:
        call('DELETE', f'{API}/applications/{settings.GITHUB_APP_CLIENT_ID}/token',
             headers={**API_HEADERS, 'Authorization': f'Basic {basic}'},
             json_body={'access_token': token})
    except ServiceError:
        pass


def _app_jwt():
    now = int(time.time())
    # iat は時計のずれを見込んで 60 秒戻す。exp は上限の 10 分より短く。
    payload = {'iat': now - 60, 'exp': now + 9 * 60, 'iss': settings.GITHUB_APP_ID}
    return jwt.encode(payload, settings.GITHUB_APP_PRIVATE_KEY, algorithm='RS256')


def _installation_token():
    headers = {**API_HEADERS, 'Authorization': f'Bearer {_app_jwt()}'}
    status, body = call('GET', f'{API}/orgs/{settings.GITHUB_ORG}/installation', headers=headers)
    if status != 200:
        raise ServiceError(f'GitHub App が org に入っていません（{status}）')
    status, body = call('POST', f'{API}/app/installations/{body["id"]}/access_tokens', headers=headers)
    if status != 201:
        raise ServiceError(f'GitHub App のトークンを受け取れませんでした（{status}）')
    return body['token']


def add_to_team(team, username):
    """WG のチームに追加する。まだ org にいない人には招待が届く（PENDING）。"""
    if not is_wg_team(team):
        raise ValueError(f'WG のチームではありません: {team}')
    url = f'{API}/orgs/{settings.GITHUB_ORG}/teams/{quote(team)}/memberships/{quote(username)}'
    headers = {**API_HEADERS, 'Authorization': f'Bearer {_installation_token()}'}

    # もうチームにいる人はそのままにする。PUT は役割を上書きするので、リーダー
    # （maintainer）がボタンを押し直すと member に下がってしまう。
    status, body = call('GET', url, headers=headers)
    if status == 200 and body.get('state') in (ACTIVE, PENDING):
        return body['state']
    if status != 404:
        raise ServiceError(f'GitHub のチームを確かめられませんでした（{status}）')

    status, body = call('PUT', url, headers=headers, json_body={'role': 'member'})
    if status == 200 and body.get('state') in (ACTIVE, PENDING):
        return body['state']
    raise ServiceError(f'GitHub のチームに追加できませんでした（{status}）')
