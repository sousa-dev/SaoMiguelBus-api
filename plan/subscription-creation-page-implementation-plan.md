# Subscription Creation Page Implementation Plan

## Overview
Create a new static page that allows users to create premium subscriptions by entering their email address. The page will be accessible via a hard-to-guess URL and will create a subscription in the database when the correct verification code is provided.

## Requirements
1. Create a new static HTML page with a 64-character random filename
2. Page should prompt user for email and verify subscription
3. API should accept a `create_subscription` parameter with a 64-digit verification code
4. If code matches, create a new Subscription entity before verification
5. Maintain existing verification logic

## Implementation Details

### 1. Webapp Changes (SaoMiguelBus-webapp/)

#### 1.1 Create New Static Page
- **File**: Create a new HTML file with a 64-character random filename
  - Example: `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6.html`
  - Use a cryptographically secure random string generator
  - Place in the root directory of SaoMiguelBus-webapp/

#### 1.2 Page Structure
The page should follow the same styling as `index.html` and include:

```html
<!DOCTYPE html>
<html lang="pt" class="scroll-smooth">
<head>
    <!-- Same head content as index.html -->
    <title>Thank You - São Miguel Bus</title>
    <!-- Include all CSS and JS dependencies from index.html -->
</head>
<body class="bg-white text-gray-800">
    <div class="min-h-screen flex items-center justify-center p-4">
        <div class="w-full max-w-md mx-auto bg-white rounded-3xl shadow-lg overflow-hidden">
            <!-- Success Alert -->
            <div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
                <div class="flex items-center">
                    <i class="fas fa-check-circle text-green-600 mr-2"></i>
                    <span class="text-green-800 font-medium" data-i18n="thankYouMessage">
                        Obrigado por ajudar o desenvolvimento do São Miguel Bus.
                    </span>
                </div>
            </div>
            
            <!-- Email Input Form -->
            <div class="p-6">
                <h2 class="text-xl font-semibold text-gray-800 mb-4" data-i18n="verifySubscriptionTitle">
                    Verificar Subscrição
                </h2>
                
                <div class="space-y-4">
                    <div>
                        <input type="email" id="verificationEmail" 
                               placeholder="Enter your subscription email" 
                               class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500"
                               data-i18n-placeholder="emailPlaceholder">
                    </div>
                    
                    <!-- Error Message -->
                    <div id="verificationError" class="hidden bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded text-sm"></div>
                    
                    <button onclick="verifyExistingSubscription()" 
                            class="w-full bg-green-500 text-white py-2 rounded-lg hover:bg-green-600 transition duration-300"
                            data-umami-event="verify-subscription">
                        <span data-i18n="verifyButton">Verify Subscription</span>
                    </button>
                </div>
            </div>
        </div>
    </div>
    
    <!-- Include necessary JavaScript files -->
    <script src="js/i18n.js"></script>
    <script src="js/adRemovalHandler.js"></script>
    <!-- Add custom script for this page -->
    <script src="js/subscriptionCreationHandler.js"></script>
</body>
</html>
```

#### 1.3 Create JavaScript Handler
Create `js/subscriptionCreationHandler.js`:

```javascript
// Hardcoded verification code (64 characters)
const CREATION_VERIFICATION_CODE = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6";

function clearVerificationError() {
    document.getElementById('verificationError').classList.add('hidden');
}

function verifyExistingSubscription() {
    const email = document.getElementById('verificationEmail').value.trim();
    
    if (!email) {
        showVerificationError('Please enter your email address');
        return;
    }
    
    if (!isValidEmail(email)) {
        showVerificationError('Please enter a valid email address');
        return;
    }
    
    // Show loading state
    const button = event.target;
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Verifying...';
    button.disabled = true;
    
    // Make API call with creation code
    fetch('https://api.saomiguelbus.com/api/v1/subscriptions/verify/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            email: email,
            create_subscription: CREATION_VERIFICATION_CODE
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.hasActiveSubscription) {
            // Success - redirect to main page
            window.location.href = '/index.html?premium=activated';
        } else {
            showVerificationError(data.message || 'No active subscription found for this email');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showVerificationError('An error occurred. Please try again.');
    })
    .finally(() => {
        // Restore button state
        button.innerHTML = originalText;
        button.disabled = false;
    });
}

function showVerificationError(message) {
    const errorDiv = document.getElementById('verificationError');
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
}

function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    // Set up language support
    if (typeof updatePageContent === 'function') {
        updatePageContent();
    }
    
    // Clear error on input
    document.getElementById('verificationEmail').addEventListener('input', clearVerificationError);
});
```

#### 1.4 Update i18n.js
Add new translation keys to `locales/` files:

**en.json:**
```json
{
  "thankYouMessage": "Thank you for supporting the App.",
  "verifySubscriptionTitle": "Verify Subscription",
  "emailPlaceholder": "Enter your subscription email",
  "verifyButton": "Verify Subscription"
}
```

**pt.json:**
```json
{
  "thankYouMessage": "Obrigado por ajudar o desenvolvimento do São Miguel Bus.",
  "verifySubscriptionTitle": "Verificar Subscrição",
  "emailPlaceholder": "Introduza o email da sua subscrição",
  "verifyButton": "Verificar Subscrição"
}
```

### 2. API Changes (SaoMiguelBus-api/)

#### 2.1 Update Subscription Model
No changes needed to the model - it already supports the required fields.

#### 2.2 Update Serializers
Update `src/subscriptions/serializers.py`:

```python
class SubscriptionVerificationRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    create_subscription = serializers.CharField(required=False, max_length=64)
```

#### 2.3 Update Views
Modify `src/subscriptions/views.py` in the `verify_subscription` function:

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

#### 2.4 Update URL Configuration
No changes needed - the existing endpoint will handle the new parameter.

### 3. Security Considerations

#### 3.1 URL Obfuscation
- The 64-character filename makes the URL difficult to guess
- The verification code adds an additional layer of protection
- Consider implementing rate limiting on the API endpoint

#### 3.2 Code Protection
- The verification code is hardcoded in both frontend and backend
- Consider environment variables for production deployment
- Monitor API logs for suspicious activity

### 4. Testing Plan

#### 4.1 Frontend Testing
1. Test page loads correctly with proper styling
2. Test email validation
3. Test API integration with correct verification code
4. Test error handling
5. Test language switching

#### 4.2 Backend Testing
1. Test subscription creation with valid code
2. Test subscription activation for existing inactive subscriptions
3. Test verification without creation code (existing functionality)
4. Test error handling for invalid codes
5. Test email validation

#### 4.3 Integration Testing
1. Test complete flow from page to subscription creation
2. Test redirect to main page after successful verification
3. Test error scenarios

### 5. Deployment Steps

#### 5.1 Webapp Deployment
1. Generate 64-character random filename
2. Create the HTML file with the generated name
3. Create the JavaScript handler file
4. Update translation files
5. Deploy to GitHub Pages

#### 5.2 API Deployment
1. Update the views.py file
2. Update serializers.py file
3. Test the changes locally
4. Deploy to production
5. Monitor logs for any issues

### 6. Monitoring and Maintenance

#### 6.1 Logging
- Monitor subscription creation logs
- Track verification attempts
- Monitor for potential abuse

#### 6.2 Maintenance
- Regularly rotate the verification code if needed
- Monitor subscription creation patterns
- Update translations as needed

## Files to Create/Modify

### New Files:
1. `SaoMiguelBus-webapp/[64-char-random].html`
2. `SaoMiguelBus-webapp/js/subscriptionCreationHandler.js`

### Modified Files:
1. `SaoMiguelBus-webapp/locales/en.json`
2. `SaoMiguelBus-webapp/locales/pt.json`
3. `SaoMiguelBus-api/src/subscriptions/serializers.py`
4. `SaoMiguelBus-api/src/subscriptions/views.py`

## Success Criteria
1. Users can access the page via the hard-to-guess URL
2. Email validation works correctly
3. Subscription creation works with the verification code
4. Existing verification functionality remains unchanged
5. Proper error handling and user feedback
6. Multilingual support
7. Consistent styling with the main application 