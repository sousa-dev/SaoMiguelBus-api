from app.models import Route, Stop, Trip, TripStop
from django.http import HttpResponse

from app.utils.str_utils import clean_string

def fix_stops(request):
    stops = Stop.objects.all()
    for stop in stops :
        stop.save()

    trip_stops = TripStop.objects.all()
    for stop in trip_stops :
        stop.save()

    routes = Route.objects.all()
    for route in routes:
        route.save()

    trip_routes = Trip.objects.all()
    for trip_route in trip_routes:
        trip_route.save()

    return HttpResponse("Stops fixed")