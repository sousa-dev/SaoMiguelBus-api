import collections
from difflib import SequenceMatcher
from django.shortcuts import render
from django.utils import timezone
from SaoMiguelBus import settings
from numpy import full
from rest_framework.decorators import api_view
from rest_framework.response import Response
from app.models import Holiday, Stop, Route, Stat, ReturnRoute, LoadRoute, Trip, TripStop, Variables, Ad, Group, Info, Data as route_data
from app.serializers import DataSerializer, HolidaySerializer, StopSerializer, RouteSerializer, StatSerializer, ReturnRouteSerializer, LoadRouteSerializer, TripSerializer, TripStopSerializer, VariablesSerializer, AdSerializer, GroupSerializer, InfoSerializer
from django.views.decorators.http import require_GET, require_POST
from datetime import datetime, date, timedelta
from statistics import median
import requests
from django.http import JsonResponse
import pytz

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
        origin = request.GET.get('origin', '')
        destination = request.GET.get('destination', '')
        type_of_day = request.GET.get('day', '')
        start_time = request.GET.get('start', '')
        full = True if request.GET.get('full', '').lower() == 'true' else False

        return_routes = get_trip_v1_logic(origin, destination, type_of_day, start_time, full)
        return Response(return_routes) if return_routes is not None else Response(status=404)
    
def get_trip_v1_logic(origin, destination, type_of_day, start_time, full, prefix=False, sort=True):
    try:
        routes = Route.objects.all()
        routes = routes.exclude(disabled=True)

        if origin in ['Povoacão', 'Lomba do Loucão', 'Ponta Garca']:
            origin = origin.replace('c', 'ç')
        routes = routes.filter(stops__icontains=origin) if origin != '' else routes


        if destination in ['Povoacão', 'Lomba do Loucão', 'Ponta Garca']:
            destination = destination.replace('c', 'ç')

        if origin == '' or destination == '':
            return Response({'error': 'Origin and destination are required'})
        routes = routes.filter(stops__icontains=destination) if destination != '' else routes
        for route in routes:
            routes = routes.exclude(id=route.id) if str(route.stops).find(origin) > str(route.stops).find(destination) else routes
        if type_of_day != '':
            routes = routes.filter(type_of_day=type_of_day.upper())
        if sort:    
            if start_time != '':
                for route in routes:
                    route_start_time = route.stops.split(',')[0].split(':')[1].replace('{','').replace('\'','').strip()
                    try:
                        route_start_time_hour = int(route_start_time.split('h')[0])
                        route_start_time_minute = int(route_start_time.split('h')[1])
                    except:
                        route_start_time_hour = int(route_start_time.split(':')[0])
                        route_start_time_minute = int(route_start_time.split(':')[1])
                    routes = routes.exclude(id=route.id) if route_start_time_hour < int(start_time.split('h')[0]) or (route_start_time_hour == int(start_time.split('h')[0]) and route_start_time_minute < int(start_time.split('h')[1])) else routes
        if not full:
            #TODO: format route.stops to exclude stops outside the scope
            pass
        #TODO: get origin, destination, start and end time
        return_routes = [ReturnRoute(route.id, route.route if not prefix else f'C{route.route}', origin, destination, route.stops.split(':')[1].split(",")[0].replace('\'', '').strip(), route.stops.split(':')[-1].split(",")[0].replace('\'', '').replace('}', '').strip(), route.stops, route.type_of_day, route.information).__dict__ for route in routes]
        return return_routes
    except Exception as e:
        print(e)
        return None   
      
@api_view(['GET'])
@require_GET
def get_gmaps_v1(request):
    print('Getting Google Maps API')
    variable = Variables.objects.first()
    if not variable.maps:
        return JsonResponse({'error': 'Google Maps API is disabled'}, status=400)

    origin = request.GET.get('origin')
    destination = request.GET.get('destination')
    if not (origin and destination):
        return JsonResponse({'error': 'Missing required parameters'}, status=400)

    origin_stop = TripStop.objects.filter(name=origin).first() or Stop.objects.filter(name=origin).first()
    destination_stop = TripStop.objects.filter(name=destination).first() or Stop.objects.filter(name=destination).first()

    origin_query = f"{origin_stop.latitude},{origin_stop.longitude}" if origin_stop else origin
    destination_query = f"{destination_stop.latitude},{destination_stop.longitude}" if destination_stop else destination

    language_code = request.GET.get('languageCode', 'en')
    arrival_departure = request.GET.get('arrival_departure', 'departure')
    day = request.GET.get('day', '')
    start = request.GET.get('start', '')
    time = request.GET.get('time', "NA")
    platform = request.GET.get('platform', 'NA')
    version = request.GET.get('version', 'NA')
    debug = request.GET.get('debug', 'False').lower() == 'true'
    sessionToken = request.GET.get('sessionToken', 'NA')
    key = request.GET.get('key', 'NA')
    
    if key != settings.AUTH_KEY or int(version.split('.')[0]) < 5:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    if day != '':
        datetime_day = datetime.strptime(day, '%Y-%m-%d')
        if start != '':
            hour, minute = map(int, start.replace('h', ':').split(':'))
            datetime_day = datetime_day.replace(hour=hour, minute=minute)
        else:
            datetime_day = datetime_day.replace(hour=0, minute=0, second=0, microsecond=0)
        time = int(datetime_day.timestamp())
    elif time == "NA":
        azores_timezone = pytz.timezone('Atlantic/Azores')
        time = int(datetime.now(azores_timezone).timestamp())

    maps_url = (
        f"https://maps.googleapis.com/maps/api/directions/json?"
        f"origin={origin_query}&destination={destination_query}&mode=transit"
        f"&key={settings.GOOGLE_MAPS_API_KEY}&language={language_code}&alternatives=true"
        f"&{'arrival_time' if arrival_departure == 'arrival' else 'departure_time'}={time}"
    )

    try:
        response = requests.get(maps_url)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'OK':
                try:
                    routeData = route_data(
                        data=data,
                        origin=str(origin),
                        destination=str(destination),
                        language_code=str(language_code),
                        time=str(time),
                        platform=str(platform),
                    )
                    routeData.save()
                    get_data_v1(request._request, routeData.id)
                except Exception as e:
                    print(e)
            return JsonResponse(data)
        else:
            return JsonResponse({'warning': 'NA'}, status=response.status_code)
    except Exception as e:
        return JsonResponse({'warning': 'NA'}, status=500)

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
            start_time = request.GET.get('start_time', datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() - timedelta(days=7).total_seconds())
            end_time = request.GET.get('end_time', datetime.now().replace(hour=23, minute=59, second=59, microsecond=0).timestamp() - timedelta(days=1).total_seconds())
            start_time = timezone.make_aware(datetime.fromtimestamp(int(start_time)), timezone.get_current_timezone())
            end_time = timezone.make_aware(datetime.fromtimestamp(int(end_time)), timezone.get_current_timezone())
            stats = stats.filter(timestamp__range=(start_time, end_time))
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
def get_group_stats_v1(request):
    if request.method == "GET":
        try:
            response = {}
            detailed_impressions = []            
            platform = request.GET.get('platform', 'all')
            language = request.GET.get('language', 'all')
            groups = request.GET.get('group', '')
            if groups == '':
                return Response({'error': 'Group is required'})
            start_time = request.GET.get('start_time', datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() - timedelta(days=7).total_seconds())
            end_time = request.GET.get('end_time', datetime.now().replace(hour=23, minute=59, second=59, microsecond=0).timestamp() - timedelta(days=1).total_seconds())
            start_time = timezone.make_aware(datetime.fromtimestamp(int(start_time)), timezone.get_current_timezone())
            end_time = timezone.make_aware(datetime.fromtimestamp(int(end_time)), timezone.get_current_timezone())

            response['start_time'] = start_time
            response['end_time'] = end_time

            stats = Stat.objects.all()
            stats = stats.filter(timestamp__range=(start_time, end_time))
            stats = stats.filter(language=language) if language != 'all' else stats
            if platform != 'all':
                if platform.find(',') != -1:
                    #remove stats that are not from the platform.split(',')
                    for stat in stats:
                        if stat.platform not in platform.split(','):
                            stats = stats.exclude(id=stat.id)
                else:
                    stats = stats.filter(platform=platform)

            search_stops = []
            home_page_impressions = 0
            #home_page_detailed_impressions = []
            for group in groups.split(','):
                if group == "home":
                    # Get the median value of the home page impressions
                    daily_loads = [
                        len(stats.filter(request='android_load', timestamp__range=(start_time + timedelta(days=i), start_time + timedelta(days=i+1))))
                        for i in range((end_time - start_time).days)
                    ]
                    median_loads = median(daily_loads)                
                    home_page_impressions = int(median_loads * (end_time - start_time).days)                  
                    continue

                for stop in Group.objects.get(name=group).stops.split(','):
                        search_stops.append(stop)

            response['search_stops'] = search_stops

            # Find stats that have at least one of the stops at destination     
            # TODO: Fix this part           
            for stat in stats:
                if stat.destination == 'NA':
                    stats = stats.exclude(id=stat.id)
                    continue
                if stat.destination in search_stops or get_most_similar_stop(stat.destination) in search_stops:
                    continue
                else:
                    stats = stats.exclude(id=stat.id)

            response['total_impressions'] = len(stats) + home_page_impressions
            response['home_page_impressions'] = home_page_impressions
            response['search_page_impressions'] = len(stats.filter(request='get_route'))
            response['find_page_impressions'] = len(stats.filter(request='find_routes'))
            response['directions_page_impressions'] = len(stats.filter(request='get_directions'))

            for stat in stats:
                detailed_impressions.append(get_detailed_impression(stat))
                    
            response['detailed_impressions'] = detailed_impressions + [f"{home_page_impressions} pessoas viram o anúncio ao entrar na app"]

            return Response(response)
        
        except Exception as e:
            print(e)
            return Response(status=404)

@api_view(['GET'])
@require_GET
def get_holidays_v1(request):
    if request.method == 'GET':
        holidays = Holiday.objects.all()
        serializer = HolidaySerializer(holidays, many=True)
        return Response(serializer.data)


def get_detailed_impression(stat):
    impression = {}
    # Get a detailed impression from stat
    type_of_request = stat.request
    origin = stat.origin
    destination = stat.destination
    type_of_day = stat.type_of_day
    time = stat.time
    platform = stat.platform
    language = stat.language
    timestamp = stat.timestamp
    # only keep the values != 'NA'
    if type_of_request != 'NA':
        if type_of_request == "android_load":
            impression['type_of_request'] = "Abriu a Home Page"
        elif type_of_request == "get_route":
            impression['type_of_request'] = "Pesquisou uma Rota"
        elif type_of_request == "find_routes":
            impression['type_of_request'] = "Pesquisou uma Rota na página 'Find'"
        elif type_of_request == "get_directions":
            impression['type_of_request'] = "Pediu direções"
        else:
            impression['type_of_request'] = type_of_request
    
    if origin != 'NA':
        impression['origin'] = origin
    if destination != 'NA':
        impression['destination'] = destination
    if type_of_day != 'NA':
        if type_of_day == "WEEKDAY":
            impression['type_of_day'] = "Dia da Semana"
        elif type_of_day == "SATURDAY":
            impression['type_of_day'] = "Sábado"
        elif type_of_day == "SUNDAY":
            impression['type_of_day'] = "Domingo ou Feriado"
        else:
            impression['type_of_day'] = type_of_day
    if time != 'NA':
        impression['time'] = time
    if platform != 'NA':
        impression['platform'] = platform
    if language != 'NA':
        impression['language'] = language
    if timestamp != 'NA':
        impression['timestamp'] = timestamp.strftime('%d-%m-%Y %H:%M')
    return impression
    

@api_view(['GET'])
@require_GET
def get_ad_v1(request):
    ads = Ad.objects.all()
    if request.method == 'GET':
        ad_time = request.GET.get('now', timezone.now().timestamp())
        advertise_on = request.GET.get('on', 'all').lower()
        platform = request.GET.get('platform', 'all')
        datetime_ad_time = timezone.make_aware(datetime.fromtimestamp(float(ad_time)), timezone.get_default_timezone())
        ads = ads.filter(status='active')
        ads = ads.filter(platform=platform) if platform != 'all' else ads
        ads = ads.filter(start__lte=datetime_ad_time, end__gte=datetime_ad_time)

        # Verify if there is multiple ad campaigns for the same advertise_on
        verify = request.GET.get('verify', False)
        if verify:
            for ad in ads:
                groups = ad.advertise_on.split(',')
                for ad_ in ads:
                    if ad.id != ad_.id:
                        groups_ = ad_.advertise_on.split(',')
                        for group in groups:
                            if group in groups_:
                                return Response({'error': 'There are two active ads for the same campaign',
                                                 'ad-1': AdSerializer(ad).data,
                                                 'ad-2': AdSerializer(ad_).data})

        if advertise_on in ["home", "all"]:
            ads = ads.filter(advertise_on__icontains=advertise_on) if advertise_on != 'all' else ads
        else:
            stops = advertise_on.split('->') 
            origin = stops[0].strip()
            destination = stops[-1].strip()

            destination_ads = ads.filter(advertise_on__icontains=get_advertise_on_value(destination))
            #Priority for destination ads
            if destination_ads.count() > 0:
                ads = destination_ads
            else:
                ads = ads.filter(advertise_on__icontains=get_advertise_on_value(origin))
                
        # If multiple ads are found, choose a random one
        if ads.count() > 1:
            print('Multiple ads found for time: ' + str(ad_time))
            print('Choosing a random ad from the list:' )
            for ad in ads:
                print(ad)
            ads = ads.order_by('?')[:1]

        # Return a default ad if no ads are found
        if ads.count() == 0:
            ads = Ad.objects.filter(platform=platform)
            ads = ads.filter(status='default')
            #Choose a random default ad
            ads = ads.order_by('?')[:1]
            
        if ads.count() == 0:
            print('No ads found for time: ' + str(ad_time))
            return Response(status=404)
        
        ad = ads[0]
        serializer = AdSerializer(ad)
        ad.seen += 1 
        ad.save()
        return Response(serializer.data)
    
#Get advertise on value based on the stop
def get_advertise_on_value(stop):
    #Find the group which the stop belongs to
    group = Group.objects.filter(stops__icontains=stop)
    if group.count() > 0:
        group = group[0]
        return group.name
    most_similar_stop = get_most_similar_stop(stop)
    group = Group.objects.filter(stops__icontains=most_similar_stop)
    if group.count() > 0:
        group = group[0]
        return group.name
    
    return "not found"

#Get the most similar stop
def get_most_similar_stop(stop):
    stops = Stop.objects.all()
    most_similar_stop = stop
    most_similar_stop_score = 0
    for stop_entity in stops:
        score = SequenceMatcher(
            lambda x: x in ['do', 'da', 'das', 'dos', 'de', ' '], 
            stop_entity.name.lower(), stop.lower()).ratio()
        if score > most_similar_stop_score:
            most_similar_stop = stop_entity.name
            most_similar_stop_score = score
    return most_similar_stop


#Increase ad clicked counter
@api_view(['POST'])
@require_POST
def click_ad_v1(request):
    if request.method == 'POST':
        try:
            ad_id = request.GET.get('id', '')
            if ad_id == '':
                return Response(status=404)
            ad = Ad.objects.get(id=ad_id)
            ad.clicked += 1
            ad.save()
            return Response({'status': 'ok'})
        except Exception as e:
            print(e)
            return Response(status=404)

@api_view(['GET'])
@require_GET
def get_all_groups_v1(request):
    if request.method == 'GET':
        if request.GET.get('verify', False):
            all_stops_obj = Stop.objects.all()
            all_stops_names = [stop.name for stop in all_stops_obj]
            all_groups = Group.objects.all()
            all_groups_stops = [group.stops for group in all_groups]
            all_groups_stops = [stop for stops in all_groups_stops for stop in stops.split(',')]
            # check for duplicates on all_groups_stops and if all_stops_names are in all_groups_stops
            if len(all_groups_stops) != len(set(all_groups_stops)) or not set(all_stops_names).issubset(set(all_groups_stops)):
                #Get missing stops
                missing_stops = set(all_stops_names) - set(all_groups_stops)
                #get duplicated stops
                duplicated_stops = [item for item, count in collections.Counter(all_groups_stops).items() if count > 1]

                return Response({'status': 'error', 'message': 'There is a problem with the defined groups', 
                                 'Missing stops': str(missing_stops), 
                                 'Duplicated stops':  str(duplicated_stops)})
        try:
            groups = Group.objects.all()
            serializer = GroupSerializer(groups, many=True)
            for group in serializer.data:
                group['name'] = group['name'].title()
                group['stops'] = group['stops'].split(',')
            return Response(serializer.data)
        except Exception as e:
            print(e)
            return Response(status=404)

@api_view(['GET'])
@require_GET
def get_infos_v1(request):
    if request.method == 'GET':
        try:
            current_time = datetime.now()
            all_infos = Info.objects.all()
            active_infos = all_infos.filter(start__lte=current_time, end__gte=current_time)
            serializer = InfoSerializer(active_infos, many=True)
            return Response(serializer.data)
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
                holidays = Holiday.objects.all()
                routes = []
                try:
                    variable = Variables.objects.all().first().__dict__
                    routes = [{'version': variable['version'], 'maps': variable['maps'], 'holidays': HolidaySerializer(holidays, many=True).data}]
                except Exception as e:
                    print(e)
                for route in all_routes:
                    stops = route.stops.replace('\'', '').replace('{', '').replace('}', '').split(',')
                    all_stops = [stop.split(':')[0].strip() for stop in stops]
                    all_times = [stop.split(':')[1].strip() for stop in stops]
                    routes.append(LoadRoute(route.id, route.route, all_stops, all_times, route.type_of_day, route.information).__dict__)
                return Response(routes)
            except Exception as e:
                print(e)
                return Response(status=404)
            
@api_view(['POST'])
@require_POST
def set_info_v1(request):
    if request.method == 'POST':
        try:
            info = request.GET.get('info', 'None')
            stop = request.GET.get('stop', '')
            clean = False if request.GET.get('clean', "False") == "False" else True
            if stop == '':
                return Response(status=404)
            updated = 0
            routes_updated = []
            if clean:
                for route in Route.objects.all():
                    print(route.information, info)
                    if stop in route.stops and route.information == info and route.information != 'None':
                        route.information = 'None'
                        route.save()
                        updated += 1
                        routes_updated.append(route.route)
            else:
                for route in Route.objects.all():
                    if stop in route.stops and route.information == "None":
                        route.information = info
                        route.save()
                        updated += 1
                        routes_updated.append(route.route)
            return Response({'status': 'ok', 'updated': updated, 'routes_updated': routes_updated})
        except Exception as e:
            print(e)
            return Response(status=404)
        
@api_view(['GET'])
@require_GET
def get_active_infos_v1(request):
    if request.method == 'GET':
        try:
            active_infos = []
            for route in Route.objects.all():
                if route.information != 'None':
                    active_infos.append((f"{route.route} -> {route.stops}", route.information))
            return Response(active_infos)
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
    start_time = request.GET.get('start_time', datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    end_time = request.GET.get('end_time', datetime.now().timestamp())
    start_time = datetime.fromtimestamp(int(start_time))
    end_time = datetime.fromtimestamp(int(end_time))

    # format to     
    start_time = start_time.strftime('%Y-%m-%d %H:%M:%S')
    end_time = end_time.strftime('%Y-%m-%d %H:%M:%S')

    ALL = Stat.objects.all()

    latest_n = int(request.GET.get('latest', '10'))
    most_searched_n = int(request.GET.get('most_searched', '10'))

    android_loads, android_loads_labels, android_loads_no = get_android_loads()

    latests_activity = [stat for stat in ALL.order_by('-timestamp')[:latest_n]]

    android_loads_today = android_loads.filter(timestamp__range=(start_time, end_time)) # filter objects created today
    get_routes_today = Stat.objects.filter(request="get_route").filter(timestamp__range=(start_time, end_time)) # filter objects created today
    find_routes_today = Stat.objects.filter(request="find_routes").filter(timestamp__range=(start_time, end_time)) # filter objects created today
    get_directions_today = Stat.objects.filter(request="get_directions").filter(timestamp__range=(start_time, end_time)) # filter objects created today


    #TODO: Get stops names conversions to portuguese
    '''Get Most Searched Destinations'''
    most_searched_destinations_labels, most_searched_destinations_values = get_most_searched("destination", ALL.filter(request='get_route').exclude(destination='null') | ALL.filter(request='get_directions').exclude(destination='null') | ALL.filter(request='find_routes').exclude(destination='null'), most_searched_n)
    most_searched_origins_labels, most_searched_origins_values = get_most_searched("origin", ALL.filter(request='get_route').exclude(origin='null'), most_searched_n)
    most_searched_routes_labels, most_searched_routes_values = get_most_searched("route", ALL.filter(request='get_route').exclude(origin='null').exclude(destination='null'), most_searched_n)
    
    #TODO: get route android vs web

    android_loads_timestamp_keys, android_loads_timestamp_values = get_android_loads_timestamp(android_loads, start_time, end_time)

    context = {
        'labels': android_loads_labels, 'no': android_loads_no, 'label': 'Android App Loads (%)',
        'latests_activity': latests_activity, 
        'android_loads_timestamp_keys': android_loads_timestamp_keys, 'android_loads_timestamp_values': android_loads_timestamp_values,
        'android_loads_today_count': android_loads_today.count(), 'get_routes_today': get_routes_today.count(), 'find_routes_today': find_routes_today.count(), 'get_directions_today': get_directions_today.count(),
        'most_searched_destinations_labels': most_searched_destinations_labels, 'most_searched_destinations_values': most_searched_destinations_values,
        'most_searched_origins_labels': most_searched_origins_labels, 'most_searched_origins_values': most_searched_origins_values,
        'most_searched_routes_labels': most_searched_routes_labels, 'most_searched_routes_values': most_searched_routes_values,
        'start_time': start_time,
        'end_time': end_time,
        }
    
    return render(request, 'app/templates/statistics.html', context)

def get_android_loads_timestamp(android_loads, start_time, end_time):
    android_loads = android_loads.filter(timestamp__range=(start_time, end_time))
    android_loads_timestamp = {}
    for android_load in android_loads:
        hour = android_load.timestamp.strftime('%Y-%m-%d %H:00:00')
        if hour in android_loads_timestamp:
            android_loads_timestamp[hour] += 1
        else:
            android_loads_timestamp[hour] = 1
    return android_loads_timestamp.keys(), android_loads_timestamp.values()

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

import math

def is_within_50km_radius(lat, lon):
    def haversine(lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        R = 6371.0
        distance = R * c
        
        return distance
    
    center_lat, center_lon = 37.782213, -25.499806
    radius = 50
    
    distance = haversine(center_lat, center_lon, lat, lon)
    
    return distance <= radius


def data_to_route(data):
    bus_stop_locations = {}
    bus_schedules = []  
    for key in data:
        if key == "routes":
            for route in data[key]:
                bus_schedule = {}

                for leg in route["legs"]:
                    departure_timestamp = leg["departure_time"]["value"]
                    trip_date = datetime.utcfromtimestamp(departure_timestamp).strftime('%Y-%m-%d')
    
                    bus_numbers = []
                    for step in leg["steps"]:
                        if step["travel_mode"] == "TRANSIT":
                            transit_details = step["transit_details"]
                            
                            departure_time = transit_details["departure_time"]["text"]
                            arrival_time = transit_details["arrival_time"]["text"]
                            
                            if 'AM' in departure_time or 'PM' in departure_time:
                                departure_time = datetime.strptime(departure_time, '%I:%M %p').strftime('%Hh%M')
                                arrival_time = datetime.strptime(arrival_time, '%I:%M %p').strftime('%Hh%M')
                            else:
                                departure_time = datetime.strptime(departure_time, '%H:%M').strftime('%Hh%M')
                                arrival_time = datetime.strptime(arrival_time, '%H:%M').strftime('%Hh%M')

                            bus_schedule[transit_details["departure_stop"]["name"]] = departure_time
                            bus_schedule[transit_details["arrival_stop"]["name"]] = arrival_time
                            bus_numbers.append(transit_details["line"]["short_name"].replace('C', ''))
                            departure_stop = transit_details["departure_stop"]["name"]
                            departure_location = (
                                transit_details["departure_stop"]["location"]["lat"],
                                transit_details["departure_stop"]["location"]["lng"]
                            )
                            arrival_stop = transit_details["arrival_stop"]["name"]
                            arrival_location = (
                                transit_details["arrival_stop"]["location"]["lat"],
                                transit_details["arrival_stop"]["location"]["lng"]
                            )
                            
                            if not is_within_50km_radius(departure_location[0], departure_location[1]) or not is_within_50km_radius(arrival_location[0], arrival_location[1]):
                                continue
                            
                            bus_stop_locations[departure_stop] = departure_location
                            bus_stop_locations[arrival_stop] = arrival_location
                bus_schedules.append({'bus': " / ".join(bus_numbers), 'stops': bus_schedule, 'day': trip_date})
    return bus_schedules, bus_stop_locations

# Get all Datas
@api_view(['GET'])
@require_GET
def get_data_v1(request, data_id):
    if request.method == 'GET':
        data = route_data.objects.get(id=data_id)
        # From unix timestamp to datetime in azores timestamp
        trips, stops = data_to_route(data.data)
        for stop in stops:
            # Check if the stop is in the database
            stop_obj = TripStop.objects.filter(name=stop)
            if stop_obj.count() == 0:
                TripStop(name=stop, latitude=stops[stop][0], longitude=stops[stop][1]).save()        
                
        for trip in trips:
            bus_number = trip['bus']
            bus_stops = trip['stops']
            trip_day = trip['day']
            trip_day = datetime.strptime(trip_day, '%Y-%m-%d').strftime('%Y-%m-%d')
            type_of_day = 'WEEKDAY'
            
            # Check if the day is an holiday
            holiday = Holiday.objects.filter(date=trip_day)
            if holiday.count() > 0:
                type_of_day = 'SUNDAY'
            # Check if the day is a saturday
            elif datetime.strptime(trip_day, '%Y-%m-%d').weekday() == 5:
                type_of_day = 'SATURDAY'
                
            trips = Trip.objects.filter(route=bus_number, stops=bus_stops, type_of_day=type_of_day)
            if trips.count() == 0:
                Trip(route=bus_number, stops=bus_stops, type_of_day=type_of_day).save()
            else:
                trip = trips[0]
                trip.added = timezone.now()

        dataSerialized = DataSerializer(data, many=True)
        tripsSerialized = TripSerializer(trips, many=True)
        stopsSerialized = TripStopSerializer(stops, many=True)
        return JsonResponse({'data': str(dataSerialized), 'trips': tripsSerialized.data, 'stops': stopsSerialized.data})
        
