"""DRF throttle for AI-assistant-facing endpoints (`/api/v3/ai/*`)."""

from __future__ import annotations

from rest_framework.throttling import ScopedRateThrottle


class AIThrottle(ScopedRateThrottle):
    """Rate-limit `/api/v3/ai/*` per client IP. Scope `ai` (`120/min`, see
    `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`).

    A plain per-IP scope, not the `_SessionScopedThrottle` the rest of the
    codebase uses (`transit/throttling.py`, `minibus/throttling.py`): AI
    assistants (`ChatGPT-User`, `ClaudeBot`, `PerplexityBot`, ...) send no
    `X-Session-Id`, so scoping by session would just fall back to IP anyway
    while adding a lookup that never matches.

    `ScopedRateThrottle.allow_request` reads `view.throttle_scope`, which the
    `@api_view` decorator does NOT copy from the wrapped function the way it
    copies `throttle_classes`/`permission_classes` (see
    `rest_framework.decorators.api_view`). Setting it on the view here, rather
    than requiring every `@api_view` function to remember a class attribute
    that plain functions don't have, keeps the throttle self-contained and
    reusable across both `ai/journeys` and `ai/stops`.
    """

    scope = 'ai'

    def allow_request(self, request, view):
        if not getattr(view, self.scope_attr, None):
            setattr(view, self.scope_attr, self.scope)
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        if not getattr(view, self.scope_attr, None):
            return None
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }
