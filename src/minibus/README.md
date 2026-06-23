# PDL Mini Bus (Ponta Delgada urban network)

Read-only catalog of lines A–D, tariffs, and official PDF/SVG documents sourced from [pdlminibus.pt](https://pdlminibus.pt).

## Setup

```bash
cd src
python manage.py migrate
python manage.py import_minibus
```

Source files live in `minibus/data/source/`. Override with `MINIBUS_SOURCE_DIR` for local dev.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/v3/minibus/lines` | Line list + attribution |
| `GET /api/v3/minibus/lines/{slug}` | Line detail |
| `GET /api/v3/minibus/tariffs` | Fare table |
| `GET /api/v3/minibus/documents` | Document catalog |
| `GET /api/v3/minibus/documents/{slug}/file` | PDF/SVG stream |
| `GET /api/v3/minibus/schematic` | Line schematic metadata |
| `GET /api/v3/minibus/network` | Stop graph with coordinates |
| `GET /api/v3/minibus/route` | Schedule-free journey search |
| `GET /api/v3/minibus/vehicles` | Live fleet snapshot (Eleven Systems AVL proxy) |
| `GET /api/v3/minibus/vehicles/{tracking_id}` | Live vehicle detail (ETAs, route shape, circulations) |

Bootstrap module key: `minibus` (`tenancy` migration `0013_enable_minibus_feature_flag`).

## Live tracking

Proxies [Eleven Systems](https://pdl.elevensystems.pt/publicapi/locations) with Redis caching. Tune freshness via `MINIBUS_TRACKING_CACHE_TTL` (default **10** seconds). See `src/src/.env.example` for all `MINIBUS_TRACKING_*` vars.

## Attribution

Schedules and fares are sourced from pdlminibus.pt. Live vehicle data is attributed to Eleven Systems in API responses (`trackingAttribution`).
