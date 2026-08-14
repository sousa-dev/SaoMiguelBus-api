"""The Holiday table must cover 2026-2027 before any sync writes ServicePattern rows.

Production holds 16 rows ending 2025-06-19, so ``is_holiday`` is false for every
date that matters. Three consequences, in rising order of damage (00 prerequisite):

  1. search diverges from upstream on every holiday;
  2. bootstrap and both offline bundles ship a list that stops in 2025, so clients
     resolve holiday dates wrongly too — the app computes its day-type from
     ``bootstrap.holidays`` (lib/transit-format.ts resolveDayType);
  3. the B6 sampler guard ("never sample a known holiday as weekday evidence")
     becomes a silent no-op, and 2026-12-01 / 2026-12-08 get recorded as ordinary
     Tuesday service.

98 claim 10 confirmed eight dates resolve to the Sunday set upstream. Seven are
seeded here. The eighth, 2027-04-04, is NOT: it is a plain Sunday (Easter 2027 is
2027-03-28), so it carries no holiday evidence at all and 98's "(Easter)" label is
a mislabel. It is asserted behaviourally instead — see the test below.
"""

from __future__ import annotations

from datetime import date

from django.test import TestCase

from tenancy.services import get_or_create_default_island
from transit.models import Holiday


# 98 claim 10, minus the mislabelled 2027-04-04. Every one of these is a genuine
# holiday AND carries real evidence: five fall on weekdays, and 2026-08-15 is a
# Saturday that returns the Sunday set rather than the Saturday set.
CONFIRMED_SUNDAY_RESOLVING_DATES = [
    date(2026, 8, 15),   # Saturday  - Assuncao
    date(2026, 10, 5),   # Monday    - Implantacao da Republica
    date(2026, 12, 1),   # Tuesday   - Restauracao da Independencia
    date(2026, 12, 8),   # Tuesday   - Imaculada Conceicao
    date(2026, 12, 25),  # Friday    - Natal
    date(2027, 1, 1),    # Friday    - Ano Novo
    date(2027, 6, 10),   # Thursday  - Dia de Portugal
]


class HolidaySeedTests(TestCase):
    def setUp(self):
        self.island = get_or_create_default_island()

    def test_confirmed_dates_are_seeded(self):
        """The 7 dates 98 measured as resolving to the Sunday set upstream."""
        seeded = set(
            Holiday.objects.filter(island=self.island).values_list('date', flat=True)
        )
        missing = [d for d in CONFIRMED_SUNDAY_RESOLVING_DATES if d not in seeded]
        self.assertEqual(
            missing,
            [],
            f'Holiday seed is missing dates 98 confirmed: {missing}. '
            'Any of these missing is a bug in the seed (00 prerequisite).',
        )

    def test_both_sample_years_are_covered(self):
        """An empty year is a seeding bug, not a year without holidays.

        The S2 sampler hard-fails on a year with no rows rather than deriving
        poisoned patterns, so this is the precondition that makes the guard real.
        """
        for year in (2026, 2027):
            count = Holiday.objects.filter(
                island=self.island, date__year=year,
            ).count()
            self.assertGreaterEqual(
                count, 10, f'{year} has only {count} holiday rows seeded',
            )

    def test_easter_2027_is_march_28_not_april_4(self):
        """Guards the specific error in 98 claim 10.

        Easter 2027 is 2027-03-28. 2027-04-04 is the Sunday after it and is not a
        holiday under any Portuguese or Azorean calendar.
        """
        seeded = set(
            Holiday.objects.filter(island=self.island).values_list('date', flat=True)
        )
        self.assertIn(date(2027, 3, 28), seeded, 'Easter Sunday 2027 not seeded')
        self.assertIn(date(2027, 3, 26), seeded, 'Good Friday 2027 not seeded')
        self.assertNotIn(
            date(2027, 4, 4),
            seeded,
            '2027-04-04 is a plain Sunday, not a holiday. Seeding it would put '
            'fabricated data into bootstrap.holidays and both offline bundles, '
            'which clients render.',
        )

    def test_2027_04_04_still_resolves_to_sunday_service(self):
        """What 98 claim 10 was actually testing for, asserted honestly.

        Upstream returns the Sunday set on 2027-04-04 because it IS a Sunday. Our
        resolution agrees, via the weekday branch rather than the holiday branch.
        """
        from transit.services.search import get_type_of_day
        from transit.models import Calendar
        from datetime import datetime

        day = datetime(2027, 4, 4)
        self.assertEqual(day.weekday(), 6, 'sanity: 2027-04-04 is a Sunday')
        self.assertEqual(
            get_type_of_day(day, is_holiday=False), Calendar.SUNDAY,
        )

    def test_seeded_rows_match_the_service_calendar(self):
        """The frozen migration and the live service module must agree.

        The migration inlines its date arithmetic on purpose, so a later edit to
        ``transit.services.holidays`` cannot retroactively change what was
        seeded. This test is what stops the two drifting apart unnoticed.
        """
        from transit.services.holidays import holiday_calendar

        expected = {
            holiday_date
            for year in (2026, 2027)
            for holiday_date, _ in holiday_calendar(year)
        }
        seeded = set(
            Holiday.objects.filter(
                island=self.island, date__year__in=(2026, 2027),
            ).values_list('date', flat=True)
        )
        self.assertEqual(
            seeded,
            expected,
            'transit/migrations/0004 and transit/services/holidays.py disagree. '
            'Reconcile them deliberately rather than editing one side.',
        )

    def test_azores_regional_holidays_are_seeded(self):
        """Senhor Santo Cristo (Easter+35) and Dia dos Acores (Easter+50)."""
        seeded = set(
            Holiday.objects.filter(island=self.island).values_list('date', flat=True)
        )
        for expected in (
            date(2026, 5, 10),   # Santo Cristo 2026 (Easter 2026-04-05 + 35)
            date(2026, 5, 25),   # Dia dos Acores 2026 (Easter + 50)
            date(2027, 5, 2),    # Santo Cristo 2027 (Easter 2027-03-28 + 35)
            date(2027, 5, 17),   # Dia dos Acores 2027 (Easter + 50)
        ):
            self.assertIn(expected, seeded, f'{expected} not seeded')
