"""Phase 7: PostgresBackend against a real PostgreSQL server.

These tests are skipped unless ``BELL_TEST_DATABASE_URL`` points at a
reachable PostgreSQL database and ``asyncpg`` is installed, so the offline
suite (``python -m pytest``) still passes without a database. CI starts a
throwaway ``postgres`` service container and sets ``BELL_REQUIRE_POSTGRES=1``
so that an unreachable database fails the job instead of skipping silently.
Locally: ``docker compose -f docker-compose.test.yml up -d`` (see
docs/TESTING.md).

``BELL_TEST_DATABASE_URL`` is deliberately *not* ``DATABASE_URL``: the bot and
the migration script read ``DATABASE_URL``, and these tests must never touch a
real bot database. Every test module run additionally works inside its own
freshly created schema (``bell_it_<random>``, selected through the
``search_path`` connection setting) and drops it at the end, so nothing
outside that schema is read or written.
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import os
import shutil
import sys
import threading
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pytest

import storage

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "json_state"
TEST_DSN_ENV = "BELL_TEST_DATABASE_URL"
REQUIRE_ENV = "BELL_REQUIRE_POSTGRES"

pytestmark = pytest.mark.postgres


def _unavailable(reason: str) -> None:
    if os.environ.get(REQUIRE_ENV, "").strip() in {"1", "true", "yes"}:
        pytest.fail(f"{REQUIRE_ENV} is set but PostgreSQL is unavailable: {reason}", pytrace=False)
    pytest.skip(f"PostgreSQL integration tests skipped: {reason}", allow_module_level=True)


def _with_search_path(dsn: str, schema: str) -> str:
    """Return ``dsn`` with ``search_path=<schema>`` (asyncpg passes unknown query params as server settings)."""
    parts = urlsplit(dsn)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "search_path"]
    query.append(("search_path", schema))
    return urlunsplit(parts._replace(query=urlencode(query)))


async def _admin(dsn: str, sql: str) -> None:
    import asyncpg  # noqa: PLC0415

    conn = await asyncpg.connect(dsn, timeout=5)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture(scope="module")
def pg_dsn():
    """DSN of an empty, schema-applied, per-module scratch schema; dropped afterwards."""
    base = os.environ.get(TEST_DSN_ENV, "").strip()
    if not base:
        _unavailable(f"{TEST_DSN_ENV} is not set")
    try:
        import asyncpg  # noqa: F401, PLC0415
    except ImportError:
        _unavailable("asyncpg is not installed")
    schema = f"bell_it_{uuid.uuid4().hex[:12]}"
    try:
        asyncio.run(_admin(base, f'CREATE SCHEMA "{schema}"'))
    except Exception as error:  # noqa: BLE001 - any connection problem means "no database"
        _unavailable(f"cannot connect ({type(error).__name__})")
    dsn = _with_search_path(base, schema)
    asyncio.run(_admin(dsn, (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")))
    try:
        yield dsn
    finally:
        asyncio.run(_admin(base, f'DROP SCHEMA "{schema}" CASCADE'))


async def _truncate_all(dsn: str) -> None:
    tables = ["bell_documents"] + [area.table for area in storage.MIGRATABLE_AREAS]
    await _admin(dsn, f"TRUNCATE {', '.join(tables)}")


@pytest.fixture
def backend(pg_dsn):
    asyncio.run(_truncate_all(pg_dsn))
    b = storage.PostgresBackend(pg_dsn)
    try:
        yield b
    finally:
        b.close()


def _fetch(dsn: str, sql: str, *args):
    import asyncpg  # noqa: PLC0415

    async def go():
        conn = await asyncpg.connect(dsn, timeout=5)
        try:
            return await conn.fetch(sql, *args)
        finally:
            await conn.close()

    return asyncio.run(go())


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_schema_creates_every_area_table_and_is_idempotent(pg_dsn):
    # Applying it a second time must be a no-op (the migration script may run it repeatedly).
    asyncio.run(_admin(pg_dsn, (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")))
    rows = _fetch(pg_dsn, "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")
    tables = {row["table_name"] for row in rows}
    assert tables == {"bell_documents"} | {area.table for area in storage.MIGRATABLE_AREAS}


# ---------------------------------------------------------------------------
# Adapter contract (mirrors tests/test_storage_contract.py)
# ---------------------------------------------------------------------------


def test_missing_key_reads_none(backend):
    assert backend.get("warnings") is None
    assert backend.exists("warnings") is False
    assert backend.list_keys() == []
    assert backend.version("warnings") == 0.0


def test_set_get_round_trip(backend):
    doc = {
        "1": {"2": [{"reason": "spam", "ts": 1.5}]},
        "unicode": "héllo ✓ 🔔",
        "null": None,
        "bools": [True, False],
        "big": 2**63,
        "neg": -0.25,
    }
    assert backend.set("warnings", doc) is True
    assert backend.get("warnings") == doc
    assert backend.exists("warnings")
    assert backend.version("warnings") > 0


def test_values_are_stored_by_value(backend):
    doc = {"a": {"b": 1}}
    backend.set("guild_settings", doc)
    doc["a"]["b"] = 2
    got = backend.get("guild_settings")
    assert got == {"a": {"b": 1}}
    got["a"]["b"] = 3
    assert backend.get("guild_settings") == {"a": {"b": 1}}


def test_overwrite_replaces_document_and_bumps_version(backend):
    backend.set("economy", {"old": 1, "gone": 2})
    v1 = backend.version("economy")
    backend.set("economy", {"new": 2})
    assert backend.get("economy") == {"new": 2}
    assert backend.version("economy") > v1


def test_delete(backend):
    backend.set("crush_game", {"guilds": {}})
    assert backend.delete("crush_game") is True
    assert backend.get("crush_game") is None
    assert backend.delete("crush_game") is False
    assert backend.version("crush_game") == 0.0


def test_list_keys_sorted_and_tracks_changes(backend):
    for key in ("warnings", "agentic_state", "economy"):
        backend.set(key, {"k": key})
    assert backend.list_keys() == ["agentic_state", "economy", "warnings"]
    backend.delete("economy")
    assert backend.list_keys() == ["agentic_state", "warnings"]


def test_empty_document_exists(backend):
    assert backend.set("economy", {}) is True
    assert backend.get("economy") == {}
    assert backend.exists("economy")
    assert backend.list_keys() == ["economy"]


def test_ensure_default_uses_area_seed(backend):
    assert backend.ensure_default("engagement") is True
    assert backend.get("engagement") == {"guilds": {}}
    assert backend.ensure_default("engagement") is False
    # Areas without a seed are not created.
    assert backend.ensure_default("crush_game") is False
    assert backend.get("crush_game") is None


def test_every_area_round_trips_into_its_own_table(backend, pg_dsn):
    for area in storage.MIGRATABLE_AREAS:
        assert backend.set(area.key, {"k": {"area": area.key}}) is True
    for area in storage.MIGRATABLE_AREAS:
        assert backend.get(area.key) == {"k": {"area": area.key}}
        rows = _fetch(pg_dsn, f"SELECT doc_key FROM {area.table}")
        assert [row["doc_key"] for row in rows] == ["k"]


def test_one_row_per_top_level_key_and_order_preserved(backend, pg_dsn):
    doc = {"z": 1, "a": {"y": 1, "b": 2}, "m": [3, 2, 1]}
    backend.set("guild_settings", doc)
    rows = _fetch(pg_dsn, "SELECT doc_key, position FROM bell_guild_settings ORDER BY position")
    assert [(row["doc_key"], row["position"]) for row in rows] == [("z", 0), ("a", 1), ("m", 2)]
    got = backend.get("guild_settings")
    assert list(got) == ["z", "a", "m"]  # top-level order kept
    assert got == doc  # nested JSONB key order is normalised, equality is not affected


def test_update_is_read_modify_write(backend):
    seen = []

    def bump(current):
        seen.append(current)
        current = dict(current or {})
        current["n"] = current.get("n", 0) + 1
        return current

    assert backend.update("groq_budget", bump) == {"n": 1}
    assert backend.update("groq_budget", bump) == {"n": 2}
    assert seen == [None, {"n": 1}]
    assert backend.get("groq_budget") == {"n": 2}


def test_update_rolls_back_when_fn_raises(backend):
    backend.set("groq_budget", {"n": 2})
    v = backend.version("groq_budget")

    def boom(_current):
        raise RuntimeError("no")

    with pytest.raises(RuntimeError):
        backend.update("groq_budget", boom)
    assert backend.get("groq_budget") == {"n": 2}
    assert backend.version("groq_budget") == v


def test_concurrent_updates_from_two_backends_lose_nothing(pg_dsn):
    """Two backends = two independent connection pools, like two bot processes."""
    asyncio.run(_truncate_all(pg_dsn))
    backends = [storage.PostgresBackend(pg_dsn), storage.PostgresBackend(pg_dsn)]
    per_thread = 15
    errors: list[BaseException] = []

    def bump(current):
        current = dict(current or {})
        current["n"] = current.get("n", 0) + 1
        return current

    def worker(b):
        try:
            for _ in range(per_thread):
                b.update("groq_budget", bump)
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(b,)) for b in backends for _ in range(3)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
        assert not errors
        assert backends[0].get("groq_budget") == {"n": per_thread * len(threads)}
    finally:
        for b in backends:
            b.close()


def test_async_api(backend):
    async def go():
        assert await backend.aset("crush_game", {"guilds": {"1": {}}})
        assert await backend.aget("crush_game") == {"guilds": {"1": {}}}
        assert await backend.alist_keys() == ["crush_game"]
        assert await backend.aupdate("crush_game", lambda cur: {"guilds": {}}) == {"guilds": {}}
        assert await backend.adelete("crush_game") is True
        assert await backend.aget("crush_game") is None

    asyncio.run(go())


def test_sync_calls_work_inside_a_running_loop(backend):
    """The bot calls storage synchronously from inside discord.py's event loop."""

    async def go():
        backend.set("economy", {"cash": 1})
        return backend.get("economy")

    assert asyncio.run(go()) == {"cash": 1}


def test_backend_is_reusable_after_close(backend):
    backend.set("warnings", {"a": 1})
    backend.close()
    assert backend.get("warnings") == {"a": 1}


# ---------------------------------------------------------------------------
# Failure behaviour: writes fail closed, the stored document is untouched
# ---------------------------------------------------------------------------


def test_unstorable_value_fails_closed_and_keeps_previous_document(backend):
    # PostgreSQL JSONB cannot hold U+0000; the JSON file backend can. The write
    # must report failure and roll back, never leave a half-written document.
    backend.set("mod_log", {"a": 1, "b": 2})
    v = backend.version("mod_log")
    assert backend.set("mod_log", {"a": "x\u0000y", "c": 3}) is False
    assert backend.get("mod_log") == {"a": 1, "b": 2}
    assert backend.version("mod_log") == v


def test_key_without_a_table_fails_closed(backend):
    # Ad-hoc keys work with JSON files but have no table in db/schema.sql.
    assert backend.set("adhoc_key", {"a": 1}) is False
    assert backend.get("adhoc_key") is None
    assert "adhoc_key" not in backend.list_keys()


def test_legacy_area_has_no_table(backend):
    with pytest.raises(ValueError):
        backend.get("legacy_aicrush")


# ---------------------------------------------------------------------------
# Callers: Groq budget governor and the migration script
# ---------------------------------------------------------------------------


def test_governor_caps_are_shared_across_processes(pg_dsn):
    from groq_budget import GroqBudgetGovernor

    asyncio.run(_truncate_all(pg_dsn))
    first, second = storage.PostgresBackend(pg_dsn), storage.PostgresBackend(pg_dsn)
    try:
        a = GroqBudgetGovernor(storage_backend=first, feature_caps={"agent": 2})
        b = GroqBudgetGovernor(storage_backend=second, feature_caps={"agent": 2})
        assert a.shared and b.shared
        assert a.try_admit_feature("agent")
        assert b.try_admit_feature("agent")
        assert not a.try_admit_feature("agent")
        assert not b.try_admit_feature("agent")
        assert first.get("groq_budget")["features"]["agent"]["used"] == 2
    finally:
        first.close()
        second.close()


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("migrate_live_pg", ROOT / "db" / "migrate_json_to_postgres.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_migration_script_against_real_database(tmp_path, pg_dsn):
    asyncio.run(_truncate_all(pg_dsn))
    data_dir = tmp_path / "data"
    shutil.copytree(FIXTURES, data_dir)
    before = {p.name: p.read_bytes() for p in data_dir.iterdir()}
    module = _load_migration_module()
    env = {"DATABASE_URL": pg_dsn}

    out = io.StringIO()
    assert module.main(["--data-dir", str(data_dir), "--apply-schema"], environ=env, out=out) == 0
    text = out.getvalue()
    assert "schema applied" in text
    assert text.count("(verified)") == len(storage.MIGRATABLE_AREAS)
    assert pg_dsn not in text and urlsplit(pg_dsn).hostname not in text

    json_backend = storage.JsonFileBackend(data_dir)
    check = storage.PostgresBackend(pg_dsn)
    try:
        assert check.list_keys() == sorted(a.key for a in storage.MIGRATABLE_AREAS)
        for area in storage.MIGRATABLE_AREAS:
            assert check.get(area.key) == json_backend.get(area.key), area.key
        assert "legacy_aicrush" not in check.list_keys()

        # A second run leaves existing documents alone ...
        out = io.StringIO()
        assert module.main(["--data-dir", str(data_dir)], environ=env, out=out) == 0
        assert out.getvalue().count("already in database") == len(storage.MIGRATABLE_AREAS)

        # ... unless --overwrite is given.
        check.set("economy", {"changed": True})
        out = io.StringIO()
        assert module.main(["--data-dir", str(data_dir), "--overwrite"], environ=env, out=out) == 0
        assert out.getvalue().count("(verified)") == len(storage.MIGRATABLE_AREAS)
        assert check.get("economy") == json_backend.get("economy")
    finally:
        check.close()

    # The JSON files are never modified.
    assert {p.name: p.read_bytes() for p in data_dir.iterdir()} == before
