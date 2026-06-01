# São Miguel Bus API (revamp)

Django REST API for São Miguel Island bus schedules. The **`revamp`** branch reorganizes this repo: legacy production code lives under [`legacy/`](./legacy/); new Azores Hub backend work will be added at the root.

## Layout

| Path | Purpose |
|------|---------|
| [`legacy/`](./legacy/) | Django 3.0 backend, Docker deploy, scripts, and docs (last shipped version) |
| Root (future) | New `djast`-based modular monolith per [SDD](https://github.com/sousa-dev/SaoMiguelBus/tree/revamp/SDD) |

## Related repos

- **Mobile / planning:** [SaoMiguelBus](https://github.com/sousa-dev/SaoMiguelBus) (`SDD/`, `MIGRATION_PLAN.md`)
- **Web PWA:** [SaoMiguelBus-webapp](https://github.com/sousa-dev/SaoMiguelBus-webapp) (not on `revamp`; deprecated after API revamp)
