"""Two different groupings of AzoresBus stop names — do not conflate them.

`collapse_stops` merges 1456 upstream POLES into 816 `transit.Stop` rows by
EXACT name, at IMPORT time: both sides of a road sharing one name. Upstream
models each pole separately: 630 names carry two codes, 5 carry three. They are
the two sides of a road — median 11.5 m apart, 629 of 630 pairs with
consecutive integer codes — so offering both to a picker asks the user a
question they cannot answer. Which pole a trip serves is a property of its
direction, not a search input (02 §3.2). One `transit.Stop` per distinct name,
positioned at the centroid, with full upstream identity kept in `ExternalStop`
so results can still show the pole code and put the boarding marker on the
correct side of the road.

`derive_area_key` / `build_area_index` group those already-collapsed 816 names
by a shared VILLAGE PREFIX, at SEARCH time: "CAPELAS (IGREJA)", "CAPELAS
(MOAGEM)" and 33 others share the key "CAPELAS", so a search for "Capelas" can
union every stop in the village rather than requiring the exact landmark. A
completely different axis from the pole-collapse above — this never merges two
`Stop` rows into one, it only tells search which several to consider together.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from transit.services.legacy_import import clean_string


EARTH_RADIUS_M = 6_371_000.0

# Groups spanning more than this get flagged for review at import. Expect 14
# (98 §3 measured 14, not the 30 an earlier draft claimed).
FLAG_SPAN_M = 75.0

# Above this, the collapse is worth surfacing to the user as a walking-distance
# hint on the result card rather than a second picker row. Expect 3.
HINT_SPAN_M = 100.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass
class StopGroupResult:
    """One collapsed place, and the poles it was built from."""

    name: str
    latitude: float
    longitude: float
    span_m: float
    members: list[dict] = field(default_factory=list)

    @property
    def needs_walking_hint(self) -> bool:
        """Covoada spans 164 m; a user sent to the centroid deserves warning."""
        return self.span_m > HINT_SPAN_M


@dataclass
class CollapseResult:
    groups: list[StopGroupResult] = field(default_factory=list)
    flagged: list[StopGroupResult] = field(default_factory=list)


def collapse_stops(stops: list[dict]) -> CollapseResult:
    """Group upstream stops by exact name; position each group at its centroid.

    Grouping is by name rather than proximity on purpose: the name is what the
    user searches for, and every same-name group in this network is a genuine
    road pair — even the 14 far ones have consecutive or +2 pole codes, so none
    of them looks like two different places (98 claim 3, §5 challenge 3).
    """
    by_name: dict[str, list[dict]] = {}
    for stop in stops:
        by_name.setdefault(stop['name'], []).append(stop)

    result = CollapseResult()
    # Sorted so the output is stable regardless of input order; a churning
    # stop list would churn every StopTime FK behind it.
    for name in sorted(by_name):
        members = sorted(by_name[name], key=lambda s: str(s['nameShort']))
        lats = [float(m['position']['lat']) for m in members]
        lons = [float(m['position']['lon']) for m in members]

        group = StopGroupResult(
            name=name,
            latitude=sum(lats) / len(lats),
            longitude=sum(lons) / len(lons),
            span_m=_max_pairwise_distance(lats, lons),
            members=members,
        )
        result.groups.append(group)
        if group.span_m > FLAG_SPAN_M:
            result.flagged.append(group)

    return result


def _max_pairwise_distance(lats: list[float], lons: list[float]) -> float:
    """Widest separation within the group. Groups are 1-3 members, so O(n^2)."""
    if len(lats) < 2:
        return 0.0
    return max(
        haversine_m(lats[i], lons[i], lats[j], lons[j])
        for i in range(len(lats))
        for j in range(i + 1, len(lats))
    )


def derive_area_key(name: str) -> str | None:
    """The village prefix a stop name declares, or None if it declares none.

    Splits on the FIRST " (" rather than requiring the string to end in ")" --
    "ARRIFES (LG. DO BOM DESPACHO) 1" must still group under ARRIFES despite the
    trailing pole number after the closing paren. A bare name with no "(" at all
    (e.g. "ACHADINHA") declares no area of its own.
    """
    if ' (' not in name:
        return None
    return name.split(' (', 1)[0].strip()


def build_area_index(stops: Iterable) -> dict[str, set[int]]:
    """Map a FOLDED village key to the ids of every stop sharing it.

    Two rules, both load-bearing:

      - Only keys with 2+ members are offered. A single stop whose name happens
        to have a "(" suffix gains nothing from being called an "area" -- the
        existing exact/prefix stop lookup already finds it.
      - A key is dropped entirely if some OTHER stop's name, exactly and on its
        own, equals that key once folded. Resolution is purely string-based --
        there is no way for "Aflitos" to mean "the one bare stop" from one tap
        and "the whole village" from another -- so where that ambiguity would
        exist, the area is not offered and the bare stop keeps its existing,
        precise, unchanged behaviour (98-style: only where it works).

    Keys are folded with `clean_string` -- the SAME fold `resolve_stop_ids`
    applies to the incoming query -- because a dict lookup is exact: a raw,
    unfolded key would never match a folded query and the area branch would
    silently never fire. Folding happens BEFORE grouping, not after: two raw
    keys that only differ by accent or case (e.g. "SÃO ROQUE" vs "SAO ROQUE",
    were upstream ever inconsistent about it) must land in the same bucket, or
    each would look like a lone, sub-2 singleton and both would be dropped.
    """
    groups: dict[str, set[int]] = defaultdict(set)
    bare_folded_names: set[str] = set()
    for stop in stops:
        key = derive_area_key(stop.name)
        if key:
            groups[clean_string(key)].add(stop.id)
        else:
            bare_folded_names.add(clean_string(stop.name))

    return {
        key: members
        for key, members in groups.items()
        if len(members) >= 2 and key not in bare_folded_names
    }
