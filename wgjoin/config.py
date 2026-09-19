# wgjoin/config.py

import base64

from django.conf import settings

from .links import decode_course_id


def club_course_id():
    """クラブの Classroom のクラスの ID。ここにいる人をメンバーとみなす。"""
    return decode_course_id(settings.CLUB_CLASSROOM_COURSE)


def club_classroom_url():
    """クラブのクラスを開く URL（WG の授業と Chat のリンクがある）。"""
    course_id = club_course_id()
    if not course_id:
        return 'https://classroom.google.com/'
    return 'https://classroom.google.com/c/' + base64.b64encode(course_id.encode()).decode().rstrip('=')


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
