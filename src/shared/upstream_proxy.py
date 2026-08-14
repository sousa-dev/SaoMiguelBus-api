"""Route upstream calls through the Tailscale Pi, or direct.

Cloudflare blocks our datacenter egress on `pdl.elevensystems.pt`, and `azb` is
behind Cloudflare too, so both integrations reach upstream through a Pi at home.

The proxy contract sends the TARGET HOST and the FULL UPSTREAM PATH, rather than
baking a per-service path mapping into the Pi:

    GET  {PROXY}/publicapi/locations
    X-Upstream-Host: https://pdl.elevensystems.pt
    X-Tracking-Proxy-Key: <shared secret>

One Pi therefore serves any number of upstreams with no config change when a new
one appears — adding AzoresBus needs no `/azb/* -> /api/*` rule, which 98 §5
challenge 5 correctly called real ops work rather than a config toggle.

With no proxy configured, calls go direct to the upstream host, so local
development and tests need no Pi.
"""

from __future__ import annotations

from decouple import config


# The Pi. Empty => go direct.
UPSTREAM_PROXY_URL = config('UPSTREAM_PROXY_URL', default='').rstrip('/')
UPSTREAM_PROXY_KEY = config('UPSTREAM_PROXY_KEY', default='')

HOST_HEADER = 'X-Upstream-Host'
KEY_HEADER = 'X-Tracking-Proxy-Key'


def build_request(
    upstream_base: str,
    path: str,
    *,
    proxy_url: str | None = None,
    proxy_key: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Return (url, headers) for one upstream call.

    `upstream_base` is the real origin plus any base path
    (``https://pdl.elevensystems.pt/publicapi``); `path` is appended to it
    (``/locations``). When a proxy is configured the origin moves to a header and
    the full path is preserved, so the Pi can forward verbatim.
    """
    proxy = UPSTREAM_PROXY_URL if proxy_url is None else proxy_url.rstrip('/')
    key = UPSTREAM_PROXY_KEY if proxy_key is None else proxy_key

    upstream_base = upstream_base.rstrip('/')
    if not path.startswith('/'):
        path = f'/{path}'

    if not proxy:
        return f'{upstream_base}{path}', {}

    origin, base_path = split_origin(upstream_base)
    headers = {HOST_HEADER: origin}
    if key:
        headers[KEY_HEADER] = key
    return f'{proxy}{base_path}{path}', headers


def split_origin(url: str) -> tuple[str, str]:
    """('https://host.tld/base/path') -> ('https://host.tld', '/base/path')."""
    scheme, _, rest = url.partition('://')
    if not rest:
        scheme, rest = 'https', url
    host, slash, tail = rest.partition('/')
    return f'{scheme}://{host}', f'{slash}{tail}'.rstrip('/') if slash else ''
