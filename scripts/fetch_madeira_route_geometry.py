"""OSM route geometry snapshot for the official Madeira and Porto Santo PR trails.

Reads src/trails/data/madeira_official_routes.json. Official route identity, official
page and access status come from Visit Madeira; geometry comes from the OSM route
relation(s) matched to that route by its official reference.

A route may carry more than one relation id when OSM maps the official route as
several signed variants (Porto Santo PR2 is mapped as its west and east approaches);
every matched relation is kept, so what is drawn is still only surveyed OSM geometry.

Nothing is written unless every relation requested in this run yields line geometry
that falls entirely inside its own area's bounds. Existing snapshotted refs are kept,
so the script can be re-run for newly matched routes alone.

Usage:
    python scripts/fetch_madeira_route_geometry.py [ref ...]
"""
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parents[1]
MANIFEST = BASE / 'src/trails/data/madeira_official_routes.json'
OUTPUT = BASE / 'src/trails/data/madeira_route_geometry.json'
USER_AGENT = 'MadeiraOfflineMap/1.0 (info@sousadev.com)'

# (min_lon, max_lon, min_lat, max_lat) per selectable area, generous enough for the
# islets each area covers and tight enough that a mismatched relation cannot pass.
AREA_BOUNDS = {
    'madeira': (-17.50, -16.55, 32.50, 33.00),
    'porto-santo': (-16.45, -16.24, 32.97, 33.15),
    'desertas': (-16.60, -16.40, 32.40, 32.65),
    'selvagens': (-16.10, -15.80, 29.95, 30.25),
}


def relation_lines(relation_id, bounds):
    request = Request(f'https://api.openstreetmap.org/api/0.6/relation/{relation_id}/full',
                      headers={'User-Agent': USER_AGENT})
    with urlopen(request, timeout=35) as response:
        root = ET.fromstring(response.read())
    nodes = {node.attrib['id']: [float(node.attrib['lon']), float(node.attrib['lat'])]
             for node in root.findall('node')}
    ways = {way.attrib['id']: [nd.attrib['ref'] for nd in way.findall('nd')]
            for way in root.findall('way')}
    relation = next((r for r in root.findall('relation') if r.attrib['id'] == str(relation_id)), None)
    if relation is None:
        raise ValueError(f'Relation {relation_id} missing')
    min_lon, max_lon, min_lat, max_lat = bounds
    lines = []
    for member in relation.findall('member'):
        if member.attrib.get('type') != 'way':
            continue
        coords = [nodes[nid] for nid in ways.get(member.attrib['ref'], []) if nid in nodes]
        if len(coords) < 2:
            continue
        if any(not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat) for lon, lat in coords):
            raise ValueError(f'Relation {relation_id} has a coordinate outside its area bounds')
        lines.append(coords)
    if not lines:
        raise ValueError(f'Relation {relation_id} has no complete lines')
    return lines


def main():
    wanted = set(sys.argv[1:])
    routes = json.loads(MANIFEST.read_text())['routes']
    out = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {}
    fetched = 0
    for route in routes:
        relation_ids = route.get('osmRelationIds') or []
        if not relation_ids or (wanted and route['ref'] not in wanted):
            continue
        bounds = AREA_BOUNDS[route['island']]
        lines = []
        for relation_id in relation_ids:
            lines.extend(relation_lines(relation_id, bounds))
            time.sleep(0.25)
        out[route['ref']] = {'type': 'MultiLineString', 'coordinates': lines}
        fetched += 1
        print(route['ref'], len(lines), 'ways', flush=True)

    unmatched = [r['ref'] for r in routes if not r.get('osmRelationIds')]
    if unmatched:
        print(f'Unmatched official routes (no geometry shipped): {", ".join(unmatched)}')

    temp = OUTPUT.with_suffix('.tmp')
    temp.write_text(json.dumps(out, separators=(',', ':')) + '\n')
    temp.replace(OUTPUT)
    print(f'Fetched {fetched} routes; {len(out)} verified route geometries on disk')


if __name__ == '__main__':
    main()
