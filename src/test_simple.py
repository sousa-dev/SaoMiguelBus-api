#!/usr/bin/env python
import os
import sys
import django
import json

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaoMiguelBus.settings')
django.setup()

from django.test import Client, TestCase
from django.urls import reverse

def test_subscription_creation():
    client = Client()
    url = reverse('subscriptions:verify_subscription')
    
    # Test data - just email first
    test_data_simple = {
        "email": "test@example.com"
    }
    
    print("Testing simple email verification:")
    response = client.post(
        url,
        data=json.dumps(test_data_simple),
        content_type="application/json"
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.content.decode()}")
    print()
    
    # Test data with create_subscription
    test_data_with_code = {
        "email": "test@example.com",
        "create_subscription": "test_code"
    }
    
    print("Testing with create_subscription parameter:")
    response = client.post(
        url,
        data=json.dumps(test_data_with_code),
        content_type="application/json"
    )
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.content.decode()}")

if __name__ == "__main__":
    test_subscription_creation() 