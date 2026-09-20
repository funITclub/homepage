# wgjoin/mail.py
#
# 確認のメール。入力されたアドレスに届く。
#
# 画面には、メンバーかどうかにかかわらず「メールを送りました」とだけ出す（他人のアドレスを
# 入れて、その人がメンバーかを探れないように）。結果はメールの中身で本人にだけ伝える。
# 他人がアドレスを入れた場合にも届くので、心当たりがない場合の案内を必ず入れる。
# 本文には入力された内容を載せない（第三者に読ませる文章を作れないように）。

from django.conf import settings
from django.core.mail import EmailMessage

from edit.models import public_contact_email


def _footer(contact):
    return (
        '■ このメールに心当たりがない場合\n'
        '第三者があなたのメールアドレスを入力した可能性があります。\n'
        'このメールを破棄していただければ、手続きは進みません。\n'
        f'気になる場合は {contact} までお知らせください。\n\n'
        '--\n'
        f'{settings.SITE_NAME}（{settings.SITE_TAGLINE}）\n'
        'このメールは自動送信です。\n'
    )


def send_link(email, wg, url, repo, guide_url):
    """メンバーあて。リンクを開くと GitHub の登録に進む。"""
    contact = public_contact_email()
    minutes = settings.WG_JOIN_LINK_MAX_AGE // 60
    EmailMessage(
        subject=f'[{settings.SITE_NAME}] {wg.name} への参加の確認',
        body=(
            f'「{wg.code} {wg.name}」への参加の手続きを受け付けました。\n\n'
            f'次のリンクを開くと、GitHub の WG のチームへの登録に進みます（{minutes}分以内）。\n'
            f'{url}\n\n'
            'WG の Chat には、Classroom のクラブのクラスの「授業」にある\n'
            f'{wg.name} のリンクから入ってください。\n\n'
            'WG のリポジトリ（パソコンの準備で VS Code にクローンするもの）:\n'
            f'{repo}\n\n'
            '■ 次にすること\n'
            'パソコンの準備（VS Code と Docker Desktop）をします。手順は資料 02 にあります。\n'
            f'{guide_url}\n\n'
            + _footer(contact)
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
        reply_to=[contact],
    ).send()


def send_not_member(email, wg, join_url):
    """クラブのクラスにいないアドレスあて。"""
    contact = public_contact_email()
    EmailMessage(
        subject=f'[{settings.SITE_NAME}] {wg.name} への参加について',
        body=(
            f'「{wg.code} {wg.name}」への参加の手続きがありましたが、\n'
            'このアドレスは fun IT club のメンバー（Classroom のクラブのクラス）として\n'
            '確認できませんでした。WG に参加できるのはメンバーだけです。\n\n'
            'まだクラブに登録していない方は、先に参加の申し込みをしてください。\n'
            f'{join_url}\n\n'
            '申し込み済みの方は、Classroom に登録しているアドレスで手続きしてください。\n\n'
            + _footer(contact)
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
        reply_to=[contact],
    ).send()
