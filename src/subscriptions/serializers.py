from rest_framework import serializers
from .models import Subscription

class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ['id', 'email', 'is_active', 'verification_count', 'created_at', 'updated_at']

class SubscriptionVerificationRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    create_subscription = serializers.CharField(required=False, max_length=128, allow_blank=True)
    
    def validate_email(self, value):
        """Validate email format and basic checks"""
        if not value or len(value.strip()) == 0:
            raise serializers.ValidationError("Email is required")
        return value.strip().lower()

class SubscriptionVerificationResponseSerializer(serializers.Serializer):
    hasActiveSubscription = serializers.BooleanField()
    subscriptionType = serializers.CharField(allow_null=True)
    expiresAt = serializers.CharField(allow_null=True)
    features = serializers.ListField(child=serializers.CharField(), default=list)
    message = serializers.CharField(allow_null=True) 