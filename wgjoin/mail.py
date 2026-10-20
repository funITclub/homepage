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

from edit.models import notification_emails, public_contact_email


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
    if wg.chat_space:
        chat_step, chat_note = 'WG の Chat スペースへの追加と、', ''
    else:
        chat_step = ''
        chat_note = ('WG の Chat には、Classroom のクラブのクラスの「授業」にある\n'
                     f'{wg.name} のリンクから入ってください。\n\n')
    EmailMessage(
        subject=f'[{settings.SITE_NAME}] {wg.name} への参加の確認',
        body=(
            f'「{wg.code} {wg.name}」への参加の手続きを受け付けました。\n\n'
            f'次のリンクを開くと、{chat_step}GitHub の WG のチームへの登録に進みます（{minutes}分以内）。\n'
            f'{url}\n\n'
            + chat_note +
            'WG のリポジトリ（パソコンの準備で VS Code にクローンするもの）:\n'
            f'{repo}\n\n'
            '■ 次にすること\n'
            '1. パソコンの準備（資料 02）… VS Code と Docker Desktop を入れる。初回だけ\n'
            '2. 開発の進め方（資料 03）… 作業するときの流れ\n'
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
            '申し込み済みの方は、Google Classroom から届いた招待の「参加」を押してから、もう一度お試しください。\n'
            'すでにクラスに参加している方は、Classroom に登録しているアドレスで手続きしてください。\n\n'
            + _footer(contact)
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
        reply_to=[contact],
    ).send()


def send_chat_failed(email, wg):
    """運営あて。Chat スペースに自動で追加できなかったことを知らせる。失敗したときだけ。

    本人には結果の画面でスペースのリンクから入るよう案内している。入っていなければ手で追加する。
    """
    EmailMessage(
        subject=f'[{settings.SITE_NAME}] {wg.code} の Chat スペースに追加できませんでした',
        body=(
            f'「{wg.code} {wg.name}」の「WG に参加」で、Chat スペースへの自動の追加に失敗しました。\n'
            'GitHub の手続きは続けています。本人にはスペースのリンクから参加するよう案内しました。\n'
            '参加していなければ、次の人をスペースに追加してください。\n\n'
            f'メールアドレス: {email}\n'
            f'Chat スペース : {wg.chat_space}\n\n'
            '失敗の理由は、別に届くエラーの通知にあります（運営の許可が切れた・スペースの管理者でない、など）。\n'
            '--\n'
            'このメールは公開サイトの「WG に参加」から自動送信しています。\n'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=notification_emails(),
    ).send()
