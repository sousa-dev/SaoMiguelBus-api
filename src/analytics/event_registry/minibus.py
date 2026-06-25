"""Minibus module analytics event schemas."""

from __future__ import annotations

from typing import Any

Scalar = str | int | bool

_VIEW_SCREENS = frozenset({
    'list',
    'search',
    'line',
    'line_map',
    'line_map_stop',
    'live',
    'directions',
})

_LIVE_ENTRY_SOURCES = frozenset({'hub', 'line_detail'})

_LIVE_FILTER_SOURCES = frozenset({'chip', 'deep_link', 'stops_toggle'})

_LIVE_SELECT_SOURCES = frozenset({'map', 'fleet_bar', 'vehicle_sheet'})

_LIVE_MAP_ACTIONS = frozenset({'center', 'zoom_in', 'zoom_out'})

_LIVE_FLEET_BAR_ACTIONS = frozenset({'expand', 'collapse', 'clear_vehicle'})

_LIVE_PERMISSION_OUTCOMES = frozenset({'granted', 'denied'})

_LIVE_HEALTH_ACTIONS = frozenset({'retry'})

_LIVE_NAVIGATE_ACTIONS = frozenset({'view_line'})

_LIVE_NAVIGATE_SOURCES = frozenset({'stop_sheet'})

_ENGAGE_ACTIONS = frozenset({
    'select_journey',
    'offline_sync',
    'open_from_hub',
    'open_from_transit',
})

_SEARCH_SOURCES = frozenset({'api', 'offline'})

_OFFLINE_SYNC_PHASES = frozenset({'start'})
_OFFLINE_SYNC_OUTCOMES = frozenset({'success', 'failure'})


def validate_minibus_event(
    event_type: str,
    properties: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(properties, dict):
        properties = {}

    validators = {
        'view': _validate_view,
        'search': _validate_search,
        'engage': _validate_engage,
        'live_entry_open': _validate_live_entry_open,
        'live_filter': _validate_live_filter,
        'live_toggle': _validate_live_toggle,
        'live_select': _validate_live_select,
        'live_map_control': _validate_live_map_control,
        'live_fleet_bar': _validate_live_fleet_bar,
        'live_permission': _validate_live_permission,
        'live_health': _validate_live_health,
        'live_navigate': _validate_live_navigate,
    }

    handler = validators.get(event_type)
    if handler is None:
        return None, f'unknown_minibus_event_type:{event_type}'

    return handler(properties)


def _scalar(value: Any, *, as_type: type) -> Scalar | None:
    if as_type is bool:
        return value if isinstance(value, bool) else None
    if as_type is int:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None
    if as_type is str:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        if isinstance(value, (int, float, bool)):
            return str(value)
        return None
    return None


def _pick(
    properties: dict[str, Any],
    spec: dict[str, tuple[type, bool]],
) -> tuple[dict[str, Scalar] | None, str | None]:
    """Pick allowed keys; required keys must be present and typed correctly."""
    cleaned: dict[str, Scalar] = {}
    for key, (value_type, required) in spec.items():
        if key not in properties:
            if required:
                return None, f'missing:{key}'
            continue
        scalar = _scalar(properties[key], as_type=value_type)
        if scalar is None:
            return None, f'invalid:{key}'
        cleaned[key] = scalar
    return cleaned, None


def _validate_enum(
    properties: dict[str, Any],
    *,
    key: str,
    allowed: frozenset[str],
    required: bool = True,
) -> tuple[str | None, str | None]:
    if key not in properties:
        if required:
            return None, f'missing:{key}'
        return None, None
    value = _scalar(properties[key], as_type=str)
    if value is None or value not in allowed:
        return None, f'invalid:{key}'
    return value, None


def _validate_view(properties: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    screen, err = _validate_enum(properties, key='screen', allowed=_VIEW_SCREENS)
    if err:
        return None, err

    optional = {
        'line': (str, False),
        'stop': (str, False),
        'origin': (str, False),
        'destination': (str, False),
        'transfers': (int, False),
        'total_stops': (int, False),
        'line_codes': (str, False),
    }
    cleaned, err = _pick(properties, {'screen': (str, True), **optional})
    if err:
        return None, err
    if cleaned['screen'] != screen:
        return None, 'invalid:screen'
    return cleaned, None


def _validate_search(properties: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    spec = {
        'origin': (str, True),
        'destination': (str, True),
        'results_count': (int, True),
        'offline': (bool, True),
        'source': (str, True),
    }
    cleaned, err = _pick(properties, spec)
    if err:
        return None, err
    if cleaned['source'] not in _SEARCH_SOURCES:
        return None, 'invalid:source'
    return cleaned, None


def _validate_engage(properties: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    action, err = _validate_enum(properties, key='action', allowed=_ENGAGE_ACTIONS)
    if err:
        return None, err

    if action == 'select_journey':
        spec = {
            'action': (str, True),
            'origin': (str, True),
            'destination': (str, True),
            'transfers': (int, True),
            'total_stops': (int, True),
            'line_codes': (str, True),
            'journey_index': (int, False),
            'offline': (bool, False),
        }
    elif action == 'offline_sync':
        spec = {
            'action': (str, True),
            'bundle': (str, True),
            'locale': (str, True),
            'phase': (str, False),
            'outcome': (str, False),
            'updated': (bool, False),
            'version': (str, False),
        }
    else:
        spec = {'action': (str, True)}

    cleaned, err = _pick(properties, spec)
    if err:
        return None, err
    if cleaned['action'] != action:
        return None, 'invalid:action'

    if action == 'offline_sync':
        phase = cleaned.get('phase')
        outcome = cleaned.get('outcome')
        if phase and phase not in _OFFLINE_SYNC_PHASES:
            return None, 'invalid:phase'
        if outcome and outcome not in _OFFLINE_SYNC_OUTCOMES:
            return None, 'invalid:outcome'
        if cleaned.get('bundle') != 'minibus':
            return None, 'invalid:bundle'
        if not phase and not outcome:
            return None, 'missing:phase_or_outcome'
    return cleaned, None


def _validate_live_entry_open(properties: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    source, err = _validate_enum(properties, key='source', allowed=_LIVE_ENTRY_SOURCES)
    if err:
        return None, err
    cleaned, err = _pick(properties, {'source': (str, True), 'line': (str, False)})
    if err:
        return None, err
    if cleaned['source'] != source:
        return None, 'invalid:source'
    return cleaned, None


def _validate_live_filter(properties: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    cleaned, err = _pick(properties, {'line_slug': (str, True), 'source': (str, False)})
    if err:
        return None, err
    source = cleaned.get('source')
    if source is not None and source not in _LIVE_FILTER_SOURCES:
        return None, 'invalid:source'
    return cleaned, None


def _validate_live_toggle(properties: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    return _pick(properties, {'show_stops': (bool, True)})


def _validate_live_select(properties: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    source, err = _validate_enum(properties, key='source', allowed=_LIVE_SELECT_SOURCES)
    if err:
        return None, err

    keys_present = [
        key
        for key in ('vehicle_id', 'stop_key', 'stop_sequence')
        if key in properties and properties[key] is not None and properties[key] != ''
    ]
    if len(keys_present) != 1:
        return None, 'invalid:selection_key'

    spec: dict[str, tuple[type, bool]] = {'source': (str, True)}
    if 'vehicle_id' in keys_present:
        spec['vehicle_id'] = (str, True)
    elif 'stop_key' in keys_present:
        spec['stop_key'] = (str, True)
    else:
        spec['stop_sequence'] = (int, True)

    cleaned, err = _pick(properties, spec)
    if err:
        return None, err
    if cleaned['source'] != source:
        return None, 'invalid:source'
    return cleaned, None


def _validate_live_map_control(properties: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    action, err = _validate_enum(properties, key='action', allowed=_LIVE_MAP_ACTIONS)
    if err:
        return None, err
    return {'action': action}, None


def _validate_live_fleet_bar(properties: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    action, err = _validate_enum(properties, key='action', allowed=_LIVE_FLEET_BAR_ACTIONS)
    if err:
        return None, err
    return {'action': action}, None


def _validate_live_permission(properties: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    outcome, err = _validate_enum(properties, key='outcome', allowed=_LIVE_PERMISSION_OUTCOMES)
    if err:
        return None, err
    return {'outcome': outcome}, None


def _validate_live_health(properties: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    action, err = _validate_enum(properties, key='action', allowed=_LIVE_HEALTH_ACTIONS)
    if err:
        return None, err
    return {'action': action}, None


def _validate_live_navigate(properties: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    action, err = _validate_enum(properties, key='action', allowed=_LIVE_NAVIGATE_ACTIONS)
    if err:
        return None, err
    source, source_err = _validate_enum(properties, key='source', allowed=_LIVE_NAVIGATE_SOURCES)
    if source_err:
        return None, source_err
    cleaned, err = _pick(
        properties,
        {'action': (str, True), 'line_slug': (str, True), 'source': (str, True)},
    )
    if err:
        return None, err
    if cleaned['action'] != action or cleaned['source'] != source:
        return None, 'invalid:action_or_source'
    return cleaned, None
