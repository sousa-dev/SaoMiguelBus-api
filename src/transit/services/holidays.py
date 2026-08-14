"""Portuguese national and Azorean regional holiday calendar.

The ``Holiday`` table drives three things: ``get_type_of_day`` (holiday -> Sunday
service), the ``holidays`` array in ``/api/v3/bootstrap`` and both offline bundles
(which clients use to compute their own day-type), and the AzoresBus sampler guard
that refuses to record a holiday's Sunday journey set as weekday evidence.

Dates are computed rather than tabulated so future years derive without another
seed migration. Easter uses the anonymous Gregorian computus.

Scope note, stated rather than guessed: this covers the national calendar plus the
two Azorean/Sao Miguel entries. 00's prerequisite also mentions "the municipal
entries" from the legacy list, which holds 16 rows in production and 1 row in the
local stub -- they cannot be reproduced from anything in this checkout, so they are
not invented here.

Our list is a HINT about what upstream does, not the source of truth. Upstream's
actual behaviour is observable, and the S2 sync detects holidays from the journey
sets themselves (a weekday whose set equals that route's Sunday set) so that dates
we did not seed are still handled.
"""

from __future__ import annotations

from datetime import date, timedelta


def easter_sunday(year: int) -> date:
    """Anonymous Gregorian computus.

    2026 -> 2026-04-05, 2027 -> 2027-03-28. The second one matters: 98 claim 10
    labels 2027-04-04 as Easter, which is a week late.
    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lunar = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lunar) // 451
    month, day = divmod(h + lunar - 7 * m + 114, 31)
    return date(year, month, day + 1)


# (month, day, name) -- fixed national holidays.
FIXED_NATIONAL: list[tuple[int, int, str]] = [
    (1, 1, 'Ano Novo'),
    (4, 25, 'Dia da Liberdade'),
    (5, 1, 'Dia do Trabalhador'),
    (6, 10, 'Dia de Portugal'),
    (8, 15, 'Assunção de Nossa Senhora'),
    (10, 5, 'Implantação da República'),
    (11, 1, 'Todos os Santos'),
    (12, 1, 'Restauração da Independência'),
    (12, 8, 'Imaculada Conceição'),
    (12, 25, 'Natal'),
]

# (offset from Easter Sunday, name) -- movable feasts.
MOVABLE: list[tuple[int, str]] = [
    (-2, 'Sexta-feira Santa'),
    (0, 'Páscoa'),
    (35, 'Senhor Santo Cristo dos Milagres'),   # 5th Sunday after Easter, São Miguel
    (50, 'Dia da Região Autónoma dos Açores'),  # Whit Monday
    (60, 'Corpo de Deus'),
]


def holiday_calendar(year: int) -> list[tuple[date, str]]:
    """Every seeded holiday for ``year``, sorted by date."""
    easter = easter_sunday(year)
    entries = [(date(year, month, day), name) for month, day, name in FIXED_NATIONAL]
    entries += [(easter + timedelta(days=offset), name) for offset, name in MOVABLE]
    return sorted(entries, key=lambda entry: entry[0])
