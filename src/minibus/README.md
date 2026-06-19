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

Bootstrap module key: `minibus` (`tenancy` migration `0013_enable_minibus_feature_flag`).

## Attribution

Schedules and fares are sourced from pdlminibus.pt. API responses include `attribution` and `source_url`.
