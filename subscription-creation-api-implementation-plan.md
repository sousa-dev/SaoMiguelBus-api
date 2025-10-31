# Subscription Creation API Implementation Plan

## Overview
Update the existing subscription verification API to support subscription creation when a specific verification code is provided. This allows users to create premium subscriptions through a dedicated web page.

## Requirements
1. Accept a `create_subscription` parameter with a 64-character verification code
2. Create new Subscription entities when the code matches
3. Maintain existing verification functionality
4. Handle both new subscriptions and activation of existing inactive subscriptions

## Implementation Details

### 1. Update Serializers

#### 1.1 Modify SubscriptionVerificationRequestSerializer
**File**: `src/subscriptions/serializers.py`

Update the existing serializer to accept the new parameter:

```python
class SubscriptionVerificationRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    create_subscription = serializers.CharField(required=False, max_length=64)
```

### 2. Update Views

#### 2.1 Modify verify_subscription Function
**File**: `src/subscriptions/views.py`

Update the existing `verify_subscription` function to handle subscription creation:

```python
def verify_subscription(request):
    """
    Verify subscription status by email
    
    Request:
    {
        "email": "user@example.com",
        "create_subscription": "optional_64_char_code"
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
        create_subscription_code = serializer.validated_data.get('create_subscription')
        
        # Hardcoded verification code (must match the one in the webapp)
        CREATION_VERIFICATION_CODE = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6"
        
        # Check if creation code is provided and matches
        if create_subscription_code and create_subscription_code == CREATION_VERIFICATION_CODE:
            # Create subscription if it doesn't exist
            subscription, created = Subscription.objects.get_or_create(
                email=email,
                defaults={
                    'is_active': True,
                    'verification_count': 0
                }
            )
            
            if created:
                logger.info(f"Created new subscription for email: {email}")
            else:
                # If subscription exists but is inactive, activate it
                if not subscription.is_active:
                    subscription.is_active = True
                    subscription.save()
                    logger.info(f"Activated existing subscription for email: {email}")
        
        # Find subscription (active or inactive) and increment verification count
        subscription = Subscription.objects.filter(email=email).first()
        
        if subscription:
            # Increment verification count
            subscription.verification_count += 1
            subscription.save()
        
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
```

### 3. Security Considerations

#### 3.1 Verification Code Protection
- The verification code is hardcoded in the backend
- Consider using environment variables for production deployment
- Monitor API logs for suspicious activity patterns

#### 3.2 Rate Limiting
- Consider implementing rate limiting on the verification endpoint
- Monitor for potential abuse of the subscription creation feature

### 4. Testing Plan

#### 4.1 Unit Testing
1. Test subscription creation with valid verification code
2. Test subscription activation for existing inactive subscriptions
3. Test verification without creation code (existing functionality)
4. Test error handling for invalid codes
5. Test email validation

#### 4.2 Integration Testing
1. Test complete flow from webapp to subscription creation
2. Test error scenarios and edge cases
3. Test logging functionality

### 5. Deployment Steps

#### 5.1 Pre-deployment
1. Update the serializers.py file
2. Update the views.py file
3. Test the changes locally
4. Review security implications

#### 5.2 Deployment
1. Deploy to staging environment first
2. Test with the webapp integration
3. Deploy to production
4. Monitor logs for any issues

#### 5.3 Post-deployment
1. Monitor subscription creation patterns
2. Check for any error logs
3. Verify existing functionality still works

### 6. Monitoring and Maintenance

#### 6.1 Logging
- Monitor subscription creation logs
- Track verification attempts
- Monitor for potential abuse

#### 6.2 Maintenance
- Regularly review the verification code
- Monitor subscription creation patterns
- Update security measures as needed

## Files to Modify

### Modified Files:
1. `src/subscriptions/serializers.py` - Add create_subscription parameter
2. `src/subscriptions/views.py` - Update verify_subscription function

### No Changes Needed:
1. `src/subscriptions/models.py` - Model already supports required fields
2. URL configuration - Existing endpoint will handle new parameter

## Success Criteria
1. API accepts create_subscription parameter
2. Subscription creation works with valid verification code
3. Existing verification functionality remains unchanged
4. Proper error handling and logging
5. Security measures are in place
6. Integration with webapp works correctly

## API Endpoint Details

**Endpoint**: `POST /api/v1/subscriptions/verify/`

**Request Body**:
```json
{
    "email": "user@example.com",
    "create_subscription": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6"
}
```

**Response**:
```json
{
    "hasActiveSubscription": true,
    "subscriptionType": "premium",
    "expiresAt": null,
    "features": ["ad_removal", "priority_support"],
    "message": null
}
```

## Verification Code
The hardcoded verification code that must be used:
```
a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
```

This code must match exactly between the frontend and backend for subscription creation to work. 