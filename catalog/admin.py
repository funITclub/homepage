# catalog/admin.py
#
# 生データを一覧・検索するための画面。編集の主導線は /edit/ 側で、
# こちらは全カラムを見たいときや絞り込み検索をしたいときに使う。

from django.contrib import admin

from .models import Wg, Work


@admin.register(Wg)
class WgAdmin(admin.ModelAdmin):
    list_display = ('sort_order', 'code', 'name', 'status', 'is_published', 'updated_at')
    list_filter = ('status', 'is_published')
    search_fields = ('code', 'name', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = ('sort_order', 'category', 'title', 'license', 'is_published', 'updated_at')
    list_filter = ('is_published', 'category')
    search_fields = ('title', 'category', 'description')
    readonly_fields = ('created_at', 'updated_at')
