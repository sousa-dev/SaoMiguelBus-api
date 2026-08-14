"""Sync worker: upstream sample -> transit models.

The dangerous part of a sync is not the fetching, it is deciding that something
has gone away. A 200 with a partial list looks exactly like a deletion
(02 §4.5), and a term/summer split makes "absent" the normal state for half the
network for half the year (98 B0).

So service is RETIRED, not deleted: the sync closes a journey's service window
and leaves the trip, its id, its votes and its observation history in place. If
the service comes back, a new observation reopens it. Hard deletion is reserved
for rows no observation references at all, and sits behind the same gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from decouple import config


AZORESBUS_SYNC_PRUNE_FLOOR = config(
    'AZORESBUS_SYNC_PRUNE_FLOOR', default=0.10, cast=float,
)


@dataclass
class RetirementDecision:
    """Whether this run has earned the right to remove service, and why."""

    allowed: bool
    reason: str = ''
    scope_dates: set[date] = field(default_factory=set)

    def as_dict(self) -> dict:
        """Serialisable for SyncRun.stats -- the decision must be auditable."""
        return {
            'allowed': self.allowed,
            'reason': self.reason,
            'scope_dates': sorted(day.isoformat() for day in self.scope_dates),
        }


def evaluate_retirement(
    *,
    status: str,
    journey_count: int,
    previous_journey_count: int | None,
    sampled_dates: list[date],
    far_season_dates: list[date],
    floor: float | None = None,
) -> RetirementDecision:
    """Gate every rule in 02 §4.5 before any service window is closed.

    Ordered so the cheapest and most decisive checks fail first, and so the
    reason returned is the most useful one rather than merely the first.
    """
    floor = AZORESBUS_SYNC_PRUNE_FLOOR if floor is None else floor
    scope = set(sampled_dates) | set(far_season_dates)

    if status != 'completed':
        return RetirementDecision(
            False,
            f'run status is {status!r}, not completed -- a budget cap, abort or '
            'failure streak leaves a partial picture',
            scope,
        )

    if not journey_count:
        return RetirementDecision(
            False,
            'the sample came back empty network-wide, which is an upstream '
            'problem and not a deletion',
            scope,
        )

    if previous_journey_count is None:
        return RetirementDecision(
            False,
            'no successful previous run to use as a baseline, so nothing this '
            'run did not see is evidence of removal',
            scope,
        )

    if not far_season_dates:
        # 98 B0: 307 loses five school runs in summer, 112/321/324/325 vanish
        # entirely. Without the contrast they all look deleted.
        return RetirementDecision(
            False,
            'no far season observations, so "out of season" cannot be told '
            'from "gone"',
            scope,
        )

    minimum = previous_journey_count * (1.0 - floor)
    if journey_count < minimum:
        return RetirementDecision(
            False,
            f'journey count {journey_count} is below the floor '
            f'({minimum:.0f} = {1 - floor:.0%} of {previous_journey_count})',
            scope,
        )

    return RetirementDecision(
        True,
        f'{journey_count} journeys across {len(scope)} sampled dates, '
        f'within {floor:.0%} of the previous {previous_journey_count}',
        scope,
    )
