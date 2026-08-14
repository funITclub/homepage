# news/admin.py
#
# 生データを一覧・検索するための画面。編集の主導線は /edit/ 側で、
# こちらは全カラムを見たいときや絞り込み検索をしたいときに使う。

from django.contrib import admin

from .models import News


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    list_display = ('published_on', 'text', 'badge', 'is_new', 'is_published', 'updated_at')
    list_filter = ('is_published', 'is_new')
    search_fields = ('text', 'badge')
    date_hierarchy = 'published_on'
    readonly_fields = ('created_at', 'updated_at')
