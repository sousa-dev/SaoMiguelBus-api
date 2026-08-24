"""Canonical stop names — the fix for upstream's inconsistent spellings.

Upstream emits the same place several ways: `P. DELGADA` for 36 names and
`PONTA DELGADA` for 3, `S. ROQUE` alongside `SÃO ROQUE`, `NORDESTE` alongside
`V. DO NORDESTE` and `VILA DO NORDESTE`. Because `derive_area_key` splits the
village prefix at the first " (" and `clean_string` folds only accents and
case, each spelling is its own area key — so "Ponta Delgada" finds 3 stops
instead of 38, and "São Vicente Ferreira" (29 stops) finds none at all, its two
spellings each looking like a sub-2-member singleton.

Driven by the same real /api/stops payload as the pole-collapse tests.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase

from azoresbus.services_names import (
    canonicalize,
    split_name,
    unexpanded_tokens,
    village_override,
)


FIXTURES = Path(__file__).parent / 'fixtures'


def upstream_stops() -> list[dict]:
    return json.loads((FIXTURES / 'stops.json').read_text(encoding='utf-8'))


class SplitNameTests(SimpleTestCase):
    def test_village_and_landmark(self):
        self.assertEqual(split_name('CAPELAS (IGREJA)'), ('CAPELAS', 'IGREJA'))

    def test_bare_name_declares_no_landmark(self):
        self.assertEqual(split_name('ACHADINHA'), ('ACHADINHA', None))

    def test_splits_on_the_first_paren_only(self):
        self.assertEqual(
            split_name('FAJÃ DE BAIXO (Cª DE SAÚDE DE S. MIGUEL)'),
            ('FAJÃ DE BAIXO', 'Cª DE SAÚDE DE S. MIGUEL'),
        )

    def test_pole_number_after_the_paren_is_pulled_inside(self):
        """`splitStopLabel` needs the name to END in ')' or it shows no subtitle."""
        self.assertEqual(
            split_name('ARRIFES (LG. DO BOM DESPACHO) 1'),
            ('ARRIFES', 'LG. DO BOM DESPACHO 1'),
        )


class ExpansionTests(SimpleTestCase):
    def test_street_abbreviations(self):
        self.assertEqual(
            canonicalize('S. ROQUE (R. DO PORTO)'), 'São Roque (Rua do Porto)',
        )

    def test_stacked_abbreviations(self):
        self.assertEqual(
            canonicalize('P. DELGADA (LG. ALM. DUNN)'),
            'Ponta Delgada (Largo Almirante Dunn)',
        )

    def test_connectors_stay_lowercase_but_not_in_first_position(self):
        self.assertEqual(canonicalize('VILA DO NORDESTE (ER)'), 'Vila do Nordeste (ER)')

    def test_roman_numerals_survive(self):
        self.assertEqual(
            canonicalize('FAJÃ DE BAIXO (PÇ. D. PEDRO IV)'),
            'Fajã de Baixo (Praça Dom Pedro IV)',
        )

    def test_acronyms_survive(self):
        self.assertEqual(
            canonicalize('P. DELGADA (EB/JI DA MATRIZ)'),
            'Ponta Delgada (EB/JI da Matriz)',
        )

    def test_personal_initials_are_not_expanded(self):
        """"A." here is a middle initial, not an abbreviation of a word."""
        self.assertEqual(
            canonicalize('LOMBA DO LOUÇÃO (R. GUSTAVO A. MEDEIROS 1)'),
            'Lomba do Loução (Rua Gustavo A. Medeiros 1)',
        )

    def test_ordinals_survive(self):
        self.assertEqual(
            canonicalize('PICO DA PEDRA (R. 1º BARÃO DA FONTE BELA 1)'),
            'Pico da Pedra (Rua 1º Barão da Fonte Bela 1)',
        )

    def test_apostrophe_inside_one_token(self):
        self.assertEqual(
            canonicalize('ÁGUA D`ALTO (LOMBINHA)'), "Água d'Alto (Lombinha)",
        )

    def test_apostrophe_split_across_two_tokens(self):
        """Upstream writes "D’ ÁGUA" with a space; it is still one word."""
        self.assertEqual(
            canonicalize('CABOUCO (ESTR. REGO D’ ÁGUA)'), "Cabouco (Estrada Rego d'Água)",
        )

    def test_phrase_override_beats_the_token_table(self):
        """"Cª" is Casa here and Canada elsewhere; "S." is Santa, not São."""
        self.assertEqual(
            canonicalize('P. DELGADA (S. Cª MISERICÓRDIA)'),
            'Ponta Delgada (Santa Casa da Misericórdia)',
        )

    def test_bare_C_is_centro_or_campo_never_an_initial(self):
        """"C." looks like a middle initial to a naive rule, and is not one.

        Without a phrase entry, `RIBEIRA GRANDE (C. S.)` canonicalizes to
        "Centro São" -- `C.` survives as an initial and `S.` expands to the
        wrong saint.
        """
        self.assertEqual(
            canonicalize('RIBEIRA GRANDE (C. S.)'), 'Ribeira Grande (Centro de Saúde)',
        )
        self.assertEqual(
            canonicalize('STO. ANTÓNIO BAIXO (C. CULTURAL)'),
            'Santo António Baixo (Centro Cultural)',
        )
        self.assertEqual(
            canonicalize('PONTA GARÇA (C. FUTEBOL)'), 'Ponta Garça (Campo de Futebol)',
        )

    def test_canada_and_casa_are_told_apart(self):
        self.assertEqual(
            canonicalize('STO. ANTÓNIO CIMA (Cª DO ALFAIATE)'),
            'Santo António Cima (Canada do Alfaiate)',
        )
        self.assertEqual(
            canonicalize('SETE CIDADES (Cª DO POVO)'), 'Sete Cidades (Casa do Povo)',
        )

    def test_phrase_matching_is_token_aware_not_substring(self):
        """Regression: a substring pass rewrites the "ER" inside "SUPERM.".

        `ER` is a real token (Estrada Regional) that must survive title casing,
        but matching it as a substring splits `SUPERM.` in half, and its own
        expansion then silently misses.
        """
        self.assertEqual(
            canonicalize('ER RIBEIRA GRANDE (SUPERM.)'),
            'ER Ribeira Grande (Supermercado)',
        )


class StructuralTests(SimpleTestCase):
    def test_pole_number_on_the_prefix_moves_into_the_landmark(self):
        """Otherwise each numbered variant is its own 1-member area key.

        `LOMBA DO BOTÃO 1/2/3`, `LOMBA DO CARRO 1/2/3` and `LOMBA DO POMAR
        1/2/3` are 9 stops that `build_area_index` drops today for being
        singletons.
        """
        self.assertEqual(canonicalize('LOMBA DO BOTÃO 1'), 'Lomba do Botão (1)')

    def test_rossio_is_reparented_under_capelas(self):
        """Rossio is a locality OF Capelas, spelled three ways upstream.

        Poles 1650 and 1651 are 23 m apart and both sit 80-92 m from the
        existing `CAPELAS (ROSSIO)` (poles 1302/1303), so the village really
        is Capelas.
        """
        self.assertEqual(
            canonicalize('ROSSIO (CAIXA AGRÍCOLA)'), 'Capelas (Rossio, Caixa Agrícola)',
        )
        self.assertEqual(
            canonicalize('ROSSIO DAS CAPELAS (ESCOLA)'), 'Capelas (Rossio, Escola)',
        )

    def test_numbered_variants_stay_distinct_stops(self):
        """`LOMBA DO BOTÃO 1/2/3` are three real stops, not one split three ways.

        1 and 2 are 148 m apart, 3 is 973 m from 1. Parenthesising the
        discriminator must keep them distinct -- collapsing them to a bare
        `Lomba do Botão` would fuse stops a kilometre apart.
        """
        names = {canonicalize(f'LOMBA DO BOTÃO {n}') for n in (1, 2, 3)}
        self.assertEqual(len(names), 3)
        self.assertEqual(
            sorted(names),
            ['Lomba do Botão (1)', 'Lomba do Botão (2)', 'Lomba do Botão (3)'],
        )


class VillageMergeTests(SimpleTestCase):
    def test_ponta_delgada_spellings_converge(self):
        self.assertEqual(
            canonicalize('P. DELGADA (MARINA)'), 'Ponta Delgada (Marina)',
        )
        self.assertEqual(
            canonicalize('PONTA DELGADA (MOAÇOR)'), 'Ponta Delgada (Moaçor)',
        )

    def test_all_three_nordeste_spellings_converge(self):
        for raw in ['NORDESTE (PEDREIRA)', 'V. DO NORDESTE (TERMINAL)',
                    'VILA DO NORDESTE (ESCOLA)']:
            self.assertTrue(canonicalize(raw).startswith('Vila do Nordeste ('), raw)

    def test_sao_roque_spellings_converge(self):
        self.assertEqual(canonicalize('S. ROQUE (IGREJA)'), 'São Roque (Igreja)')
        self.assertEqual(canonicalize('SÃO ROQUE (IGREJA)'), 'São Roque (Igreja)')


class SantaBarbaraCollisionTests(SimpleTestCase):
    """`STA. BÁRBARA` is TWO villages 16.5 km apart.

    Poles 1773/1774 sit 0.4 km from `STA. BÁRBARA BAIXO` and 0.6 km from
    `STA. BÁRBARA CIMA`; poles 5200-5220 sit 0.8 km from Ribeira Seca. A blind
    `STA. -> Santa` rewrite merges two real places into one area, which is
    exactly the failure this whole module exists to avoid.
    """

    def test_the_two_clusters_get_different_names(self):
        near_cima = canonicalize('STA. BÁRBARA (R. ARADO GRANDE)', '1773')
        near_ribeira_grande = canonicalize('STA. BÁRBARA (R. DO MEIO)', '5217')
        self.assertNotEqual(near_cima, near_ribeira_grande)

    def test_the_ribeira_grande_cluster_is_disambiguated(self):
        self.assertEqual(
            canonicalize('STA. BÁRBARA (BOCA DA RIBEIRA)', '5206'),
            'Santa Bárbara da Ribeira Grande (Boca da Ribeira)',
        )

    def test_the_other_cluster_joins_the_unabbreviated_spelling(self):
        self.assertEqual(
            canonicalize('STA. BÁRBARA (R. ARADO GRANDE)', '1773'),
            'Santa Bárbara (Rua Arado Grande)',
        )
        self.assertEqual(
            canonicalize('SANTA BÁRBARA (ESCOLAS)', '1726'), 'Santa Bárbara (Escolas)',
        )

    def test_the_code_scoped_rule_is_declared_before_the_general_one(self):
        self.assertEqual(
            village_override('STA. BÁRBARA', '5206'), 'Santa Bárbara da Ribeira Grande',
        )
        self.assertEqual(village_override('STA. BÁRBARA', '1773'), 'Santa Bárbara')

    def test_merge_can_be_disabled(self):
        """The span guard backs a merge out by NOT expanding the village.

        Expansion is itself a merge operator -- "S. ROQUE" and "SÃO ROQUE"
        become one village the moment `S.` expands -- so reverting only the
        curated overrides would leave that merge standing. The landmark half
        is still expanded; the ambiguity is about which village, not which
        street.
        """
        self.assertEqual(
            canonicalize('P. DELGADA (LG. ALM. DUNN)', merge=False),
            'P. Delgada (Largo Almirante Dunn)',
        )
        self.assertEqual(
            canonicalize('STA. BÁRBARA (R. DO MEIO)', '5217', merge=False),
            'Sta. Bárbara (Rua do Meio)',
        )


class RealPayloadTests(SimpleTestCase):
    """Against all 1456 real poles, not hand-picked examples."""

    def setUp(self):
        self.stops = upstream_stops()
        self.canonical = [
            (stop, canonicalize(stop['name'], str(stop['nameShort'])))
            for stop in self.stops
        ]

    def test_every_abbreviation_is_expanded(self):
        """A token surviving here is one missing from the tables."""
        leftover = sorted({
            token for _, name in self.canonical for token in unexpanded_tokens(name)
        })
        self.assertEqual(leftover, [])

    def test_canonicalization_is_idempotent(self):
        """The data migration re-runs this over already-canonical names."""
        for stop, name in self.canonical:
            self.assertEqual(canonicalize(name, str(stop['nameShort'])), name)

    def test_the_parenthesis_convention_is_preserved(self):
        """`derive_area_key` and the webapp's `deriveAreaKey` depend on it."""
        for stop, name in self.canonical:
            if ' (' in stop['name']:
                self.assertIn(' (', name, stop['name'])
                self.assertTrue(name.endswith(')'), name)

    def test_only_two_names_genuinely_merge(self):
        """Both are one physical stop upstream spelled two ways.

        `S. ROQUE (BARRACUDA)` / `SÃO ROQUE (BARRACUDA)` are 15 m apart, and
        `P. DELGADA (AV. D. JOÃO III)` / `(AV. DOM JOÃO III)` are 41 m apart on
        consecutive pole codes — the two sides of one road.
        """
        merged: dict[str, set[str]] = {}
        for stop, name in self.canonical:
            merged.setdefault(name, set()).add(stop['name'])
        collisions = {name: raw for name, raw in merged.items() if len(raw) > 1}
        self.assertEqual(
            sorted(collisions),
            ['Ponta Delgada (Avenida Dom João III)', 'São Roque (Barracuda)'],
        )

    def test_no_canonical_name_contains_a_dash_separator(self):
        """`serialize_legacy_stops_v2` splits on " - " to build v1/v2 aliases.

        `compat.py` does `stop.name.split(' - ')[0]` for every stop. Upstream
        AzoresBus names contain no " - ", which is why that path is a silent
        no-op for this dataset today -- introducing one would emit a phantom
        stop named "Capelas (Rossio" with an unbalanced paren.
        """
        offenders = [name for _, name in self.canonical if ' - ' in name]
        self.assertEqual(offenders, [])

    def test_distinct_name_count(self):
        self.assertEqual(len({stop['name'] for stop in self.stops}), 816)
        self.assertEqual(len({name for _, name in self.canonical}), 814)
