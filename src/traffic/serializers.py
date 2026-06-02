"""Request validation for traffic v3 writes (service layer builds responses)."""

from __future__ import annotations

from rest_framework import serializers


class ReportWriteSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=128)
    category_slug = serializers.SlugField(required=False, allow_blank=True)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    road = serializers.CharField(max_length=160, required=False, allow_blank=True, default='')
    active_from = serializers.DateTimeField(required=False, allow_null=True)
    active_until = serializers.DateTimeField(required=False, allow_null=True)


class ConfirmSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=128)
    vote = serializers.ChoiceField(choices=['still_there', 'gone'])
