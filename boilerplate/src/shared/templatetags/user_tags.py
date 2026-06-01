"""Custom template tags and filters for user-related display logic.

Load in templates with ``{% load user_tags %}``.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.formats import date_format
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="has_group")
def has_group(user: Any, group_name: str) -> bool:
    """Return ``True`` if *user* belongs to *group_name*."""
    return user.groups.filter(name=group_name).exists()


@register.filter(name="has_permission")
def has_permission(user: Any, permission_codename: str) -> bool:
    """Return ``True`` if *user* has the permission identified by codename."""
    return user.has_perm(permission_codename)


@register.filter(name="full_name")
def full_name(user: Any) -> str:
    """Return the user's full name, falling back to their username."""
    return user.get_full_name() or user.username


@register.filter(name="format_date")
def format_date(value: datetime, format_string: str = "DATE_FORMAT") -> str:
    """Format a datetime using Django's locale-aware ``date_format``."""
    return date_format(value, format_string)


@register.filter(name="jsonify")
def jsonify(value: Any) -> str:
    """Serialize a Python object to a JSON string safe for template embedding."""
    return mark_safe(json.dumps(value, cls=DjangoJSONEncoder))
