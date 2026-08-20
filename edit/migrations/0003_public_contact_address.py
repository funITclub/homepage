# 公開する問い合わせ先を役割アドレス（settings.PUBLIC_CONTACT_EMAIL）にする。
#
# 個人の大学アカウントはローカル部が学籍番号そのもので、公開すると恒久的に晒される。
# 役割アドレスは転送で受け取るので、担当者が代わっても転送先を変えるだけで済む。
#
# 通知の宛先（settings.JOIN_NOTIFY_EMAIL）を別に設定している場合は、そちらは公開せず
# 受け取り専用にする。役割アドレスへ通知を送ると、転送で同じ受信箱に二重で届くため。

from django.conf import settings
from django.db import migrations


def add_role_address(apps, schema_editor):
    Administrator = apps.get_model('edit', 'Administrator')

    # 通知先が未設定（＝役割アドレスと同じ）なら、1件で両方を兼ねる。
    # 分けてしまうと通知を受け取る行が無くなる。
    same = settings.PUBLIC_CONTACT_EMAIL == settings.JOIN_NOTIFY_EMAIL

    Administrator.objects.update_or_create(
        email=settings.PUBLIC_CONTACT_EMAIL,
        defaults={
            'name': 'fun IT club 事務局',
            'is_public_contact': True,
            'receives_notifications': same,
            'sort_order': -1,
        },
    )

    if not same:
        # 通知用の受信箱は公開しない
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
