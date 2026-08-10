"""DRF throttle for the atlas sync endpoint."""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle


class AtlasSyncThrottle(SimpleRateThrottle):
    """Rate-limit by pseudonymous session (falls back to client IP), scoped per island."""

    scope = 'atlas_sync'

    def get_cache_key(self, request, view):
        session_id = request.headers.get('X-Session-Id', '').strip()
        island = getattr(request, 'island', None)
        island_key = island.key if island else 'unknown'
        ident = session_id or self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': f'{island_key}:{ident}'}
