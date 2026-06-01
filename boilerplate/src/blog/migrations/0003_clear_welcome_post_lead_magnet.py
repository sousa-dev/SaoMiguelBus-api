"""Remove misleading lead magnet label from the welcome blog post."""

from __future__ import annotations

from django.db import migrations


def clear_lead_magnet(apps, schema_editor) -> None:
    """Clear lead_magnet_title so the CTA is not labeled as a free resource."""
    BlogPost = apps.get_model("blog", "BlogPost")
    BlogPost.objects.filter(slug="welcome-to-djast", language="en").update(
        lead_magnet_title="",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0002_seed_example_post"),
    ]

    operations = [
        migrations.RunPython(clear_lead_magnet, migrations.RunPython.noop),
    ]
