# Review captures — do not edit

Copied verbatim from the 2026-08-14 adversarial review of the AzoresBus plan set
(`docs/azoresbus/98-review-findings.md`). The originals lived in `/tmp`, which is
not durable; these are the durable copies.

| File | sha256 | Contents |
|---|---|---|
| `sweep_compact.json` | `242b6c12427f4e93…` | Routes **101, 301, 335** × **51 dates**, each `{date, weekday, n, ids, first}` |
| `findings.json` | `3e7158033212e668…` | Route id↔`nameShort` map, stop-collapse statistics, holiday probes, night-time maxima, tariff headers |

**These are evidence, not test data to be tuned.** If a test disagrees with them,
the test is wrong. Never regenerate them by hitting upstream — 98 already paid the
request cost, and re-probing before we have a proxy path is how we get blocked.

## What `sweep_compact.json` proves, with no further requests

- **Holiday poisoning (98 B6).** 2026-12-01 and 2026-12-08 are Tuesdays that return
  the Sunday set on 101 and 301. A weekday sampler that trusts the calendar records
  Sunday journeys as Tuesday service.
- **Data floor (98 B1).** 2026-04-05 and 2026-06-10…14 return `[]` because the feed
  has no data that far back, not because of holiday semantics. Sampling below the
  floor looks like a network-wide deletion and would trip the prune.
- **Holiday detection.** 2027-06-10 is a Thursday returning the Sunday set — the case
  upstream-derived detection has to catch.
- **2027-04-04 is a plain Sunday.** It returns `n=1, ids=[10]` on 101, identical to
  every ordinary Sunday (e.g. 2026-09-06). 98 claim 10 labels it "(Easter)"; Easter
  2027 is 2027-03-28. It carries no holiday evidence and is not seeded.

## What it does NOT cover

Only 101, 301 and 335 — and 98 §6 is explicit that those three are the lines that
*do* behave as Wed≈weekday/Sat/Sun. **Do not generalise from them.** The
per-weekday and seasonal cases (102, 112, 307, 315, 318, 321, 324, 325) need the
bounded capture in `azoresbus/tests/capture_fixtures.py`, or hand-built fixtures
citing 98's measured tables.
