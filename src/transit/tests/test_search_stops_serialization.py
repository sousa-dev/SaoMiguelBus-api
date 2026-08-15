"""Repeated stop names must survive serialization (98 B7, 03 section 5c).

`search_routes` emits the stop list as a Python dict literal and the v3
serializer read it back with `ast.literal_eval`, which COLLAPSES duplicate keys:
the first occurrence's position survived carrying the last occurrence's time.

That broke sequence matching on exactly the trips it exists for. On line 301
journey 488 the trip has 59 stop times and 14 repeated names, so the array the
client received had 45 entries -- and `alighting.sequence` 59 indexed past its
end. The client could not slice on the pair the server had chosen, so loop routes
fell back to name matching, which is the bug being fixed.

The string itself was never lossy; only building a dict from it was.
"""

from __future__ import annotations

from transit.services.v3 import _parse_stops_string


class ParseStopsStringTests:
    pass


def test_repeated_stop_names_are_preserved():
    """A loop opens and closes at the same stop."""
    stops = "{'ALFA': '06h00', 'BRAVO': '06h30', 'ALFA': '08h00'}"
    parsed = _parse_stops_string(stops)

    assert len(parsed) == 3, 'the middle visit was collapsed away'
    assert [row['name'] for row in parsed] == ['ALFA', 'BRAVO', 'ALFA']


def test_each_occurrence_keeps_its_own_time():
    """Collapsing overwrote the first visit's time with the last one's."""
    parsed = _parse_stops_string("{'ALFA': '06h00', 'BRAVO': '06h30', 'ALFA': '08h00'}")

    assert parsed[0]['time'] == '06h00', 'the outbound leg lost its own departure'
    assert parsed[2]['time'] == '08h00'


def test_sequence_indices_line_up_with_the_array():
    """boarding/alighting.sequence is 1-based over this list (02 section 7.1b)."""
    names = ['ALFA', 'BRAVO', 'CHARLIE', 'DELTA', 'ALFA']
    stops = '{' + ', '.join(
        f"'{name}': '0{index}h00'" for index, name in enumerate(names, start=6)
    ) + '}'
    parsed = _parse_stops_string(stops)

    assert len(parsed) == len(names)
    # The server picks the later leg CHARLIE -> ALFA as sequence 3 -> 5.
    assert parsed[3 - 1]['name'] == 'CHARLIE'
    assert parsed[5 - 1]['name'] == 'ALFA'


def test_order_is_sequence_order_not_first_seen():
    parsed = _parse_stops_string("{'B': '07h00', 'A': '07h30', 'B': '08h00'}")
    assert [row['name'] for row in parsed] == ['B', 'A', 'B']


def test_a_trip_with_no_repeats_is_unchanged():
    parsed = _parse_stops_string("{'ALFA': '06h00', 'BRAVO': '06h30'}")
    assert parsed == [
        {'name': 'ALFA', 'time': '06h00'},
        {'name': 'BRAVO', 'time': '06h30'},
    ]


def test_empty_and_malformed_input_degrade_quietly():
    assert _parse_stops_string('') == []
    assert _parse_stops_string('not a dict') == []
    # The regex fallback still handles a truncated literal.
    assert _parse_stops_string("{'ALFA': '06h00',") == [{'name': 'ALFA', 'time': '06h00'}]


def test_real_upstream_loop_fixture_survives_intact():
    """Line 301 journey 488: 59 stop times, 14 repeated names."""
    import json
    from pathlib import Path

    fixture = (
        Path(__file__).resolve().parent.parent.parent
        / 'azoresbus' / 'tests' / 'fixtures' / 'journey_25_488.json'
    )
    circulations = sorted(
        json.loads(fixture.read_text())['circulations'], key=lambda row: row['sequence']
    )

    def hhmm(seconds: int) -> str:
        seconds %= 86400
        return f'{seconds // 3600:02d}h{(seconds % 3600) // 60:02d}'

    stops = '{' + ', '.join(
        f"'{row['stage']['name']}': '{hhmm(row['departureTime'])}'"
        for row in circulations
    ) + '}'

    parsed = _parse_stops_string(stops)
    assert len(parsed) == len(circulations) == 59
    assert parsed[40 - 1]['name'] == 'ARRIFES (R. DOS VALADOS)'
    assert parsed[59 - 1]['name'] == 'PONTA DELGADA (ALFÂNDEGA)'
    assert parsed[0]['time'] == '06h30', 'seq 1 kept seq 59 time before the fix'
