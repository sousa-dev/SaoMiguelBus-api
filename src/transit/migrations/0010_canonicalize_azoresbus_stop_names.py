"""Rewrite AzoresBus stop names to their canonical form, in place.

`Stop` carries no upstream id -- `cleaned_name` IS its identity -- and nothing
in this codebase prunes stops. So letting the next sync discover the rename
would create a second row per renamed stop and strand the original: 437 of
them, un-deletable because `StopTime.stop` is PROTECT, with StopTimes split
across old and new rows (only trips whose `payload_hash` changed get their
StopTimes rebuilt).

Renaming in place instead preserves `Stop.pk`, which is what mobile
favourites, `/transit/stop/:id` links, `AtlasPoi.external_refs.transitStopId`
and the offline bundle's stop indices are all built on.

`services_names.canonicalize` is idempotent over its own output, so this
migration is safe to re-run and converges with `_reconcile_stop`, which does
the same work on every sync.
"""

from __future__ import annotations

from django.db import migrations

from azoresbus.services_names import canonicalize
from transit.services.legacy_import import clean_string


DATASET_AZORESBUS = 'azoresbus'
SOURCE_TRANSIT = 'transit'


def _pole_code(external_stops, stop_id: str) -> str:
    """Any pole code for this stop -- the code-scoped village rules need one.

    `STA. BÁRBARA` names two villages, and only the pole code tells them
    apart. Codes within one stop always belong to the same village, so the
    lowest is as good as any and keeps the run deterministic.
    """
    codes = sorted(
        code for code in external_stops.get(stop_id, ()) if code
    )
    return codes[0] if codes else ''


# Any 64-bit constant; only has to be unique among this project's advisory locks.
_MIGRATION_LOCK_ID = 8_275_310_441_002


def _serialize_across_containers(schema_editor):
    """Make concurrent `manage.py migrate` runs safe.

    `runserver.sh` (web) and `celery-entrypoint.sh` (worker AND beat) all run
    `migrate` on boot, and compose starts them in parallel -- three processes
    can enter this migration at once. Django takes no lock of its own, so
    without this two of them could interleave the merge step: one repoints
    StopTimes onto a survivor while another deletes the row it just chose.

    `pg_advisory_xact_lock` is released automatically when the surrounding
    transaction ends, so a crashed migration cannot strand it. The losers wait,
    then re-run a body that is idempotent by construction and find nothing to
    do.
    """
    if schema_editor is None or schema_editor.connection.vendor != 'postgresql':
        return  # SQLite tests are single-process
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [_MIGRATION_LOCK_ID])


def canonicalize_stop_names(apps, schema_editor):
    _serialize_across_containers(schema_editor)

    Stop = apps.get_model('transit', 'Stop')
    StopAlias = apps.get_model('transit', 'StopAlias')
    StopTime = apps.get_model('transit', 'StopTime')
    ExternalStop = apps.get_model('azoresbus', 'ExternalStop')
    AtlasPoi = apps.get_model('atlas', 'AtlasPoi')

    stops = list(
        Stop.objects.filter(dataset=DATASET_AZORESBUS).order_by('pk'),
    )
    if not stops:
        return

    codes_by_stop: dict[int, list[str]] = {}
    for stop_id, code in ExternalStop.objects.filter(
        dataset=DATASET_AZORESBUS,
    ).values_list('stop_id', 'code'):
        codes_by_stop.setdefault(stop_id, []).append(str(code))

    touched_islands: set[int] = set()

    for stop in stops:
        if not Stop.objects.filter(pk=stop.pk).exists():
            continue  # already absorbed as the loser of an earlier merge

        old_cleaned = stop.cleaned_name
        canonical = canonicalize(stop.name, _pole_code(codes_by_stop, stop.pk))
        new_cleaned = clean_string(canonical)

        # Two upstream spellings of one road pair converging on one name.
        # Repoint before deleting -- StopTime.stop is PROTECT.
        duplicate = (
            Stop.objects.filter(
                island_id=stop.island_id,
                dataset=DATASET_AZORESBUS,
                cleaned_name=new_cleaned,
            )
            .exclude(pk=stop.pk)
            .order_by('pk')
            .first()
        )
        if duplicate is not None:
            survivor, loser = (
                (stop, duplicate) if stop.pk < duplicate.pk else (duplicate, stop)
            )
            StopTime.objects.filter(stop=loser).update(stop=survivor)
            ExternalStop.objects.filter(stop=loser).update(stop=survivor)
            StopAlias.objects.filter(stop=loser).update(stop=survivor)
            AtlasPoi.objects.filter(
                island_id=loser.island_id,
                source=SOURCE_TRANSIT,
                source_ref=loser.cleaned_name,
            ).delete()
            loser.delete()
            stop = survivor

        if stop.name != canonical or stop.cleaned_name != new_cleaned:
            stop.name = canonical
            stop.cleaned_name = new_cleaned
            stop.save(update_fields=['name', 'cleaned_name'])
            touched_islands.add(stop.island_id)

        if old_cleaned and old_cleaned != new_cleaned:
            # The name every existing favourite, deep link and shared URL was
            # built on. Skipped if some other stop legitimately owns it now.
            taken = Stop.objects.filter(
                island_id=stop.island_id,
                dataset=DATASET_AZORESBUS,
                cleaned_name=old_cleaned,
            ).exists()
            if not taken:
                StopAlias.objects.update_or_create(
                    island_id=stop.island_id,
                    dataset=DATASET_AZORESBUS,
                    cleaned_alias=old_cleaned,
                    defaults={'stop': stop},
                )

            # `atlas/importers/base.py` tombstones any owned POI whose
            # source_ref stops being emitted, and sets description/media/tips
            # on CREATE only. Without this the next Atlas run would unpublish
            # 437 bus stops, recreate them with fresh uids, and lose every
            # enrichment plus every Hub deep link.
            AtlasPoi.objects.filter(
                island_id=stop.island_id,
                source=SOURCE_TRANSIT,
                source_ref=old_cleaned,
            ).update(source_ref=new_cleaned)

    # The offline bundle's version hashes COUNTS, not content, so a pure
    # rename would otherwise leave every phone on the old names.
    if touched_islands:
        from transit.services.offline_bundle import bump_data_revision

        for island_id in sorted(touched_islands):
            bump_data_revision(island_id)


def noop_reverse(apps, schema_editor):
    """Irreversible by design.

    The verbatim upstream names survive on `ExternalStop.name`, so a rollback
    is a re-sync, not a reverse migration.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('transit', '0009_stop_alias'),
        ('azoresbus', '0002_periodic_tasks'),
        ('atlas', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(canonicalize_stop_names, noop_reverse),
    ]
