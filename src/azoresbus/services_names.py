"""Canonical stop names for the AzoresBus network.

Upstream spells the same place several ways. 36 stop names begin ``P. DELGADA``
and 3 begin ``PONTA DELGADA``; ``S. ROQUE`` and ``SÃO ROQUE`` both exist; so do
``V. DO NORDESTE``, ``VILA DO NORDESTE`` and ``NORDESTE``. 68 distinct
abbreviated tokens appear across the payload, 40 of which ALSO appear expanded
somewhere in the same payload.

That is not cosmetic. ``derive_area_key`` splits the village prefix off at the
first " (" and ``clean_string`` folds only accents, case and hyphens -- so
"P. DELGADA" and "PONTA DELGADA" are two different area keys, and a user
searching "Ponta Delgada" gets 3 stops instead of 38. ``SÃO VICENTE FERREIRA``
is worse: 29 stops, and the area is dropped entirely because each spelling
looks like a sub-2-member singleton to ``build_area_index``.

This module produces ONE name per place, in the form a user would actually
type it: Portuguese title case, abbreviations expanded, accents kept.

    S. ROQUE (R. DO PORTO)      ->  São Roque (Rua do Porto)
    P. DELGADA (LG. ALM. DUNN)  ->  Ponta Delgada (Largo Almirante Dunn)
    ROSSIO (CAIXA AGRÍCOLA)     ->  Capelas (Rossio - Caixa Agrícola)
    LOMBA DO BOTÃO 1            ->  Lomba do Botão (1)

The ``VILLAGE (LANDMARK)`` convention is preserved deliberately and must stay
that way: ``derive_area_key`` and the webapp's ``deriveAreaKey`` both depend on
splitting at the first " (". Rewriting it to "Village — Landmark" would
silently disable village search island-wide.

WHY EXPANSION ALONE IS NOT SAFE
-------------------------------
``STA. BÁRBARA`` denotes two different villages 16.5 km apart (poles 1773/1774
next to Santa Bárbara Cima/Baixo, and poles 5200-5220 out by Ribeira Seca). A
blind ``STA. -> Santa`` rewrite merges them into one area. ``S.`` expands to
São/Santo/Santa/Sete/Seca and ``P.`` to Ponta/Porto/Pico/Pedra/Praia, so the
same trap exists for tokens we have not hit yet.

Hence the split below: rules handle the unambiguous bulk, ``VILLAGE_OVERRIDES``
handles the merges rules cannot derive (keyed by pole code where the code is
what disambiguates), and ``collapse_stops`` runs a geographic span guard over
the RESULT so a collision we did not anticipate is reported rather than
silently merged.
"""

from __future__ import annotations

import re
import unicodedata


# Connectors stay lowercase unless they open the name: "Vila do Nordeste",
# "Rua da Igreja", but "Da Ponte" if a name ever begins with one.
CONNECTORS = frozenset(
    {'de', 'da', 'do', 'das', 'dos', 'e', 'em', 'no', 'na', 'nos', 'nas', 'a', 'o'},
)

# Tokens that are acronyms, not words, and must survive title casing intact.
# ER = Estrada Regional, the island's trunk-road naming.
ACRONYMS = frozenset({'ER', 'EBI', 'EB/JI', 'PDL', 'AVIGEX/DIONISIO', 'PROVISE/SERVIEL'})

_ROMAN_RE = re.compile(r'^[IVX]+$')
_ORDINAL_RE = re.compile(r'^\d+[ºª]?$')
_INITIAL_RE = re.compile(r'^[A-ZÁÉÍÓÚÂÊÔÃÕÇ]\.$')
_APOSTROPHES = str.maketrans({'`': "'", '’': "'", '‘': "'"})
_TRAILING_NUMBER_RE = re.compile(r'^(.*?)\s+(\d+)$')
_PAREN_THEN_NUMBER_RE = re.compile(r'^(.*)\)\s+(\d+)$')

# Unambiguous one-token expansions. Every one of these has exactly one sensible
# reading in this corpus -- the ambiguous ones live in PHRASE_OVERRIDES instead.
ABBREVIATIONS: dict[str, str] = {
    'R.': 'Rua',
    'RUA': 'Rua',
    'AV.': 'Avenida',
    'LG.': 'Largo',
    'PÇ.': 'Praça',
    'PC.': 'Praça',
    'TV.': 'Travessa',
    'TRAV.': 'Travessa',
    'BC.': 'Beco',
    'ESTR.': 'Estrada',
    'CAN.': 'Canada',
    'RAM.': 'Ramal',
    'ROT.': 'Rotunda',
    'AL.': 'Alameda',
    'PTE.': 'Ponte',
    'CRZ.': 'Cruzamento',
    'CRUZ.': 'Cruzamento',
    'ENT.': 'Entrada',
    'DIR.': 'Direita',
    'MIRAD.': 'Miradouro',
    'GR.': 'Grota',
    'QTA.': 'Quinta',
    'STO.': 'Santo',
    'STA.': 'Santa',
    'SRA.': 'Senhora',
    'NS.': 'Nossa',
    'N.': 'Nossa',
    'PE.': 'Padre',
    'PDE.': 'Padre',
    'DR.': 'Doutor',
    'ENG.': 'Engenheiro',
    'PROF.': 'Professor',
    'CARD.': 'Cardeal',
    'ALM.': 'Almirante',
    'CAP.': 'Capitão',
    'MDA.': 'Madre',
    'INF.': 'Infante',
    'FRAN.': 'Francisco',
    'MTS.': 'Montes',
    'Mº': 'Moinho',
    'PQ.': 'Parque',
    'ESTAC.': 'Estacionamento',
    'ESC.': 'Escola',
    'SEC.': 'Secundária',
    'AGRUP.': 'Agrupamento',
    'MUS.': 'Museu',
    'OBS.': 'Observatório',
    'MONUM.': 'Monumento',
    'PAL.': 'Palácio',
    'ED.': 'Edifício',
    'FÁB.': 'Fábrica',
    'PLANT.': 'Plantação',
    'ESTALG.': 'Estalagem',
    'REST.': 'Restaurante',
    'SUPERM.': 'Supermercado',
    'MINIMERC.': 'Minimercado',
    'HIPER.': 'Hipermercado',
    'MERC.': 'Mercado',
    'AG.': 'Agência',
    'FIL.ª': 'Filarmónica',
    'FIG.ª': 'Figueira',
    'EB.': 'Escola Básica',
    'EST.': 'Estádio',
    'V.': 'Vila',
    'P.': 'Ponta',
    'S.': 'São',
}

# Multi-token readings that the single-token table would get WRONG. Matched on
# whole-token sequences, longest first, BEFORE ABBREVIATIONS runs.
#
# Token-aware matching is load-bearing, not fastidiousness: a substring pass
# rewrites the "ER" inside "SUPERM.", splitting the token so its own expansion
# then misses. There is a regression test for exactly that.
PHRASE_OVERRIDES: list[tuple[tuple[str, ...], str]] = [
    (('S.', 'Cª', 'MISERICÓRDIA'), 'Santa Casa da Misericórdia'),
    (('Cª', 'DE', 'SAÚDE', 'DE', 'S.', 'MIGUEL'), 'Casa de Saúde de São Miguel'),
    (('Cª', 'POVO', 'RIBEIRA', 'GRANDE'), 'Casa do Povo da Ribeira Grande'),
    (('Cª', 'NATÁLIA', 'CORREIA'), 'Casa Natália Correia'),
    (('Cª', 'DO', 'POVO'), 'Casa do Povo'),
    (('Cª', 'CORREIO'), 'Casa do Correio'),
    (('Cª', 'DO', 'ALFAIATE'), 'Canada do Alfaiate'),
    (('Cª', 'DE', 'GALO'), 'Canada de Galo'),
    (('Cª', 'TELHADA'), 'Canada Telhada'),
    (('Cª', 'PIEDADE'), 'Canada da Piedade'),
    (('C.', 'CÍVICO'), 'Centro Cívico'),
    (('C.', 'CULTURAL'), 'Centro Cultural'),
    (('C.', 'S.'), 'Centro de Saúde'),
    (('C.', 'FUTEBOL'), 'Campo de Futebol'),
    (('EST.', 'DE', 'S.', 'MIGUEL'), 'Estádio de São Miguel'),
    (('D.', 'AMÉLIA'), 'Dona Amélia'),
    (('D.', 'JOÃO', 'III'), 'Dom João III'),
    (('DOM', 'JOÃO', 'III'), 'Dom João III'),
    (('D.', 'PEDRO', 'IV'), 'Dom Pedro IV'),
    (('D.', 'HENRIQUE'), 'Dom Henrique'),
    (('S.', 'JOSÉ'), 'São José'),
    (('S.', 'SEBASTIÃO'), 'São Sebastião'),
    (('S.', 'MIGUEL'), 'São Miguel'),
    (('S.', 'BRÁS'), 'São Brás'),
    (('S.', 'PEDRO'), 'São Pedro'),
    (('STA.', 'TERESA'), 'Santa Teresa'),
    (('STA.', 'RITA'), 'Santa Rita'),
    (('STA.', 'LUZIA'), 'Santa Luzia'),
    (('STO.', 'ANTÃO'), 'Santo Antão'),
    (('STO.', 'CRISTO'), 'Santo Cristo'),
    (('ESPÍRITO', 'STO.'), 'Espírito Santo'),
]
PHRASE_OVERRIDES.sort(key=lambda entry: len(entry[0]), reverse=True)


class VillageRule:
    """One curated village-prefix merge.

    ``codes`` narrows the rule to a pole-code range. That is what makes the two
    Santa Bárbaras separable: the name alone cannot tell them apart, but poles
    5200-5220 are unambiguously the Ribeira Grande one.
    """

    __slots__ = ('prefixes', 'canonical', 'codes')

    def __init__(self, prefixes, canonical, codes=None):
        self.prefixes = frozenset(prefixes)
        self.canonical = canonical
        self.codes = codes

    def matches(self, prefix: str, code: str) -> bool:
        if prefix not in self.prefixes:
            return False
        if self.codes is None:
            return True
        low, high = self.codes
        return code.isdigit() and low <= int(code) <= high


# Order matters: the first match wins, so narrower code-scoped rules come first.
VILLAGE_OVERRIDES: list[VillageRule] = [
    VillageRule(
        ['STA. BÁRBARA', 'SANTA BÁRBARA'],
        'Santa Bárbara da Ribeira Grande',
        codes=(5200, 5220),
    ),
    VillageRule(['STA. BÁRBARA', 'SANTA BÁRBARA'], 'Santa Bárbara'),
    VillageRule(['P. DELGADA', 'PONTA DELGADA'], 'Ponta Delgada'),
    VillageRule(['NORDESTE', 'V. DO NORDESTE', 'VILA DO NORDESTE'], 'Vila do Nordeste'),
    VillageRule(['S. ROQUE', 'SÃO ROQUE'], 'São Roque'),
    VillageRule(['S. VICENTE FERREIRA', 'SÃO VICENTE FERREIRA'], 'São Vicente Ferreira'),
    VillageRule(['STO. ANTÓNIO CIMA', 'SANTO ANTÓNIO CIMA'], 'Santo António Cima'),
    VillageRule(['LOMBA DE S. PEDRO', 'LOMBA DE SÃO PEDRO'], 'Lomba de São Pedro'),
    VillageRule(['GR. DO MORRO', 'GROTA DO MORRO'], 'Grota do Morro'),
]

# Prefixes that move under another village, carrying their old name into the
# sub-name so nothing is lost. Rossio is a locality OF Capelas -- upstream
# spells it both "ROSSIO" and "ROSSIO DAS CAPELAS", 23 m apart on consecutive
# pole codes, and "CAPELAS (ROSSIO)" already exists as a third spelling.
#
# The separator is ", " and must NOT be " - ": `serialize_legacy_stops_v2`
# splits on " - " to synthesise the v1/v2 short-name alias rows, so a name
# containing one would emit a phantom stop called "Capelas (Rossio" with an
# unbalanced paren. AzoresBus names contain no " - " today, which is exactly
# why that code path is currently a silent no-op for this dataset.
REPARENTED: dict[str, tuple[str, str]] = {
    'ROSSIO': ('CAPELAS', 'Rossio'),
    'ROSSIO DAS CAPELAS': ('CAPELAS', 'Rossio'),
}

LOCALITY_SEPARATOR = ', '

# Set of canonical names produced by an explicit override above. The span guard
# in ``collapse_stops`` exempts these: they are deliberate, human-approved
# merges, which is how Vila do Nordeste's 5.6 km span is allowed through.
CURATED_CANONICAL_NAMES = frozenset(
    [rule.canonical for rule in VILLAGE_OVERRIDES] + ['Capelas'],
)


def _join_apostrophes(tokens: list[str]) -> list[str]:
    """Glue "D’" + "ÁGUA" into one token so it title-cases as d'Água.

    Upstream is inconsistent: "ÁGUA D`ALTO" is one token with a backtick,
    "ESTR. REGO D’ ÁGUA" is two tokens with a curly apostrophe and a space.
    """
    joined: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.endswith("'") and index + 1 < len(tokens):
            joined.append(token + tokens[index + 1])
            index += 2
        else:
            joined.append(token)
            index += 1
    return joined


def _apply_phrases(tokens: list[str]) -> list[str]:
    """Replace known multi-token phrases, matching on whole tokens only."""
    out: list[str] = []
    index = 0
    while index < len(tokens):
        for phrase, replacement in PHRASE_OVERRIDES:
            width = len(phrase)
            if tuple(tokens[index:index + width]) == phrase:
                out.extend(replacement.split(' '))
                index += width
                break
        else:
            out.append(tokens[index])
            index += 1
    return out


def _title_token(token: str, position: int) -> str:
    """Title-case one token, leaving the things that must not be touched."""
    if token in ACRONYMS or _ROMAN_RE.match(token) or _ORDINAL_RE.match(token):
        return token
    if _INITIAL_RE.match(token):
        return token
    lowered = token.lower()
    if position > 0 and lowered in CONNECTORS:
        return lowered
    if any(char.islower() for char in token[1:]):
        # Already cased by a phrase override -- do not re-capitalize "do".
        return token
    if "'" in token:
        head, _, tail = token.partition("'")
        prefix = head.lower() if position > 0 and len(head) == 1 else head.capitalize()
        return f"{prefix}'{tail.capitalize()}"
    return token.capitalize()


def _titlecase_only(text: str) -> str:
    """Title-case without expanding anything -- keeps "S." distinct from "São"."""
    tokens = _join_apostrophes(text.translate(_APOSTROPHES).split())
    return ' '.join(
        _title_token(token, position) for position, token in enumerate(tokens)
    )


def _canonicalize_fragment(text: str) -> str:
    """Expand abbreviations and title-case one side of the parentheses."""
    tokens = _join_apostrophes(text.translate(_APOSTROPHES).split())
    tokens = _apply_phrases(tokens)
    expanded: list[str] = []
    for token in tokens:
        replacement = ABBREVIATIONS.get(token)
        expanded.extend(replacement.split(' ') if replacement else [token])
    return ' '.join(
        _title_token(token, position) for position, token in enumerate(expanded)
    )


def split_name(name: str) -> tuple[str, str | None]:
    """Split ``VILLAGE (LANDMARK)`` into its two halves.

    Mirrors ``derive_area_key``: split at the FIRST " (" so the prefix is the
    same string the area index will key on.

    "ARRIFES (LG. DO BOM DESPACHO) 1" carries its pole number AFTER the closing
    paren, which leaves the name unparseable by the webapp's ``splitStopLabel``
    (it requires the string to end in ")") -- so it renders raw with no
    subtitle. Pull the number inside the parentheses where it belongs.
    """
    if ' (' not in name:
        return name.strip(), None
    prefix, _, rest = name.partition(' (')
    trailing = _PAREN_THEN_NUMBER_RE.match(rest)
    if trailing:
        sub = f'{trailing.group(1)} {trailing.group(2)}'
    elif rest.endswith(')'):
        sub = rest[:-1]
    else:
        sub = rest
    return prefix.strip(), sub.strip() or None


def village_override(prefix: str, code: str) -> str | None:
    """The curated canonical village for this raw prefix, or None."""
    for rule in VILLAGE_OVERRIDES:
        if rule.matches(prefix, code):
            return rule.canonical
    return None


def canonical_village(prefix: str, code: str, *, merge: bool = True) -> str:
    """Canonical form of a village prefix.

    ``merge=False`` is the span guard backing a merge out. It skips BOTH the
    curated overrides and the abbreviation expansion, leaving only title
    casing -- because expansion is itself a merge operator: "S. FICTÍCIA" and
    "SÃO FICTÍCIA" become one village the moment ``S.`` expands. Reverting the
    overrides alone would leave that merge standing.

    The LANDMARK half is still fully expanded either way. The ambiguity is
    about which village a stop is in, never about which street.
    """
    if not merge:
        return _titlecase_only(prefix)
    override = village_override(prefix, code)
    if override:
        return override
    return _canonicalize_fragment(prefix)


def canonicalize(name: str, code: str = '', *, merge: bool = True) -> str:
    """The canonical display name for one upstream stop.

    ``code`` is the upstream ``nameShort`` pole code, needed only by the
    code-scoped village rules. ``merge=False`` disables the curated village
    merges; see ``canonical_village``.
    """
    prefix, sub = split_name(name)

    reparent = REPARENTED.get(prefix)
    if reparent and merge:
        prefix, locality = reparent
        sub = f'{locality}{LOCALITY_SEPARATOR}{sub}' if sub else locality

    if sub is None:
        # "LOMBA DO BOTÃO 1" -- a discriminator sitting OUTSIDE the
        # parentheses, so `derive_area_key` reads the whole string as the
        # village and each numbered variant becomes its own 1-member area key.
        # `build_area_index` then drops all 9 of them for being singletons.
        #
        # These are three genuinely different stops, not duplicates: 1 and 2
        # are 148 m apart and 3 is nearly a kilometre from 1. Parenthesising
        # the discriminator keeps them distinct while letting them rejoin
        # their village -- `lomba do botao` goes from 6 members to 9.
        trailing = _TRAILING_NUMBER_RE.match(prefix)
        if trailing:
            prefix, sub = trailing.group(1), trailing.group(2)

    canonical_prefix = canonical_village(prefix, code, merge=merge)
    if sub is None:
        return canonical_prefix
    return f'{canonical_prefix} ({_canonicalize_fragment(sub)})'


def unexpanded_tokens(name: str) -> list[str]:
    """Abbreviated tokens that survived canonicalization.

    Anything here is a token missing from the tables above. ``collapse_stops``
    reports these rather than shipping them, so a new upstream abbreviation
    surfaces as a line in the sync report instead of as an odd-looking name.
    """
    suspicious: list[str] = []
    for fragment in unicodedata.normalize('NFC', name).replace(')', '(').split('('):
        for position, token in enumerate(fragment.split()):
            if not token.endswith('.'):
                continue
            if not _INITIAL_RE.match(token):
                suspicious.append(token)
            elif position == 0:
                # "C. São" -- a lone capital opening a fragment is an
                # abbreviation we failed to expand, not somebody's middle
                # initial. "Rua Gustavo A. Medeiros" is the legitimate shape,
                # and there the initial never comes first.
                suspicious.append(token)
    return suspicious
