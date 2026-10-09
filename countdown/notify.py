# countdown/notify.py
#
# カウントダウンのメール通知。
#
# 通知先 … ID（Board）ごとに1つ。登録は任意。ID には合言葉がなく、ID を知っている人なら
#          誰でも登録の操作ができるので、入力されたアドレスに確認のメールを送り、
#          そのリンクを開いて「受け取る」を押したアドレスだけを保存する。
#          確認を待つ間のアドレスはキャッシュに置き、期限（COUNTDOWN_CONFIRM_MAX_AGE）で消える。
#          DB にもキャッシュにも、暗号化して置く（countdown/crypto.py）。
#          リンクにアドレスは入れない。
# 送信   … 1日1通。印（CountEvent.notify）の付いた、当日を含むこれからの予定をまとめる。
#          対象がない日は送らない。同じ日に2通送らないよう Board.notified_on に控える。
# 解除   … 登録されたアドレスに届くメールのリンクからだけできる。解除するとアドレスを消す。
#          ID を知っている人が、画面から通知を止めたり自分のアドレスに差し替えたりできないよう、
#          通知先がある間は画面からの変更・解除を受け付けない（変えたいときは解除して登録し直す）。
#          解除のリンクは毎回の通知に付けるほか、画面から「解除用のメール」として
#          登録されたアドレスへ送れる（通知が届かない日でも止められるように）。
#
# アドレスはログに出さない。

import logging
import secrets
import smtplib

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.mail import BadHeaderError, EmailMessage
from django.urls import reverse
from django.utils import timezone

from edit.models import public_contact_email
from wgjoin.verify import _count, address_key

from .crypto import decrypt, encrypt
from .models import Board, board_url

logger = logging.getLogger(__name__)

CONFIRM_SALT = 'countdown.notify.confirm'
STOP_SALT = 'countdown.notify.stop'


class LinkInvalid(Exception):
    """リンクが壊れている・期限切れ・使用済み・いまの通知先のものではない。"""


def allow_send(ip, email):
    """確認のメールを送ってよいか（settings.COUNTDOWN_CONFIRM_SEND_LIMITS）。"""
    ip_limit, address_limit = settings.COUNTDOWN_CONFIRM_SEND_LIMITS
    ok = True
    if ip:
        ok = _count(f'countdown-confirm-ip:{ip}', *ip_limit) and ok
    ok = _count(f'countdown-confirm-addr:{address_key(email)}', *address_limit) and ok
    return ok


def _pending_key(nonce):
    return f'countdown-confirm:{nonce}'


def make_confirm_token(board, email):
    """確認のリンクに入れる値。アドレスはキャッシュに預け、リンクには番号だけを入れる。"""
    nonce = secrets.token_urlsafe(16)
    cache.set(_pending_key(nonce), encrypt(email), settings.COUNTDOWN_CONFIRM_MAX_AGE)
    return signing.dumps({'b': board.pk, 'n': nonce}, salt=CONFIRM_SALT)


def read_confirm_token(token, consume=False):
    """(Board, アドレス)。使えないリンクなら LinkInvalid。consume なら二度使えなくする。"""
    try:
        data = signing.loads(token, salt=CONFIRM_SALT, max_age=settings.COUNTDOWN_CONFIRM_MAX_AGE)
    except signing.BadSignature as e:  # SignatureExpired も含む
        raise LinkInvalid from e
    email = decrypt(cache.get(_pending_key(data['n'])))
    board = Board.objects.filter(pk=data['b']).first()
    # 通知先がすでにあるなら、差し替えになるので受け付けない
    if not email or board is None or board.notify_email:
        raise LinkInvalid
    if consume:
        cache.delete(_pending_key(data['n']))
    return board, email


def make_stop_token(board):
    """解除のリンクに入れる値。通知先が変わったら、前のアドレスあてのリンクは効かなくなる。"""
    return signing.dumps({'b': board.pk, 'a': address_key(board.notify_email)[:16]}, salt=STOP_SALT)


def read_stop_token(token):
    """Board。いまの通知先あてのリンクでなければ LinkInvalid。"""
    try:
        data = signing.loads(token, salt=STOP_SALT)
    except signing.BadSignature as e:
        raise LinkInvalid from e
    board = Board.objects.filter(pk=data['b']).first()
    if board is None or not board.notify_email:
        raise LinkInvalid
    if address_key(board.notify_email)[:16] != data['a']:
        raise LinkInvalid
    return board


def _footer():
    return (
        '--\n'
        f'{settings.SITE_NAME} カウントアップ＆ダウン\n'
        f'このメールは自動送信です。お問い合わせは {public_contact_email()} まで。\n'
    )


def send_confirmation(board, email, url):
    """入力されたアドレスあて。リンクを開いて「受け取る」を押すと通知先になる。"""
    minutes = settings.COUNTDOWN_CONFIRM_MAX_AGE // 60
    EmailMessage(
        subject=f'[{settings.SITE_NAME}] カウントダウンのメール通知の確認',
        body=(
            f'カウントアップ＆ダウンの ID「{board.code}」で、このアドレスを通知先にする手続きがありました。\n\n'
            f'次のリンクを開いて「受け取る」を押すと、登録されます（{minutes}分以内）。\n'
            f'{url}\n\n'
            '登録すると、印を付けたカウントダウンの残り日数が、当日まで毎日0時ごろに1通届きます。\n'
            '\n'
            '■ 解除について\n'
            '登録したあとは、このアドレスに届くメールのリンクからしか解除できません\n'
            '（画面からは変更も解除もできません）。解除のリンクは毎回の通知に付いています。\n'
            f'このアドレスのメールを受け取れなくなったときは、{public_contact_email()} までお知らせください。\n\n'
            '■ このメールに心当たりがない場合\n'
            '第三者があなたのメールアドレスを入力した可能性があります。\n'
            'このメールを破棄していただければ、登録されず、今後メールは届きません。\n\n'
            + _footer()
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    ).send()


def send_stop_link(board, url):
    """登録されているアドレスあて。リンクを開いて「通知を止める」を押すと解除される。"""
    EmailMessage(
        subject=f'[{settings.SITE_NAME}] カウントダウンのメール通知の解除',
        body=(
            f'カウントアップ＆ダウンの ID「{board.code}」で、メール通知を解除する手続きがありました。\n\n'
            '次のリンクを開いて「通知を止める」を押すと、通知が止まり、登録されているアドレスが消えます。\n'
            f'{url}\n\n'
            '■ このメールに心当たりがない場合\n'
            'この ID を知っている人が手続きをした可能性があります。\n'
            'このメールを破棄していただければ、通知はそのまま続きます。\n\n'
            + _footer()
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[board.notify_email],
    ).send()


def _line(event):
    count = '本日' if event.is_today else f'残り{event.count_days}日'
    return f'・{event.name}　{event.date:%Y-%m-%d}　{count}'


def send_daily(today=None):
    """今日の分を送る。送った通数を返す。何度呼んでも、同じ日に同じ ID へは1通だけ。

    1件の失敗でほかの ID を止めない。失敗したものは控えを進めないので、次に呼ばれたときに送り直す。
    """
    today = today or timezone.localdate()
    boards = (
        Board.objects.exclude(notify_email_enc='')
        .exclude(notified_on=today)
        .filter(events__notify=True, events__date__gte=today)
        .distinct()
    )
    sent = 0
    for board in boards:
        email = board.notify_email
        if not email:
            # 鍵が替わって読めなくなったもの。送れないので飛ばす
            continue
        events = board.events.filter(notify=True, date__gte=today).order_by('date', 'pk')
        base = settings.SITE_URL
        try:
            EmailMessage(
                subject=f'[{settings.SITE_NAME}] カウントダウン {today:%Y-%m-%d}（ID: {board.code}）',
                body=(
                    f'{today:%Y-%m-%d} のカウントダウンです。\n\n'
                    + '\n'.join(_line(e) for e in events) + '\n\n'
                    '一覧を開く:\n'
                    f'{base}{board_url(board, "list")}\n\n'
                    'メール通知を止める:\n'
                    f'{base}{reverse("countdown:notify_stop", args=[make_stop_token(board)])}\n\n'
                    + _footer()
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email],
            ).send()
        except (smtplib.SMTPException, OSError, BadHeaderError) as e:
            # 例外の文言には宛先のアドレスが入ることがあるので、種類だけ残す
            logger.error('カウントダウンの通知を送れませんでした（ID の番号 %s、%s）',
                         board.pk, type(e).__name__)
            continue
        Board.objects.filter(pk=board.pk).update(notified_on=today)
        sent += 1
    return sent
