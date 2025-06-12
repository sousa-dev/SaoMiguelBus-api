from django.contrib import admin
from .models import Subscription

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        'email', 'is_active', 'created_at', 'updated_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['email']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Subscription Info', {
            'fields': ('email', 'is_active')
        }),
        ('System Fields', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
