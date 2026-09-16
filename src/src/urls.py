"""src URL Configuration."""

from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from tenancy.api_v3 import app_update_check_view, bootstrap_view

urlpatterns = [
    path('dashboard/admin/', admin.site.urls),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/docs/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/v1/', include('compat.urls_v1')),
    path('api/v2/', include('compat.urls_v2')),
    path('api/v1/ops/', include('tenancy.urls')),
    path('api/v3/agent-docs/', include('agent_docs.urls_v3')),
    path('api/v3/bootstrap', bootstrap_view),
    path('api/v3/app/update-check', app_update_check_view),
    path('api/v3/auth/', include('user_management.urls_v3')),
    path('api/v3/azoresbus/', include('azoresbus.urls_v3')),
    path('api/v3/billing/', include('billing.urls_v3')),
    path('api/v3/consent/', include('consent.urls')),
    path('api/v3/personalization/', include('personalization.urls')),
    path('api/v3/privacy/', include('consent.urls_privacy')),
    path('api/v3/analytics/', include('analytics.urls_v3')),
    path('api/v3/transit/', include('transit.urls_v3')),
    path('api/v3/news/', include('news.urls_v3')),
    path('api/v3/seismic/', include('seismic.urls_v3')),
    path('api/v3/trails/', include('trails.urls_v3')),
    path('api/v3/marketplace/', include('marketplace.urls_v3')),
    path('api/v3/traffic/', include('traffic.urls_v3')),
    path('api/v3/events/', include('events.urls_v3')),
]

if 'weather' in settings.INSTALLED_APPS:
    urlpatterns.append(path('api/v3/weather/', include('weather.urls_v3')))

if 'minibus' in settings.INSTALLED_APPS:
    urlpatterns.append(path('api/v3/minibus/', include('minibus.urls_v3')))

if 'atlas' in settings.INSTALLED_APPS:
    urlpatterns.append(path('api/v3/atlas/', include('atlas.urls_v3')))

if 'assistant' in settings.INSTALLED_APPS:
    from assistant.views_discovery import (
        OpenAPIJSONView,
        llms_full_txt_view,
        llms_txt_view,
        robots_txt_view,
    )

    urlpatterns.append(path('api/v3/ai/', include('assistant.urls_v3')))
    urlpatterns.append(path('llms.txt', llms_txt_view))
    urlpatterns.append(path('llms-full.txt', llms_full_txt_view))
    urlpatterns.append(path('robots.txt', robots_txt_view))
    urlpatterns.append(path('openapi.json', OpenAPIJSONView.as_view()))

if 'mcp_server' in settings.INSTALLED_APPS and settings.MCP_ENABLED:
    urlpatterns.append(path('api/v3/mcp', include('mcp_server.urls_v3')))

if 'legal' in settings.INSTALLED_APPS:
    urlpatterns.append(path('legal/', include('legal.urls')))

if 'stripe_payments' in settings.INSTALLED_APPS:
    urlpatterns.append(path('payment/', include('stripe_payments.urls')))

if 'user_management' in settings.INSTALLED_APPS:
    urlpatterns.append(path('', include('user_management.urls')))

if 'allauth' in settings.INSTALLED_APPS:
    urlpatterns.append(path('accounts/', include('allauth.urls')))
