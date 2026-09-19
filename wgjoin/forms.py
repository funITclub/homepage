# wgjoin/forms.py

from django import forms
from django.conf import settings


class JoinEmailForm(forms.Form):
    """WG への参加の入口。大学のアドレスだけを受け付ける。"""

    email = forms.EmailField(
        label='大学のメールアドレス',
        help_text='クラブの Classroom に登録しているアドレス（@{}）。'.format(
            settings.JOIN_ALLOWED_EMAIL_DOMAIN),
        widget=forms.EmailInput(attrs={
            'placeholder': '例: bu0000000000@{}'.format(settings.JOIN_ALLOWED_EMAIL_DOMAIN),
            'autocomplete': 'email',
        }),
    )

    def clean_email(self):
        email = self.cleaned_data['email'].strip()
        if email.rsplit('@', 1)[-1].lower() != settings.JOIN_ALLOWED_EMAIL_DOMAIN:
            raise forms.ValidationError(
                '大学から発行されたメールアドレス（@{}）を入力してください。'.format(
                    settings.JOIN_ALLOWED_EMAIL_DOMAIN))
        return email
