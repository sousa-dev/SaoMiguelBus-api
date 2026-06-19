from django.urls import path

from minibus.api_v3 import (
    document_file_view,
    documents_list_view,
    line_detail_view,
    lines_list_view,
    network_stops_view,
    route_search_view,
    schematic_view,
    tariffs_list_view,
)

urlpatterns = [
    path('lines', lines_list_view, name='v3-minibus-lines'),
    path('lines/<slug:slug>', line_detail_view, name='v3-minibus-line-detail'),
    path('network', network_stops_view, name='v3-minibus-network'),
    path('route', route_search_view, name='v3-minibus-route'),
    path('tariffs', tariffs_list_view, name='v3-minibus-tariffs'),
    path('documents', documents_list_view, name='v3-minibus-documents'),
    path('documents/<slug:slug>/file', document_file_view, name='v3-minibus-document-file'),
    path('schematic', schematic_view, name='v3-minibus-schematic'),
]
