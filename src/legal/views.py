"""Legal page views.

Renders privacy policy, terms of service, and license pages from JSON
data files located in ``legal/data/``.
"""

from __future__ import annotations

import json
import os
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from src import settings


def privacy_policy(request: HttpRequest) -> HttpResponse:
    """Render the privacy policy page."""
    return _legal_page(request, "privacy_policy")


def terms_of_service(request: HttpRequest) -> HttpResponse:
    """Render the terms of service page."""
    return _legal_page(request, "terms_of_service")


def licenses(request: HttpRequest) -> HttpResponse:
    """Render the licenses page."""
    return _legal_page(request, "licenses")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _legal_page(request: HttpRequest, slug: str) -> HttpResponse:
    """Load a legal JSON document and render it with contact info."""
    context = _load_legal_content(slug)
    contact = _load_json("contact_info")
    context.update(contact)
    context["product_name"] = settings.PROJECT_NAME
    return render(request, "legal/legal.html", context)


def _data_path(filename: str) -> str:
    return os.path.join(settings.BASE_DIR, "legal", "data", f"{filename}.json")


def _load_json(filename: str) -> dict[str, Any]:
    with open(_data_path(filename), "r") as fh:
        return json.load(fh)


def _load_legal_content(filename: str) -> dict[str, Any]:
    content = _load_json(filename)
    for section in content.get("sections", []):
        section["content"] = _join_content(section["content"])
        for subsection in section.get("subsections", []):
            subsection["content"] = _join_content(subsection["content"])
    return content


def _join_content(content: str | list[str]) -> str:
    if isinstance(content, list):
        return " ".join(content)
    return content
