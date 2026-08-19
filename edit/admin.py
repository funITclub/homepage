# edit/admin.py

from django.contrib import admin

from .models import Administrator


@admin.register(Administrator)
class AdministratorAdmin(admin.ModelAdmin):
    """運営の連絡先。通知の宛先と公開ページの問い合わせ先はここで決まる。"""

    list_display = ['email', 'name', 'receives_notifications', 'is_public_contact',
                    'is_active', 'sort_order']
    list_editable = ['receives_notifications', 'is_public_contact', 'is_active',
                     'sort_order']
    search_fields = ['email', 'name']
    readonly_fields = ['created_at', 'updated_at']
