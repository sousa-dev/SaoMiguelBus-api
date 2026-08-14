"""Deterministic search fixtures for the S0 behaviour snapshot.

These exist to freeze what ``search_routes`` does *today*, before the AzoresBus
matcher rewrite touches it. Three changes are planned and will alter results
(the holiday seed, the boarding-time filter, and sequence-based pair matching);
every one of them has to show up as a reviewed diff against this baseline rather
than as a surprise. See ``test_search_snapshot.py`` and ``test_search_diff.py``.

Trips are keyed by a stable string so the golden file never contains an
autoincrement PK, which would make it non-reproducible across runs.
"""

from __future__ import annotations

from datetime import time

from tenancy.models import Island
from tenancy.services import get_or_create_default_island
from transit.models import Calendar, Line, Operator, Stop, StopTime, Trip
from transit.services.legacy_import import clean_string


# (key, code, service_type, [(stop_name, 'HH:MM'), ...])
SCENARIOS: list[tuple[str, str, str, list[tuple[str, str]]]] = [
    # Loop: first and last stop share a name. A search for CHARLIE -> ALFA is a
    # valid ride (sequence 3 -> 5) that today's first-occurrence matcher drops,
    # because ALFA is also at sequence 1. 98 B7.
    (
        'loop_weekday',
        'SNAP-LOOP',
        Calendar.WEEKDAY,
        [
            ('ALFA', '06:00'),
            ('BRAVO', '06:30'),
            ('CHARLIE', '07:00'),
            ('DELTA', '07:30'),
            ('ALFA', '08:00'),
        ],
    ),
    # Late board: the trip departs at 06:00 but reaches FOXTROT at 09:00. Today's
    # filter compares the request against the trip's FIRST stop time, so a
    # start=08h30 search drops it. 02 section 3.4.
    (
        'late_board_weekday',
        'SNAP-LATE',
        Calendar.WEEKDAY,
        [
            ('ECHO', '06:00'),
            ('FOXTROT', '09:00'),
            ('GOLF', '09:30'),
        ],
    ),
    # Plain controls, one per service type. These must never change.
    ('plain_weekday', 'SNAP-WD', Calendar.WEEKDAY, [('HOTEL', '08:00'), ('INDIA', '08:30')]),
    ('plain_saturday', 'SNAP-SAT', Calendar.SATURDAY, [('HOTEL', '10:00'), ('INDIA', '10:30')]),
    ('plain_sunday', 'SNAP-SUN', Calendar.SUNDAY, [('HOTEL', '11:00'), ('INDIA', '11:30')]),
    # Substring behaviour. This trip serves ACHADA proper.
    (
        'achada_real',
        'SNAP-ACH',
        Calendar.WEEKDAY,
        [('ACHADA', '07:00'), ('JULIET', '07:40')],
    ),
    # Negative control. 'achada' is NOT a substring of 'achadinha' (position 5 is
    # 'i', not 'a'), so despite 02 section 3.4 citing this pair, it does not
    # actually collide. Frozen to prove that.
    (
        'achadinha_only',
        'SNAP-ACHI',
        Calendar.WEEKDAY,
        [('ACHADINHA', '07:05'), ('JULIET', '07:45')],
    ),
    # The real containment mis-hit: 'lagoa' IS a substring of 'lagoa do fogo', so
    # a search for LAGOA -> JULIET matches this trip today even though it never
    # stops at LAGOA. Resolving by stop id removes it.
    (
        'lagoa_do_fogo_only',
        'SNAP-LGF',
        Calendar.WEEKDAY,
        [('LAGOA DO FOGO', '07:10'), ('JULIET', '07:50')],
    ),
    # Accented names. The order gate uses the RAW origin against the RAW stops
    # string, so a case/accent mismatch makes both find() calls return -1 and the
    # gate silently passes. Frozen deliberately: it is current behaviour.
    (
        'accented_weekday',
        'SNAP-ACC',
        Calendar.WEEKDAY,
        [('POVOAÇÃO', '07:00'), ('FURNAS', '07:30')],
    ),
]


# (key, kwargs passed straight to search_routes)
QUERIES: list[tuple[str, dict]] = [
    # --- the three planned changes, each with a query that exposes it ---
    ('loop_reverse_leg', {
        'origin': 'CHARLIE', 'destination': 'ALFA',
        'day': 'weekday', 'start_time': '00h00',
    }),
    ('late_board_after_start', {
        'origin': 'FOXTROT', 'destination': 'GOLF',
        'day': 'weekday', 'start_time': '08h30',
    }),
    ('christmas_2026', {
        'origin': 'HOTEL', 'destination': 'INDIA',
        'day': '2026-12-25', 'start_time': '00h00',
    }),
    # --- controls that must not move ---
    ('plain_weekday_literal', {
        'origin': 'HOTEL', 'destination': 'INDIA',
        'day': 'weekday', 'start_time': '00h00',
    }),
    ('plain_saturday_literal', {
        'origin': 'HOTEL', 'destination': 'INDIA',
        'day': 'saturday', 'start_time': '00h00',
    }),
    ('plain_sunday_literal', {
        'origin': 'HOTEL', 'destination': 'INDIA',
        'day': 'sunday', 'start_time': '00h00',
    }),
    # 2026-12-14 is a Monday, 2026-12-26 a Saturday, 2026-12-27 a Sunday.
    ('iso_monday', {
        'origin': 'HOTEL', 'destination': 'INDIA',
        'day': '2026-12-14', 'start_time': '00h00',
    }),
    ('iso_saturday', {
        'origin': 'HOTEL', 'destination': 'INDIA',
        'day': '2026-12-26', 'start_time': '00h00',
    }),
    ('iso_sunday', {
        'origin': 'HOTEL', 'destination': 'INDIA',
        'day': '2026-12-27', 'start_time': '00h00',
    }),
    ('start_time_filters_out', {
        'origin': 'HOTEL', 'destination': 'INDIA',
        'day': 'weekday', 'start_time': '09h00',
    }),
    # --- negative control: ACHADA must not pull in the ACHADINHA-only trip ---
    ('achada_vs_achadinha', {
        'origin': 'ACHADA', 'destination': 'JULIET',
        'day': 'weekday', 'start_time': '00h00',
    }),
    # --- real containment mis-hit: LAGOA pulls in the LAGOA DO FOGO trip ---
    ('lagoa_substring_mishit', {
        'origin': 'LAGOA', 'destination': 'JULIET',
        'day': 'weekday', 'start_time': '00h00',
    }),
    # --- the raw-find order gate no-op on accent/case mismatch ---
    ('accent_mismatch_gate', {
        'origin': 'povoação', 'destination': 'furnas',
        'day': 'weekday', 'start_time': '00h00',
    }),
    # _normalize_origin rewrites 'Povoacão' -> 'Povoação' before matching.
    ('normalize_origin_hack', {
        'origin': 'Povoacão', 'destination': 'FURNAS',
        'day': 'weekday', 'start_time': '00h00',
    }),
    # --- flag combinations ---
    ('prefix_true_low_votes', {
        'origin': 'HOTEL', 'destination': 'INDIA',
        'day': 'weekday', 'start_time': '00h00', 'prefix': True,
    }),
    ('full_true', {
        'origin': 'HOTEL', 'destination': 'INDIA',
        'day': 'weekday', 'start_time': '00h00', 'full': True,
    }),
    # --- no match at all ---
    ('unknown_origin', {
        'origin': 'NOWHERE', 'destination': 'INDIA',
        'day': 'weekday', 'start_time': '00h00',
    }),
    # --- reversed direction on a linear trip: correctly rejected today ---
    ('reversed_linear', {
        'origin': 'INDIA', 'destination': 'HOTEL',
        'day': 'weekday', 'start_time': '00h00',
    }),
]


def _parse(hhmm: str) -> time:
    hour, minute = hhmm.split(':')
    return time(int(hour), int(minute))


def ensure_search_snapshot_fixtures() -> tuple[Island, dict[str, Trip]]:
    """Create the snapshot dataset. Idempotent, all rows ``dataset='legacy'``."""
    island = get_or_create_default_island()
    operator, _ = Operator.objects.get_or_create(
        island=island, name='CRP', defaults={'contact': {}},
    )

    calendars = {
        service_type: Calendar.objects.get_or_create(
            island=island, service_type=service_type,
        )[0]
        for service_type in (Calendar.WEEKDAY, Calendar.SATURDAY, Calendar.SUNDAY)
    }

    trips: dict[str, Trip] = {}
    for key, code, service_type, stops in SCENARIOS:
        line, _ = Line.objects.get_or_create(
            island=island, code=code,
            defaults={'operator': operator, 'display_name': f'Snapshot {key}'},
        )
        trip, created = Trip.objects.get_or_create(
            island=island, line=line, calendar=calendars[service_type],
            defaults={'likes': 0, 'dislikes': 0, 'source': Trip.SOURCE_OPERATOR},
        )
        if created:
            for sequence, (stop_name, hhmm) in enumerate(stops, start=1):
                stop, _ = Stop.objects.get_or_create(
                    island=island,
                    cleaned_name=clean_string(stop_name),
                    defaults={
                        'name': stop_name,
                        'latitude': 37.74 + sequence / 1000,
                        'longitude': -25.67 + sequence / 1000,
                    },
                )
                StopTime.objects.create(
                    island=island, trip=trip, stop=stop,
                    sequence=sequence, departure_time=_parse(hhmm),
                )
        trips[key] = trip

    return island, trips


def normalize_results(results, trips: dict[str, Trip]) -> list[dict]:
    """Replace autoincrement trip PKs with their stable fixture key.

    Without this the golden file would change every time the test database
    sequences move, and the snapshot would be worthless as a baseline.
    """
    by_id = {trip.id: key for key, trip in trips.items()}
    normalized = []
    for row in results or []:
        row = dict(row)
        row['id'] = by_id.get(row['id'], f'UNKNOWN:{row["id"]}')
        normalized.append(row)
    return normalized
