# news/models.py
#
# TOP のお知らせ。テンプレート直書きだった内容をモデル化したもの。
# 保存先は funITclub 専用データベース（hirahira_room とは別DB・同じ PostgreSQL サーバー）。
# 万一 DB_NAME が共有DBを向いてもテーブル名が衝突しないよう db_table を明示する。

from django.db import models
from django.utils import timezone


class NewsQuerySet(models.QuerySet):

    def published(self):
        """公開中のお知らせだけを返す（掲載日が未来のものは出さない）。"""
        return self.filter(is_published=True, published_on__lte=timezone.localdate())


class News(models.Model):
    """TOP に載せるお知らせ1件。"""

    published_on = models.DateField(
        '掲載日',
        default=timezone.localdate,
        help_text='一覧では新しい順に並びます。',
    )
    text = models.CharField(
        '本文',
        max_length=200,
        help_text='TOP に1行で表示されます。',
    )
    badge = models.CharField(
        'バッジ',
        max_length=20,
        blank=True,
        help_text='右端に出る小さなラベル（例: イベント / GitHub）。空欄なら表示しません。',
    )
    is_new = models.BooleanField(
        'NEW を付ける',
        default=False,
        help_text='バッジの代わりに NEW を強調表示します。',
    )
    is_published = models.BooleanField(
        '公開する',
        default=True,
        help_text='外すと下書き扱いになり、TOP には出ません。',
    )
    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)

    objects = NewsQuerySet.as_manager()

    class Meta:
        db_table = 'funitclub_news'
        ordering = ['-published_on', '-id']
        verbose_name = 'お知らせ'
        verbose_name_plural = 'お知らせ'

    def __str__(self):
        return f'{self.published_on} {self.text}'
