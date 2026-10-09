"""カウントダウンのメール通知を、今日の分だけ送る。

通常は GitHub Actions（.github/workflows/countdown-notify.yml）が毎日0時に
/countdown/notify/run/ を呼んで送る。手で送りたいとき・確かめたいときに使う。
同じ日に何度流しても、同じ ID には1通しか送らない。

    python manage.py send_countdown_mails
"""

from django.core.management.base import BaseCommand

from countdown.notify import send_daily


class Command(BaseCommand):
    help = 'カウントダウンのメール通知を、今日の分だけ送る。'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(
            'カウントダウンの通知を {} 通送りました。'.format(send_daily())
        ))
