"""Agent documentation v3 API — machine-readable context for LLM agents."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from agent_docs.manifest import EXTERNAL_REFERENCES, get_document, list_documents


def _openapi_links(request: Request) -> dict[str, str]:
    return {
        'schema_url': request.build_absolute_uri('/api/schema/'),
        'swagger_ui_url': request.build_absolute_uri('/api/docs/'),
        'redoc_url': request.build_absolute_uri('/api/docs/redoc/'),
    }


@api_view(['GET'])
@permission_classes([AllowAny])
def agent_docs_index_view(request: Request) -> Response:
    """Catalog of agent context files and OpenAPI documentation links."""
    documents = [doc.to_index_item(request) for doc in list_documents()]
    return Response({
        'documents': documents,
        'external_references': EXTERNAL_REFERENCES,
        'openapi': _openapi_links(request),
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def agent_docs_detail_view(request: Request, slug: str) -> Response:
    """Return a single agent context document by slug."""
    document = get_document(slug)
    if document is None:
        return Response(
            {'error': {'code': 'not_found', 'message': f'Unknown document slug: {slug}'}},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not document.exists():
        return Response(
            {
                'error': {
                    'code': 'unavailable',
                    'message': f'Document file missing on server: {document.path.name}',
                }
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    content = document.read_text()
    # Use `raw=1` — DRF reserves the `format` query param for content negotiation.
    wants_raw = (
        request.query_params.get('raw') in ('1', 'true', 'yes')
        or 'text/plain' in request.headers.get('Accept', '')
    )

    if wants_raw:
        return Response(content, content_type='text/plain; charset=utf-8')

    payload = {
        'slug': document.slug,
        'title': document.title,
        'description': document.description,
        'format': document.format,
        'category': document.category,
        'content': content,
        **document.stat(),
    }
    return Response(payload)
