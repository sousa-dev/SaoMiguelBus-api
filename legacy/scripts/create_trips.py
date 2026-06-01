import random
import time
import requests

endpoint = 'https://127.0.0.1:8000/api/v1/data/'

for i in range(1, 6000):
    try:
        print(f"Requesting {endpoint}{i}")
        response = requests.get(f"{endpoint}{i}")
        print(f'\t{response}\n')
        wait_time = random.uniform(0.1, 1)
        print(f"Waiting {wait_time} seconds")             
        time.sleep(wait_time)
    except Exception as e:
        print(f"Error: {e}")
        continue
        
    