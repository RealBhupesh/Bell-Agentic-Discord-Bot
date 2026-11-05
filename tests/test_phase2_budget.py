"""Enterprise-model cleanup of fallback chains and durable governor counters."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

import groq_budget
from groq_budget import GroqBudgetGovernor, ModelLimits

ROOT = Path(__file__).resolve().parent.parent
ENTERPRISE = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "moonshotai/kimi-k2-instruct-0905"]


# ---------------------------------------------------------------------------
# Fallback-chain cleanup
# ---------------------------------------------------------------------------


def test_is_enterprise_model():
    for model in ENTERPRISE + ["moonshotai/kimi-k2-instruct"]:
        assert groq_budget.is_enterprise_model(model)
    for model in ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "meta-llama/llama-prompt-guard-2-86m"]:
        assert not groq_budget.is_enterprise_model(model)


def test_default_chains_contain_only_free_models():
    model, fallbacks = groq_budget.load_groq_model_config({})
    assert not any(groq_budget.is_enterprise_model(m) for m in [model, *fallbacks])
    assert groq_budget.load_model_chain("X", "openai/gpt-oss-20b,qwen/qwen3.8-27b", {}) == [
        "openai/gpt-oss-20b",
        "qwen/qwen3.8-27b",
    ]


def test_bot_defaults_have_no_enterprise_models():
    source = (ROOT / "bot.py").read_text(encoding="utf-8-sig")
    for model in ENTERPRISE:
        assert model not in source
    assert "moonshotai/kimi" not in source
    # Every Groq model setting goes through the gated loaders.
    for name in ("AICRUSH", "ALTFINDER", "SOCIALINTEL"):
        assert re.search(rf'{name}_FALLBACK_MODELS = groq_budget\.load_model_chain\(', source)
        assert re.search(rf'{name}_EXPLAIN_MODEL = groq_budget\.load_primary_model\(', source)
        assert re.search(rf'{name}_RANK_MODEL = groq_budget\.load_primary_model\(', source)


def test_env_chains_strip_enterprise_models_without_opt_in():
    env = {"AICRUSH_FALLBACK_MODELS": "llama-3.3-70b-versatile, openai/gpt-oss-20b ,moonshotai/kimi-k2-instruct-0905"}
    assert groq_budget.load_model_chain("AICRUSH_FALLBACK_MODELS", "a/b", env) == ["openai/gpt-oss-20b"]
    assert groq_budget.load_primary_model("M", "openai/gpt-oss-120b", {"M": "llama-3.1-8b-instant"}) == (
        "openai/gpt-oss-120b"
    )
    model, fallbacks = groq_budget.load_groq_model_config(
        {"GROQ_MODEL": "llama-3.3-70b-versatile", "GROQ_FALLBACK_MODELS": "llama-3.1-8b-instant,qwen/qwen3.8-27b"}
    )
    assert model == groq_budget.DEFAULT_GROQ_MODEL and fallbacks == ["qwen/qwen3.8-27b"]


def test_enterprise_opt_in_keeps_models():
    env = {"GROQ_ALLOW_ENTERPRISE_MODELS": "1", "C": "llama-3.3-70b-versatile,openai/gpt-oss-20b"}
    assert groq_budget.load_model_chain("C", "", env) == ["llama-3.3-70b-versatile", "openai/gpt-oss-20b"]
    assert groq_budget.load_primary_model("M", "x", {**env, "M": "llama-3.1-8b-instant"}) == "llama-3.1-8b-instant"
    assert GroqBudgetGovernor.from_env(env).allow_enterprise_models
    assert not GroqBudgetGovernor.from_env({}).allow_enterprise_models


def test_governor_skips_enterprise_models_unless_allowed():
    called: list[str] = []

    async def attempt(model):
        called.append(model)
        return f"from {model}", 10

    gov = GroqBudgetGovernor()
    model, _ = asyncio.run(gov.run(["llama-3.3-70b-versatile", "openai/gpt-oss-20b"], attempt))
    assert model == "openai/gpt-oss-20b" and called == ["openai/gpt-oss-20b"]
    with pytest.raises(RuntimeError, match="GROQ_ALLOW_ENTERPRISE_MODELS"):
        asyncio.run(gov.run(["llama-3.1-8b-instant"], attempt))

    allowed = GroqBudgetGovernor(allow_enterprise_models=True)
    model, _ = asyncio.run(allowed.run(["llama-3.3-70b-versatile"], attempt))
    assert model == "llama-3.3-70b-versatile"


# ---------------------------------------------------------------------------
# Durable counters
# ---------------------------------------------------------------------------


class Clocks:
    """Separate monotonic and wall clocks, like a real process restart."""

    def __init__(self, mono: float = 1000.0, wall: float = 1_800_000_000.0) -> None:
        self.mono = mono
        self.wall = wall

    def advance(self, seconds: float) -> None:
        self.mono += seconds
        self.wall += seconds


def make_gov(path, clocks: Clocks, day="2026-11-05", **kwargs):
    return GroqBudgetGovernor(
        default_limits=ModelLimits(rpm=100, rpd=5, tpm=100_000, tpd=100_000),
        state_path=path,
        clock=lambda: clocks.mono,
        wall_clock=lambda: clocks.wall,
        day_key=lambda: day,
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


def test_counters_persist_across_reinstantiation(tmp_path):
    path = tmp_path / "state" / "budget.json"
    clocks = Clocks()
    gov = make_gov(path, clocks, feature_caps={"agent": 10})
    serve(gov, 3)
    assert path.exists()
    assert gov.feature_usage("agent") == 3

    # "Restart": new process, monotonic clock restarts from a different origin.
    restarted = Clocks(mono=5.0, wall=clocks.wall + 30)
    gov2 = make_gov(path, restarted, feature_caps={"agent": 10})
    assert gov2.feature_usage("agent") == 3
    rpd_left = gov2.snapshot()["m1"]["rpd"]
    assert rpd_left == pytest.approx(2.0, abs=0.01)  # 5 - 3, plus ~30s of daily refill

    serve(gov2, 2)
    with pytest.raises(groq_budget.BudgetExhaustedError):
        serve(gov2, 1)  # daily allowance did not reset on restart


def test_feature_cap_survives_restart(tmp_path):
    path = tmp_path / "budget.json"
    clocks = Clocks()
    serve(make_gov(path, clocks, feature_caps={"agent": 2}), 2)
    with pytest.raises(groq_budget.FeatureCapExceededError):
        serve(make_gov(path, Clocks(mono=1.0, wall=clocks.wall + 5), feature_caps={"agent": 2}), 1)
    # A new UTC day resets the feature counter even after a restart.
    gov = make_gov(path, Clocks(mono=1.0, wall=clocks.wall + 5), day="2026-11-06", feature_caps={"agent": 2})
    assert gov.feature_usage("agent") == 0


def test_elapsed_wall_time_refills_buckets(tmp_path):
    path = tmp_path / "budget.json"
    clocks = Clocks()
    serve(make_gov(path, clocks), 5)
    later = Clocks(mono=1.0, wall=clocks.wall + 86_400)
    gov = make_gov(path, later)
    assert gov.snapshot()["m1"]["rpd"] == pytest.approx(5.0)


def test_rate_limit_block_survives_restart(tmp_path):
    path = tmp_path / "budget.json"
    clocks = Clocks()
    gov = make_gov(path, clocks)

    async def limited(model):
        raise groq_budget.ModelRateLimited("429", retry_after=600)

    with pytest.raises(groq_budget.GroqBudgetError):
        asyncio.run(gov.run(["m1"], limited))
    gov2 = make_gov(path, Clocks(mono=3.0, wall=clocks.wall + 100))
    assert gov2.snapshot()["m1"]["blocked_for"] == pytest.approx(500.0)
    assert gov2.circuit_open()


def test_state_file_is_written_atomically(tmp_path):
    path = tmp_path / "budget.json"
    gov = make_gov(path, Clocks())
    serve(gov, 1)
    payload = json.loads(path.read_text())
    assert payload["version"] == 1 and "m1" in payload["models"]
    assert payload["features"]["agent"] == {"day": "2026-11-05", "used": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["budget.json"]  # no temp files left behind


def test_atomic_write_keeps_old_file_on_failure(tmp_path):
    path = tmp_path / "f.json"
    groq_budget.atomic_write_json(path, {"a": 1})
    with pytest.raises(TypeError):
        groq_budget.atomic_write_json(path, {"bad": object()})
    assert json.loads(path.read_text()) == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["f.json"]


def test_corrupt_state_file_is_ignored(tmp_path):
    path = tmp_path / "budget.json"
    path.write_text("{not json")
    gov = make_gov(path, Clocks())
    assert gov.feature_usage("agent") == 0
    serve(gov, 1)
    assert json.loads(path.read_text())["features"]["agent"]["used"] == 1


def test_no_state_file_without_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gov = GroqBudgetGovernor.from_env({})
    assert gov.state_path is None
    serve(gov, 1)
    assert list(tmp_path.iterdir()) == []
    assert GroqBudgetGovernor.from_env({"GROQ_BUDGET_STATE_FILE": str(tmp_path / "s.json")}).state_path == (
        tmp_path / "s.json"
    )
