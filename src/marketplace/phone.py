"""Portuguese phone number normalization for marketplace listings."""

from __future__ import annotations

import re

PT_COUNTRY_CODE = '351'
PT_NATIONAL_DIGITS = 9


def normalize_pt_phone(raw: str | None) -> str | None:
    """Normalize a phone/WhatsApp value to ``+351XXXXXXXXX``.

    Returns:
        - ``''`` for empty/whitespace input (unchanged empty).
        - ``+351`` + 9 national digits when the value can be parsed.
        - ``None`` when non-empty input cannot be normalized (leave as-is).
    """
    if raw is None:
        return ''
    text = str(raw).strip()
    if not text:
        return ''

    digits = re.sub(r'\D', '', text)
    if not digits:
        return None

    if digits.startswith('00'):
        digits = digits[2:]

    if digits.startswith(PT_COUNTRY_CODE):
        national = digits[len(PT_COUNTRY_CODE) :]
        if len(national) == PT_NATIONAL_DIGITS + 1 and national.startswith('0'):
            national = national[1:]
        if len(national) == PT_NATIONAL_DIGITS:
            return f'+{PT_COUNTRY_CODE}{national}'
        return None

    if len(digits) == PT_NATIONAL_DIGITS + 1 and digits.startswith('0'):
        digits = digits[1:]

    if len(digits) == PT_NATIONAL_DIGITS:
        return f'+{PT_COUNTRY_CODE}{digits}'

    return None
