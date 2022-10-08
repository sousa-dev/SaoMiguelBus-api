from django.shortcuts import render
from numpy import full
from rest_framework.decorators import api_view
from rest_framework.response import Response
from app.models import Stop, Route, Stat, ReturnRoute, LoadRoute
from app.serializers import StopSerializer, RouteSerializer, StatSerializer, ReturnRouteSerializer, LoadRouteSerializer
from django.views.decorators.http import require_GET, require_POST
from datetime import datetime, date
import json


# Create your views here.

#Get All Stops
@api_view(['GET'])
@require_GET
def get_all_stops_v1(request):
    if request.method == 'GET':
        all_stops = Stop.objects.all()
        serializer = StopSerializer(all_stops, many=True)
        return Response(serializer.data)

#Get All Routes
@api_view(['GET'])
@require_GET
def get_all_routes_v1(request):
    if request.method == 'GET':
        all_routes = Route.objects.all()
        serializer = RouteSerializer(all_routes, many=True)
        return Response(serializer.data)

@api_view(['GET'])
@require_GET
def get_trip_v1(request):
    if request.method == 'GET':
        try:
            routes = Route.objects.all()
            routes = routes.exclude(disabled=True)
            origin = request.GET.get('origin', '')
            routes = routes.filter(stops__icontains=origin) if origin != '' else routes
            destination = request.GET.get('destination', '')
            if origin == '' or destination == '':
                return Response({'error': 'Origin and destination are required'})
            routes = routes.filter(stops__icontains=destination) if destination != '' else routes
            for route in routes:
                routes = routes.exclude(id=route.id) if str(route.stops).find(origin) > str(route.stops).find(destination) else routes
            type_of_day = request.GET.get('day', '')
            if type_of_day != '':
                routes = routes.filter(type_of_day=type_of_day.upper())
            start_time = request.GET.get('start', '')
            if start_time != '':
                for route in routes:
                    route_start_time = route.stops.split(',')[0].split(':')[1].replace('{','').replace('\'','').strip()
                    route_start_time_hour = int(route_start_time.split('h')[0])
                    route_start_time_minute = int(route_start_time.split('h')[1])
                    routes = routes.exclude(id=route.id) if route_start_time_hour < int(start_time.split('h')[0]) or (route_start_time_hour == int(start_time.split('h')[0]) and route_start_time_minute < int(start_time.split('h')[1])) else routes
            full = True if request.GET.get('full', '').lower() == 'true' else False
            if not full:
                #TODO: format route.stops to exclude stops outside the scope
                pass
            #TODO: get origin, destination, start and end time
            return_routes = [ReturnRoute(route.id, route.route, origin, destination, route.stops.split(':')[1].split(",")[0].replace('\'', '').strip(), route.stops.split(':')[-1].split(",")[0].replace('\'', '').replace('}', '').strip(), route.stops, route.type_of_day, route.information).__dict__ for route in routes]
            return Response(return_routes)
        except Exception as e:
            print(e)
            return Response(status=404)

@api_view(['GET'])
@require_GET
def get_route_v1(request, route_id):
    if request.method == 'GET':
        try:
            routes = Route.objects.all()
            routes = routes.filter(route__icontains=route_id)
            serializer = RouteSerializer(routes, many=True)
            #TODO: Return a new formatted entity
            return Response(serializer.data)
        except Exception as e:
            print(e)
            return Response(status=404)

@api_view(['GET'])
@require_GET
def get_stats_v1(request):
    if request.method == 'GET':
        try:
            stats = Stat.objects.all()
            serializer = StatSerializer(stats, many=True)
            return Response(serializer.data)
        except Exception as e:
            print(e)
            return Response(status=404)

@api_view(['POST'])
@require_POST
def add_stat_v1(request):
    if request.method == 'POST':
        try:
            stat = Stat()
            stat.request = request.GET.get('request', 'NA')
            stat.origin = request.GET.get('origin', '')
            stat.destination = request.GET.get('destination', '')
            stat.type_of_day = request.GET.get('day', 'NA')
            stat.time = request.GET.get('time', 'NA')
            stat.platform = request.GET.get('platform', 'NA')
            stat.language = request.GET.get('language', 'NA')
            #stat.timestamp = datetime.now()
            stat.save()
            return Response({'status': 'ok'})
        except Exception as e:
            print(e)
            return Response(status=404)

@api_view(['GET'])
@require_GET
def get_android_load_v1(request):
        if request.method == 'GET':
            try:
                all_routes = Route.objects.all()
                all_routes = all_routes.exclude(disabled=True)
                routes = []
                for route in all_routes:
                    stops = route.stops.replace('\'', '').replace('{', '').replace('}', '').split(',')
                    all_stops = [stop.split(':')[0].strip() for stop in stops]
                    all_times = [stop.split(':')[1].strip() for stop in stops]
                    routes.append(LoadRoute(route.id, route.route, all_stops, all_times, route.type_of_day, route.information).__dict__)
                return Response(routes)
            except Exception as e:
                print(e)
                return Response(status=404)

@api_view(['GET'])
@require_GET
def get_android_load_v2(request):
        if request.method == 'GET':
            try:
                all_routes = Route.objects.all()
                all_routes = all_routes.exclude(disabled=True)
                loads = []
                full_routes = {}
                for route in all_routes:
                    if route.route in full_routes:
                        full_routes[route.route].append(route)
                    else:
                        full_routes[route.route] = [route]
                print(full_routes)
                for route_id in full_routes:
                    print("\n\n\n"+route_id)
                    for route in full_routes[route_id]:
                        print(route)
                        print(route.start)
                        print(route.end)
                '''
                    route_id = route.route
                    unique_id = route.id
                    type_of_day = route.type_of_day
                    information = route.information
                    print(route_id, unique_id, type_of_day, information)
                    #TODO: Get formatted route to load on Sao Miguel Bus Android app
                    stops = route.stops.replace('\'', '').replace('{', '').replace('}', '').split(',')
                    stop_times = [(stop.split(':')[0].strip(), stop.split(':')[1].strip()) for stop in stops]
                    print(stop_times)
                    
                    if route.route in full_routes:
                        full_routes[route.route].append(LoadRoute(route.id, route.route, stop_name, stop_time, route.type_of_day, route.information).__dict__)
                    else:
                        full_routes[route.route] = [LoadRoute(route.id, route.route, stop_name, stop_time, route.type_of_day, route.information).__dict__]
                '''
                #print(full_routes)
                return Response("pass")
            except Exception as e:
                print(e)
                return Response(status=404)

@api_view(['GET'])
@require_GET
def index (request):
    return render(request, 'app/templates/index.html')

@api_view(['GET'])
@require_GET
def stats (request):
    '''
    #TODO: protect this code with an hash
    secret_hash = "4357870571671307646"
    secret = request.GET.get('secret', '')
    if hash(secret) == secret_hash:
        return render(request, 'app/templates/statistics.html')
    else:
        return render(request, 'app/templates/index.html')
    '''
    ALL = Stat.objects.all()

    latest_n = int(request.GET.get('latest', '10'))
    most_searched_n = int(request.GET.get('most_searched', '10'))

    android_loads, android_loads_labels, android_loads_no = get_android_loads()

    latests_activity = [stat for stat in ALL.order_by('-timestamp')[:latest_n]]

    android_loads_today = android_loads.filter(timestamp__range=(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0), datetime.now())) # filter objects created today

    #TODO: Get stops names conversions to portuguese
    '''Get Most Searched Destinations'''
    most_searched_destinations_labels, most_searched_destinations_values = get_most_searched("destination", ALL.filter(request='get_route').exclude(destination='null') | ALL.filter(request='get_directions').exclude(destination='null') | ALL.filter(request='find_routes').exclude(destination='null'), most_searched_n)
    most_searched_origins_labels, most_searched_origins_values = get_most_searched("origin", ALL.filter(request='get_route').exclude(origin='null'), most_searched_n)
    most_searched_routes_labels, most_searched_routes_values = get_most_searched("route", ALL.filter(request='get_route').exclude(origin='null').exclude(destination='null'), most_searched_n)
    
    #TODO: get route android vs web

    context = {
        'labels': android_loads_labels, 'no': android_loads_no, 'label': 'Android App Loads (%)',
        'latests_activity': latests_activity,
        'android_loads_today': android_loads_today.count(),
        'most_searched_destinations_labels': most_searched_destinations_labels, 'most_searched_destinations_values': most_searched_destinations_values,
        'most_searched_origins_labels': most_searched_origins_labels, 'most_searched_origins_values': most_searched_origins_values,
        'most_searched_routes_labels': most_searched_routes_labels, 'most_searched_routes_values': most_searched_routes_values,
        }
    
    return render(request, 'app/templates/statistics.html', context)

def get_android_loads():
    android_loads = Stat.objects.filter(request='android_load')

    android_loads_en = int(android_loads.filter(language='en').count())*100/android_loads.count()
    android_loads_pt = int(android_loads.filter(language='pt').count())*100/android_loads.count()
    android_loads_esp = int(android_loads.filter(language='es').count())*100/android_loads.count()
    android_loads_fr = int(android_loads.filter(language='fr').count())*100/android_loads.count()
    android_loads_ger = int(android_loads.filter(language='de').count())*100/android_loads.count()
    android_loads_other = 100.0 - (android_loads_pt + android_loads_en + android_loads_fr + android_loads_ger + android_loads_esp)

    android_loads_labels = ['Portuguese', 'English', "Spanish", 'French', 'German', 'Other']
    android_loads_no = [android_loads_pt, android_loads_en,  android_loads_esp, android_loads_fr, android_loads_ger, android_loads_other]

    return android_loads, android_loads_labels, android_loads_no

def get_most_searched(n, stats, most_searched_n):
    most_searched = {}
    for stat in stats: 
        key = get_dict_key(n, stat)
        if key in most_searched:
            most_searched[key] += 1
        else:
            most_searched[key] = 1

    stops = [origin for origin in most_searched.keys()]

    most_searched_labels = sorted(stops, key=lambda x: most_searched[x], reverse=True)[:most_searched_n]
    most_searched_values = [most_searched[destination] for destination in most_searched_labels]

    return most_searched_labels, most_searched_values

def get_dict_key(n, stat):
    if n == 'destination':
        return stat.destination
    elif n == 'origin':
        return stat.origin
    elif n == 'route':
        return f"{stat.origin} -> {stat.destination}"



