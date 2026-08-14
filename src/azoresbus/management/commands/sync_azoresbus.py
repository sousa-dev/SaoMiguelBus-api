"""Sync AzoresBus schedules from upstream into transit models.

    python manage.py sync_azoresbus --dry-run          # plan only, no network
    python manage.py sync_azoresbus --dates A..B       # explicit sample
    python manage.py sync_azoresbus --no-prune         # never retire service

`--dry-run` fetches nothing. It prints the exact dates the run would sample, the
request budget it would spend and the retirement decision it would reach, which
is what you actually want to read on the morning of 1 September -- before a run
touches anything.

`--dates` makes the sample explicit and reproducible, because a run's
correctness now depends on WHICH dates it sampled (02 §4.7). Any run with a
non-standard sample implies --no-prune: a hand-picked window is not evidence
that anything outside it has gone away.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from azoresbus.client import AZORESBUS_SYNC_MAX_REQUESTS
from azoresbus.models import ServiceObservation, SyncRun
from azoresbus.services_sampling import DATA_FLOOR, build_sample
from azoresbus.services_sync import evaluate_retirement
from tenancy.models import Island
from tenancy.services import for_island
from transit.models import DATASET_AZORESBUS, Holiday, Trip
from transit.services.schedule_phase import today_in_azores

logger = logging.getLogger(__name__)

UPSTREAM_ROUTE_COUNT = 55


class Command(BaseCommand):
    help = 'Sync AzoresBus schedules. Use --dry-run first.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('--island', dest='island_key', default='sao-miguel')
        parser.add_argument('--dry-run', action='store_true',
                            help='Print the plan and change nothing.')
        parser.add_argument('--full', action='store_true',
                            help='Include the far-season week.')
        parser.add_argument('--dates', default='',
                            help='Explicit sample, e.g. 2026-09-14..2026-09-20')
        parser.add_argument('--no-prune', action='store_true',
                            help='Never retire service, whatever the gate says.')
        parser.add_argument('--max-requests', type=int,
                            default=AZORESBUS_SYNC_MAX_REQUESTS)

    def handle(self, *args, **options) -> None:
        island = Island.objects.filter(key=options['island_key']).first()
        if island is None:
            raise CommandError(f'Island not found: {options["island_key"]}')

        explicit = self._parse_dates(options['dates'])
        dry_run = bool(options['dry_run'])
        no_prune = bool(options['no_prune']) or bool(explicit)

        with for_island(island):
            holidays = set(
                Holiday.objects.filter(island=island).values_list('date', flat=True)
            )
            self._guard_holiday_table(holidays)

            if explicit:
                dates = explicit
                near, far = explicit, []
            else:
                sample = build_sample(
                    today=today_in_azores(),
                    holidays=holidays,
                    full=bool(options['full']) or self._needs_full_run(island),
                )
                dates, near, far = sample.all_dates, sample.near_week, sample.far_week

            self._report_plan(island, dates, near, far, options['max_requests'])
            self._report_retirement(island, near, far, no_prune)

            if dry_run:
                self.stdout.write(self.style.WARNING(
                    '\nDRY RUN -- nothing fetched, nothing written.'
                ))
                return

            self._execute(island, dates, near, far, holidays,
                          options['max_requests'], no_prune)

    # -- execution ----------------------------------------------------------

    def _execute(self, island, dates, near, far, holidays,
                 max_requests, no_prune) -> None:
        from azoresbus.client import AzoresbusClient, AzoresbusError
        from azoresbus.services_import import import_schedules

        run = SyncRun.objects.create(
            island=island,
            kind=SyncRun.KIND_SCHEDULES,
            sampled_dates=[day.isoformat() for day in dates],
        )
        client = AzoresbusClient(max_requests=max_requests)

        try:
            payloads = self._fetch(client, dates)
        except AzoresbusError as exc:
            run.status = SyncRun.STATUS_PARTIAL
            run.error = str(exc)
            run.request_count = client.request_count
            run.finished_at = timezone.now()
            run.save()
            raise CommandError(
                f'{exc}\nRun marked partial after {client.request_count} '
                'requests. Nothing was retired.'
            )

        report = import_schedules(
            island, run=run, holidays=holidays,
            sampled_dates=dates, **payloads,
        )

        decision = evaluate_retirement(
            status=SyncRun.STATUS_COMPLETED,
            journey_count=report['journey_count'],
            previous_journey_count=self._previous_count(island, run),
            sampled_dates=near,
            far_season_dates=far,
        )
        if no_prune:
            decision.allowed = False
            decision.reason = 'suppressed by --no-prune / explicit --dates'

        run.status = SyncRun.STATUS_COMPLETED
        run.request_count = client.request_count
        run.finished_at = timezone.now()
        run.stats = {**report, 'retirement': decision.as_dict()}
        run.save()

        self.stdout.write(self.style.SUCCESS(
            f'\nimported {report["lines"]} lines, {report["stops"]} stops, '
            f'{report["trips"]} trips in {client.request_count} requests'
        ))
        self.stdout.write(
            f'retirement        {"applied" if decision.allowed else "skipped"} '
            f'-- {decision.reason}'
        )

    def _fetch(self, client, dates) -> dict:
        """Index, route details, per-date listings, then journey details.

        Journey details are unavoidable: the listing carries no circulations, so
        a stored hash cannot skip the GET (98 §4 gap). The hash skips the write.
        """
        stops = client.get_json('/stops')
        routes = client.get_json('/routes?active=true&passengerInfo=true')

        journeys: dict = {}
        seen: dict[str, str] = {}
        for route in routes:
            route_id = str(route['id'])
            for day in dates:
                rows = client.get_json(
                    f'/routes/{route_id}/journeys?day={day.isoformat()}'
                )
                journeys[(route_id, day)] = rows
                for row in rows:
                    seen[str(row['id'])] = route_id

        details = {}
        for journey_id, route_id in seen.items():
            details[journey_id] = client.get_json(
                f'/routes/{route_id}/journeys/{journey_id}'
            )

        return {'stops': stops, 'routes': routes,
                'journeys': journeys, 'details': details}

    def _previous_count(self, island, current_run):
        previous = (
            SyncRun.objects.filter(
                island=island, kind=SyncRun.KIND_SCHEDULES,
                status=SyncRun.STATUS_COMPLETED,
            )
            .exclude(pk=current_run.pk)
            .order_by('-started_at')
            .first()
        )
        return (previous.stats or {}).get('journey_count') if previous else None

    # -- guards -------------------------------------------------------------

    def _guard_holiday_table(self, holidays: set[date]) -> None:
        """Refuse to derive patterns against an empty holiday year (98 B6).

        An empty holiday set for a year is a seeding bug, not a year without
        holidays. Deriving anyway records Sunday journey sets as weekday
        service, which is precisely the failure the guard exists to prevent.
        """
        year = today_in_azores().year
        if not any(day.year == year for day in holidays):
            raise CommandError(
                f'No Holiday rows for {year}. Refusing to derive patterns: an '
                'empty holiday year is a seeding bug, and sampling through it '
                'records Sunday sets as weekday service (98 B6). Run migrations '
                'so transit.0004_seed_holidays_2026_2027 applies.'
            )

    def _needs_full_run(self, island: Island) -> bool:
        """No stored far-season evidence => upgrade to a full run (02 §4.1)."""
        return not ServiceObservation.objects.filter(
            island=island, dataset=DATASET_AZORESBUS,
        ).exists()

    # -- reporting ----------------------------------------------------------

    def _report_plan(self, island, dates, near, far, max_requests) -> None:
        listings = UPSTREAM_ROUTE_COUNT * len(dates)
        # 2 index calls + one detail per route + the listings + roughly one
        # journey detail per journey seen.
        estimate = 2 + UPSTREAM_ROUTE_COUNT + listings + 1200

        self.stdout.write(f'island            {island.key}')
        self.stdout.write(f'dataset           {DATASET_AZORESBUS}')
        self.stdout.write(f'sampled dates     {len(dates)}')
        for day in dates:
            tier = 'near' if day in near else ('far' if day in far else 'extra')
            self.stdout.write(f'  {day}  {day:%a}  {tier}')
        self.stdout.write(f'floor             {DATA_FLOOR} (never sample below)')
        self.stdout.write(
            f'requests          ~{estimate} '
            f'({listings} listings + ~1200 details), cap {max_requests}'
        )
        if estimate > max_requests:
            self.stdout.write(self.style.ERROR(
                '  estimate exceeds the cap: the run would be marked partial '
                'and would retire nothing.'
            ))
        self.stdout.write(
            f'duration          ~{estimate * 0.35 / 60:.0f} min at 0.35s'
        )

    def _report_retirement(self, island, near, far, no_prune) -> None:
        previous = (
            SyncRun.objects.filter(
                island=island, kind=SyncRun.KIND_SCHEDULES,
                status=SyncRun.STATUS_COMPLETED,
            )
            .order_by('-started_at')
            .first()
        )
        previous_count = (previous.stats or {}).get('journey_count') if previous else None
        current = Trip.objects.filter(
            island=island, dataset=DATASET_AZORESBUS,
        ).count()

        self.stdout.write('')
        self.stdout.write(f'existing trips    {current}')
        self.stdout.write(
            f'last good run     {previous.started_at:%Y-%m-%d %H:%M} '
            f'({previous_count} journeys)' if previous else
            'last good run     none'
        )

        if no_prune:
            self.stdout.write(self.style.WARNING(
                'retirement        suppressed (--no-prune or explicit --dates)'
            ))
            return

        decision = evaluate_retirement(
            status=SyncRun.STATUS_COMPLETED,
            journey_count=current or 1,
            previous_journey_count=previous_count,
            sampled_dates=near,
            far_season_dates=far,
        )
        style = self.style.SUCCESS if decision.allowed else self.style.WARNING
        self.stdout.write(style(
            f'retirement        {"allowed" if decision.allowed else "blocked"} '
            f'-- {decision.reason}'
        ))

    # -- parsing ------------------------------------------------------------

    def _parse_dates(self, raw: str) -> list[date]:
        if not raw.strip():
            return []
        out: set[date] = set()
        for chunk in raw.split(','):
            chunk = chunk.strip()
            if not chunk:
                continue
            if '..' in chunk:
                start, end = (self._one(p) for p in chunk.split('..', 1))
                if end < start:
                    raise CommandError(f'{chunk}: end precedes start')
                day = start
                while day <= end:
                    out.add(day)
                    day = day.fromordinal(day.toordinal() + 1)
            else:
                out.add(self._one(chunk))

        below = sorted(day for day in out if day < DATA_FLOOR)
        if below:
            raise CommandError(
                f'{below[0]} is below the {DATA_FLOOR} data floor. Upstream '
                'returns [] there because the feed has no data that far back, '
                'not because of any semantics -- sampling it would look like a '
                'network-wide deletion (98 B1).'
            )
        return sorted(out)

    def _one(self, raw: str) -> date:
        try:
            return datetime.strptime(raw.strip(), '%Y-%m-%d').date()
        except ValueError:
            raise CommandError(f'{raw!r} is not an ISO date (YYYY-MM-DD)')
