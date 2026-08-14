# countdown/admin.py
#
# 公開ボードなので誰でも書き込める。荒らしの整理は admin から行う。

from django.contrib import admin

from .models import CountEvent


@admin.register(CountEvent)
class CountEventAdmin(admin.ModelAdmin):
    list_display = ('date', 'name', 'memo', 'created_at', 'updated_at')
    list_filter = ('date',)
    search_fields = ('name', 'memo')
    date_hierarchy = 'date'
    readonly_fields = ('created_at', 'updated_at')
