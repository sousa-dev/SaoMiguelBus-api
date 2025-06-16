from django.test import TestCase, Client
from django.urls import reverse
from rest_framework import status
import json
from .models import Subscription


class SubscriptionModelTests(TestCase):
    """Test the Subscription model and its behavior"""
    
    def test_subscription_creation(self):
        """Test creating a subscription with default verification count"""
        subscription = Subscription.objects.create(
            email="test@example.com",
            is_active=True
        )
        self.assertEqual(subscription.verification_count, 0)
        self.assertTrue(subscription.is_active)
        self.assertEqual(str(subscription), "test@example.com - Active")
    
    def test_subscription_inactive_str(self):
        """Test string representation for inactive subscription"""
        subscription = Subscription.objects.create(
            email="inactive@example.com",
            is_active=False
        )
        self.assertEqual(str(subscription), "inactive@example.com - Inactive")


class SubscriptionVerificationTests(TestCase):
    """Test the subscription verification API endpoint"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.verify_url = reverse('subscriptions:verify_subscription')
        
        # Create test subscriptions
        self.active_subscription = Subscription.objects.create(
            email="active@example.com",
            is_active=True,
            verification_count=5
        )
        
        self.inactive_subscription = Subscription.objects.create(
            email="inactive@example.com", 
            is_active=False,
            verification_count=2
        )
    
    def test_verify_active_subscription_increments_count(self):
        """Test that verifying an active subscription increments the count"""
        initial_count = self.active_subscription.verification_count
        
        response = self.client.post(
            self.verify_url,
            data=json.dumps({"email": "active@example.com"}),
            content_type="application/json"
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        # Check response format
        self.assertTrue(data['hasActiveSubscription'])
        self.assertEqual(data['subscriptionType'], 'premium')
        self.assertEqual(data['features'], ['ad_removal', 'priority_support'])
        self.assertIsNone(data['expiresAt'])
        
        # Check that verification count was incremented
        self.active_subscription.refresh_from_db()
        self.assertEqual(self.active_subscription.verification_count, initial_count + 1)
    
    def test_verify_inactive_subscription_increments_count(self):
        """Test that verifying an inactive subscription increments count but returns no subscription"""
        initial_count = self.inactive_subscription.verification_count
        
        response = self.client.post(
            self.verify_url,
            data=json.dumps({"email": "inactive@example.com"}),
            content_type="application/json"
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        # Should return no active subscription
        self.assertFalse(data['hasActiveSubscription'])
        self.assertIsNone(data['subscriptionType'])
        self.assertEqual(data['features'], [])
        self.assertEqual(data['message'], 'No active subscription found for this email')
        
        # But verification count should still be incremented
        self.inactive_subscription.refresh_from_db()
        self.assertEqual(self.inactive_subscription.verification_count, initial_count + 1)
    
    def test_verify_nonexistent_email_no_count_increment(self):
        """Test that verifying a non-existent email doesn't create or increment anything"""
        response = self.client.post(
            self.verify_url,
            data=json.dumps({"email": "nonexistent@example.com"}),
            content_type="application/json"
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        # Should return no subscription
        self.assertFalse(data['hasActiveSubscription'])
        self.assertIsNone(data['subscriptionType'])
        self.assertEqual(data['features'], [])
        self.assertEqual(data['message'], 'No active subscription found for this email')
        
        # No subscription should be created
        self.assertFalse(Subscription.objects.filter(email="nonexistent@example.com").exists())
    
    def test_multiple_verifications_increment_count(self):
        """Test that multiple verifications correctly increment the count"""
        initial_count = self.active_subscription.verification_count
        
        # Call verify multiple times
        for i in range(3):
            response = self.client.post(
                self.verify_url,
                data=json.dumps({"email": "active@example.com"}),
                content_type="application/json"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check that count increased by 3
        self.active_subscription.refresh_from_db()
        self.assertEqual(self.active_subscription.verification_count, initial_count + 3)
    
    def test_invalid_email_format(self):
        """Test that invalid email format returns validation error"""
        response = self.client.post(
            self.verify_url,
            data=json.dumps({"email": "invalid-email"}),
            content_type="application/json"
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('error', data)
        self.assertIn('details', data)
    
    def test_missing_email_field(self):
        """Test that missing email field returns validation error"""
        response = self.client.post(
            self.verify_url,
            data=json.dumps({}),
            content_type="application/json"
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('error', data)
    
    def test_email_case_insensitive(self):
        """Test that email verification is case insensitive"""
        # Create subscription with lowercase email
        subscription = Subscription.objects.create(
            email="case@example.com",
            is_active=True,
            verification_count=0
        )
        
        # Test with uppercase email
        response = self.client.post(
            self.verify_url,
            data=json.dumps({"email": "CASE@EXAMPLE.COM"}),
            content_type="application/json"
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['hasActiveSubscription'])
        
        # Count should be incremented
        subscription.refresh_from_db()
        self.assertEqual(subscription.verification_count, 1)


class SubscriptionStatusTests(TestCase):
    """Test the subscription status API endpoint"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.status_url = reverse('subscriptions:subscription_status')
        
        self.active_subscription = Subscription.objects.create(
            email="status@example.com",
            is_active=True,
            verification_count=10
        )
    
    def test_subscription_status_active(self):
        """Test getting status for active subscription"""
        response = self.client.get(
            self.status_url,
            {'email': 'status@example.com'}
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        self.assertTrue(data['active'])
        self.assertIsNotNone(data['subscription'])
        self.assertEqual(data['subscription']['email'], 'status@example.com')
        self.assertEqual(data['subscription']['verification_count'], 10)
    
    def test_subscription_status_inactive(self):
        """Test getting status for inactive subscription"""
        response = self.client.get(
            self.status_url,
            {'email': 'nonexistent@example.com'}
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        self.assertFalse(data['active'])
        self.assertIsNone(data['subscription'])
    
    def test_subscription_status_missing_email(self):
        """Test status endpoint without email parameter"""
        response = self.client.get(self.status_url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('error', data)


class SubscriptionVerificationCountTests(TestCase):
    """Specific tests for verification count functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.verify_url = reverse('subscriptions:verify_subscription')
    
    def test_verification_count_starts_at_zero(self):
        """Test that new subscriptions start with verification_count = 0"""
        subscription = Subscription.objects.create(
            email="new@example.com",
            is_active=True
        )
        self.assertEqual(subscription.verification_count, 0)
    
    def test_verification_count_tracks_all_calls(self):
        """Test that verification count tracks calls regardless of subscription status"""
        # Create subscription
        subscription = Subscription.objects.create(
            email="track@example.com",
            is_active=True,
            verification_count=0
        )
        
        # Call API when active
        self.client.post(
            self.verify_url,
            data=json.dumps({"email": "track@example.com"}),
            content_type="application/json"
        )
        
        subscription.refresh_from_db()
        self.assertEqual(subscription.verification_count, 1)
        
        # Deactivate subscription
        subscription.is_active = False
        subscription.save()
        
        # Call API when inactive
        self.client.post(
            self.verify_url,
            data=json.dumps({"email": "track@example.com"}),
            content_type="application/json"
        )
        
        subscription.refresh_from_db()
        self.assertEqual(subscription.verification_count, 2)
    
    def test_concurrent_verification_count_increments(self):
        """Test that verification count handles multiple rapid calls correctly"""
        subscription = Subscription.objects.create(
            email="concurrent@example.com",
            is_active=True,
            verification_count=0
        )
        
        # Simulate rapid successive calls
        for _ in range(5):
            response = self.client.post(
                self.verify_url,
                data=json.dumps({"email": "concurrent@example.com"}),
                content_type="application/json"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        subscription.refresh_from_db()
        self.assertEqual(subscription.verification_count, 5)
    
    def test_updated_at_changes_when_verification_count_incremented(self):
        """Test that updated_at field is updated when verification count is incremented"""
        from django.utils import timezone
        import time
        
        subscription = Subscription.objects.create(
            email="timestamp@example.com",
            is_active=True,
            verification_count=0
        )
        
        # Store initial updated_at
        initial_updated_at = subscription.updated_at
        
        # Wait a small amount to ensure timestamp difference
        time.sleep(0.1)
        
        # Call verification endpoint
        response = self.client.post(
            self.verify_url,
            data=json.dumps({"email": "timestamp@example.com"}),
            content_type="application/json"
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Refresh and check
        subscription.refresh_from_db()
        
        # Verification count should be incremented
        self.assertEqual(subscription.verification_count, 1)
        
        # updated_at should be newer than initial
        self.assertGreater(subscription.updated_at, initial_updated_at)
        
        # Test second increment
        second_updated_at = subscription.updated_at
        time.sleep(0.1)
        
        # Call again
        self.client.post(
            self.verify_url,
            data=json.dumps({"email": "timestamp@example.com"}),
            content_type="application/json"
        )
        
        subscription.refresh_from_db()
        self.assertEqual(subscription.verification_count, 2)
        self.assertGreater(subscription.updated_at, second_updated_at)
