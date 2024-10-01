import collections
from difflib import SequenceMatcher
from django.shortcuts import render
from django.utils import timezone
from SaoMiguelBus import settings
from numpy import full
from rest_framework.decorators import api_view
from rest_framework.response import Response
from app.models import Holiday, Stop, Route, Stat, ReturnRoute, LoadRoute, Trip, TripStop, Variables, Ad, Group, Info, Data as route_data
from app.serializers import DataSerializer, HolidaySerializer, StopSerializer, RouteSerializer, StatSerializer, ReturnRouteSerializer, LoadRouteSerializer, VariablesSerializer, AdSerializer, GroupSerializer, InfoSerializer
from django.views.decorators.http import require_GET, require_POST
from datetime import datetime, date, timedelta
from statistics import median
import requests
from django.http import JsonResponse
import pytz
import requests

@api_view(['GET'])
@require_GET
def get_all_stops_v2(request):
    if request.method == 'GET':
        all_stops = TripStop.objects.all()
        serializer = StopSerializer(all_stops, many=True)
        return Response(serializer.data)

@api_view(['GET'])
@require_GET
def get_trip_v2(request):
    if request.method == 'GET':
        origin = request.GET.get('origin', '')
        destination = request.GET.get('destination', '')
        absolute_url = request.build_absolute_uri('/')
        mapsURL =  absolute_url + "api/v1/gmaps?" + \
            "origin=" + origin + \
            "&destination=" + destination + \
            "&departure_time=$time" + "&key=" + settings.AUTH_KEY + \
            "&platform=web" + \
            "&version=5"
        
        def fetch_and_process_routes():
            try:
                # Filter routes that are more than 1 month old
                one_month_ago = timezone.now() - timedelta(days=30)
                old_routes = Trip.objects.filter(added__lte=one_month_ago)
                # Delete old routes
                old_routes.delete()

                routes = Trip.objects.all().exclude(disabled=True)

                origin_cleaned = origin.lower().replace('á', 'a').replace('à', 'a').replace('â', 'a').replace('ã', 'a').replace('ä', 'a') \
                                        .replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('ë', 'e') \
                                        .replace('í', 'i').replace('ì', 'i').replace('î', 'i').replace('ï', 'i') \
                                        .replace('ó', 'o').replace('ò', 'o').replace('ô', 'o').replace('õ', 'o').replace('ö', 'o') \
                                        .replace('ú', 'u').replace('ù', 'u').replace('û', 'u').replace('ü', 'u') \
                                        .replace('ç', 'c')
                destination_cleaned = destination.lower().replace('á', 'a').replace('à', 'a').replace('â', 'a').replace('ã', 'a').replace('ä', 'a') \
                                             .replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('ë', 'e') \
                                             .replace('í', 'i').replace('ì', 'i').replace('î', 'i').replace('ï', 'i') \
                                             .replace('ó', 'o').replace('ò', 'o').replace('ô', 'o').replace('õ', 'o').replace('ö', 'o') \
                                             .replace('ú', 'u').replace('ù', 'u').replace('û', 'u').replace('ü', 'u') \
                                             .replace('ç', 'c')
                
                if origin_cleaned == '' or destination_cleaned == '':
                    return {'error': 'Origin and destination are required'}

                for route in routes:
                    routeStops = str(route.stops).lower().replace('á', 'a').replace('à', 'a').replace('â', 'a').replace('ã', 'a').replace('ä', 'a') \
                                         .replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('ë', 'e') \
                                         .replace('í', 'i').replace('ì', 'i').replace('î', 'i').replace('ï', 'i') \
                                         .replace('ó', 'o').replace('ò', 'o').replace('ô', 'o').replace('õ', 'o').replace('ö', 'o') \
                                         .replace('ú', 'u').replace('ù', 'u').replace('û', 'u').replace('ü', 'u') \
                                         .replace('ç', 'c')
                    if origin_cleaned not in routeStops or destination_cleaned not in routeStops or routeStops.find(origin_cleaned) > routeStops.find(destination_cleaned):
                        routes = routes.exclude(id=route.id)

                type_of_day = request.GET.get('day', '')
                if type_of_day:
                    routes = routes.filter(type_of_day=type_of_day.upper())

                start_time = request.GET.get('start', '')
                if start_time:
                    for route in routes:
                        route_start_time = str(route.stops).split(',')[0].split(':')[1].replace('{','').replace('\'','').strip()
                        route_start_time_hour = int(route_start_time.split('h')[0])
                        route_start_time_minute = int(route_start_time.split('h')[1])
                        input_hour, input_minute = map(int, start_time.split('h'))
                        if route_start_time_hour < input_hour or (route_start_time_hour == input_hour and route_start_time_minute < input_minute):
                            routes = routes.exclude(id=route.id)

                full = request.GET.get('full', '').lower() == 'true'
                if not full:
                    #TODO: format route.stops to exclude stops outside the scope
                    pass

                return routes
            except Exception as e:
                print(e)
                return None

        try:
            routes = fetch_and_process_routes()
            if routes is None:
                return Response(status=404)

            if not routes.exists():
                # Fetch maps data and retry processing routes
                requests.get(mapsURL)
                routes = fetch_and_process_routes()
                if not routes or not routes.exists():
                    return Response({'error': 'No routes found after fetching maps data'}, status=404)

            return_routes = [
                ReturnRoute(
                    route.id,
                    route.route,
                    origin.lower().replace('á', 'a').replace('à', 'a').replace('â', 'a').replace('ã', 'a').replace('ä', 'a') \
                          .replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('ë', 'e') \
                          .replace('í', 'i').replace('ì', 'i').replace('î', 'i').replace('ï', 'i') \
                          .replace('ó', 'o').replace('ò', 'o').replace('ô', 'o').replace('õ', 'o').replace('ö', 'o') \
                          .replace('ú', 'u').replace('ù', 'u').replace('û', 'u').replace('ü', 'u') \
                          .replace('ç', 'c'),
                    destination.lower().replace('á', 'a').replace('à', 'a').replace('â', 'a').replace('ã', 'a').replace('ä', 'a') \
                               .replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('ë', 'e') \
                               .replace('í', 'i').replace('ì', 'i').replace('î', 'i').replace('ï', 'i') \
                               .replace('ó', 'o').replace('ò', 'o').replace('ô', 'o').replace('õ', 'o').replace('ö', 'o') \
                               .replace('ú', 'u').replace('ù', 'u').replace('û', 'u').replace('ü', 'u') \
                               .replace('ç', 'c'),
                    str(route.stops).split(':')[1].split(",")[0].replace('\'', '').strip(),
                    str(route.stops).split(':')[-1].split(",")[0].replace('\'', '').replace('}', '').strip(),
                    str(route.stops),
                    route.type_of_day,
                    route.information
                ).__dict__ for route in routes
            ]
            return Response(return_routes)
        except Exception as e:
            print(e)
            return Response(status=404)
