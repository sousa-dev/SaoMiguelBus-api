from django.urls import path

from azoresbus.api_v3 import (
    azoresbus_live_activity_register_view,
    azoresbus_live_activity_unregister_view,
    azoresbus_routes_view,
    azoresbus_stop_arrivals_view,
    azoresbus_tracking_health_view,
    azoresbus_trips_live_view,
    azoresbus_vehicle_detail_view,
    azoresbus_vehicles_view,
)

urlpatterns = [
    path('vehicles', azoresbus_vehicles_view, name='azoresbus-vehicles-v3'),
    path('vehicles/<str:vehicle_id>', azoresbus_vehicle_detail_view,
         name='azoresbus-vehicle-detail-v3'),
    path('routes', azoresbus_routes_view, name='azoresbus-routes-v3'),
    path('stops/<int:stop_id>/arrivals', azoresbus_stop_arrivals_view,
         name='azoresbus-stop-arrivals-v3'),
    path('trips/live', azoresbus_trips_live_view, name='azoresbus-trips-live-v3'),
    path('live-activities', azoresbus_live_activity_register_view,
         name='azoresbus-live-activity-register-v3'),
    path('live-activities/<str:push_token>', azoresbus_live_activity_unregister_view,
         name='azoresbus-live-activity-unregister-v3'),
    path('tracking/health', azoresbus_tracking_health_view,
         name='azoresbus-tracking-health-v3'),
]
