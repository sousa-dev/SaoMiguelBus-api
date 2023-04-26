from sqlite3 import Timestamp
from django.db import models
from jsonfield import JSONField
import json
from sqlalchemy import null


# Create your models here.

class Stop(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    def __str__(self):
        return self.name

class Route(models.Model):
    id = models.AutoField(primary_key=True)
    route = models.CharField(max_length=100)
    stops = JSONField()
    type_of_day = models.CharField(max_length=100)
    information = JSONField()
    disabled = models.BooleanField(default=False)

    start = ""
    start_time = ""
    end = ""

    def __str__(self):
        self.start = self.stops.split(',')[0].split(':')[0].replace('{','').replace('\'','').strip()
        self.start_time = self.stops.split(',')[0].split(':')[1].replace('{','').replace('\'','').strip()
        self.end = self.stops.split(',')[-1].split(':')[0].replace('}','').replace('\'','').strip()
        return f"{self.route.strip()} | {self.start} -> {self.end} | {self.start_time} | {self.type_of_day}"

class Stat(models.Model):    
    id = models.AutoField(primary_key=True)
    request= models.CharField(max_length=100)
    origin = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
    type_of_day = models.CharField(max_length=100)
    time = models.CharField(max_length=100)
    platform = models.CharField(max_length=100)
    language = models.CharField(max_length=100)
    timestamp = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.request} | {self.origin} -> {self.destination} | {self.type_of_day}"
    
class Variables(models.Model):
    version = models.CharField(max_length=100)
    maps = models.BooleanField(default=False)

    def __str__(self):
        return f"Version: {self.version} | Maps: {self.maps}"


class ReturnRoute():
    def __init__(self, id, route, origin, destination, start, end, stops, type_of_day, information):
        self.id = id
        self.route = route
        self.origin = origin
        self.destination = destination
        self.start = start
        self.end = end
        self.stops = stops
        self.type_of_day = type_of_day
        self.information = information
    def __str__(self):
        return self.route

class LoadRoute():
    def __init__(self, id, route, stops, times, weekday, information = ""):
        self.id = id
        self.route = route
        self.stops = stops
        self.times = times
        self.weekday = weekday
        self.information = information
    def __str__(self):
        stop_times = ""
        for stop in self.stops:
            stop_times += f"{stop}-{self.times[stop]},"
        return '{' + f'"id": {self.id}, "route": {self.route}, "stops": {stop_times}, "weekday": {self.weekday}, "information": {self.information}' + '}'