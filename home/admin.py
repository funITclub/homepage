# home/admin.py

from django.contrib import admin
from django.utils import timezone

from .models import BlockedIp


@admin.register(BlockedIp)
class BlockedIpAdmin(admin.ModelAdmin):
    """遮断中の IP。

    解除は「今すぐ解除する」を使う（行は残るので、再犯したときに回数を引き継げる）。
    完全に無かったことにしたいときだけ削除する。
    """

    list_display = ['ip', 'state', 'block_count', 'expires_at', 'reason', 'updated_at']
    list_filter = ['block_count']
    search_fields = ['ip', 'reason']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['release']

    @admin.display(description='状態')
    def state(self, obj):
        if not obj.is_active:
            return '解除済み'
        return '遮断中（恒久）' if obj.is_permanent else '遮断中'

    @admin.action(description='選択した IP を今すぐ解除する')
    def release(self, request, queryset):
        count = queryset.update(expires_at=timezone.now())
        # 次のリクエストから効かせる
        from config.middleware import BlockedIpMiddleware
        BlockedIpMiddleware.forget_cache()
        self.message_user(request, f'{count}件を解除しました。')
