"""Pluggable AI enrichment provider interface (SDD 02 §5.2.3, 00 D16).

No model/provider is chosen yet — this SDD specifies field ownership, the merge-safety rule
against the monthly OSM importer, and the safety-review publish gate, but not the enrichment
implementation itself (see HANDOVER.md). `NullEnrichmentProvider` is the default: it does
nothing, so `enrich_atlas_pois` is safe to run in dev and in CI without an LLM configured.
Wire a real provider by setting `ATLAS_ENRICHMENT_PROVIDER` in settings to a dotted path.

A real provider MUST ground its prompt in the POI's actual tags/description (SDD 07 §6) rather
than name+coordinates alone, and MUST NOT be trusted to gate its own safety-critical output —
that gate is enforced structurally by the DB constraint on AtlasPoi.is_published, not by the
provider being careful.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from atlas.models import AtlasPoi

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class EnrichmentResult:
    description: dict[str, str] = dataclasses.field(default_factory=dict)
    tips: dict[str, Any] = dataclasses.field(default_factory=dict)
    media: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    accessibility: dict[str, Any] = dataclasses.field(default_factory=dict)


class EnrichmentProvider:
    """Subclass and set `model_name`; implement `enrich()`."""

    model_name: str = ''

    def enrich(self, poi: AtlasPoi) -> EnrichmentResult | None:
        """Return None to skip a row this run (e.g. rate limit, low-confidence output)."""
        raise NotImplementedError


class NullEnrichmentProvider(EnrichmentProvider):
    """Default: does nothing. Lets the pipeline scaffolding (field ownership, safety gate,
    merge-safety against the OSM importer) run and be tested before a real provider exists."""

    model_name = 'null'

    def enrich(self, poi: AtlasPoi) -> EnrichmentResult | None:
        logger.debug('NullEnrichmentProvider: skipping %s (no provider configured)', poi.uid)
        return None


def load_provider() -> EnrichmentProvider:
    from django.conf import settings
    from django.utils.module_loading import import_string

    dotted_path = getattr(settings, 'ATLAS_ENRICHMENT_PROVIDER', None)
    if not dotted_path:
        return NullEnrichmentProvider()
    provider_cls = import_string(dotted_path)
    return provider_cls()
