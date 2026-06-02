# Traffic module

Waze-style, community-sourced traffic + hazard alerts, scoped per island
(`TenantScopedModel`). Reports are **public on create** — no moderation queue.
Abuse is mitigated by per-session write throttling, confirm/deny voting,
auto-expiry (category TTL), and admin takedown.

## Models (`models.py`)

- **`TrafficCategory`** — admin-managed pick list. `default_ttl_minutes` drives
  auto-expiry; `is_schedulable` gates the radar scheduling UI. Seeded for
  `sao-miguel` by migration `0002`.
- **`TrafficReport`** — `status ∈ {active, scheduled, expired, removed}`.
  Ownership is pseudonymous via `created_by_session_hash`. Carries
  `latitude/longitude`, optional `description/road`, `active_from/active_until`
  (scheduling), `expires_at`, and `confirm_count/deny_count`.
- **`TrafficConfirmation`** — one `still_there` / `gone` vote per
  report+session (unique). `gone` votes ≥ `DENY_THRESHOLD` (3) expire a report.

## Lifecycle

```
scheduled --(active_from ≤ now)--> active --(expires_at ≤ now | 3× deny)--> expired
                                      └--(owner/admin delete)--> removed
```

Transitions are driven by `services.run_lifecycle()`, invoked every minute by
the Celery beat task `traffic.run_lifecycle` (registered in migration `0003`).
It runs **unscoped** across islands (time-driven transitions are tenant-agnostic).

## API (`/api/v3/traffic/`)

| Method | Path | Notes |
|---|---|---|
| GET | `/categories` | Pick list for the quick-report sheet. |
| GET | `/reports` | Filters: `lat,lng,radius_km` (near-me, Haversine) or `bbox`, `category`, `include_scheduled`, `limit`. |
| POST | `/reports` | Create. Throttled (`traffic_write`, 30/min per session). Location plausibility checked against island radius. |
| GET | `/reports/{id}` | Single report. |
| PATCH/DELETE | `/reports/{id}` | Owner (via `X-Session-Id`) or staff only. DELETE is a soft `removed`. |
| POST | `/reports/{id}/confirm` | Body `{vote: still_there\|gone}`. Upserts the caller's vote. |

Writes identify the caller via the `X-Session-Id` header (hashed server-side).

## Seeding demo data

```bash
cd src
python manage.py seed_traffic_demo            # ~10 active + 2 scheduled radars
python manage.py seed_traffic_demo --clear    # remove seeded rows first
```

## Tests

```bash
cd src && python manage.py test traffic
```
