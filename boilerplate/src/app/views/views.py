"""Core application views."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def index(request: HttpRequest) -> HttpResponse:
    """Render the main application dashboard / home page."""
    return render(request, "app/index.html")


def product(request: HttpRequest) -> HttpResponse:
    """Render the product detail page."""
    return render(request, "app/product/product_page.html")
