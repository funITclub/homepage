# wgjoin/google.py
#
# 本人の大学の Google アカウントで Classroom を操作する。
#
# 使う権限は、本人の同意で借りる「Classroom のクラスを見る」だけ（運営のアカウントの権限は
# 使わない）。クラブのクラスを読めるか＝そのクラスの生徒か先生か、でメンバーかを確かめる。
# WG の授業も Chat のリンクもクラブのクラスの中にあるので、サイトが登録するものはない。
#
# 受け取ったトークンは処理が済んだらすぐ取り消し、どこにも保存しない。
# メールアドレスなどのプロフィールは要求しない（openid / email を頼まない）。

import base64
import hashlib
import secrets
from urllib.parse import urlencode

from django.conf import settings

from .http import ServiceError, call

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
CLASSROOM_API = 'https://classroom.googleapis.com/v1'

SCOPES = [
    'https://www.googleapis.com/auth/classroom.courses.readonly',
]


def new_pkce():
    """(code_verifier, code_challenge)。認可コードを横取りされても使えないようにする。"""
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
        'access_type': 'online',
        'prompt': 'select_account',
        'hd': settings.WG_JOIN_GOOGLE_DOMAIN,
    }
    return f'{AUTH_URL}?{urlencode(params)}'


def exchange_code(code, verifier, redirect_uri):
    """認可コードをアクセストークンに換える。本人が権限を一部しか許可しなければ ServiceError。"""
    status, body = call('POST', TOKEN_URL, form={
        'code': code,
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
        'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
        'code_verifier': verifier,
    })
    token = body.get('access_token')
    if status != 200 or not token:
        raise ServiceError(f'Google のトークンを受け取れませんでした（{status} {body.get("error", "")}）')
    granted = set((body.get('scope') or '').split())
    if not set(SCOPES) <= granted:
        revoke(token)
        raise ServiceError('Classroom の権限が許可されませんでした')
    return token


def is_club_member(token, club_course_id):
    """クラブのクラスを読めるか（＝そのクラスの生徒か先生か）。"""
    status, body = call('GET', f'{CLASSROOM_API}/courses/{club_course_id}',
                        headers={'Authorization': f'Bearer {token}'})
    if status == 200:
        return body.get('courseState') == 'ACTIVE'
    if status in (403, 404):
        return False
    raise ServiceError(f'Classroom でメンバーか確かめられませんでした（{status}）')


def revoke(token):
    """トークンを取り消す。失敗しても処理は止めない（1時間で失効する）。"""
    try:
        call('POST', REVOKE_URL, form={'token': token})
    except ServiceError:
        pass
