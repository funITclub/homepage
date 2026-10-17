# countdown/models.py
#
# hirahira_room の countdown アプリからの移植。
# あちらはユーザーごとの個人用（CountEvent.user への外部キーあり）だが、
# funITclub には会員登録が無いため、本アプリの中の ID（Board）ごとに分けて持つ。
# ID を使わない人のために、誰でも読み書きできる共有ボードも残してある。
# ID には通知先のメールアドレスを1つ登録でき（任意）、印を付けたカウントダウンを
# 1日1通にまとめて知らせる（countdown/notify.py）。
# 日数の数え方（経過・残り・週・周年）はそのまま引き継いだ。

from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .crypto import decrypt, encrypt


class Board(models.Model):
    """ID ごとの置き場。登録した出来事・予定は、その ID の一覧にだけ出る。

    一覧は /countdown/<ID>/ で開く。編集画面のアカウントとは紐づけない。
    ID は本人が決め、ID を知っている人なら誰でも開ける（合言葉などの確認はしない）。
    大文字小文字は区別せず、小文字にそろえて持つ。fe アプリの Learner と同じ考え方。
    """

    code = models.CharField(
        'ID', max_length=30, unique=True,
        validators=[RegexValidator(
            r'^[a-z0-9_-]{3,30}$',
            'ID は半角の英小文字・数字・「_」「-」で、3〜30文字にしてください。',
        )],
    )
    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    # 任意。確認のメールのリンクを開いたアドレスだけが入る。解除すると空に戻す。
    # 会としては個人情報をシステムに持たない方針で、ここはその例外。
    # 本人が通知を望んだときだけ持ち、通知を送る以外には使わない。
    # DB には暗号化して持つ（countdown/crypto.py）。読み書きは notify_email と
    # set_notify_email を通す。
    notify_email_enc = models.TextField('通知先（暗号化）', blank=True, editable=False)
    # 同じ日に2通送らないための控え。
    notified_on = models.DateField('最後に通知した日', null=True, blank=True)

    class Meta:
        db_table = 'funitclub_countboard'
        ordering = ['code']
        verbose_name = verbose_name_plural = 'カウント ID'

    def __str__(self):
        return self.code

    @property
    def notify_email(self):
        """通知先のアドレス。未登録なら空。"""
        return decrypt(self.notify_email_enc)

    def set_notify_email(self, email):
        """通知先を登録・変更する。空を渡すと解除（アドレスを消す）。"""
        self.notify_email_enc = encrypt(email)
        self.notified_on = None
        self.save(update_fields=['notify_email_enc', 'notified_on'])

    @property
    def masked_email(self):
        """画面に出す通知先。ID を知っている人なら誰でも見られるので、伏せて出す。"""
        email = self.notify_email
        if not email:
            return ''
        local, _, domain = email.partition('@')
        return f'{local[:1]}***@{domain}'

    @property
    def mail_url(self):
        return reverse('countdown:board_mail', args=[self.code])


def board_url(board, page, *args):
    """一覧・登録・編集・削除の場所。board が None なら共有ボードのもの。"""
    if board is None:
        return reverse(f'countdown:event_{page}', args=args)
    return reverse(f'countdown:board_{page}', args=[board.code, *args])


class CountEvent(models.Model):
    """カウントアップ／カウントダウンの対象となる出来事・予定。"""

    # 空のものは、ID を使わない共有ボードに登録されたもの。
    board = models.ForeignKey(
        Board, verbose_name='ID', null=True, blank=True,
        on_delete=models.CASCADE, related_name='events',
    )
    name = models.CharField('名前', max_length=50)
    date = models.DateField('日付')
    memo = models.TextField('メモ', max_length=300, blank=True)
    # カウントダウン（当日を含むこれからの予定）の間だけ効く。共有ボードでは使わない。
    notify = models.BooleanField('メールで知らせる', default=False)
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
    def update_url(self):
        return board_url(self.board, 'update', self.pk)

    @property
    def delete_url(self):
        return board_url(self.board, 'delete', self.pk)

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
