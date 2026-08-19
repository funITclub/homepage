# edit/notify.py
#
# 運営あての通知メールの共通部分。宛先は管理者テーブル（edit.Administrator）から取る。
#
# 通知が溢れると読まれなくなるため、種類ごとに1時間あたりの上限を持たせる。

import logging

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMessage

from .models import notification_emails

logger = logging.getLogger(__name__)


def allow_notification(kind, max_per_hour=None):
    """この通知を送ってよいか。kind ごとに1時間あたりの通数で頭を打たせる。

    障害が続くと同じ通知が延々と飛ぶ。特に DB やキャッシュが落ちたときは
    リクエストのたびにエラーが出るため、上限が無いと受信箱が埋まり、
    メールの送信量そのものも問題になる。

    数えられない（キャッシュ障害）ときは送る側に倒す。異常時に黙るより、
    多少うるさいほうがましなため。
    """
    if max_per_hour is None:
        max_per_hour = settings.ADMIN_NOTIFY_MAX_PER_HOUR

    key = f'admin-notify:{kind}'
    try:
        count = (cache.get(key) or 0) + 1
        cache.set(key, count, 60 * 60)
    except Exception:
        return True

    if count > max_per_hour:
        # ここで warning 止まりにしておくこと。error にすると通知ハンドラが
        # 反応して、通知の抑制のために通知が飛ぶ堂々巡りになる。
        logger.warning('通知（%s）が1時間の上限に達したため送信を控えました（%s件目）',
                       kind, count)
        return False

    return True


def notify_admins(subject, body, kind, max_per_hour=None):
    """管理者に通知メールを送る。

    通知は付加機能なので、失敗しても呼び出し元の処理は止めない。
    """
    if not allow_notification(kind, max_per_hour):
        return False

    try:
        EmailMessage(
            subject=f'[{settings.SITE_NAME}] {subject}',
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=notification_emails(),
        ).send()
    except Exception:
        # 通知経路そのものが壊れている場合はここに来る。ログだけ残す。
        logger.exception('管理者への通知に失敗しました: %s', subject)
        return False

    return True
