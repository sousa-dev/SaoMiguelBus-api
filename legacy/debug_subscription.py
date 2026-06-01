#!/usr/bin/env python
import os
import sys
import django
import json

# Setup Django
sys.path.append('src')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaoMiguelBus.settings')
django.setup()

from django.test import Client
from django.urls import reverse

def test_subscription_creation():
    client = Client()
    
    # Try to get the correct URL
    try:
        url = reverse('subscriptions:verify_subscription')
        print(f"URL resolved to: {url}")
    except Exception as e:
        print(f"URL resolution error: {e}")
        # Let's try the direct URL
        url = '/api/v1/subscription/verify'
        print(f"Using direct URL: {url}")
    
    # Test data
    test_data = {
        "email": "test@example.com",
        "create_subscription": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6"
    }
    
    print(f"Sending request to: {url}")
    print(f"Data: {test_data}")
    
    response = client.post(
        url,
        data=json.dumps(test_data),
        content_type="application/json"
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.content.decode()}")

if __name__ == "__main__":
    test_subscription_creation() 