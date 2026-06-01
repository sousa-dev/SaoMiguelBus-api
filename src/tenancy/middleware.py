"""Resolve active island from incoming requests."""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpRequest, JsonResponse

from tenancy.context import set_active_island
from tenancy.models import Island

logger = logging.getLogger(__name__)


class TenantMiddleware:
    """Bind request.island and the contextvar used by TenantManager."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        island_key = self._resolve_island_key(request)
        island = None

        if island_key:
            try:
                island = Island.objects.get(key=island_key)
            except Island.DoesNotExist:
                return JsonResponse(
                    {'error': {'code': 'unknown_island', 'message': f'Unknown island: {island_key}'}},
                    status=400,
                )
            if not island.is_live and not getattr(settings, 'ALLOW_INACTIVE_ISLANDS', False):
                return JsonResponse(
                    {'error': {'code': 'island_not_live', 'message': f'Island not live: {island_key}'}},
                    status=400,
                )

        request.island = island
        set_active_island(island)
        try:
            return self.get_response(request)
        finally:
            set_active_island(None)

    def _resolve_island_key(self, request: HttpRequest) -> str | None:
        header = request.headers.get('X-Island') or request.META.get('HTTP_X_ISLAND')
        if header:
            return header.strip().lower()

        host = request.get_host().split(':')[0]
        if '.' in host:
            subdomain = host.split('.')[0]
            if subdomain not in {'www', 'api', 'localhost', '127'}:
                return subdomain.lower()

        query = request.GET.get('island')
        if query:
            return query.strip().lower()

        default = getattr(settings, 'DEFAULT_ISLAND_KEY', None)
        return default.lower() if default else None
