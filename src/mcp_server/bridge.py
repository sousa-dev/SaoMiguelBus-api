from __future__ import annotations

from functools import partial
from typing import Callable

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections

from mcp_server.errors import error
from tenancy.models import Island
from tenancy.services import for_island


def resolve_island_sync(island_key: str | None):
    key = (island_key or settings.DEFAULT_ISLAND_KEY).strip()
    island = Island.objects.filter(key=key).first()
    if island is None:
        return error('unknown_island', f'Unknown island: {key}')
    if not island.is_live:
        return error('island_not_live', f'Island is not live: {key}')
    return island


def _run_sync(fn: Callable, island_key: str | None, args: tuple, kwargs: dict):
    close_old_connections()
    try:
        island = resolve_island_sync(island_key)
        if isinstance(island, dict):
            return island
        with for_island(island):
            return fn(island, *args, **kwargs)
    except ValueError as exc:
        return error('invalid_request', str(exc))
    except Exception:  # noqa: BLE001 - public tools return stable errors
        return error('internal_error', 'The requested data could not be loaded')
    finally:
        close_old_connections()


async def run_in_island(fn: Callable, island_key: str | None, *args, **kwargs):
    return await sync_to_async(_run_sync, thread_sensitive=False)(fn, island_key, args, kwargs)