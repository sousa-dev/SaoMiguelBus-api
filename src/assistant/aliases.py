"""Curated aliases for common English / tourist search terms.

A hit here NEVER resolves a stop by itself -- `assistant.services.stop_finder`
only ever offers it as a scored candidate alongside the fuzzy matches, so
"airport" surfaces "Aeroporto" as something to retry with instead of the
caller being told nothing matched (and instead of the server silently
guessing, which is the one thing `/api/v3/ai/journeys` must never do -- a
wrong line is worse than no line).

Keys are matched against `transit.services.search.clean_string(query)`, so
they must already be lower-case, accent-stripped and hyphen-free.
"""

from __future__ import annotations

STOP_ALIASES: dict[str, str] = {
    'airport': 'Aeroporto',
    'the airport': 'Aeroporto',
    'airport pdl': 'Aeroporto',
    'hot springs': 'Furnas',
    'hot spring': 'Furnas',
    'thermal pools': 'Furnas',
    'thermal baths': 'Furnas',
    'lagoon': 'Sete Cidades',
    'lagoons': 'Sete Cidades',
    'blue lagoon': 'Sete Cidades',
    'green lagoon': 'Sete Cidades',
    'crater lake': 'Sete Cidades',
    'twin lakes': 'Sete Cidades',
    'downtown': 'Ponta Delgada',
    'city center': 'Ponta Delgada',
    'city centre': 'Ponta Delgada',
    'tea plantation': 'Gorreana',
    'tea factory': 'Gorreana',
    'waterfall': 'Ribeira dos Caldeiroes',
    'volcano': 'Sete Cidades',
    'viewpoint': 'Sete Cidades',
}
