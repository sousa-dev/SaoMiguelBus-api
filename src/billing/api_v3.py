"""Billing v3 API: entitlement read + RevenueCat reconcile webhook (seam)."""

from __future__ import annotations

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from billing.services import entitlement_response, reconcile_revenuecat


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def entitlement_view(request: Request) -> Response:
    return Response(entitlement_response(request.user))


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def revenuecat_webhook(request: Request) -> Response:
    """Future-IAP seam: reconcile RevenueCat events into Entitlement.

    Authorized by a shared secret sent in the Authorization header (configured
    in the RevenueCat dashboard). No client SDK is wired yet.
    """
    secret = getattr(settings, 'REVENUECAT_WEBHOOK_SECRET', '')
    provided = request.headers.get('Authorization', '')
    if not secret or provided != secret:
        return Response({'error': 'unauthorized'}, status=status.HTTP_400_BAD_REQUEST)

    body = request.data if isinstance(request.data, dict) else {}
    event = body.get('event') or {}
    reconcile_revenuecat(event)
    return Response({'status': 'ok'})
