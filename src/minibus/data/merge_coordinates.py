"""Merge official stop coordinates from stops_registry into network_stops JSON."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

# Registry rows with nameShort N/D mapped to our stop keys (line_code, sequence).
ND_STOP_TARGETS: dict[str, tuple[str, int]] = {
    '412': ('D', 12),  # Centro de Radioncologia
    '413': ('D', 13),  # Hospital consultas externas
    '215': ('B', 15),  # Hospital visitas (line B)
    '415': ('D', 15),  # Hospital visitas (line D)
}

# When two registry rows share the same nameShort, prefer this external id.
PREFERRED_EXTERNAL_IDS: dict[tuple[str, int], str] = {
    ('D', 3): '403',  # Santa Clara, not Eng. Abel Ferin Coutinho (426)
}


def stops_registry_path() -> Path:
    return Path(__file__).resolve().parent / 'stops_registry_sao_miguel.json'


def network_stops_path() -> Path:
    return Path(__file__).resolve().parent / 'network_stops_sao_miguel.json'


def load_stops_registry() -> list[dict[str, Any]]:
    with stops_registry_path().open(encoding='utf-8') as handle:
        return json.load(handle)


def load_network_stops() -> dict[str, Any]:
    with network_stops_path().open(encoding='utf-8') as handle:
        return json.load(handle)


def normalize_name(text: str) -> str:
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii').upper()
    return re.sub(r'\s+', ' ', text.strip())


def parse_name_short(name_short: str) -> tuple[str, int] | None:
    parts = name_short.strip().split()
    if len(parts) != 2:
        return None
    line_code, seq_raw = parts
    if line_code == 'N/D' or not line_code.isalpha() or len(line_code) != 1:
        return None
    try:
        return line_code.upper(), int(seq_raw)
    except ValueError:
        return None


def stop_lookup(network: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    lookup: dict[tuple[str, int], dict[str, Any]] = {}
    for line in network['lines']:
        code = line['code']
        for stop in line['stops']:
            lookup[(code, stop['sequence'])] = stop
    return lookup


def registry_coordinate_index(registry: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    """Map (line_code, sequence) -> registry row."""
    index: dict[tuple[str, int], dict[str, Any]] = {}
    duplicates: dict[tuple[str, int], list[str]] = {}

    for row in registry:
        external_id = str(row['id'])
        position = row.get('position') or {}
        lat = position.get('lat')
        lon = position.get('lon')
        if lat is None or lon is None:
            continue

        nd_target = ND_STOP_TARGETS.get(external_id)
        if nd_target is not None:
            index[nd_target] = row
            continue

        parsed = parse_name_short(row.get('nameShort', ''))
        if parsed is None:
            continue

        preferred = PREFERRED_EXTERNAL_IDS.get(parsed)
        if parsed in index:
            duplicates.setdefault(parsed, []).append(external_id)
            if preferred and external_id == preferred:
                index[parsed] = row
            continue

        index[parsed] = row

    return index


def apply_coordinates(network: dict[str, Any], registry: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a new network dict with coordinates merged onto each stop."""
    coord_index = registry_coordinate_index(registry)
    merged = json.loads(json.dumps(network))
    lookup = stop_lookup(merged)

    for line in merged['lines']:
        code = line['code']
        stops = sorted(line['stops'], key=lambda s: s['sequence'])
        first_stop = stops[0] if stops else None
        last_stop = stops[-1] if stops else None

        for stop in line['stops']:
            key = (code, stop['sequence'])
            row = coord_index.get(key)
            if row is not None:
                stop['external_id'] = str(row['id'])
                stop['latitude'] = float(row['position']['lat'])
                stop['longitude'] = float(row['position']['lon'])
            else:
                stop.setdefault('external_id', None)
                stop.setdefault('latitude', None)
                stop.setdefault('longitude', None)

        # Loop terminuses: last stop at same physical place as first (circular lines).
        if first_stop and last_stop and first_stop['key'] != last_stop['key']:
            if first_stop.get('latitude') is not None and last_stop.get('latitude') is None:
                last_stop['external_id'] = first_stop.get('external_id')
                last_stop['latitude'] = first_stop['latitude']
                last_stop['longitude'] = first_stop['longitude']

    return merged


def validate_network_coordinates(network: dict[str, Any]) -> list[str]:
    """Return human-readable errors for stops missing coordinates."""
    errors: list[str] = []
    for line in network['lines']:
        for stop in line['stops']:
            if stop.get('latitude') is None or stop.get('longitude') is None:
                errors.append(f"{line['code']} seq {stop['sequence']} ({stop['key']}): missing coordinates")
    return errors


def merge_report(registry: list[dict[str, Any]], network: dict[str, Any]) -> dict[str, Any]:
    coord_index = registry_coordinate_index(registry)
    lookup = stop_lookup(network)
    matched_keys = set(coord_index.keys())
    routable_keys = set(lookup.keys())

    unmatched_registry: list[str] = []
    for row in registry:
        external_id = str(row['id'])
        if external_id in ND_STOP_TARGETS:
            target = ND_STOP_TARGETS[external_id]
            if target not in routable_keys:
                unmatched_registry.append(external_id)
            continue
        parsed = parse_name_short(row.get('nameShort', ''))
        if parsed is None:
            unmatched_registry.append(external_id)
            continue
        if parsed not in routable_keys and external_id not in {v for v in PREFERRED_EXTERNAL_IDS.values()}:
            if parsed not in matched_keys or PREFERRED_EXTERNAL_IDS.get(parsed) != external_id:
                unmatched_registry.append(external_id)

    # Registry rows not on the route graph (informational).
    skipped_not_on_route = [str(r['id']) for r in registry if str(r['id']) in {'321', '322', '426'}]

    return {
        'registry_count': len(registry),
        'routable_stops': len(routable_keys),
        'coordinate_mappings': len(coord_index),
        'skipped_not_on_route': skipped_not_on_route,
        'unmatched_registry_ids': unmatched_registry,
        'validation_errors': validate_network_coordinates(apply_coordinates(network, registry)),
    }


def write_merged_network(*, dry_run: bool = False) -> dict[str, Any]:
    registry = load_stops_registry()
    network = load_network_stops()
    report = merge_report(registry, network)
    merged = apply_coordinates(network, registry)

    if not dry_run:
        with network_stops_path().open('w', encoding='utf-8') as handle:
            json.dump(merged, handle, ensure_ascii=False, indent=2)
            handle.write('\n')

    report['written'] = not dry_run
    return report


if __name__ == '__main__':
    import sys

    dry = '--dry-run' in sys.argv
    result = write_merged_network(dry_run=dry)
    print(json.dumps(result, indent=2))
    if result['validation_errors']:
        raise SystemExit(1)
