"""DRF throttles for minibus live tracking v3 endpoints."""

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


class MinibusTrackingThrottle(_SessionScopedThrottle):
    scope = 'minibus_tracking'
