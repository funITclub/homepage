# home/notifications.py
#
# 参加フォーム由来の通知メール。宛先の決め方は edit.notify に任せる。

from django.conf import settings

from edit.notify import notify_admins


def send_block_notification(blocked):
    """IP を遮断したことを運営に知らせる。

    遮断された側は問い合わせフォームにも辿り着けないため、こちらから気づく手段が
    これしかない。IP を変えながら攻撃されると通知が増えるので、edit.notify 側の
    上限（settings.IP_BLOCK_NOTIFY_MAX_PER_HOUR）で頭を打たせる。
    """
    if blocked.is_permanent:
        period = '恒久（解除するまで）'
    else:
        period = f'{blocked.expires_at:%Y-%m-%d %H:%M} まで'

    body = (
        '参加フォームの連続送信を検知したため、以下の IP を遮断しました。\n\n'
        f'IP　　　　: {blocked.ip}\n'
        f'遮断回数　: {blocked.block_count}回目\n'
        f'期間　　　: {period}\n'
        f'理由　　　: {blocked.reason}\n\n'
        '■ 巻き添えの可能性について\n'
        '大学の構内ネットワークや携帯回線では、多数の人が同じ IP を共有しています。\n'
        '攻撃ではなく、無関係な方が巻き込まれている場合があります。\n'
        '心当たりのない遮断は、期限切れを待つか、下記から解除してください。\n\n'
        '■ 解除のしかた\n'
        '/admin/ →「遮断IP」→ 対象を選んで「今すぐ解除する」\n\n'
        '■ 自分が遮断されて /admin/ に入れないとき\n'
        'App Service のアプリケーション設定に IP_BLOCK_EXEMPT=<自分のIP> を追加すると\n'
        '遮断より優先して通ります（手順は deploy.txt の「メール送信」を参照）。\n'
    )

    notify_admins(
        subject=f'IP を遮断しました: {blocked.ip}',
        body=body,
        kind='ip-block',
        max_per_hour=settings.IP_BLOCK_NOTIFY_MAX_PER_HOUR,
    )
