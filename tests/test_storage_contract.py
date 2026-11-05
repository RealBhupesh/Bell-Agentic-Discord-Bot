"""Phase 5: storage adapter contract, run against JsonFileBackend.

Hermetic: every test works in ``tmp_path``; no network, no database.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

import storage
from storage import JsonFileBackend


@pytest.fixture
def backend(tmp_path):
    logs: list[str] = []
    b = JsonFileBackend(tmp_path / "data", log=logs.append)
    b.logs = logs  # type: ignore[attr-defined]
    return b


# ---------------------------------------------------------------------------
# Contract (any StorageBackend must pass these)
# ---------------------------------------------------------------------------


def test_missing_key_reads_none(backend):
    assert backend.get("warnings") is None
    assert backend.exists("warnings") is False
    assert backend.list_keys() == []
    assert backend.version("warnings") == 0.0


def test_set_get_round_trip(backend):
    doc = {"1": {"2": [{"reason": "spam", "ts": 1.5}]}, "unicode": "héllo ✓"}
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


def test_overwrite_replaces_document(backend):
    backend.set("economy", {"old": 1})
    backend.set("economy", {"new": 2})
    assert backend.get("economy") == {"new": 2}


def test_delete(backend):
    backend.set("crush_game", {"guilds": {}})
    assert backend.delete("crush_game") is True
    assert backend.get("crush_game") is None
    assert backend.delete("crush_game") is False


def test_list_keys_sorted_and_tracks_changes(backend):
    for key in ("warnings", "agentic_state", "economy"):
        backend.set(key, {"k": key})
    assert backend.list_keys() == ["agentic_state", "economy", "warnings"]
    backend.delete("economy")
    assert backend.list_keys() == ["agentic_state", "warnings"]


def test_update_is_read_modify_write(backend):
    seen = []

    def bump(current):
        seen.append(current)
        current = dict(current or {"n": 0})
        current["n"] += 1
        return current

    assert backend.update("groq_budget", bump) == {"n": 1}
    assert backend.update("groq_budget", bump) == {"n": 2}
    assert seen == [None, {"n": 1}]
    assert backend.get("groq_budget") == {"n": 2}


def test_update_that_raises_writes_nothing(backend):
    backend.set("warnings", {"keep": True})

    def boom(_current):
        raise RuntimeError("no")

    with pytest.raises(RuntimeError):
        backend.update("warnings", boom)
    assert backend.get("warnings") == {"keep": True}


def test_ensure_default_seeds_only_when_absent(backend):
    assert backend.ensure_default("engagement") is True
    assert backend.get("engagement") == {"guilds": {}}
    backend.set("engagement", {"guilds": {"1": {}}})
    assert backend.ensure_default("engagement") is False
    assert backend.get("engagement") == {"guilds": {"1": {}}}
    # Areas without a seed need an explicit value.
    assert backend.ensure_default("crush_game") is False
    assert backend.ensure_default("capabilities_overrides", {"schema_version": 1}) is True
    assert backend.get("capabilities_overrides") == {"schema_version": 1}


def test_async_api_matches_sync(backend):
    async def go():
        assert await backend.aget("mod_log") is None
        assert await backend.aset("mod_log", {"cases": {}}) is True
        assert await backend.aget("mod_log") == {"cases": {}}
        assert await backend.alist_keys() == ["mod_log"]
        assert await backend.aupdate("mod_log", lambda cur: {**cur, "x": 1}) == {"cases": {}, "x": 1}
        assert await backend.adelete("mod_log") is True
        assert await backend.aget("mod_log") is None

    asyncio.run(go())


def test_every_area_key_round_trips(backend):
    for area in storage.MIGRATABLE_AREAS:
        assert backend.set(area.key, {"area": area.key})
        assert backend.get(area.key) == {"area": area.key}
    assert backend.list_keys() == sorted(a.key for a in storage.MIGRATABLE_AREAS)


def test_invalid_keys_rejected(backend):
    for bad in ("../etc", "Warnings", "a b", ""):
        with pytest.raises(ValueError):
            backend.get(bad)


def test_ad_hoc_keys_are_supported(backend):
    assert backend.set("scratch_area", {"x": 1})
    assert backend.get("scratch_area") == {"x": 1}
    assert "scratch_area" in backend.list_keys()


# ---------------------------------------------------------------------------
# JsonFileBackend: exact on-disk behaviour
# ---------------------------------------------------------------------------


def test_pretty_files_and_backup_match_previous_format(backend):
    doc = {"b": 1, "a": {"nested": [1, 2]}}
    backend.set("warnings", doc)
    path = backend.data_dir / "warnings.json"
    expected = json.dumps(doc, indent=2)
    assert path.read_text(encoding="utf-8") == expected
    assert (backend.data_dir / "warnings.json.bak").read_text(encoding="utf-8") == expected


def test_capabilities_files_have_no_backup(backend):
    backend.set("capabilities_catalog", {"commands": []})
    assert (backend.data_dir / "capabilities_catalog.json").exists()
    assert not (backend.data_dir / "capabilities_catalog.json.bak").exists()


def test_groq_budget_uses_compact_sorted_format_without_backup(tmp_path):
    target = tmp_path / "custom" / "budget.json"
    b = JsonFileBackend(tmp_path / "data", paths={"groq_budget": target})
    b.set("groq_budget", {"z": 1, "a": {"y": 2, "b": 3}})
    assert target.read_text(encoding="utf-8") == '{"a":{"b":3,"y":2},"z":1}'
    assert not target.with_suffix(".json.bak").exists()
    assert not (tmp_path / "data").exists()


def test_read_falls_back_to_backup(backend):
    backend.set("economy", {"cash": 5})
    primary = backend.data_dir / "business_state.json"
    primary.write_text("{corrupt", encoding="utf-8")
    assert backend.get("economy") == {"cash": 5}
    primary.write_text("{}", encoding="utf-8")
    assert backend.get("economy") == {"cash": 5}
    primary.unlink()
    assert backend.get("economy") == {"cash": 5}


def test_empty_document_without_backup_reads_empty(backend):
    backend.data_dir.mkdir(parents=True)
    (backend.data_dir / "warnings.json").write_text("{}", encoding="utf-8")
    assert backend.get("warnings") == {}


def test_non_object_json_reads_as_missing(backend):
    backend.data_dir.mkdir(parents=True)
    (backend.data_dir / "crush_game.json").write_text("[1, 2]", encoding="utf-8")
    assert backend.get("crush_game") is None


def test_writes_leave_no_temp_files(backend):
    for i in range(5):
        backend.set("engagement", {"i": i})
        backend.set("groq_budget", {"i": i})
    names = sorted(p.name for p in backend.data_dir.iterdir())
    assert names == ["engagement_state.json", "engagement_state.json.bak", "groq_budget_state.json"]


def test_atomic_replace_failure_falls_back_to_direct_write(backend, monkeypatch):
    real_replace = os.replace

    def failing_replace(src, dst):
        raise OSError(18, "cross-device")

    monkeypatch.setattr(storage.os, "replace", failing_replace)
    assert backend.set("warnings", {"x": 1}) is True
    monkeypatch.setattr(storage.os, "replace", real_replace)
    assert backend.get("warnings") == {"x": 1}
    assert any("atomic_replace" in line for line in backend.logs)
    assert not [p for p in backend.data_dir.iterdir() if ".tmp-" in p.name]


def test_unwritable_target_reports_failure(backend):
    (backend.data_dir / "warnings.json").mkdir(parents=True)
    assert backend.set("warnings", {"x": 1}) is False
    assert any("JSON WRITE ERROR" in line for line in backend.logs)


def test_unserialisable_payload_is_rejected(backend):
    assert backend.set("groq_budget", {"bad": object()}) is False
    assert backend.get("groq_budget") is None


def test_seed_texts_match_previous_bot_defaults(backend):
    for key in ("warnings", "guild_settings", "mod_log", "engagement", "economy", "altfinder", "socialintel"):
        backend.ensure_default(key)
    d = backend.data_dir
    assert (d / "warnings.json").read_text() == "{}"
    assert (d / "mod_config.json").read_text() == "{}"
    assert (d / "ai_mod_state.json").read_text() == "{}"
    assert (d / "engagement_state.json").read_text() == '{"guilds": {}}'
    assert (d / "business_state.json").read_text() == "{}"
    assert (d / "altfinder_state.json").read_text() == '{"schema_version": 1, "guilds": {}}'
    assert (d / "socialintel_state.json").read_text() == '{"schema_version": 1, "guilds": {}}'
    # Seeding never creates backups.
    assert not list(d.glob("*.bak"))


def test_delete_files_removes_primary_and_backup(backend):
    backend.set("warnings", {"x": 1})
    removed = backend.delete_files("warnings")
    assert sorted(removed) == sorted(
        [str(backend.data_dir / "warnings.json"), str(backend.data_dir / "warnings.json.bak")]
    )
    assert backend.delete_files("warnings") == []


# ---------------------------------------------------------------------------
# Backend selection / Postgres stays inactive
# ---------------------------------------------------------------------------


def test_default_backend_is_json(tmp_path):
    b = storage.backend_from_env({}, data_dir=tmp_path)
    assert isinstance(b, JsonFileBackend)
    assert b.shared is False


def test_database_url_selects_postgres_without_connecting(monkeypatch):
    monkeypatch.delitem(sys.modules, "asyncpg", raising=False)
    b = storage.backend_from_env({"DATABASE_URL": "postgresql://bell:s3cret@db.invalid/bell"})
    assert isinstance(b, storage.PostgresBackend)
    assert b.shared is True
    assert "asyncpg" not in sys.modules  # imported lazily, on first query only
    assert b._loop is None and b._pool is None
    assert "s3cret" not in repr(b)


def test_redact_dsn():
    assert storage.redact_dsn("postgresql://u:pw@h:5432/d") == "postgresql://u:***@h:5432/d"
    assert storage.redact_dsn("postgresql://h/d") == "postgresql://h/d"


def test_storage_module_imports_no_database_driver():
    source = (storage.__file__ and open(storage.__file__, encoding="utf-8").read()) or ""
    top_level = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert not [line for line in top_level if "asyncpg" in line or "sqlalchemy" in line]
