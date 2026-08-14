# catalog/models.py
#
# 公開サイトに載せる WG と成果物。テンプレート直書きだった内容をモデル化したもの。
# 保存先は funITclub 専用データベース。お知らせ（news）と同じく、万一 DB_NAME が
# 共有DBを向いてもテーブル名が衝突しないよう db_table を明示する。

from django.db import models


class PublishedQuerySet(models.QuerySet):

    def published(self):
        """公開中のものだけを返す。"""
        return self.filter(is_published=True)


class Wg(models.Model):
    """WG（ワーキンググループ）1件。"""

    ACTIVE = 'active'
    IDLE = 'idle'
    STATUS_CHOICES = [
        (ACTIVE, '活動中'),
        (IDLE, '準備中'),
    ]

    code = models.CharField(
        '識別子',
        max_length=20,
        help_text='カードの上に出る番号（例: WG-01）。',
    )
    name = models.CharField('名前', max_length=60)
    description = models.TextField(
        '説明',
        max_length=300,
        help_text='カードの本文。2〜3行くらい。',
    )
    status = models.CharField(
        '状態',
        max_length=10,
        choices=STATUS_CHOICES,
        default=ACTIVE,
        help_text='「活動中」だけが TOP の「活動中のWG」件数に入ります。'
                  '「準備中」のカードには参加ボタンだけを出します。',
    )
    app_url = models.URLField(
        'Webアプリの URL',
        blank=True,
        help_text='空欄なら「作成中」ページに繋ぎます（活動中のWGのみ表示）。',
    )
    link_label = models.CharField(
        '追加リンクの名前',
        max_length=20,
        blank=True,
        help_text='2つ目のボタン（例: GitHub / 成果物レポート）。空欄なら出しません。',
    )
    link_url = models.URLField(
        '追加リンクの URL',
        blank=True,
        help_text='空欄なら「作成中」ページに繋ぎます。',
    )
    sort_order = models.IntegerField(
        '表示順',
        default=0,
        help_text='小さいほど先に出ます。同じ値なら識別子順。',
    )
    is_published = models.BooleanField(
        '公開する',
        default=True,
        help_text='外すと下書き扱いになり、WG一覧にも件数にも出ません。',
    )
    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        db_table = 'funitclub_wg'
        ordering = ['sort_order', 'code']
        verbose_name = 'WG'
        verbose_name_plural = 'WG'

    def __str__(self):
        return f'{self.code} {self.name}'

    @property
    def is_active(self):
        return self.status == self.ACTIVE


class Work(models.Model):
    """成果物1件。"""

    category = models.CharField(
        '種別',
        max_length=30,
        help_text='カードの上に出る分類（例: Web App / Model + API / Notebook）。',
    )
    title = models.CharField('題名', max_length=60)
    description = models.TextField(
        '説明',
        max_length=300,
        help_text='カードの本文。2〜3行くらい。',
    )
    license = models.CharField(
        'ライセンス',
        max_length=20,
        blank=True,
        help_text='カード右下のラベル（例: MIT / CC BY）。空欄なら出しません。',
    )
    url = models.URLField(
        '公開先の URL',
        blank=True,
        help_text='空欄なら「作成中」ページに繋ぎます。',
    )
    sort_order = models.IntegerField(
        '表示順',
        default=0,
        help_text='小さいほど先に出ます。同じ値なら新しい順。',
    )
    is_published = models.BooleanField(
        '公開する',
        default=True,
        help_text='外すと下書き扱いになり、成果物一覧にも件数にも出ません。',
    )
    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        db_table = 'funitclub_work'
        ordering = ['sort_order', '-id']
        verbose_name = '成果物'
        verbose_name_plural = '成果物'

    def __str__(self):
        return self.title
