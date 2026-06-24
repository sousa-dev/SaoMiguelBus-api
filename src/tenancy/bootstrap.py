"""Island bootstrap payload for v3 clients."""

from __future__ import annotations

from django.utils import timezone

from consent.services import CONSENT_POLICY_VERSION
from tenancy.models import Island
from tenancy.services_release import get_or_create_app_release_config
from transit.models import Holiday
from transit.services.compat import _serialize_active_infos
from user_management.social import social_auth_capabilities


MODULE_KEYS = (
    'transit',
    'news',
    'seismic',
    'marketplace',
    'trails',
    'traffic',
    'events',
    'weather',
    'minibus',
)


def enabled_modules(island: Island) -> list[str]:
    flags = island.feature_flags or {}
    return [key for key in MODULE_KEYS if flags.get(key, False)]


def serialize_bootstrap(island: Island) -> dict:
    theme = island.theme or {}
    flags = island.feature_flags or {}
    holidays = [
        {'id': h.id, 'date': h.date.isoformat(), 'name': h.name}
        for h in Holiday.objects.all().order_by('date')
    ]

    release = get_or_create_app_release_config(island)

    return {
        'island': {
            'key': island.key,
            'name': island.name,
            'archipelago': island.archipelago,
            'defaultLocale': island.default_locale,
            'locales': island.locales or [],
            'timezone': island.timezone,
            'theme': {
                'primaryColor': theme.get('primaryColor', '#218732'),
                'secondaryColor': theme.get('secondaryColor', '#343434'),
                'accentColor': theme.get('accentColor', '#ffc107'),
            },
            'mapCenter': {
                'lat': island.center_lat,
                'lng': island.center_lng,
            },
            'radiusKm': island.radius_km,
            'enabledModules': enabled_modules(island),
        },
        'version': flags.get('version', '6.0.0'),
        'mapsEnabled': bool(flags.get('maps', False)),
        'consentPolicyVersion': flags.get('consentPolicyVersion', CONSENT_POLICY_VERSION),
        'inAppReviewEnabled': bool(release.in_app_review_enabled),
        'storeUrls': {
            'ios': release.ios_store_url,
            'android': release.android_store_url,
        },
        'socialAuth': social_auth_capabilities(),
        'holidays': holidays,
        'infos': _serialize_active_infos(),
        'generatedAt': timezone.now().isoformat(),
    }
