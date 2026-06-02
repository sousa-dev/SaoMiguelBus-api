"""Seismic v3 request serializers."""

from __future__ import annotations

from rest_framework import serializers


class FeltReportSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=128)
    intensity = serializers.IntegerField(min_value=1, max_value=12)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
