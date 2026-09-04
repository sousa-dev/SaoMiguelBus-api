import json
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from azoresbus.apns import (
    MAX_PAYLOAD_BYTES,
    TOKEN_CACHE_KEY,
    _auth_token,
    build_provider_token,
    live_activity_payload,
)

LOC_MEM_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


def _ec_keypair() -> tuple[str, str]:
    """A throwaway ES256 keypair -- no real Apple credentials needed to test signing."""
    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


class BuildProviderTokenTests(SimpleTestCase):
    def test_produces_a_verifiable_es256_jwt_with_kid_and_iss(self):
        private_pem, public_pem = _ec_keypair()
        token = build_provider_token(private_pem, 'KEY123', 'TEAM456', now=1_000_000)

        header = jwt.get_unverified_header(token)
        self.assertEqual(header['alg'], 'ES256')
        self.assertEqual(header['kid'], 'KEY123')

        claims = jwt.decode(token, public_pem, algorithms=['ES256'])
        self.assertEqual(claims['iss'], 'TEAM456')
        self.assertEqual(claims['iat'], 1_000_000)


@override_settings(CACHES=LOC_MEM_CACHE)
class AuthTokenCachingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_reuses_the_cached_token_rather_than_minting_a_new_one(self):
        with patch('azoresbus.apns.build_provider_token', return_value='token-a') as builder:
            first = _auth_token()
            second = _auth_token()
        self.assertEqual(first, 'token-a')
        self.assertEqual(second, 'token-a')
        # Apple rejects a client minting more than one token per ~20 minutes --
        # calling twice in a row must not build twice.
        builder.assert_called_once()

    def test_a_cleared_cache_mints_again(self):
        with patch('azoresbus.apns.build_provider_token', side_effect=['token-a', 'token-b']) as builder:
            first = _auth_token()
            cache.delete(TOKEN_CACHE_KEY)
            second = _auth_token()
        self.assertEqual(first, 'token-a')
        self.assertEqual(second, 'token-b')
        self.assertEqual(builder.call_count, 2)


class LiveActivityPayloadTests(SimpleTestCase):
    def test_update_payload_has_no_dismissal_date(self):
        payload = live_activity_payload({'state': 'riding'}, event='update')
        self.assertEqual(payload['aps']['event'], 'update')
        self.assertEqual(payload['aps']['content-state'], {'state': 'riding'})
        self.assertNotIn('dismissal-date', payload['aps'])

    def test_end_payload_carries_a_dismissal_date(self):
        payload = live_activity_payload({'state': 'completed'}, event='end', dismiss_in_seconds=120)
        self.assertEqual(payload['aps']['event'], 'end')
        self.assertIn('dismissal-date', payload['aps'])
        self.assertGreater(payload['aps']['dismissal-date'], payload['aps']['timestamp'])

    def test_a_worst_case_snapshot_serialises_under_the_apns_limit(self):
        # Every field maxed out with plausible worst-case content.
        snapshot = {
            'v': 1,
            'state': 'riding',
            'nextStopName': 'Ribeira Grande (Estação Rodoviária Municipal)',
            'minutesToNextStop': 59,
            'delayMinutes': -59,
            'progress': 0.987654321,
            'updatedAtEpochMs': 1893456000000.0,
        }
        payload = live_activity_payload(snapshot, event='update')
        self.assertLess(len(json.dumps(payload).encode('utf-8')), MAX_PAYLOAD_BYTES)
