"""98 B0/B6: derive per-journey weekday masks and date ranges from a sample.

Driven by the real capture: routes 1/2/9/25/31/48/53 across a term week
(2026-09-14..20), a pre-term Wednesday, a holiday Tuesday, a winter Monday and a
summer Monday.

The load-bearing cases:

  * 112 runs Tuesday and Thursday only. A WEEKDAY bucket cannot say that.
  * 307 runs 38 journeys in term and 33 in summer; the five extras are school
    runs. A sync that sampled only 2026-09-02 would store the summer set.
  * 102 has a Wednesday-only extra (1009) and a DIFFERENT Friday-only extra
    (1011), so "Wednesday represents the weekday pattern" fails even on counts.
  * 2026-12-08 is a Tuesday that returns the SUNDAY set. It must contribute no
    Tuesday evidence, or Sunday journeys get stored as Tuesday service.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from django.test import SimpleTestCase

from azoresbus.services_calendar import build_observation_matrix, derive_patterns


FIXTURES = Path(__file__).parent / 'fixtures'

TERM_WEEK = [date(2026, 9, day) for day in range(14, 21)]
PRE_TERM = date(2026, 9, 2)
HOLIDAY_TUESDAY = date(2026, 12, 8)
WINTER = date(2027, 1, 11)
SUMMER = date(2027, 7, 12)

ALL_SAMPLED = TERM_WEEK + [PRE_TERM, HOLIDAY_TUESDAY, WINTER, SUMMER]

# 98 claim 10 + our own seed. 2026-12-08 is Imaculada Conceicao.
HOLIDAYS = {HOLIDAY_TUESDAY}

ROUTE_IDS = ['1', '2', '9', '25', '31', '48', '53']


def load_sample(route_ids=ROUTE_IDS, dates=None):
    """{(route_id, date): [journey ids]} straight from the captured payloads."""
    dates = dates or ALL_SAMPLED
    sample = {}
    for route_id in route_ids:
        for day in dates:
            path = FIXTURES / f'journeys_{route_id}_{day.isoformat()}.json'
            journeys = json.loads(path.read_text(encoding='utf-8'))
            sample[(route_id, day)] = [j['id'] for j in journeys]
    return sample


class ObservationMatrixTests(SimpleTestCase):
    def test_matrix_maps_each_journey_to_the_dates_it_ran(self):
        matrix = build_observation_matrix(load_sample())

        # 112's two journeys ran on exactly the term Tuesday and Thursday.
        self.assertEqual(matrix['236'], {date(2026, 9, 15), date(2026, 9, 17)})
        self.assertEqual(matrix['237'], {date(2026, 9, 15), date(2026, 9, 17)})

    def test_journeys_absent_everywhere_are_absent_from_the_matrix(self):
        matrix = build_observation_matrix(load_sample())
        self.assertNotIn('999999', matrix)


class WeekdayMaskTests(SimpleTestCase):
    def setUp(self):
        self.patterns = derive_patterns(
            build_observation_matrix(load_sample()),
            sampled_dates=ALL_SAMPLED,
            holidays=HOLIDAYS,
        )

    def test_112_runs_tuesday_and_thursday_only(self):
        for journey_id in ('236', '237'):
            rule = self.patterns[journey_id]
            self.assertEqual(
                rule.weekdays, {1, 3},
                f'journey {journey_id} should be Tue/Thu only, got {rule.weekdays}',
            )

    def test_102_wednesday_and_friday_extras_are_distinct(self):
        self.assertEqual(self.patterns['1009'].weekdays, {2})
        self.assertEqual(self.patterns['1011'].weekdays, {4})

    def test_an_everyday_journey_gets_the_full_weekday_mask(self):
        # 307's base service runs Mon-Fri and Saturday, never Sunday.
        rule = self.patterns['634']
        self.assertTrue({0, 1, 2, 3, 4} <= rule.weekdays)
        self.assertNotIn(6, rule.weekdays)


class HolidayPoisoningTests(SimpleTestCase):
    """98 B6, the failure that arrives through the mitigation for B6."""

    def test_holiday_tuesday_contributes_no_tuesday_evidence(self):
        patterns = derive_patterns(
            build_observation_matrix(load_sample()),
            sampled_dates=ALL_SAMPLED,
            holidays=HOLIDAYS,
        )
        # 112 does not run on 2026-12-08 (nothing does but the Sunday set), yet
        # it must still hold its Tuesday bit from the term week.
        self.assertIn(1, patterns['236'].weekdays)

    def test_without_the_holiday_guard_tuesday_evidence_is_poisoned(self):
        """Proves the guard is load-bearing rather than decorative.

        Note which journey this uses. 112's runs are term-only, so 2026-12-08
        falls outside their active window and cannot reach them either way. The
        guard bites on a YEAR-ROUND Tuesday journey, whose window spans the
        holiday -- 301's 488, which runs every weekday all year.
        """
        guarded = derive_patterns(
            build_observation_matrix(load_sample()),
            sampled_dates=ALL_SAMPLED,
            holidays=HOLIDAYS,
        )
        self.assertIn(1, guarded['488'].weekdays)
        self.assertNotIn(1, guarded['488'].ambiguous_weekdays)

        poisoned = derive_patterns(
            build_observation_matrix(load_sample()),
            sampled_dates=ALL_SAMPLED,
            holidays=set(),          # the production state before the S0 seed
        )
        self.assertNotIn(
            1, poisoned['488'].weekdays,
            'with an empty Holiday table, 2026-12-08 looks like an ordinary '
            'Tuesday on which 488 did not run, so its Tuesday bit is lost',
        )
        self.assertIn(1, poisoned['488'].ambiguous_weekdays)

    def test_sunday_journeys_are_not_credited_to_tuesday(self):
        patterns = derive_patterns(
            build_observation_matrix(load_sample()),
            sampled_dates=ALL_SAMPLED,
            holidays=HOLIDAYS,
        )
        sunday_only = json.loads(
            (FIXTURES / 'journeys_25_2026-09-20.json').read_text(encoding='utf-8')
        )
        term_tuesday = {
            j['id'] for j in json.loads(
                (FIXTURES / 'journeys_25_2026-09-15.json').read_text(encoding='utf-8')
            )
        }
        for journey in sunday_only:
            if journey['id'] in term_tuesday:
                continue
            self.assertNotIn(
                1, patterns[journey['id']].weekdays,
                f'journey {journey["id"]} runs only on Sundays and the holiday '
                'Tuesday, so it must not carry a Tuesday bit',
            )


class SeasonalRangeTests(SimpleTestCase):
    def setUp(self):
        self.patterns = derive_patterns(
            build_observation_matrix(load_sample()),
            sampled_dates=ALL_SAMPLED,
            holidays=HOLIDAYS,
        )

    def test_307_school_extras_are_bounded_to_term(self):
        """98 B0: 633, 645, 647, 661, 662 appear in term and not in summer."""
        for journey_id in ('633', '645', '647', '661', '662'):
            rule = self.patterns[journey_id]
            self.assertEqual(
                rule.start_date, date(2026, 9, 14),
                'the bracket resolves to its conservative (later) end -- we '
                'never claim a school run exists before we have seen it',
            )
            self.assertEqual(rule.confidence, 'sampled')
            # We saw them absent on 2027-07-12, so we know term ends -- but one
            # winter sample cannot say when. Flagged rather than guessed.
            self.assertTrue(rule.end_unknown)
            self.assertIsNone(rule.end_date)

    def test_year_round_journeys_stay_unbounded(self):
        rule = self.patterns['634']
        self.assertIsNone(rule.start_date)
        self.assertIsNone(rule.end_date)

    def test_102_is_seasonal_too_not_just_307(self):
        """Measured in our capture, beyond what 98 B0 recorded.

        102 returns 27 journeys on a term Monday and 25 on both the pre-term
        Wednesday and the summer Monday. Treating 307 as the only seasonal line
        would bake the summer 102 timetable in as year-round.
        """
        for journey_id in ('51', '1015'):
            self.assertEqual(self.patterns[journey_id].start_date, date(2026, 9, 14))


class AmbiguityTests(SimpleTestCase):
    """A split sample is recorded, never averaged (02 section 3.3)."""

    def test_a_journey_seen_on_some_but_not_all_of_a_weekday_is_ambiguous(self):
        # The gap must fall INSIDE the active window. A trailing absence is not
        # ambiguity -- it is the journey ending, and is bounded instead.
        matrix = {
            'amb': {date(2026, 9, 15), date(2027, 1, 19)},   # 2 of 3 Tuesdays
        }
        sampled = [date(2026, 9, 15), date(2027, 1, 12), date(2027, 1, 19)]
        patterns = derive_patterns(matrix, sampled_dates=sampled, holidays=set())

        rule = patterns['amb']
        self.assertNotIn(
            1, rule.weekdays, 'a split sample must not silently set the bit',
        )
        self.assertIn(1, rule.ambiguous_weekdays)

    def test_a_trailing_absence_is_an_ending_not_an_ambiguity(self):
        """The journey ran, then stopped. We know THAT, not WHEN."""
        sampled = [date(2026, 9, 15), date(2027, 1, 12), date(2027, 1, 19)]
        patterns = derive_patterns(
            {'stopped': {date(2026, 9, 15), date(2027, 1, 12)}},
            sampled_dates=sampled, holidays=set(),
        )
        rule = patterns['stopped']
        self.assertEqual(rule.weekdays, {1})
        self.assertEqual(rule.ambiguous_weekdays, set())
        self.assertTrue(rule.end_unknown)
        self.assertIsNone(
            rule.end_date,
            '02 section 3.3: flag the end, do not claim the last sighting is it',
        )

    def test_unanimous_presence_is_not_ambiguous(self):
        sampled = [date(2026, 9, 15), date(2027, 1, 12)]
        patterns = derive_patterns(
            {'sure': set(sampled)}, sampled_dates=sampled, holidays=set(),
        )
        self.assertEqual(patterns['sure'].weekdays, {1})
        self.assertEqual(patterns['sure'].ambiguous_weekdays, set())


class DeterminismTests(SimpleTestCase):
    def test_same_matrix_produces_the_same_key(self):
        """Re-derivation must be idempotent (02 section 3.3)."""
        first = derive_patterns(
            build_observation_matrix(load_sample()),
            sampled_dates=ALL_SAMPLED, holidays=HOLIDAYS,
        )
        second = derive_patterns(
            build_observation_matrix(load_sample()),
            sampled_dates=list(reversed(ALL_SAMPLED)), holidays=HOLIDAYS,
        )
        self.assertEqual(
            {jid: rule.key for jid, rule in first.items()},
            {jid: rule.key for jid, rule in second.items()},
        )

    def test_journeys_with_identical_rules_share_a_key(self):
        patterns = derive_patterns(
            build_observation_matrix(load_sample()),
            sampled_dates=ALL_SAMPLED, holidays=HOLIDAYS,
        )
        self.assertEqual(patterns['236'].key, patterns['237'].key)
        self.assertNotEqual(patterns['236'].key, patterns['1009'].key)
