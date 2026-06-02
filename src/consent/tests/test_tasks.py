"""Consent retention and DSAR tests."""

from django.test import TestCase

from consent.dsar import dsar_delete, dsar_export_bundle
from consent.models import ConsentRecord
from consent.services import hash_session_id, save_consent
from consent.session_salt import get_session_salt
from consent.tasks import expire_consent_task, rotate_session_salt_task


class ConsentTasksTestCase(TestCase):
    def test_rotate_session_salt_changes_value(self):
        before = get_session_salt()
        rotate_session_salt_task()
        after = get_session_salt()
        self.assertNotEqual(before, after)

    def test_expire_consent_withdraws_old_policy(self):
        session_hash = hash_session_id('expire-me', 'sao-miguel')
        ConsentRecord.objects.create(
            session_hash=session_hash,
            purposes={'strictly_necessary': True, 'analytics': True},
            policy_version='0.9.0',
        )
        result = expire_consent_task()
        self.assertEqual(result['expired'], 1)
        record = ConsentRecord.objects.get(session_hash=session_hash)
        self.assertIsNotNone(record.withdrawn_at)

    def test_dsar_export_and_delete(self):
        session_hash = hash_session_id('dsar-user', 'sao-miguel')
        save_consent(session_hash=session_hash, purposes={'strictly_necessary': True, 'analytics': True})

        bundle = dsar_export_bundle(session_hash=session_hash)
        self.assertEqual(bundle['session_hash'], session_hash)
        self.assertGreaterEqual(len(bundle['consent']), 1)

        deleted = dsar_delete(session_hash=session_hash)
        self.assertGreaterEqual(deleted['consent_records_deleted'], 1)
        self.assertEqual(ConsentRecord.objects.filter(session_hash=session_hash).count(), 0)
