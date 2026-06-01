"""Tests for global context processors."""

from __future__ import annotations

from django.http import HttpRequest
from django.test import RequestFactory, SimpleTestCase, override_settings

from context_processors import _resolve_page_type, analytics_context
from shared.analytics import PAGE_TYPES


class ResolvePageTypeTests(SimpleTestCase):
    """URL name → page_type mapping."""

    def test_blog_post_detail(self) -> None:
        self.assertEqual(
            _resolve_page_type("post_detail", "blog"),
            PAGE_TYPES.BLOG_POST,
        )

    def test_free_tool_detail(self) -> None:
        self.assertEqual(
            _resolve_page_type("tool_detail", "free_tools"),
            PAGE_TYPES.TOOL,
        )

    def test_unknown_without_match(self) -> None:
        self.assertEqual(_resolve_page_type(None, None), PAGE_TYPES.UNKNOWN)


@override_settings(
    GOOGLE_ANALYTICS_ID="G-TEST123",
    CONSENT_REQUIRED=False,
    GA_DEBUG_MODE=True,
)
class AnalyticsContextTests(SimpleTestCase):
    """analytics_context processor output."""

    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_injects_ga_settings(self) -> None:
        request = self.factory.get("/blog/my-post/")
        request.user = type("U", (), {"is_authenticated": False})()
        request.resolver_match = type(
            "M",
            (),
            {"url_name": "post_detail", "namespace": "blog"},
        )()
        ctx = analytics_context(request)
        self.assertEqual(ctx["GOOGLE_ANALYTICS_ID"], "G-TEST123")
        self.assertFalse(ctx["CONSENT_REQUIRED"])
        self.assertTrue(ctx["GA_DEBUG_MODE"])
        self.assertEqual(ctx["GA_PAGE"]["page_type"], PAGE_TYPES.BLOG_POST)
        self.assertIn("page_type", ctx["GA_PAGE_JSON"])
