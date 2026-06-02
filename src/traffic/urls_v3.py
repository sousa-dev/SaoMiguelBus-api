"""Traffic v3 URL routes."""

from __future__ import annotations

from django.urls import path

from traffic.api_v3 import (
    categories_view,
    report_confirm_view,
    report_detail_view,
    reports_view,
)

urlpatterns = [
    path('categories', categories_view, name='v3-traffic-categories'),
    path('reports', reports_view, name='v3-traffic-reports'),
    path('reports/<int:report_id>', report_detail_view, name='v3-traffic-report-detail'),
    path('reports/<int:report_id>/confirm', report_confirm_view, name='v3-traffic-report-confirm'),
]
