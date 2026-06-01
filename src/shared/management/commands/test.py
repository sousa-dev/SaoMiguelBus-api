"""Run pytest when ``manage.py test`` is invoked."""

from __future__ import annotations

import subprocess
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Show a deprecation notice, then delegate to pytest."""

    help = "Run the pytest suite (preferred: pytest directly from src/)."

    def add_arguments(self, parser) -> None:
        """Accept optional paths/flags to forward to pytest after ``--``."""
        parser.add_argument(
            "pytest_args",
            nargs="*",
            help="Optional paths or pytest flags (use -- before flags, e.g. test -- -q).",
        )

    def handle(self, *args: object, **options: object) -> None:
        """Print a short notice and run pytest with any forwarded arguments."""
        self.stderr.write(
            self.style.WARNING(
                "manage.py test runs pytest in djast. "
                "Prefer: cd src && pytest\n"
            )
        )

        try:
            import pytest  # noqa: F401
        except ImportError:
            self.stderr.write(
                self.style.ERROR(
                    "pytest is not installed. Install dev dependencies:\n"
                    "  pip install -r requirements-dev.txt\n"
                )
            )
            sys.exit(1)

        pytest_args = list(options.get("pytest_args") or [])

        result = subprocess.run(
            [sys.executable, "-m", "pytest", *pytest_args],
            check=False,
        )
        sys.exit(result.returncode)
