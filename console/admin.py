from django.contrib import admin

from .models import ActionCount, DailyVisitors, PageView


@admin.register(PageView)
class PageViewAdmin(admin.ModelAdmin):
    list_display = ('date', 'path', 'title', 'count')
    list_filter = ('date',)
    search_fields = ('path',)
    date_hierarchy = 'date'


@admin.register(ActionCount)
class ActionCountAdmin(admin.ModelAdmin):
    list_display = ('date', 'name', 'count')
    list_filter = ('date', 'name')
    date_hierarchy = 'date'


@admin.register(DailyVisitors)
class DailyVisitorsAdmin(admin.ModelAdmin):
    list_display = ('date', 'count')
    date_hierarchy = 'date'
