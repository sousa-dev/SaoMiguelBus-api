# São Miguel Hub — Analytics Dashboard

A zero-build, static (HTML/CSS/JS) analytics dashboard — umami-style — for the
São Miguel Hub backend. It reads aggregated stats from the AUTH_KEY-protected
reporting API and renders them entirely in the browser. No data is stored
server-side by the dashboard; the AUTH key lives only in the visitor's
`localStorage`.

## What it shows

Two data sources, switchable from the top tabs:

- **Hub (v3)** — the first-party `AnalyticsEvent` stream (`/api/v3/analytics/reports/*`).
  Metrics: events, sessions. Breakdowns: modules, event types, platforms, locales.
- **Legacy** — the legacy `Stat` table (`/api/v3/analytics/reports/legacy/*`).
  Metrics: requests, route searches. Breakdowns: request types, top routes /
  origins / destinations, platforms, languages, day type.

Each source has date-range presets (24h → 1y) + custom range, a time-series
chart, breakdown panels, and a paginated raw-events table with filters.

## Backing API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v3/analytics/reports/overview` | v3 totals, time series, breakdowns |
| `GET /api/v3/analytics/reports/events` | v3 raw events (paginated, filterable) |
| `GET /api/v3/analytics/reports/meta` | v3 distinct filter values + bounds |
| `GET /api/v3/analytics/reports/legacy/overview` | legacy totals, series, breakdowns |
| `GET /api/v3/analytics/reports/legacy/events` | legacy raw stats (paginated) |
| `GET /api/v3/analytics/reports/legacy/meta` | legacy distinct filter values |

All require the `AUTH_KEY` via the `X-Auth-Key` header (or `?key=`). The v3
endpoints are tenant-scoped via the `X-Island` header.

Common query params: `start`, `end` (`YYYY-MM-DD`), `interval`
(`hour|day|month`), `page`, `page_size`, plus the per-source filters
(`module`, `event_type`, `platform`, `locale` / `request`, `language`).

## Configuration

Open **⚙ Settings** in the dashboard and set:

- **API base URL** — e.g. `https://api.saomiguelhub.com` (default).
- **AUTH key** — the backend `AUTH_KEY`.
- **Island key** — tenant slug, default `sao-miguel`.

## Local preview

```bash
cd docs
python3 -m http.server 4000
# open http://localhost:4000
```

## Deploy to GitHub Pages

GitHub repo → **Settings → Pages** → *Deploy from a branch* → select the branch
and the `/docs` folder. The `.nojekyll` file disables Jekyll processing. The
dashboard is fully client-side, so no build pipeline is required.

> Cross-origin requests work because the API sets `CORS_ALLOW_ALL_ORIGINS` and
> allows the `X-Auth-Key` / `X-Island` headers.
