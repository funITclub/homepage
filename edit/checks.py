# edit/checks.py
#
# 定期点検。いまのところ SMTP のシークレット期限だけを見ている。
#
# シークレットが切れると参加フォームの送信が止まるが、「申し込みが来ない」状態と
# 区別がつかず気づけない。切れる前に知らせる。

import logging
from datetime import date

from django.conf import settings
from django.core.cache import cache

from .notify import notify_admins

logger = logging.getLogger(__name__)

#: 残り日数がこれを下回ったら通知する（1段階につき1通）
WARN_DAYS = [30, 14, 7, 1]


def secret_expiry_date():
    """settings.EMAIL_SECRET_EXPIRES_ON を日付にする。未設定・不正なら None。"""
    raw = getattr(settings, 'EMAIL_SECRET_EXPIRES_ON', '')
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        logger.warning('EMAIL_SECRET_EXPIRES_ON の日付が不正です: %r', raw)
        return None


def warn_if_secret_expiring(today=None):
    """SMTP のシークレットの期限が近ければ通知する。

    30日前・14日前・7日前・前日、および失効後に1通ずつ送る。
    同じ段階で何度も送らないよう、送った段階をキャッシュに覚えておく。
    """
    expires_on = secret_expiry_date()
    if expires_on is None:
        return

    today = today or date.today()
    remaining = (expires_on - today).days

    if remaining < 0:
        stage = 'expired'
        subject = 'SMTP のシークレットが失効しています'
        lead = (f'メール送信に使うシークレットは {expires_on} に失効しました。\n'
                '参加フォームからの送信はすでに止まっています。\n')
    else:
        stage = next((str(d) for d in sorted(WARN_DAYS) if remaining <= d), None)
        if stage is None:
            return
        subject = f'SMTP のシークレットの期限が近づいています（残り{remaining}日）'
        lead = (f'メール送信に使うシークレットは {expires_on} に失効します（残り{remaining}日）。\n'
                '失効すると参加フォームからのメール送信が止まります。\n')

    key = f'secret-expiry-warned:{expires_on}:{stage}'
    try:
        if cache.get(key):
            return
        # 次の段階まで覚えておけば十分（最長でも30日）
        cache.set(key, True, 30 * 24 * 60 * 60)
    except Exception:
        logger.debug('期限通知の重複判定に失敗しました', exc_info=True)

    notify_admins(
        subject=subject,
        body=(
            f'{lead}\n'
            '■ 更新のしかた\n'
            '1. 新しいシークレットを発行する\n'
            '   az ad app credential reset --id <appId> --years 2\n'
            '2. Key Vault を更新する（App Service 側は自動で追従します）\n'
            '   az keyvault secret set --vault-name funitclub-kv \\\n'
            '     --name funitclub-smtp-password --value "<新しい値>"\n'
            '3. アプリケーション設定の期限日を更新する\n'
            '   az webapp config appsettings set --name funITclub \\\n'
            '     --settings EMAIL_SECRET_EXPIRES_ON="<新しい期限 YYYY-MM-DD>"\n\n'
            '詳しい手順は deploy.txt の「メール送信」を参照してください。\n'
        ),
        kind='secret-expiry',
    )


def run_daily_checks():
    """1日1回だけ点検する。リクエストのたびに走らせないためのゲート。"""
    key = 'daily-checks-done'
    try:
        if cache.get(key):
            return False
        cache.set(key, True, 24 * 60 * 60)
    except Exception:
        logger.debug('定期点検の実行判定に失敗しました', exc_info=True)
        return False

    try:
        warn_if_secret_expiring()
    except Exception:
        logger.exception('定期点検に失敗しました')
    return True
