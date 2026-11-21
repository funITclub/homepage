# console/models.py
#
# ページビューの記録。日ごと・パスごとの件数（とページの題名）、日ごとの訪問者数、ボタンが押された回数だけを持つ。
#
# 誰が見たか（IP・User-Agent・Cookie）は残さない。個人情報をシステムに持たない方針なので、
# 数えるのに要らないものは最初から受け取らない。

import logging

from django.db import IntegrityError, models, transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)


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


class DailyVisitors(models.Model):
    """ある日にサイトを訪れた人の数。同じブラウザはその日1人と数える（console.middleware）。

    数えたことはブラウザの Cookie（その日の日付だけ）で覚える。ID・IP は持たない。
    """

    date = models.DateField('日付', unique=True)
    count = models.PositiveIntegerField('訪問者数', default=0)

    class Meta:
        db_table = 'funitclub_dailyvisitors'
        ordering = ['-date']
        verbose_name = '訪問者数'
        verbose_name_plural = '訪問者数'

    def __str__(self):
        return f'{self.date} {self.count}'

    @classmethod
    def record(cls, date):
        _count_up(cls, {'date': date})

    @classmethod
    def on(cls, date):
        return cls.objects.filter(date=date).values_list('count', flat=True).first() or 0


class ActionCount(models.Model):
    """ある日に、あるボタンが押された回数。誰が押したかは残さない。"""

    #: 数えるボタン。値はコンソールに出す名前
    ACTIONS = {
        'join_apply': '申し込みページの「申し込む」ボタン',
    }

    #: WG への参加のボタン（name は「<キー>:<WG の pk>」）。値はコンソールに出す名前
    WG_JOIN_ACTIONS = {
        'wg_join_send': '「確認のメールを送る」ボタン',
        'wg_join_confirm': '「GitHub でログインして登録する」ボタン',
    }

    @classmethod
    def record_now(cls, request, name):
        """今日の分として数える。ログイン中の運営は数えない。失敗してもページの処理は止めない。"""
        if request.user.is_authenticated:
            return
        try:
            cls.record(timezone.localdate(), name)
        except Exception:
            logger.exception('ボタンの回数の記録に失敗しました')

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


class SuspiciousAccess(models.Model):
    """不審なアクセス（console.suspicious）。人のアクセスは残さない。

    「個人情報をシステムに持たない」方針の例外として、不審と判断したものだけ IP・User-Agent・
    パス・日時を残す（運営が決めた。遮断や調べものに使うため）。KEEP_DAYS より古いものは毎日消す。
    """

    PROBE = 'probe'
    FAKE_BROWSER = 'fake_browser'
    SCANNER = 'scanner'
    BLOCKED = 'blocked'
    BURST = 'burst'
    KINDS = {
        PROBE: '攻撃用のパスを探る',
        FAKE_BROWSER: '人のふりをしたロボット',
        SCANNER: '名乗っているスキャナー',
        BLOCKED: '遮断中の IP',
        BURST: '参加フォームの連続送信',
    }

    #: 残す日数
    KEEP_DAYS = 30

    created_at = models.DateTimeField('日時', db_index=True)
    kind = models.CharField('種類', max_length=20, choices=list(KINDS.items()))
    ip = models.GenericIPAddressField('IP アドレス', null=True, blank=True)
    user_agent = models.CharField('User-Agent', max_length=255, blank=True)
    method = models.CharField('メソッド', max_length=10, blank=True)
    path = models.CharField('パス', max_length=255, blank=True)

    class Meta:
        db_table = 'funitclub_suspiciousaccess'
        ordering = ['-created_at']
        verbose_name = '不審なアクセス'
        verbose_name_plural = '不審なアクセス'

    def __str__(self):
        return f'{self.created_at:%Y-%m-%d %H:%M} {self.kind} {self.ip} {self.path}'


class PendingView(models.Model):
    """ブラウザからの知らせ（beacon）を待っているページ。来なければ「人のふりをしたロボット」とする。

    知らせが来たら消す。PENDING_SECONDS 過ぎても残っていたら SuspiciousAccess に移して消す
    （console.suspicious.sweep_pending）。人のアクセスはここに数十分いるだけで残らない。
    """

    created_at = models.DateTimeField('日時', db_index=True)
    nonce = models.CharField('番号', max_length=32, unique=True)
    ip = models.GenericIPAddressField('IP アドレス', null=True, blank=True)
    user_agent = models.CharField('User-Agent', max_length=255, blank=True)
    path = models.CharField('パス', max_length=255, blank=True)

    class Meta:
        db_table = 'funitclub_pendingview'
        verbose_name = '知らせ待ちのページ'
        verbose_name_plural = '知らせ待ちのページ'
