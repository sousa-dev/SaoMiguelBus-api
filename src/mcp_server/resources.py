from __future__ import annotations

from agent_docs.manifest import get_document, list_documents

from mcp_server.instance import mcp


@mcp.resource('saomiguelbus://docs', name='agent-documents', mime_type='application/json')
def documents_resource() -> str:
    import json
    return json.dumps([
        {
            'slug': doc.slug,
            'title': doc.title,
            'description': doc.description,
            'format': doc.format,
        }
        for doc in list_documents()
    ])


@mcp.resource('saomiguelbus://docs/{slug}', name='agent-document', mime_type='text/markdown')
def document_resource(slug: str) -> str:
    document = get_document(slug)
    return document.read_text() if document and document.exists() else f'Unknown document: {slug}'


@mcp.resource('saomiguelbus://guide', name='guide', mime_type='text/markdown')
def guide_resource() -> str:
    return (
        '# São Miguel Bus MCP\n\n'
        'Use transit_journeys for real schedules. Times are local to Atlantic/Azores. '
        'Use transit_find_stops when a stop name is uncertain; never guess a stop. '
        'The optional island argument defaults to the configured live island.\n'
    )