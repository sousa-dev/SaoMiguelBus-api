from datetime import date
import re


_DAY_TYPES = {'weekday', 'saturday', 'sunday'}
_TIME_RE = re.compile(r'^([01][0-9]|2[0-3]):[0-5][0-9]$')


def parse_day(value: str) -> str:
    value = str(value or '').strip().lower()
    if value in _DAY_TYPES:
        return value
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('day must be weekday, saturday, sunday, or YYYY-MM-DD') from exc
    return value


def parse_start(value: str) -> str:
    value = str(value or '').strip()
    if not _TIME_RE.fullmatch(value):
        raise ValueError('start must be HH:MM in 24-hour time')
    return value