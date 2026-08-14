"""Guard the committed review captures.

These files are evidence from the 2026-08-14 review (98). They cost ~1,500 live
requests to produce and cannot be regenerated without hammering upstream. If one
is edited or truncated, the calendar tests built on top of them would quietly
start asserting something else, so their load-bearing contents are pinned here.

If a test disagrees with these files, the test is wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase


FIXTURES = Path(__file__).parent / 'fixtures' / 'review'


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class ReviewFixtureIntegrityTests(SimpleTestCase):
    def test_sweep_covers_three_routes_over_51_dates(self):
        sweep = load('sweep_compact.json')
        self.assertEqual(sorted(sweep), ['101', '301', '335'])
        for line, rows in sweep.items():
            self.assertEqual(len(rows), 51, f'{line} lost dates')

    def test_holiday_poisoning_evidence_is_intact(self):
        """98 B6: 2026-12-01 and 2026-12-08 are Tuesdays returning the Sunday set.

        This is the whole reason the sampler may not treat a calendar weekday as
        weekday evidence. Line 301's Sunday set is ids 515-522.
        """
        rows = {row['date']: row for row in load('sweep_compact.json')['301']}
        sunday = rows['2026-09-06']
        self.assertEqual(sunday['weekday'], 'Sunday')
        self.assertEqual(sunday['n'], 8)

        for poisoned in ('2026-12-01', '2026-12-08'):
            row = rows[poisoned]
            self.assertEqual(row['weekday'], 'Tuesday')
            self.assertEqual(
                row['ids'], sunday['ids'],
                f'{poisoned} no longer matches the Sunday set',
            )
            # ...and is emphatically NOT the ordinary Tuesday set.
            self.assertNotEqual(row['ids'], rows['2026-09-15']['ids'])

    def test_data_floor_evidence_is_intact(self):
        """98 B1: dates before 2026-07-27 return [] because the feed is empty."""
        rows = {row['date']: row for row in load('sweep_compact.json')['101']}
        for empty in ('2026-04-05', '2026-06-10', '2026-06-11', '2026-06-13'):
            self.assertEqual(rows[empty]['n'], 0, f'{empty} should be empty')

    def test_2027_04_04_is_an_ordinary_sunday(self):
        """Why it is not seeded as a Holiday. 98 claim 10 mislabels it as Easter."""
        rows = {row['date']: row for row in load('sweep_compact.json')['101']}
        self.assertEqual(rows['2027-04-04']['weekday'], 'Sunday')
        self.assertEqual(
            rows['2027-04-04']['ids'], rows['2026-09-06']['ids'],
            'identical to an ordinary Sunday, so it carries no holiday evidence',
        )

    def test_route_id_map_is_intact(self):
        """Route id vs nameShort are different namespaces (01 section 0)."""
        findings = load('findings.json')
        by_line = dict(
            zip(findings['routes_active']['nameShorts'],
                findings['routes_active']['ids'])
        )
        self.assertEqual(len(by_line), 55)
        for line, route_id in (
            ('101', '1'), ('102', '2'), ('112', '9'), ('301', '25'),
            ('307', '31'), ('335', '48'), ('N03', '53'),
        ):
            self.assertEqual(by_line[line], route_id)

    def test_stop_collapse_statistics_are_intact(self):
        """02 section 3.2 sizes the import review queue off these numbers."""
        findings = load('findings.json')
        self.assertEqual(findings['stops_count'], 1456)
        self.assertEqual(findings['distinct_names'], 816)
        sep = findings['duplicate_separation']
        self.assertEqual(sep['gt_75m'], 14, '02 section 3.2 says 14, not 30')
        self.assertEqual(sep['gt_100m'], 3)
        self.assertEqual(sep['gt_250m'], 0)
        self.assertEqual(sep['consecutive_pairs'], 629)
        self.assertEqual(sep['pair_total'], 630)

    def test_isactive_is_a_display_flag(self):
        """98 B5: five routes carry isActive false; 328 is weekend-only."""
        findings = load('findings.json')
        inactive = {r['nameShort'] for r in findings['routes_all']['inactive']}
        self.assertEqual(inactive, {'112', '321', '324', '325', '328'})
