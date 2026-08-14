"""Turn upstream observations into schedule data.

Two jobs, both of which the 2026-08-13 plan got wrong and 98 corrected:

  * `circulations_to_stop_times` -- assign `day_offset` by detecting a DECREASE
    along `sequence`. Upstream never emits a value above 86400 (98 B2), so the
    original `divmod(seconds, 86400)` converter would never have fired and every
    night trip would have been silently reordered.

  * pattern derivation from the observation matrix -- per-journey weekday mask
    plus date ranges, because upstream service is weekday-specific AND seasonal
    (98 B0). `Calendar`'s three rows cannot express "Tuesday and Thursday, school
    term only".
"""

from __future__ import annotations

import datetime
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Iterator


SECONDS_PER_DAY = 86400

# The confidence of a rule we inferred rather than one the operator published.
CONFIDENCE_SAMPLED = 'sampled'
CONFIDENCE_OFFICIAL = 'official'


def seconds_to_time(seconds: int) -> datetime.time:
    """Seconds since midnight -> time. Callers must supply an in-day value."""
    if not 0 <= seconds < SECONDS_PER_DAY:
        raise ValueError(
            f'{seconds} is outside a single day. Upstream never emits this '
            '(98 B2 measured a maximum of 86341); a value here means the feed '
            'changed shape and the wrap rule needs re-deriving.'
        )
    hour, remainder = divmod(seconds, 3600)
    minute, second = divmod(remainder, 60)
    return datetime.time(hour, minute, second)


def circulations_to_stop_times(circulations: Iterable[dict]) -> Iterator[dict]:
    """Yield stop-time rows in sequence order, with `day_offset` applied.

    Past midnight is a wrap to zero inside one journey: N03 journey 984 runs
    seq 42 at 86341, seq 43 at 0, seq 47 at 600. A wrap has occurred when
    `departureTime` DECREASES as `sequence` increases; from that point the stop
    is on the next calendar day.

    A journey that merely *starts* at 00:00 is a separate journey, not a
    continuation -- only a decrease within one journey's circulations counts.
    """
    offset = 0
    previous: int | None = None

    for circulation in sorted(circulations, key=lambda c: int(c['sequence'])):
        seconds = int(circulation['departureTime'])
        if previous is not None and seconds < previous:
            offset += 1
        previous = seconds

        row = {
            'sequence': int(circulation['sequence']),
            'departure_time': seconds_to_time(seconds),
            'day_offset': offset,
        }

        arrival = circulation.get('arrivalTime')
        if arrival is not None:
            row['arrival_time'] = seconds_to_time(int(arrival) % SECONDS_PER_DAY)

        stage = circulation.get('stage') or {}
        if stage:
            row['stage'] = stage

        yield row


@dataclass
class ServiceRule:
    """A derived answer to "which dates does this journey run on?".

    This is an inference from a bounded sample, not a published calendar. The
    `confidence` field says so, and `ambiguous_weekdays` records the days the
    sample could not settle rather than guessing them (02 section 3.3).
    """

    weekdays: set[int] = field(default_factory=set)          # 0=Mon .. 6=Sun
    ambiguous_weekdays: set[int] = field(default_factory=set)
    start_date: datetime.date | None = None                  # None => unbounded
    end_date: datetime.date | None = None
    # True when the sample shows the journey stopping (absent on a later date
    # it should have run) but is too sparse to say WHEN. 02 section 3.3 keeps
    # end_date null in that case rather than claiming the last sighting is the
    # boundary -- the sentinel probe is what narrows it.
    end_unknown: bool = False
    confidence: str = CONFIDENCE_SAMPLED

    @property
    def key(self) -> str:
        """Stable hash of the rule, so identical rules share a ServicePattern.

        Deterministic across runs: the same observation matrix must always
        produce the same key, or re-derivation churns the database.
        """
        raw = '|'.join([
            ''.join('1' if day in self.weekdays else '0' for day in range(7)),
            self.start_date.isoformat() if self.start_date else '',
            self.end_date.isoformat() if self.end_date else '',
            'end_unknown' if self.end_unknown else '',
            ','.join(str(day) for day in sorted(self.ambiguous_weekdays)),
        ])
        return 'svc_' + hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]


def build_observation_matrix(sample: dict) -> dict[str, set[datetime.date]]:
    """{(route_id, date): [journey ids]} -> {journey id: {dates seen}}.

    Keeping the raw sample means a later run can re-derive without re-fetching,
    and a pattern change is diffable rather than mysterious.
    """
    matrix: dict[str, set[datetime.date]] = defaultdict(set)
    for (_route_id, day), journey_ids in sample.items():
        for journey_id in journey_ids:
            matrix[str(journey_id)].add(day)
    return dict(matrix)


def derive_patterns(
    matrix: dict[str, set[datetime.date]],
    *,
    sampled_dates: Iterable[datetime.date],
    holidays: Iterable[datetime.date],
) -> dict[str, ServiceRule]:
    """Infer a ServiceRule per journey from the observation matrix.

    The rules, in order:

    1. Drop holiday dates from weekday inference entirely. Upstream resolves a
       holiday to its Sunday set, so a journey's absence on 2026-12-08 says
       nothing about Tuesdays -- and its *presence* says nothing either
       (98 B6). This is the guard that is a no-op against an empty Holiday
       table, which is why S0 seeds it.
    2. Set a weekday bit only where the journey appeared on EVERY non-holiday
       sampled date of that weekday; clear it where it appeared on none. A split
       sample is an ambiguity, recorded and never averaged.
    3. Bound the rule by season only when the sample brackets a change. A
       boundary derived from a sample is a bracket, not a date, so start_date
       resolves to the conservative (later) end of it.
    """
    holiday_set = set(holidays)
    sampled = sorted(set(sampled_dates))
    clean = [day for day in sampled if day not in holiday_set]

    by_weekday: dict[int, list[datetime.date]] = defaultdict(list)
    for day in clean:
        by_weekday[day.weekday()].append(day)

    patterns: dict[str, ServiceRule] = {}
    for journey_id, seen in matrix.items():
        patterns[journey_id] = _derive_rule(seen, clean)

    return patterns


def _derive_rule(
    seen: set[datetime.date],
    clean: list[datetime.date],
) -> ServiceRule:
    """Range first, then weekdays WITHIN the range.

    Inferring weekday bits across the whole sample conflates two different
    reasons for absence: "does not run that weekday" and "out of season". On
    307's school extras that reads every weekday as ambiguous and yields an
    empty mask. So bracket the journey's active window first, infer the mask
    inside it, and only then ask whether the window is bounded.
    """
    rule = ServiceRule()
    if not seen:
        return rule

    first_seen, last_seen = min(seen), max(seen)
    in_range = [day for day in clean if first_seen <= day <= last_seen]

    by_weekday: dict[int, list[datetime.date]] = defaultdict(list)
    for day in in_range:
        by_weekday[day.weekday()].append(day)

    for weekday, days in by_weekday.items():
        hits = sum(1 for day in days if day in seen)
        if hits == len(days):
            rule.weekdays.add(weekday)
        elif hits:
            # Seen on some but not all of this weekday, inside its own active
            # window: a genuine ambiguity. Record it, do not average.
            rule.ambiguous_weekdays.add(weekday)

    if not rule.weekdays:
        return rule

    # A start is claimed only when the journey should have run earlier and did
    # not. The bracket resolves to its conservative end -- the first date we
    # actually saw it -- so we never claim a school run exists before then.
    ran_before = [
        day for day in clean
        if day < first_seen and day.weekday() in rule.weekdays
    ]
    if ran_before:
        rule.start_date = first_seen

    ran_after = [
        day for day in clean
        if day > last_seen and day.weekday() in rule.weekdays
    ]
    if ran_after:
        # We know it stops; we do not know when. Flagged, not guessed.
        rule.end_unknown = True

    return rule
