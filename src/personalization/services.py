"""Personalization profile read/write for v3 API."""

from __future__ import annotations

from consent.services import hash_session_id  # reuse — keeps hashes aligned with DSAR

from personalization.models import PersonalizationProfile


def save_profile(
    *,
    session_hash: str,
    user_type: str,
    interests: list[str],
    home_municipality: str = '',
    platform: str | None = None,
    user=None,
) -> PersonalizationProfile:
    defaults: dict = {
        'user': user,
        'user_type': user_type,
        'interests': interests,
        'home_municipality': home_municipality,
    }
    if platform is not None:
        defaults['platform'] = platform
    return PersonalizationProfile.objects.update_or_create(
        session_hash=session_hash,
        defaults=defaults,
    )[0]


def get_latest_profile(*, session_hash: str) -> PersonalizationProfile | None:
    if not session_hash:
        return None
    return (
        PersonalizationProfile.objects.filter(session_hash=session_hash)
        .order_by('-updated_at')
        .first()
    )


def serialize_profile(record: PersonalizationProfile | None) -> dict:
    if record is None:
        return {
            'user_type': None,
            'interests': [],
            'home_municipality': '',
            'platform': '',
            'updated_at': None,
        }
    return {
        'user_type': record.user_type,
        'interests': record.interests,
        'home_municipality': record.home_municipality,
        'platform': record.platform,
        'updated_at': record.updated_at.isoformat() if record.updated_at else None,
    }


__all__ = ['hash_session_id', 'save_profile', 'get_latest_profile', 'serialize_profile']
