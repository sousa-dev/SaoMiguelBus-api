"""Blog URL configuration.

Template views and REST API endpoints for the blog app.
"""

from django.urls import path

from blog import api, views

app_name = "blog"

urlpatterns = [
    # -- Template views -------------------------------------------------------
    path("", views.post_list, name="post_list"),
    path("category/<slug:slug>/", views.category_detail, name="category_detail"),
    path("tag/<slug:slug>/", views.tag_detail, name="tag_detail"),
    path("author/<str:username>/", views.author_detail, name="author_detail"),

    # -- REST API -------------------------------------------------------------
    path("api/posts/", api.PostListCreateView.as_view(), name="api_post_list"),
    path("api/posts/<slug:slug>/", api.PostDetailView.as_view(), name="api_post_detail"),
    path("api/categories/", api.CategoryListCreateView.as_view(), name="api_category_list"),
    path("api/tags/", api.TagListCreateView.as_view(), name="api_tag_list"),

    # -- Post detail (must be last — catches all slugs) -----------------------
    path("<slug:slug>/", views.post_detail, name="post_detail"),
]
