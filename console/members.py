# console/members.py
#
# 会員数。名簿はサイトに持たない方針なので、そのつど Google（Classroom・Chat）に人数を聞く。
# 受け取るのは数だけで、名前・アドレスは受け取らない・残さない（wgjoin.google の count_*）。
#
# 開くたびに聞くと遅く、API の回数も増えるので、結果（数だけ）を CACHE_SECONDS のあいだ覚える。

import logging

from django.core.cache import cache
from django.utils import timezone

from catalog.models import Wg
from wgjoin import google
from wgjoin.config import can_invite_to_club, club_course_id
from wgjoin.http import ServiceError
from wgjoin.links import decode_chat_space

logger = logging.getLogger(__name__)

CACHE_KEY = 'console:members'
CACHE_SECONDS = 10 * 60


def _ask(label, func, *args):
    """人数を聞く。聞けなければ None（画面には「取得できませんでした」と出す）。"""
    try:
        return func(*args)
    except ServiceError:
        logger.warning('会員数: %s を数えられませんでした', label, exc_info=True)
        return None


def collect():
    """その場で Google に聞いた人数。Google の設定（運営の許可）が無ければ configured が False。"""
    if not can_invite_to_club():
        return {'configured': False, 'checked_at': timezone.now()}
    course = club_course_id()
    wgs = []
    for wg in Wg.objects.published().order_by('code'):
        space = decode_chat_space(wg.chat_space)
        if not space:
            continue
        wgs.append({'title': f'{wg.code} {wg.name}',
                    'chat': _ask(f'{wg.code} の Chat', google.count_chat_members, space)})
    return {
        'configured': True,
        'checked_at': timezone.now(),
        'students': _ask('クラブのクラスの生徒', google.count_club_students, course),
        'invited': _ask('クラブのクラスの招待中', google.count_club_invitations, course),
        'wgs': wgs,
    }


def summary(refresh=False):
    """会員数。CACHE_SECONDS のあいだは覚えた数を返す。refresh で聞き直す。"""
    data = None if refresh else cache.get(CACHE_KEY)
    if data is None:
        data = collect()
        cache.set(CACHE_KEY, data, CACHE_SECONDS)
    return data
