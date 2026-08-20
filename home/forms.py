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

from django import forms
from django.conf import settings
from django.core.mail import EmailMessage, get_connection

from catalog.models import Wg
from edit.models import notification_emails, public_contact_email


class JoinForm(forms.Form):
    """参加の申し込み。事務局への通知と、申込者への自動返信を送る。"""

    name = forms.CharField(
        label='お名前',
        max_length=30,
        widget=forms.TextInput(attrs={'placeholder': '例: 佛教 太郎'}),
    )
    email = forms.EmailField(
        label='大学のメールアドレス',
        help_text='大学から発行された @{} のアドレスのみ受け付けます。'.format(
            settings.JOIN_ALLOWED_EMAIL_DOMAIN),
        widget=forms.EmailInput(
            attrs={'placeholder': '例: bu0000000000@{}'.format(
                settings.JOIN_ALLOWED_EMAIL_DOMAIN)},
        ),
    )
    wg = forms.ModelChoiceField(
        label='興味のあるWG',
        queryset=Wg.objects.none(),  # 実際の候補は __init__ で入れる
        required=False,
        empty_label='まだ決めていない・相談したい',
        help_text='あとから変えられます。迷ったら空欄のままで構いません。',
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 公開中のWGだけを候補にする。毎回引き直したいので __init__ で入れる。
        self.fields['wg'].queryset = Wg.objects.published()

    def clean_name(self):
        """氏名に URL を書かせない。

        自動返信は入力されたアドレス宛に届くので、氏名欄も第三者に読まれる文章に
        なる（冒頭の「○○ 様」と本文の「お名前」）。短縮URLなら30文字に収まるため、
        ここを塞いでおかないとリンクを第三者に届けられる。
        """
        name = self.cleaned_data['name']
        lowered = name.lower()
        if any(token in lowered for token in ('http', 'www.', '://')):
            raise forms.ValidationError('お名前に URL は入力できません。')
        return name

    def clean_email(self):
        """佛教大学のドメインだけを通す。"""
        email = self.cleaned_data['email']
        domain = email.rsplit('@', 1)[-1].lower()
        if domain != settings.JOIN_ALLOWED_EMAIL_DOMAIN:
            raise forms.ValidationError(
                '大学から発行されたメールアドレス（@{}）を入力してください。'.format(
                    settings.JOIN_ALLOWED_EMAIL_DOMAIN))
        return email

    def send_email(self):
        """事務局への通知と、申込者への自動返信を1本の接続でまとめて送る。"""
        name = self.cleaned_data['name']
        email = self.cleaned_data['email']
        wg = self.cleaned_data['wg']

        wg_label = f'{wg.code} {wg.name}' if wg else '未定'
        summary = '\n'.join([
            f'お名前　　　　: {name}',
            f'メールアドレス: {email}',
            f'興味のあるWG　: {wg_label}',
        ])

        # 差出人は「fun IT club <no-reply@funitclub.org>」で統一する（settings の既定値）。
        # 宛先と問い合わせ先は管理者テーブル（edit.Administrator）から取る。
        from_email = settings.DEFAULT_FROM_EMAIL
        notify_to = notification_emails()
        contact = public_contact_email()

        # 事務局あて。そのまま返信すれば申込者に届くよう Reply-To を申込者にする。
        notification = EmailMessage(
            subject=f'[{settings.SITE_NAME}] 参加申し込み: {name}',
            body=(
                '公開サイトの参加フォームから申し込みがありました。\n\n'
                f'{summary}\n\n'
                '--\n'
                'このメールは公開サイト（/join/）から自動送信しています。\n'
                'このまま返信すると申込者に届きます。\n'
            ),
            from_email=from_email,
            to=notify_to,
            reply_to=[email],
        )

        # 申込者あての控え。問い合わせ先は事務局アドレス。
        # 申し込みフォームは入力されたアドレスの持ち主を確認していないので、
        # 第三者が他人のアドレスを入れた場合にもこのメールが届く。受け取った人が
        # 戸惑わないよう、身に覚えがない場合の案内を必ず入れておく。
        auto_reply = EmailMessage(
            subject=f'[{settings.SITE_NAME}] 参加申し込みを受け付けました',
            body=(
                f'{name} 様\n\n'
                f'{settings.SITE_NAME} への参加申し込みをありがとうございます。\n'
                '以下の内容で受け付けました。担当者から7日以内に折り返しご連絡します。\n'
                'それまでにお手続きいただくことはありません。\n\n'
                f'{summary}\n\n'
                '■ 7日を過ぎても連絡がない場合\n'
                '行き違いの可能性がありますので、\n'
                f'{contact} までお知らせください。\n\n'
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

        connection = get_connection()
        connection.send_messages([notification, auto_reply])
