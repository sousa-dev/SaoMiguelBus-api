from rest_framework import serializers


class ConsentWriteSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=128)
    purposes = serializers.DictField(child=serializers.BooleanField())
    policy_version = serializers.CharField(max_length=32, required=False)
