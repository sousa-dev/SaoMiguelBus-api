"""src URL Configuration."""

from django.contrib import admin
from django.contrib.sitemaps import views as sitemap_views
from django.urls import include, path
from django.views.decorators.cache import cache_page
from django.views.generic import TemplateView

from app import views
from django.conf import settings

urlpatterns = [
    path('dashboard/admin/', admin.site.urls),
    path('', include('user_management.urls')),
    path('__reload__/', include('django_browser_reload.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    path('media/<path:path>', views.fetch_media, name='get_media'),
]

if 'landing_page' in settings.INSTALLED_APPS:
    urlpatterns.append(path('', include('landing_page.urls')))
    urlpatterns.append(path('app/', include('app.urls')))
else:
    urlpatterns.append(path('', include('app.urls')))

if 'documentation' in settings.INSTALLED_APPS:
    urlpatterns.append(path('docs/', include('documentation.urls')))

if 'allauth' in settings.INSTALLED_APPS:
    urlpatterns.append(path('accounts/', include('allauth.urls')))

if 'stripe_payments' in settings.INSTALLED_APPS:
    urlpatterns.append(path('payment/', include('stripe_payments.urls')))

if 'legal' in settings.INSTALLED_APPS:
    urlpatterns.append(path('legal/', include('legal.urls')))

# -- Blog + Free Tools + SEO infrastructure ------------------------------------
sitemaps = {}

if 'blog' in settings.INSTALLED_APPS:
    urlpatterns.append(path('blog/', include('blog.urls')))
    from blog.sitemaps import BlogCategorySitemap, BlogPostSitemap
    sitemaps['blog-posts'] = BlogPostSitemap
    sitemaps['blog-categories'] = BlogCategorySitemap

if 'free_tools' in settings.INSTALLED_APPS:
    urlpatterns.append(path('tools/', include('free_tools.urls')))
    from free_tools.sitemaps import FreeToolSitemap, ToolCategorySitemap
    sitemaps['free-tools'] = FreeToolSitemap
    sitemaps['tool-categories'] = ToolCategorySitemap
if sitemaps:
    urlpatterns += [
        path('sitemap.xml',
             cache_page(3600)(sitemap_views.index),
             {'sitemaps': sitemaps, 'sitemap_url_name': 'sitemaps'}),
        path('sitemap-<section>.xml',
             cache_page(3600)(sitemap_views.sitemap),
             {'sitemaps': sitemaps},
             name='sitemaps'),
    ]

urlpatterns.append(
    path('robots.txt',
         TemplateView.as_view(template_name='robots.txt', content_type='text/plain'),
         name='robots_txt'),
)
