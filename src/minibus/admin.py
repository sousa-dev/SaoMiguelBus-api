from django.contrib import admin

from minibus.models import MinibusDocument, MinibusImportMeta, MinibusLine, MinibusTariff


@admin.register(MinibusLine)
class MinibusLineAdmin(admin.ModelAdmin):
    list_display = ('code', 'name_pt', 'slug', 'island', 'is_active', 'sort_order')
    list_filter = ('island', 'is_active')
    search_fields = ('code', 'slug', 'name_pt', 'name_en')
    readonly_fields = ('route_shapes',)


@admin.register(MinibusTariff)
class MinibusTariffAdmin(admin.ModelAdmin):
    list_display = ('key', 'label_pt', 'price_eur', 'island', 'sort_order', 'is_active')
    list_filter = ('island', 'is_active')
    search_fields = ('key', 'label_pt', 'label_en')


@admin.register(MinibusDocument)
class MinibusDocumentAdmin(admin.ModelAdmin):
    list_display = ('slug', 'doc_type', 'line', 'island', 'is_active', 'source_filename')
    list_filter = ('island', 'doc_type', 'is_active')
    search_fields = ('slug', 'title_pt', 'title_en', 'source_filename')


@admin.register(MinibusImportMeta)
class MinibusImportMetaAdmin(admin.ModelAdmin):
    list_display = ('island', 'source_url', 'imported_at', 'tariffs_effective_date', 'source_revision')
