from django.contrib import admin

from personalization.models import PersonalizationProfile


@admin.register(PersonalizationProfile)
class PersonalizationProfileAdmin(admin.ModelAdmin):
    list_display = ('session_hash', 'user_type', 'home_municipality', 'updated_at')
    list_filter = ('user_type',)
    search_fields = ('session_hash',)
    readonly_fields = ('created_at', 'updated_at')
