"""DRF throttles for transit v3 endpoints."""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle


class _SessionScopedThrottle(SimpleRateThrottle):
    """Rate-limit by pseudonymous session (falls back to client IP), scoped per island."""

    def get_cache_key(self, request, view):
        session_id = (
            request.GET.get('session_id', '').strip()
            or request.headers.get('X-Session-Id', '').strip()
        )
        island = getattr(request, 'island', None)
        island_key = island.key if island else 'unknown'
        ident = session_id or self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': f'{island_key}:{ident}'}


class DirectionsSessionThrottle(_SessionScopedThrottle):
    scope = 'directions'


class OfflineBundleThrottle(_SessionScopedThrottle):
    """Rate-limit offline-bundle downloads (large payload) per session/IP."""

    scope = 'offline-bundle'


class LiveCountsThrottle(_SessionScopedThrottle):
    """Rate-limit the shared live vehicle-count endpoint per session/IP."""

    scope = 'live_counts'
