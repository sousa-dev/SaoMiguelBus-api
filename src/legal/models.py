"""Legal app models.

Legal content is driven by JSON data files rather than database records.
Add models here only if you need to store legal consent or audit records.
"""

from __future__ import annotations

from django.db import models  # noqa: F401 — keep for subclass convenience
