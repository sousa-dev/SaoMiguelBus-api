"""02 §4.1: the sample is tiered, and its guards are what keep it honest.

Three canonical dates cannot capture this calendar (98 B0/B6). The sample is a
full week in the season we are serving, a cached week in the opposite season, the
known holidays, and a forward sentinel probe.

The guards matter more than the tiers:
  * never take a known holiday as weekday evidence (2026-12-01 and 2026-12-08
    are weekdays returning Sunday sets);
  * never sample below the 2026-07-27 data floor, or an empty response looks
    like a network-wide deletion and trips the retirement gate;
  * never hardcode a term start -- it is observed, not official.
"""

from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase

from azoresbus.services_sampling import DATA_FLOOR, build_sample


HOLIDAYS = {
    date(2026, 12, 1), date(2026, 12, 8), date(2026, 12, 25),
    date(2027, 1, 1), date(2026, 10, 5), date(2026, 8, 15),
}


class NearWeekTests(SimpleTestCase):
    def test_near_week_is_seven_consecutive_days_from_a_monday(self):
        sample = build_sample(today=date(2026, 9, 9), holidays=HOLIDAYS)

        near = sample.near_week
        self.assertEqual(len(near), 7)
        self.assertEqual(near[0].weekday(), 0)
        self.assertEqual(near[-1].weekday(), 6)
        self.assertEqual([(d - near[0]).days for d in near], list(range(7)))

    def test_near_week_starts_after_today(self):
        sample = build_sample(today=date(2026, 9, 9), holidays=HOLIDAYS)
        self.assertGreater(sample.near_week[0], date(2026, 9, 9))


class HolidayGuardTests(SimpleTestCase):
    """98 B6, the failure that arrives through the mitigation for B6."""

    def test_a_week_containing_a_holiday_substitutes_that_weekday(self):
        # 2026-12-08 is a Tuesday holiday. The week of Mon 2026-12-07 contains
        # it, so the Tuesday slot must come from elsewhere.
        sample = build_sample(today=date(2026, 12, 2), holidays=HOLIDAYS)

        self.assertNotIn(date(2026, 12, 8), sample.weekday_evidence_dates)
        tuesdays = [
            d for d in sample.weekday_evidence_dates if d.weekday() == 1
        ]
        self.assertTrue(tuesdays, 'the Tuesday slot was dropped, not replaced')
        for day in tuesdays:
            self.assertNotIn(day, HOLIDAYS)

    def test_holidays_are_still_sampled_as_exception_evidence(self):
        """We want to SEE the holiday, just not count it as a Tuesday."""
        sample = build_sample(today=date(2026, 11, 25), holidays=HOLIDAYS)
        self.assertTrue(set(sample.holiday_dates) & HOLIDAYS)
        self.assertFalse(set(sample.weekday_evidence_dates) & HOLIDAYS)

    def test_no_holiday_ever_appears_as_weekday_evidence(self):
        for start in (date(2026, 9, 1), date(2026, 11, 26), date(2026, 12, 20)):
            sample = build_sample(today=start, holidays=HOLIDAYS)
            self.assertFalse(
                set(sample.weekday_evidence_dates) & HOLIDAYS,
                f'holiday leaked into weekday evidence from {start}',
            )


class DataFloorTests(SimpleTestCase):
    def test_nothing_is_sampled_below_the_floor(self):
        """98 B1: 2026-07-25 and 07-26 return []; 07-27 is the first real date."""
        sample = build_sample(today=date(2026, 7, 20), holidays=HOLIDAYS)
        for day in sample.all_dates:
            self.assertGreaterEqual(
                day, DATA_FLOOR,
                f'{day} is below the data floor; an empty response there looks '
                'like a network-wide deletion',
            )

    def test_the_floor_is_the_observed_value(self):
        self.assertEqual(DATA_FLOOR, date(2026, 7, 27))


class FarWeekTests(SimpleTestCase):
    def test_a_full_run_includes_a_far_season_week(self):
        sample = build_sample(
            today=date(2026, 9, 9), holidays=HOLIDAYS, full=True,
        )
        self.assertEqual(len(sample.far_week), 7)
        self.assertNotEqual(
            sample.far_week[0].month, sample.near_week[0].month,
        )

    def test_an_incremental_run_omits_the_far_week(self):
        sample = build_sample(
            today=date(2026, 9, 9), holidays=HOLIDAYS, full=False,
        )
        self.assertEqual(sample.far_week, [])

    def test_far_week_is_summer_when_near_week_is_term(self):
        sample = build_sample(
            today=date(2026, 10, 1), holidays=HOLIDAYS, full=True,
        )
        self.assertIn(sample.far_week[0].month, (7, 8))

    def test_far_week_is_term_when_near_week_is_summer(self):
        sample = build_sample(
            today=date(2027, 7, 20), holidays=HOLIDAYS, full=True,
        )
        self.assertNotIn(sample.far_week[0].month, (7, 8))


class SentinelTests(SimpleTestCase):
    def test_sentinel_dates_probe_forward(self):
        """Term end is unknown; this is what detects the flip (98 §7)."""
        today = date(2026, 9, 9)
        sample = build_sample(today=today, holidays=HOLIDAYS)

        self.assertTrue(sample.sentinel_dates)
        for day in sample.sentinel_dates:
            self.assertGreater(day, today)
        self.assertGreater(max(sample.sentinel_dates), today.replace(month=10))

    def test_sentinels_are_never_holidays(self):
        sample = build_sample(today=date(2026, 11, 3), holidays=HOLIDAYS)
        self.assertFalse(set(sample.sentinel_dates) & HOLIDAYS)


class BudgetTests(SimpleTestCase):
    def test_incremental_is_materially_cheaper_than_full(self):
        incremental = build_sample(
            today=date(2026, 9, 9), holidays=HOLIDAYS, full=False,
        )
        full = build_sample(
            today=date(2026, 9, 9), holidays=HOLIDAYS, full=True,
        )
        self.assertLess(len(incremental.all_dates), len(full.all_dates))

    def test_a_full_sample_stays_near_the_planned_16_dates(self):
        full = build_sample(
            today=date(2026, 9, 9), holidays=HOLIDAYS, full=True,
        )
        self.assertLessEqual(
            len(full.all_dates), 20,
            '55 routes x this many dates drives the request budget',
        )

    def test_dates_are_unique_and_sorted(self):
        sample = build_sample(
            today=date(2026, 9, 9), holidays=HOLIDAYS, full=True,
        )
        self.assertEqual(sample.all_dates, sorted(set(sample.all_dates)))
