#!/usr/bin/env python3
"""Copy the bot's JSON state files into PostgreSQL.

Run from the repository root with the bot stopped:

    python db/migrate_json_to_postgres.py --dry-run
    DATABASE_URL=... python db/migrate_json_to_postgres.py --apply-schema

``--dry-run`` only reads the JSON files and reports what would be migrated;
it never imports asyncpg and never opens a database connection. A real run
reads the connection string from the ``DATABASE_URL`` environment variable
only (never from the command line, so it does not end up in shell history)
and never prints it. Existing documents in the database are left alone
unless ``--overwrite`` is given. The JSON files are never modified.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence, TextIO

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import storage  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


@dataclass
class AreaReport:
    key: str
    path: Path
    table: str
    status: str  # ok | from-backup | empty | missing | unreadable
    rows: int = 0
    size: int = 0
    payload: dict | None = None

    @property
    def migratable(self) -> bool:
        return self.status in {"ok", "from-backup", "empty"}


def inspect_area(backend: storage.JsonFileBackend, area: storage.StateArea) -> AreaReport:
    path = backend.path_for(area.key)
    report = AreaReport(area.key, path, area.table, "missing")
    primary_exists = path.exists()
    backup_exists = area.backup and backend.backup_path(path).exists()
    if not primary_exists and not backup_exists:
        return report
    if primary_exists:
        try:
            report.size = path.stat().st_size
        except OSError:
            report.size = 0
    primary = backend._read_file(path) if primary_exists else None
    payload = backend.get(area.key)
    if payload is None:
        report.status = "unreadable"
        return report
    if primary is not None and (primary or payload == primary):
        report.status = "ok" if payload else "empty"
    else:
        report.status = "from-backup"
    report.payload = payload
    report.rows = len(payload)
    return report


def collect(data_dir: Path, groq_budget_file: Path | None) -> tuple[list[AreaReport], list[Path]]:
    paths = {"groq_budget": groq_budget_file} if groq_budget_file else None
    backend = storage.JsonFileBackend(data_dir, paths=paths, log=lambda _msg: None)
    reports = [inspect_area(backend, area) for area in storage.MIGRATABLE_AREAS]
    legacy = []
    for area in storage.AREAS:
        if area.legacy:
            path = backend.path_for(area.key)
            legacy.extend(p for p in (path, backend.backup_path(path)) if p.exists())
    return reports, legacy


def render_report(reports: Sequence[AreaReport], legacy: Sequence[Path], *, dry_run: bool, out: TextIO) -> None:
    mode = "DRY RUN - no database connection, nothing written" if dry_run else "LIVE"
    out.write(f"Bell JSON -> PostgreSQL migration ({mode})\n")
    out.write(f"{'area':<24} {'table':<30} {'status':<12} {'rows':>6} {'bytes':>9}  source\n")
    for r in reports:
        out.write(f"{r.key:<24} {r.table:<30} {r.status:<12} {r.rows:>6} {r.size:>9}  {r.path}\n")
    for path in legacy:
        out.write(f"skip (legacy, never migrated; delete with &legacydata wipe confirm): {path}\n")
    docs = [r for r in reports if r.migratable]
    rows = sum(r.rows for r in docs)
    missing = sum(1 for r in reports if r.status == "missing")
    unreadable = sum(1 for r in reports if r.status == "unreadable")
    verb = "would migrate" if dry_run else "migrating"
    out.write(
        f"Summary: {verb} {len(docs)} documents ({rows} rows); "
        f"{missing} missing, {unreadable} unreadable.\n"
    )


async def _migrate(reports: Sequence[AreaReport], dsn: str, *, apply_schema: bool, overwrite: bool, out: TextIO) -> int:
    backend = storage.PostgresBackend(dsn)
    try:
        if apply_schema:
            sql = SCHEMA_PATH.read_text(encoding="utf-8")

            async def run_schema() -> None:
                pool = await backend._get_pool()
                async with pool.acquire() as conn:
                    await conn.execute(sql)

            await backend._dispatch(run_schema())
            out.write("schema applied\n")
        existing = set(await backend.alist_keys())
        failures = 0
        for r in reports:
            if not r.migratable or r.payload is None:
                continue
            if r.key in existing and not overwrite:
                out.write(f"skip {r.key}: already in database (use --overwrite to replace)\n")
                continue
            ok = await backend.aset(r.key, r.payload)
            stored = await backend.aget(r.key) if ok else None
            if ok and stored == r.payload:
                out.write(f"migrated {r.key}: {r.rows} rows -> {r.table} (verified)\n")
            else:
                failures += 1
                out.write(f"FAILED {r.key}\n")
        return 1 if failures else 0
    finally:
        backend.close()


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="directory with the JSON files (default: data)")
    parser.add_argument(
        "--groq-budget-file",
        type=Path,
        default=None,
        help="Groq budget counters file (default: $GROQ_BUDGET_STATE_FILE or <data-dir>/groq_budget_state.json)",
    )
    parser.add_argument("--dry-run", action="store_true", help="report what would be migrated; no database access")
    parser.add_argument("--apply-schema", action="store_true", help="run db/schema.sql before copying")
    parser.add_argument("--overwrite", action="store_true", help="replace documents that already exist in the database")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, *, environ: dict[str, str] | None = None, out: TextIO = sys.stdout) -> int:
    args = parse_args(argv)
    env = os.environ if environ is None else environ
    groq_file = args.groq_budget_file
    if groq_file is None and str(env.get("GROQ_BUDGET_STATE_FILE", "")).strip():
        groq_file = Path(str(env["GROQ_BUDGET_STATE_FILE"]).strip())
    reports, legacy = collect(args.data_dir, groq_file)

    if args.json:
        payload: dict[str, Any] = {
            "dry_run": bool(args.dry_run),
            "areas": [
                {"key": r.key, "table": r.table, "status": r.status, "rows": r.rows, "bytes": r.size, "source": str(r.path)}
                for r in reports
            ],
            "legacy_skipped": [str(p) for p in legacy],
        }
        out.write(json.dumps(payload, indent=2) + "\n")
    else:
        render_report(reports, legacy, dry_run=args.dry_run, out=out)

    if args.dry_run:
        return 0

    dsn = str(env.get(storage.DATABASE_URL_ENV, "") or "").strip()
    if not dsn:
        out.write(f"error: set {storage.DATABASE_URL_ENV} for a real run (or use --dry-run)\n")
        return 2
    if any(r.status == "unreadable" for r in reports):
        out.write("error: fix or remove the unreadable files listed above before migrating\n")
        return 2
    import asyncio

    out.write(f"target: ${storage.DATABASE_URL_ENV} (value not shown)\n")
    return asyncio.run(_migrate(reports, dsn, apply_schema=args.apply_schema, overwrite=args.overwrite, out=out))


if __name__ == "__main__":
    raise SystemExit(main())
