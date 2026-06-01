"""Media file serving views."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_GET

from app.utils.media_utils import get_media


@require_GET
def fetch_media(request: HttpRequest, path: str) -> HttpResponse:
    """Serve a file from ``MEDIA_ROOT`` with correct MIME type."""
    return get_media(path)
