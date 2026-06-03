from django.urls import path

from news.api_v3 import news_article_detail_view, news_articles_view, news_sources_view

urlpatterns = [
    path('sources', news_sources_view, name='v3-news-sources'),
    path('articles', news_articles_view, name='v3-news-articles'),
    path('articles/<int:article_id>', news_article_detail_view, name='v3-news-article-detail'),
]
