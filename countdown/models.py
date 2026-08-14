# countdown/models.py
#
# hirahira_room の countdown アプリからの移植。
# あちらはユーザーごとの個人用（CountEvent.user への外部キーあり）だが、
# funITclub には会員登録が無いため、誰でも読み書きできる共有ボードにしている。
# 日数の数え方（経過・残り・週・周年）はそのまま引き継いだ。

from django.db import models
from django.utils import timezone


class CountEvent(models.Model):
    """カウントアップ／カウントダウンの対象となる出来事・予定。"""

    name = models.CharField('名前', max_length=50)
    date = models.DateField('日付')
    memo = models.TextField('メモ', max_length=300, blank=True)
    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)

    class Meta:
        db_table = 'funitclub_countevent'
        ordering = ['date']
        verbose_name = 'カウント対象'
        verbose_name_plural = 'カウント対象'

    def __str__(self):
        return self.name

    @property
    def days_delta(self):
        """今日から見た日数差。未来なら正、過去なら負、当日は0。"""
        return (self.date - timezone.localdate()).days

    @property
    def is_today(self):
        return self.days_delta == 0

    @property
    def is_upcoming(self):
        """未来の予定（カウントダウン対象）。"""
        return self.days_delta > 0

    @property
    def is_past(self):
        """過去の出来事（カウントアップ対象）。"""
        return self.days_delta < 0

    @property
    def count_days(self):
        """画面に表示する日数（常に0以上）。未来は残り日数、過去は経過日数。"""
        return abs(self.days_delta)

    @property
    def count_label(self):
        """日数の意味を表すラベル。"""
        if self.is_today:
            return '当日'
        return '残り' if self.is_upcoming else '経過'

    @property
    def weeks_and_days(self):
        """日数の補足表示用。(週数, 端数の日数)。"""
        return divmod(self.count_days, 7)

    @property
    def years_passed(self):
        """過去の出来事の周年数（何回目の記念日を迎えたか）。"""
        if not self.is_past:
            return 0
        today = timezone.localdate()
        years = today.year - self.date.year
        if (today.month, today.day) < (self.date.month, self.date.day):
            years -= 1
        return years
