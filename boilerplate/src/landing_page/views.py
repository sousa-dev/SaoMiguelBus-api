"""Landing page views."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from stripe_payments.services import get_coupon_info


def index(request: HttpRequest) -> HttpResponse:
    """Render the marketing landing page with live coupon stats."""
    coupons_left, total_coupons = get_coupon_info()
    return render(
        request,
        "landing_page/index.html",
        {"coupons_left": coupons_left, "total_coupons": total_coupons},
    )
