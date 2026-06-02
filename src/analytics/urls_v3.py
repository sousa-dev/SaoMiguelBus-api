from django.urls import path

from analytics.api_v3 import analytics_events_view

urlpatterns = [
    path('events', analytics_events_view, name='v3-analytics-events'),
]
