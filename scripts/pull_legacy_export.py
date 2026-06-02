#!/usr/bin/env python3
"""
Pull a full legacy export via the batched API and write import_legacy-compatible JSON.

Checkpoints after EVERY batch (JSONL on disk + state.json cursor) so a 504 mid-run
does not lose progress. Re-run the same command to resume automatically.

Stdlib only — no pip dependencies required.

Example:
  python3 scripts/pull_legacy_export.py \\
    --base-url https://api.saomiguelbus.com \\
    --key "$AUTH_KEY" \\
    --output smb_legacy_export.json \\
    --limit 0 \\
    --timeout 0

Resume after failure (same command — detects checkpoint):
  python3 scripts/pull_legacy_export.py --key "$AUTH_KEY" --output smb_legacy_export.json --essential-only

If app_stat is done and you're stuck on app_data, finalize immediately:
  python3 scripts/pull_legacy_export.py --output smb_legacy_export.json --finalize-only

Start over:
  python3 scripts/pull_legacy_export.py ... --fresh
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SERVER_MAX_LIMIT = 10000
RETRYABLE_HTTP_CODES = {502, 503, 504}

EXPORT_TABLE_ORDER = [
    'app_variables',
    'app_stop',
    'app_holiday',
    'app_group',
    'app_route',
    'app_ad',
    'app_info',
    'subscriptions',
    'app_stat',
    'app_data',
    'app_trip',
    'app_tripstop',
    'app_aifeedback',
    'app_emailopen',
]

# Not needed for webapp / schedule search — safe to skip (app_data is huge JSON blobs).
OPTIONAL_TABLES = frozenset({
    'app_data',       # cached Google Directions responses from /api/v1/gmaps
    'app_trip',       # legacy side-table (NOT app_route schedules)
    'app_tripstop',   # legacy side-table (NOT app_stop)
    'app_aifeedback', # AI survey responses
    'app_emailopen',  # email open tracking
})


def parse_cursor(cursor: str) -> tuple[str, int]:
    table, raw_id = cursor.split(':', 1)
    return table, int(raw_id)


def advance_past_skipped(cursor: Optional[str], skip_tables: frozenset[str]) -> Optional[str]:
    """Return the next cursor, jumping over skipped tables without API calls."""
    if not skip_tables or not cursor:
        return cursor
    table, _last_id = parse_cursor(cursor)
    if table not in skip_tables:
        return cursor
    try:
        index = EXPORT_TABLE_ORDER.index(table)
    except ValueError:
        return cursor
    for next_table in EXPORT_TABLE_ORDER[index + 1:]:
        if next_table not in skip_tables:
            return f'{next_table}:0'
    return None


def fetch_json(url: str, timeout: Optional[int]) -> dict:
    request = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def fetch_json_with_retries(
    url: str,
    timeout: Optional[int],
    *,
    max_retries: int,
    retry_base_seconds: float,
) -> dict:
    attempt = 0
    while True:
        attempt += 1
        try:
            return fetch_json(url, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_CODES or attempt > max_retries:
                body = exc.read().decode('utf-8', errors='replace')
                raise RuntimeError(f'HTTP {exc.code}: {body}') from exc
            wait = retry_base_seconds * (2 ** (attempt - 1))
            print(
                f'  retry {attempt}/{max_retries} after HTTP {exc.code}, sleeping {wait:.0f}s...',
                flush=True,
            )
            time.sleep(wait)
        except urllib.error.URLError as exc:
            if attempt > max_retries:
                raise RuntimeError(f'Network error: {exc}') from exc
            wait = retry_base_seconds * (2 ** (attempt - 1))
            print(
                f'  retry {attempt}/{max_retries} after network error, sleeping {wait:.0f}s...',
                flush=True,
            )
            time.sleep(wait)


def build_url(base_url: str, path: str, params: dict[str, str]) -> str:
    base = base_url.rstrip('/')
    query = urllib.parse.urlencode(params)
    return f'{base}{path}?{query}'


def checkpoint_dir_for(output_path: str, override: Optional[str]) -> Path:
    if override:
        return Path(override)
    return Path(output_path).with_suffix(Path(output_path).suffix + '.checkpoint')


def tables_dir(checkpoint: Path) -> Path:
    path = checkpoint / 'tables'
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_state(checkpoint: Path) -> Optional[dict[str, Any]]:
    state_path = checkpoint / 'state.json'
    if not state_path.is_file():
        return None
    return json.loads(state_path.read_text(encoding='utf-8'))


def save_state(checkpoint: Path, state: dict[str, Any]) -> None:
    checkpoint.mkdir(parents=True, exist_ok=True)
    state_path = checkpoint / 'state.json'
    tmp_path = checkpoint / 'state.json.tmp'
    tmp_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
    tmp_path.replace(state_path)


def append_rows(checkpoint: Path, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    jsonl_path = tables_dir(checkpoint) / f'{table}.jsonl'
    with jsonl_path.open('a', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write('\n')


def count_table_rows(checkpoint: Path, table: str) -> int:
    jsonl_path = tables_dir(checkpoint) / f'{table}.jsonl'
    if not jsonl_path.is_file():
        return 0
    count = 0
    with jsonl_path.open('r', encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def total_checkpoint_rows(checkpoint: Path, table_counts: dict[str, int]) -> int:
    return sum(table_counts.values())


def finalize_output(
    checkpoint: Path,
    output_path: str,
    *,
    format_version: int,
) -> dict[str, int]:
    """Stream JSONL checkpoint files into one import_legacy-compatible JSON file."""
    tables_path = tables_dir(checkpoint)
    present_tables = [name for name in EXPORT_TABLE_ORDER if (tables_path / f'{name}.jsonl').is_file()]

    counts: dict[str, int] = {}
    with open(output_path, 'w', encoding='utf-8') as out:
        out.write('{\n')
        out.write(f'  "format_version": {format_version},\n')
        out.write(f'  "exported_at": "{datetime.now(timezone.utc).isoformat()}",\n')
        out.write('  "source": "pull_legacy_export.py",\n')
        out.write('  "tables": {\n')

        for index, table in enumerate(present_tables):
            jsonl_path = tables_path / f'{table}.jsonl'
            out.write(f'    "{table}": [\n')
            first = True
            row_count = 0
            with jsonl_path.open('r', encoding='utf-8') as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    if not first:
                        out.write(',\n')
                    out.write('      ')
                    out.write(line)
                    first = False
                    row_count += 1
            counts[table] = row_count
            out.write('\n    ]')
            if index + 1 < len(present_tables):
                out.write(',')
            out.write('\n')

        out.write('  }\n}\n')

    return counts


def pull_export(
    *,
    base_url: str,
    key: str,
    output_path: str,
    checkpoint: Path,
    limit: int,
    timeout: Optional[int],
    sleep_seconds: float,
    max_retries: int,
    retry_base_seconds: float,
    fresh: bool,
    finalize_only: bool,
    skip_tables: frozenset[str],
) -> dict[str, int]:
    if fresh and checkpoint.exists():
        print(f'Removing checkpoint dir {checkpoint}', flush=True)
        for path in sorted(checkpoint.rglob('*'), reverse=True):
            if path.is_file():
                path.unlink()
        for path in sorted(checkpoint.rglob('*'), reverse=True):
            if path.is_dir():
                path.rmdir()
        if checkpoint.is_dir():
            checkpoint.rmdir()

    state = load_state(checkpoint)

    if finalize_only:
        if state is None:
            raise RuntimeError(f'No checkpoint found at {checkpoint}')
        counts = finalize_output(
            checkpoint,
            output_path,
            format_version=int(state.get('format_version', 2)),
        )
        print(f'Finalized {output_path} from checkpoint ({sum(counts.values())} rows)', flush=True)
        return counts

    if state and state.get('export_complete'):
        print('Checkpoint already complete — finalizing output file...', flush=True)
        counts = finalize_output(
            checkpoint,
            output_path,
            format_version=int(state.get('format_version', 2)),
        )
        print(f'Wrote {output_path} ({sum(counts.values())} rows)', flush=True)
        return counts

    if state:
        cursor = state.get('cursor')
        batch_num = int(state.get('batch_num', 0))
        table_counts = dict(state.get('table_counts') or {})
        format_version = int(state.get('format_version', 2))
        print(
            f'Resuming from checkpoint: cursor={cursor!r}, '
            f'batch={batch_num}, rows saved={total_checkpoint_rows(checkpoint, table_counts)}',
            flush=True,
        )
    else:
        cursor = None
        batch_num = 0
        table_counts = {}
        format_version = 2
        checkpoint.mkdir(parents=True, exist_ok=True)
        save_state(
            checkpoint,
            {
                'cursor': None,
                'batch_num': 0,
                'table_counts': {},
                'format_version': format_version,
                'export_complete': False,
                'started_at': datetime.now(timezone.utc).isoformat(),
            },
        )
        print(f'Checkpoint dir: {checkpoint}', flush=True)

    if skip_tables:
        skipped = ', '.join(sorted(skip_tables))
        print(f'Skipping tables: {skipped}', flush=True)

    cursor = advance_past_skipped(cursor, skip_tables)
    if cursor is None and batch_num > 0:
        print('All remaining tables skipped — finalizing from checkpoint...', flush=True)
        save_state(
            checkpoint,
            {
                'cursor': None,
                'batch_num': batch_num,
                'table_counts': table_counts,
                'format_version': format_version,
                'export_complete': True,
                'updated_at': datetime.now(timezone.utc).isoformat(),
            },
        )
        counts = finalize_output(checkpoint, output_path, format_version=format_version)
        print(f'Wrote {output_path} ({sum(counts.values())} rows)', flush=True)
        return counts

    while True:
        cursor = advance_past_skipped(cursor, skip_tables)
        if cursor is None and batch_num > 0:
            save_state(
                checkpoint,
                {
                    'cursor': None,
                    'batch_num': batch_num,
                    'table_counts': table_counts,
                    'format_version': format_version,
                    'export_complete': True,
                    'updated_at': datetime.now(timezone.utc).isoformat(),
                },
            )
            break

        params = {'key': key, 'limit': str(limit)}
        if cursor:
            params['next'] = cursor

        url = build_url(base_url, '/api/v1/export/legacy/batch', params)
        batch_num += 1
        print(f'batch {batch_num}: fetching cursor={cursor or "START"}...', flush=True)

        payload = fetch_json_with_retries(
            url,
            timeout,
            max_retries=max_retries,
            retry_base_seconds=retry_base_seconds,
        )

        if 'error' in payload:
            save_state(
                checkpoint,
                {
                    'cursor': cursor,
                    'batch_num': batch_num - 1,
                    'table_counts': table_counts,
                    'format_version': format_version,
                    'export_complete': False,
                    'last_error': payload['error'],
                },
            )
            raise RuntimeError(f'API error on batch {batch_num}: {payload["error"]}')

        format_version = int(payload.get('format_version', format_version))
        table = payload['table']
        rows = payload.get('rows') or []

        append_rows(checkpoint, table, rows)
        table_counts[table] = count_table_rows(checkpoint, table)
        total_rows = total_checkpoint_rows(checkpoint, table_counts)

        print(
            f'batch {batch_num}: {table} +{len(rows)} rows '
            f'(table total {table_counts[table]}, export total {total_rows}) — checkpoint saved',
            flush=True,
        )

        export_complete = bool(payload.get('export_complete'))
        cursor = payload.get('next')
        if export_complete:
            cursor = None
        cursor = advance_past_skipped(cursor, skip_tables)
        if cursor is None:
            export_complete = True

        save_state(
            checkpoint,
            {
                'cursor': cursor,
                'batch_num': batch_num,
                'table_counts': table_counts,
                'format_version': format_version,
                'export_complete': export_complete,
                'last_table': table,
                'updated_at': datetime.now(timezone.utc).isoformat(),
            },
        )

        if export_complete:
            break

        if not cursor:
            raise RuntimeError(f'batch {batch_num}: missing next cursor before export_complete')

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    counts = finalize_output(checkpoint, output_path, format_version=format_version)
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
    parser.add_argument('--key', help='AUTH_KEY query parameter (not required for --finalize-only)')
    parser.add_argument(
        '--output',
        default='smb_legacy_export.json',
        help='Output JSON file path (default: smb_legacy_export.json)',
    )
    parser.add_argument(
        '--checkpoint-dir',
        help='Checkpoint directory (default: <output>.json.checkpoint)',
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
    parser.add_argument(
        '--retries',
        type=int,
        default=12,
        help='Retries per batch on 502/503/504 or network errors (default: 12)',
    )
    parser.add_argument(
        '--retry-base-seconds',
        type=float,
        default=5.0,
        help='Base backoff seconds for retries (default: 5)',
    )
    parser.add_argument(
        '--fresh',
        action='store_true',
        help='Delete checkpoint and start from scratch',
    )
    parser.add_argument(
        '--finalize-only',
        action='store_true',
        help='Build output JSON from existing checkpoint without fetching',
    )
    parser.add_argument(
        '--essential-only',
        action='store_true',
        help='Skip optional tables (app_data, app_trip, app_tripstop, aifeedback, emailopen)',
    )
    parser.add_argument(
        '--skip-tables',
        help='Comma-separated table names to skip (e.g. app_data,app_trip)',
    )
    args = parser.parse_args()

    skip_tables: frozenset[str] = frozenset()
    if args.essential_only:
        skip_tables = OPTIONAL_TABLES
    if args.skip_tables:
        skip_tables = skip_tables | frozenset(
            part.strip() for part in args.skip_tables.split(',') if part.strip()
        )

    if not args.finalize_only and not args.key:
        print('--key is required unless using --finalize-only', file=sys.stderr)
        return 2

    limit = SERVER_MAX_LIMIT if args.limit == 0 else args.limit
    if limit < 1:
        print('limit must be >= 1 or 0 for server max', file=sys.stderr)
        return 2

    timeout: Optional[int] = None if args.timeout == 0 else args.timeout
    if timeout is not None and timeout < 1:
        print('timeout must be >= 1 or 0 for no timeout', file=sys.stderr)
        return 2

    checkpoint = checkpoint_dir_for(args.output, args.checkpoint_dir)

    try:
        pull_export(
            base_url=args.base_url,
            key=args.key or '',
            output_path=args.output,
            checkpoint=checkpoint,
            limit=limit,
            timeout=timeout,
            sleep_seconds=args.sleep,
            max_retries=args.retries,
            retry_base_seconds=args.retry_base_seconds,
            fresh=args.fresh,
            finalize_only=args.finalize_only,
            skip_tables=skip_tables,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        print(
            f'\nProgress is saved under {checkpoint}. '
            f'Re-run the same command to resume, or --finalize-only if export_complete.',
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
