from django.contrib import admin

from legacy_archive.models import (
    LegacyAIFeedback,
    LegacyData,
    LegacyEmailOpen,
    LegacyTrip,
    LegacyTripStop,
)


@admin.register(LegacyData)
class LegacyDataAdmin(admin.ModelAdmin):
    list_display = ('id', 'origin', 'destination', 'platform')


@admin.register(LegacyTrip)
class LegacyTripAdmin(admin.ModelAdmin):
    list_display = ('id', 'route', 'type_of_day', 'disabled')


@admin.register(LegacyTripStop)
class LegacyTripStopAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'latitude', 'longitude')


@admin.register(LegacyAIFeedback)
class LegacyAIFeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'language', 'timestamp')


@admin.register(LegacyEmailOpen)
class LegacyEmailOpenAdmin(admin.ModelAdmin):
    list_display = ('id', 'email_template_id', 'contact_id', 'clicks')
