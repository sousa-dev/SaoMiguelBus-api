"""GDPR retention and pseudonymization Celery tasks."""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from consent.services import CONSENT_POLICY_VERSION
from consent.session_salt import rotate_session_salt

logger = logging.getLogger(__name__)


@shared_task(name='consent.rotate_session_salt')
def rotate_session_salt_task() -> dict:
    salt = rotate_session_salt()
    logger.info('Rotated analytics session salt (prefix=%s…)', salt[:8])
    return {'status': 'ok', 'salt_prefix': salt[:8]}


@shared_task(name='consent.expire_consent')
def expire_consent_task() -> dict:
    """Withdraw consent rows tied to an outdated policy version."""
    from consent.models import ConsentRecord

    now = timezone.now()
    qs = ConsentRecord.objects.filter(
        withdrawn_at__isnull=True,
    ).exclude(policy_version=CONSENT_POLICY_VERSION)
    updated = qs.update(withdrawn_at=now)
    logger.info('Expired %s consent records (policy != %s)', updated, CONSENT_POLICY_VERSION)
    return {'status': 'ok', 'expired': updated}
