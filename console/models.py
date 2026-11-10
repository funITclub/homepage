# console/models.py
#
# ページビューの記録。日ごと・パスごとの件数だけを持つ。
#
# 誰が見たか（IP・User-Agent・Cookie）は残さない。個人情報をシステムに持たない方針なので、
# 数えるのに要らないものは最初から受け取らない。

from django.db import IntegrityError, models, transaction
from django.db.models import F


class PageView(models.Model):
    """ある日の、あるページの表示回数。"""

    date = models.DateField('日付')
    path = models.CharField('パス', max_length=255)
    count = models.PositiveIntegerField('表示回数', default=0)

    class Meta:
        db_table = 'funitclub_pageview'
        ordering = ['-date', '-count', 'path']
        constraints = [
            models.UniqueConstraint(fields=['date', 'path'], name='funitclub_pageview_date_path'),
        ]
        verbose_name = 'ページビュー'
        verbose_name_plural = 'ページビュー'

    def __str__(self):
        return f'{self.date} {self.path} {self.count}'

    @classmethod
    def record(cls, date, path):
        """1回ぶん数える。同時に来ても取りこぼさないよう、足し算は DB にさせる。"""
        rows = cls.objects.filter(date=date, path=path)
        if rows.update(count=F('count') + 1):
            return
        try:
            with transaction.atomic():
                cls.objects.create(date=date, path=path, count=1)
        except IntegrityError:
            # 別のリクエストが先に行を作った
            rows.update(count=F('count') + 1)
