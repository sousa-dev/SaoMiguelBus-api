"""Rate-limited HTTP client for azb.elevensystems.pt.

Upstream publishes no rate limit and sent no Retry-After or X-RateLimit-* header
at any rate the review tried (98 §6). Absence of a published limit is not
permission: the pacing, the identifying User-Agent and the hard budget cap live
here so no caller can accidentally turn a sync into a hammer.

Follows the house shape (minibus/tracking_client.py): module-level decouple
constants, a domain exception, and a three-stage error funnel -- transport,
status, body.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import requests
from decouple import config


logger = logging.getLogger(__name__)

AZORESBUS_API_BASE_URL = config(
    'AZORESBUS_API_BASE_URL', default='https://azb.elevensystems.pt/api',
).rstrip('/')
AZORESBUS_PROXY_KEY = config('AZORESBUS_PROXY_KEY', default='')
AZORESBUS_SYNC_DELAY = config('AZORESBUS_SYNC_DELAY', default=0.35, cast=float)
AZORESBUS_SYNC_TIMEOUT = config('AZORESBUS_SYNC_TIMEOUT', default=20, cast=int)
AZORESBUS_SYNC_MAX_REQUESTS = config(
    'AZORESBUS_SYNC_MAX_REQUESTS', default=4000, cast=int,
)

# A caller passing delay=0 must not be able to remove the pacing.
MIN_DELAY = 0.35
MAX_ATTEMPTS = 4
MAX_CONSECUTIVE_FAILURES = 10

USER_AGENT = (
    'SaoMiguelBus/3.x schedule-sync '
    '(+https://saomiguelbus.com; contact@saomiguelbus.com)'
)


class AzoresbusError(Exception):
    """Upstream request failed."""


class AzoresbusNotFound(AzoresbusError):
    """Upstream returned 404. An answer, not a transient failure."""


class BudgetExhausted(AzoresbusError):
    """The run hit its request cap. Marks the run partial; suppresses pruning."""


class AzoresbusClient:
    """Serial, paced, budget-capped. One in-flight request, ever."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        delay: float | None = None,
        jitter: float = 0.2,
        timeout: int | None = None,
        max_requests: int | None = None,
        max_attempts: int = MAX_ATTEMPTS,
        max_consecutive_failures: int = MAX_CONSECUTIVE_FAILURES,
    ):
        self.base_url = (base_url or AZORESBUS_API_BASE_URL).rstrip('/')
        self.delay = max(
            MIN_DELAY,
            AZORESBUS_SYNC_DELAY if delay is None else delay,
        )
        self.jitter = jitter
        self.timeout = timeout or AZORESBUS_SYNC_TIMEOUT
        self.max_requests = max_requests or AZORESBUS_SYNC_MAX_REQUESTS
        self.max_attempts = max_attempts
        self.max_consecutive_failures = max_consecutive_failures

        self.request_count = 0
        self.consecutive_failures = 0
        self._last_request_at: float | None = None

    # -- pacing ------------------------------------------------------------

    def _wait_turn(self) -> None:
        if self._last_request_at is None:
            return
        wait = self.delay
        if self.jitter:
            wait *= 1.0 + random.uniform(-self.jitter, self.jitter)
        time.sleep(max(wait, MIN_DELAY))

    def _headers(self) -> dict[str, str]:
        headers = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
        if AZORESBUS_PROXY_KEY:
            headers['X-Tracking-Proxy-Key'] = AZORESBUS_PROXY_KEY
        return headers

    # -- the one entry point ------------------------------------------------

    def get_json(self, path: str) -> Any:
        if self.consecutive_failures >= self.max_consecutive_failures:
            raise AzoresbusError(
                f'aborting: {self.consecutive_failures} consecutive failures. '
                'Upstream is down, not flaky.'
            )
        if self.request_count >= self.max_requests:
            raise BudgetExhausted(
                f'request budget of {self.max_requests} exhausted. The run is '
                'partial and must not prune or retire anything.'
            )

        url = f'{self.base_url}{path}'
        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            self._wait_turn()
            self._last_request_at = time.monotonic()
            self.request_count += 1

            try:
                response = requests.get(
                    url, timeout=self.timeout, headers=self._headers(),
                )
            except requests.RequestException as exc:
                last_error = exc
                logger.warning('azoresbus request failed url=%s attempt=%s',
                               url, attempt)
                if attempt < self.max_attempts:
                    self._backoff(attempt, None)
                    continue
                break

            if response.status_code == 404:
                # Not transient. Retrying wastes budget against a real answer.
                self.consecutive_failures = 0
                raise AzoresbusNotFound(f'404 for {path}')

            if response.status_code == 429 or response.status_code >= 500:
                last_error = AzoresbusError(
                    f'HTTP {response.status_code} for {path}'
                )
                logger.warning('azoresbus HTTP %s url=%s body=%s',
                               response.status_code, url, response.text[:500])
                if attempt < self.max_attempts:
                    self._backoff(attempt, response.headers.get('Retry-After'))
                    continue
                break

            if not response.ok:
                self.consecutive_failures += 1
                raise AzoresbusError(f'HTTP {response.status_code} for {path}')

            try:
                payload = response.json()
            except ValueError as exc:
                self.consecutive_failures += 1
                raise AzoresbusError(f'invalid JSON from {path}') from exc

            self.consecutive_failures = 0
            return payload

        self.consecutive_failures += 1
        raise AzoresbusError(
            f'giving up on {path} after {self.max_attempts} attempts'
        ) from last_error

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        """2 ** attempt seconds, or Retry-After when upstream sends one.

        Defensive rather than observed: upstream has never sent Retry-After at
        any rate tried (98 §6).
        """
        if retry_after:
            try:
                time.sleep(float(retry_after))
                return
            except (TypeError, ValueError):
                pass
        time.sleep(float(2 ** attempt))
