"""Request validation for marketplace v3 writes (service layer builds responses)."""

from __future__ import annotations

from rest_framework import serializers


class ProviderWriteSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=128)
    name = serializers.CharField(max_length=160, required=False)
    category_slug = serializers.SlugField(required=False, allow_blank=True)
    category_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    bio = serializers.CharField(required=False, allow_blank=True)
    hourly_rate = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True
    )
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    whatsapp = serializers.CharField(max_length=32, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)

    def validate(self, attrs: dict) -> dict:
        slug = (attrs.get('category_slug') or '').strip()
        name = (attrs.get('category_name') or '').strip()
        if slug and name:
            raise serializers.ValidationError(
                'Provide category_slug or category_name, not both.'
            )
        if slug:
            attrs['category_slug'] = slug
        if name:
            attrs['category_name'] = name
        return attrs


class ReviewWriteSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=128)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(required=False, allow_blank=True, default='')


class ModerateSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['publish', 'reject'])
