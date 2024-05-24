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
        try:
            routes = Trip.objects.all()
            routes = routes.exclude(disabled=True)
            origin = request.GET.get('origin', '')

            if origin in ['Povoacão', 'Lomba do Loucão', 'Ponta Garca']:
                origin = origin.replace('c', 'ç')
            routes = routes.filter(stops__icontains=origin) if origin != '' else routes

            destination = request.GET.get('destination', '')

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