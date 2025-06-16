from django.shortcuts import render
import logging
from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from .models import Subscription
from .serializers import (
    SubscriptionSerializer,
    SubscriptionVerificationRequestSerializer,
    SubscriptionVerificationResponseSerializer
)

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
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
        
        # Find subscription (active or inactive) and increment verification count
        subscription = Subscription.objects.filter(email=email).first()
        
        if subscription:
            # Increment verification count
            subscription.verification_count += 1
            subscription.save()  # Remove update_fields to allow auto_now to work
        
        # Check if subscription is active for response
        active_subscription = Subscription.objects.filter(
            email=email,
            is_active=True
        ).first()
        
        # Prepare response
        if active_subscription:
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
