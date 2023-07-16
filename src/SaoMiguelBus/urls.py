"""SaoMiguelBus URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from app import views



urlpatterns = [
    path('', views.index),
    path('admin/', admin.site.urls),
    path('api/v1/stops', views.get_all_stops_v1),
    path('api/v1/routes', views.get_all_routes_v1),
    path('api/v1/route', views.get_trip_v1),
    path('api/v1/route/<int:route_id>', views.get_route_v1),
    path('api/v1/android/load', views.get_android_load_v1),
    path('api/v2/android/load', views.get_android_load_v2),
    path('api/v1/stats', views.get_stats_v1),
    path('api/v1/stat', views.add_stat_v1),
    path('api/v1/ad', views.get_ad_v1),
    path('api/v1/ad/click', views.click_ad_v1),
    path('api/v1/groups', views.get_all_groups_v1),
    path('api/v1/stats/group', views.get_group_stats_v1),
    path('statistics', views.stats),
]
