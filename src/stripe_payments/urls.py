from django.urls import path

from src import settings
from . import views

urlpatterns = [
    path('pay/', views.payment, name='payment'),
    path('successful/', views.success, name='success'),
    path('cancelled/', views.cancel, name='cancel'),
    path('webhook/', views.stripe_webhook, name='stripe-webhook')
]