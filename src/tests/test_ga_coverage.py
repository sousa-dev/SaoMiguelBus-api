"""Ensure GA snippet is present on all user-facing surfaces."""

from __future__ import annotations

import unittest

from django.conf import settings
from django.test import TestCase, override_settings

# Each surface below is served by a toggleable app (settings.py's `apps` list).
# Skipped, not deleted, and conditioned on the live toggle rather than a fixed
# `True`/`False`: if the app is switched on, the coverage check resumes without
# anyone having to remember this file exists. `legal` itself is enabled, but its
# template extends one that `{% load tailwind_tags %}`, so it needs `tailwind`.
_LANDING_PAGE_ON = 'landing_page' in settings.INSTALLED_APPS
_TAILWIND_ON = 'tailwind' in settings.INSTALLED_APPS
_STRIPE_ON = 'stripe_payments' in settings.INSTALLED_APPS


@override_settings(
    GOOGLE_ANALYTICS_ID="G-TESTCOVERAGE",
    CONSENT_REQUIRED=False,
    GA_DEBUG_MODE=False,
)
class GACoverageTests(TestCase):
    """Render key pages and assert gtag is loaded."""

    def _assert_has_gtag(self, response) -> None:
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("gtag('config'", content)
        self.assertIn("G-TESTCOVERAGE", content)
        self.assertIn("djast-analytics.js", content)

    @unittest.skipUnless(_LANDING_PAGE_ON, "landing_page app is disabled")
    def test_landing_page(self) -> None:
        response = self.client.get("/")
        self._assert_has_gtag(response)

    @unittest.skipUnless(_TAILWIND_ON, "tailwind app is disabled; legal.html needs its tags")
    def test_legal_privacy(self) -> None:
        response = self.client.get("/legal/privacy-policy/")
        self._assert_has_gtag(response)

    @unittest.skipUnless(_STRIPE_ON, "stripe_payments app is disabled")
    def test_payment_cancelled(self) -> None:
        response = self.client.get("/payment/cancelled/")
        self._assert_has_gtag(response)
