# wgjoin/links.py
#
# クラブの Classroom のクラスの ID と、WG 紹介に登録する GitHub のチーム名・Chat スペースの読み取りと検査。
# 編集画面のフォームと参加の処理の両方から使う。

import base64
import binascii
import re

#: チームを操作する GitHub App は org 全体のメンバーを変えられる。登録の間違いや
#: 書き換えで運営用などのチームに人を入れないよう、WG のチームの名前だけに絞る。
GITHUB_TEAM_PATTERN = re.compile(r'^wg-[a-z0-9]+(?:-[a-z0-9]+)*$')

_COURSE_SEGMENT = re.compile(r'/c/([A-Za-z0-9_-]+)')

# Chat スペースの URL の形は2通りある（mail.google.com/chat/…#chat/space/<ID> と chat.google.com/room/<ID>）
_CHAT_SPACE_SEGMENT = re.compile(r'(?:space/|spaces/|room/)([A-Za-z0-9_-]+)')
_CHAT_SPACE_ID = re.compile(r'^[A-Za-z0-9_-]{6,}$')


def decode_course_id(value):
    """授業の ID を取り出す。数字の ID か、授業の URL の /c/ の後ろ（ID を base64 にしたもの）。

    読めなければ None。
    """
    value = (value or '').strip()
    if value.isdigit():
        return value
    match = _COURSE_SEGMENT.search(value)
    segment = match.group(1) if match else value
    if segment.isdigit():
        return segment
    try:
        decoded = base64.urlsafe_b64decode(segment + '=' * (-len(segment) % 4)).decode('ascii')
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    return decoded if decoded.isdigit() else None


def is_wg_team(slug):
    return bool(GITHUB_TEAM_PATTERN.match(slug or ''))


def decode_chat_space(value):
    """Chat スペースの名前（spaces/<ID>）を取り出す。スペースの URL か、spaces/<ID> か、ID だけ。

    読めなければ None。
    """
    value = (value or '').strip()
    match = _CHAT_SPACE_SEGMENT.search(value)
    space_id = match.group(1) if match else value
    return f'spaces/{space_id}' if _CHAT_SPACE_ID.match(space_id) else None
