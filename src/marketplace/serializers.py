"""Request validation for marketplace v3 writes (service layer builds responses)."""

from __future__ import annotations

from rest_framework import serializers

MAX_SOCIAL_LINKS = 10


class SocialLinkSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=40)
    url = serializers.URLField(max_length=300)


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
    website = serializers.URLField(required=False, allow_blank=True, max_length=300)
    socials = SocialLinkSerializer(many=True, required=False)
    claimed_owner = serializers.BooleanField(required=False, default=False)
    internal_email = serializers.EmailField(required=False, allow_blank=True)
    internal_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
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

        if 'website' in attrs:
            attrs['website'] = (attrs.get('website') or '').strip()

        if 'socials' in attrs:
            raw_socials = attrs.get('socials') or []
            cleaned: list[dict[str, str]] = []
            for entry in raw_socials:
                label = (entry.get('label') or '').strip()
                url = (entry.get('url') or '').strip()
                if not label and not url:
                    continue
                if not label or not url:
                    raise serializers.ValidationError(
                        {'socials': 'Each social link needs a label and a URL.'}
                    )
                cleaned.append({'label': label, 'url': url})
            if len(cleaned) > MAX_SOCIAL_LINKS:
                raise serializers.ValidationError(
                    {'socials': f'At most {MAX_SOCIAL_LINKS} social links allowed.'}
                )
            attrs['socials'] = cleaned
        return attrs


class ReviewWriteSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=128)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(required=False, allow_blank=True, default='')


class ModerateSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['publish', 'reject'])


class ProviderAdminWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False)
    category_slug = serializers.SlugField(required=False, allow_blank=True)
    bio = serializers.CharField(required=False, allow_blank=True)
    hourly_rate = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True
    )
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    whatsapp = serializers.CharField(max_length=32, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True, max_length=300)
    socials = SocialLinkSerializer(many=True, required=False)
    claimed_owner = serializers.BooleanField(required=False)
    internal_email = serializers.EmailField(required=False, allow_blank=True)
    internal_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    is_promoted = serializers.BooleanField(required=False)
    verified_by_owner = serializers.BooleanField(required=False)
    status = serializers.ChoiceField(
        choices=['pending', 'published', 'rejected', 'deleted'],
        required=False,
    )

    def validate(self, attrs: dict) -> dict:
        if 'category_slug' in attrs:
            attrs['category_slug'] = (attrs.get('category_slug') or '').strip()
        if 'website' in attrs:
            attrs['website'] = (attrs.get('website') or '').strip()
        if 'socials' in attrs:
            raw_socials = attrs.get('socials') or []
            cleaned: list[dict[str, str]] = []
            for entry in raw_socials:
                label = (entry.get('label') or '').strip()
                url = (entry.get('url') or '').strip()
                if not label and not url:
                    continue
                if not label or not url:
                    raise serializers.ValidationError(
                        {'socials': 'Each social link needs a label and a URL.'}
                    )
                cleaned.append({'label': label, 'url': url})
            if len(cleaned) > MAX_SOCIAL_LINKS:
                raise serializers.ValidationError(
                    {'socials': f'At most {MAX_SOCIAL_LINKS} social links allowed.'}
                )
            attrs['socials'] = cleaned
        return attrs


class ReviewAdminWriteSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    text = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=['pending', 'published', 'rejected', 'deleted'],
        required=False,
    )


class CategoryAdminWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80, required=False)
    slug = serializers.SlugField(max_length=80, required=False)
    icon = serializers.CharField(max_length=64, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    approve = serializers.BooleanField(required=False, default=False)
