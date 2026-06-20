"""Marketplace authorization helpers."""

from __future__ import annotations

from rest_framework.request import Request


def is_marketplace_superuser(request: Request) -> bool:
    user = getattr(request, 'user', None)
    return bool(user and user.is_authenticated and user.is_superuser)
