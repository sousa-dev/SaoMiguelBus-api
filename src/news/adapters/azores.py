"""Parse açores.net ALRA/JORAA daily digest RSS descriptions into individual items."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup, Tag


def _preceding_h3(li: Tag) -> str:
    for sibling in li.previous_elements:
        if isinstance(sibling, Tag) and sibling.name == 'h3':
            return sibling.get_text(' ', strip=True)
    return ''


def _nested_summary(li: Tag) -> str:
    nested = li.find('ul')
    if not nested:
        return ''
    lines: list[str] = []
    for child in nested.find_all('li', recursive=False):
        text = child.get_text(' ', strip=True)
        if text:
            lines.append(text)
    return '\n'.join(lines)


def _is_item_li(li: Tag) -> bool:
    if li.name != 'li':
        return False
    direct_a = li.find('a', recursive=False)
    direct_ul = li.find('ul', recursive=False)
    return direct_a is not None and direct_ul is not None


def parse_azores_digest(description_html: str) -> list[dict[str, Any]]:
    """Split a digest description into one dict per top-level list item."""
    if not description_html or not description_html.strip():
        return []

    soup = BeautifulSoup(description_html, 'html.parser')
    items: list[dict[str, Any]] = []

    for li in soup.find_all('li'):
        if not _is_item_li(li):
            continue

        anchor = li.find('a', recursive=False)
        if anchor is None:
            continue

        title = anchor.get_text(' ', strip=True)
        link = (anchor.get('href') or '').strip()
        if not title or not link:
            continue

        summary = _nested_summary(li)
        section = _preceding_h3(li)
        items.append(
            {
                'title': title,
                'link': link,
                'summary': summary,
                'section': section,
            }
        )

    return items
