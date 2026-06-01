"""User management signals.

Populates the user's email from GitHub OAuth ``extra_data`` on first signup.
"""

from __future__ import annotations

import logging

from allauth.account.models import EmailAddress
from allauth.account.signals import user_signed_up
from django.conf import settings
from django.dispatch import receiver

if "allauth.socialaccount" in settings.INSTALLED_APPS:
    from allauth.socialaccount.models import SocialAccount

logger = logging.getLogger(__name__)


@receiver(user_signed_up)
def populate_user_email_from_github(sender: type, request: object, user: object, **kwargs: object) -> None:
    """On GitHub signup, copy the primary verified email to the Django user."""
    social_account = SocialAccount.objects.filter(user=user, provider="github").first()
    if not social_account:
        return

    emails = social_account.extra_data.get("emails", [])
    if not emails:
        email = social_account.extra_data.get("email")
        if email:
            emails = [{"email": email, "primary": True, "verified": True}]

    if not isinstance(emails, list):
        return

    primary_email = next(
        (e for e in emails if e.get("primary") and e.get("verified")),
        None,
    )
    if primary_email:
        user_email = primary_email["email"]
        user.email = user_email
        user.save()
        EmailAddress.objects.update_or_create(
            user=user,
            email=user_email,
            defaults={"verified": True, "primary": True},
        )
