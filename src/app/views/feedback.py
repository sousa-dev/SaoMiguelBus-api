import json
from django.http import JsonResponse
from app.models import AIFeedback
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def gather_feedback(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            language = data.get('language')
            first_time = True if data.get('firstTime') == 'sim' else False
            residence_status = data.get('residenceStatus')
            guide_preference = data.get('guidePreference')
            payment_willingness = data.get('paymentWillingness')
            feedback = AIFeedback(
                language=language,
                first_time=first_time,
                residence_status=residence_status,
                guide_preference=guide_preference,
                payment_willingness=payment_willingness
            )
            feedback.save()
            return JsonResponse({'message': 'Feedback saved successfully'}, status=201)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)