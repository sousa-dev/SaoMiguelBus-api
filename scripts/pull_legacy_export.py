#!/usr/bin/env python3
"""
Pull a full legacy export via the batched API and write import_legacy-compatible JSON.

Stdlib only — no pip dependencies required.

Example (run until done, largest batches, no per-request timeout):
  python3 scripts/pull_legacy_export.py \\
    --base-url https://api.saomiguelbus.com \\
    --key "$AUTH_KEY" \\
    --output smb_legacy_export.json \\
    --limit 0 \\
    --timeout 0
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

SERVER_MAX_LIMIT = 10000


def fetch_json(url: str, timeout: Optional[int]) -> dict:
    request = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def build_url(base_url: str, path: str, params: dict[str, str]) -> str:
    base = base_url.rstrip('/')
    query = urllib.parse.urlencode(params)
    return f'{base}{path}?{query}'


def pull_export(
    *,
    base_url: str,
    key: str,
    output_path: str,
    limit: int,
    timeout: Optional[int],
    sleep_seconds: float,
) -> dict[str, int]:
    tables: dict[str, list[dict]] = defaultdict(list)
    cursor: str | None = None
    batch_num = 0

    while True:
        params = {'key': key, 'limit': str(limit)}
        if cursor:
            params['next'] = cursor

        url = build_url(base_url, '/api/v1/export/legacy/batch', params)
        batch_num += 1

        try:
            payload = fetch_json(url, timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'HTTP {exc.code} on batch {batch_num}: {body}') from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f'Network error on batch {batch_num}: {exc}') from exc

        if 'error' in payload:
            raise RuntimeError(f'API error on batch {batch_num}: {payload["error"]}')

        table = payload['table']
        rows = payload.get('rows') or []
        tables[table].extend(rows)

        total_rows = sum(len(rows_for_table) for rows_for_table in tables.values())
        print(
            f'batch {batch_num}: {table} +{len(rows)} rows '
            f'(table total {len(tables[table])}, export total {total_rows})',
            flush=True,
        )

        if payload.get('export_complete'):
            break

        cursor = payload.get('next')
        if not cursor:
            raise RuntimeError(f'batch {batch_num}: missing next cursor before export_complete')

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    counts = {name: len(rows) for name, rows in sorted(tables.items())}
    export_doc = {
        'format_version': payload.get('format_version', 2),
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'source': 'pull_legacy_export.py',
        'tables': dict(tables),
    }

    with open(output_path, 'w', encoding='utf-8') as handle:
        json.dump(export_doc, handle, indent=2, ensure_ascii=False)

    print(f'Wrote {output_path} ({sum(counts.values())} rows across {len(counts)} tables)', flush=True)
    for name, count in counts.items():
        print(f'  {name}: {count}', flush=True)

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description='Pull full legacy export in batches')
    parser.add_argument(
        '--base-url',
        default='https://api.saomiguelbus.com',
        help='API base URL (default: https://api.saomiguelbus.com)',
    )
    parser.add_argument('--key', required=True, help='AUTH_KEY query parameter')
    parser.add_argument(
        '--output',
        default='smb_legacy_export.json',
        help='Output JSON file path (default: smb_legacy_export.json)',
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=5000,
        help='Rows per batch (0 = server max %d, default: 5000)' % SERVER_MAX_LIMIT,
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=120,
        help='HTTP timeout per batch in seconds (0 = no timeout, default: 120)',
    )
    parser.add_argument(
        '--sleep',
        type=float,
        default=0.0,
        help='Optional sleep between batch requests in seconds',
    )
    args = parser.parse_args()

    limit = SERVER_MAX_LIMIT if args.limit == 0 else args.limit
    if limit < 1:
        print('limit must be >= 1 or 0 for server max', file=sys.stderr)
        return 2

    timeout: Optional[int] = None if args.timeout == 0 else args.timeout
    if timeout is not None and timeout < 1:
        print('timeout must be >= 1 or 0 for no timeout', file=sys.stderr)
        return 2

    try:
        pull_export(
            base_url=args.base_url,
            key=args.key,
            output_path=args.output,
            limit=limit,
            timeout=timeout,
            sleep_seconds=args.sleep,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
