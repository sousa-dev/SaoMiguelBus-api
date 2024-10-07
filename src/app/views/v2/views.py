import json
from django.utils import timezone
import requests
from SaoMiguelBus import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from app.models import Stop, TripStop, ReturnRoute, Trip
from app.serializers import StopSerializer, TripSerializer
from django.views.decorators.http import require_GET
import django.db.models as models
from datetime import datetime, timedelta
from django.http import JsonResponse

from app.utils.day_utils import get_type_of_day
from app.views.v1.views import get_trip_v1_logic

@api_view(['GET'])
@require_GET
def get_all_stops_v2(request):
    if request.method == 'GET':
        all_trip_stops = TripStop.objects.all()
        all_normal_stops = Stop.objects.all()  # Get normal stops
        combined_stops = list(all_trip_stops) + list(all_normal_stops)  # Combine both trip stops and normal stops
        serializer = StopSerializer(combined_stops, many=True)
        return Response(serializer.data)

@api_view(['GET'])
@require_GET
def get_trip_v2(request):
    if request.method == 'GET':
        if request.GET.get('all', False):
            trips = Trip.objects.all()
            serializer = TripSerializer(trips, many=True)
            return JsonResponse(serializer.data, safe=False)
        
        origin = request.GET.get('origin', '')
        destination = request.GET.get('destination', '')
        date_day = request.GET.get('day', '')
        start_time = request.GET.get('start', '00:00')

        full_ = request.GET.get('full', '').lower() == 'true'

        day = get_type_of_day(datetime.strptime(date_day, '%Y-%m-%d'))

        absolute_url = request.build_absolute_uri('/')

        mapsURL =  absolute_url + "api/v1/gmaps?" + \
            "origin=" + origin + \
            "&destination=" + destination + \
            "&day=" + date_day + \
            "&start=" + start_time + \
            "&key=" + settings.AUTH_KEY + \
            "&platform=web" + \
            "&version=5"
        
        def clean_string(s):
            translation_table = str.maketrans(
                'áàâãäéèêëíìîïóòôõöúùûüç',
                'aaaaaeeeeiiiiooooouuuuc'
            )
            return s.lower().translate(translation_table)

        origin_cleaned = clean_string(origin)
        destination_cleaned = clean_string(destination)

        def fetch_and_process_routes():
            try:
                # Delete routes older than 1 month
                one_month_ago = timezone.now() - timedelta(days=30)
                Trip.objects.filter(added__lte=one_month_ago).delete()

                if not origin_cleaned or not destination_cleaned:
                    return {'error': 'Origin and destination are required'}
                
                routes = Trip.objects.filter(disabled=False).annotate(
                    cleaned_stops=models.Func(
                        models.F('stops'),
                        function='LOWER',
                        output_field=models.CharField()
                    )
                ).filter(
                    cleaned_stops__contains=origin_cleaned).filter(
                        cleaned_stops__contains=destination_cleaned
                ).exclude(
                    cleaned_stops__regex=rf'{destination_cleaned}.*{origin_cleaned}'
                )

                type_of_day = get_type_of_day(datetime.strptime(date_day, '%Y-%m-%d'))
                if type_of_day:
                    routes = routes.filter(type_of_day=type_of_day.upper())

                if not full_:
                    # TODO: format route.stops to exclude stops outside the scope
                    pass
                return routes
            except Exception as e:
                import traceback
                traceback.print_exc()
                return None

        try:
            routes = fetch_and_process_routes()
            if routes is None:
                return Response(status=404)

            if not routes.exists():
                requests.get(mapsURL)
                routes = fetch_and_process_routes()
                
            old_routes = get_trip_v1_logic(origin, destination, day, start_time.replace(':', 'h'), full_, prefix=True, sort=False) or []

            # Prepare the start time for comparison
            try:
                if start_time == '':
                    input_hour, input_minute = 0, 0
                else:
                    input_hour, input_minute = map(int, start_time.replace('h', ':').split(':'))
            except ValueError:
                import traceback
                traceback.print_exc()
                return Response({'error': 'Invalid start time format'}, status=400)

            # Process routes in a more efficient manner
            return_routes = old_routes
            for route in routes:
                stops = route.stops
                stops_tuple = [(stop, time) for stop, time in stops.items()]

                first_stop_time = stops_tuple[0][1]
                try:
                    split_first_stop_time = first_stop_time.split('h')
                except:
                    split_first_stop_time = first_stop_time.split(':')
                first_stop_time_hour = int(split_first_stop_time[0])
                first_stop_time_minute = int(split_first_stop_time[1])
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
                            route.information
                        ).__dict__ 
                    )
            return_routes.sort(key=lambda x: x['start'])
            return Response(return_routes)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(status=404)