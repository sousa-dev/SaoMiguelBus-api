"""Seed an example published blog post."""

from __future__ import annotations

import uuid

from django.db import migrations
from django.utils import timezone


POST_BODY = """
<h2>Introduction</h2>
<p>Building a SaaS product from scratch is hard. You spend weeks wiring up authentication,
payment flows, email delivery, background jobs, and legal pages before you write a single
line of product code. That is exactly the problem djast solves.</p>
<p>djast is an AI-native Django 5 boilerplate designed for developers who want to ship
fast. It comes pre-configured with everything a modern SaaS needs — so you can focus on
what makes your product unique instead of reinventing infrastructure.</p>

<h2>Why djast Exists</h2>
<p>Most Django starters give you a bare project with a README and wish you luck. djast
goes further: it ships with production-ready auth (django-allauth with Google and GitHub
OAuth), Stripe Checkout with webhook handling, Celery background tasks with Redis,
Tailwind CSS, legal pages, markdown documentation, brute-force protection via
django-axes, and an agent-ready architecture that AI coding assistants can navigate
without hand-holding.</p>
<p>The goal is simple: go from zero to a deployable SaaS in a weekend, not a month.</p>

<h2>What Is Included Out of the Box</h2>
<h3>Authentication and Security</h3>
<p>Email/password signup, social OAuth (Google, GitHub), password reset, email
verification, and brute-force lockout are all wired up. django-axes protects your
login endpoints from credential stuffing attacks.</p>
<h3>Payments</h3>
<p>Stripe Checkout integration with webhook handlers for subscription lifecycle events.
The service layer pattern keeps payment logic testable and separate from HTTP concerns.</p>
<h3>Background Tasks</h3>
<p>Celery 5.4 with Redis as broker and result backend. Periodic tasks via Celery Beat
with django-celery-beat database scheduler. Every task is designed for idempotency and
retries.</p>
<h3>Frontend</h3>
<p>Tailwind CSS 3.4 with django-tailwind. Separate landing page and authenticated app
themes. Dark-mode landing page with a clean dashboard for logged-in users.</p>
<h3>Content and SEO</h3>
<p>A full blog module with multi-language support, SEO metadata, JSON-LD structured data,
sitemaps, and lead-generation CTAs. A free tools module for developer utilities that
drive organic traffic.</p>
<h3>Developer Experience</h3>
<p>Type hints on every function, Google-style docstrings, service layer pattern, feature
toggles via the apps list in settings.py, Docker Compose for production deployment,
and AGENT_INSTRUCTIONS.md files that teach AI agents how to extend the boilerplate.</p>

<h2>How to Ship in a Weekend</h2>
<p>Here is a realistic timeline for going from clone to deployed SaaS:</p>
<ul>
<li><strong>Hour 1:</strong> Clone the repo, run <code>python setup.py</code>, start
dev servers with <code>python run.py</code>.</li>
<li><strong>Hours 2-4:</strong> Customize branding — logo, colors, landing page copy,
pricing tiers.</li>
<li><strong>Hours 5-8:</strong> Build your core feature as a new Django app. Add models,
services, views, and templates following the existing patterns.</li>
<li><strong>Hours 9-12:</strong> Configure Stripe products, set up Resend for production
email, add your domain.</li>
<li><strong>Hours 13-16:</strong> Write tests, deploy with Docker Compose, configure
monitoring.</li>
</ul>
<p>That is two focused days — not two months of infrastructure work.</p>

<h2>Architecture Highlights</h2>
<p>djast follows a strict service layer pattern. Views are thin HTTP adapters that
parse requests and return responses. All business logic lives in <code>services.py</code>
files that accept typed arguments and return dataclasses. This makes the codebase
testable, readable, and agent-friendly.</p>
<p>Feature toggles in <code>settings.py</code> let you enable or disable entire apps.
URL routing and middleware adapt automatically — no dead code paths cluttering your
project.</p>

<h2>Key Takeaways</h2>
<ul>
<li>djast eliminates weeks of boilerplate setup for Django SaaS products.</li>
<li>Auth, payments, background jobs, email, and legal pages are production-ready.</li>
<li>The service layer pattern and type hints make the codebase maintainable and AI-agent-friendly.</li>
<li>Blog and free tools modules drive organic traffic and lead generation.</li>
<li>Deploy with Docker Compose in minutes — web, worker, beat, postgres, and redis.</li>
</ul>

<h2>Frequently Asked Questions</h2>
<h3>Is djast free?</h3>
<p>djast is open source. Clone it, customize it, ship your product. No license fees,
no vendor lock-in.</p>
<h3>What Python and Django versions does it use?</h3>
<p>Python 3.10+ and Django 5.0.6. All dependencies are pinned in requirements.txt.</p>
<h3>Can I use it for a non-SaaS project?</h3>
<p>Absolutely. Disable the Stripe app in settings.py and you have a solid Django starter
with auth, background tasks, and Tailwind CSS.</p>
<h3>How does the AI-native architecture work?</h3>
<p>Every app includes AGENT_INSTRUCTIONS.md files, coding standards in
.agentic/coding_standards.md, and a service layer that agents can extend without
breaking conventions. Feature toggles mean agents only see the code that is active.</p>
<h3>Does it support multi-language content?</h3>
<p>Yes. Both the blog and free tools modules support translations linked via
translation_group UUIDs with automatic hreflang tag generation.</p>
"""


def seed_example_post(apps, schema_editor) -> None:
    """Create category, tags, and a published welcome blog post."""
    Category = apps.get_model("blog", "Category")
    Tag = apps.get_model("blog", "Tag")
    BlogPost = apps.get_model("blog", "BlogPost")

    category, _ = Category.objects.get_or_create(
        slug="django",
        defaults={
            "name": "Django",
            "description": "Articles about Django development, best practices, and the djast boilerplate.",
        },
    )

    tag_data = [
        ("django", "Django"),
        ("boilerplate", "Boilerplate"),
        ("saas", "SaaS"),
    ]
    tags = []
    for slug, name in tag_data:
        tag, _ = Tag.objects.get_or_create(slug=slug, defaults={"name": name})
        tags.append(tag)

    post, created = BlogPost.objects.get_or_create(
        slug="welcome-to-djast",
        language="en",
        defaults={
            "title": "Welcome to djast — the AI-native Django SaaS boilerplate",
            "body": POST_BODY.strip(),
            "excerpt": (
                "djast is an AI-native Django 5 boilerplate that ships with auth, "
                "Stripe payments, Celery, Tailwind CSS, and agent-ready architecture. "
                "Go from zero to deployed SaaS in a weekend."
            ),
            "meta_title": "Welcome to djast — Django SaaS Boilerplate",
            "meta_description": (
                "Discover djast, the AI-native Django 5 SaaS boilerplate with auth, "
                "Stripe, Celery, Tailwind, and agent-ready architecture. Ship in a weekend."
            ),
            "focus_keyword": "django saas boilerplate",
            "category": category,
            "status": "published",
            "published_at": timezone.now(),
            "translation_group": uuid.uuid4(),
            "cta_text": "Get started with djast",
            "cta_url": "/accounts/signup/",
            "lead_magnet_title": "",
        },
    )

    if created:
        post.tags.set(tags)
        post.word_count = len(post.body.split())
        post.save(update_fields=["word_count"])


def remove_example_post(apps, schema_editor) -> None:
    """Remove seeded blog content."""
    Category = apps.get_model("blog", "Category")
    Tag = apps.get_model("blog", "Tag")
    BlogPost = apps.get_model("blog", "BlogPost")

    BlogPost.objects.filter(slug="welcome-to-djast", language="en").delete()
    Tag.objects.filter(slug__in=["django", "boilerplate", "saas"]).delete()
    Category.objects.filter(slug="django").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_example_post, remove_example_post),
    ]
