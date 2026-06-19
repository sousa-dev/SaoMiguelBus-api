"""Mini Bus v3 API — read-only catalog + document streaming."""

from __future__ import annotations

from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from minibus.models import MinibusDocument, MinibusLine, MinibusTariff
from minibus.services import (
    build_meta_payload,
    build_offline_bundle,
    compute_bundle_version,
    document_file_url,
    open_document_file,
    resolve_locale,
    search_minibus_routes,
    serialize_document,
    serialize_line,
    serialize_network_stops,
    serialize_tariff,
)
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
def lines_list_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    locale = resolve_locale(request)
    with for_island(request.island):
        lines = MinibusLine.objects.filter(island=request.island, is_active=True).order_by('sort_order', 'code')
        payload = [serialize_line(line, locale=locale, request=request) for line in lines]

    return Response({'lines': payload, **build_meta_payload(request.island)})


@api_view(['GET'])
@permission_classes([AllowAny])
def line_detail_view(request: Request, slug: str) -> Response:
    err = _require_island(request)
    if err:
        return err

    locale = resolve_locale(request)
    with for_island(request.island):
        line = MinibusLine.objects.filter(island=request.island, slug=slug, is_active=True).first()
        if line is None:
            return Response(
                {'error': {'code': 'not_found', 'message': 'Line not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        payload = serialize_line(line, locale=locale, request=request)

    return Response({**payload, **build_meta_payload(request.island)})


@api_view(['GET'])
@permission_classes([AllowAny])
def tariffs_list_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    locale = resolve_locale(request)
    with for_island(request.island):
        tariffs = MinibusTariff.objects.filter(island=request.island, is_active=True).order_by('sort_order', 'key')
        payload = [serialize_tariff(t, locale=locale) for t in tariffs]

    return Response({'tariffs': payload, **build_meta_payload(request.island)})


@api_view(['GET'])
@permission_classes([AllowAny])
def documents_list_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    locale = resolve_locale(request)
    with for_island(request.island):
        documents = MinibusDocument.objects.filter(island=request.island, is_active=True).order_by('doc_type', 'slug')
        payload = [serialize_document(doc, locale=locale, request=request) for doc in documents]

    return Response({'documents': payload, **build_meta_payload(request.island)})


@api_view(['GET'])
@permission_classes([AllowAny])
def schematic_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    locale = resolve_locale(request)
    with for_island(request.island):
        document = MinibusDocument.objects.filter(
            island=request.island,
            doc_type=MinibusDocument.DOC_SCHEMATIC,
            is_active=True,
        ).first()
        if document is None:
            return Response(
                {'error': {'code': 'not_found', 'message': 'Schematic not found'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        payload = serialize_document(document, locale=locale, request=request)

    return Response({**payload, **build_meta_payload(request.island)})


@api_view(['GET'])
@permission_classes([AllowAny])
def network_stops_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    locale = resolve_locale(request)
    with for_island(request.island):
        payload = serialize_network_stops(island=request.island, locale=locale, request=request)

    return Response({**payload, **build_meta_payload(request.island)})


@api_view(['GET'])
@permission_classes([AllowAny])
def route_search_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    origin = request.GET.get('origin', '').strip()
    destination = request.GET.get('destination', '').strip()
    if not origin or not destination:
        return Response(
            {'error': {'code': 'invalid_request', 'message': 'origin and destination are required'}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    locale = resolve_locale(request)
    with for_island(request.island):
        payload = search_minibus_routes(
            island=request.island,
            origin=origin,
            destination=destination,
            locale=locale,
        )

    return Response({**payload, **build_meta_payload(request.island)})


@api_view(['GET'])
@permission_classes([AllowAny])
def offline_bundle_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    locale = resolve_locale(request)
    with for_island(request.island):
        payload = build_offline_bundle(island=request.island, locale=locale, request=request)

    return Response(payload)


@api_view(['GET'])
@permission_classes([AllowAny])
def offline_bundle_version_view(request: Request) -> Response:
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        version = compute_bundle_version(request.island)

    return Response({'version': version})


@api_view(['GET'])
@permission_classes([AllowAny])
def document_file_view(request: Request, slug: str) -> FileResponse | Response:
    err = _require_island(request)
    if err:
        return err

    with for_island(request.island):
        document = MinibusDocument.objects.filter(island=request.island, slug=slug, is_active=True).first()
        if document is None:
            raise Http404('Document not found')

        try:
            handle, content_type, filename = open_document_file(document)
        except FileNotFoundError:
            raise Http404('Document not found') from None

        return FileResponse(handle, content_type=content_type, filename=filename)
