from django.urls import path

from personalization.api import personalization_view

urlpatterns = [
    path('', personalization_view, name='v3-personalization'),
]
