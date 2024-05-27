import collections
from difflib import SequenceMatcher
from django.shortcuts import render
from django.utils import timezone
from SaoMiguelBus import settings
from numpy import full
from rest_framework.decorators import api_view
from rest_framework.response import Response
from app.models import Holiday, Stop, Route, Stat, ReturnRoute, LoadRoute, Trip, TripStop, Variables, Ad, Group, Info, Data as route_data
from app.serializers import DataSerializer, HolidaySerializer, StopSerializer, RouteSerializer, StatSerializer, ReturnRouteSerializer, LoadRouteSerializer, TripSerializer, VariablesSerializer, AdSerializer, GroupSerializer, InfoSerializer
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
        if request.GET.get('all', False):
            trips = Trip.objects.all()
            serializer = TripSerializer(trips, many=True)
            print(serializer.data)  # Adiciona isto para verificar a saída do serializer
            return JsonResponse(serializer.data, safe=False)
        
        origin = request.GET.get('origin', '')
        destination = request.GET.get('destination', '')
        absolute_url = request.build_absolute_uri('/')
        mapsURL =  absolute_url+"api/v1/gmaps?" + \
        "origin=" + origin + \
        "&destination=" + destination + \
        "&departure_time=$time" + "&key=" + settings.AUTH_KEY + \
        "&platform=web" + \
        "&version=5"
        
        requests.get(mapsURL)
        
        try:
            routes = Trip.objects.all()
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
            type_of_day = request.GET.get('day', '')
            if type_of_day != '':
                routes = routes.filter(type_of_day=type_of_day.upper())
            start_time = request.GET.get('start', '')
            if start_time != '':
                for route in routes:
                    route_start_time = str(route.stops).split(',')[0].split(':')[1].replace('{','').replace('\'','').strip()
                    route_start_time_hour = int(route_start_time.split('h')[0])
                    route_start_time_minute = int(route_start_time.split('h')[1])
                    routes = routes.exclude(id=route.id) if route_start_time_hour < int(start_time.split('h')[0]) or (route_start_time_hour == int(start_time.split('h')[0]) and route_start_time_minute < int(start_time.split('h')[1])) else routes
            full = True if request.GET.get('full', '').lower() == 'true' else False
            if not full:
                #TODO: format route.stops to exclude stops outside the scope
                pass
            #TODO: get origin, destination, start and end time
            return_routes = [ReturnRoute(route.id, route.route, origin, destination, str(route.stops).split(':')[1].split(",")[0].replace('\'', '').strip(), str(route.stops).split(':')[-1].split(",")[0].replace('\'', '').replace('}', '').strip(), str(route.stops), route.type_of_day, route.information).__dict__ for route in routes]
            return Response(return_routes)
        except Exception as e:
            print(e)
            return Response(status=404)