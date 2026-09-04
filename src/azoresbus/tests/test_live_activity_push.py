from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from azoresbus.services_live_activity_push import (
    current_leg,
    has_finished,
    snapshot_from_live_row,
)

TZ = timezone.utc


def at(h: int, m: int) -> datetime:
    return datetime(2026, 9, 2, h, m, tzinfo=TZ)


LEGS = [
    {'tripId': 1936, 'startsAt': at(21, 15).isoformat(), 'endsAt': at(21, 59).isoformat()},
    {'tripId': 2001, 'startsAt': at(22, 10).isoformat(), 'endsAt': at(22, 40).isoformat()},
]


class CurrentLegTests(SimpleTestCase):
    def test_before_everything_returns_the_first_leg(self):
        self.assertEqual(current_leg(LEGS, at(20, 0))['tripId'], 1936)

    def test_inside_a_leg_returns_that_leg(self):
        self.assertEqual(current_leg(LEGS, at(21, 30))['tripId'], 1936)

    def test_in_the_gap_returns_the_upcoming_leg(self):
        self.assertEqual(current_leg(LEGS, at(22, 0))['tripId'], 2001)

    def test_past_everything_returns_the_last_leg(self):
        self.assertEqual(current_leg(LEGS, at(23, 0))['tripId'], 2001)

    def test_empty_legs_is_none(self):
        self.assertIsNone(current_leg([], at(21, 30)))


class HasFinishedTests(SimpleTestCase):
    def test_false_inside_the_grace_window(self):
        self.assertFalse(has_finished(LEGS, at(22, 42), grace_seconds=300))

    def test_true_past_the_grace_window(self):
        self.assertTrue(has_finished(LEGS, at(22, 50), grace_seconds=300))

    def test_empty_legs_is_finished(self):
        self.assertTrue(has_finished([], at(21, 30)))


LEG = LEGS[0]


def live_row(**vehicle_overrides) -> dict:
    vehicle = {
        'id': 'v1', 'position': {'lat': 37.8, 'lon': -25.6}, 'delaySeconds': 240,
        'speed': 30, 'status': 'inTransitTo', 'currentStopSequence': 2,
        'nextStop': {'sequence': 3, 'name': 'Pico da Pedra', 'stopId': 9, 'dueInMinutes': 4},
        'upcomingStops': [{'sequence': 3, 'name': 'Pico da Pedra', 'stopId': 9, 'dueInMinutes': 4}],
        'capturedAt': at(21, 41).isoformat(), 'stale': False,
    }
    vehicle.update(vehicle_overrides)
    return {'tripId': 1936, 'state': 'live', 'vehicle': vehicle}


class SnapshotFromLiveRowTests(SimpleTestCase):
    def test_riding_with_live_next_stop_and_rounded_delay(self):
        snapshot = snapshot_from_live_row(LEG, live_row(), at(21, 45))
        self.assertEqual(snapshot['v'], 1)
        self.assertEqual(snapshot['state'], 'riding')
        self.assertEqual(snapshot['nextStopName'], 'Pico da Pedra')
        self.assertEqual(snapshot['minutesToNextStop'], 4)
        self.assertEqual(snapshot['delayMinutes'], 4)
        self.assertGreater(snapshot['progress'], 0)
        self.assertLess(snapshot['progress'], 1)

    def test_arriving_when_due_imminently(self):
        row = live_row(nextStop={'sequence': 3, 'name': 'Pico da Pedra', 'stopId': 9, 'dueInMinutes': 1})
        snapshot = snapshot_from_live_row(LEG, row, at(21, 45))
        self.assertEqual(snapshot['state'], 'arriving')

    def test_waiting_before_departure_with_no_row(self):
        snapshot = snapshot_from_live_row(LEG, {'tripId': 1936, 'state': 'not_found', 'vehicle': None}, at(21, 0))
        self.assertEqual(snapshot['state'], 'waiting')
        self.assertIsNone(snapshot['nextStopName'])
        self.assertIsNone(snapshot['minutesToNextStop'])
        self.assertEqual(snapshot['progress'], 0)

    def test_completed_past_the_last_stop(self):
        snapshot = snapshot_from_live_row(LEG, None, at(22, 30))
        self.assertEqual(snapshot['state'], 'completed')
        self.assertEqual(snapshot['progress'], 1)

    def test_stale_drops_eta_but_keeps_delay(self):
        row = live_row(stale=True, nextStop=None, upcomingStops=[])
        snapshot = snapshot_from_live_row(LEG, row, at(21, 45))
        self.assertEqual(snapshot['state'], 'stale')
        self.assertIsNone(snapshot['nextStopName'])
        self.assertIsNone(snapshot['minutesToNextStop'])
        self.assertEqual(snapshot['delayMinutes'], 4)

    def test_none_row_while_riding_is_just_unattributed_not_stale(self):
        snapshot = snapshot_from_live_row(LEG, None, at(21, 45))
        self.assertEqual(snapshot['state'], 'riding')
        self.assertIsNone(snapshot['nextStopName'])
