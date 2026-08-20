# edit/models.py
#
# 運営（管理者）の連絡先。
#
# 通知メールの宛先も、公開ページに出す問い合わせ先も、すべてここを参照する。
# 設定ファイルやテンプレートにアドレスを書かないこと。担当者が代わったときに
# 追いきれなくなるうえ、HTML に個人のアカウントが残る。

from django.conf import settings
from django.db import models


class AdministratorQuerySet(models.QuerySet):

    def notified(self):
        """通知メールを受け取る管理者。"""
        return self.filter(is_active=True, receives_notifications=True)

    def public_contacts(self):
        """公開ページに載せてよい問い合わせ先。"""
        return self.filter(is_active=True, is_public_contact=True)


class Administrator(models.Model):
    """運営メンバーの連絡先1件。"""

    name = models.CharField(
        '名前',
        max_length=60,
        blank=True,
        help_text='メールの宛名や管理画面の表示に使います（例: 事務局）。',
    )
    email = models.EmailField('メールアドレス', unique=True)
    receives_notifications = models.BooleanField(
        '通知を受け取る',
        default=True,
        help_text='参加申し込み・IP遮断・エラーなどの通知メールが届きます。',
    )
    is_public_contact = models.BooleanField(
        '公開ページの問い合わせ先にする',
        default=True,
        help_text='アクセス制限の画面などに連絡先として表示されます。',
    )
    is_active = models.BooleanField(
        '有効',
        default=True,
        help_text='外すと通知も表示もされなくなります（記録は残ります）。',
    )
    sort_order = models.IntegerField(
        '表示順',
        default=0,
        help_text='小さいほど先に使われます。問い合わせ先は先頭の1件を出します。',
    )
    created_at = models.DateTimeField('登録日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)

    objects = AdministratorQuerySet.as_manager()

    class Meta:
        db_table = 'funitclub_administrator'
        ordering = ['sort_order', 'email']
        verbose_name = '管理者'
        verbose_name_plural = '管理者'

    def __str__(self):
        return f'{self.name} <{self.email}>' if self.name else self.email


def notification_emails():
    """通知メールの宛先。

    テーブルが空だったり DB を読めないときは settings.JOIN_NOTIFY_EMAIL に落とす。
    通知の宛先が無いせいで異常に気づけない、という事態を避けるための保険。
    """
    try:
        emails = list(Administrator.objects.notified().values_list('email', flat=True))
    except Exception:
        emails = []
    return emails or [settings.JOIN_NOTIFY_EMAIL]


def public_contact_email():
    """公開ページに出す問い合わせ先（先頭の1件）。

    予備は settings.PUBLIC_CONTACT_EMAIL（役割アドレス）にする。
    JOIN_NOTIFY_EMAIL に落とすと、テーブルを読めないときに個人の大学アカウントが
    公開ページへ出てしまう。学籍番号を含むアドレスなので、そちらには絶対に倒さない。
    """
    try:
        email = Administrator.objects.public_contacts().values_list(
            'email', flat=True).first()
    except Exception:
        email = None
    return email or settings.PUBLIC_CONTACT_EMAIL
