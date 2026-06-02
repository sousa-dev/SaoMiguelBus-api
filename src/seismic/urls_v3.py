from django.urls import path

from seismic.api_v3 import (
    seismic_event_detail_view,
    seismic_event_felt_view,
    seismic_events_view,
)

urlpatterns = [
    path('events', seismic_events_view, name='v3-seismic-events'),
    path('events/<int:event_id>', seismic_event_detail_view, name='v3-seismic-event-detail'),
    path('events/<int:event_id>/felt', seismic_event_felt_view, name='v3-seismic-event-felt'),
]
