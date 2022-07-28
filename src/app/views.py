from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from app.models import Stop, Route, ReturnRoute
from app.serializers import StopSerializer, RouteSerializer, ReturnRouteSerializer
from datetime import datetime
import json


# Create your views here.

#Get All Stops
@api_view(['GET'])
def get_all_stops_v1(request):
    if request.method == 'GET':
        all_stops = Stop.objects.all()
        serializer = StopSerializer(all_stops, many=True)
        return Response(serializer.data)

#Get All Routes
@api_view(['GET'])
def get_all_routes_v1(request):
    if request.method == 'GET':
        all_routes = Route.objects.all()
        serializer = RouteSerializer(all_routes, many=True)
        return Response(serializer.data)

@api_view(['GET'])
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
                pass
            full = True if request.GET.get('full', '').lower() == 'true' else False
            if not full:
                #TODO: format route.stops to exclude stops outside the scope
                pass
            #TODO: get origin, destination, start and end time
            return_routes = [ReturnRoute(route.id, route.route, "origin", "destination", "start", "end", route.stops, route.type_of_day, route.information).__dict__ for route in routes]
            return Response(return_routes)
        except Exception:
            print(Exception)
            return Response(status=404)

@api_view(['GET'])
def get_route_v1(request, route_id):
    if request.method == 'GET':
        try:
            routes = Route.objects.all()
            routes = routes.filter(route__icontains=route_id)
            serializer = RouteSerializer(routes, many=True)
            #TODO: Return a new formatted entity
            return Response(serializer.data)
        except Exception:
            print(Exception)
            return Response(status=404)

@api_view(['GET'])
def get_android_load_v1(request):
        if request.method == 'GET':
            try:
                all_routes = Route.objects.all()
                all_routes = all_routes.exclude(disabled=True)
                for route in all_routes:
                    #TODO: Get formatted route to load on Sao Miguel Bus Android app
                    stops = route.stops.replace('\'', '').replace('{', '').replace('}', '').split(',')
                    for stop in stops:
                        stop_name = stop.split(':')[0].strip()
                        stop_time = stop.split(':')[1].strip()
                        print(stop_name, stop_time)
                serializer = RouteSerializer(all_routes, many=True)
                return Response("pass")
                return Response(serializer.data)
            except Exception as e:
                print(e)
                return Response(status=404)

