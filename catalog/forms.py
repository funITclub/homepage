# catalog/forms.py

from django import forms

from .models import Wg, Work


class WgForm(forms.ModelForm):

    class Meta:
        model = Wg
        fields = [
            'code', 'name', 'description', 'status',
            'app_url', 'link_label', 'link_url',
            'sort_order', 'is_published',
        ]
        widgets = {
            'code': forms.TextInput(attrs={'placeholder': '例: WG-01'}),
            'name': forms.TextInput(attrs={'placeholder': '例: データ可視化'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'link_label': forms.TextInput(attrs={'placeholder': '例: GitHub'}),
        }


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
