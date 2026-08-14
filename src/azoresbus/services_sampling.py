"""Build the date sample a sync run will fetch.

Three canonical dates ("next Wednesday, Saturday, Sunday") cannot represent this
network: service is weekday-specific AND seasonal (98 B0), and two of the
weekday holidays return Sunday sets (98 B6). So the sample is tiered:

  near week      the season we are serving, every run
  far week       the opposite season, full runs only, otherwise reused from
                 stored ServiceObservation rows
  holidays       known holidays, as exception evidence -- never weekday evidence
  sentinels      a forward probe that detects the term flip we have no
                 calendar for

Nothing here hardcodes a term start. 2026-09-14 is observed, not official
(98 §7), and lives in Island.feature_flags where it can be corrected without a
deploy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


# 98 B1: 2026-07-25 and 07-26 return []; 07-27 onward is populated. Sampling
# below this looks like a network-wide deletion and would trip the retirement
# gate for the wrong reason.
DATA_FLOOR = date(2026, 7, 27)

# Months upstream serves the reduced summer timetable (307: 33 vs 38).
SUMMER_MONTHS = (7, 8)

# How far ahead the sentinel probe looks for a service change.
SENTINEL_WEEKS = (4, 8)


@dataclass
class DateSample:
    near_week: list[date] = field(default_factory=list)
    far_week: list[date] = field(default_factory=list)
    holiday_dates: list[date] = field(default_factory=list)
    sentinel_dates: list[date] = field(default_factory=list)

    @property
    def weekday_evidence_dates(self) -> list[date]:
        """Dates whose journey sets may be read as weekday evidence.

        Holidays are excluded by construction: upstream resolves them to the
        Sunday set, so counting one as a Tuesday stores Sunday journeys as
        Tuesday service (98 B6).
        """
        return sorted(set(self.near_week) | set(self.far_week))

    @property
    def all_dates(self) -> list[date]:
        return sorted(
            set(self.near_week)
            | set(self.far_week)
            | set(self.holiday_dates)
            | set(self.sentinel_dates)
        )


def _next_monday(after: date) -> date:
    return after + timedelta(days=(7 - after.weekday()) or 7)


def _clean_week(start: date, holidays: set[date]) -> list[date]:
    """A Mon-Sun week with any holiday slot substituted from a later week.

    Shifting the whole week would move it across a season boundary; replacing
    the single poisoned weekday keeps the rest of the week's contrast intact.
    """
    week: list[date] = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        while day in holidays:
            day += timedelta(days=7)
        week.append(max(day, DATA_FLOOR))
    return week


def _far_week_start(near_start: date, holidays: set[date]) -> date:
    """A week in the opposite season to the one the near week sits in.

    Supplies the contrast the derivation needs for date bounds, and the
    "out of season != deleted" evidence the retirement gate depends on.
    """
    if near_start.month in SUMMER_MONTHS:
        # Near week is summer -> reach for a term week the following autumn.
        candidate = date(near_start.year, 10, 5)
        if candidate <= near_start:
            candidate = date(near_start.year + 1, 10, 5)
    else:
        # Near week is term -> reach for the next July.
        year = near_start.year if near_start.month < 7 else near_start.year + 1
        candidate = date(year, 7, 5)

    return _next_monday(max(candidate, DATA_FLOOR) - timedelta(days=1))


def build_sample(
    *,
    today: date,
    holidays: set[date] | None = None,
    full: bool = False,
    horizon_days: int = 120,
) -> DateSample:
    """Compute the dates this run should fetch.

    `full` adds the far-season week. The first run is always full, and an
    incremental run that finds no stored far-season observations upgrades
    itself, or the first retirement pass has no way to tell "out of season" from
    "deleted" (02 §4.1).
    """
    holidays = holidays or set()
    sample = DateSample()

    near_start = max(_next_monday(today), DATA_FLOOR)
    sample.near_week = _clean_week(near_start, holidays)

    if full:
        sample.far_week = _clean_week(
            _far_week_start(near_start, holidays), holidays,
        )

    # Holidays inside the horizon, as ServiceException evidence. Confirms
    # upstream still resolves them to Sunday, and catches the ones our table
    # does not know about when the sync compares journey sets.
    horizon = today + timedelta(days=horizon_days)
    sample.holiday_dates = sorted(
        day for day in holidays if DATA_FLOOR <= day <= horizon
    )[:3]

    # Forward probe: the mechanism that replaces the term calendar we do not
    # have. A change in a sentinel line's journey set schedules a re-derivation.
    for weeks in SENTINEL_WEEKS:
        day = today + timedelta(weeks=weeks)
        while day in holidays:
            day += timedelta(days=1)
        sample.sentinel_dates.append(max(day, DATA_FLOOR))

    return sample
