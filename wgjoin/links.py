# wgjoin/links.py
#
# クラブの Classroom のクラスの ID と、WG 紹介に登録する GitHub のチーム名の読み取りと検査。
# 編集画面のフォームと参加の処理の両方から使う。

import base64
import binascii
import re

#: チームを操作する GitHub App は org 全体のメンバーを変えられる。登録の間違いや
#: 書き換えで運営用などのチームに人を入れないよう、WG のチームの名前だけに絞る。
GITHUB_TEAM_PATTERN = re.compile(r'^wg-[a-z0-9]+(?:-[a-z0-9]+)*$')

_COURSE_SEGMENT = re.compile(r'/c/([A-Za-z0-9_-]+)')


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
