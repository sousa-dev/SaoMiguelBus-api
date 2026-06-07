"""Registry of agent-facing documentation files served by the API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings


@dataclass(frozen=True)
class AgentDocument:
    slug: str
    title: str
    description: str
    format: str
    path: Path
    category: str = 'repository'

    def exists(self) -> bool:
        return self.path.is_file()

    def stat(self) -> dict[str, Any]:
        if not self.exists():
            return {}
        mtime = datetime.fromtimestamp(self.path.stat().st_mtime, tz=timezone.utc)
        return {
            'size_bytes': self.path.stat().st_size,
            'updated_at': mtime.isoformat(),
        }

    def read_text(self) -> str:
        return self.path.read_text(encoding='utf-8')

    def to_index_item(self, request) -> dict[str, Any]:
        item = {
            'slug': self.slug,
            'title': self.title,
            'description': self.description,
            'format': self.format,
            'category': self.category,
            'url': request.build_absolute_uri(f'/api/v3/agent-docs/{self.slug}'),
            'available': self.exists(),
        }
        if self.exists():
            item.update(self.stat())
        return item


def repo_root() -> Path:
    return Path(settings.BASE_DIR).parent


def handbook_root() -> Path:
    return Path(settings.BASE_DIR) / 'documentation' / 'docs'


EXTERNAL_REFERENCES: list[dict[str, str]] = [
    {
        'slug': 'sdd-index',
        'title': 'SDD (System Design Docs)',
        'description': 'Architecture source of truth in the SaoMiguelBus mobile repo.',
        'url': 'https://github.com/sousa-dev/SaoMiguelBus/tree/revamp/SDD',
        'category': 'external',
    },
    {
        'slug': 'sdd-api-design',
        'title': 'SDD — API Design',
        'description': 'v3 endpoint inventory, compat contract, module boundaries.',
        'url': 'https://github.com/sousa-dev/SaoMiguelBus/blob/revamp/SDD/04-api-design.md',
        'category': 'external',
    },
    {
        'slug': 'webapp-agents-md',
        'title': 'Webapp AGENTS.md',
        'description': 'Agent instructions for the React webapp repository.',
        'url': 'https://github.com/sousa-dev/SaoMiguelBus-webapp/blob/main/AGENTS.md',
        'category': 'external',
    },
]


def _documents() -> list[AgentDocument]:
    root = repo_root()
    base = Path(settings.BASE_DIR)

    return [
        AgentDocument(
            slug='agents-md',
            title='AGENTS.md',
            description='Primary LLM agent instructions for this API repository.',
            format='markdown',
            path=root / 'AGENTS.md',
            category='repository',
        ),
        AgentDocument(
            slug='readme',
            title='README.md',
            description='Repository overview, layout, and quick-start commands.',
            format='markdown',
            path=root / 'README.md',
            category='repository',
        ),
        AgentDocument(
            slug='env-example',
            title='Environment variables (.env.example)',
            description='All supported environment variables with defaults and comments.',
            format='env',
            path=base / 'src' / '.env.example',
            category='configuration',
        ),
        AgentDocument(
            slug='ai-agents-handbook',
            title='djast AI Agents Handbook',
            description='Cursor rules, slash commands, and djast-* custom agents.',
            format='markdown',
            path=handbook_root() / '1_get_started' / '4_ai_agents.md',
            category='handbook',
        ),
        AgentDocument(
            slug='feature-toggles',
            title='Feature toggles',
            description='How apps are enabled/disabled in settings.py.',
            format='markdown',
            path=handbook_root() / '2_configuration' / '1_feature_toggles.md',
            category='handbook',
        ),
        AgentDocument(
            slug='adding-an-app',
            title='Adding a Django app',
            description='Scaffold checklist for new SMB domain modules.',
            format='markdown',
            path=handbook_root() / '6_customization' / '2_adding_an_app.md',
            category='handbook',
        ),
        AgentDocument(
            slug='traffic-readme',
            title='Traffic module README',
            description='Traffic incidents module setup and API notes.',
            format='markdown',
            path=base / 'traffic' / 'README.md',
            category='module',
        ),
    ]


def list_documents() -> list[AgentDocument]:
    return _documents()


def get_document(slug: str) -> AgentDocument | None:
    return next((doc for doc in _documents() if doc.slug == slug), None)
