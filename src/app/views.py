from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from app.models import Stop, Route
from app.serializers import StopSerializer, RouteSerializer
from datetime import datetime


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
def get_route_v1(request):
    if request.method == 'GET':
        try:
            routes = Route.objects.all()
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
            serializer = RouteSerializer(routes, many=True)
            return Response(serializer.data)
        except Exception:
            print(Exception)
            return Response(status=404)

