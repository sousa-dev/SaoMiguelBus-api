from rest_framework import serializers

VALID_USER_TYPES = ['tourist', 'resident', 'newcomer']

VALID_INTERESTS = [
    'transit', 'minibus', 'news', 'seismic', 'trails',
    'marketplace', 'traffic', 'events', 'weather',
]

VALID_MUNICIPALITIES = [
    'ponta-delgada', 'ribeira-grande', 'lagoa',
    'vila-franca-do-campo', 'povoacao', 'nordeste',
]


class PersonalizationWriteSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=128)
    user_type = serializers.ChoiceField(choices=VALID_USER_TYPES)
    interests = serializers.ListField(
        child=serializers.ChoiceField(choices=VALID_INTERESTS),
        allow_empty=True,
        max_length=len(VALID_INTERESTS),
    )
    home_municipality = serializers.ChoiceField(
        choices=VALID_MUNICIPALITIES + [''],
        required=False,
        allow_blank=True,
        default='',
    )
