# documentation/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.search_docs, name='search_docs'), 
    path('<str:section>/<str:page>/', views.docs_view, name='docs'),
    path('<str:section>/', views.docs_view, {'page': 'index'}, name='docs_index'),
    path('', views.docs_view, {'page': 'index'}, name='docs-home'),
]