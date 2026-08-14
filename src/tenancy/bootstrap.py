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


def serialize_transit_schedule(island: Island) -> dict:
    """Which network is active, and when that stops being true.

    New serialization work, not a flag pass-through: bootstrap emits modules
    plus maps/version and does not expose arbitrary nested feature_flags
    (98 §6). Every field here is one admin edit away from changing, which is
    what makes a rollback an edit rather than a deploy.
    """
    from transit.services.schedule_phase import (
        DATASET_AZORESBUS,
        PHASE_PREVIEW,
        azoresbus_flags,
        cutover_at,
        next_transition_at,
        resolve_dataset,
        schedule_phase,
    )

    flags = azoresbus_flags(island)
    phase = schedule_phase(island)
    cutover = cutover_at(island)
    transition = next_transition_at(island)

    # The preview toggle only exists while there is something to preview.
    preview = (
        DATASET_AZORESBUS
        if phase == PHASE_PREVIEW and flags.get('previewEnabled')
        else None
    )

    return {
        'activeDataset': resolve_dataset(island),
        'previewDataset': preview,
        # Instants, not calendar dates: a date comparison flips at Lisbon
        # midnight for a tourist whose phone is still on WET/CEST.
        'cutoverAt': cutover.isoformat() if cutover else None,
        # The app persists bootstrap for 24h and never refetches it, so without
        # this it cannot know when its cached copy became a lie.
        'nextTransitionAt': transition.isoformat() if transition else None,
        'phase': phase,
        'banner': flags.get('banner'),
        'badge': flags.get('badge'),
        'trackingEnabled': bool(flags.get('trackingEnabled', False)),
    }


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
        'transitSchedule': serialize_transit_schedule(island),
        'infos': _serialize_active_infos(),
        'generatedAt': timezone.now().isoformat(),
    }
