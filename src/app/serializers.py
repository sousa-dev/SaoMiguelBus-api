"""DRF serializers for the ``app`` module.

Define your API serializers here. Each serializer should include:

* A descriptive docstring.
* Explicit ``fields`` in the ``Meta`` class (avoid ``__all__``).
* Validation methods with type hints.

Example::

    class ProjectSerializer(serializers.ModelSerializer):
        \"\"\"Read/write serializer for :class:`app.models.Project`.\"\"\"

        class Meta:
            model = Project
            fields = ["id", "name", "owner", "created_at"]
            read_only_fields = ["id", "created_at"]
"""

from __future__ import annotations

from rest_framework import serializers  # noqa: F401 — keep for subclass convenience
