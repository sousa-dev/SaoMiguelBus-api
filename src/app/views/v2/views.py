import json
import logging
from django.utils import timezone
import requests
from SaoMiguelBus import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from app.models import Holiday, LoadRoute, Route, Stop, TripStop, ReturnRoute, Trip, Variables
from app.serializers import HolidaySerializer, StopSerializer, TripSerializer
from django.views.decorators.http import require_GET
import django.db.models as models
from datetime import datetime, timedelta
from django.http import JsonResponse

from app.utils.day_utils import get_type_of_day
from app.utils.str_utils import clean_string
from app.views.v1.views import get_trip_v1_logic

logger = logging.getLogger(__name__)

@api_view(['GET'])
@require_GET
def get_all_stops_v2(request):
    logger.info("Received GET request for get_all_stops_v2")
    if request.method == 'GET':
        try:
            #all_trip_stops = TripStop.objects.all()
            all_normal_stops = Stop.objects.all()  # Get normal stops
            #combined_stops = list(all_trip_stops) + list(all_normal_stops)  # Combine both trip stops and normal stops
            #serializer = StopSerializer(all_normal_stops, many=True)
            unique_names = set()
            cleaned_stops = []
            for stop in all_normal_stops:
                name = stop.name.split(' - ')[0]
                if name not in unique_names:
                    unique_names.add(name)
                    cleaned_stops.append({
                        "id": stop.id,
                        "name": name,
                        "latitude": stop.latitude,
                        "longitude": stop.longitude
                    })
            logger.debug(f"Serialized {len(cleaned_stops)} stops")
            return Response(StopSerializer(all_normal_stops, many=True).data + cleaned_stops)
        except Exception as e:
            logger.exception("Error occurred in get_all_stops_v2")
            return Response({'error': 'Internal Server Error'}, status=500)

@api_view(['GET'])
@require_GET
def get_trip_v2(request):
    logger.info("Received GET request for get_trip_v2")
    if request.method == 'GET':
        if request.GET.get('all', False):
            try:
                trips = Trip.objects.all()
                serializer = TripSerializer(trips, many=True)
                logger.debug(f"Serialized {len(trips)} trips")
                return JsonResponse(serializer.data, safe=False)
            except Exception as e:
                logger.exception("Error retrieving all trips")
                return Response({'error': 'Internal Server Error'}, status=500)
        
        origin = request.GET.get('origin', '')
        destination = request.GET.get('destination', '')
        date_day = request.GET.get('day', '')
        start_time = request.GET.get('start', '00:00')
        full_ = request.GET.get('full', '').lower() == 'true'

        logger.debug(f"Parameters received - Origin: {origin}, Destination: {destination}, Day: {date_day}, Start Time: {start_time}, Full: {full_}")

        try:
            day_date = datetime.strptime(date_day, '%Y-%m-%d')
            day = get_type_of_day(day_date, Holiday.objects.filter(date=day_date).exists())
            logger.debug(f"Determined type_of_day: {day}")
        except Exception as e:
            logger.warning(f"Failed to parse date_day '{date_day}', using upper case: {date_day.upper()}")
            day = date_day.upper()

        absolute_url = request.build_absolute_uri('/')
        mapsURL =  f"{absolute_url}api/v1/gmaps?origin={origin}&destination={destination}&day={date_day}&start={start_time}&key={settings.AUTH_KEY}&platform=web&version=5"
        logger.debug(f"Maps URL constructed: {mapsURL}")

        origin_cleaned = clean_string(origin)
        destination_cleaned = clean_string(destination)

        def fetch_and_process_routes():
            logger.info("Fetching and processing routes")
            try:
                # Delete routes older than 1 month
                one_month_ago = timezone.now() - timedelta(days=30)
                deleted_count, _ = Trip.objects.filter(added__lte=one_month_ago).delete()
                logger.debug(f"Deleted {deleted_count} routes older than one month")

                if not origin_cleaned or not destination_cleaned:
                    logger.warning("Origin and destination are required but not provided")
                    return {'error': 'Origin and destination are required'}
                
                routes = Trip.objects.filter(disabled=False).filter(
                    cleaned_stops__contains=origin_cleaned).filter(
                        cleaned_stops__contains=destination_cleaned
                )
                
                logger.debug(f"Found {routes.count()} routes after filtering")

                day_date = datetime.strptime(date_day, '%Y-%m-%d')
                type_of_day = get_type_of_day(day_date, Holiday.objects.filter(date=day_date).exists())
                if type_of_day:
                    routes = routes.filter(type_of_day=type_of_day.upper())
                    logger.debug(f"Filtered routes by type_of_day: {type_of_day.upper()}")

                if not full_:
                    # TODO: format route.stops to exclude stops outside the scope
                    logger.debug("Full parameter is False; excluding stops outside the scope")
                    pass
                return routes
            except Exception as e:
                logger.exception("Error in fetch_and_process_routes")
                return None

        try:
            routes = fetch_and_process_routes()
            if routes is None:
                logger.error("Routes fetching and processing returned None")
                return Response(status=404)

            if not routes.exists():
                try:
                    variable = Variables.objects.filter(populate_maps_routes=True).exists()
                    if variable:
                        logger.info("populate_maps_routes is True, fetching maps routes")
                        response = requests.get(mapsURL)
                        logger.debug(f"Maps API response status: {response.status_code}")
                        routes = fetch_and_process_routes()
                        if not routes:
                            logger.warning("No routes found after fetching maps routes")
                    else:
                        logger.info("populate_maps_routes is False. Skipping fetching maps routes.")
                except Variables.DoesNotExist:
                    logger.warning("Variables.objects.get(populate_maps_routes=True) did not find any matching records")
                    logger.info("populate_maps_routes is False. Skipping fetching maps routes.")

            old_routes = get_trip_v1_logic(origin_cleaned, destination_cleaned, day, start_time.replace(':', 'h'), full_, prefix=True) or []
            logger.debug(f"Retrieved {len(old_routes)} old routes from get_trip_v1_logic")

            # Prepare the start time for comparison
            try:
                if start_time == '':
                    input_hour, input_minute = 0, 0
                else:
                    input_hour, input_minute = map(int, start_time.replace('h', ':').split(':'))
                logger.debug(f"Input time - Hour: {input_hour}, Minute: {input_minute}")
            except ValueError:
                logger.exception(f"Invalid start time format: {start_time}")
                return Response({'error': 'Invalid start time format'}, status=400)

            # Process routes in a more efficient manner
            return_routes = old_routes
            for route in []:#routes:
                stops = route.stops
                stops_tuple = [(stop, time) for stop, time in json.loads(str(stops).replace("'", '"')).items()]
                origin_idx = next((index for index, (stop, _) in enumerate(stops_tuple) if origin_cleaned in clean_string(stop)), None)
                destination_idx = next((index for index, (stop, _) in enumerate(stops_tuple) if destination_cleaned in clean_string(stop)), None)
                if origin_idx is not None and destination_idx is not None and origin_idx >= destination_idx:
                    logger.debug(f"Skipping route {route.id} as origin index {origin_idx} >= destination index {destination_idx}")
                    continue

                first_stop_time = stops_tuple[0][1]
                try:
                    split_first_stop_time = first_stop_time.split('h')
                except Exception:
                    split_first_stop_time = first_stop_time.split(':')
                try:
                    first_stop_time_hour = int(split_first_stop_time[0])
                    first_stop_time_minute = int(split_first_stop_time[1])
                    logger.debug(f"Route {route.id} first stop time - Hour: {first_stop_time_hour}, Minute: {first_stop_time_minute}")
                except (ValueError, IndexError) as e:
                    logger.exception(f"Error parsing first stop time '{first_stop_time}' for route {route.id}")
                    continue

                if first_stop_time_hour > input_hour or (first_stop_time_hour == input_hour and first_stop_time_minute > input_minute):
                    last_stop_time = stops_tuple[-1][1]
                    return_routes.append(
                        ReturnRoute(
                            route.id,
                            route.route,
                            origin_cleaned,
                            destination_cleaned,
                            first_stop_time,
                            last_stop_time,
                            str(stops),
                            route.type_of_day,
                            route.information,
                            route.likes_percent,
                            route.dislikes_percent
                        ).__dict__ 
                    )
                    logger.debug(f"Added route {route.id} to return_routes")

            return_routes.sort(key=lambda x: x['start'])
            logger.info(f"Returning {len(return_routes)} routes")
            return Response(return_routes)
        except Exception as e:
            logger.exception("Error occurred in get_trip_v2")
            return Response(status=404)
        
@api_view(['GET'])
@require_GET
def get_webapp_load_v2(request):
        if request.method == 'GET':
            try:
                all_routes = Route.objects.all()
                all_routes = all_routes.exclude(disabled=True)
                holidays = Holiday.objects.all()
                routes = []
                all_stops = set()  # Use a set to store unique stops
                try:
                    variable = Variables.objects.all().first().__dict__
                    routes = [{'version': variable['version'], 'maps': variable['maps'], 'holidays': HolidaySerializer(holidays, many=True).data}]
                except Exception as e:
                    print(e)
                for route in all_routes:
                    stops = route.stops.replace('\'', '').replace('{', '').replace('}', '').split(',')
                    route_stops = [stop.split(':')[0].strip() for stop in stops]
                    all_stops.update(route_stops)  # Add stops to the set
                    all_times = [stop.split(':')[1].strip() for stop in stops]
                    routes.append(LoadRoute(route.id, route.route, route_stops, all_times, route.type_of_day, route.information).__dict__)
                
                # Convert set to list for JSON serialization
                all_stops_list = list(all_stops)
                
                # Add all_stops to the response
                routes[0]['stops'] = all_stops_list
                
                return Response(routes)
            except Exception as e:
                print(e)
                return Response(status=404)