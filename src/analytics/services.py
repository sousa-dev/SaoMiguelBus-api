"""Legacy stat ingestion for compat shim."""

from __future__ import annotations

from analytics.models import Stat


def ingest_legacy_stat(
    *,
    request: str,
    origin: str = '',
    destination: str = '',
    day: str = 'NA',
    time: str = 'NA',
    platform: str = 'NA',
    language: str = 'NA',
) -> None:
    Stat.objects.create(
        request=request or 'NA',
        origin=origin or '',
        destination=destination or '',
        type_of_day=day or 'NA',
        time=time or 'NA',
        platform=platform or 'NA',
        language=language or 'NA',
    )
