"""Admin configuration for stripe_payments."""

from __future__ import annotations

from django.contrib import admin

from .models import UserPayment


@admin.register(UserPayment)
class UserPaymentAdmin(admin.ModelAdmin):
    list_display = ["id", "app_user", "email", "payment_bool", "stripe_checkout_id"]
    list_filter = ["payment_bool"]
    search_fields = ["email", "stripe_checkout_id"]
