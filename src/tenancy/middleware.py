"""Resolve active island from incoming requests."""

from __future__ import annotations

import ipaddress
import logging

from django.conf import settings
from django.http import HttpRequest, JsonResponse

from tenancy.context import set_active_island
from tenancy.models import Island

logger = logging.getLogger(__name__)

# Hosts that are not island subdomains (first label of the hostname).
_RESERVED_SUBDOMAINS = frozenset({'www', 'api', 'localhost', '127', 'dashboard'})

# Paths that always use DEFAULT_ISLAND_KEY (never hostname subdomain parsing).
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
        island = None

        if island_key:
            try:
                island = Island.objects.get(key=island_key)
            except Island.DoesNotExist:
                if self._is_non_tenant_path(request):
                    island = None
                else:
                    return JsonResponse(
                        {
                            'error': {
                                'code': 'unknown_island',
                                'message': f'Unknown island: {island_key}',
                            }
                        },
                        status=400,
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
                            'message': f'Island not live: {island_key}',
                        }
                    },
                    status=400,
                )

        request.island = island
        set_active_island(island)
        try:
            return self.get_response(request)
        finally:
            set_active_island(None)

    def _is_non_tenant_path(self, request: HttpRequest) -> bool:
        path = request.path
        return any(path.startswith(prefix) for prefix in _NON_TENANT_PATH_PREFIXES)

    def _default_island_key(self) -> str | None:
        default = getattr(settings, 'DEFAULT_ISLAND_KEY', None)
        return default.lower() if default else None

    def _host_is_ip(self, host: str) -> bool:
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return False

    def _resolve_island_key(self, request: HttpRequest) -> str | None:
        if self._is_non_tenant_path(request):
            return self._default_island_key()

        header = request.headers.get('X-Island') or request.META.get('HTTP_X_ISLAND')
        if header:
            return header.strip().lower()

        host = request.get_host().split(':')[0]
        if not self._host_is_ip(host) and '.' in host:
            subdomain = host.split('.')[0].lower()
            if subdomain not in _RESERVED_SUBDOMAINS and not subdomain.isdigit():
                return subdomain

        query = request.GET.get('island')
        if query:
            return query.strip().lower()

        return self._default_island_key()
