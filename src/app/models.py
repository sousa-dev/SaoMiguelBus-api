from sqlite3 import Timestamp
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
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
    
class Ad(models.Model):
    id = models.AutoField(primary_key=True)
    entity = models.CharField(max_length=100)
    description = models.CharField(max_length=100, null=True, blank=True)
    media = models.CharField(max_length=1000)
    start = models.DateTimeField(default=timezone.now)
    end = models.DateTimeField(default=timezone.now)
    ACTION_CHOICES = [('open', 'Open URL'), ('directions', 'Get Directions To'), ('call', 'Call To Number'), ('sms', 'Send SMS'), ('email', 'Send Email'), ('whatsapp', 'Send WhatsApp Message')]
    action = models.CharField(max_length=100, choices=ACTION_CHOICES, null=True, blank=True)
    target = models.CharField(max_length=100, null=True, blank=True)
    advertise_on = models.CharField(max_length=100)
    PLATFORM_CHOICES = [('android', 'Android'), ('ios', 'iOS'), ('web', 'Web')]
    platform = models.CharField(max_length=100, choices=PLATFORM_CHOICES)
    STATUS_CHOICES = [('pending', 'Pending'), ('active', 'Active'), ('inactive', 'Inactive'), ('failed', 'Failed'), ('default', 'Default')]
    status = models.CharField(max_length=100, choices=STATUS_CHOICES, default="pending")
    seen = models.IntegerField(default=0)
    clicked = models.IntegerField(default=0)

    def clean(self):
        if (self.action is None and self.target is not None) or (self.action is not None and self.target is None):
            raise ValidationError("Target cannot be set if action is not set or vice versa.")
    
    def __str__(self):
        return f"{self.entity} | {self.status} | {self.start} -> {self.end}"

class Group(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50)
    stops = models.CharField(max_length=500)

    def __str__(self):
        return f"{self.name.title()}"

class Info(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=50)
    message = models.CharField(max_length=1000)
    start = models.DateTimeField(default=timezone.now)
    end = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=500)
    company = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.company} - {self.title} | {self.message} | {self.start} -> {self.end}"
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