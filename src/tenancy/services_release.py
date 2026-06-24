"""Mobile app release / update-check helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from django.conf import settings

from packaging.version import InvalidVersion, Version

from tenancy.models import AppReleaseConfig, Island

logger = logging.getLogger(__name__)

AppPlatform = Literal['ios', 'android']
UpdateMode = Literal['optional', 'required']


class ReleaseValidationError(ValueError):
    """Invalid platform or client version for update check."""


@dataclass(frozen=True)
class ReleaseConfig:
    current_version: str
    update_mode: UpdateMode
    store_url: str


def env_release_defaults() -> dict[str, str]:
    """Bootstrap values for new AppReleaseConfig rows (from env / settings defaults)."""
    return {
        'ios_current_version': settings.APP_RELEASE_IOS_VERSION,
        'android_current_version': settings.APP_RELEASE_ANDROID_VERSION,
        'ios_update_mode': settings.APP_UPDATE_IOS_MODE,
        'android_update_mode': settings.APP_UPDATE_ANDROID_MODE,
        'ios_store_url': settings.APP_STORE_IOS_URL,
        'android_store_url': settings.APP_STORE_ANDROID_URL,
    }


def get_or_create_app_release_config(island: Island) -> AppReleaseConfig:
    config, _ = AppReleaseConfig.objects.get_or_create(
        island=island,
        defaults=env_release_defaults(),
    )
    return config


def normalize_platform(platform: str) -> AppPlatform:
    normalized = (platform or '').strip().lower()
    if normalized not in ('ios', 'android'):
        raise ReleaseValidationError(f'Unsupported platform: {platform!r}')
    return normalized  # type: ignore[return-value]


def get_release_config(platform: AppPlatform, *, island: Island) -> ReleaseConfig:
    config = get_or_create_app_release_config(island)
    if platform == 'ios':
        return ReleaseConfig(
            current_version=config.ios_current_version,
            update_mode=config.ios_update_mode,  # type: ignore[arg-type]
            store_url=config.ios_store_url,
        )
    return ReleaseConfig(
        current_version=config.android_current_version,
        update_mode=config.android_update_mode,  # type: ignore[arg-type]
        store_url=config.android_store_url,
    )


def _parse_version(label: str, value: str) -> Version | None:
    try:
        return Version(value.strip())
    except InvalidVersion:
        logger.warning('Invalid %s version string: %r', label, value)
        return None


def build_update_check(platform: str, client_version: str, *, island: Island) -> dict:
    """Compare client semver to configured release; return API payload."""
    normalized_platform = normalize_platform(platform)
    client = (client_version or '').strip()
    if not client:
        raise ReleaseValidationError('version query parameter is required')

    release = get_release_config(normalized_platform, island=island)
    client_parsed = _parse_version('client', client)
    current_parsed = _parse_version('current', release.current_version)

    payload: dict = {
        'updateRequired': False,
        'currentVersion': release.current_version,
        'clientVersion': client,
    }

    if client_parsed is None or current_parsed is None:
        return payload

    if client_parsed < current_parsed:
        payload['updateRequired'] = True
        payload['updateMode'] = release.update_mode
        payload['storeUrl'] = release.store_url

    return payload
