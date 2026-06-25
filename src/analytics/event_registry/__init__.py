"""Per-module analytics event property validation at ingest."""

from __future__ import annotations

from typing import Any

from analytics.models import AnalyticsEvent

from analytics.event_registry.minibus import validate_minibus_event


def validate_event(
    module: str,
    event_type: str,
    properties: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Validate and normalize event properties for registered modules.

    Returns (cleaned_properties, drop_reason). When drop_reason is set,
    the event must not be stored.
    """
    if module != AnalyticsEvent.MODULE_MINIBUS:
        return properties, None

    return validate_minibus_event(event_type, properties)
