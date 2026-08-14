"""One-shot upstream capture for the AzoresBus test fixtures.

Committed so it never needs re-running. The payloads it fetches (stops,
circulations, per-date journey lists) exist nowhere else -- 98's review captured
summaries, not bodies -- and re-probing upstream before we have a proxy path and
an allowlist is how a polite integration becomes a blocked one.

    python azoresbus/tests/capture_fixtures.py --dry-run     # print the plan
    python azoresbus/tests/capture_fixtures.py               # capture

Limits, enforced in code rather than trusted to the operator:

  * HARD CAP of 200 requests. The plan below is 98.
  * Serial only, one in-flight request, >= 0.35 s apart.
  * Identifying User-Agent.
  * An explicit allowlist -- any URL not matching it raises before the socket
    is opened. Widening it is a decision, not a typo.

Do NOT sweep. Do NOT re-verify anything 98 already measured.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE = 'https://azb.elevensystems.pt/api'
OUT = Path(__file__).parent / 'fixtures'

HARD_CAP = 200
MIN_DELAY = 0.35
TIMEOUT = 25
USER_AGENT = (
    'SaoMiguelBus/3.x fixture-capture (+https://saomiguelbus.com; '
    'one-shot, see azoresbus/tests/capture_fixtures.py)'
)

# route id -> public line number (01 section 0: different namespaces).
ROUTES = {
    '1': '101',    # small, two-directional
    '2': '102',    # Wed extra 1009, Fri extra 1011
    '9': '112',    # Tue/Thu only, isActive false
    '25': '301',   # loop, 17 weekday journeys
    '31': '307',   # the seasonal case: 33 summer / 38 term
    '48': '335',   # 36 repeating names, not a loop
    '53': 'N03',   # night route, journey 984 wraps past midnight
}

# A term week, a pre-term Wednesday, a holiday, a winter date, a summer date.
DATES = [
    '2026-09-14', '2026-09-15', '2026-09-16', '2026-09-17',
    '2026-09-18', '2026-09-19', '2026-09-20',
    '2026-09-02',   # pre-term Wednesday: 307 should show 33, not 38
    '2026-12-08',   # a Tuesday that returns the Sunday set (98 B6)
    '2027-01-11',   # winter, still term
    '2027-07-12',   # summer, extras gone
]

# (route id, journey id) -- the specific journeys the matcher tests need.
JOURNEY_DETAILS = [
    ('53', '984'),                                    # the wrap (98 B2)
    ('2', '1009'), ('2', '1011'),                     # Wed vs Fri extras
    ('31', '633'), ('31', '645'), ('31', '647'),      # 307 school extras
    ('31', '661'), ('31', '662'),
    ('9', '236'), ('9', '237'),                       # 112 Tue/Thu
    ('25', '488'),                                    # a 301 loop journey
    ('48', '950'),                                    # a 335 journey (97 stops, 36 repeated names)
]

ALLOWLIST = [
    re.compile(r'^/stops$'),
    re.compile(r'^/routes\?active=true&passengerInfo=true$'),
    re.compile(r'^/routes/(?:' + '|'.join(ROUTES) + r')$'),
    re.compile(
        r'^/routes/(?:' + '|'.join(ROUTES) + r')/journeys\?day='
        r'(?:' + '|'.join(re.escape(d) for d in DATES) + r')$'
    ),
    re.compile(
        r'^/routes/(?:' + '|'.join(ROUTES) + r')/journeys/(?:'
        + '|'.join(sorted({j for _, j in JOURNEY_DETAILS})) + r')$'
    ),
]


class AllowlistViolation(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


def build_plan() -> list[tuple[str, str]]:
    """(path, output filename) pairs, in fetch order."""
    plan: list[tuple[str, str]] = [
        ('/stops', 'stops.json'),
        ('/routes?active=true&passengerInfo=true', 'routes.json'),
    ]
    for route_id in ROUTES:
        plan.append((f'/routes/{route_id}', f'route_{route_id}.json'))
    for route_id in ROUTES:
        for day in DATES:
            plan.append((
                f'/routes/{route_id}/journeys?day={day}',
                f'journeys_{route_id}_{day}.json',
            ))
    for route_id, journey_id in JOURNEY_DETAILS:
        plan.append((
            f'/routes/{route_id}/journeys/{journey_id}',
            f'journey_{route_id}_{journey_id}.json',
        ))
    return plan


def check_allowed(path: str) -> None:
    if not any(pattern.match(path) for pattern in ALLOWLIST):
        raise AllowlistViolation(
            f'{path} is outside the capture allowlist. Widening it is a '
            'decision to take deliberately, not a typo to work around.'
        )


def fetch(path: str) -> bytes:
    check_allowed(path)
    request = Request(BASE + path, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'application/json',
    })
    with urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true',
                        help='print the plan and validate it, fetch nothing')
    parser.add_argument('--delay', type=float, default=MIN_DELAY)
    args = parser.parse_args()

    plan = build_plan()
    delay = max(args.delay, MIN_DELAY)

    for path, _ in plan:
        check_allowed(path)

    print(f'plan: {len(plan)} requests (hard cap {HARD_CAP})')
    print(f'delay: {delay}s  ->  ~{len(plan) * delay / 60:.1f} min')
    if len(plan) > HARD_CAP:
        raise BudgetExceeded(f'{len(plan)} exceeds the {HARD_CAP} cap')

    if args.dry_run:
        for path, name in plan:
            print(f'  GET {path}  ->  {name}')
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    log = []
    for index, (path, name) in enumerate(plan, start=1):
        if index > HARD_CAP:
            raise BudgetExceeded('hard cap reached mid-run')
        if index > 1:
            time.sleep(delay)
        try:
            body = fetch(path)
        except HTTPError as exc:
            # 335's journey id is a guess -- 98 records no ids for that route.
            # Log and continue rather than losing 90 good responses; the run
            # report shows what to re-pick from the captured listing.
            log.append({'n': index, 'path': path, 'status': exc.code})
            print(f'{index:3d}/{len(plan)}  HTTP {exc.code}  {path}')
            continue
        (OUT / name).write_bytes(body)
        log.append({'n': index, 'path': path, 'file': name, 'bytes': len(body)})
        print(f'{index:3d}/{len(plan)}  {len(body):7d}B  {path}')

    (OUT / 'capture_log.json').write_text(
        json.dumps(log, indent=2) + '\n', encoding='utf-8',
    )
    print(f'\ndone: {len(log)} requests, log at {OUT / "capture_log.json"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
