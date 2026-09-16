"""Let an explicit assistant format win over generic client Accept headers."""

from __future__ import annotations

from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.renderers import JSONRenderer

from assistant.renderers import MarkdownRenderer


class AssistantContentNegotiation(DefaultContentNegotiation):
    def select_renderer(self, request, renderers, format_suffix=None):
        explicit_format = request.query_params.get('format')
        if explicit_format == 'md':
            return MarkdownRenderer(), MarkdownRenderer.media_type
        if explicit_format == 'json':
            return JSONRenderer(), JSONRenderer.media_type
        return super().select_renderer(request, renderers, format_suffix)
