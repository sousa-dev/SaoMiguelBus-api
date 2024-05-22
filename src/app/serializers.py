from rest_framework import serializers
from app.models import Data, Stop, Route, Stat, ReturnRoute, LoadRoute, Variables, Ad, Group, Info, Holiday
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

class AdSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ad
        fields = '__all__'

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = '__all__'

class InfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Info
        fields = '__all__'

class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = '__all__'
        
class ReturnRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReturnRoute
        fields = '__all__'

class LoadRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoadRoute
        fields = '__all__'
        
class DataSerializer(serializers.Serializer):
    class Meta:
        model = Data
        fields = '__all__'