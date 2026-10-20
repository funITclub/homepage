# home/forms.py
#
# 参加フォーム（/join/）。hirahira_room の InquiryForm と同じ作りで、
# モデルは持たず、入力内容をメールで送るだけ（DB には残さない）。
#
# 申し込みは大学から発行されたメールアドレスからのみ受け付ける
# （settings.JOIN_ALLOWED_EMAIL_DOMAIN）。活動ツールが大学の
# Google Workspace 前提なので、私用アドレスでは受け付けても先に進めないため。
#
# ※ 自由記述（メッセージ欄）は意図的に持たせていない。復活させないこと。
#   入力されたアドレスが本人のものか確認していないため、他人のアドレスを入れて
#   自動返信を第三者に届けられる。自由記述があると、その本文に任意の文章を
#   載せられてしまい、フィッシングの配送路になる（差出人は SPF/DKIM/DMARC が
#   通った funitclub.org なので、受信側の認証チェックはすべて成功する）。
#   聞きたいことは、届いた自動返信に返信してもらえば事務局に届く。
#
# 入力はメールアドレスだけ。お名前と興味のある WG の欄は 2026-10-20 になくした
# （クラスへの招待には要らず、個人情報はなるべく受け取らない）。名前は、クラスに
# 参加すれば Classroom の名簿に大学のアカウントの名前で出る。

from django import forms
from django.conf import settings
from django.core.mail import EmailMessage, get_connection

from edit.models import notification_emails, public_contact_email
from wgjoin import google
from wgjoin.config import club_classroom_url

#: 事務局への通知に書く、クラブのクラスへの招待の結果（views.JoinApplyView）。
#: 招待できた・もうクラスにいるときは事務局に知らせない（会の運営に介入しない）ので、
#: 手作業が要る2つだけ。
CLASSROOM_NOTES = {
    'failed': '招待を送れませんでした。手作業で招待してください',
    None: '自動の招待は使っていません。手作業で招待してください',
}


class JoinForm(forms.Form):
    """参加の申し込み。申込者への自動返信を送る（クラスに招待できなかったときは事務局にも）。"""

    email = forms.EmailField(
        label='大学のメールアドレス',
        help_text='大学から発行された @{} のアドレスのみ受け付けます。'.format(
            settings.JOIN_ALLOWED_EMAIL_DOMAIN),
        widget=forms.EmailInput(
            attrs={'placeholder': '例: bu0000000000@{}'.format(
                settings.JOIN_ALLOWED_EMAIL_DOMAIN)},
        ),
    )

    def clean_email(self):
        """佛教大学のドメインだけを通す。"""
        email = self.cleaned_data['email']
        domain = email.rsplit('@', 1)[-1].lower()
        if domain != settings.JOIN_ALLOWED_EMAIL_DOMAIN:
            raise forms.ValidationError(
                '大学から発行されたメールアドレス（@{}）を入力してください。'.format(
                    settings.JOIN_ALLOWED_EMAIL_DOMAIN))
        return email

    def send_email(self, classroom=None):
        """申込者への自動返信を送る。手作業が要るときは事務局への通知も1本の接続でまとめて送る。

        classroom はクラブのクラスへの招待の結果（google.MEMBER / 'failed' / None＝招待していない）。
        招待できたとき（google.INVITED）は呼ばない。MEMBER は事務局に知らせない。
        """
        email = self.cleaned_data['email']
        summary = f'メールアドレス: {email}'

        # 差出人は「fun IT club <no-reply@funitclub.org>」で統一する（settings の既定値）。
        # 宛先と問い合わせ先は管理者テーブル（edit.Administrator）から取る。
        from_email = settings.DEFAULT_FROM_EMAIL
        notify_to = notification_emails()
        contact = public_contact_email()

        messages = []
        if classroom in CLASSROOM_NOTES:
            # 事務局あて。そのまま返信すれば申込者に届くよう Reply-To を申込者にする。
            messages.append(self._notification(email, summary, classroom, from_email, notify_to))

        # 申込者あての控え。問い合わせ先は事務局アドレス。
        # 申し込みフォームは入力されたアドレスの持ち主を確認していないので、
        # 第三者が他人のアドレスを入れた場合にもこのメールが届く。受け取った人が
        # 戸惑わないよう、身に覚えがない場合の案内を必ず入れておく。
        auto_reply = EmailMessage(
            subject=f'[{settings.SITE_NAME}] 参加申し込みを受け付けました',
            body=(
                f'{settings.SITE_NAME} への参加申し込みをありがとうございます。\n'
                + _next_step(classroom, summary, contact) +
                '■ このメールに心当たりがない場合\n'
                '第三者があなたのメールアドレスを入力した可能性があります。\n'
                'このメールを破棄していただければ、手続きは進みません。\n'
                f'気になる場合は {contact} までお知らせください。\n\n'
                '--\n'
                f'{settings.SITE_NAME}（{settings.SITE_TAGLINE}）\n'
                'このメールは自動送信です。ご質問はこのまま返信してください。\n'
            ),
            from_email=from_email,
            to=[email],
            reply_to=[contact],
        )

        messages.append(auto_reply)
        connection = get_connection()
        connection.send_messages(messages)

    @staticmethod
    def _notification(email, summary, classroom, from_email, notify_to):
        return EmailMessage(
            subject=f'[{settings.SITE_NAME}] 参加申し込み（手作業での招待が必要）',
            body=(
                '公開サイトの参加フォームから申し込みがありました。\n\n'
                f'{summary}\n'
                f'Classroom　　 : {CLASSROOM_NOTES[classroom]}\n\n'
                '--\n'
                'このメールは公開サイト（/join/）から自動送信しています。\n'
                'このまま返信すると申込者に届きます。\n'
            ),
            from_email=from_email,
            to=notify_to,
            reply_to=[email],
        )


def _next_step(classroom, summary, contact):
    """控えのメールの、受け付けた内容と次にすること。"""
    # 招待できたとき（google.INVITED）は送らない（views.JoinApplyView）
    if classroom == google.MEMBER:
        return (
            '以下の内容で受け付けました。\n\n'
            f'{summary}\n\n'
            f'このアドレスは、すでに {settings.SITE_NAME} の Google Classroom のクラスに登録されています。\n'
            f'{club_classroom_url()}\n'
            'サイトの WG 一覧の「WG に参加」から WG に入れます。\n\n'
        )
    return (
        '以下の内容で受け付けました。担当者から7日以内に折り返しご連絡します。\n'
        'それまでにお手続きいただくことはありません。\n\n'
        f'{summary}\n\n'
        '■ 7日を過ぎても連絡がない場合\n'
        '行き違いの可能性がありますので、\n'
        f'{contact} までお知らせください。\n\n'
    )
