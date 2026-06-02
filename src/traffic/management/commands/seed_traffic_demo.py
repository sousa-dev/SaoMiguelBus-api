"""Seed active + scheduled traffic reports for local dev / demo."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from consent.services import hash_session_id
from tenancy.models import Island
from tenancy.services import for_island
from traffic import services
from traffic.models import TrafficReport

DEMO_SESSION_PREFIX = 'demo-traffic-'

# (category_slug, road, description, lat, lng)
DEMO_REPORTS: list[tuple] = [
    ('acidente', 'EN1-1A', 'Despiste junto à rotunda, fila a formar-se.', 37.7411, -25.6756),
    ('transito', 'Av. Infante D. Henrique', 'Trânsito lento na marginal.', 37.7395, -25.6680),
    ('obras', 'EN1-1A — Lagoa', 'Trabalhos na via, uma faixa cortada.', 37.7450, -25.5700),
    ('desvio', 'Ribeira Grande', 'Desvio no centro por evento.', 37.8210, -25.5150),
    ('inundacao', 'EN1-1A — Água Retorta', 'Água na faixa após chuva forte.', 37.8000, -25.2300),
    ('perigo', 'Sete Cidades', 'Pedras na via na descida.', 37.8600, -25.7900),
    ('policia', 'Ponta Delgada', 'Fiscalização à saída da cidade.', 37.7360, -25.6600),
    ('tempo', 'Lagoa do Fogo', 'Nevoeiro denso, visibilidade reduzida.', 37.8550, -25.4750),
    ('acidente', 'Furnas', 'Colisão ligeira, trânsito condicionado.', 37.7710, -25.3100),
    ('transito', 'Nordeste', 'Fila à entrada da vila.', 37.8200, -25.1450),
]

# Schedulable radars announced in advance — (road, description, hours_from_now, duration_h, lat, lng)
DEMO_SCHEDULED: list[tuple] = [
    ('EN1-1A — Vila Franca', 'Radar anunciado pela PSP.', 2, 3, 37.7180, -25.4330),
    ('EN2-2A — Rabo de Peixe', 'Operação de velocidade.', 6, 2, 37.8050, -25.5800),
]


class Command(BaseCommand):
    help = 'Seed ~10 active + 2 scheduled traffic reports for demo/dev.'

    def add_arguments(self, parser):
        parser.add_argument('--island', default='sao-miguel', help='Island key (default: sao-miguel)')
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Remove reports seeded by this command first',
        )

    def handle(self, *args, **options):
        island_key: str = options['island']
        try:
            island = Island.objects.get(key=island_key)
        except Island.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'Unknown island: {island_key}'))
            return

        if options['clear']:
            removed = self._clear_demo(island)
            self.stdout.write(f'Removed {removed} demo report(s).')

        created = 0
        now = timezone.now()
        with for_island(island):
            for idx, (slug, road, desc, lat, lng) in enumerate(DEMO_REPORTS, start=1):
                session_hash = hash_session_id(f'{DEMO_SESSION_PREFIX}{idx}', island.key)
                if TrafficReport.objects.filter(
                    island=island,
                    created_by_session_hash=session_hash,
                ).exists():
                    continue
                try:
                    services.create_report(
                        island=island,
                        session_hash=session_hash,
                        category_slug=slug,
                        latitude=lat,
                        longitude=lng,
                        description=desc,
                        road=road,
                    )
                    created += 1
                except services.TrafficError as exc:
                    self.stderr.write(self.style.WARNING(f'Skip {slug} ({road}): {exc}'))

            for idx, (road, desc, start_h, dur_h, lat, lng) in enumerate(DEMO_SCHEDULED, start=1):
                session_hash = hash_session_id(f'{DEMO_SESSION_PREFIX}sched-{idx}', island.key)
                if TrafficReport.objects.filter(
                    island=island,
                    created_by_session_hash=session_hash,
                ).exists():
                    continue
                active_from = now + timedelta(hours=start_h)
                try:
                    services.create_report(
                        island=island,
                        session_hash=session_hash,
                        category_slug='radar',
                        latitude=lat,
                        longitude=lng,
                        description=desc,
                        road=road,
                        active_from=active_from,
                        active_until=active_from + timedelta(hours=dur_h),
                    )
                    created += 1
                except services.TrafficError as exc:
                    self.stderr.write(self.style.WARNING(f'Skip scheduled radar ({road}): {exc}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Seeded {created} traffic report(s) on {island_key} '
                f'({len(DEMO_REPORTS)} active + {len(DEMO_SCHEDULED)} scheduled available).'
            )
        )

    def _clear_demo(self, island: Island) -> int:
        with for_island(island):
            reports = TrafficReport.objects.filter(
                created_by_session_hash__startswith=DEMO_SESSION_PREFIX
            )
            count = reports.count()
            reports.delete()
            return count
