"""Phase 5: the bot's real state documents round-trip unchanged through the adapter.

bot.py imports discord, so it is checked statically here; the state documents
themselves are exercised through storage.JsonFileBackend with fixture files
that mirror the bot's on-disk layout.
"""

from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path

import pytest

import agentic_automation
import crush_game
import storage
from groq_budget import GroqBudgetGovernor

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "json_state"
BOT_SOURCE = (ROOT / "bot.py").read_text(encoding="utf-8-sig")


@pytest.fixture
def data_dir(tmp_path):
    target = tmp_path / "data"
    shutil.copytree(FIXTURES, target)
    return target


@pytest.mark.parametrize("area", storage.MIGRATABLE_AREAS, ids=lambda a: a.key)
def test_document_round_trips_byte_for_byte(data_dir, area):
    backend = storage.JsonFileBackend(data_dir)
    path = data_dir / area.filename
    original = path.read_bytes()
    payload = backend.get(area.key)
    assert payload is not None and payload
    assert backend.set(area.key, payload)
    assert path.read_bytes() == original
    backup = data_dir / f"{area.filename}.bak"
    if area.backup:
        assert backup.read_bytes() == original
    else:
        assert not backup.exists()
    assert backend.get(area.key) == payload


def test_crush_and_agentic_state_objects_round_trip(data_dir):
    backend = storage.JsonFileBackend(data_dir)
    for key, cls in (("crush_game", crush_game.CrushGameState), ("agentic_state", agentic_automation.AgenticState)):
        path = data_dir / storage.AREAS_BY_KEY[key].filename
        original = path.read_bytes()
        state = cls(backend.get(key))
        assert backend.set(key, state.data)
        assert path.read_bytes() == original


def test_governor_counters_round_trip(data_dir):
    backend = storage.JsonFileBackend(data_dir)
    before = backend.get("groq_budget")
    wall = before["saved_at"]
    gov = GroqBudgetGovernor(storage_backend=backend, wall_clock=lambda: wall, day_key=lambda: "2026-11-05")
    assert gov.feature_usage("agent") == 4
    exported = gov.export_state()
    assert exported["features"] == before["features"]
    assert exported["models"]["openai/gpt-oss-120b"]["rpd"]["tokens"] == pytest.approx(990.0)


def test_legacy_aicrush_files_are_deleted_through_adapter(data_dir):
    backend = storage.JsonFileBackend(data_dir)
    (data_dir / "aicrush_state.json.bak").write_text("{}", encoding="utf-8")
    removed = backend.delete_files("legacy_aicrush")
    assert sorted(Path(p).name for p in removed) == ["aicrush_state.json", "aicrush_state.json.bak"]
    assert "legacy_aicrush" not in backend.list_keys()


# ---------------------------------------------------------------------------
# Static checks on bot.py wiring
# ---------------------------------------------------------------------------


def test_bot_has_no_direct_json_file_io():
    assert "read_json(" not in BOT_SOURCE and "write_json(" not in BOT_SOURCE
    for match in re.finditer(r"(\w+)\.(read_text|write_text)\(", BOT_SOURCE):
        assert match.group(1) == "BAD_WORDS_FILE", match.group(0)
    assert "_write_text_atomic" not in BOT_SOURCE
    assert "os.replace(" not in BOT_SOURCE
    # The only .json path literal left is the Groq budget default, handed to the adapter.
    json_literals = re.findall(r'"[\w./-]*\.json"', BOT_SOURCE)
    assert json_literals == ['"groq_budget_state.json"']


def test_bot_state_keys_are_registered_areas():
    tree = ast.parse(BOT_SOURCE)
    keys = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.endswith("_KEY") and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                keys[name] = node.value.value
    assert set(keys.values()) == {area.key for area in storage.AREAS}
    for call in ("read_state", "write_state"):
        for match in re.finditer(rf"{call}\((\w+)", BOT_SOURCE):
            if match.group(1) != "key":
                assert match.group(1) in keys, match.group(0)


def test_bot_routes_governor_and_storage_through_adapter():
    assert "STORAGE = storage.backend_from_env(" in BOT_SOURCE
    assert "storage_backend=STORAGE" in BOT_SOURCE
