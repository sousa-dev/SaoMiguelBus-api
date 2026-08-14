from django.urls import path

from azoresbus.api_v3 import (
    azoresbus_tracking_health_view,
    azoresbus_vehicle_detail_view,
    azoresbus_vehicles_view,
)

urlpatterns = [
    path('vehicles', azoresbus_vehicles_view, name='azoresbus-vehicles-v3'),
    path('vehicles/<str:vehicle_id>', azoresbus_vehicle_detail_view,
         name='azoresbus-vehicle-detail-v3'),
    path('tracking/health', azoresbus_tracking_health_view,
         name='azoresbus-tracking-health-v3'),
]
