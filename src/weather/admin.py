from django.contrib import admin

from weather.models import Parish, ParishProximity


@admin.register(Parish)
class ParishAdmin(admin.ModelAdmin):
    list_display = ('name', 'concelho', 'slug', 'island', 'is_active', 'latitude', 'longitude')
    list_filter = ('island', 'concelho', 'is_active')
    search_fields = ('name', 'slug', 'concelho')


@admin.register(ParishProximity)
class ParishProximityAdmin(admin.ModelAdmin):
    list_display = (
        'source_module',
        'source_label',
        'parish',
        'distance_km',
        'island',
        'latitude',
        'longitude',
    )
    list_filter = ('island', 'source_module')
    search_fields = (
        'source_ref',
        'parish__name',
        'parish__slug',
        'parish__concelho',
    )
    list_select_related = ('parish', 'island')
    raw_id_fields = ('parish',)
    ordering = ('source_module', 'source_ref')

    fieldsets = (
        (
            None,
            {
                'fields': (
                    'island',
                    'source_module',
                    'source_ref',
                    'parish',
                    'distance_km',
                    'latitude',
                    'longitude',
                ),
            },
        ),
    )

    @admin.display(description='Source')
    def source_label(self, obj: ParishProximity) -> str:
        if obj.source_module == 'transit_stop':
            from transit.models import Stop

            stop = Stop.objects.filter(id=obj.source_ref, island=obj.island).first()
            if stop is not None:
                return f'{stop.name} (#{stop.id})'
        return obj.source_ref
