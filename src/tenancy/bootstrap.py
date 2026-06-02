"""Island bootstrap payload for v3 clients."""

from __future__ import annotations

from django.utils import timezone

from consent.services import CONSENT_POLICY_VERSION
from tenancy.models import Island
from transit.models import Holiday
from transit.services.compat import _serialize_active_infos


MODULE_KEYS = (
    'transit',
    'news',
    'seismic',
    'marketplace',
    'trails',
    'traffic',
    'events',
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
        'holidays': holidays,
        'infos': _serialize_active_infos(),
        'generatedAt': timezone.now().isoformat(),
    }
