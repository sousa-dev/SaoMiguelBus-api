"""02 section 4.5: a 200 with a partial list looks exactly like a deletion.

The sync retires service by closing its window rather than deleting trips, so
ids, votes and observation history survive. But closing every window on a bad
sample is just as destructive as deleting, so the same gate guards both.
"""

from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase

from azoresbus.services_sync import RetirementDecision, evaluate_retirement


TERM_WEEK = [date(2026, 9, day) for day in range(14, 21)]
SUMMER = [date(2027, 7, day) for day in range(6, 13)]


def decision(**overrides) -> RetirementDecision:
    kwargs = {
        'status': 'completed',
        'journey_count': 989,
        'previous_journey_count': 989,
        'sampled_dates': TERM_WEEK,
        'far_season_dates': SUMMER,
        'floor': 0.10,
    }
    kwargs.update(overrides)
    return evaluate_retirement(**kwargs)


class GateTests(SimpleTestCase):
    def test_a_clean_run_may_retire(self):
        self.assertTrue(decision().allowed)

    def test_partial_run_never_retires(self):
        """Budget cap, abort, or consecutive failures all land here."""
        result = decision(status='partial')
        self.assertFalse(result.allowed)
        self.assertIn('partial', result.reason)

    def test_a_drop_beyond_the_floor_blocks_retirement(self):
        result = decision(journey_count=840)          # -15%
        self.assertFalse(result.allowed)
        self.assertIn('floor', result.reason)

    def test_a_drop_within_the_floor_is_allowed(self):
        """The network legitimately changes size across the term boundary."""
        result = decision(journey_count=int(989 * 0.95))
        self.assertTrue(result.allowed)

    def test_growth_is_always_allowed(self):
        self.assertTrue(decision(journey_count=1200).allowed)

    def test_an_empty_sample_never_retires(self):
        result = decision(journey_count=0)
        self.assertFalse(result.allowed)
        self.assertIn('empty', result.reason)

    def test_first_ever_run_may_retire_nothing(self):
        """No baseline to compare against, so nothing is evidence of removal."""
        result = decision(previous_journey_count=None)
        self.assertFalse(result.allowed)
        self.assertIn('baseline', result.reason)

    def test_missing_far_season_evidence_blocks_retirement(self):
        """98 B0: out of season is not deleted.

        Without a far-season observation set the run cannot tell a school run
        that ended from one that is simply out of term.
        """
        result = decision(far_season_dates=[])
        self.assertFalse(result.allowed)
        self.assertIn('far season', result.reason)


class ScopeTests(SimpleTestCase):
    def test_retirement_is_scoped_to_the_dates_actually_sampled(self):
        result = decision()
        self.assertEqual(result.scope_dates, set(TERM_WEEK) | set(SUMMER))

    def test_a_journey_seen_only_in_the_far_season_is_not_retired(self):
        """The specific way a term/summer split can delete half the network."""
        result = decision(sampled_dates=TERM_WEEK, far_season_dates=SUMMER)
        self.assertTrue(result.allowed)
        self.assertIn(
            SUMMER[0], result.scope_dates,
            'the far season must be in scope, or its journeys look deleted',
        )


class ReasonTests(SimpleTestCase):
    def test_every_refusal_explains_itself(self):
        for kwargs in (
            {'status': 'partial'},
            {'journey_count': 100},
            {'journey_count': 0},
            {'previous_journey_count': None},
            {'far_season_dates': []},
        ):
            result = decision(**kwargs)
            self.assertFalse(result.allowed)
            self.assertTrue(
                result.reason,
                f'{kwargs} refused without a reason -- SyncRun.stats needs one',
            )

    def test_the_decision_is_serialisable_for_syncrun_stats(self):
        payload = decision(status='partial').as_dict()
        self.assertEqual(payload['allowed'], False)
        self.assertIn('reason', payload)
        self.assertIsInstance(payload['scope_dates'], list)
