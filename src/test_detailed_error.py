import os
import django
import json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaoMiguelBus.settings')
django.setup()

from django.test import Client
from django.urls import reverse

def test_subscription_detailed():
    client = Client()
    url = reverse('subscriptions:verify_subscription')
    
    # Test with minimal valid data first
    test_data = {'email': 'test@example.com'}
    
    print(f"Testing URL: {url}")
    print(f"Test data: {test_data}")
    
    response = client.post(
        url, 
        data=json.dumps(test_data), 
        content_type='application/json',
        HTTP_ACCEPT='application/json'
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.items())}")
    
    # Try to parse JSON response
    try:
        response_data = response.json()
        print(f"JSON Response: {json.dumps(response_data, indent=2)}")
    except:
        print(f"Raw Response: {response.content.decode()}")

if __name__ == "__main__":
    test_subscription_detailed() 