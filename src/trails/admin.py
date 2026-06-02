from django.contrib import admin

from trails.models import POI, Trail, TrailStage


class TrailStageInline(admin.TabularInline):
    model = TrailStage
    extra = 0


@admin.register(Trail)
class TrailAdmin(admin.ModelAdmin):
    list_display = ('name', 'difficulty', 'distance_km', 'island')
    list_filter = ('island', 'difficulty')
    search_fields = ('name', 'source_ref')
    inlines = [TrailStageInline]


@admin.register(POI)
class POIAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'island')
    list_filter = ('island', 'category')
    search_fields = ('name',)
