import os
import django
import json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaoMiguelBus.settings')
django.setup()

from django.test import Client, override_settings
from django.urls import reverse

@override_settings(DEBUG=False)
def test_with_debug_false():
    client = Client()
    url = reverse('subscriptions:verify_subscription')
    test_data = {'email': 'test@example.com'}
    response = client.post(url, data=json.dumps(test_data), content_type='application/json')
    print(f'Status: {response.status_code}')
    print(f'Content: {response.content.decode()}')

if __name__ == "__main__":
    test_with_debug_false() 