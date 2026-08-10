"""Importer registry consumed by `manage.py import_atlas --source <name>`.

`enrich_atlas_pois` is deliberately not here — it isn't an importer, doesn't own a `source`,
and runs against rows any importer produced. See atlas/management/commands/enrich_atlas_pois.py.
"""

from __future__ import annotations

from atlas.importers.curated import CuratedImporter
from atlas.importers.minibus import MinibusImporter
from atlas.importers.osm import OsmImporter
from atlas.importers.trails import TrailsImporter
from atlas.importers.transit import TransitImporter

IMPORTER_REGISTRY = {
    'curated': CuratedImporter,
    'transit': TransitImporter,
    'minibus': MinibusImporter,
    'trails': TrailsImporter,
    'osm': OsmImporter,
}
