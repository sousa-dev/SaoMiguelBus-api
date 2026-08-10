"""PDL urban network stops from our own minibus data (SDD 07 §4).

minibus has no Stop model — its network stops live in a bundled JSON registry
(minibus/data/network_stops_sao_miguel.json), merged with line metadata at request time.
Reading that file directly is still a same-repo, no-HTTP read; it's just a file instead of a
table. Only applies to São Miguel — the PDL urban network doesn't exist on other islands.
"""

from __future__ import annotations

from typing import Iterator

from atlas.importers.base import BaseImporter, ImportRow
from atlas.models import AtlasPoi
from minibus.services import load_network_stops


class MinibusImporter(BaseImporter):
    SOURCE = AtlasPoi.SOURCE_MINIBUS

    def rows(self) -> Iterator[ImportRow]:
        if self.island.key != 'sao-miguel':
            return

        try:
            network = load_network_stops()
        except FileNotFoundError:
            return

        seen_external_ids: set[str] = set()
        for line in network.get('lines', []):
            for stop in line.get('stops', []):
                external_id = stop.get('external_id')
                if not external_id or external_id in seen_external_ids:
                    continue
                seen_external_ids.add(external_id)
                name_pt = stop.get('name_pt', '')
                yield ImportRow(
                    ref=external_id,
                    name={'pt': name_pt, 'en': name_pt},
                    latitude=stop['latitude'],
                    longitude=stop['longitude'],
                    category_slug='bus-stop',
                    kind=AtlasPoi.KIND_POI,
                    tier=AtlasPoi.TIER_STANDARD,
                    external_refs={'minibusExternalId': external_id},
                )
