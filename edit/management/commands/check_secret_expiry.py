# SMTP のシークレット期限を点検して、近ければ管理者に通知する。
#
# 通常は日次のゲート（edit.checks.run_daily_checks）が自動で走らせるので、
# このコマンドは手元での確認や、スケジューラから明示的に叩きたいときに使う。

from django.core.management.base import BaseCommand

from edit.checks import secret_expiry_date, warn_if_secret_expiring


class Command(BaseCommand):
    help = 'SMTP のシークレット期限を点検し、近ければ管理者に通知する'

    def handle(self, *args, **options):
        expires_on = secret_expiry_date()
        if expires_on is None:
            self.stdout.write(self.style.WARNING(
                'EMAIL_SECRET_EXPIRES_ON が未設定です。点検できません。'))
            return

        from datetime import date
        remaining = (expires_on - date.today()).days
        self.stdout.write(f'期限: {expires_on}（残り{remaining}日）')

        warn_if_secret_expiring()
        self.stdout.write('点検しました（必要なら通知を送りました）。')
