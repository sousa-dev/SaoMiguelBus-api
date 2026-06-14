from django.urls import path

from analytics.api_reporting import (
    legacy_events_view,
    legacy_meta_view,
    legacy_overview_view,
    v3_events_view,
    v3_meta_view,
    v3_overview_view,
    v3_properties_view,
)
from analytics.api_v3 import analytics_events_view

urlpatterns = [
    path('events', analytics_events_view, name='v3-analytics-events'),
    # Read-side reporting (AUTH_KEY protected) — powers the stats dashboard.
    path('reports/overview', v3_overview_view, name='v3-analytics-overview'),
    path('reports/events', v3_events_view, name='v3-analytics-report-events'),
    path('reports/properties', v3_properties_view, name='v3-analytics-properties'),
    path('reports/meta', v3_meta_view, name='v3-analytics-meta'),
    path('reports/legacy/overview', legacy_overview_view, name='v3-analytics-legacy-overview'),
    path('reports/legacy/events', legacy_events_view, name='v3-analytics-legacy-events'),
    path('reports/legacy/meta', legacy_meta_view, name='v3-analytics-legacy-meta'),
]
