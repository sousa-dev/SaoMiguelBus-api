"""Documentation views.

Renders markdown files from ``documentation/docs/`` as HTML pages with
sidebar navigation and full-text search.
"""

from __future__ import annotations

import os
import re
from typing import Any

import markdown2
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render


def docs_view(
    request: HttpRequest,
    section: str = "get_started",
    page: str = "index",
) -> HttpResponse:
    """Render a single documentation page within *section*."""
    docs_dir = _docs_dir()
    sections = _collect_sections(docs_dir)

    section_dir = next(
        (os.path.join(docs_dir, s["dir_name"]) for s in sections if s["section"] == section),
        None,
    )
    if section_dir is None or not os.path.isdir(section_dir):
        raise Http404("Documentation section not found.")

    subsections, markdown_file = _collect_subsections(section_dir, page)

    with open(markdown_file, "r", encoding="utf-8") as fh:
        markdown_content = fh.read()

    html_content = markdown2.markdown(
        markdown_content,
        extras=["fenced-code-blocks", "tables", "code-friendly"],
    )

    page_title = (
        f"{section.replace('_', ' ').title()} - {page.replace('_', ' ').title()}"
        if page != "index"
        else section.replace("_", " ").title()
    )

    return render(request, "documentation/docs.html", {
        "content": html_content,
        "sections": sections,
        "subsections": subsections,
        "current_section": section,
        "current_page": page,
        "current_path": f"{section}/{os.path.basename(markdown_file)}",
        "section_display_name": section.replace("_", " ").title(),
        "page_display_name": page.replace("_", " ").title(),
        "page_title": page_title,
    })


def search_docs(request: HttpRequest) -> HttpResponse:
    """Full-text search across all markdown documentation files."""
    query = request.GET.get("q", "").strip()
    docs_dir = _docs_dir()
    sections = _collect_sections(docs_dir)
    results: list[dict[str, Any]] = []

    if query:
        for root, _dirs, files in os.walk(docs_dir):
            for filename in files:
                if not filename.endswith(".md"):
                    continue
                file_path = os.path.join(root, filename)
                with open(file_path, "r", encoding="utf-8") as fh:
                    content = fh.read()
                if query.lower() not in content.lower():
                    continue

                relative_path = os.path.relpath(file_path, docs_dir)
                dir_name, _ = os.path.split(relative_path)

                section_parts = dir_name.split("/", 1)
                section_dir = section_parts[0]
                section_name = _strip_numeric_prefix(section_dir)

                results.append({
                    "section": section_name,
                    "subsection": "index",
                    "display_name": section_name.replace("_", " ").title(),
                    "file_display_name": filename.replace(".md", "").replace("_", " ").title(),
                    "file_name": "_".join(filename.replace(".md", "").split("_")[1:]),
                    "content_preview": _content_preview(content, query),
                })

    return render(request, "documentation/search_results.html", {
        "query": query,
        "search_results": results,
        "page_title": "Search Results",
        "sections": sections,
    })


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _docs_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "docs")


def _strip_numeric_prefix(name: str) -> str:
    """Remove a leading ``<digits>_`` prefix from a directory/file name."""
    parts = name.split("_", 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1]
    return name


def _collect_sections(docs_dir: str) -> list[dict[str, Any]]:
    """Build a list of section metadata from the docs directory."""
    sections: list[dict[str, Any]] = []
    for dir_name in sorted(os.listdir(docs_dir)):
        dir_path = os.path.join(docs_dir, dir_name)
        if not os.path.isdir(dir_path):
            continue
        section_name = _strip_numeric_prefix(dir_name)
        sections.append({
            "section": section_name,
            "subsections": _collect_subsections(dir_path)[0],
            "display_name": section_name.replace("_", " ").title(),
            "dir_name": dir_name,
        })
    return sections


def _collect_subsections(
    section_dir: str, page: str = "index"
) -> tuple[list[dict[str, Any]], str]:
    """Collect subsection metadata and resolve the markdown file to render."""
    subsections: list[dict[str, Any]] = []
    markdown_file: str | None = None

    for filename in sorted(os.listdir(section_dir)):
        if not filename.endswith(".md"):
            continue
        name = os.path.splitext(filename)[0]
        subsection_name = _strip_numeric_prefix(name)

        subsections.append({
            "subsection": subsection_name,
            "display_name": subsection_name.replace("_", " ").title(),
            "file": filename,
            "path": os.path.join(
                re.sub(r"\d+_", "", os.path.basename(section_dir)), filename
            ),
        })

        if subsection_name == page:
            markdown_file = os.path.join(section_dir, filename)

    if markdown_file is None or not os.path.exists(markdown_file):
        markdown_file = os.path.join(section_dir, "index.md")
        if not os.path.exists(markdown_file):
            raise Http404("Documentation page not found.")

    return subsections, markdown_file


def _content_preview(content: str, query: str, length: int = 150) -> str:
    """Return a text snippet centred around the first occurrence of *query*."""
    start = content.lower().find(query.lower())
    if start == -1:
        return content[:length]
    start = max(start - 20, 0)
    end = min(start + length, len(content))
    return content[start:end] + ("..." if end < len(content) else "")
