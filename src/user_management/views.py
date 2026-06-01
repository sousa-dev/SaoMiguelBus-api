"""User management views — thin redirects to django-allauth."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


def login(request: HttpRequest) -> HttpResponse:
    """Redirect to the allauth login page, preserving ``?next=``."""
    if request.user.is_authenticated:
        return redirect("index")

    next_url = request.GET.get("next", "")
    login_url = "/accounts/login"
    if next_url:
        login_url = f"{login_url}?next={next_url}"
    return redirect(login_url)


def logout(request: HttpRequest) -> HttpResponse:
    """Redirect to the allauth logout flow."""
    return redirect("/accounts/logout")
