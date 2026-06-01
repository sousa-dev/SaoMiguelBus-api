"""Tests for shared analytics constants."""

from __future__ import annotations

import unittest

from shared.analytics import ALL_EVENT_NAMES, EVENT_NAMES, MAX_PARAM_NAME_LENGTH


class AnalyticsConstantsTests(unittest.TestCase):
    """Validate GA4 event name constants."""

    def test_event_names_are_snake_case(self) -> None:
        for name in ALL_EVENT_NAMES:
            self.assertRegex(name, r"^[a-z][a-z0-9_]*$", msg=name)

    def test_event_names_within_ga4_param_limit(self) -> None:
        for name in ALL_EVENT_NAMES:
            self.assertLessEqual(len(name), MAX_PARAM_NAME_LENGTH, msg=name)

    def test_recommended_events_present(self) -> None:
        self.assertEqual(EVENT_NAMES.PURCHASE, "purchase")
        self.assertEqual(EVENT_NAMES.BEGIN_CHECKOUT, "begin_checkout")
        self.assertEqual(EVENT_NAMES.LOGIN, "login")
        self.assertEqual(EVENT_NAMES.SIGN_UP, "sign_up")
