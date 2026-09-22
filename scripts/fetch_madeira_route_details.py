"""Scrape the published facts for each official Madeira/Porto Santo route.

Visit Madeira's route pages carry a "Details" block — distance, difficulty, duration and
altitudes. Those are the route's facts; the OSM line we ship is only an approximation of
where it runs, and measuring it would present our approximation as the publisher's figure
(PR1 is published as 6.1 km; its matched relation measures 5.33 km).

Writes the `official` object back into src/trails/data/madeira_official_routes.json. A route
whose page cannot be parsed is left without `official`, and then has no distance at all —
which is the honest outcome, not a reason to fall back to measuring.

    python scripts/fetch_madeira_route_details.py [ref ...]
"""
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
MANIFEST = BASE / 'src/trails/data/madeira_official_routes.json'
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) MadeiraOfflineMap/1.0'


def page_text(url):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=40) as response:
        raw = response.read().decode('utf-8', 'ignore')
    text = re.sub(r'<(script|style).*?</\1>', ' ', raw, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', html.unescape(text))


def parse_duration_minutes(value):
    """'3 hours', '1h30', '2:30' and '45 minutes' all appear on these pages."""
    value = value.lower()
    hours = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:h(?:ours?|oras?)?)\b', value)
    minutes = re.search(r'(\d+)\s*(?:min|minutes?|minutos?)\b', value)
    clock = re.search(r'\b(\d{1,2})[:h](\d{2})\b', value)
    if clock:
        return int(clock.group(1)) * 60 + int(clock.group(2))
    total = 0
    if hours:
        total += round(float(hours.group(1).replace(',', '.')) * 60)
    if minutes:
        total += int(minutes.group(1))
    return total or None


def parse_details(text):
    """Pull the Details block's fields. Every field is optional."""
    details = {}

    distance = re.search(r'Distance:\s*([\d.,]+)\s*km', text, re.I)
    if distance:
        details['distanceKm'] = float(distance.group(1).replace(',', '.'))

    difficulty = re.search(r'Difficulty:\s*([A-Za-z ]+?)\s+(?:Duration|Start|Max|Distance|Recommended)', text, re.I)
    if difficulty:
        details['difficulty'] = difficulty.group(1).strip()

    duration = re.search(r'Duration:\s*(.+?)\s+(?:Start|Max|Difficulty|Distance|Recommended)', text, re.I)
    if duration:
        parsed = parse_duration_minutes(duration.group(1))
        if parsed:
            details['durationMin'] = parsed

    altitudes = re.search(r'Max\.?\s*Altitude\s*/\s*Min\.?\s*Altitude:\s*([\d.,]+)\s*m\s*/\s*([\d.,]+)\s*m', text, re.I)
    if altitudes:
        details['maxAltitudeM'] = int(float(altitudes.group(1).replace(',', '.')))
        details['minAltitudeM'] = int(float(altitudes.group(2).replace(',', '.')))

    start_end = re.search(r'Start/End:\s*(.+?)\s+(?:Max|Difficulty|Duration|Distance|How)', text, re.I)
    if start_end:
        details['startEnd'] = start_end.group(1).strip()[:200]

    return details


def main():
    wanted = set(sys.argv[1:])
    data = json.loads(MANIFEST.read_text())
    scraped = 0
    for route in data['routes']:
        if wanted and route['ref'] not in wanted:
            continue
        try:
            details = parse_details(page_text(route['officialUrl']))
        except Exception as exc:  # network or decoding — leave the route without facts
            print(f'{route["ref"]:8} FAILED {exc}')
            continue
        if not details.get('distanceKm'):
            print(f'{route["ref"]:8} no distance found')
            continue
        route['official'] = details
        scraped += 1
        print(f'{route["ref"]:8} {details.get("distanceKm")} km  {details.get("difficulty", "?")}  '
              f'{details.get("durationMin", "?")} min')
        time.sleep(1.0)

    data['detailsAccessed'] = time.strftime('%Y-%m-%d')
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    missing = [r['ref'] for r in data['routes'] if not r.get('official')]
    print(f'\nScraped {scraped} routes; {len(missing)} without published facts'
          + (f': {", ".join(missing)}' if missing else ''))


if __name__ == '__main__':
    main()
