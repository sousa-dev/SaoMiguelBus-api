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
        return f"{self.route.strip()} | {self.start} -> {self.end} | {self.start_time}"

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