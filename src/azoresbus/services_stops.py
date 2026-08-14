"""Collapse 1456 upstream stops to 816 searchable places.

Upstream models each pole separately: 630 names carry two codes, 5 carry three.
They are the two sides of a road — median 11.5 m apart, 629 of 630 pairs with
consecutive integer codes — so offering both to a picker asks the user a
question they cannot answer. Which pole a trip serves is a property of its
direction, not a search input (02 §3.2).

So: one `transit.Stop` per distinct name, positioned at the centroid, with full
upstream identity kept in `ExternalStop` so results can still show the pole code
and put the boarding marker on the correct side of the road.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


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
