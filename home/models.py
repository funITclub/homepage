# home/models.py
#
# 公開ページ自体は DB を持たないが、参加フォームの悪用対策で遮断した IP だけを記録する。

from django.db import models
from django.utils import timezone


class BlockedIpQuerySet(models.QuerySet):

    def active(self):
        """いま効いている遮断だけを返す。"""
        return self.filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now())
        )


class BlockedIp(models.Model):
    """遮断した IP アドレス。

    参加フォームの連続送信を検知したときに追加され、以降そのIPからのアクセスを
    403 で返す（config.middleware.BlockedIpMiddleware）。

    期間は繰り返すほど延びる（settings.IP_BLOCK_DURATIONS）。IP は個人の持ち物ではなく
    貸出品で、大学の構内ネットワークや携帯のCGNATでは多数の人が共有している。初回から
    恒久にすると、1人の乱用で無関係な人を巻き込んだまま気づけない。まず短く切って
    自動で解け、繰り返す相手だけ恒久に落とす。

    期限切れの行は消さずに残す（回数を数えるため）。解除は admin から。
    """

    ip = models.GenericIPAddressField('IPアドレス', unique=True)
    reason = models.CharField('理由', max_length=200, blank=True)
    block_count = models.PositiveIntegerField(
        '遮断回数',
        default=1,
        help_text='繰り返すほど遮断期間が延びます。',
    )
    expires_at = models.DateTimeField(
        '解除予定',
        null=True,
        blank=True,
        help_text='空欄なら恒久遮断（解除するまで続きます）。',
    )
    created_at = models.DateTimeField('初回遮断日時', auto_now_add=True)
    updated_at = models.DateTimeField('最終遮断日時', auto_now=True)

    objects = BlockedIpQuerySet.as_manager()

    class Meta:
        db_table = 'funitclub_blocked_ip'
        ordering = ['-updated_at']
        verbose_name = '遮断IP'
        verbose_name_plural = '遮断IP'

    def __str__(self):
        return self.ip

    @property
    def is_permanent(self):
        return self.expires_at is None

    @property
    def is_active(self):
        return self.is_permanent or self.expires_at > timezone.now()
