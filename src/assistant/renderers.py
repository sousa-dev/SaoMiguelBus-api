"""Plain Markdown renderer for the assistant journeys endpoint."""

from __future__ import annotations

import json

from rest_framework.renderers import BaseRenderer


class MarkdownRenderer(BaseRenderer):
    media_type = 'text/markdown'
    format = 'md'
    charset = 'utf-8'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, str):
            return data.encode(self.charset)
        return ('```json\n' + json.dumps(data, ensure_ascii=False) + '\n```\n').encode(self.charset)
