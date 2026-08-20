# 運営の連絡先を登録する。宛先は設定から取り、コードには実アドレスを書かない。
#
# 以降、通知の宛先と公開ページの問い合わせ先はこのテーブルだけを見る。
# 増減は admin（/admin/ → 管理者）から行う。

from django.conf import settings
from django.db import migrations


def add_current_account(apps, schema_editor):
    Administrator = apps.get_model('edit', 'Administrator')
    Administrator.objects.get_or_create(
        email=settings.JOIN_NOTIFY_EMAIL,
        defaults={'name': '事務局', 'sort_order': 0},
    )


def remove_current_account(apps, schema_editor):
    Administrator = apps.get_model('edit', 'Administrator')
    Administrator.objects.filter(email=settings.JOIN_NOTIFY_EMAIL).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('edit', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_current_account, remove_current_account),
    ]
