"""Create a Django superuser from DB_USER / DB_PASSWORD when not already present."""

from __future__ import annotations

from decouple import config
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Ensure a superuser exists using credentials from the environment."""

    help = (
        "Create a superuser from DB_USER and DB_PASSWORD when both are set "
        "and no user with that username exists."
    )

    def handle(self, *args: object, **options: object) -> None:
        """Create the superuser or no-op when vars are unset or user exists."""
        username = config('DB_USER', default='').strip()
        password = config('DB_PASSWORD', default='')

        if not username or not password:
            self.stdout.write(
                'Skipping superuser bootstrap (DB_USER and DB_PASSWORD must both be set).',
            )
            return

        user_model = get_user_model()
        if user_model.objects.filter(username=username).exists():
            self.stdout.write(f'Superuser "{username}" already exists; skipping.')
            return

        email = config('SUPERUSER_EMAIL', default=f'{username}@localhost').strip()
        user_model.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f'Created superuser "{username}".'))
