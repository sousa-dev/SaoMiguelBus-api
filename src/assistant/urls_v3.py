from django.urls import path

from assistant.api_v3 import ai_journeys_view, ai_stops_view

urlpatterns = [
    path('journeys', ai_journeys_view, name='v3-ai-journeys'),
    path('stops', ai_stops_view, name='v3-ai-stops'),
]
