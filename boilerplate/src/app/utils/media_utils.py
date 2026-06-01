"""Utilities for serving media files."""

from __future__ import annotations

import mimetypes
import os

from django.http import FileResponse, HttpResponse, JsonResponse

from src import settings


def get_media(path: str) -> HttpResponse:
    """Return a ``FileResponse`` for the requested media path.

    Args:
        path: Relative path under ``MEDIA_ROOT``.

    Returns:
        A streaming ``FileResponse`` on success or a JSON 404.
    """
    file_path = os.path.join(settings.MEDIA_ROOT, path)
    if not os.path.exists(file_path):
        return JsonResponse({"error": "File not found"}, status=404)

    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = "application/octet-stream"

    file = open(file_path, "rb")
    response = FileResponse(file, content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{os.path.basename(file_path)}"'
    return response
