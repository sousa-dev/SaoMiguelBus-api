from django.contrib import admin

from billing.models import Entitlement, Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_active', 'verification_count', 'created_at', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('email',)
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)


@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    # status is editable inline so staff can revoke legacy/manual premium quickly.
    list_display = ('id', 'user', 'email', 'tier', 'source', 'status', 'current_period_end', 'updated_at')
    list_editable = ('status',)
    list_filter = ('tier', 'source', 'status', 'platform')
    search_fields = ('email', 'user__email', 'user__username', 'external_id')
    raw_id_fields = ('user',)
    date_hierarchy = 'created_at'
    ordering = ('-updated_at',)
