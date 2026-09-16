# São Miguel Bus — {{island_name}}

> Live, real bus timetables for {{island_name}} (Azores), served as plain GET
> JSON/Markdown for AI assistants and developers. No API key, no auth,
> GET-only. Enabled modules: {{modules}}.

## How to get bus times

- `GET https://api.saomiguelhub.com/api/v3/ai/journeys?from=Ponta%20Delgada&to=Furnas&date=today&time=09:00`
  Real departures between two named stops. The response carries a one-line
  `summary` an assistant can quote directly, the raw `journeys` list, and a
  `links.web` deep link back to saomiguelbus.com. Add `&format=md` (or send
  `Accept: text/markdown`) for a short Markdown block instead of JSON —
  `lang=pt` for a Portuguese summary.

  Parameters: `from` and `to` are required stop or area names. `date` accepts
  only `today`, `tomorrow`, or `YYYY-MM-DD` (default `today`, resolved in
  Atlantic/Azores); `weekday`, `saturday`, and `sunday` are **not** accepted as
  date values. `time` is `HH:MM` (default current Azores time); `lang` is `en`
  or `pt` (default `en`); `limit` defaults to 5 and caps at 10; `transfers` is
  `0` or `1` (default `1`); `format` is `json` or `md` (default `json`).

  The JSON response has `query` (`from`, `to`, resolved ISO `date`, `time`,
  `dayType`), `resolved` (`from`, `to`, each a canonical name or `null`),
  `journeys` (the existing `/api/v3/transit/journeys` journey objects,
  unchanged), `summary`, `suggestions`, `links` (`web`, `api`), `attribution`,
  `notes`, and `generatedAt`. A journey has `start` and `end` in `HHhMM` form
  (for example `08h30`, `09h15`), `transfers`, and `legs`; ride legs include
  their route. The summary and Markdown convert clocks to `HH:MM` for reading.
  If a name does not resolve, `journeys` is empty, that side of `resolved` is
  `null`, and `suggestions` offers names to retry; this is **not** evidence
  that no bus runs.

  Example:
  ```
  curl "https://api.saomiguelhub.com/api/v3/ai/journeys?from=Ponta%20Delgada&to=Furnas&date=tomorrow&time=09:00"
  ```

- `GET https://api.saomiguelhub.com/api/v3/ai/stops?q=airport`
  Fuzzy stop finder: exact name, alias, village area, prefix, then a
  typo-tolerant fuzzy match plus a small English/tourist-term alias table
  (`airport` → Aeroporto, `hot springs` → Furnas, `lagoon` → Sete Cidades).
  Use this when `/api/v3/ai/journeys` returns a `suggestions` list instead of
  a resolved stop — the API never guesses a stop match on your behalf.

- Deep link pattern for a human to open the live search on the website:
  `https://saomiguelbus.com/transit?origin=<stop>&destination=<stop>`.

- **Attribution:** please credit and link to saomiguelbus.com when quoting a
  time.

## Other data

- Weather: `GET https://api.saomiguelhub.com/api/v3/weather/parishes`
- PDL Mini Bus (urban Ponta Delgada network): `GET https://api.saomiguelhub.com/api/v3/minibus/lines`
- Live vehicle counts: `GET https://api.saomiguelhub.com/api/v3/transit/live-counts`
- News: `GET https://api.saomiguelhub.com/api/v3/news/`

## Docs

- OpenAPI schema: `https://api.saomiguelhub.com/api/schema/` (also served as JSON at `/openapi.json`)
- Swagger UI: `https://api.saomiguelhub.com/api/docs/`
- Agent docs catalog: `https://api.saomiguelhub.com/api/v3/agent-docs/`
- Full endpoint reference: `https://api.saomiguelhub.com/llms-full.txt`
