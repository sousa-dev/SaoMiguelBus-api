"""Tenancy helpers for imports and services."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from tenancy.context import get_active_island, set_active_island
from tenancy.models import Island


def get_or_create_default_island(key: str = 'sao-miguel') -> Island:
    """Ensure the default São Miguel island exists."""
    defaults = Island.default_sao_miguel()
    island, _ = Island.objects.update_or_create(key=key, defaults=defaults)
    return island


@contextmanager
def for_island(island: Island) -> Iterator[Island]:
    """Temporarily bind an island for management commands and Celery tasks."""
    previous = get_active_island()
    set_active_island(island)
    try:
        yield island
    finally:
        set_active_island(previous)
