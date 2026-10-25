# wgjoin/config.py

import base64
from urllib.parse import urlencode

from django.conf import settings

from .links import decode_chat_space, decode_course_id


def club_course_id():
    """クラブの Classroom のクラスの ID。ここにいる人をメンバーとみなす。"""
    return decode_course_id(settings.CLUB_CLASSROOM_COURSE)


def club_chat_space():
    """クラブのお知らせの Chat スペース（spaces/<ID>）。参加の申し込みで申込者を追加する。"""
    return decode_chat_space(settings.CLUB_CHAT_SPACE)


def club_classroom_url():
    """クラブのクラスを開く URL（WG の授業と Chat のリンクがある）。"""
    course_id = club_course_id()
    if not course_id:
        return 'https://classroom.google.com/'
    return 'https://classroom.google.com/c/' + base64.b64encode(course_id.encode()).decode().rstrip('=')


def repo_url(team):
    """WG のリポジトリの URL。リポジトリはチームと同じ名前にする決まり（WG 立ち上げガイドの資料 01）。"""
    return f'https://github.com/{settings.GITHUB_ORG}/{team}'


def chat_space_url(space, email=None):
    """WG の Chat スペースを開く URL。スペースが登録されていなければ空。

    email を渡すと authuser を付け、ブラウザにほかの Google アカウントがあっても、
    そのアカウントで開く。
    """
    if not space:
        return ''
    query = '?' + urlencode({'authuser': email}) if email else ''
    return f'https://mail.google.com/chat/{query}#chat/space/' + space.removeprefix('spaces/')


def can_invite_to_club():
    """参加の申し込みで、クラブのクラスに招待できるだけの設定がそろっているか。"""
    return all([
        club_course_id(),
        settings.GOOGLE_OAUTH_CLIENT_ID,
        settings.GOOGLE_OAUTH_CLIENT_SECRET,
        settings.GOOGLE_OAUTH_REFRESH_TOKEN,
    ])


def can_add_to_club_chat():
    """参加の申し込みで、クラブのお知らせの Chat スペースに追加できるだけの設定がそろっているか。"""
    return all([
        club_chat_space(),
        settings.GOOGLE_OAUTH_CLIENT_ID,
        settings.GOOGLE_OAUTH_CLIENT_SECRET,
        settings.GOOGLE_OAUTH_REFRESH_TOKEN,
    ])


def is_enabled():
    """「WG に参加」を受け付けられるだけの設定がそろっているか。

    ひとつでも欠けていればボタンを出さない（押しても途中で失敗するだけなので）。
    """
    return all([
        club_course_id(),
        settings.GOOGLE_OAUTH_CLIENT_ID,
        settings.GOOGLE_OAUTH_CLIENT_SECRET,
        settings.GOOGLE_OAUTH_REFRESH_TOKEN,
        settings.GITHUB_APP_ID,
        settings.GITHUB_APP_CLIENT_ID,
        settings.GITHUB_APP_CLIENT_SECRET,
        settings.GITHUB_APP_PRIVATE_KEY,
    ])
