from django.contrib import admin

from consent.models import ConsentRecord


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ('session_hash', 'policy_version', 'granted_at', 'withdrawn_at')
    list_filter = ('policy_version',)
    search_fields = ('session_hash',)
    readonly_fields = ('granted_at',)
