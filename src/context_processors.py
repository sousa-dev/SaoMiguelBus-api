"""Global template context processors.

These inject project-wide variables into every template render context.
Registered in ``settings.TEMPLATES[0]['OPTIONS']['context_processors']``.
"""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.http import HttpRequest

from shared.analytics import PAGE_TYPES


def project_name(request: HttpRequest) -> dict[str, Any]:
    """Inject ``PROJECT_NAME`` into the template context."""
    return {"PROJECT_NAME": settings.PROJECT_NAME}


def _resolve_page_type(url_name: str | None, namespace: str | None) -> str:
    """Map Django URL resolver metadata to a GA4 ``page_type`` dimension."""
    if not url_name:
        return PAGE_TYPES.UNKNOWN

    ns = namespace or ""

    if ns == "blog":
        if url_name == "post_detail":
            return PAGE_TYPES.BLOG_POST
        if url_name in ("post_list",):
            return PAGE_TYPES.BLOG_LIST
        return PAGE_TYPES.BLOG_ARCHIVE

    if ns == "free_tools":
        if url_name == "tool_detail":
            return PAGE_TYPES.TOOL
        if url_name == "tool_index":
            return PAGE_TYPES.TOOL_INDEX
        return PAGE_TYPES.TOOL_ARCHIVE

    if ns == "documentation" or url_name in ("docs", "docs_search"):
        return PAGE_TYPES.DOCS

    if ns == "legal" or url_name in (
        "privacy_policy",
        "terms_of_service",
        "licenses",
    ):
        return PAGE_TYPES.LEGAL

    if url_name in ("payment", "success", "cancel") or ns == "stripe_payments":
        return PAGE_TYPES.PAYMENT

    if url_name in (
        "account_login",
        "account_signup",
        "account_logout",
        "account_reset_password",
        "account_reset_password_done",
        "account_reset_password_from_key",
        "account_email_verification_sent",
        "socialaccount_login",
        "socialaccount_signup",
    ) or url_name.startswith("account_") or url_name.startswith("socialaccount_"):
        return PAGE_TYPES.AUTH

    if url_name in ("landing_page", "index") and ns in ("", "landing_page"):
        return PAGE_TYPES.LANDING

    if url_name in ("index", "product") and ns in ("", "app"):
        return PAGE_TYPES.APP

    if url_name == "landing_page":
        return PAGE_TYPES.LANDING

    return PAGE_TYPES.UNKNOWN


def analytics_context(request: HttpRequest) -> dict[str, Any]:
    """Inject GA4 settings, page metadata, and consent flags."""
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match else None
    namespace = match.namespace if match else None

    ga_page: dict[str, Any] = {
        "page_type": _resolve_page_type(url_name, namespace),
        "page_section": "",
        "url_name": url_name or "",
        "user_authenticated": request.user.is_authenticated,
    }

    return {
        "GOOGLE_ANALYTICS_ID": settings.GOOGLE_ANALYTICS_ID,
        "CONSENT_REQUIRED": settings.CONSENT_REQUIRED,
        "GA_DEBUG_MODE": settings.GA_DEBUG_MODE,
        "GA_PAGE": ga_page,
        "GA_PAGE_JSON": json.dumps(ga_page, separators=(",", ":")),
    }


def google_analytics_id(request: HttpRequest) -> dict[str, Any]:
    """Backward-compatible alias for ``analytics_context``."""
    return analytics_context(request)
