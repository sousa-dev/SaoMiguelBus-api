from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('verify/', views.verify_subscription, name='verify_subscription'),
    path('status/', views.subscription_status, name='subscription_status'),
] 