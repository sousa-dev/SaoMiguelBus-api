"""User-Agent -> known AI-crawler-name heuristic, for the `assistant_hit` log line.

Not a security control -- User-Agent is client-supplied and trivially spoofed.
Purely observability: whether the assistants this app exists for (ChatGPT,
Claude, Perplexity, search-engine AI crawlers, ...) are actually finding and
calling `/api/v3/ai/*` and `/llms.txt`.
"""

from __future__ import annotations

KNOWN_BOTS: tuple[str, ...] = (
    'GPTBot',
    'OAI-SearchBot',
    'ChatGPT-User',
    'ClaudeBot',
    'Claude-User',
    'Claude-SearchBot',
    'PerplexityBot',
    'Perplexity-User',
    'Google-Extended',
    'Googlebot',
    'Bingbot',
    'Applebot',
    'CCBot',
    'Amazonbot',
    'meta-externalagent',
    'DuckAssistBot',
)


def detect_bot(user_agent: str | None) -> str | None:
    """First known bot token found in `user_agent`, else `None`.

    Substring match on the lower-cased header: real crawler UAs vary the rest
    of the string (version, "+https://...") around a stable product token.
    """
    if not user_agent:
        return None
    lowered = user_agent.lower()
    for name in KNOWN_BOTS:
        if name.lower() in lowered:
            return name
    return None
