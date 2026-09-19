# wgjoin/google.py
#
# クラブの Classroom のクラスの名簿で、あるアドレスの人がメンバーかを確かめる。
#
# 名簿を読むのは運営のアカウント（クラスの先生）の権限。運営が一度だけ
# `manage.py wgjoin_google_authorize` で許可し、そのリフレッシュトークンを
# GOOGLE_OAUTH_REFRESH_TOKEN に置く（本番は Key Vault）。頼む権限は
# 「名簿を見る」（classroom.rosters.readonly）だけ。
#
# 名簿はアドレスで1人ずつ引くだけで、一覧は取らない。結果もアドレスも保存しない。

import base64
import hashlib
import secrets
from urllib.parse import quote, urlencode

from django.conf import settings

from .http import ServiceError, call

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
CLASSROOM_API = 'https://classroom.googleapis.com/v1'

SCOPES = [
    'https://www.googleapis.com/auth/classroom.rosters.readonly',
]


def _access_token():
    """運営のリフレッシュトークンから、その場限りのアクセストークンをもらう。"""
    status, body = call('POST', TOKEN_URL, form={
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
        'refresh_token': settings.GOOGLE_OAUTH_REFRESH_TOKEN,
        'grant_type': 'refresh_token',
    })
    token = body.get('access_token')
    if status != 200 or not token:
        # invalid_grant なら、運営が許可を取り消したかパスワードを変えた。許可し直す
        raise ServiceError(f'Google のトークンを受け取れませんでした（{status} {body.get("error", "")}）')
    return token


def is_club_member(email, club_course_id):
    """クラブのクラスの生徒か先生に、このアドレスの人がいるか。"""
    headers = {'Authorization': f'Bearer {_access_token()}'}
    for role in ('students', 'teachers'):
        status, _ = call('GET', f'{CLASSROOM_API}/courses/{club_course_id}/{role}/{quote(email)}',
                         headers=headers)
        if status == 200:
            return True
        if status != 404:
            # 403 なら、許可したアカウントがクラスの先生でない
            raise ServiceError(f'Classroom の名簿を読めませんでした（{status}）')
    return False


# ---- 運営が一度だけ行う許可（manage.py wgjoin_google_authorize） ----

def new_pkce():
    """(code_verifier, code_challenge)。"""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    return verifier, challenge


def authorize_url(state, challenge, redirect_uri):
    params = {
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': ' '.join(SCOPES),
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
        # リフレッシュトークンを受け取るため。許可し直すときも必ず出させる
        'access_type': 'offline',
        'prompt': 'consent',
    }
    return f'{AUTH_URL}?{urlencode(params)}'


def exchange_for_refresh_token(code, verifier, redirect_uri):
    status, body = call('POST', TOKEN_URL, form={
        'code': code,
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
        'code_verifier': verifier,
    })
    token = body.get('refresh_token')
    if status != 200 or not token:
        raise ServiceError(f'リフレッシュトークンを受け取れませんでした（{status} {body.get("error", "")}）')
    if not set(SCOPES) <= set((body.get('scope') or '').split()):
        raise ServiceError('名簿を見る権限が許可されませんでした')
    return token
