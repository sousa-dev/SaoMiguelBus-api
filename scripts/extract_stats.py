import requests
import functions as f

if __name__ == "__main__":
    response = requests.get('https://saomiguelbus-api.herokuapp.com/api/v1/stats').json()

    stats = {}

    for stat in response:
        if stat['request'] in stats:
            stats[stat['request']].append(stat)
        else:
            stats[stat['request']] = [stat]


    print("Get Route Requests")
    get_route_requests = f.group_get_routes(stats['get_route'])
    for route, request in get_route_requests.items():
        print(f"{route}: {len(request)}")

    print("\nFind Requests")
    find_requests = f.group_find(stats['find_routes'])
    for route, request in find_requests.items():
        print(f"{route}: {len(request)}")

    print("\nMap Requests")
    map_requests = f.group_map(stats['get_directions'])
    for route, request in map_requests.items():
        print(f"{route}: {len(request)}")

    print("\nTotal Android Loads: ", len(stats['android_load']))
