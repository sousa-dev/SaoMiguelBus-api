"""Legacy ad serving logic."""

from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher

from django.db.models import Q
from django.utils import timezone

from transit.models import Ad, Stop, StopGroup


def _serialize_ad(ad: Ad) -> dict:
    return {
        'id': ad.id,
        'entity': ad.entity,
        'description': ad.description,
        'media': ad.media,
        'start': ad.start.isoformat() if ad.start else None,
        'end': ad.end.isoformat() if ad.end else None,
        'action': ad.action or None,
        'target': ad.target or None,
        'advertise_on': ad.advertise_on,
        'platform': ad.platform,
        'status': ad.status,
        'seen': ad.seen,
        'clicked': ad.clicked,
    }


def get_most_similar_stop(stop: str) -> str:
    best_name = stop
    best_score = 0.0
    for entity in Stop.objects.all():
        score = SequenceMatcher(
            lambda x: x in ['do', 'da', 'das', 'dos', 'de', ' '],
            entity.name.lower(),
            stop.lower(),
        ).ratio()
        if score > best_score:
            best_name = entity.name
            best_score = score
    return best_name


def get_advertise_on_value(stop: str) -> str:
    for grp in StopGroup.objects.all():
        for name in grp.stop_names:
            if stop.lower() in name.lower() or name.lower() in stop.lower():
                return grp.name
    similar = get_most_similar_stop(stop)
    for grp in StopGroup.objects.all():
        for name in grp.stop_names:
            if similar.lower() in name.lower() or name.lower() in similar.lower():
                return grp.name
    return 'not found'


def select_ad(*, advertise_on: str, platform: str, now_ts: float | None = None) -> Ad | None:
    ad_time = now_ts if now_ts is not None else timezone.now().timestamp()
    ad_dt = timezone.make_aware(datetime.fromtimestamp(float(ad_time)))

    ads = Ad.objects.filter(status='active', start__lte=ad_dt, end__gte=ad_dt)
    if platform != 'all':
        # A specific client platform (e.g. ios/android) is eligible for both its
        # own targeted campaigns and any cross-platform `platform='all'` campaign.
        ads = ads.filter(Q(platform=platform) | Q(platform='all'))

    if advertise_on in ('home', 'interstitial', 'all'):
        if advertise_on != 'all':
            ads = ads.filter(advertise_on__icontains=advertise_on)
    else:
        parts = advertise_on.split('->')
        origin = parts[0].strip()
        destination = parts[-1].strip()
        dest_key = get_advertise_on_value(destination)
        dest_ads = ads.filter(advertise_on__icontains=dest_key)
        ads = dest_ads if dest_ads.exists() else ads.filter(advertise_on__icontains=get_advertise_on_value(origin))

    ad = ads.order_by('?').first()
    if ad is None:
        default_qs = Ad.objects.filter(status='default')
        if platform != 'all':
            default_qs = default_qs.filter(Q(platform=platform) | Q(platform='all'))
        ad = default_qs.order_by('?').first()
    if ad is None and platform not in ('all', ''):
        # Dev sqlite often has android-only defaults; serve any default rather than 404
        ad = Ad.objects.filter(status='default').order_by('?').first()
    return ad


def get_ad_payload(*, advertise_on: str, platform: str, now_ts: float | None = None) -> dict | None:
    ad = select_ad(advertise_on=advertise_on, platform=platform, now_ts=now_ts)
    if ad is None:
        return None
    ad.seen += 1
    ad.save(update_fields=['seen'])
    return _serialize_ad(ad)


def record_ad_click(ad_id: int) -> bool:
    try:
        ad = Ad.objects.get(id=ad_id)
    except Ad.DoesNotExist:
        return False
    ad.clicked += 1
    ad.save(update_fields=['clicked'])
    return True
