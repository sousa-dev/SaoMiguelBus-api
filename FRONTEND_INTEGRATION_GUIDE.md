# 📱 Frontend Integration Guide - Subscription Verification API

## 🎯 Overview

This guide explains how the subscription verification API works and how your frontend should integrate with it to handle subscription-based features like ad removal and premium content.

## 🌐 API Endpoint Details

### Primary Verification Endpoint
- **URL**: `POST /api/v1/subscription/verify`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **Purpose**: Verify if an email has an active subscription

### Request Format
```json
{
    "email": "user@example.com"
}
```

### Response Format (Always HTTP 200 for valid requests)
```json
{
    "hasActiveSubscription": boolean,
    "subscriptionType": string | null,
    "expiresAt": string | null,
    "features": string[],
    "message": string | null
}
```

## 📋 Response Scenarios

### 1. ✅ Active Subscription Found
**Scenario**: Email exists in database with `is_active: true`

```json
{
    "hasActiveSubscription": true,
    "subscriptionType": "premium",
    "expiresAt": null,
    "features": ["ad_removal", "priority_support"],
    "message": null
}
```

**Frontend Action**: Enable premium features, hide ads

### 2. ❌ No Active Subscription (Email Exists but Inactive)
**Scenario**: Email exists in database with `is_active: false`

```json
{
    "hasActiveSubscription": false,
    "subscriptionType": null,
    "expiresAt": null,
    "features": [],
    "message": "No active subscription found for this email"
}
```

**Frontend Action**: Show ads, disable premium features

### 3. ❌ Email Doesn't Exist in Database
**Scenario**: Email has never been registered for any subscription

```json
{
    "hasActiveSubscription": false,
    "subscriptionType": null,
    "expiresAt": null,
    "features": [],
    "message": "No active subscription found for this email"
}
```

**Frontend Action**: Show ads, disable premium features

### 4. ⚠️ Invalid Email Format
**Scenario**: Malformed email address submitted

```json
{
    "error": "Invalid request data",
    "details": {
        "email": ["Enter a valid email address."]
    }
}
```
**HTTP Status**: `400 Bad Request`
**Frontend Action**: Show validation error to user

## 🔧 Frontend Implementation Logic

### Basic Integration Flow

```javascript
async function checkSubscriptionStatus(email) {
    try {
        const response = await fetch('/api/v1/subscription/verify', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email: email })
        });

        if (response.ok) {
            const data = await response.json();
            
            // Check if response has error (400 status for invalid email)
            if (data.error) {
                console.error('Validation error:', data.details);
                return { hasSubscription: false, error: data.details };
            }
            
            // Normal response - check subscription status
            return {
                hasSubscription: data.hasActiveSubscription,
                features: data.features || [],
                subscriptionType: data.subscriptionType,
                message: data.message
            };
        } else {
            console.error('API request failed:', response.status);
            return { hasSubscription: false, error: 'API request failed' };
        }
    } catch (error) {
        console.error('Network error:', error);
        return { hasSubscription: false, error: 'Network error' };
    }
}
```

### Feature Control Logic

```javascript
function applySubscriptionFeatures(subscriptionData) {
    const { hasSubscription, features } = subscriptionData;
    
    if (hasSubscription) {
        // User has active subscription
        if (features.includes('ad_removal')) {
            hideAllAds();
        }
        if (features.includes('priority_support')) {
            enablePrioritySupport();
        }
        showPremiumBadge();
    } else {
        // User doesn't have active subscription
        showAllAds();
        disablePremiumFeatures();
        hidePremiumBadge();
    }
}

function hideAllAds() {
    document.querySelectorAll('.advertisement').forEach(ad => {
        ad.style.display = 'none';
    });
}

function showAllAds() {
    document.querySelectorAll('.advertisement').forEach(ad => {
        ad.style.display = 'block';
    });
}
```

### Complete Usage Example

```javascript
// Example usage in your app
async function initializeUserExperience(userEmail) {
    // Show loading state
    showLoadingSpinner();
    
    // Check subscription status
    const subscriptionResult = await checkSubscriptionStatus(userEmail);
    
    if (subscriptionResult.error) {
        // Handle errors (invalid email, network issues, etc.)
        showErrorMessage('Unable to verify subscription status');
        // Default to showing ads on error
        showAllAds();
    } else {
        // Apply subscription-based features
        applySubscriptionFeatures(subscriptionResult);
        
        // Optional: Show subscription status to user
        if (subscriptionResult.hasSubscription) {
            showSubscriptionStatus('Premium Active ✨');
        }
    }
    
    hideLoadingSpinner();
}
```

## ⚠️ Important Behavior Notes

### 1. **No Errors for Non-Existent Emails**
- ✅ Non-existent emails return `hasActiveSubscription: false` 
- ✅ HTTP status is always `200 OK` for valid email formats
- ✅ No exceptions or 404 errors are thrown
- **Frontend should treat this the same as inactive subscriptions**

### 2. **Email Validation**
- ❌ Invalid email formats return `400 Bad Request`
- Check for `data.error` in response to handle validation errors
- Display user-friendly validation messages

### 3. **Features Array**
- Current features: `["ad_removal", "priority_support"]`
- Check for specific features instead of assuming all premium features
- Future-proof for additional feature types

### 4. **Subscription Types**
- Currently only `"premium"` or `null`
- Future versions may include different subscription tiers

## 🔄 Recommended Error Handling

```javascript
function handleSubscriptionResponse(data, response) {
    // Case 1: Validation error (400 status)
    if (!response.ok && data.error) {
        return {
            status: 'validation_error',
            message: 'Please enter a valid email address',
            hasSubscription: false
        };
    }
    
    // Case 2: Network/server error (500, etc.)
    if (!response.ok) {
        return {
            status: 'server_error',
            message: 'Unable to verify subscription. Please try again.',
            hasSubscription: false  // Default to no subscription on errors
        };
    }
    
    // Case 3: Successful response
    return {
        status: 'success',
        hasSubscription: data.hasActiveSubscription,
        features: data.features,
        subscriptionType: data.subscriptionType,
        message: data.message
    };
}
```

## 🧪 Testing Your Frontend Integration

### Test Cases to Verify

1. **Active Subscription**:
   - Test with: `premium_user@saomiguelbus.com`
   - Expected: Ads hidden, premium features enabled

2. **Inactive Subscription**:
   - Test with: `cancelled_user@example.com`
   - Expected: Ads shown, premium features disabled

3. **Non-Existent Email**:
   - Test with: `nonexistent@test.com`
   - Expected: Ads shown, premium features disabled (same as inactive)

4. **Invalid Email**:
   - Test with: `invalid-email`
   - Expected: Validation error message, ads shown

5. **Network Error**:
   - Test with API offline
   - Expected: Error message, ads shown (fail-safe)

## 📊 Sample Test Data

The API currently has these test subscriptions available:

```javascript
// Active subscriptions (should hide ads)
const activeEmails = [
    'premium_user@saomiguelbus.com',
    'paid_user@example.com',
    'vip_user@premium.com'
];

// Inactive subscriptions (should show ads)
const inactiveEmails = [
    'cancelled_user@example.com',
    'inactive_user@test.com'
];

// Non-existent emails (should show ads)
const nonExistentEmails = [
    'random@test.com',
    'user@nowhere.com'
];
```

## 🎯 Key Frontend Checklist

- [ ] Handle `hasActiveSubscription: false` for both non-existent and inactive emails
- [ ] Check `features` array for specific capabilities
- [ ] Handle validation errors for invalid email formats
- [ ] Implement fail-safe behavior (show ads on API errors)
- [ ] Test all scenarios with sample data
- [ ] Show appropriate loading states during API calls
- [ ] Provide user feedback for subscription status

## 🚀 Performance Tips

1. **Cache subscription status** for the session to avoid repeated API calls
2. **Implement timeout** for API requests (5-10 seconds recommended)
3. **Show ads immediately on timeout** for better user experience
4. **Preload subscription check** when user email is available

## 🔒 Security Considerations

- API endpoints are public (no authentication required)
- Only email verification, no sensitive data exposed
- Rate limiting may apply (implement request throttling if needed)
- Always validate email format client-side before API calls

---

This API provides a simple, reliable way to verify subscription status and control premium features in your frontend application. The consistent response format and error handling make it easy to integrate and maintain. 