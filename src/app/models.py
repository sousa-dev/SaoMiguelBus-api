from sqlite3 import Timestamp
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from jsonfield import JSONField
import json
from sqlalchemy import null

from app.utils.str_utils import clean_string


class Data(models.Model):
    id = models.AutoField(primary_key=True)
    data = JSONField()
    origin = models.CharField(max_length=100, null=True, blank=True)
    destination = models.CharField(max_length=100, null=True, blank=True)
    language_code = models.CharField(max_length=100, null=True, blank=True)
    time = models.CharField(max_length=100, null=True, blank=True)
    platform = models.CharField(max_length=100, null=True, blank=True)
    
    def __str__(self):
        return str(self.origin) + " -> " + str(self.destination) + " | " + str(self.time)

class TripStop(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    cleaned_name = models.CharField(max_length=100, null=True, blank=True)

    def save(self, *args, **kwargs):
        self.cleaned_name = clean_string(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Trip(models.Model):
    id = models.AutoField(primary_key=True)
    route = models.CharField(max_length=100)
    stops = JSONField()
    cleaned_stops = JSONField()
    type_of_day = models.CharField(max_length=100)
    information = JSONField()
    disabled = models.BooleanField(default=False)
    
    added = models.DateTimeField(auto_now_add=True)

    likes = models.IntegerField(default=0)
    dislikes = models.IntegerField(default=0)

    @property
    def likes_percent(self):
        total = self.likes + self.dislikes
        return int(self.likes / total * 100) if total > 0 else 0

    @property
    def dislikes_percent(self):
        total = self.likes + self.dislikes
        return int(self.dislikes / total * 100) if total > 0 else 0
    
    start = ""
    start_time = ""
    end = ""

    def save(self, *args, **kwargs):
        self.stops = str(self.stops)
        self.cleaned_stops = clean_string(str(self.stops))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.route.strip()} | {self.type_of_day}"

class Stop(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    cleaned_name = models.CharField(max_length=100, null=True, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()

    def save(self, *args, **kwargs):
        self.cleaned_name = clean_string(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Route(models.Model):
    id = models.AutoField(primary_key=True)
    route = models.CharField(max_length=100)
    stops = JSONField()
    cleaned_stops = JSONField(null=True, blank=True)
    type_of_day = models.CharField(max_length=100)
    information = JSONField()
    disabled = models.BooleanField(default=False)

    likes = models.IntegerField(default=0)
    dislikes = models.IntegerField(default=0)

    @property
    def likes_percent(self):
        total = self.likes + self.dislikes
        return int(self.likes / total * 100) if total > 0 else 0

    @property
    def dislikes_percent(self):
        total = self.likes + self.dislikes
        return int(self.dislikes / total * 100) if total > 0 else 0
    
    start = ""
    start_time = ""
    end = ""

    def save(self, *args, **kwargs):
        self.stops = str(self.stops)
        self.cleaned_stops = clean_string(str(self.stops))
        super().save(*args, **kwargs)

    def __str__(self):
        self.start = str(self.stops).split(',')[0].split(':')[0].replace('{','').replace('\'','').strip()
        self.start_time = str(self.stops).split(',')[0].split(':')[1].replace('{','').replace('\'','').strip()
        self.end = str(self.stops).split(',')[-1].split(':')[0].replace('}','').replace('\'','').strip()
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
    populate_maps_routes = models.BooleanField(default=False)

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

    titlePT = models.TextField(default="")
    messagePT = models.TextField(default="")
    titleEN = models.TextField(default="")
    messageEN = models.TextField(default="")
    titleES = models.TextField(default="")
    messageES = models.TextField(default="")
    titleFR = models.TextField(default="")
    messageFR = models.TextField(default="")
    titleDE = models.TextField(default="")
    messageDE = models.TextField(default="")

    start = models.DateTimeField(default=timezone.now)
    end = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=500)
    company = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.company} - {self.titlePT} | {self.messagePT} | {self.start} -> {self.end}"
    
class Holiday(models.Model):
    id = models.AutoField(primary_key=True)
    date = models.DateField()
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} | {self.date}"
    
class ReturnRoute():
    def __init__(self, id, route, origin, destination, start, end, stops, type_of_day, information, likes_percent, dislikes_percent):
        self.id = id
        self.route = route
        self.origin = origin
        self.destination = destination
        self.start = start
        self.end = end
        self.stops = stops
        self.type_of_day = type_of_day
        self.information = information
        self.likes_percent = likes_percent
        self.dislikes_percent = dislikes_percent
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
class AIFeedback(models.Model):
    id = models.AutoField(primary_key=True)
    language = models.CharField(max_length=10, null=True)
    first_time = models.BooleanField(null=True)
    residence_status = models.CharField(max_length=50, null=True)
    guide_preference = models.CharField(max_length=50, null=True)
    payment_willingness = models.CharField(max_length=50, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback {self.id} | {self.timestamp}"
    
class EmailOpen(models.Model):
    id = models.AutoField(primary_key=True)
    email_template_id = models.IntegerField()
    contact_id = models.IntegerField()
    clicks = models.IntegerField(default=0)

    def __str__(self):
        return f"Email open {self.email_template_id} | {self.contact_id} | {self.clicks} clicks"