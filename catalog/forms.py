# catalog/forms.py

from django import forms

from wgjoin.links import is_wg_team

from .models import Wg, Work


class WgForm(forms.ModelForm):

    class Meta:
        model = Wg
        fields = [
            'code', 'name', 'description', 'status',
            'app_url', 'link_label', 'link_url',
            'github_team',
            'sort_order', 'is_published',
        ]
        widgets = {
            'code': forms.TextInput(attrs={'placeholder': '例: WG-01'}),
            'name': forms.TextInput(attrs={'placeholder': '例: データ可視化'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'link_label': forms.TextInput(attrs={'placeholder': '例: GitHub'}),
            'github_team': forms.TextInput(attrs={'placeholder': '例: wg-countdown'}),
        }

    def clean_github_team(self):
        team = self.cleaned_data['github_team'].strip()
        if team and not is_wg_team(team):
            raise forms.ValidationError(
                'wg- で始まる、英小文字・数字・ハイフンの名前にしてください（例: wg-countdown）。')
        return team


class WorkForm(forms.ModelForm):

    class Meta:
        model = Work
        fields = [
            'category', 'title', 'description', 'license',
            'url', 'sort_order', 'is_published',
        ]
        widgets = {
            'category': forms.TextInput(attrs={'placeholder': '例: Web App'}),
            'title': forms.TextInput(attrs={'placeholder': '例: 花の種類分類API'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'license': forms.TextInput(attrs={'placeholder': '例: CC BY'}),
        }
