"""Seed 2026-2027 holidays; production stops at 2025-06-19.

Without these rows ``is_holiday`` is false for every date in the changeover
window, so search diverges from upstream on every holiday, bootstrap and both
offline bundles ship a list ending in 2025 (clients compute their own day-type
from it), and the AzoresBus sampler guard that refuses to treat a holiday as
weekday evidence silently becomes a no-op. See 00 prerequisite and 98 B6.

The date arithmetic is inlined rather than imported from
``transit.services.holidays`` so this migration stays frozen: a later change to
that module must not retroactively alter what this migration seeded.
``transit/tests/test_holiday_seed.py`` asserts the two agree today.
"""

from datetime import date, timedelta

from django.db import migrations


FIXED_NATIONAL = [
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

# (offset from Easter Sunday, name, sao_miguel_only)
MOVABLE = [
    (-2, 'Sexta-feira Santa', False),
    (0, 'Páscoa', False),
    (35, 'Senhor Santo Cristo dos Milagres', True),
    (50, 'Dia da Região Autónoma dos Açores', False),
    (60, 'Corpo de Deus', False),
]

SEED_YEARS = (2026, 2027)


def _easter_sunday(year):
    """Anonymous Gregorian computus. 2026 -> 04-05, 2027 -> 03-28."""
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


def _entries_for(year, island_key):
    easter = _easter_sunday(year)
    entries = [(date(year, month, day), name) for month, day, name in FIXED_NATIONAL]
    for offset, name, sao_miguel_only in MOVABLE:
        if sao_miguel_only and island_key != 'sao-miguel':
            continue
        entries.append((easter + timedelta(days=offset), name))
    return sorted(entries, key=lambda entry: entry[0])


def seed_holidays(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    Holiday = apps.get_model('transit', 'Holiday')

    for island in Island.objects.all():
        for year in SEED_YEARS:
            for holiday_date, name in _entries_for(year, island.key):
                Holiday.objects.update_or_create(
                    island=island,
                    date=holiday_date,
                    defaults={
                        'name': name,
                        'legacy_ref': {'source': 'seed_holidays_2026_2027'},
                    },
                )


def unseed_holidays(apps, schema_editor):
    """Remove only rows this migration created, never hand-curated ones."""
    Holiday = apps.get_model('transit', 'Holiday')
    Holiday.objects.filter(
        date__year__in=SEED_YEARS,
        legacy_ref__source='seed_holidays_2026_2027',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('transit', '0003_adevent'),
        ('tenancy', '0018_seed_sao_miguel_island'),
    ]

    operations = [
        migrations.RunPython(seed_holidays, unseed_holidays),
    ]
