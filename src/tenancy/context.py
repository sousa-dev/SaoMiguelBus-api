"""Request-scoped active island context."""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenancy.models import Island

_active_island: ContextVar[Island | None] = ContextVar('active_island', default=None)


def get_active_island() -> Island | None:
    """Return the island bound to the current request or task context."""
    return _active_island.get()


def set_active_island(island: Island | None) -> None:
    """Bind an island to the current context."""
    _active_island.set(island)
