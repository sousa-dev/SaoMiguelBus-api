from django.contrib import admin

from weather.models import Parish


@admin.register(Parish)
class ParishAdmin(admin.ModelAdmin):
    list_display = ('name', 'concelho', 'slug', 'island', 'is_active', 'latitude', 'longitude')
    list_filter = ('island', 'concelho', 'is_active')
    search_fields = ('name', 'slug', 'concelho')
