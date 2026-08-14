"""The behavioural gate for the AzoresBus changeover.

Current ``search_routes`` behaviour must equal the frozen S0 baseline
(``search_snapshot_s0.json``) EXCEPT for changes declared in ``INTENDED_DIFFS``.

Three changes are planned and will alter results:

  1. the holiday seed          (S0b)
  2. the boarding-time filter  (S3, 02 section 3.4)
  3. sequence-based pair matching, which also resolves stops by id instead of
     fuzzy substring                (S3, 98 B7)

Each one is added here as an explicit entry stating the exact new output and
citing its source. Anything else that moves is a bug, and this test is what
makes that enforceable rather than aspirational.

Adding an entry is a deliberate, reviewable act. Re-recording the golden file
instead of adding an entry defeats the whole mechanism — do not do it.
"""

from __future__ import annotations

from django.test import TestCase

from transit.tests.test_search_snapshot import collect_snapshot, load_golden


# query key -> {'reason': str, 'source': str, 'results': <exact new output>}
#
# Each stage that changes behaviour adds its entries here, stating the exact new
# output. "This query is allowed to change" is not good enough -- the new value is
# declared so a second, unrelated change to the same query still fails.
INTENDED_DIFFS: dict[str, dict] = {
    # ---- Intended diff #1: the holiday seed (S0b) ----
    'christmas_2026': {
        'reason': (
            '2026-12-25 now resolves to SUNDAY service instead of WEEKDAY. Before '
            'the seed the Holiday table stopped at 2025-06-19, so every date in '
            'the changeover window evaluated as "not a holiday" and search '
            'diverged from upstream, which returns the Sunday set on that date.'
        ),
        'source': '00 prerequisite; 98 claim 10; 98 B6',
        'results': [
            {
                'id': 'plain_sunday',
                'route': 'SNAP-SUN',
                'origin': 'HOTEL',
                'destination': 'INDIA',
                'start': '11h00',
                'end': '11h30',
                'stops': "{'HOTEL': '11h00', 'INDIA': '11h30'}",
                'type_of_day': 'SUNDAY',
                'information': {},
                'likes_percent': 0,
                'dislikes_percent': 0,
            }
        ],
    },
}


class SearchBehaviourDiffTests(TestCase):
    def test_only_intended_diffs_against_s0_baseline(self):
        current = collect_snapshot()
        golden = load_golden()

        unexpected: list[str] = []
        for key in sorted(golden):
            expected = (
                INTENDED_DIFFS[key]['results']
                if key in INTENDED_DIFFS
                else golden[key]
            )
            if current[key] != expected:
                label = 'declared diff' if key in INTENDED_DIFFS else 'S0 baseline'
                unexpected.append(
                    f'\n  {key}: does not match its {label}'
                    f'\n    expected: {expected}'
                    f'\n    actual:   {current[key]}'
                )

        self.assertEqual(
            unexpected,
            [],
            'search_routes behaviour moved in a way nobody declared.'
            + ''.join(unexpected)
            + '\n\nIf this change is intended, add an INTENDED_DIFFS entry with a '
            'reason and a source citation. Do not re-record the S0 golden.',
        )

    def test_every_declared_diff_actually_differs(self):
        """A stale entry — one whose output now matches the baseline — is a lie.

        It would silently grant permission for that query to change again later.
        """
        golden = load_golden()
        stale = [
            key
            for key, entry in INTENDED_DIFFS.items()
            if entry['results'] == golden.get(key)
        ]
        self.assertEqual(
            stale,
            [],
            f'INTENDED_DIFFS entries no longer differ from the S0 baseline: {stale}. '
            'Remove them so they stop granting blanket permission to change.',
        )

    def test_every_declared_diff_is_documented(self):
        undocumented = [
            key
            for key, entry in INTENDED_DIFFS.items()
            if not entry.get('reason') or not entry.get('source')
        ]
        self.assertEqual(
            undocumented,
            [],
            f'INTENDED_DIFFS entries missing a reason or source: {undocumented}.',
        )

    def test_declared_diffs_reference_real_queries(self):
        golden = load_golden()
        unknown = [key for key in INTENDED_DIFFS if key not in golden]
        self.assertEqual(
            unknown,
            [],
            f'INTENDED_DIFFS references queries not in the baseline: {unknown}.',
        )
