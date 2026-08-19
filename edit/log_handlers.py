# edit/log_handlers.py
#
# 500 エラーの通知。
#
# Django 標準の AdminEmailHandler は settings.ADMINS 宛に送るが、宛先を設定ファイルに
# 書きたくないので、管理者テーブル（edit.Administrator）を見るように差し替える。
# 本文の組み立て（トレースバック・リクエスト情報）は標準実装をそのまま使う。

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils.log import AdminEmailHandler

logger = logging.getLogger(__name__)


class DbAdminEmailHandler(AdminEmailHandler):
    """未処理の例外を管理者テーブルの宛先に送る。"""

    def send_mail(self, subject, message, *args, **kwargs):
        # 循環 import を避けるため、送るときに読む
        from .models import notification_emails
        from .notify import allow_notification

        # DB やキャッシュが落ちるとリクエストのたびに ERROR が出る。
        # 上限を設けないと、障害1回で受信箱が埋まる。
        if not allow_notification('error', settings.ERROR_NOTIFY_MAX_PER_HOUR):
            return

        try:
            EmailMessage(
                subject=f'[{settings.SITE_NAME}] {subject}',
                body=message,
                from_email=settings.SERVER_EMAIL,
                to=notification_emails(),
                connection=self.connection(),
            ).send(fail_silently=True)
        except Exception:
            # ここで例外を上げるとログ出力自体が壊れるので握る
            logger.debug('エラー通知の送信に失敗しました', exc_info=True)
