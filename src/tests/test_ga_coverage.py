"""Ensure GA snippet is present on all user-facing surfaces."""

from __future__ import annotations

from django.test import TestCase, override_settings


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

    def test_landing_page(self) -> None:
        response = self.client.get("/")
        self._assert_has_gtag(response)

    def test_legal_privacy(self) -> None:
        response = self.client.get("/legal/privacy-policy/")
        self._assert_has_gtag(response)

    def test_payment_cancelled(self) -> None:
        response = self.client.get("/payment/cancelled/")
        self._assert_has_gtag(response)
