import requests

response = requests.get('https://saomiguelbus-api.herokuapp.com/api/v1/stats').json()

stats = {}

for stat in response:
    if stat['request'] in stats:
        stats[stat['request']].append(stat)
    else:
        stats[stat['request']] = [stat]

#print(f"Android Load Requests: {len(stats['android_load'])}\nGet Route Requests: {len(stats['get_route'])}")
