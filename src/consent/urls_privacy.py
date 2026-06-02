from django.urls import path

from consent.api import dsar_delete_view, dsar_export_view

urlpatterns = [
    path('dsar/export', dsar_export_view, name='v3-privacy-dsar-export'),
    path('dsar/delete', dsar_delete_view, name='v3-privacy-dsar-delete'),
]
