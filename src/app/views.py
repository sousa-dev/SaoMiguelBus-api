from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from app.models import Stop, Route
from app.serializers import StopSerializer, RouteSerializer
from datetime import datetime


# Create your views here.

#Get All Stops
@api_view(['GET', 'POST'])
def get_all_stops_v1(request):
    if request.method == 'GET':
        all_stops = Stop.objects.all()
        serializer = StopSerializer(all_stops, many=True)
        return Response(serializer.data)

    if request.method == 'POST':
        pass

#Get All Routes
@api_view(['GET', 'POST'])
def get_all_routes_v1(request):
    if request.method == 'GET':
        all_routes = Route.objects.all()
        serializer = RouteSerializer(all_routes, many=True)
        return Response(serializer.data)

    if request.method == 'POST':
        pass
