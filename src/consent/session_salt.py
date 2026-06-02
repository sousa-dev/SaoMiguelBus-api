"""Rotating salt for analytics session pseudonymization."""

from __future__ import annotations

import secrets

from django.core.cache import cache

SESSION_SALT_CACHE_KEY = 'consent:session_hash_salt'
SESSION_SALT_TTL_SECONDS = 60 * 60 * 48  # keep previous salt briefly after rotation


def get_session_salt() -> str:
    salt = cache.get(SESSION_SALT_CACHE_KEY)
    if salt:
        return salt
    salt = secrets.token_hex(16)
    cache.set(SESSION_SALT_CACHE_KEY, salt, timeout=None)
    return salt


def rotate_session_salt() -> str:
    salt = secrets.token_hex(16)
    cache.set(SESSION_SALT_CACHE_KEY, salt, timeout=None)
    return salt
