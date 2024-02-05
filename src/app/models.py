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

class MAPLocation(models.Model):
    lat = models.FloatField()
    lng = models.FloatField()

    def __str__(self):
        return f"Location(lat={self.lat}, lng={self.lng})"

class MAPStep(models.Model):
    distance_text = models.CharField(max_length=100)
    distance_value = models.IntegerField()
    duration_text = models.CharField(max_length=100)
    duration_value = models.IntegerField()
    end_location = models.OneToOneField(MAPLocation, related_name='step_end_location', on_delete=models.CASCADE)
    html_instructions = models.TextField()
    maneuver = models.CharField(max_length=100, blank=True, null=True)
    polyline = models.TextField()
    start_location = models.OneToOneField(MAPLocation, related_name='step_start_location', on_delete=models.CASCADE)
    travel_mode = models.CharField(max_length=50)

    def __str__(self):
        return f"Step(distance={self.distance_text}, duration={self.duration_text}, instructions={self.html_instructions})"

class MAPLeg(models.Model):
    arrival_time_text = models.CharField(max_length=100)
    arrival_time_time_zone = models.CharField(max_length=100)
    arrival_time_value = models.BigIntegerField()
    departure_time_text = models.CharField(max_length=100)
    departure_time_time_zone = models.CharField(max_length=100)
    departure_time_value = models.BigIntegerField()
    distance_text = models.CharField(max_length=100)
    distance_value = models.IntegerField()
    duration_text = models.CharField(max_length=100)
    duration_value = models.IntegerField()
    end_address = models.CharField(max_length=255)
    end_location = models.OneToOneField(MAPLocation, related_name='leg_end_location', on_delete=models.CASCADE)
    start_address = models.CharField(max_length=255)
    start_location = models.OneToOneField(MAPLocation, related_name='leg_start_location', on_delete=models.CASCADE)
    steps = models.ManyToManyField(MAPStep)

    def __str__(self):
        return f"Leg(from {self.start_address} to {self.end_address}, duration={self.duration_text})"

class MAPRoute(models.Model):
    bounds_northeast = models.OneToOneField(MAPLocation, related_name='route_bounds_northeast', on_delete=models.CASCADE)
    bounds_southwest = models.OneToOneField(MAPLocation, related_name='route_bounds_southwest', on_delete=models.CASCADE)
    copyrights = models.CharField(max_length=255)
    legs = models.ManyToManyField(MAPLeg)
    overview_polyline = models.TextField()
    summary = models.CharField(max_length=255, blank=True, null=True)
    warnings = models.TextField(blank=True, null=True)
    waypoint_order = models.TextField()

    def __str__(self):
        return f"Route(summary={self.summary})"

import json
from typing import Any, Dict, List

class Location:
    def __init__(self, lat: float, lng: float):
        self.lat = lat
        self.lng = lng
    def __str__(self):
        return f"Location(lat={self.lat}, lng={self.lng})"

class Step:
    def __init__(self, distance_text: str, distance_value: int, duration_text: str, duration_value: int, end_location: Location, html_instructions: str, maneuver: str, polyline: str, start_location: Location, travel_mode: str):
        self.distance_text = distance_text
        self.distance_value = distance_value
        self.duration_text = duration_text
        self.duration_value = duration_value
        self.end_location = end_location
        self.html_instructions = html_instructions
        self.maneuver = maneuver
        self.polyline = polyline
        self.start_location = start_location
        self.travel_mode = travel_mode
    def __str__(self):
        return f"Step(distance={self.distance_text} [{self.distance_value} meters], duration={self.duration_text} [{self.duration_value} seconds], start={self.start_location}, end={self.end_location}, instructions={self.html_instructions}, maneuver={self.maneuver}, mode={self.travel_mode})"

class Leg:
    def __init__(self, arrival_time_text: str, arrival_time_time_zone: str, arrival_time_value: int, departure_time_text: str, departure_time_time_zone: str, departure_time_value: int, distance_text: str, distance_value: int, duration_text: str, duration_value: int, end_address: str, end_location: Location, start_address: str, start_location: Location, steps: List[Step]):
        self.arrival_time_text = arrival_time_text
        self.arrival_time_time_zone = arrival_time_time_zone
        self.arrival_time_value = arrival_time_value
        self.departure_time_text = departure_time_text
        self.departure_time_time_zone = departure_time_time_zone
        self.departure_time_value = departure_time_value
        self.distance_text = distance_text
        self.distance_value = distance_value
        self.duration_text = duration_text
        self.duration_value = duration_value
        self.end_address = end_address
        self.end_location = end_location
        self.start_address = start_address
        self.start_location = start_location
        self.steps = steps
    def __str__(self):
            steps_str = '\n'.join([str(step) for step in self.steps])
            return f"Leg(from {self.start_address} to {self.end_address}, duration={self.duration_text}, steps=[\n{steps_str}\n])"


class MAPRoute:
    def __init__(self, bounds_northeast: Location, bounds_southwest: Location, copyrights: str, legs: List[Leg], overview_polyline: str, summary: str, warnings: List[str], waypoint_order: List[int]):
        self.bounds_northeast = bounds_northeast
        self.bounds_southwest = bounds_southwest
        self.copyrights = copyrights
        self.legs = legs
        self.overview_polyline = overview_polyline
        self.summary = summary
        self.warnings = warnings
        self.waypoint_order = waypoint_order
    def __str__(self):
        legs_str = '\n'.join([str(leg) for leg in self.legs])
        return f"Route(summary={self.summary}, legs=[\n{legs_str}\n])"

class GeocodedWaypoint:
    def __init__(self, geocoder_status: str, place_id: str, types: List[str]):
        self.geocoder_status = geocoder_status
        self.place_id = place_id
        self.types = types
    def __str__(self):
        return f"GeocodedWaypoint(status={self.geocoder_status}, place_id={self.place_id}, types={self.types})"

class DirectionsResponse:
    def __init__(self, geocoded_waypoints: List[GeocodedWaypoint], routes: List[MAPRoute]):
        self.geocoded_waypoints = geocoded_waypoints
        self.routes = routes
    def __str__(self):
        waypoints_str = ', '.join([str(wp) for wp in self.geocoded_waypoints])
        routes_str = '\n'.join([str(route) for route in self.routes])
        return f"DirectionsResponse(waypoints=[{waypoints_str}], routes=[\n{routes_str}\n])"

# Assuming the class definitions provided above are already defined

def parse_location(data: Dict[str, Any]) -> Location:
    return Location(lat=data["lat"], lng=data["lng"])

def parse_step(data: Dict[str, Any]) -> Step:
    end_location = parse_location(data["end_location"])
    start_location = parse_location(data["start_location"])
    return Step(
        distance_text=data["distance"]["text"],
        distance_value=data["distance"]["value"],
        duration_text=data["duration"]["text"],
        duration_value=data["duration"]["value"],
        end_location=end_location,
        html_instructions=data["html_instructions"],
        maneuver=data.get("maneuver", ""),  # Optional field
        polyline=data["polyline"]["points"],
        start_location=start_location,
        travel_mode=data["travel_mode"]
    )

def parse_leg(data: Dict[str, Any]) -> Leg:
    end_location = parse_location(data["end_location"])
    start_location = parse_location(data["start_location"])
    steps = [parse_step(step) for step in data["steps"]]
    return Leg(
        arrival_time_text=data["arrival_time"]["text"],
        arrival_time_time_zone=data["arrival_time"]["time_zone"],
        arrival_time_value=data["arrival_time"]["value"],
        departure_time_text=data["departure_time"]["text"],
        departure_time_time_zone=data["departure_time"]["time_zone"],
        departure_time_value=data["departure_time"]["value"],
        distance_text=data["distance"]["text"],
        distance_value=data["distance"]["value"],
        duration_text=data["duration"]["text"],
        duration_value=data["duration"]["value"],
        end_address=data["end_address"],
        end_location=end_location,
        start_address=data["start_address"],
        start_location=start_location,
        steps=steps
    )

def parse_route(data: Dict[str, Any]) -> MAPRoute:
    bounds_northeast = parse_location(data["bounds"]["northeast"])
    bounds_southwest = parse_location(data["bounds"]["southwest"])
    legs = [parse_leg(leg) for leg in data["legs"]]
    return MAPRoute(
        bounds_northeast=bounds_northeast,
        bounds_southwest=bounds_southwest,
        copyrights=data["copyrights"],
        legs=legs,
        overview_polyline=data["overview_polyline"]["points"],
        summary=data["summary"],
        warnings=data["warnings"],
        waypoint_order=data["waypoint_order"]
    )

def parse_geocoded_waypoint(data: Dict[str, Any]) -> GeocodedWaypoint:
    return GeocodedWaypoint(
        geocoder_status=data["geocoder_status"],
        place_id=data["place_id"],
        types=data["types"]
    )

def parse_directions_response(json_data: str) -> DirectionsResponse:
    data = json_data
    geocoded_waypoints = [parse_geocoded_waypoint(wp) for wp in data["geocoded_waypoints"]]
    routes = [parse_route(route) for route in data["routes"]]
    return DirectionsResponse(geocoded_waypoints=geocoded_waypoints, routes=routes)