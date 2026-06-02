"""DRF throttle for traffic write endpoints."""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')


class TrafficWriteThrottle(SimpleRateThrottle):
    """Throttle writes per (island, session); reads are never throttled."""

    scope = 'traffic_write'

    def get_cache_key(self, request, view):
        if request.method in SAFE_METHODS:
            return None
        session_id = request.headers.get('X-Session-Id', '').strip()
        if not session_id:
            try:
                session_id = str(request.data.get('session_id', '')).strip()
            except Exception:
                session_id = ''
        island = getattr(request, 'island', None)
        island_key = island.key if island else 'unknown'
        ident = session_id or self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': f'{island_key}:{ident}'}
