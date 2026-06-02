from django.contrib import admin

from news.models import NewsArticle, NewsSource


@admin.register(NewsSource)
class NewsSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'island', 'language', 'active', 'rss_url')
    list_filter = ('active', 'language', 'island')
    search_fields = ('name', 'rss_url')


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'island', 'published_at', 'category')
    list_filter = ('island', 'category', 'source')
    search_fields = ('title', 'link')
    date_hierarchy = 'published_at'
