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
