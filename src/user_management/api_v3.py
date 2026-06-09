"""REST account/auth API (v3).

Token auth for the mobile client. Public endpoints stay AllowAny globally; these
account endpoints opt into IsAuthenticated where a session is required.
"""

from __future__ import annotations

from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from user_management import services
from user_management.serializers import (
    LoginSerializer,
    RegisterSerializer,
    SocialSerializer,
    UserSerializer,
)
from user_management.social import SocialVerificationError, verify_social_identity


def _auth_payload(user) -> dict:
    token = services.get_or_create_token(user)
    return {'token': token.key, 'user': UserSerializer(user).data}


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def register_view(request: Request) -> Response:
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data['email']
    if services.email_taken(email):
        return Response(
            {'error': {'code': 'email_taken', 'message': 'An account with this email already exists.'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    user = services.create_account(
        email=email,
        password=serializer.validated_data['password'],
        display_name=serializer.validated_data.get('display_name', ''),
    )
    return Response(_auth_payload(user), status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def login_view(request: Request) -> Response:
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = services.authenticate_user(
        request,
        email=serializer.validated_data['email'],
        password=serializer.validated_data['password'],
    )
    if user is None:
        return Response(
            {'error': {'code': 'invalid_credentials', 'message': 'Incorrect email or password.'}},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    services.honor_legacy_entitlement(user)
    return Response(_auth_payload(user))


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def social_view(request: Request) -> Response:
    serializer = SocialSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        identity = verify_social_identity(
            provider=serializer.validated_data['provider'],
            identity_token=serializer.validated_data['identity_token'],
            nonce=serializer.validated_data.get('nonce') or None,
        )
    except SocialVerificationError as exc:
        return Response(
            {'error': {'code': 'invalid_social_token', 'message': str(exc)}},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    user = services.find_user_by_email(identity.email)
    if user is None:
        user = services.create_account(
            email=identity.email,
            password=None,
            display_name=serializer.validated_data.get('display_name', '') or identity.name,
        )
    else:
        services.honor_legacy_entitlement(user)

    if identity.provider == 'apple':
        from user_management.apple_oauth import exchange_code_for_refresh_token

        refresh_token = exchange_code_for_refresh_token(
            serializer.validated_data.get('authorization_code', '')
        )
        services.link_social_connection(
            user=user,
            provider='apple',
            subject=identity.subject,
            refresh_token=refresh_token or '',
        )

    return Response(_auth_payload(user))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request: Request) -> Response:
    return Response(UserSerializer(request.user).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def logout_view(request: Request) -> Response:
    services.rotate_token(request.user)
    return Response({'status': 'ok'})


@api_view(['DELETE', 'POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def delete_account_view(request: Request) -> Response:
    """Permanently delete the authenticated user's account (App Store 5.1.1(v)).

    Accepts DELETE (RESTful) and POST (for clients/proxies that cannot send a
    DELETE) — both perform the same irreversible deletion.
    """
    services.delete_account(request.user)
    return Response({'status': 'deleted'}, status=status.HTTP_200_OK)
