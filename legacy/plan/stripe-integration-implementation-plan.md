# Stripe Integration Implementation Plan

## Overview
Replace the current manual subscription system with a Stripe-first approach that:
1. **Primary**: Always check Stripe for active subscriptions
2. **Fallback**: Use manual database entries if Stripe fails or has no active subscription
3. **Benefits**: Automatic sync with actual payments + manual override capability

## Architecture Change

### Current Flow
```
Email Input → Database Lookup → Response
```

### New Flow
```
Email Input → Stripe API Check → If Active: Return True
                                ↓ If Not Active/Error
                             → Database Fallback → Response
```

## Implementation Details

### 1. New Service Layer

#### Create `subscriptions/stripe_service.py`
```python
import stripe
import logging
from typing import Tuple, List

logger = logging.getLogger(__name__)

# Hardcoded for now - move to settings later
stripe.api_key = "sk_test_YOUR_STRIPE_SECRET_KEY_HERE"

def check_stripe_subscription(email: str) -> Tuple[bool, List[str], str]:
    """
    Check Stripe for active subscription
    
    Returns:
        (has_active_subscription, features_list, subscription_type)
    """
    try:
        # Find customer by email
        customers = stripe.Customer.list(email=email, limit=1)
        
        if not customers.data:
            logger.info(f"No Stripe customer found for email: {email}")
            return False, [], None
        
        customer = customers.data[0]
        logger.info(f"Found Stripe customer: {customer.id} for email: {email}")
        
        # Get active subscriptions
        subscriptions = stripe.Subscription.list(
            customer=customer.id,
            status='active',
            limit=10,
            expand=['data.items.data.price.product']
        )
        
        if not subscriptions.data:
            logger.info(f"No active subscriptions found for customer: {customer.id}")
            return False, [], None
        
        # Process subscription data
        features = ['ad_removal', 'priority_support']  # Default premium features
        subscription_type = 'premium'
        
        # Could enhance this to read from product metadata
        # for sub in subscriptions.data:
        #     for item in sub.items.data:
        #         product = item.price.product
        #         if hasattr(product, 'metadata'):
        #             # Extract features from product metadata
        #             pass
        
        logger.info(f"Active subscription found for {email}")
        return True, features, subscription_type
        
    except stripe.error.RateLimitError as e:
        logger.error(f"Stripe rate limit error for {email}: {e}")
        return False, [], None
        
    except stripe.error.InvalidRequestError as e:
        logger.error(f"Stripe invalid request for {email}: {e}")
        return False, [], None
        
    except stripe.error.AuthenticationError as e:
        logger.error(f"Stripe authentication error: {e}")
        return False, [], None
        
    except stripe.error.APIConnectionError as e:
        logger.error(f"Stripe connection error for {email}: {e}")
        return False, [], None
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe general error for {email}: {e}")
        return False, [], None
        
    except Exception as e:
        logger.error(f"Unexpected error checking Stripe for {email}: {e}")
        return False, [], None

def check_manual_subscription(email: str) -> Tuple[bool, List[str], str]:
    """
    Fallback to manual database subscription
    
    Returns:
        (has_active_subscription, features_list, subscription_type)
    """
    from .models import Subscription
    
    try:
        subscription = Subscription.objects.filter(
            email=email,
            is_active=True
        ).first()
        
        if subscription:
            logger.info(f"Manual subscription found for {email}")
            return True, ['ad_removal', 'priority_support'], 'premium'
        else:
            logger.info(f"No manual subscription found for {email}")
            return False, [], None
            
    except Exception as e:
        logger.error(f"Error checking manual subscription for {email}: {e}")
        return False, [], None

def verify_subscription_combined(email: str) -> dict:
    """
    Combined verification: Stripe first, then manual fallback
    
    Returns:
        Complete response dict ready for API
    """
    # Step 1: Check Stripe
    has_stripe_sub, stripe_features, stripe_type = check_stripe_subscription(email)
    
    if has_stripe_sub:
        logger.info(f"Using Stripe subscription for {email}")
        return {
            'hasActiveSubscription': True,
            'subscriptionType': stripe_type,
            'expiresAt': None,
            'features': stripe_features,
            'message': None,
            'source': 'stripe'
        }
    
    # Step 2: Fallback to manual database
    logger.info(f"Stripe check failed/inactive for {email}, checking manual database")
    has_manual_sub, manual_features, manual_type = check_manual_subscription(email)
    
    if has_manual_sub:
        logger.info(f"Using manual subscription for {email}")
        return {
            'hasActiveSubscription': True,
            'subscriptionType': manual_type,
            'expiresAt': None,
            'features': manual_features,
            'message': None,
            'source': 'manual'
        }
    
    # Step 3: No subscription found anywhere
    logger.info(f"No subscription found for {email} in Stripe or manual database")
    return {
        'hasActiveSubscription': False,
        'subscriptionType': None,
        'expiresAt': None,
        'features': [],
        'message': 'No active subscription found for this email',
        'source': 'none'
    }
```

### 2. Update Views

#### Modify `subscriptions/views.py`
```python
# Add import
from .stripe_service import verify_subscription_combined

@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def verify_subscription(request):
    """
    Verify subscription status by email
    Now using Stripe-first approach with manual fallback
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
        
        # Use combined verification (Stripe + Manual fallback)
        response_data = verify_subscription_combined(email)
        
        # Remove 'source' from response (internal use only)
        response_for_client = {k: v for k, v in response_data.items() if k != 'source'}
        
        # Validate response format
        response_serializer = SubscriptionVerificationResponseSerializer(data=response_for_client)
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
        # Fail-safe: return no subscription on unexpected errors
        return Response({
            'hasActiveSubscription': False,
            'subscriptionType': None,
            'expiresAt': None,
            'features': [],
            'message': 'Unable to verify subscription status'
        }, status=status.HTTP_200_OK)
```

### 3. Update Requirements

#### Add to `requirements.txt`
```
stripe>=5.0.0
```

### 4. Enhanced Logging

#### Add to `settings.py`
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'subscriptions.log',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'subscriptions': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

## Testing Strategy

### 1. Unit Tests
```python
# subscriptions/tests.py
from django.test import TestCase
from unittest.mock import patch, MagicMock
from .stripe_service import check_stripe_subscription, verify_subscription_combined

class StripeIntegrationTests(TestCase):
    
    @patch('stripe.Customer.list')
    def test_stripe_customer_not_found(self, mock_customer_list):
        mock_customer_list.return_value.data = []
        
        has_sub, features, sub_type = check_stripe_subscription('notfound@test.com')
        
        self.assertFalse(has_sub)
        self.assertEqual(features, [])
        self.assertIsNone(sub_type)
    
    @patch('stripe.Subscription.list')
    @patch('stripe.Customer.list')
    def test_stripe_active_subscription(self, mock_customer_list, mock_sub_list):
        # Mock customer found
        mock_customer = MagicMock()
        mock_customer.id = 'cus_test123'
        mock_customer_list.return_value.data = [mock_customer]
        
        # Mock active subscription
        mock_subscription = MagicMock()
        mock_sub_list.return_value.data = [mock_subscription]
        
        has_sub, features, sub_type = check_stripe_subscription('premium@test.com')
        
        self.assertTrue(has_sub)
        self.assertEqual(features, ['ad_removal', 'priority_support'])
        self.assertEqual(sub_type, 'premium')
    
    def test_fallback_to_manual_subscription(self):
        # Create manual subscription
        from .models import Subscription
        Subscription.objects.create(email='manual@test.com', is_active=True)
        
        # Mock Stripe failure
        with patch('subscriptions.stripe_service.check_stripe_subscription') as mock_stripe:
            mock_stripe.return_value = (False, [], None)
            
            result = verify_subscription_combined('manual@test.com')
            
            self.assertTrue(result['hasActiveSubscription'])
            self.assertEqual(result['source'], 'manual')
```

### 2. Integration Tests
- Test with real Stripe test customers
- Test with manual database entries
- Test fallback scenarios
- Test error handling

### 3. Manual Testing Scenarios
```python
# Test emails to verify in different scenarios:

# Stripe test customers (create these in your Stripe dashboard)
stripe_active_emails = [
    'stripe_user@test.com',  # Create active subscription in Stripe
    'stripe_premium@test.com'
]

# Manual database entries (for fallback testing)
manual_fallback_emails = [
    'manual_override@saomiguelbus.com',
    'special_access@example.com'
]

# No subscription anywhere
no_subscription_emails = [
    'random@nowhere.com',
    'notfound@test.com'
]
```

## Migration Plan

### Phase 1: Implementation (1-2 hours)
1. Install Stripe SDK: `pip install stripe`
2. Create `stripe_service.py` with hardcoded key
3. Update views to use new service
4. Test with Stripe test data

### Phase 2: Testing (30 minutes)
1. Create test Stripe customers with active subscriptions
2. Test API endpoints with various scenarios
3. Verify fallback to manual database works
4. Check error handling and logging

### Phase 3: Production Preparation (Later)
1. Move Stripe key to environment variables
2. Set up proper Stripe webhook endpoints
3. Add monitoring and alerting
4. Performance optimization if needed

## Error Handling Strategy

### Stripe API Failures
- **Rate Limits**: Log and fallback to manual DB
- **Network Issues**: Log and fallback to manual DB  
- **Authentication**: Log error, fallback to manual DB
- **Invalid Requests**: Log and fallback to manual DB

### Manual DB Failures
- **Database Errors**: Log error, return no subscription (fail-safe)
- **Model Issues**: Log error, return no subscription

### Response Strategy
- Always return HTTP 200 for valid email formats
- Never expose Stripe errors to frontend
- Log all errors for debugging
- Graceful degradation (show ads when in doubt)

## Benefits of This Approach

### ✅ Advantages
1. **Real-time accuracy**: Always reflects current Stripe billing status
2. **Manual override**: Can force subscriptions via database when needed
3. **Fault tolerance**: Falls back gracefully if Stripe is down
4. **No sync issues**: No cron jobs or delayed updates
5. **Easy testing**: Can test with both Stripe test data and manual entries

### ⚠️ Considerations
1. **Slightly slower**: Each request hits Stripe API (usually <200ms)
2. **API dependency**: Relies on Stripe being available
3. **Rate limits**: Stripe has API rate limits (handled with fallback)

## Monitoring & Logging

### Key Metrics to Track
- Stripe API response times
- Stripe API error rates
- Fallback usage frequency
- Overall subscription verification success rate

### Log Messages to Monitor
- `"Using Stripe subscription for {email}"` - Stripe success
- `"Using manual subscription for {email}"` - Fallback used
- `"Stripe rate limit error"` - Need to optimize or cache
- `"Stripe connection error"` - Network issues

## Future Enhancements

### Phase 2 (Optional)
1. **Caching Layer**: Cache Stripe responses for 5-10 minutes
2. **Multiple Plans**: Support different subscription tiers from Stripe
3. **Metadata Features**: Read feature lists from Stripe product metadata
4. **Webhook Sync**: Add webhook endpoint to keep manual DB in sync
5. **Analytics**: Track subscription verification patterns

## Implementation Checklist

- [ ] Create `stripe_service.py` with hardcoded key
- [ ] Update `views.py` to use new service
- [ ] Add stripe to requirements.txt
- [ ] Test with Stripe test customers
- [ ] Test fallback to manual database
- [ ] Verify error handling works
- [ ] Test all existing manual subscriptions still work
- [ ] Update logging configuration
- [ ] Create unit tests
- [ ] Document new behavior for frontend team

## Risk Mitigation

### Rollback Plan
- Keep existing views and models unchanged initially
- Add new service as optional layer
- Can easily revert to pure manual system if issues arise

### Gradual Deployment
1. Deploy with feature flag to test subset of requests
2. Monitor logs and error rates
3. Gradually increase Stripe usage percentage
4. Full rollout once stable

---

This plan provides a robust, fault-tolerant subscription system that leverages Stripe's real-time data while maintaining manual override capabilities. 