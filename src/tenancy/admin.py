from django.contrib import admin

from tenancy.models import Island


@admin.register(Island)
class IslandAdmin(admin.ModelAdmin):
    list_display = ('key', 'name', 'archipelago', 'is_live', 'updated_at')
    list_filter = ('is_live', 'archipelago')
    search_fields = ('key', 'name')
    readonly_fields = ('created_at', 'updated_at')
