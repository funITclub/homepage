# console/models.py
#
# ページビューの記録。日ごと・パスごとの件数（とページの題名）と、ボタンが押された回数だけを持つ。
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
    #: ページの <title>（最後に数えたときのもの）。コンソールでページ名を出すのに使う
    title = models.CharField('ページの題名', max_length=255, blank=True, default='')

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
    def record(cls, date, path, title=''):
        """1回ぶん数える。同時に来ても取りこぼさないよう、足し算は DB にさせる。"""
        _count_up(cls, {'date': date, 'path': path}, title=title[:255])


class ActionCount(models.Model):
    """ある日に、あるボタンが押された回数。誰が押したかは残さない。"""

    #: 数えるボタン。値はコンソールに出す名前
    ACTIONS = {
        'join_apply': '申し込みページの「申し込む」ボタン',
    }

    date = models.DateField('日付')
    name = models.CharField('ボタン', max_length=50)
    count = models.PositiveIntegerField('押された回数', default=0)

    class Meta:
        db_table = 'funitclub_actioncount'
        ordering = ['-date', 'name']
        constraints = [
            models.UniqueConstraint(fields=['date', 'name'], name='funitclub_actioncount_date_name'),
        ]
        verbose_name = 'ボタンの回数'
        verbose_name_plural = 'ボタンの回数'

    def __str__(self):
        return f'{self.date} {self.name} {self.count}'

    @classmethod
    def record(cls, date, name):
        _count_up(cls, {'date': date, 'name': name})


def _count_up(model, key, **fields):
    """key の行の count を 1 足す（無ければ作る）。fields は一緒に書き換える値。"""
    rows = model.objects.filter(**key)
    if rows.update(count=F('count') + 1, **fields):
        return
    try:
        with transaction.atomic():
            model.objects.create(count=1, **key, **fields)
    except IntegrityError:
        # 別のリクエストが先に行を作った
        rows.update(count=F('count') + 1, **fields)
