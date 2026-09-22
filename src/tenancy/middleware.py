"""Resolve active island from incoming requests."""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpRequest, JsonResponse

from tenancy.context import set_active_island
from tenancy.models import Island

logger = logging.getLogger(__name__)

# Paths that always use DEFAULT_ISLAND_KEY.
_NON_TENANT_PATH_PREFIXES = (
    '/dashboard/',
    '/accounts/',
    '/legal/',
    '/payment/',
    '/static/',
    '/media/',
)


class TenantMiddleware:
    """Bind request.island and the contextvar used by TenantManager."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        island_key = self._resolve_island_key(request)
        island = self._load_island(island_key)

        if (
            island is not None
            and island_key
            and island.key != island_key
        ):
            logger.info(
                'Unknown island %r — using default %r',
                island_key,
                island.key,
            )

        if (
            island is not None
            and not island.is_live
            and not getattr(settings, 'ALLOW_INACTIVE_ISLANDS', False)
            and not self._is_non_tenant_path(request)
        ):
            return JsonResponse(
                {
                    'error': {
                        'code': 'island_not_live',
                        'message': f'Island not live: {island.key}',
                    }
                },
                status=400,
            )

        # Offline-map endpoints must never answer an explicit unknown island with
        # São Miguel's catalogue or forecast. Other legacy endpoints keep their fallback.
        #
        # Only an *explicit* key is held to this: normalised the same way
        # _resolve_island_key does it, so a blank header counts as no header rather than
        # being refused as "Unknown island: " with nothing named, and so a deployment whose
        # configured default island is missing does not start refusing header-less requests.
        explicit_key = (request.headers.get('X-Island') or request.GET.get('island') or '').strip().lower()
        strict_paths = ('/api/v3/atlas/', '/api/v3/trails/', '/api/v3/weather/')
        if explicit_key and request.path.startswith(strict_paths) and (island is None or explicit_key != island.key):
            return JsonResponse({'error': {'code': 'unknown_island', 'message': f'Unknown island: {island_key}'}}, status=400)

        request.island = island
        set_active_island(island)
        try:
            return self.get_response(request)
        finally:
            set_active_island(None)

    def _is_non_tenant_path(self, request: HttpRequest) -> bool:
        path = request.path
        return any(path.startswith(prefix) for prefix in _NON_TENANT_PATH_PREFIXES)

    def _default_island_key(self) -> str:
        return getattr(settings, 'DEFAULT_ISLAND_KEY', 'sao-miguel').lower()

    def _load_island(self, island_key: str | None) -> Island | None:
        if not island_key:
            island_key = self._default_island_key()

        try:
            return Island.objects.get(key=island_key)
        except Island.DoesNotExist:
            default_key = self._default_island_key()
            if island_key == default_key:
                return None
            try:
                return Island.objects.get(key=default_key)
            except Island.DoesNotExist:
                return None

    def _resolve_island_key(self, request: HttpRequest) -> str | None:
        """Island from explicit header/query only — never from hostname."""
        if self._is_non_tenant_path(request):
            return self._default_island_key()

        header = request.headers.get('X-Island') or request.META.get('HTTP_X_ISLAND')
        if header:
            return header.strip().lower()

        query = request.GET.get('island')
        if query:
            return query.strip().lower()

        return self._default_island_key()
