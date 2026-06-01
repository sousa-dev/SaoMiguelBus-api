"""Tests for ensure_superuser management command."""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

@pytest.mark.django_db
def test_skips_when_db_credentials_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Command no-ops when DB_USER or DB_PASSWORD is empty."""
    monkeypatch.setenv('DB_USER', '')
    monkeypatch.setenv('DB_PASSWORD', '')

    out = StringIO()
    call_command('ensure_superuser', stdout=out)

    assert 'Skipping superuser bootstrap' in out.getvalue()
    assert get_user_model().objects.filter(is_superuser=True).count() == 0


@pytest.mark.django_db
def test_creates_superuser_from_db_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Command creates a superuser when DB_USER and DB_PASSWORD are set."""
    monkeypatch.setenv('DB_USER', 'deploy-admin')
    monkeypatch.setenv('DB_PASSWORD', 'deploy-secret')
    monkeypatch.setenv('SUPERUSER_EMAIL', 'admin@staging.example')

    out = StringIO()
    call_command('ensure_superuser', stdout=out)

    user = get_user_model().objects.get(username='deploy-admin')
    assert user.is_superuser is True
    assert user.email == 'admin@staging.example'
    assert user.check_password('deploy-secret')
    assert 'Created superuser' in out.getvalue()


@pytest.mark.django_db
def test_does_not_recreate_existing_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Command is idempotent when the username already exists."""
    user_model = get_user_model()
    user_model.objects.create_superuser(
        username='deploy-admin',
        email='existing@example.com',
        password='original',
    )

    monkeypatch.setenv('DB_USER', 'deploy-admin')
    monkeypatch.setenv('DB_PASSWORD', 'new-password')

    out = StringIO()
    call_command('ensure_superuser', stdout=out)

    user = user_model.objects.get(username='deploy-admin')
    assert user.check_password('original')
    assert 'already exists' in out.getvalue()
