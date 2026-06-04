from django.urls import path

from user_management import api_v3

urlpatterns = [
    path('register', api_v3.register_view, name='v3-auth-register'),
    path('login', api_v3.login_view, name='v3-auth-login'),
    path('social', api_v3.social_view, name='v3-auth-social'),
    path('me', api_v3.me_view, name='v3-auth-me'),
    path('logout', api_v3.logout_view, name='v3-auth-logout'),
]
