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

from azoresbus.services_names import (
    CURATED_CANONICAL_NAMES,
    canonicalize,
    split_name,
    unexpanded_tokens,
)
from transit.services.legacy_import import clean_string


EARTH_RADIUS_M = 6_371_000.0

# Groups spanning more than this get flagged for review at import. Expect 14
# (98 §3 measured 14, not the 30 an earlier draft claimed).
FLAG_SPAN_M = 75.0

# Above this, the collapse is worth surfacing to the user as a walking-distance
# hint on the result card rather than a second picker row. Expect 3.
HINT_SPAN_M = 100.0

# A canonical VILLAGE spanning more than this is not a village -- it is two
# places that canonicalization has merged by mistake. Real ones top out around
# 5.6 km (Vila do Nordeste 5.57 after its curated merge, Lagoa 5.53, Ponta
# Garca 5.25, Capelas 5.11), so 8 km separates signal from noise cleanly.
AREA_SPAN_LIMIT_M = 8_000.0


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
class AmbiguousArea:
    """A canonical village key that spans too far to be one place."""

    name: str
    span_m: float
    pole_codes: list[str] = field(default_factory=list)
    raw_prefixes: list[str] = field(default_factory=list)
    unmerged: bool = False

    def as_dict(self) -> dict:
        return {
            'name': self.name,
            'span_m': round(self.span_m, 1),
            'pole_codes': self.pole_codes,
            'raw_prefixes': self.raw_prefixes,
            'unmerged': self.unmerged,
        }


@dataclass
class CollapseResult:
    groups: list[StopGroupResult] = field(default_factory=list)
    flagged: list[StopGroupResult] = field(default_factory=list)
    ambiguous_areas: list[AmbiguousArea] = field(default_factory=list)
    unexpanded: list[str] = field(default_factory=list)


def _area_span_m(members: list[dict]) -> float:
    """Widest separation across a whole village. Bounding-box diagonal.

    O(n) rather than the O(n^2) `_max_pairwise_distance` used for 1-3 member
    pole groups, because Capelas alone has 71 poles and this runs over every
    village on every import.
    """
    lats = [float(m['position']['lat']) for m in members]
    lons = [float(m['position']['lon']) for m in members]
    return haversine_m(min(lats), min(lons), max(lats), max(lons))


def _canonical_names(stops: list[dict]) -> tuple[dict[int, str], list[AmbiguousArea]]:
    """Canonical name per stop, with over-wide village merges backed out.

    Expansion is what makes village search work, but it is also what makes it
    dangerous: `STA. BÁRBARA` names two villages 16.5 km apart, and `S.`
    expands to São/Santo/Santa/Sete/Seca. A curated rule handles the
    collisions we know about; this guard catches the ones we do not.

    When a canonical village spans further than any real village could, the
    merge is backed out (`merge=False` keeps the expansion and title casing,
    drops only the curated unification) and the area is reported. Two upstream
    prefixes that were ALREADY identical cannot be separated this way -- those
    are reported but left as they are, because inventing a distinction would
    be a worse guess than leaving upstream's.

    Never raises. A naming problem must not take the whole network offline;
    it surfaces in `SyncRun.stats` for a human to curate.
    """
    names = {id(stop): canonicalize(stop['name'], str(stop['nameShort']))
             for stop in stops}

    by_village: dict[str, list[dict]] = defaultdict(list)
    for stop in stops:
        by_village[split_name(names[id(stop)])[0]].append(stop)

    ambiguous: list[AmbiguousArea] = []
    for village in sorted(by_village):
        members = by_village[village]
        if len(members) < 2 or village in CURATED_CANONICAL_NAMES:
            continue
        span = _area_span_m(members)
        if span <= AREA_SPAN_LIMIT_M:
            continue

        raw_prefixes = sorted({split_name(m['name'])[0] for m in members})
        unmerged = len(raw_prefixes) > 1
        if unmerged:
            for member in members:
                names[id(member)] = canonicalize(
                    member['name'], str(member['nameShort']), merge=False,
                )
        ambiguous.append(AmbiguousArea(
            name=village,
            span_m=span,
            pole_codes=sorted(str(m['nameShort']) for m in members),
            raw_prefixes=raw_prefixes,
            unmerged=unmerged,
        ))

    return names, ambiguous


def collapse_stops(stops: list[dict]) -> CollapseResult:
    """Group upstream stops by canonical name; position each at its centroid.

    Names are canonicalized BEFORE grouping (see `services_names`), so that the
    grouping key, `Stop.name`, `Stop.cleaned_name` and `derive_area_key` all
    see one consistent value. Canonicalizing later would leave this grouping
    on raw names, and the two spellings of `(BARRACUDA)` would produce two
    `Stop` rows that then collide on `cleaned_name` at import.

    Grouping is by name rather than proximity on purpose: the name is what the
    user searches for, and every same-name group in this network is a genuine
    road pair — even the 14 far ones have consecutive or +2 pole codes, so none
    of them looks like two different places (98 claim 3, §5 challenge 3).
    """
    canonical, ambiguous = _canonical_names(stops)

    by_name: dict[str, list[dict]] = {}
    for stop in stops:
        by_name.setdefault(canonical[id(stop)], []).append(stop)

    result = CollapseResult(ambiguous_areas=ambiguous)
    result.unexpanded = sorted({
        token for name in by_name for token in unexpanded_tokens(name)
    })
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


def build_azoresbus_area_index(dataset: str, stops=None) -> dict[str, set[int]]:
    """The village index plus every retired spelling that must still open it.

    The one place both `search_routes` and `search_journeys` should build it,
    so the alias keys can never be present on one path and missing on the
    other.
    """
    from transit.models import Stop, StopAlias

    if stops is None:
        stops = Stop.objects.filter(dataset=dataset).only('id', 'name')
    stops = list(stops)
    index = build_area_index(stops)
    aliases = (
        StopAlias.objects.filter(dataset=dataset)
        .select_related('stop').only('cleaned_alias', 'stop__name')
    )
    return merge_area_aliases(index, aliases, reserved=_reserved_keys(stops))


def _reserved_keys(stops: Iterable) -> set[str]:
    """Folded strings a real stop already answers to, as a village or on its own.

    An alias key must not shadow one of these. A village with a single stop is
    not in `area_index` (the 2-member rule), but "sao roque" still resolves to
    `São Roque (Igreja)` through the prefix fallback -- so letting an alias
    claim that string would silently redirect the query to another village.
    """
    reserved: set[str] = set()
    for stop in stops:
        key = derive_area_key(stop.name)
        reserved.add(clean_string(key if key else stop.name))
    return reserved


def merge_area_aliases(
    area_index: dict[str, set[int]],
    aliases: Iterable,
    reserved: set[str] | None = None,
) -> dict[str, set[int]]:
    """Add retired village spellings as extra keys onto an existing area index.

    `build_area_index` keys on the CANONICAL name, so after the rename
    "ponta delgada" opens the village and "p. delgada" -- the string in every
    link and favourite made before the rename -- opens nothing. Each
    `StopAlias` still carries its old full name, so its village prefix can be
    recovered with the same `derive_area_key` split.

    An old prefix that now maps to more than one village is DROPPED, not
    guessed: "sta. barbara" was two different places, and sending half those
    users to the wrong one is worse than falling through to the prefix
    fallback. `reserved` blocks the same thing one level down -- a string some
    real stop already answers to, whether as a village or as its own bare
    name, is never handed to an alias.

    Kept out of `build_area_index` on purpose -- that function is mirrored in
    TypeScript and contract-tested against a shared fixture, and it has no
    database to read aliases from.
    """
    candidates: dict[str, set[str]] = defaultdict(set)
    for alias in aliases:
        old_key = derive_area_key(alias.cleaned_alias)
        new_key = derive_area_key(alias.stop.name)
        if not old_key or not new_key:
            continue
        folded_old, folded_new = clean_string(old_key), clean_string(new_key)
        if folded_old != folded_new and folded_new in area_index:
            candidates[folded_old].add(folded_new)

    merged = dict(area_index)
    blocked = reserved or set()
    for folded_old, targets in candidates.items():
        if folded_old in merged or folded_old in blocked or len(targets) > 1:
            continue
        merged[folded_old] = area_index[next(iter(targets))]
    return merged


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
