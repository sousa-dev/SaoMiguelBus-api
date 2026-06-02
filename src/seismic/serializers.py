"""Seismic v3 request serializers."""

from __future__ import annotations

from rest_framework import serializers


class FeltReportSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=128)
    felt = serializers.BooleanField()
    intensity = serializers.IntegerField(
        min_value=1, max_value=12, required=False, allow_null=True
    )
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
