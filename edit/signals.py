# edit/signals.py
#
# 編集画面・管理画面へのログイン失敗を監視する。
#
# 参加フォームの連続送信より、こちらのほうが実害は大きい（管理権限の奪取につながる）。
# 遮断はしない。正規の運営が打ち間違えただけで締め出すと、復旧の手段を失うため。

import logging

from django.conf import settings
from django.contrib.auth.signals import user_login_failed
from django.core.cache import cache
from django.dispatch import receiver

from .notify import notify_admins

logger = logging.getLogger(__name__)


@receiver(user_login_failed)
def warn_on_repeated_login_failures(sender, credentials=None, request=None, **kwargs):
    """同一IPからのログイン失敗が続いたら通知する。"""
    if request is None:
        return

    # home を読むのは循環しないが、遅延 import にしてアプリ起動順に依存させない
    from home.netutils import client_ip

    ip = client_ip(request)
    if not ip:
        return

    limit, seconds = settings.LOGIN_FAILURE_RULE
    key = f'login-failure:{ip}'
    try:
        count = (cache.get(key) or 0) + 1
        cache.set(key, count, seconds)
    except Exception:
        logger.debug('ログイン失敗の計測に失敗しました', exc_info=True)
        return

    # 入力されたユーザー名は載せない（打ち間違いで本物のIDが漏れるため）
    logger.warning('ログインに失敗しました: %s分間に%s回 IP=%s', seconds // 60, count, ip)

    if count != limit:
        # 上限に達した瞬間だけ通知する（以降は通知せずログに残す）
        return

    notify_admins(
        subject=f'ログイン失敗が続いています: {ip}',
        body=(
            '編集画面または管理画面へのログイン失敗が続いています。\n\n'
            f'IP　　: {ip}\n'
            f'回数　: {seconds // 60}分間に{count}回\n\n'
            '■ 心当たりがない場合\n'
            'パスワードの総当たりを試されている可能性があります。\n'
            '運営のパスワードを変更してください。\n'
            '  python manage.py changepassword <ユーザー名>\n\n'
            '■ 心当たりがある場合\n'
            '運営の誰かが打ち間違えているだけかもしれません。\n\n'
            '※ ログイン失敗ではIPを遮断していません。'
            '正規の運営が締め出されて復旧できなくなるのを避けるためです。\n'
        ),
        kind='login-failure',
    )
