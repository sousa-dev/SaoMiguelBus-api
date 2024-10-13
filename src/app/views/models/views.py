from django.http import JsonResponse
from requests import Response
from app.models import Route, Trip
from rest_framework.decorators import api_view
from django.views.decorators.http import require_POST

import json

@api_view(['POST'])
@require_POST
def like_trip(request, trip_id):
    try:
        type_trip = request.GET.get('type_route', 'route')
        trip = Route.objects.get(id=trip_id) if type_trip == 'route' else Trip.objects.get(id=trip_id)

        request_count = int(request.GET.get('count', 1))

        if request_count == 2:
            trip.dislikes = max(0, trip.dislikes - 1)
            trip.likes += 1
        else:
            trip.likes += 1

        trip.save()
        return JsonResponse({'message': 'Likes updated successfully', 'likes_percent': trip.likes_percent, 'dislikes_percent': trip.dislikes_percent}, status=200)
    except (Trip.DoesNotExist, Route.DoesNotExist):
        return JsonResponse({'error': 'Trip not found'}, status=404)
    except Exception as e:
        print(e)
        return JsonResponse({'error': 'Internal Server Error'}, status=500)

@api_view(['POST'])
@require_POST
def dislike_trip(request, trip_id):
    try:
        type_trip = request.GET.get('type_route', 'route')
        trip = Route.objects.get(id=trip_id) if type_trip == 'route' else Trip.objects.get(id=trip_id)

        request_count = int(request.GET.get('count', 1))

        if request_count == 2:
            trip.likes = max(0, trip.likes - 1)
            trip.dislikes += 1
        else:
            trip.dislikes += 1

        trip.save()
        return JsonResponse({'message': 'Dislikes updated successfully', 'likes_percent': trip.likes_percent, 'dislikes_percent': trip.dislikes_percent}, status=200)
    except (Trip.DoesNotExist, Route.DoesNotExist):
        return JsonResponse({'error': 'Trip not found'}, status=404)
    except Exception as e:
        print(e)
        return JsonResponse({'error': 'Internal Server Error'}, status=500)
