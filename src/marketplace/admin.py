from django.contrib import admin

from marketplace.models import Review, ServiceCategory, ServiceProvider


def _publish(modeladmin, request, queryset):
    queryset.update(status=ServiceProvider.PUBLISHED)


_publish.short_description = 'Publish selected'


def _reject(modeladmin, request, queryset):
    queryset.update(status=ServiceProvider.REJECTED)


_reject.short_description = 'Reject selected'


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'user_suggested', 'island', 'icon')
    list_filter = ('island', 'is_active', 'user_suggested')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(ServiceProvider)
class ServiceProviderAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'category',
        'status',
        'claimed_owner',
        'verified_by_owner',
        'is_promoted',
        'rating',
        'review_count',
        'website',
        'island',
    )
    list_filter = ('island', 'status', 'claimed_owner', 'verified_by_owner', 'is_promoted', 'category')
    search_fields = ('name', 'bio', 'phone', 'email', 'website', 'internal_email', 'internal_phone')
    actions = [_publish, _reject]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('provider', 'rating', 'status', 'island', 'created_at')
    list_filter = ('island', 'status', 'rating')
    search_fields = ('text',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from marketplace.services import recompute_rating

        recompute_rating(obj.provider)
