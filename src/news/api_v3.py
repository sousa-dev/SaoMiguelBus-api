"""News v3 API."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from news.services import get_article, list_articles, list_sources
from tenancy.services import for_island


def _require_island(request: Request) -> Response | None:
    if request.island is None:
        return Response(
            {'error': {'code': 'island_required', 'message': 'Island context required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


@api_view(['GET'])
@permission_classes([AllowAny])
def news_sources_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        sources = list_sources()
    return Response({'sources': sources})


@api_view(['GET'])
@permission_classes([AllowAny])
def news_articles_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    category = request.GET.get('category', '').strip()
    query = request.GET.get('q', '').strip()
    source_raw = request.GET.get('source', '').strip()
    source_id = int(source_raw) if source_raw.isdigit() else None
    limit_raw = request.GET.get('limit', '50').strip()
    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 50

    with for_island(request.island):
        articles = list_articles(
            category=category,
            source_id=source_id,
            query=query,
            limit=limit,
        )
    return Response({'articles': articles})


@api_view(['GET'])
@permission_classes([AllowAny])
def news_article_detail_view(request: Request, article_id: int) -> Response:
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        payload = get_article(article_id)
    if payload is None:
        return Response(
            {'error': {'code': 'not_found', 'message': 'Article not found'}},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(payload)
