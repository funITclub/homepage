"""基本情報の問題メールを、ある時間帯の分だけ送る。

通常は GitHub Actions（.github/workflows/fe-mails.yml）が9〜18時の毎時に /fe/tasks/send-mails/ を
呼んで送る。手で送りたいとき・確かめたいときに使う。同じ日の同じ時間帯には、
同じ登録へ1通しか送らないので、何度流してもよい。

    python manage.py send_fe_mails --slot h09 --settings=config.settings_dev
    python manage.py send_fe_mails --slot h18 --date 2026-11-11 --settings=config.settings_dev
"""

import datetime

from django.core.management.base import BaseCommand, CommandError

from works.fe.mail import send_slot
from works.fe.slots import HOURLY_SLOTS


class Command(BaseCommand):
    help = '基本情報の問題メールを、ある時間帯（h09〜h18）の分だけ送る。'

    def add_arguments(self, parser):
        parser.add_argument('--slot', required=True, choices=HOURLY_SLOTS, help='時間帯（h09〜h18）')
        parser.add_argument('--date', help='枠の日付（YYYY-MM-DD。省略すると今日。枠の時刻が12時間を超えて先なら前の日）')

    def handle(self, *args, slot, date=None, **options):
        today = None
        if date:
            try:
                today = datetime.date.fromisoformat(date)
            except ValueError as e:
                raise CommandError('日付は YYYY-MM-DD で指定してください。') from e
        result = send_slot(slot, today=today)
        self.stdout.write(self.style.SUCCESS(
            '{sent} 通を送りました（送り済み {already}・失敗 {failed}・期限切れで消した問題 {purged}）。'.format(**result)
        ))
