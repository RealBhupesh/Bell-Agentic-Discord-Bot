"""Phase 5: db/migrate_json_to_postgres.py --dry-run against fixture JSON files.

Hermetic: fixtures are copied to ``tmp_path``; no database, no network.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import sys
from pathlib import Path

import pytest

import storage

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "json_state"


def _load_script():
    spec = importlib.util.spec_from_file_location("migrate_json_to_postgres", ROOT / "db" / "migrate_json_to_postgres.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


migrate = _load_script()


@pytest.fixture
def data_dir(tmp_path):
    target = tmp_path / "data"
    shutil.copytree(FIXTURES, target)
    return target


@pytest.fixture(autouse=True)
def no_database(monkeypatch):
    """Any attempt to build a Postgres backend fails the test."""

    def refuse(*_a, **_k):
        raise AssertionError("dry run must not touch the database")

    monkeypatch.setattr(storage, "PostgresBackend", refuse)
    monkeypatch.delitem(sys.modules, "asyncpg", raising=False)


def _digest(directory: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.iterdir())}


def _run(argv, environ=None):
    out = io.StringIO()
    code = migrate.main(argv, environ=environ or {}, out=out)
    return code, out.getvalue()


def _expected_rows(name: str) -> int:
    return len(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_dry_run_reports_every_area(data_dir):
    before = _digest(data_dir)
    code, output = _run(["--dry-run", "--data-dir", str(data_dir)])
    assert code == 0
    assert "DRY RUN - no database connection, nothing written" in output
    lines = {line.split()[0]: line.split() for line in output.splitlines()[2:] if line and not line.startswith(("skip", "Summary"))}
    assert set(lines) == {area.key for area in storage.MIGRATABLE_AREAS}
    for area in storage.MIGRATABLE_AREAS:
        key, table, status, rows, size, source = lines[area.key]
        assert table == area.table
        assert status == "ok"
        assert int(rows) == _expected_rows(area.filename)
        assert int(size) == (FIXTURES / area.filename).stat().st_size
        assert Path(source) == data_dir / area.filename
    total_rows = sum(_expected_rows(a.filename) for a in storage.MIGRATABLE_AREAS)
    assert f"Summary: would migrate {len(storage.MIGRATABLE_AREAS)} documents ({total_rows} rows); 0 missing, 0 unreadable." in output
    assert f"skip (legacy, never migrated; the bot deletes it at startup): {data_dir / 'aicrush_state.json'}" in output
    assert "asyncpg" not in sys.modules
    assert _digest(data_dir) == before  # nothing on disk changed


def test_dry_run_flags_missing_backup_and_unreadable(data_dir):
    (data_dir / "warnings.json").unlink()
    (data_dir / "warnings.json.bak").unlink()
    (data_dir / "business_state.json").write_text("{broken", encoding="utf-8")  # .bak still good
    (data_dir / "capabilities_catalog.json").write_text("{broken", encoding="utf-8")  # no .bak for this area
    (data_dir / "altfinder_state.json").write_text("{}", encoding="utf-8")
    (data_dir / "altfinder_state.json.bak").unlink()
    code, output = _run(["--dry-run", "--data-dir", str(data_dir), "--json"])
    assert code == 0
    report = json.loads(output)
    assert report["dry_run"] is True
    status = {a["key"]: a for a in report["areas"]}
    assert status["warnings"]["status"] == "missing"
    assert status["economy"]["status"] == "from-backup"
    assert status["economy"]["rows"] == _expected_rows("business_state.json")
    assert status["capabilities_catalog"]["status"] == "unreadable"
    assert status["altfinder"]["status"] == "empty"
    assert status["altfinder"]["rows"] == 0
    assert report["legacy_skipped"] == [str(data_dir / "aicrush_state.json")]


def test_groq_budget_file_override(data_dir, tmp_path):
    custom = tmp_path / "elsewhere" / "budget.json"
    custom.parent.mkdir()
    shutil.move(str(data_dir / "groq_budget_state.json"), custom)
    _, output = _run(["--dry-run", "--data-dir", str(data_dir)], environ={"GROQ_BUDGET_STATE_FILE": str(custom)})
    line = next(line for line in output.splitlines() if line.startswith("groq_budget "))
    assert " ok " in line and str(custom) in line


def test_empty_data_dir(tmp_path):
    code, output = _run(["--dry-run", "--data-dir", str(tmp_path / "nothing")])
    assert code == 0
    assert f"would migrate 0 documents (0 rows); {len(storage.MIGRATABLE_AREAS)} missing, 0 unreadable." in output


def test_real_run_requires_database_url_and_never_connects(data_dir):
    code, output = _run(["--data-dir", str(data_dir)])
    assert code == 2
    assert "set DATABASE_URL" in output


def test_real_run_refuses_unreadable_files(data_dir):
    (data_dir / "capabilities_catalog.json").write_text("{broken", encoding="utf-8")
    code, output = _run(["--data-dir", str(data_dir)], environ={"DATABASE_URL": "postgresql://u:pw@db.invalid/x"})
    assert code == 2
    assert "unreadable" in output
    assert "pw@" not in output and "db.invalid" not in output


def test_schema_has_a_table_for_every_area():
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS bell_documents" in sql
    for area in storage.MIGRATABLE_AREAS:
        assert f"CREATE TABLE IF NOT EXISTS {area.table} (" in sql
    assert "aicrush" not in sql
