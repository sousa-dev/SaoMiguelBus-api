"""Seed the Django Secret Key Generator free tool."""

from __future__ import annotations

import uuid

from django.db import migrations
from django.utils import timezone


def seed_secret_key_generator(apps, schema_editor) -> None:
    """Create Security category and the secret key generator tool."""
    ToolCategory = apps.get_model("free_tools", "ToolCategory")
    FreeTool = apps.get_model("free_tools", "FreeTool")

    category, _ = ToolCategory.objects.get_or_create(
        slug="security",
        defaults={
            "name": "Security",
            "description": "Security utilities for developers — key generators, validators, and more.",
            "icon_class": "fas fa-shield-alt",
        },
    )

    description = """
<h2>What is the Django Secret Key Generator?</h2>
<p>Every Django project needs a cryptographically secure <code>SECRET_KEY</code> in settings.
This free online tool generates one instantly using your browser's built-in
<code>crypto.getRandomValues()</code> API — no server round-trip, no data stored.</p>

<h2>How to Use</h2>
<p>Select your desired key length (50 characters is the Django default), click
<strong>Generate</strong>, then copy the key into your <code>.env</code> file as
<code>SECRET_KEY=your-key-here</code>.</p>

<h2>Why You Need a Strong Secret Key</h2>
<p>Django uses <code>SECRET_KEY</code> for session signing, CSRF tokens, password
reset tokens, and cryptographic signing. A weak or leaked key compromises your
entire application. Never commit it to version control — always load it from
environment variables.</p>

<h2>Frequently Asked Questions</h2>
<h3>Is this tool free?</h3>
<p>Yes, completely free with no signup required.</p>
<h3>Is my data safe?</h3>
<p>All processing happens in your browser. No data is sent to our servers.</p>
<h3>What length should I use?</h3>
<p>50 characters is the Django default and is sufficient for most projects.
Use 64 or 128 for extra entropy in high-security environments.</p>
"""

    FreeTool.objects.get_or_create(
        slug="django-secret-key-generator",
        language="en",
        defaults={
            "name": "Django Secret Key Generator",
            "tagline": "Generate a cryptographically secure Django SECRET_KEY instantly.",
            "description": description.strip(),
            "template_name": "free_tools/tools/secret_key_generator.html",
            "meta_title": "Django Secret Key Generator - Free Online",
            "meta_description": "Generate a secure Django SECRET_KEY instantly. Free, no signup, runs in your browser. Copy and paste into your .env file.",
            "focus_keyword": "django secret key generator",
            "icon_class": "fas fa-key",
            "category": category,
            "status": "published",
            "published_at": timezone.now(),
            "sort_order": 10,
            "translation_group": uuid.uuid4(),
            "cta_text": "Build faster with djast",
            "cta_url": "https://djast.dev",
            "lead_magnet_title": "djast — Django SaaS Boilerplate",
        },
    )


def remove_secret_key_generator(apps, schema_editor) -> None:
    """Remove seeded tool and category if no other tools reference it."""
    ToolCategory = apps.get_model("free_tools", "ToolCategory")
    FreeTool = apps.get_model("free_tools", "FreeTool")

    FreeTool.objects.filter(slug="django-secret-key-generator", language="en").delete()
    ToolCategory.objects.filter(slug="security").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("free_tools", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_secret_key_generator, remove_secret_key_generator),
    ]
