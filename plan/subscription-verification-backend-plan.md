# Subscription Verification Backend Implementation Plan

## Overview
Implement a simple subscription verification system for the São Miguel Bus API that allows users to verify their premium subscription status via email. This system will use a simple database model with email and active flag for manual subscription management.

## Current Architecture Analysis

### Existing Components
- **Django 3.0.14** with REST Framework
- **PostgreSQL** (production) / **SQLite** (development) databases
- **CORS** enabled for cross-origin requests
- **Existing API structure**: `/api/v1/` endpoints
- **Ad system**: Already implemented with `Ad` model
- **Authentication**: Basic API key system with `AUTH_KEY`

### Current Models
- `Ad`: Manages advertisements
- `Stat`: Tracks API usage statistics
- `Info`: Manages informational content
- Various route and stop models

## Implementation Plan

### Phase 1: Create Subscription Django App

#### 1.1 Create New Django App
```bash
cd src
python manage.py startapp subscriptions
```

#### 1.2 App Structure
```
src/subscriptions/
├── __init__.py
├── admin.py
├── apps.py
├── models.py
├── serializers.py
├── urls.py
├── views.py
└── migrations/
```

### Phase 2: Simple Database Model

#### 2.1 Subscription Model (`subscriptions/models.py`)

```python
from django.db import models
from django.core.validators import EmailValidator

class Subscription(models.Model):
    """Simple subscription model for manual management"""
    id = models.AutoField(primary_key=True)
    email = models.EmailField(validators=[EmailValidator()], unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'subscriptions'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.email} - {'Active' if self.is_active else 'Inactive'}"
```

### Phase 3: Serializers

#### 3.1 Subscription Serializers (`subscriptions/serializers.py`)

```python
from rest_framework import serializers
from .models import Subscription

class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ['id', 'email', 'is_active', 'created_at', 'updated_at']

class SubscriptionVerificationRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    
    def validate_email(self, value):
        """Validate email format and basic checks"""
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Email is required")
        return value.strip().lower()

class SubscriptionVerificationResponseSerializer(serializers.Serializer):
    hasActiveSubscription = serializers.BooleanField()
    subscriptionType = serializers.CharField(allow_null=True)
    expiresAt = serializers.CharField(allow_null=True)
    features = serializers.ListField(child=serializers.CharField(), default=list)
    message = serializers.CharField(allow_null=True)
```

### Phase 4: Views and API Endpoints

#### 4.1 Subscription Views (`subscriptions/views.py`)

```python
import logging
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Subscription
from .serializers import (
    SubscriptionVerificationRequestSerializer,
    SubscriptionVerificationResponseSerializer
)

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
@require_POST
def verify_subscription(request):
    """
    Verify subscription status by email
    
    Request:
    {
        "email": "user@example.com"
    }
    
    Response:
    {
        "hasActiveSubscription": true/false,
        "subscriptionType": "premium" | null,
        "expiresAt": null,
        "features": ["ad_removal", "priority_support"],
        "message": "Optional message"
    }
    """
    try:
        # Validate request data
        serializer = SubscriptionVerificationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'error': 'Invalid request data',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data['email']
        
        # Find active subscription
        subscription = Subscription.objects.filter(
            email=email,
            is_active=True
        ).first()
        
        # Prepare response
        if subscription:
            response_data = {
                'hasActiveSubscription': True,
                'subscriptionType': 'premium',
                'expiresAt': None,  # No expiration for manual subscriptions
                'features': ['ad_removal', 'priority_support'],
                'message': None
            }
        else:
            response_data = {
                'hasActiveSubscription': False,
                'subscriptionType': None,
                'expiresAt': None,
                'features': [],
                'message': 'No active subscription found for this email'
            }
        
        # Validate response
        response_serializer = SubscriptionVerificationResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)
        
        return Response(response_serializer.validated_data, status=status.HTTP_200_OK)
        
    except ValidationError as e:
        logger.error(f"Validation error in subscription verification: {e}")
        return Response({
            'error': 'Validation error',
            'message': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        logger.error(f"Unexpected error in subscription verification: {e}")
        return Response({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def subscription_status(request):
    """
    Get subscription status (for internal use)
    """
    email = request.GET.get('email')
    if not email:
        return Response({
            'error': 'Email parameter is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    subscription = Subscription.objects.filter(
        email=email,
        is_active=True
    ).first()
    
    if subscription:
        return Response({
            'active': True,
            'subscription': SubscriptionSerializer(subscription).data
        })
    else:
        return Response({
            'active': False,
            'subscription': None
        })
```

### Phase 5: URL Configuration

#### 5.1 Subscription URLs (`subscriptions/urls.py`)

```python
from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('verify', views.verify_subscription, name='verify_subscription'),
    path('status', views.subscription_status, name='subscription_status'),
]
```

#### 5.2 Update Main URLs (`SaoMiguelBus/urls.py`)

```python
# Add to existing urlpatterns
path('api/v1/subscription/', include('subscriptions.urls')),
```

### Phase 6: Admin Interface

#### 6.1 Admin Configuration (`subscriptions/admin.py`)

```python
from django.contrib import admin
from .models import Subscription

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        'email', 'is_active', 'created_at', 'updated_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['email']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Subscription Info', {
            'fields': ('email', 'is_active')
        }),
        ('System Fields', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
```

### Phase 7: Settings Configuration

#### 7.1 Update Settings (`SaoMiguelBus/settings.py`)

```python
# Add to INSTALLED_APPS
INSTALLED_APPS = [
    # ... existing apps
    'subscriptions',
]
```

### Phase 8: Database Migrations

#### 8.1 Create and Run Migrations

```bash
cd src
python manage.py makemigrations subscriptions
python manage.py migrate
```

## API Endpoints Summary

### 1. Subscription Verification
- **URL**: `POST /api/v1/subscription/verify`
- **Purpose**: Verify subscription status by email
- **Request**: `{"email": "user@example.com"}`
- **Response**: Subscription status with features

### 2. Subscription Status (Internal)
- **URL**: `GET /api/v1/subscription/status?email=user@example.com`
- **Purpose**: Internal subscription status check
- **Response**: Detailed subscription information

## Manual Subscription Management

### Adding Subscriptions via Django Admin
1. Go to Django Admin: `/admin/`
2. Navigate to "Subscriptions"
3. Click "Add Subscription"
4. Enter email and set `is_active` to True
5. Save

### Adding Subscriptions via Django Shell
```python
from subscriptions.models import Subscription

# Add a subscription
Subscription.objects.create(
    email="user@example.com",
    is_active=True
)

# Deactivate a subscription
subscription = Subscription.objects.get(email="user@example.com")
subscription.is_active = False
subscription.save()
```

## Frontend Integration Points

### 1. API Endpoint
The frontend will call `POST /api/v1/subscription/verify` with the user's email to verify subscription status.

### 2. Response Format
The API returns a standardized response that matches the frontend expectations:
```json
{
    "hasActiveSubscription": true,
    "subscriptionType": "premium",
    "expiresAt": null,
    "features": ["ad_removal", "priority_support"]
}
```

### 3. Error Handling
The API provides clear error messages for various scenarios:
- Invalid email format
- No subscription found
- Server errors

## Timeline

- **Phase 1-2**: 1 day (App creation, simple model)
- **Phase 3-4**: 1 day (Views, serializers)
- **Phase 5-6**: 1 day (URLs, admin)
- **Phase 7-8**: 1 day (Settings, migrations, testing)

**Total Estimated Time**: 4 days

## Success Metrics

1. **API Response Time**: < 200ms for subscription verification
2. **Uptime**: 99.9% availability
3. **Error Rate**: < 1% for valid requests
4. **Integration**: Seamless frontend integration
5. **Simplicity**: Easy manual management via admin
