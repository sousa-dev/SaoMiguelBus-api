from django.contrib import admin

from transit.models import (
    Ad,
    Calendar,
    Holiday,
    Line,
    Operator,
    RouteInfo,
    Stop,
    StopGroup,
    StopTime,
    Trip,
)


class IslandScopedAdmin(admin.ModelAdmin):
    list_filter = ('island',)
    list_select_related = ('island',)


class StopTimeInline(admin.TabularInline):
    model = StopTime
    extra = 0
    fields = ('sequence', 'stop', 'departure_time', 'arrival_time')
    raw_id_fields = ('stop',)
    ordering = ('sequence',)


@admin.register(Operator)
class OperatorAdmin(IslandScopedAdmin):
    list_display = ('name', 'island')
    search_fields = ('name',)


@admin.register(Calendar)
class CalendarAdmin(IslandScopedAdmin):
    list_display = ('service_type', 'island')


@admin.register(Stop)
class StopAdmin(IslandScopedAdmin):
    list_display = ('name', 'cleaned_name', 'latitude', 'longitude', 'island')
    search_fields = ('name', 'cleaned_name')
    list_per_page = 100


@admin.register(Line)
class LineAdmin(IslandScopedAdmin):
    list_display = ('code', 'operator', 'disabled', 'island')
    search_fields = ('code', 'display_name')
    list_filter = ('island', 'disabled', 'operator')
    list_select_related = ('island', 'operator')


@admin.register(Trip)
class TripAdmin(IslandScopedAdmin):
    list_display = ('line', 'calendar', 'source', 'likes', 'dislikes', 'island')
    list_filter = ('island', 'calendar', 'source')
    search_fields = ('line__code', 'headsign')
    list_select_related = ('island', 'line', 'calendar')
    raw_id_fields = ('line', 'calendar')
    inlines = (StopTimeInline,)


@admin.register(StopTime)
class StopTimeAdmin(IslandScopedAdmin):
    list_display = ('trip', 'sequence', 'stop', 'departure_time', 'island')
    list_filter = ('island',)
    search_fields = ('stop__name', 'trip__line__code')
    list_select_related = ('island', 'trip', 'stop', 'trip__line')
    raw_id_fields = ('trip', 'stop')
    list_per_page = 100


@admin.register(Holiday)
class HolidayAdmin(IslandScopedAdmin):
    list_display = ('date', 'name', 'island')
    search_fields = ('name',)
    date_hierarchy = 'date'


@admin.register(StopGroup)
class StopGroupAdmin(IslandScopedAdmin):
    list_display = ('name', 'island')
    search_fields = ('name',)


@admin.register(RouteInfo)
class RouteInfoAdmin(IslandScopedAdmin):
    list_display = ('company', 'source', 'start', 'end', 'island')
    search_fields = ('company', 'source')
    list_filter = ('island', 'company')


@admin.register(Ad)
class AdAdmin(IslandScopedAdmin):
    list_display = ('entity', 'platform', 'status', 'start', 'end', 'seen', 'clicked', 'island')
    list_filter = ('island', 'platform', 'status')
    search_fields = ('entity', 'description')
    date_hierarchy = 'start'
