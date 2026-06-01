"""Authentication middleware.

Enforces site-wide login when ``AUTHENTICATION_REQUIRED`` is enabled,
with configurable path exclusions.
"""

from __future__ import annotations

from typing import Callable

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from src import settings


class LoginRequiredMiddleware:
    """Redirect unauthenticated users to the login page.

    Paths listed in ``EXCLUDED_EXACT_PATHS`` are matched exactly;
    those in ``EXCLUDED_PATH_PREFIXES`` are matched by prefix.
    """

    EXCLUDED_EXACT_PATHS: list[str] = ["/"]
    EXCLUDED_PATH_PREFIXES: list[str] = [
        "/media/",
        "/login",
        "/accounts",
        "/payment",
        "/legal",
        "/blog/",
        "/tools/",
    ]

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not request.user.is_authenticated and settings.AUTHENTICATION_REQUIRED:
            path = request.path
            if path not in self.EXCLUDED_EXACT_PATHS and not any(
                path.startswith(prefix) for prefix in self.EXCLUDED_PATH_PREFIXES
            ):
                return redirect(f"{reverse('login')}?next={path}")
        return self.get_response(request)
