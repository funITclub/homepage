# wgjoin/google.py
#
# 運営のアカウントの権限で、Google の2つのことをする。
#
#   名簿     … クラブの Classroom のクラスの名簿で、あるアドレスの人がメンバーかを確かめる。
#              参加の申し込み（/join/apply/）では、まだいない人をクラスに招待する
#   Chat     … WG の Chat スペースに本人を追加する（WG に Chat スペースが登録されているとき）。
#              参加の申し込みでは、クラブのお知らせのスペースに追加する（CLUB_CHAT_SPACE があるとき）
#
# 運営（クラスの先生で、お知らせと各 WG のスペースのメンバー）が一度だけ
# `manage.py wgjoin_google_authorize` で許可し、そのリフレッシュトークンを
# GOOGLE_OAUTH_REFRESH_TOKEN に置く（本番は Key Vault）。頼む権限は
# 「名簿を管理する」（classroom.rosters。見る・招待する）と「Chat のメンバーを管理する」（chat.memberships）。
#
# 名簿はアドレスで1人ずつ引くだけで、一覧は取らない。結果もアドレスも保存しない。
# 運営コンソールの会員数（console.members）だけは人数を数えるために一覧を引くが、受け取るのは
# Google の内部の ID と種類だけ（fields で絞る。名前・アドレスは受け取らない）で、数えたら捨てる。

import base64
import hashlib
import secrets
from urllib.parse import quote, urlencode

from django.conf import settings

from .http import ServiceError, call

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
CLASSROOM_API = 'https://classroom.googleapis.com/v1'
CHAT_API = 'https://chat.googleapis.com/v1'

SCOPES = [
    'https://www.googleapis.com/auth/classroom.rosters',
    'https://www.googleapis.com/auth/chat.memberships',
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


# 申し込み（/join/apply/）のクラスへの招待の結果
MEMBER = 'member'    # もうクラスにいる（招待しない）
INVITED = 'invited'  # 招待を送った・もう招待が届いている。本人が Classroom で「参加」を押すと入る


def invite_to_club(email, club_course_id):
    """クラブのクラスに生徒として招待する。もういる人は招待しない。"""
    if is_club_member(email, club_course_id):
        return MEMBER
    status, _ = call('POST', f'{CLASSROOM_API}/invitations',
                     headers={'Authorization': f'Bearer {_access_token()}'},
                     json_body={'userId': email, 'courseId': club_course_id, 'role': 'STUDENT'})
    if status in (200, 409):  # 409 はもう招待が届いている
        return INVITED
    # 403 なら、許可に名簿を管理する権限がない（許可し直す）か、運営がクラスの先生でない
    raise ServiceError(f'Classroom のクラスに招待できませんでした（{status}）')


def add_to_chat_space(space, email):
    """Chat スペース（spaces/<ID>。WG のスペースかクラブのお知らせ）に追加する。もういる人はそのまま。"""
    status, body = call('POST', f'{CHAT_API}/{space}/members',
                        headers={'Authorization': f'Bearer {_access_token()}'},
                        json_body={'member': {'name': f'users/{email}', 'type': 'HUMAN'}})
    if status in (200, 409):  # 409 はもうスペースにいる
        return
    # 403 なら、許可に chat.memberships がない（許可し直す）か、運営がスペースのメンバーでない・
    # メンバーを追加できる役割でない、大学の管理者が Chat API を止めている、など。404 なら、
    # スペースの登録が違う。どれかを切り分けられるよう、Google が返した理由を通知に載せる
    raise ServiceError(f'Chat スペースに追加できませんでした（{status} {_google_reason(body)}）')


def _count_pages(url, key, fields, params=None, keep=lambda item: True):
    """一覧の API をページをめくって引き、keep に合う件数を返す。中身は数えるだけで残さない。"""
    headers = {'Authorization': f'Bearer {_access_token()}'}
    params = {**(params or {}), 'pageSize': 1000, 'fields': f'nextPageToken,{key}({fields})'}
    count = 0
    for _ in range(100):  # 念のための上限（10 万件）
        status, body = call('GET', url, headers=headers, params=params)
        if status != 200:
            raise ServiceError(f'人数を数えられませんでした（{status} {_google_reason(body)}）')
        count += sum(1 for item in body.get(key) or [] if keep(item))
        token = body.get('nextPageToken')
        if not token:
            break
        params['pageToken'] = token
    return count


def count_club_students(club_course_id):
    """クラブのクラスの生徒の数。"""
    return _count_pages(f'{CLASSROOM_API}/courses/{club_course_id}/students', 'students', 'userId')


def count_club_teachers(club_course_id):
    """クラブのクラスの先生の数（運営など。is_club_member と同じく会員に数える）。"""
    return _count_pages(f'{CLASSROOM_API}/courses/{club_course_id}/teachers', 'teachers', 'userId')


def count_club_invitations(club_course_id):
    """クラブのクラスに生徒として招待していて、まだ「参加」を押していない人の数。"""
    return _count_pages(f'{CLASSROOM_API}/invitations', 'invitations', 'id,role',
                        params={'courseId': club_course_id},
                        keep=lambda item: item.get('role') == 'STUDENT')


def count_chat_members(space):
    """Chat スペースに入っている人の数（アプリ・招待中の人は数えない）。"""
    return _count_pages(f'{CHAT_API}/{space}/members', 'memberships', 'member/type',
                        keep=lambda item: (item.get('member') or {}).get('type') == 'HUMAN')


def _google_reason(body):
    """Google の API のエラーの理由（PERMISSION_DENIED など）。本文（message）は載せない。

    message には相手のアドレスが入ることがあるので、決まった値の status と reason だけを使う。
    """
    error = body.get('error') if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return ''
    reasons = [d.get('reason') for d in error.get('details') or [] if isinstance(d, dict) and d.get('reason')]
    return ' '.join(str(x) for x in [error.get('status'), *reasons] if x)


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
        raise ServiceError('許可されていない権限があります。名簿を管理する権限と、Chat のメンバーを管理する権限の両方を許可してください')
    return token
