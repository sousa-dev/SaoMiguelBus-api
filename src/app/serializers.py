from rest_framework import serializers
from app.models import Stop, Route, Stat, ReturnRoute, LoadRoute, Variables
class StopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stop
        fields = '__all__'

class VariablesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variables
        fields = '__all__'

class RouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Route
        fields = '__all__'

class StatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stat
        fields = '__all__'

class ReturnRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReturnRoute
        fields = '__all__'

class LoadRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoadRoute
        fields = '__all__'