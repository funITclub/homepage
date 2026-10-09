# countdown/admin.py
#
# 誰でも書き込める公開アプリ。荒らしの整理や、使われなくなった ID の削除は admin から行う。

from django.contrib import admin

from .models import Board, CountEvent


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    # 通知先のアドレスは暗号化して持っていて、管理画面には出さない（登録の有無だけ）
    list_display = ('code', 'has_notify_email', 'notified_on', 'created_at')
    search_fields = ('code',)
    readonly_fields = ('created_at', 'notified_on')

    actions = ['clear_notify_email']

    @admin.action(description='選んだ ID の通知先を消す（通知を止める）')
    def clear_notify_email(self, request, queryset):
        """本人がメールを受け取れなくなり、自分では解除できないときのため。"""
        for board in queryset:
            board.set_notify_email('')
        self.message_user(request, f'{queryset.count()} 件の通知先を消しました。')

    @admin.display(description='通知先', boolean=True)
    def has_notify_email(self, obj):
        return bool(obj.notify_email_enc)


@admin.register(CountEvent)
class CountEventAdmin(admin.ModelAdmin):
    list_display = ('date', 'name', 'board', 'notify', 'memo', 'created_at', 'updated_at')
    list_filter = ('date',)
    search_fields = ('name', 'memo', 'board__code')
    date_hierarchy = 'date'
    readonly_fields = ('created_at', 'updated_at')
