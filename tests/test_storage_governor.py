"""Phase 5: Groq budget counters persist through the storage adapter."""

from __future__ import annotations

import asyncio
import json
import threading

import pytest

import storage
from groq_budget import FeatureCapExceededError, GroqBudgetGovernor, ModelLimits


class Clocks:
    def __init__(self, mono: float = 1000.0, wall: float = 1_800_000_000.0) -> None:
        self.mono = mono
        self.wall = wall


def make_gov(clocks: Clocks, **kwargs):
    kwargs.setdefault("default_limits", ModelLimits(rpm=100, rpd=5, tpm=100_000, tpd=100_000))
    return GroqBudgetGovernor(
        clock=lambda: clocks.mono,
        wall_clock=lambda: clocks.wall,
        day_key=lambda: "2026-11-05",
        max_wait_seconds=1.0,
        **kwargs,
    )


async def _ok(model):
    return "ok", None


def serve(gov, n, feature="agent"):
    async def go():
        for _ in range(n):
            await gov.run(["m1"], _ok, feature=feature, estimated_tokens=10)

    asyncio.run(go())


class CountingBackend(storage.JsonFileBackend):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.gets = 0
        self.sets = 0

    def get(self, key):
        self.gets += 1
        return super().get(key)

    def set(self, key, value):
        self.sets += 1
        return super().set(key, value)


class SharedMemoryBackend(storage.StorageBackend):
    """Stand-in for PostgresBackend: one store shared by several governors, locked updates."""

    shared = True
    name = "memory-shared"

    def __init__(self) -> None:
        self.docs: dict[str, str] = {}
        self.lock = threading.Lock()
        self.updates = 0

    def get(self, key):
        raw = self.docs.get(key)
        return None if raw is None else json.loads(raw)

    def set(self, key, value):
        self.docs[key] = json.dumps(value)
        return True

    def delete(self, key):
        return self.docs.pop(key, None) is not None

    def list_keys(self):
        return sorted(self.docs)

    def update(self, key, fn):
        with self.lock:
            self.updates += 1
            new = fn(self.get(key))
            self.set(key, new)
            return json.loads(json.dumps(new))

    def version(self, key):
        return float(len(self.docs.get(key, "")))


def test_counters_persist_across_reinstantiation_via_adapter(tmp_path):
    backend = storage.JsonFileBackend(tmp_path / "data")
    clocks = Clocks()
    gov = make_gov(clocks, storage_backend=backend)
    serve(gov, 3)
    assert gov.feature_usage("agent") == 3
    rpd_left = gov.snapshot()["m1"]["rpd"]

    clocks.mono = 5.0  # "restart": new monotonic origin, same wall time
    fresh_backend = storage.JsonFileBackend(tmp_path / "data")
    again = make_gov(clocks, storage_backend=fresh_backend)
    assert again.feature_usage("agent") == 3
    assert again.snapshot()["m1"]["rpd"] == pytest.approx(rpd_left)
    serve(again, 2)
    with pytest.raises(Exception):
        serve(again, 1)  # rpd=5 exhausted across the restart
    stored = fresh_backend.get("groq_budget")
    assert stored["features"]["agent"]["used"] == 5


def test_adapter_file_keeps_original_compact_format(tmp_path):
    path = tmp_path / "data" / "groq_budget_state.json"
    gov = make_gov(Clocks(), storage_backend=storage.JsonFileBackend(tmp_path / "data"))
    serve(gov, 1)
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    assert text == json.dumps(payload, separators=(",", ":"), sort_keys=True)
    assert not path.with_name(path.name + ".bak").exists()


def test_state_path_still_works_and_goes_through_adapter(tmp_path):
    path = tmp_path / "custom.json"
    gov = make_gov(Clocks(), state_path=path)
    assert isinstance(gov.storage, storage.JsonFileBackend)
    assert gov.storage.path_for("groq_budget") == path
    serve(gov, 2)
    assert make_gov(Clocks(), state_path=path).feature_usage("agent") == 2


def test_no_storage_means_no_persistence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gov = make_gov(Clocks())
    assert gov.storage is None and gov.shared is False
    serve(gov, 1)
    assert list(tmp_path.iterdir()) == []


def test_json_backend_is_single_process_and_never_rereads(tmp_path):
    backend = CountingBackend(tmp_path / "data")
    gov = make_gov(Clocks(), storage_backend=backend)
    assert gov.shared is False
    serve(gov, 3)
    assert backend.gets == 1  # loaded once at start-up, like the old file code
    assert backend.sets >= 3


def test_shared_backend_merges_counters_across_processes():
    shared = SharedMemoryBackend()
    clocks = Clocks()
    a = make_gov(clocks, storage_backend=shared, feature_caps={"agent": 3})
    b = make_gov(clocks, storage_backend=shared, feature_caps={"agent": 3})
    assert a.shared and b.shared
    serve(a, 1)
    serve(b, 1)
    serve(a, 1)
    assert shared.get("groq_budget")["features"]["agent"]["used"] == 3
    # The cap is enforced across both "processes".
    with pytest.raises(FeatureCapExceededError):
        serve(b, 1)
    assert shared.get("groq_budget")["features"]["agent"]["used"] == 3
    assert b.feature_usage("agent") == 3
    assert shared.updates > 0


def test_shared_backend_shares_request_buckets():
    shared = SharedMemoryBackend()
    clocks = Clocks()
    a = make_gov(clocks, storage_backend=shared)
    b = make_gov(clocks, storage_backend=shared)
    serve(a, 3)
    serve(b, 2)  # rpd=5 in total across both
    with pytest.raises(Exception):
        serve(a, 1)


def test_feature_admission_without_model_call_is_persisted(tmp_path):
    backend = storage.JsonFileBackend(tmp_path / "data")
    gov = make_gov(Clocks(), storage_backend=backend, feature_caps={"nudge": 2})
    assert gov.try_admit_feature("nudge") and gov.try_admit_feature("nudge")
    assert not gov.try_admit_feature("nudge")
    reloaded = make_gov(Clocks(), storage_backend=storage.JsonFileBackend(tmp_path / "data"), feature_caps={"nudge": 2})
    assert reloaded.feature_usage("nudge") == 2


# ---------------------------------------------------------------------------
# Fail closed on quota persistence failure
# ---------------------------------------------------------------------------

from groq_budget import QuotaPersistenceError  # noqa: E402


def _break_replace(monkeypatch):
    real = storage.os.replace

    def failing(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(storage.os, "replace", failing)
    return real


class FlakyBackend(storage.JsonFileBackend):
    """JSON backend whose set() can be told to return False or raise."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.mode = "ok"

    def set(self, key, value):
        if self.mode == "false":
            return False
        if self.mode == "raise":
            raise RuntimeError("storage down")
        return super().set(key, value)


def test_missing_state_file_allows_normal_operation(tmp_path):
    backend = storage.JsonFileBackend(tmp_path / "data")
    assert not backend.exists("groq_budget")
    gov = make_gov(Clocks(), storage_backend=backend)
    assert gov.persistence_healthy
    serve(gov, 2)
    assert backend.get("groq_budget")["features"]["agent"]["used"] == 2


@pytest.mark.parametrize("mode", ["false", "raise"])
def test_save_failure_blocks_subsequent_provider_requests(tmp_path, mode):
    backend = FlakyBackend(tmp_path / "data")
    gov = make_gov(Clocks(), storage_backend=backend)
    serve(gov, 1)
    backend.mode = mode
    calls = []

    async def attempt(model):
        calls.append(model)
        return "ok", None

    async def go():
        return await gov.run(["m1"], attempt, feature="agent", estimated_tokens=10)

    # The admission is counted in memory, its save fails, and the request is refused
    # before any provider call; so is every later one while saving keeps failing.
    with pytest.raises(QuotaPersistenceError):
        asyncio.run(go())
    with pytest.raises(QuotaPersistenceError):
        asyncio.run(go())
    assert calls == []
    assert not gov.persistence_healthy
    assert gov.try_admit_feature("nudge") is False  # non-model features fail closed too


def test_save_failure_from_failed_atomic_replace_blocks_requests(tmp_path, monkeypatch):
    backend = storage.JsonFileBackend(tmp_path / "data")
    gov = make_gov(Clocks(), storage_backend=backend)
    serve(gov, 1)
    path = tmp_path / "data" / "groq_budget_state.json"
    good = path.read_bytes()
    _break_replace(monkeypatch)
    with pytest.raises(QuotaPersistenceError):
        serve(gov, 1)
    assert path.read_bytes() == good  # last good counters preserved


def test_later_successful_save_recovers(tmp_path):
    backend = FlakyBackend(tmp_path / "data")
    gov = make_gov(Clocks(), storage_backend=backend)
    serve(gov, 1)
    backend.mode = "false"
    with pytest.raises(QuotaPersistenceError):
        serve(gov, 1)
    backend.mode = "ok"
    serve(gov, 1)  # the gate retries the save, it succeeds, normal operation resumes
    assert gov.persistence_healthy
    # Usage counted while saving failed was kept, not reset.
    stored = backend.get("groq_budget")
    assert stored["features"]["agent"]["used"] == gov.feature_usage("agent") >= 2
    assert make_gov(Clocks(), storage_backend=storage.JsonFileBackend(tmp_path / "data")).feature_usage("agent") == (
        gov.feature_usage("agent")
    )


@pytest.mark.parametrize(
    "content",
    ["{not json", "[1, 2]", '{"version": 999, "features": {}}'],
    ids=["corrupt", "not-an-object", "unknown-version"],
)
def test_corrupt_existing_state_blocks_requests(tmp_path, content):
    path = tmp_path / "data" / "groq_budget_state.json"
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    gov = make_gov(Clocks(), storage_backend=storage.JsonFileBackend(tmp_path / "data"))
    assert not gov.persistence_healthy
    with pytest.raises(QuotaPersistenceError):
        serve(gov, 1)
    assert gov.try_admit_feature("agent") is False
    assert path.read_text(encoding="utf-8") == content  # never replaced by zeroed counters


def test_fixing_or_removing_corrupt_state_recovers(tmp_path):
    path = tmp_path / "data" / "groq_budget_state.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    clocks = Clocks()
    gov = make_gov(clocks, storage_backend=storage.JsonFileBackend(tmp_path / "data"))
    with pytest.raises(QuotaPersistenceError):
        serve(gov, 1)

    # Owner restores a good copy: its counters are honoured.
    donor = make_gov(clocks, storage_backend=storage.JsonFileBackend(tmp_path / "donor"))
    serve(donor, 3)
    path.write_bytes((tmp_path / "donor" / "groq_budget_state.json").read_bytes())
    serve(gov, 1)
    assert gov.persistence_healthy and gov.feature_usage("agent") == 4

    # Or deletes it deliberately: treated as a fresh install.
    path.write_text("{not json", encoding="utf-8")
    other = make_gov(clocks, storage_backend=storage.JsonFileBackend(tmp_path / "data"))
    with pytest.raises(QuotaPersistenceError):
        serve(other, 1)
    path.unlink()
    serve(other, 1)
    assert other.persistence_healthy and other.feature_usage("agent") == 1


class BrokenSharedBackend(SharedMemoryBackend):
    def __init__(self):
        super().__init__()
        self.fail_updates = False
        self.fail_reads = False

    def get(self, key):
        if self.fail_reads:
            raise RuntimeError("database unreachable")
        return super().get(key)

    def update(self, key, fn):
        if self.fail_updates:
            raise RuntimeError("database unreachable")
        return super().update(key, fn)


def test_shared_backend_update_failure_blocks_and_recovers():
    shared = BrokenSharedBackend()
    gov = make_gov(Clocks(), storage_backend=shared)
    serve(gov, 1)
    shared.fail_updates = True
    with pytest.raises(QuotaPersistenceError):
        serve(gov, 1)
    assert shared.get("groq_budget")["features"]["agent"]["used"] == 1
    shared.fail_updates = False
    serve(gov, 1)
    assert gov.persistence_healthy
    assert shared.get("groq_budget")["features"]["agent"]["used"] == 2


def test_shared_backend_read_failure_blocks_requests():
    shared = BrokenSharedBackend()
    gov = make_gov(Clocks(), storage_backend=shared)
    serve(gov, 1)
    shared.fail_reads = True
    with pytest.raises(QuotaPersistenceError):
        serve(gov, 1)
    shared.fail_reads = False
    serve(gov, 1)
    assert shared.get("groq_budget")["features"]["agent"]["used"] == 2


def test_feature_cap_errors_are_not_mistaken_for_persistence_failures():
    shared = SharedMemoryBackend()
    gov = make_gov(Clocks(), storage_backend=shared, feature_caps={"agent": 1})
    serve(gov, 1)
    with pytest.raises(FeatureCapExceededError):
        serve(gov, 1)
    assert gov.persistence_healthy
