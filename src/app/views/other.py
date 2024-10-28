from app.models import EmailOpen, Route, Stop, Trip, TripStop
from django.http import HttpResponse, JsonResponse

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

def track_email_open(request):
    email_template_id = request.GET.get('email_template_id')
    contact_id = request.GET.get('contact_id')
    
    if email_template_id and contact_id:
        email_open, created = EmailOpen.objects.get_or_create(
            email_template_id=email_template_id,
            contact_id=contact_id,
        )
        email_open.clicks += 1
        email_open.save()
        
        return HttpResponse("Email open tracked", status=200)
    else:
        return HttpResponse("Missing parameters", status=400)
    
def get_email_opens(request):
    email_open = EmailOpen.objects.all()
    return JsonResponse(list(email_open), safe=False)