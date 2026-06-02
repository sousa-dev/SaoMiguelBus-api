#!/usr/bin/env python3
"""
Split a monolithic legacy export JSON into a batched directory for low-memory import.

Output layout (import with: import_legacy --export-dir DIR --async):

  DIR/
    manifest.json
    batches/
      0001_app_variables.jsonl
      0002_app_stop.jsonl
      ...
      0042_app_stat_0001.jsonl
      0043_app_stat_0002.jsonl

Each JSONL line is one row dict (format v2). The Celery importer streams one batch
file at a time — no 400MB json.loads in the worker.

Stdlib only.

Examples:
  # From finalized monolithic JSON (needs RAM ~2x file size during split):
  python3 scripts/split_legacy_export.py \\
    --input final_smb_legacy_export.json \\
    --output-dir smb_export_batches \\
    --batch-size 5000

  # From pull_legacy_export checkpoint (memory-safe — streams JSONL):
  python3 scripts/split_legacy_export.py \\
    --checkpoint-dir final_smb_legacy_export.json.checkpoint \\
    --output-dir smb_export_batches \\
    --batch-size 5000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

LEGACY_EXPORT_FORMAT_VERSION = 2
BATCHED_EXPORT_LAYOUT = 'batched_jsonl'

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


def normalize_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    raise TypeError(f'Expected dict row in export v2, got {type(row).__name__}')


def write_jsonl_rows(path: Path, rows: Iterator[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write('\n')
            count += 1
    return count


def batch_filename(seq: int, table: str, part: int) -> str:
    if part <= 1:
        return f'{seq:04d}_{table}.jsonl'
    return f'{seq:04d}_{table}_{part:04d}.jsonl'


def split_rows_into_batches(
    *,
    table: str,
    rows: Iterator[dict[str, Any]],
    output_dir: Path,
    batch_size: int,
    seq_start: int,
) -> tuple[list[dict[str, Any]], int]:
    """Write one or more JSONL batch files for a table. Returns (batch entries, next seq)."""
    batches: list[dict[str, Any]] = []
    seq = seq_start
    part = 0
    chunk: list[dict[str, Any]] = []

    def flush_chunk() -> None:
        nonlocal seq, part, chunk
        if not chunk:
            return
        part += 1
        relative = f'batches/{batch_filename(seq, table, part)}'
        row_count = write_jsonl_rows(output_dir / relative, iter(chunk))
        batches.append(
            {
                'seq': seq,
                'table': table,
                'file': relative,
                'rows': row_count,
            }
        )
        seq += 1
        chunk = []

    for row in rows:
        chunk.append(row)
        if len(chunk) >= batch_size:
            flush_chunk()

    flush_chunk()
    return batches, seq


def iter_checkpoint_table_rows(checkpoint_dir: Path, table: str) -> Iterator[dict[str, Any]]:
    jsonl_path = checkpoint_dir / 'tables' / f'{table}.jsonl'
    if not jsonl_path.is_file():
        return
    with jsonl_path.open('r', encoding='utf-8') as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                yield normalize_row(json.loads(stripped))


def split_from_checkpoint(
    *,
    checkpoint_dir: Path,
    output_dir: Path,
    batch_size: int,
    metadata: dict[str, Any],
) -> dict[str, int]:
    table_counts: dict[str, int] = {}
    all_batches: list[dict[str, Any]] = []
    seq = 1

    for table in EXPORT_TABLE_ORDER:
        jsonl_path = checkpoint_dir / 'tables' / f'{table}.jsonl'
        if not jsonl_path.is_file():
            continue

        def row_iter() -> Iterator[dict[str, Any]]:
            yield from iter_checkpoint_table_rows(checkpoint_dir, table)

        batches, seq = split_rows_into_batches(
            table=table,
            rows=row_iter(),
            output_dir=output_dir,
            batch_size=batch_size,
            seq_start=seq,
        )
        if batches:
            all_batches.extend(batches)
            table_counts[table] = sum(item['rows'] for item in batches)
            print(
                f'{table}: {table_counts[table]} rows -> {len(batches)} batch file(s)',
                flush=True,
            )

    write_manifest(output_dir, metadata, all_batches, table_counts, batch_size)
    return table_counts


def split_from_monolithic_json(
    *,
    input_path: Path,
    output_dir: Path,
    batch_size: int,
) -> dict[str, int]:
    print(f'Loading {input_path} (needs free RAM ~2x file size)...', flush=True)
    payload = json.loads(input_path.read_text(encoding='utf-8'))
    version = payload.get('format_version')
    if version != LEGACY_EXPORT_FORMAT_VERSION:
        raise ValueError(f'Unsupported format_version={version!r} (expected 2)')

    metadata = {
        'format_version': version,
        'exported_at': payload.get('exported_at'),
        'source': payload.get('source'),
    }
    tables: dict[str, Any] = payload.get('tables') or {}

    table_counts: dict[str, int] = {}
    all_batches: list[dict[str, Any]] = []
    seq = 1

    for table in EXPORT_TABLE_ORDER:
        raw_rows = tables.get(table) or []
        if not raw_rows:
            continue

        def row_iter(rows=raw_rows) -> Iterator[dict[str, Any]]:
            for row in rows:
                yield normalize_row(row)

        batches, seq = split_rows_into_batches(
            table=table,
            rows=row_iter(),
            output_dir=output_dir,
            batch_size=batch_size,
            seq_start=seq,
        )
        all_batches.extend(batches)
        table_counts[table] = sum(item['rows'] for item in batches)
        print(
            f'{table}: {table_counts[table]} rows -> {len(batches)} batch file(s)',
            flush=True,
        )
        tables.pop(table, None)

    write_manifest(output_dir, metadata, all_batches, table_counts, batch_size)
    return table_counts


def write_manifest(
    output_dir: Path,
    metadata: dict[str, Any],
    batches: list[dict[str, Any]],
    table_counts: dict[str, int],
    batch_size: int,
) -> None:
    manifest = {
        'format_version': metadata.get('format_version', LEGACY_EXPORT_FORMAT_VERSION),
        'layout': BATCHED_EXPORT_LAYOUT,
        'batch_size': batch_size,
        'exported_at': metadata.get('exported_at'),
        'source': metadata.get('source'),
        'split_at': datetime.now(timezone.utc).isoformat(),
        'table_counts': table_counts,
        'batches': batches,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Wrote {manifest_path} ({len(batches)} batch files)', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='Split legacy export JSON into batched JSONL directory')
    parser.add_argument('--input', help='Monolithic export JSON file (format v2)')
    parser.add_argument(
        '--checkpoint-dir',
        help='Checkpoint dir from pull_legacy_export.py (memory-safe streaming source)',
    )
    parser.add_argument('--output-dir', required=True, help='Output directory for batched export')
    parser.add_argument(
        '--batch-size',
        type=int,
        default=5000,
        help='Max rows per batch file (default: 5000)',
    )
    parser.add_argument(
        '--fresh',
        action='store_true',
        help='Delete output directory before writing',
    )
    args = parser.parse_args()

    if not args.input and not args.checkpoint_dir:
        print('Provide --input or --checkpoint-dir', file=sys.stderr)
        return 2
    if args.input and args.checkpoint_dir:
        print('Use only one of --input or --checkpoint-dir', file=sys.stderr)
        return 2
    if args.batch_size < 1:
        print('--batch-size must be >= 1', file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    if args.fresh and output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)

    if args.checkpoint_dir:
        checkpoint_dir = Path(args.checkpoint_dir)
        if not checkpoint_dir.is_dir():
            print(f'Checkpoint dir not found: {checkpoint_dir}', file=sys.stderr)
            return 2
        state_path = checkpoint_dir / 'state.json'
        metadata: dict[str, Any] = {'format_version': LEGACY_EXPORT_FORMAT_VERSION}
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding='utf-8'))
            metadata['exported_at'] = state.get('updated_at')
            metadata['source'] = 'pull_legacy_export-checkpoint'
        split_from_checkpoint(
            checkpoint_dir=checkpoint_dir,
            output_dir=output_dir,
            batch_size=args.batch_size,
            metadata=metadata,
        )
    else:
        input_path = Path(args.input)
        if not input_path.is_file():
            print(f'Input file not found: {input_path}', file=sys.stderr)
            return 2
        split_from_monolithic_json(
            input_path=input_path,
            output_dir=output_dir,
            batch_size=args.batch_size,
        )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
