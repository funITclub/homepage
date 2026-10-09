# countdown/forms.py

from django import forms

from .models import Board, CountEvent

# /countdown/ 直下のほかの画面と同じ名前は、ID ごとの一覧の URL（/countdown/<ID>/）と
# ぶつかるので ID にできない。
RESERVED_CODES = {'events', 'enter', 'notify'}


class BoardForm(forms.Form):
    """ID の入力。入るときは既にある ID、作るときはまだ無い ID を受け付ける。

    打ち間違えた ID で新しく作ってしまわないよう、「入る」と「作る」を分ける。
    """

    code = forms.CharField(
        label='ID', max_length=30,
        widget=forms.TextInput(attrs={
            'autocomplete': 'username', 'autocapitalize': 'none', 'spellcheck': 'false',
        }),
        help_text='半角の英小文字・数字・「_」「-」で、3〜30文字。',
    )

    def __init__(self, *args, creating=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.creating = creating
        self.board = None

    def clean_code(self):
        code = self.cleaned_data['code'].strip().lower()
        for validator in Board._meta.get_field('code').validators:
            validator(code)
        exists = Board.objects.filter(code=code).first()
        if self.creating:
            if code in RESERVED_CODES:
                raise forms.ValidationError('この ID は使えません。別の ID にしてください。')
            if exists:
                raise forms.ValidationError('その ID は既に使われています。')
        else:
            if exists is None:
                raise forms.ValidationError(
                    'その ID はまだありません。初めてなら「新しく作る」を押してください。'
                )
            self.board = exists
        return code


class NotifyEmailForm(forms.Form):
    """通知先のアドレス。確認のメールを送る先でもある。"""

    email = forms.EmailField(
        label='メールアドレス', max_length=254,
        widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
        help_text='このアドレスに確認のメールを送ります。メールのリンクを開くと登録されます。',
    )

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class CountEventForm(forms.ModelForm):
    """出来事・予定。メール通知の印は、通知先を持てる ID の一覧でだけ出す。"""

    class Meta:
        model = CountEvent
        fields = ['name', 'date', 'memo', 'notify']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': '例: 部会、発表会、設立日'}),
            'date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'memo': forms.Textarea(attrs={'rows': 3, 'placeholder': 'メモ（任意）'}),
        }

    def __init__(self, *args, board=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].input_formats = ['%Y-%m-%d']
        self.fields['date'].help_text = (
            '今日より後なら残り日数のカウントダウン、'
            '今日より前なら経過日数のカウントアップになります。'
        )
        if board is None:
            del self.fields['notify']
        else:
            help_text = (
                '当日まで毎日0時ごろに、残り日数をメールで知らせます'
                '（印を付けたカウントダウンを1通にまとめます）。過ぎた日付には送りません。'
            )
            if not board.notify_email:
                help_text += (
                    '通知先のメールアドレスがまだ登録されていません。'
                    '一覧の「メール通知」から登録すると届くようになります。'
                )
            self.fields['notify'].help_text = help_text
