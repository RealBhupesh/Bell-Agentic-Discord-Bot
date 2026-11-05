"""Phase 5: PostgresBackend logic against an in-memory fake pool.

No database and no asyncpg: the backend's ``connector`` hook is given a fake
that understands exactly the statements the backend issues. This checks the
adapter contract and the row layout, not PostgreSQL itself.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from contextlib import asynccontextmanager

import pytest

import storage


class FakeDB:
    def __init__(self) -> None:
        self.documents: dict[str, int] = {}
        self.tables: dict[str, dict[str, tuple[int, str]]] = {}
        self.statements: list[str] = []
        self.dsn_seen: str | None = None


class FakeConn:
    def __init__(self, db: FakeDB) -> None:
        self.db = db

    @asynccontextmanager
    async def transaction(self):
        snapshot = (dict(self.db.documents), {t: dict(rows) for t, rows in self.db.tables.items()})
        try:
            yield
        except BaseException:
            self.db.documents, self.db.tables = snapshot
            raise

    async def execute(self, sql: str, *args):
        self.db.statements.append(sql)
        if sql.startswith("SELECT pg_advisory_xact_lock"):
            return "SELECT 1"
        if sql.startswith("INSERT INTO bell_documents"):
            self.db.documents[args[0]] = self.db.documents.get(args[0], 0) + 1
            return "INSERT 0 1"
        if sql.startswith("DELETE FROM bell_documents"):
            existed = self.db.documents.pop(args[0], None) is not None
            return f"DELETE {1 if existed else 0}"
        match = re.match(r"DELETE FROM (\w+)$", sql)
        if match:
            rows = self.db.tables.pop(match.group(1), {})
            return f"DELETE {len(rows)}"
        raise AssertionError(f"unexpected SQL: {sql}")

    async def executemany(self, sql: str, rows):
        self.db.statements.append(sql)
        table = re.match(r"INSERT INTO (\w+) \(doc_key, position, value\)", sql).group(1)
        target = self.db.tables.setdefault(table, {})
        for doc_key, position, value in rows:
            json.loads(value)  # must be valid JSON text for ::jsonb
            target[doc_key] = (position, value)

    async def fetchval(self, sql: str, *args):
        self.db.statements.append(sql)
        if sql.startswith("SELECT 1 FROM bell_documents"):
            return 1 if args[0] in self.db.documents else None
        if sql.startswith("SELECT version FROM bell_documents"):
            return self.db.documents.get(args[0])
        raise AssertionError(f"unexpected SQL: {sql}")

    async def fetch(self, sql: str, *args):
        self.db.statements.append(sql)
        if sql.startswith("SELECT doc_name FROM bell_documents"):
            return [{"doc_name": name} for name in sorted(self.db.documents)]
        table = re.match(r"SELECT doc_key, value FROM (\w+) ORDER BY position, doc_key", sql).group(1)
        rows = self.db.tables.get(table, {})
        ordered = sorted(rows.items(), key=lambda item: (item[1][0], item[0]))
        return [{"doc_key": key, "value": value} for key, (_pos, value) in ordered]


class FakePool:
    def __init__(self, db: FakeDB) -> None:
        self.db = db
        self.closed = False

    @asynccontextmanager
    async def acquire(self):
        yield FakeConn(self.db)

    async def close(self):
        self.closed = True


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def backend(db):
    async def connector(dsn, **_kwargs):
        db.dsn_seen = dsn
        return FakePool(db)

    b = storage.PostgresBackend("postgresql://bell:pw@db.invalid/bell", connector=connector)
    yield b
    b.close()


def test_contract_basics(backend, db):
    assert backend.get("warnings") is None
    assert backend.list_keys() == []
    doc = {"g1": {"u1": [{"reason": "spam"}]}, "g2": {}}
    assert backend.set("warnings", doc) is True
    assert backend.get("warnings") == doc
    assert backend.list_keys() == ["warnings"]
    assert backend.version("warnings") == 1.0
    backend.set("warnings", {"g3": 1})
    assert backend.get("warnings") == {"g3": 1}
    assert backend.version("warnings") == 2.0
    assert backend.delete("warnings") is True
    assert backend.delete("warnings") is False
    assert backend.get("warnings") is None
    assert "asyncpg" not in sys.modules


def test_one_row_per_top_level_key_in_order(backend, db):
    doc = {"z": 1, "a": {"nested": True}, "m": [1, 2]}
    backend.set("guild_settings", doc)
    rows = db.tables["bell_guild_settings"]
    assert {k: (pos, json.loads(v)) for k, (pos, v) in rows.items()} == {
        "z": (0, 1),
        "a": (1, {"nested": True}),
        "m": (2, [1, 2]),
    }
    assert list(backend.get("guild_settings")) == ["z", "a", "m"]


def test_empty_document_exists(backend):
    backend.set("altfinder", {})
    assert backend.get("altfinder") == {}
    assert backend.exists("altfinder")
    assert backend.ensure_default("altfinder") is False


def test_ensure_default_uses_area_seed(backend):
    assert backend.ensure_default("engagement") is True
    assert backend.get("engagement") == {"guilds": {}}


def test_update_locks_and_rolls_back_on_error(backend, db):
    backend.set("groq_budget", {"n": 1})
    assert backend.update("groq_budget", lambda cur: {"n": cur["n"] + 1}) == {"n": 2}
    assert any("pg_advisory_xact_lock" in sql for sql in db.statements)

    def boom(_cur):
        raise RuntimeError("no")

    with pytest.raises(RuntimeError):
        backend.update("groq_budget", boom)
    assert backend.get("groq_budget") == {"n": 2}


def test_async_api_from_another_event_loop(backend):
    async def go():
        assert await backend.aset("crush_game", {"guilds": {"1": {}}})
        assert await backend.aget("crush_game") == {"guilds": {"1": {}}}
        assert await backend.alist_keys() == ["crush_game"]
        assert await backend.aupdate("crush_game", lambda cur: {"guilds": {}}) == {"guilds": {}}
        assert await backend.adelete("crush_game") is True

    asyncio.run(go())


def test_sync_calls_work_inside_a_running_loop(backend):
    """The bot calls storage synchronously from inside discord.py's loop."""

    async def go():
        backend.set("economy", {"cash": 1})
        return backend.get("economy")

    assert asyncio.run(go()) == {"cash": 1}


def test_legacy_area_has_no_table(backend):
    with pytest.raises(ValueError):
        backend.get("legacy_aicrush")


def test_tables_come_from_the_area_registry(backend, db):
    for area in storage.MIGRATABLE_AREAS:
        backend.set(area.key, {"k": area.key})
    assert set(db.tables) == {area.table for area in storage.MIGRATABLE_AREAS}


def test_governor_on_postgres_backend_is_shared(backend):
    from groq_budget import GroqBudgetGovernor

    a = GroqBudgetGovernor(storage_backend=backend, feature_caps={"agent": 2})
    b = GroqBudgetGovernor(storage_backend=backend, feature_caps={"agent": 2})
    assert a.try_admit_feature("agent")
    assert b.try_admit_feature("agent")
    assert not a.try_admit_feature("agent")
    assert backend.get("groq_budget")["features"]["agent"]["used"] == 2


def test_migration_script_copies_fixtures_into_fake_database(tmp_path, monkeypatch, db):
    """The live path of db/migrate_json_to_postgres.py, against the fake pool only."""
    import importlib.util
    import io
    import shutil
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    data_dir = tmp_path / "data"
    shutil.copytree(Path(__file__).resolve().parent / "fixtures" / "json_state", data_dir)
    spec = importlib.util.spec_from_file_location("migrate_live_fake", root / "db" / "migrate_json_to_postgres.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    async def connector(dsn, **_kwargs):
        return FakePool(db)

    real = storage.PostgresBackend
    monkeypatch.setattr(storage, "PostgresBackend", lambda dsn: real(dsn, connector=connector))
    env = {"DATABASE_URL": "postgresql://bell:pw@db.invalid/bell"}

    out = io.StringIO()
    assert module.main(["--data-dir", str(data_dir)], environ=env, out=out) == 0
    text = out.getvalue()
    assert "pw@" not in text and "db.invalid" not in text
    assert text.count("(verified)") == len(storage.MIGRATABLE_AREAS)
    assert sorted(db.documents) == sorted(a.key for a in storage.MIGRATABLE_AREAS)

    json_backend = storage.JsonFileBackend(data_dir)
    check = real("postgresql://x", connector=connector)
    try:
        for area in storage.MIGRATABLE_AREAS:
            assert check.get(area.key) == json_backend.get(area.key)
    finally:
        check.close()

    out = io.StringIO()
    assert module.main(["--data-dir", str(data_dir)], environ=env, out=out) == 0
    assert out.getvalue().count("already in database") == len(storage.MIGRATABLE_AREAS)
