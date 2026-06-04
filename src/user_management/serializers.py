"""Serializers for the REST account/auth surface."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, max_length=128)
    display_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, max_length=128)


class SocialSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=['apple', 'google'])
    identity_token = serializers.CharField()
    nonce = serializers.CharField(required=False, allow_blank=True)
    display_name = serializers.CharField(max_length=150, required=False, allow_blank=True)


class UserSerializer(serializers.ModelSerializer):
    displayName = serializers.SerializerMethodField()
    dateJoined = serializers.DateTimeField(source='date_joined', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'displayName', 'dateJoined']

    def get_displayName(self, obj) -> str:  # noqa: N802 (camelCase API field)
        return obj.first_name or obj.email
