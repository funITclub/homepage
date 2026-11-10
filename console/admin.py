from django.contrib import admin

from .models import PageView


@admin.register(PageView)
class PageViewAdmin(admin.ModelAdmin):
    list_display = ('date', 'path', 'count')
    list_filter = ('date',)
    search_fields = ('path',)
    date_hierarchy = 'date'
