"""U4 task test: the Celery task drives the lifecycle transitions."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from tenancy.services import for_island, get_or_create_default_island
from traffic.models import TrafficCategory, TrafficReport
from traffic.tasks import run_lifecycle_task

pytestmark = pytest.mark.django_db


def test_run_lifecycle_task_transitions():
    island = get_or_create_default_island()
    now = timezone.now()
    with for_island(island):
        cat = TrafficCategory.objects.create(
            island=island, name='Radar', slug='radar', is_schedulable=True,
        )
        due = TrafficReport.objects.create(
            island=island, category=cat, latitude=37.78, longitude=-25.50,
            status=TrafficReport.SCHEDULED, active_from=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=1),
        )
        stale = TrafficReport.objects.create(
            island=island, category=cat, latitude=37.78, longitude=-25.50,
            status=TrafficReport.ACTIVE, expires_at=now - timedelta(minutes=1),
        )

    result = run_lifecycle_task()

    assert result['status'] == 'ok'
    assert TrafficReport.objects.unscoped().get(id=due.id).status == TrafficReport.ACTIVE
    assert TrafficReport.objects.unscoped().get(id=stale.id).status == TrafficReport.EXPIRED
