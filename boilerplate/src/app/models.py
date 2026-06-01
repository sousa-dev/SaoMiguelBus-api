"""Application models.

Add your project-specific models here. Each model should include:

* A descriptive docstring.
* Type-annotated fields with ``help_text`` for admin and agent readability.
* A ``__str__`` method returning a human-readable representation.
* An inner ``Meta`` class with ordering and/or indexes where appropriate.

Example::

    class Project(models.Model):
        \"\"\"A user-owned project.\"\"\"

        name = models.CharField(max_length=120, help_text="Display name.")
        owner = models.ForeignKey(
            settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
            related_name="projects",
        )
        created_at = models.DateTimeField(auto_now_add=True)

        class Meta:
            ordering = ["-created_at"]

        def __str__(self) -> str:
            return self.name
"""

from __future__ import annotations

from django.db import models  # noqa: F401 — keep for subclass convenience
