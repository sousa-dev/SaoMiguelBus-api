from django.urls import path

from mcp_server.api_v3 import discovery_view

urlpatterns = [path('', discovery_view, name='v3-mcp-discovery')]