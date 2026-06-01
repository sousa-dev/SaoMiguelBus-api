"""Free tools URL configuration."""

from django.urls import path

from free_tools import api, views

app_name = "free_tools"

urlpatterns = [
    # Template views
    path("", views.tool_index, name="tool_index"),
    path("category/<slug:slug>/", views.category_detail, name="category_detail"),

    # REST API
    path("api/tools/", api.ToolListCreateView.as_view(), name="api_tool_list"),
    path("api/tools/<slug:slug>/", api.ToolDetailView.as_view(), name="api_tool_detail"),
    path("api/categories/", api.CategoryListCreateView.as_view(), name="api_category_list"),

    # Tool detail (last — catches all slugs)
    path("<slug:slug>/", views.tool_detail, name="tool_detail"),
]
