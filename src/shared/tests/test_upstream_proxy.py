"""The proxy contract: target host in a header, full path preserved."""

from __future__ import annotations

from django.test import SimpleTestCase

from shared.upstream_proxy import HOST_HEADER, KEY_HEADER, build_request, split_origin

PDL = 'https://pdl.elevensystems.pt/publicapi'
AZB = 'https://azb.elevensystems.pt/api'
PROXY = 'http://100.64.0.5:8080'


class SplitOriginTests(SimpleTestCase):
    def test_origin_and_base_path_are_separated(self):
        self.assertEqual(
            split_origin(PDL), ('https://pdl.elevensystems.pt', '/publicapi'),
        )

    def test_a_bare_origin_has_no_base_path(self):
        self.assertEqual(
            split_origin('https://example.test'), ('https://example.test', ''),
        )

    def test_a_scheme_is_assumed_when_missing(self):
        origin, _ = split_origin('example.test/api')
        self.assertEqual(origin, 'https://example.test')


class DirectTests(SimpleTestCase):
    def test_no_proxy_means_a_direct_call(self):
        url, headers = build_request(PDL, '/locations', proxy_url='')
        self.assertEqual(url, f'{PDL}/locations')
        self.assertEqual(headers, {})

    def test_a_missing_leading_slash_is_tolerated(self):
        url, _ = build_request(PDL, 'locations', proxy_url='')
        self.assertEqual(url, f'{PDL}/locations')


class ProxiedTests(SimpleTestCase):
    def test_the_full_upstream_path_is_preserved(self):
        url, _ = build_request(
            PDL, '/locations/11010934', proxy_url=PROXY, proxy_key='k',
        )
        self.assertEqual(url, f'{PROXY}/publicapi/locations/11010934')

    def test_the_target_host_travels_in_a_header(self):
        _, headers = build_request(PDL, '/locations', proxy_url=PROXY, proxy_key='k')
        self.assertEqual(headers[HOST_HEADER], 'https://pdl.elevensystems.pt')
        self.assertEqual(headers[KEY_HEADER], 'k')

    def test_a_second_upstream_needs_no_new_proxy_rule(self):
        """The point of the contract: adding AzoresBus is not ops work."""
        url, headers = build_request(
            AZB, '/routes/1/journeys?day=2026-09-14',
            proxy_url=PROXY, proxy_key='k',
        )
        self.assertEqual(
            url, f'{PROXY}/api/routes/1/journeys?day=2026-09-14',
        )
        self.assertEqual(headers[HOST_HEADER], 'https://azb.elevensystems.pt')

    def test_the_two_upstreams_are_distinguishable_at_the_proxy(self):
        _, pdl = build_request(PDL, '/locations', proxy_url=PROXY)
        _, azb = build_request(AZB, '/locations', proxy_url=PROXY)
        self.assertNotEqual(pdl[HOST_HEADER], azb[HOST_HEADER])

    def test_the_key_is_omitted_when_unset(self):
        _, headers = build_request(PDL, '/locations', proxy_url=PROXY, proxy_key='')
        self.assertNotIn(KEY_HEADER, headers)
        self.assertIn(HOST_HEADER, headers)
