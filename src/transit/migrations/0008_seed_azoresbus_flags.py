"""Seed the AzoresBus feature-flag block, with the cutover DISARMED.

Every phase decision is one field here, so a rollback is an admin edit rather
than a deploy (00 Rollback).

`cutoverAt` is deliberately null. Arming it before a reviewed sync has populated
the new network is the one sequence that can actually hurt: resolve_dataset would
flip on 1 September and the empty-dataset fallback only catches a TOTAL absence,
not a half-import. Set it in admin once `sync_azoresbus` has run and its diff has
been inspected.

Everything else ships ready: preview off, tracking off, and the observed term
start recorded as observed rather than official (98 §7).
"""

from django.db import migrations

ISLAND_KEY = 'sao-miguel'

FLAGS = {
    # null => resolve_dataset returns legacy forever. Set after a reviewed sync.
    'cutoverAt': None,
    'bannerUntil': '2026-10-01T00:00:00+00:00',
    'previewEnabled': False,
    'trackingEnabled': False,
    # OBSERVED on 2026-09-14, not published by the operator. Treated as a
    # bracket by the derivation, never as a fact.
    'observedTermStart': '2026-09-14',
    'banner': {
        'id': 'azoresbus-live-2026-09',
        'tone': 'info',
        'dismissible': False,
        'text': {
            'pt': 'Os novos horários da AzoresBus já estão em vigor.',
            'en': 'The new AzoresBus timetables are now in effect.',
        },
    },
    'badge': {
        'text': {
            'pt': 'Válido desde 1 de setembro',
            'en': 'Valid since 1 September',
        },
    },
}


def seed(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    island = Island.objects.filter(key=ISLAND_KEY).first()
    if island is None:
        return
    flags = dict(island.feature_flags or {})
    # Never clobber an operator's edits: only fill in what is missing.
    existing = dict(flags.get('azoresbus') or {})
    flags['azoresbus'] = {**FLAGS, **existing}
    island.feature_flags = flags
    island.save(update_fields=['feature_flags'])


def unseed(apps, schema_editor):
    Island = apps.get_model('tenancy', 'Island')
    island = Island.objects.filter(key=ISLAND_KEY).first()
    if island is None:
        return
    flags = dict(island.feature_flags or {})
    flags.pop('azoresbus', None)
    island.feature_flags = flags
    island.save(update_fields=['feature_flags'])


class Migration(migrations.Migration):

    dependencies = [
        ('transit', '0007_backfill_legacy_services'),
        ('tenancy', '0018_seed_sao_miguel_island'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
