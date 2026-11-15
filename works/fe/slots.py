"""問題メールの時間帯（9〜18時の毎時）と、出典の書き方。

hirahira_room では X 投稿（fe.x_post）と問題メール（fe.mail）が共有している部品。
funitclub は X 投稿を取り込まないので、問題メールが使う分だけをここに置く。
中身は hirahira_room の apps/fe/x_post.py の同じ名前のものと同じ。
"""

import datetime
import re

from django.utils import timezone

from .models import IPA_SAMPLE_PREFIX

# 毎時の枠（9〜18時）。値は h09 のように時刻を2桁で持つ
HOURLY_SLOTS = ['h{:02d}'.format(hour) for hour in range(9, 19)]
# 時間帯ごとの予定の時刻（日本時間）
SLOT_HOURS = {slot: int(slot[1:]) for slot in HOURLY_SLOTS}
WEEKDAYS = '月火水木金土日'
EXAM_NAME = '基本情報技術者試験'


def is_official(source):
    """IPA の公開問題・サンプル問題を転記したものか。"""
    return source.strip().startswith(('令和', '平成', IPA_SAMPLE_PREFIX))


def citation(source):
    """IPA の求める形の出典。「出典：令和7年度 基本情報技術者試験 科目A 問2」。

    転記の問題の source は、出典の後ろに「 ／ 」でシラバスの項目を続けているので、
    その前だけを使う。IPA の公開問題でなければ空文字を返す。
    """
    if not is_official(source):
        return ''
    head = source.split(' ／ ')[0].strip()
    if head.startswith(IPA_SAMPLE_PREFIX):
        return '出典：{} {}'.format(EXAM_NAME, head)
    match = re.match(r'(\S+年度(?:\s*[春秋]期)?)\s*(.*)', head)
    if not match:
        return '出典：{} {}'.format(EXAM_NAME, head)
    return '出典：{} {} {}'.format(match.group(1), EXAM_NAME, match.group(2)).strip()


def slot_date(slot, now=None):
    """予定の日付が渡されなかったときの、その枠の日付。

    枠の時刻が今より12時間を超えて先なら、前の日の枠が日付をまたいで遅れて
    届いたとみなす（例：18時の枠が翌日の1時に届いたら、前の日の18時の枠）。
    """
    local = timezone.localtime(now or timezone.now())
    if SLOT_HOURS[slot] - local.hour > 12:
        return local.date() - datetime.timedelta(days=1)
    return local.date()
