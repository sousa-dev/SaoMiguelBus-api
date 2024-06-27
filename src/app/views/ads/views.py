from app.models import Ad
from app.serializers import AdSerializer
from django.http import JsonResponse


def get_ad_info(request, ad_id):
    if request.method == 'GET':
        try:
            ad = Ad.objects.get(id=ad_id)
            serializer = AdSerializer(ad)
            return JsonResponse(serializer.data)
        except Ad.DoesNotExist:
            return JsonResponse({'error': 'Ad not found'}, status=404)