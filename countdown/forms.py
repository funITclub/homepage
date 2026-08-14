# countdown/forms.py

from django import forms

from .models import CountEvent


class CountEventForm(forms.ModelForm):

    class Meta:
        model = CountEvent
        fields = ['name', 'date', 'memo']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': '例: 部会、発表会、設立日'}),
            'date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'memo': forms.Textarea(attrs={'rows': 3, 'placeholder': 'メモ（任意）'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].input_formats = ['%Y-%m-%d']
        self.fields['date'].help_text = (
            '今日より後なら残り日数のカウントダウン、'
            '今日より前なら経過日数のカウントアップになります。'
        )
