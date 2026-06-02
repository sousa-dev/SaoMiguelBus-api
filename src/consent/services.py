"""Consent read/write for v3 API."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from django.conf import settings
from django.utils import timezone

from consent.models import ConsentRecord

CONSENT_POLICY_VERSION = '1.0.0'

DEFAULT_PURPOSES = {
    'strictly_necessary': True,
    'analytics': False,
    'ads': False,
    'personalization': False,
}


def hash_session_id(raw_session_id: str, island_key: str) -> str:
    """Pseudonymous session hash for consent + analytics."""
    secret = settings.SECRET_KEY.encode()
    payload = f'{raw_session_id}:{island_key}'.encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def normalize_purposes(purposes: dict[str, Any] | None) -> dict[str, bool]:
    merged = {**DEFAULT_PURPOSES}
    if purposes:
        for key, value in purposes.items():
            if key in merged and isinstance(value, bool):
                merged[key] = value
    merged['strictly_necessary'] = True
    return merged


def get_latest_consent(*, session_hash: str) -> ConsentRecord | None:
    if not session_hash:
        return None
    return (
        ConsentRecord.objects.filter(session_hash=session_hash, withdrawn_at__isnull=True)
        .order_by('-granted_at')
        .first()
    )


def save_consent(
    *,
    session_hash: str,
    purposes: dict[str, bool],
    policy_version: str | None = None,
    user=None,
) -> ConsentRecord:
    normalized = normalize_purposes(purposes)
    version = policy_version or CONSENT_POLICY_VERSION

    ConsentRecord.objects.filter(
        session_hash=session_hash,
        withdrawn_at__isnull=True,
    ).update(withdrawn_at=timezone.now())

    return ConsentRecord.objects.create(
        user=user,
        session_hash=session_hash,
        purposes=normalized,
        policy_version=version,
    )


def serialize_consent(record: ConsentRecord | None) -> dict:
    if record is None:
        return {
            'purposes': DEFAULT_PURPOSES,
            'policy_version': CONSENT_POLICY_VERSION,
            'granted_at': None,
        }
    return {
        'purposes': record.purposes,
        'policy_version': record.policy_version,
        'granted_at': record.granted_at.isoformat() if record.granted_at else None,
    }
