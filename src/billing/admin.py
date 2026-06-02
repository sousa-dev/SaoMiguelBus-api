from django.contrib import admin

from billing.models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_active', 'verification_count', 'created_at', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('email',)
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
