# 公開する問い合わせ先を、大学アカウントから役割アドレスに切り替える。
#
# 大学アカウントのローカル部は学籍番号そのもので、公開ページに出すと特定の学生の
# 学籍番号がサイトと紐づいて恒久的に晒される。役割アドレス（contact@funitclub.org）は
# 転送で受け取るので、担当者が代わっても転送先を変えるだけで済む。
#
# 通知の宛先は大学アカウントのまま（実際に読むのはそちらの受信箱）。
# 役割アドレスは転送なので、通知を送ると同じ受信箱に二重で届いてしまう。

from django.conf import settings
from django.db import migrations


def add_role_address(apps, schema_editor):
    Administrator = apps.get_model('edit', 'Administrator')

    Administrator.objects.update_or_create(
        email=settings.PUBLIC_CONTACT_EMAIL,
        defaults={
            'name': 'fun IT club 事務局',
            'is_public_contact': True,
            'receives_notifications': False,
            'sort_order': -1,
        },
    )
    # 大学アカウントは通知の受け取り専用にする
    Administrator.objects.filter(email=settings.JOIN_NOTIFY_EMAIL).update(
        is_public_contact=False)


def remove_role_address(apps, schema_editor):
    Administrator = apps.get_model('edit', 'Administrator')
    Administrator.objects.filter(email=settings.PUBLIC_CONTACT_EMAIL).delete()
    Administrator.objects.filter(email=settings.JOIN_NOTIFY_EMAIL).update(
        is_public_contact=True)


class Migration(migrations.Migration):

    dependencies = [
        ('edit', '0002_seed_administrator'),
    ]

    operations = [
        migrations.RunPython(add_role_address, remove_role_address),
    ]
