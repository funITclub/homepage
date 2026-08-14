# news/forms.py

from django import forms

from .models import News


class NewsForm(forms.ModelForm):

    class Meta:
        model = News
        fields = ['published_on', 'text', 'badge', 'is_new', 'is_published']
        widgets = {
            'published_on': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date'},
            ),
            'text': forms.TextInput(
                attrs={'placeholder': '例: GitHubリポジトリを公開しました。'},
            ),
            'badge': forms.TextInput(
                attrs={'placeholder': '例: イベント'},
            ),
        }
