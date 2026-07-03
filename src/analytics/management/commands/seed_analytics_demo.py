"""Seed demo analytics data (legacy stats, v3 events, ads) for the dashboard."""

from __future__ import annotations

import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.models import AnalyticsEvent, Stat
from tenancy.models import Island
from transit.models import Ad, AdEvent

DEMO_MARKER = {'seeded_by': 'seed_analytics_demo'}
DEMO_AD_PREFIX = 'demo-ad-'

ROUTES = [
    ('Ponta Delgada', 'Ribeira Grande', 30),
    ('Ponta Delgada', 'Furnas', 22),
    ('Ponta Delgada', 'Lagoa', 18),
    ('Ribeira Grande', 'Ponta Delgada', 16),
    ('Lagoa', 'Vila Franca do Campo', 10),
    ('Vila Franca do Campo', 'Furnas', 8),
    ('Ponta Delgada', 'Sete Cidades', 8),
    ('Ponta Delgada', 'Nordeste', 5),
    ('Furnas', 'Povoação', 4),
    ('Ribeira Grande', 'Maia', 3),
]
PLATFORMS = ['web', 'android', 'ios']
PLATFORM_WEIGHTS = [5, 3, 2]
LOCALES = ['pt', 'en', 'de', 'fr', 'es']
LOCALE_WEIGHTS = [5, 4, 2, 1, 1]
DAY_TYPES = ['weekday', 'saturday', 'sunday']

MODULE_EVENTS = [
    ('transit', 'view', 4),
    ('news', 'view', 3),
    ('news', 'open_article', 2),
    ('trails', 'view', 2),
    ('seismic', 'view', 1),
    ('traffic', 'view', 1),
]


class Command(BaseCommand):
    help = 'Seed ~60 days of demo Stat/AnalyticsEvent/Ad/AdEvent rows for the dashboard.'

    def add_arguments(self, parser):
        parser.add_argument('--island', default='sao-miguel', help='Island key (default: sao-miguel)')
        parser.add_argument('--days', type=int, default=60, help='How many days back to seed')
        parser.add_argument('--clear', action='store_true', help='Remove previously seeded demo rows first')
        parser.add_argument('--seed', type=int, default=42, help='Random seed (deterministic by default)')

    def handle(self, *args, **options):
        try:
            island = Island.objects.get(key=options['island'])
        except Island.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Unknown island: {options['island']}"))
            return

        rng = random.Random(options['seed'])
        now = timezone.now()
        days = options['days']

        if options['clear']:
            self._clear_demo(island)

        stats = self._seed_legacy(rng, now, days)
        events = self._seed_v3(island, rng, now, days)
        ads, ad_events = self._seed_ads(island, rng, now, days)

        self.stdout.write(
            self.style.SUCCESS(
                f'Seeded {stats} legacy stats, {events} v3 events, '
                f'{ads} ads with {ad_events} ad events over {days} days.'
            )
        )

    def _day_volume(self, rng: random.Random, day_offset: int, base: int) -> int:
        # Weekly rhythm + mild long-term growth toward the present.
        weekday_boost = 1.4 if day_offset % 7 < 5 else 0.8
        growth = 1.0 + (0.5 * (1 - day_offset / 90))
        return max(1, int(base * weekday_boost * growth * rng.uniform(0.7, 1.3)))

    def _seed_legacy(self, rng: random.Random, now, days: int) -> int:
        rows = []
        for day in range(days):
            for _ in range(self._day_volume(rng, day, 10)):
                origin, destination, _ = rng.choices(ROUTES, weights=[w for _, _, w in ROUTES])[0]
                rows.append(Stat(
                    request='GET_ROUTE',
                    origin=origin,
                    destination=destination,
                    type_of_day=rng.choice(DAY_TYPES).upper(),
                    time=f'{rng.randint(7, 20):02d}:00',
                    platform=rng.choices(PLATFORMS, weights=PLATFORM_WEIGHTS)[0],
                    language=rng.choices(LOCALES, weights=LOCALE_WEIGHTS)[0],
                ))
        created = Stat.objects.bulk_create(rows)
        # bulk_create can't set auto_now_add timestamps — spread them afterwards.
        for day, chunk in self._group_by_day(created, rng, now, days):
            Stat.objects.filter(id__in=[s.id for s in chunk]).update(
                timestamp=now - timedelta(days=day, hours=rng.randint(0, 23))
            )
        return len(created)

    def _group_by_day(self, rows, rng: random.Random, now, days: int):
        per_day = max(1, len(rows) // max(days, 1))
        for day in range(days):
            chunk = rows[day * per_day:(day + 1) * per_day]
            if chunk:
                yield day, chunk

    def _seed_v3(self, island: Island, rng: random.Random, now, days: int) -> int:
        rows = []
        for day in range(days):
            when = now - timedelta(days=day)
            # transit searches
            for _ in range(self._day_volume(rng, day, 8)):
                origin, destination, _ = rng.choices(ROUTES, weights=[w for _, _, w in ROUTES])[0]
                rows.append(AnalyticsEvent(
                    island=island,
                    module='transit',
                    event_type='search',
                    properties={
                        **DEMO_MARKER,
                        'origin': origin,
                        'destination': destination,
                        'day_type': rng.choice(DAY_TYPES),
                        'results_count': rng.randint(0, 6),
                    },
                    session_hash=f'demo-sess-{day}-{rng.randint(0, 5)}',
                    consent_state={'analytics': True},
                    platform=rng.choices(PLATFORMS, weights=PLATFORM_WEIGHTS)[0],
                    locale=rng.choices(LOCALES, weights=LOCALE_WEIGHTS)[0],
                    app_version='3.0.0',
                    occurred_at=when - timedelta(hours=rng.randint(0, 23)),
                ))
            # other module traffic
            for module, event_type, weight in MODULE_EVENTS:
                for _ in range(self._day_volume(rng, day, weight)):
                    rows.append(AnalyticsEvent(
                        island=island,
                        module=module,
                        event_type=event_type,
                        properties=dict(DEMO_MARKER),
                        session_hash=f'demo-sess-{day}-{rng.randint(0, 5)}',
                        consent_state={'analytics': True},
                        platform=rng.choices(PLATFORMS, weights=PLATFORM_WEIGHTS)[0],
                        locale=rng.choices(LOCALES, weights=LOCALE_WEIGHTS)[0],
                        app_version='3.0.0',
                        occurred_at=when - timedelta(hours=rng.randint(0, 23)),
                    ))
        AnalyticsEvent.objects.bulk_create(rows, batch_size=500)
        return len(rows)

    def _seed_ads(self, island: Island, rng: random.Random, now, days: int) -> tuple[int, int]:
        specs = [
            ('Cafe Central', 'home', 0.10),
            ('Hotel Azul', 'interstitial', 0.03),
            ('Tours Ilha Verde', 'home', 0.06),
        ]
        event_rows = []
        for idx, (entity, slot, ctr) in enumerate(specs, start=1):
            ad, _ = Ad.objects.get_or_create(
                island=island,
                entity=entity,
                defaults={
                    'media': f'https://example.com/{DEMO_AD_PREFIX}{idx}.png',
                    'start': now - timedelta(days=days),
                    'end': now + timedelta(days=30),
                    'advertise_on': slot,
                    'platform': 'all',
                    'status': 'active',
                },
            )
            impressions = clicks = 0
            for day in range(days):
                when = now - timedelta(days=day)
                for _ in range(self._day_volume(rng, day, 6 - idx)):
                    platform = rng.choices(PLATFORMS, weights=PLATFORM_WEIGHTS)[0]
                    event_rows.append(AdEvent(
                        island=island, ad=ad, kind=AdEvent.KIND_IMPRESSION,
                        platform=platform,
                        occurred_at=when - timedelta(hours=rng.randint(0, 23)),
                    ))
                    impressions += 1
                    if rng.random() < ctr:
                        event_rows.append(AdEvent(
                            island=island, ad=ad, kind=AdEvent.KIND_CLICK,
                            platform=platform,
                            occurred_at=when - timedelta(hours=rng.randint(0, 23)),
                        ))
                        clicks += 1
            Ad.objects.filter(id=ad.id).update(seen=impressions, clicked=clicks)
        AdEvent.objects.unscoped().bulk_create(event_rows, batch_size=500)
        return len(specs), len(event_rows)

    def _clear_demo(self, island: Island) -> None:
        events = AnalyticsEvent.objects.for_island(island).filter(
            properties__seeded_by='seed_analytics_demo'
        )
        stats = Stat.objects.filter(request='GET_ROUTE', time__endswith=':00')
        demo_ads = Ad.objects.for_island(island).filter(media__contains=DEMO_AD_PREFIX)
        counts = (events.count(), stats.count(), demo_ads.count())
        events.delete()
        stats.delete()
        demo_ads.delete()  # cascades to AdEvent
        self.stdout.write(f'Removed {counts[0]} events, {counts[1]} stats, {counts[2]} ads.')
