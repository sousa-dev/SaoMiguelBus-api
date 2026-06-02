from rest_framework import serializers


class AnalyticsEventItemSerializer(serializers.Serializer):
    module = serializers.CharField(max_length=32)
    event_type = serializers.CharField(max_length=32)
    properties = serializers.DictField(required=False, default=dict)
    occurred_at = serializers.DateTimeField(required=False)


class AnalyticsEventsBatchSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=128)
    platform = serializers.ChoiceField(
        choices=['android', 'ios', 'web'],
        default='web',
    )
    locale = serializers.CharField(max_length=8, required=False)
    app_version = serializers.CharField(max_length=32, required=False, allow_blank=True)
    events = AnalyticsEventItemSerializer(many=True, min_length=1, max_length=50)
