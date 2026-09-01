"""DRF throttles for AzoresBus live tracking v3 endpoints.

Reuses the minibus session-scoped throttle rather than redefining it: the two
feature sets poll the same vendor through the same Pi, so they should be
rate-limited the same way and drift between them would be a bug.
"""

from __future__ import annotations

from minibus.throttling import _SessionScopedThrottle


class AzoresbusTrackingThrottle(_SessionScopedThrottle):
    scope = 'azoresbus_tracking'
