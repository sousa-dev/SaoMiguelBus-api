"""U2 service tests: create/lifecycle/voting/geo/ownership."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from tenancy.services import for_island, get_or_create_default_island
from traffic import services
from traffic.models import TrafficCategory, TrafficReport

pytestmark = pytest.mark.django_db


def _island():
    island = get_or_create_default_island()
    # center 37.782213, -25.499806, radius 50km
    return island


def _category(island, slug='acidente', ttl=120, schedulable=False):
    return TrafficCategory.objects.create(
        island=island, name=slug.title(), slug=slug,
        default_ttl_minutes=ttl, is_schedulable=schedulable,
    )


def test_create_report_is_active_immediately():
    island = _island()
    with for_island(island):
        _category(island)
        payload = services.create_report(
            island=island, session_hash='a', category_slug='acidente',
            latitude=37.78, longitude=-25.50,
        )
        assert payload['status'] == TrafficReport.ACTIVE
        listed = services.list_reports()
    assert any(r['id'] == payload['id'] for r in listed)


def test_create_scheduled_radar_hidden_by_default():
    island = _island()
    with for_island(island):
        _category(island, slug='radar', schedulable=True)
        future = timezone.now() + timedelta(hours=3)
        payload = services.create_report(
            island=island, session_hash='a', category_slug='radar',
            latitude=37.78, longitude=-25.50, active_from=future,
        )
        assert payload['status'] == TrafficReport.SCHEDULED
        assert all(r['id'] != payload['id'] for r in services.list_reports())
        assert any(
            r['id'] == payload['id']
            for r in services.list_reports(include_scheduled=True)
        )


def test_scheduling_rejected_on_non_schedulable_category():
    island = _island()
    with for_island(island):
        _category(island, slug='acidente')
        with pytest.raises(services.SchedulingNotAllowed):
            services.create_report(
                island=island, session_hash='a', category_slug='acidente',
                latitude=37.78, longitude=-25.50,
                active_from=timezone.now() + timedelta(hours=1),
            )


def test_location_implausible_outside_radius():
    island = _island()
    with for_island(island):
        _category(island)
        with pytest.raises(services.LocationImplausible):
            services.create_report(
                island=island, session_hash='a', category_slug='acidente',
                latitude=40.0, longitude=-8.0,  # mainland Portugal
            )


def test_unknown_category_raises():
    island = _island()
    with for_island(island):
        with pytest.raises(services.CategoryNotFound):
            services.create_report(
                island=island, session_hash='a', category_slug='nope',
                latitude=37.78, longitude=-25.50,
            )


def test_confirm_still_there_extends_and_counts():
    island = _island()
    with for_island(island):
        _category(island, ttl=120)
        created = services.create_report(
            island=island, session_hash='a', category_slug='acidente',
            latitude=37.78, longitude=-25.50,
        )
        before = TrafficReport.objects.get(id=created['id']).expires_at
        result = services.upsert_confirmation(
            report_id=created['id'], session_hash='voter1', vote='still_there'
        )
        payload, was_created = result
        assert was_created is True
        assert payload['confidence']['confirm'] == 1
        after = TrafficReport.objects.get(id=created['id']).expires_at
        assert after > before


def test_confirm_upsert_one_per_session():
    island = _island()
    with for_island(island):
        _category(island)
        created = services.create_report(
            island=island, session_hash='a', category_slug='acidente',
            latitude=37.78, longitude=-25.50,
        )
        services.upsert_confirmation(report_id=created['id'], session_hash='v', vote='still_there')
        _, was_created = services.upsert_confirmation(
            report_id=created['id'], session_hash='v', vote='gone'
        )
        assert was_created is False
        report = TrafficReport.objects.get(id=created['id'])
        assert report.confirm_count == 0
        assert report.deny_count == 1


def test_deny_threshold_expires_report():
    island = _island()
    with for_island(island):
        _category(island)
        created = services.create_report(
            island=island, session_hash='a', category_slug='acidente',
            latitude=37.78, longitude=-25.50,
        )
        for i in range(services.DENY_THRESHOLD):
            services.upsert_confirmation(
                report_id=created['id'], session_hash=f'v{i}', vote='gone'
            )
        assert TrafficReport.objects.get(id=created['id']).status == TrafficReport.EXPIRED


def test_list_reports_radius_filters_and_sorts():
    island = _island()
    with for_island(island):
        _category(island)
        near = services.create_report(
            island=island, session_hash='a', category_slug='acidente',
            latitude=37.783, longitude=-25.50,
        )
        far = services.create_report(
            island=island, session_hash='b', category_slug='acidente',
            latitude=37.85, longitude=-25.40,
        )
        results = services.list_reports(lat=37.782, lng=-25.499, radius_km=2)
        ids = [r['id'] for r in results]
        assert near['id'] in ids
        assert far['id'] not in ids


def test_list_reports_bbox_filters():
    island = _island()
    with for_island(island):
        _category(island)
        inside = services.create_report(
            island=island, session_hash='a', category_slug='acidente',
            latitude=37.78, longitude=-25.50,
        )
        outside = services.create_report(
            island=island, session_hash='b', category_slug='acidente',
            latitude=37.88, longitude=-25.30,
        )
        results = services.list_reports(bbox=(-25.55, 37.75, -25.45, 37.80))
        ids = [r['id'] for r in results]
        assert inside['id'] in ids
        assert outside['id'] not in ids


def test_update_and_delete_ownership():
    island = _island()
    with for_island(island):
        _category(island)
        created = services.create_report(
            island=island, session_hash='owner', category_slug='acidente',
            latitude=37.78, longitude=-25.50,
        )
        with pytest.raises(services.OwnershipError):
            services.update_report(created['id'], session_hash='other', is_staff=False,
                                   data={'description': 'x'})
        updated = services.update_report(created['id'], session_hash='owner', is_staff=False,
                                         data={'description': 'updated'})
        assert updated['description'] == 'updated'
        with pytest.raises(services.OwnershipError):
            services.soft_delete_report(created['id'], session_hash='other', is_staff=False)
        assert services.soft_delete_report(created['id'], session_hash='owner', is_staff=False)
        assert TrafficReport.objects.get(id=created['id']).status == TrafficReport.REMOVED


def test_run_lifecycle_activates_and_expires():
    island = _island()
    with for_island(island):
        cat = _category(island, slug='radar', schedulable=True)
        now = timezone.now()
        # scheduled, due now
        scheduled = TrafficReport.objects.create(
            island=island, category=cat, latitude=37.78, longitude=-25.50,
            status=TrafficReport.SCHEDULED, active_from=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=1),
        )
        # active, past expiry
        stale = TrafficReport.objects.create(
            island=island, category=cat, latitude=37.78, longitude=-25.50,
            status=TrafficReport.ACTIVE, expires_at=now - timedelta(minutes=1),
        )
    counts = services.run_lifecycle()
    assert counts['activated'] >= 1
    assert counts['expired'] >= 1
    assert TrafficReport.objects.unscoped().get(id=scheduled.id).status == TrafficReport.ACTIVE
    assert TrafficReport.objects.unscoped().get(id=stale.id).status == TrafficReport.EXPIRED
    # idempotent
    second = services.run_lifecycle()
    assert second['activated'] == 0
