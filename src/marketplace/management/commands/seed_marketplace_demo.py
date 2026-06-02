"""Seed published marketplace listings for local dev / demo."""

from __future__ import annotations

import random

from django.core.management.base import BaseCommand

from consent.services import hash_session_id
from marketplace import services
from marketplace.models import Review, ServiceCategory, ServiceProvider
from tenancy.models import Island
from tenancy.services import for_island

DEMO_SESSION_PREFIX = 'demo-seed-'

# (name, category_slug, bio snippet, hourly_rate or None, phone, lat, lng, promoted)
DEMO_PROVIDERS: list[tuple] = [
    ('Azores Transfer Co.', 'transfers', 'Aeroporto, hotel e porto — Ponta Delgada e ilha toda.', 35, '+351912100001', 37.7411, -25.6756, True),
    ('Taxi João Ponta Delgada', 'transfers', 'Serviço 24h na cidade e aeroporto.', 28, '+351912100002', 37.7394, -25.6687, False),
    ('São Miguel Island Tours', 'tours', 'Full-day van tours: Sete Cidades, Furnas, Nordeste.', 45, '+351912100003', 37.8225, -25.5178, True),
    ('Volcanic Lakes Experience', 'tours', 'Pequenos grupos à Lagoa do Fogo e Sete Cidades.', 50, '+351912100004', 37.8500, -25.7500, False),
    ('Guide Maria — História & Natureza', 'guides', 'Guiada certificada em PT/EN/FR.', 40, '+351912100005', 37.7560, -25.6600, False),
    ('Pedro Trekking Guide', 'guides', 'Trilhos PR e caminhadas costeiras.', 38, '+351912100006', 37.8100, -25.4200, False),
    ('Quinta das Hortênsias', 'accommodation', 'Quartos com pequeno-almoço em Furnas.', None, '+351912100007', 37.7710, -25.3040, False),
    ('Casa do Atlântico', 'accommodation', 'AL familiar com vista mar em Ribeira Grande.', None, '+351912100008', 37.8210, -25.5150, False),
    ('Dive Azores — São Miguel', 'activities', 'Mergulho e baptismo na costa sul.', 55, '+351912100009', 37.7150, -25.5200, True),
    ('Canyoning Açores', 'activities', 'Canyoning e coasteering com guias locais.', 65, '+351912100010', 37.7300, -25.4900, False),
    ('Whale Watch São Miguel', 'activities', 'Observação de cetáceos — saídas de Ponta Delgada.', 48, '+351912100011', 37.7380, -25.6650, False),
    ('Surf School Ribeira', 'activities', 'Aulas de surf e aluguer de pranchas.', 35, '+351912100012', 37.8150, -25.5300, False),
    ('Restaurante O Forno — Catering', 'food', 'Catering para eventos e grupos turísticos.', 30, '+351912100013', 37.7410, -25.6700, False),
    ('Sabores da Terra', 'food', 'Experiências gastronómicas em quintas locais.', 42, '+351912100014', 37.7800, -25.3500, False),
    ('Rent-a-Car São Miguel', 'rentals', 'Viaturas e carrinhas sem chauffeur.', 25, '+351912100015', 37.7420, -25.6970, False),
    ('E-Bike Azores', 'rentals', 'Aluguer de e-bikes e entrega no hotel.', 18, '+351912100016', 37.7400, -25.6720, False),
    ('Electricista Ribeira', 'other', 'Instalações eléctricas residenciais e comerciais.', 32, '+351912100017', 37.8200, -25.5100, False),
    ('Canalizador Furnas', 'other', 'Canalização, fugas e aquecimento.', 30, '+351912100018', 37.7700, -25.3100, False),
    ('Fotógrafo de Casamentos Açores', 'other', 'Sessões e casamentos em locais icónicos.', 75, '+351912100019', 37.7550, -25.6800, False),
    ('Jardim & Paisagismo Verde', 'other', 'Manutenção de jardins e relvados.', 22, '+351912100020', 37.7480, -25.6550, False),
    ('Pet Sit São Miguel', 'other', 'Passeio e cuidados de animais à domicílio.', 15, '+351912100021', 37.7350, -25.6750, False),
    ('Massagem & Bem-estar Furnas', 'other', 'Massagens terapêuticas pós-trilho.', 40, '+351912100022', 37.7690, -25.3050, False),
    ('Tradutor EN-PT Juramentado', 'other', 'Traduções e apoio burocrático.', 45, '+351912100023', 37.7415, -25.6670, False),
    ('Limpeza Doméstica Ponta Delgada', 'other', 'Limpeza regular ou one-off para AL.', 20, '+351912100024', 37.7370, -25.6620, False),
    ('Informática & Wi-Fi AL', 'other', 'Redes, routers e suporte a alojamento local.', 35, '+351912100025', 37.7430, -25.6710, False),
    ('Pintura & Remodelação', 'other', 'Interiores, exteriores e pequenas obras.', 28, '+351912100026', 37.7520, -25.6480, False),
    ('Yoga ao Ar Livre — Sete Cidades', 'activities', 'Aulas matinais com vista para a lagoa.', 25, '+351912100027', 37.8450, -25.7800, False),
    ('Pesca Desportiva São Miguel', 'activities', 'Embarcações partilhadas e privadas.', 80, '+351912100028', 37.7310, -25.6580, False),
]

REVIEW_SNIPPETS = [
    ('Excelente serviço, pontual e simpático.', 5),
    ('Recomendo — muito profissional.', 5),
    ('Boa experiência, voltaria a contratar.', 4),
    ('Preço justo para a qualidade.', 4),
    ('Comunicação fácil por WhatsApp.', 5),
    ('Serviço correcto, nada a apontar.', 4),
    ('Fantástico para turistas de primeira viagem.', 5),
]


class Command(BaseCommand):
    help = 'Seed ~28 published marketplace providers (and sample reviews) for demo/dev.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--island',
            default='sao-miguel',
            help='Island key (default: sao-miguel)',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=0,
            help='Max providers to create (0 = all demo rows, default 28)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Remove providers/reviews seeded by this command first',
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
            self.stdout.write(f'Removed {removed} demo provider(s).')

        rows = DEMO_PROVIDERS
        if options['count'] > 0:
            rows = rows[: options['count']]

        created = 0
        with for_island(island):
            categories = {c.slug: c for c in ServiceCategory.objects.all()}
            if not categories:
                self.stderr.write(
                    self.style.ERROR(
                        'No categories on this island — run migrations first '
                        '(0002_seed_default_categories).'
                    )
                )
                return

            for idx, row in enumerate(rows, start=1):
                (
                    name,
                    cat_slug,
                    bio,
                    hourly_rate,
                    phone,
                    lat,
                    lng,
                    is_promoted,
                ) = row
                if cat_slug not in categories:
                    self.stderr.write(self.style.WARNING(f'Skip {name}: unknown category {cat_slug}'))
                    continue

                session_id = f'{DEMO_SESSION_PREFIX}{idx}'
                session_hash = hash_session_id(session_id, island.key)

                if ServiceProvider.objects.filter(
                    island=island,
                    name=name,
                    created_by_session_hash=session_hash,
                ).exists():
                    continue

                payload = services.create_provider(
                    island=island,
                    session_hash=session_hash,
                    data={
                        'name': name,
                        'category_slug': cat_slug,
                        'bio': bio,
                        'hourly_rate': hourly_rate,
                        'phone': phone,
                        'whatsapp': phone,
                        'email': f'demo{idx}@example.com',
                        'latitude': lat,
                        'longitude': lng,
                    },
                )
                provider = ServiceProvider.objects.get(id=payload['id'])
                provider.is_promoted = is_promoted
                provider.status = ServiceProvider.PUBLISHED
                provider.save(update_fields=['is_promoted', 'status', 'updated_at'])

                review_count = random.randint(1, 3)
                for r_idx in range(review_count):
                    text, rating = random.choice(REVIEW_SNIPPETS)
                    reviewer_session = f'{DEMO_SESSION_PREFIX}review-{idx}-{r_idx}'
                    reviewer_hash = hash_session_id(reviewer_session, island.key)
                    result = services.upsert_review(
                        provider_id=provider.id,
                        session_hash=reviewer_hash,
                        rating=rating,
                        text=text,
                    )
                    if result:
                        review_id = result[0]['id']
                        services.moderate_review(review_id, 'publish')

                services.recompute_rating(provider)
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Seeded {created} published provider(s) on {island_key} '
                f'({len(rows)} demo rows available).'
            )
        )

    def _clear_demo(self, island: Island) -> int:
        with for_island(island):
            providers = ServiceProvider.objects.filter(
                created_by_session_hash__startswith=DEMO_SESSION_PREFIX
            )
            count = providers.count()
            Review.objects.filter(provider__in=providers).delete()
            providers.delete()
            return count
