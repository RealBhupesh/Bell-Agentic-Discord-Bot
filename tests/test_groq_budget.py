"""Tests for groq_budget with a mocked Groq HTTP layer (no network, no discord)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import groq_budget
from groq_budget import (
    BudgetCoolingDownError,
    BudgetExhaustedError,
    FeatureCapExceededError,
    GroqBudgetGovernor,
    ModelLimits,
)

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeClock:
    """Monotonic clock whose sleep() advances time instantly."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


class FakeResponse:
    def __init__(self, status: int, body: dict | str, headers: dict | None = None) -> None:
        self.status = status
        self.text = body if isinstance(body, str) else json.dumps(body)
        self.headers = headers or {}


def ok(content: str, total_tokens: int | None = None) -> FakeResponse:
    body: dict = {"choices": [{"message": {"content": content}}]}
    if total_tokens is not None:
        body["usage"] = {"total_tokens": total_tokens}
    return FakeResponse(200, body)


def rate_limited(retry_after: str | None = None, body: str = "Rate limit reached") -> FakeResponse:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return FakeResponse(429, {"error": {"message": body}}, headers)


class MockGroqHTTP:
    """Mocked HTTP layer: per-model scripted responses, records every POST."""

    def __init__(self, scripts: dict[str, list[FakeResponse]] | None = None, clock: FakeClock | None = None):
        self.scripts = {model: list(responses) for model, responses in (scripts or {}).items()}
        self.calls: list[tuple[str, str, float]] = []  # (model, tag, time)
        self.clock = clock

    async def post(self, model: str, tag: str = "") -> FakeResponse:
        self.calls.append((model, tag, self.clock() if self.clock else 0.0))
        await asyncio.sleep(0)
        queue = self.scripts.get(model)
        if queue:
            return queue.pop(0)
        return ok(f"reply from {model}")

    def models_called(self) -> list[str]:
        return [model for model, _, _ in self.calls]


def make_attempt(http: MockGroqHTTP, tag: str = ""):
    """Translate mocked HTTP responses the same way bot.request_groq_completion does."""

    async def attempt(model: str):
        response = await http.post(model, tag)
        if response.status == 429:
            raise groq_budget.ModelRateLimited(
                f"Groq API error `429` for `{model}`",
                retry_after=groq_budget.parse_retry_after(response.headers.get("retry-after")),
                daily=groq_budget.is_daily_limit_body(response.text),
            )
        if response.status >= 500:
            raise groq_budget.ModelUnavailable(f"Groq API error `{response.status}` for `{model}`")
        if response.status >= 400:
            raise RuntimeError(f"Groq API error `{response.status}` for `{model}`")
        data = json.loads(response.text)
        usage = data.get("usage") or {}
        return data["choices"][0]["message"]["content"], usage.get("total_tokens")

    return attempt


def make_governor(clock: FakeClock, **kwargs) -> GroqBudgetGovernor:
    kwargs.setdefault("max_wait_seconds", 20.0)
    return GroqBudgetGovernor(clock=clock, sleep=clock.sleep, **kwargs)


MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


def test_config_defaults_when_env_unset():
    model, fallbacks = groq_budget.load_groq_model_config({})
    assert model == "openai/gpt-oss-120b"
    assert fallbacks == ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"]


def test_config_env_overrides_still_work():
    model, fallbacks = groq_budget.load_groq_model_config(
        {"GROQ_MODEL": "  my/model  ", "GROQ_FALLBACK_MODELS": " a/b , ,c/d "}
    )
    assert model == "my/model"
    assert fallbacks == ["a/b", "c/d"]


def test_bot_uses_new_groq_defaults():
    source = (ROOT / "bot.py").read_text(encoding="utf-8-sig")
    assert "groq_budget.load_groq_model_config(os.environ)" in source
    assert "llama-3.1-8b-instant" not in source
    # Every Groq chat completion goes through the governor.
    assert source.count("session.post(GROQ_API_URL") == 1
    assert "GROQ_BUDGET.run(" in source
    # OpenRouter path is still present and selectable.
    assert 'if _AI_PROVIDER_RAW in {"openrouter", "groq"}:' in source
    assert "async def request_openrouter_completion(" in source


def test_free_tier_limit_defaults_and_env_overrides():
    gov = GroqBudgetGovernor.from_env({})
    for model in MODELS:
        assert gov.limits_for(model) == ModelLimits(rpm=30, rpd=1000, tpm=8000, tpd=200000)
    guard = gov.limits_for("meta-llama/llama-prompt-guard-2-86m")
    assert (guard.rpm, guard.rpd) == (30, 14400)

    gov = GroqBudgetGovernor.from_env(
        {
            "GROQ_LIMIT_RPM": "5",
            "GROQ_MODEL_LIMITS": "openai/gpt-oss-20b=1:2:3:4",
            "GROQ_FEATURE_DAILY_CAPS": "ai_chat=10, aicrush_explain=3",
            "GROQ_BUDGET_MAX_WAIT_SECONDS": "7",
        }
    )
    assert gov.limits_for("unknown/model").rpm == 5
    assert gov.limits_for("openai/gpt-oss-20b") == ModelLimits(1, 2, 3, 4)
    assert gov.feature_caps == {"ai_chat": 10, "aicrush_explain": 3}
    assert gov.max_wait_seconds == 7.0


# ---------------------------------------------------------------------------
# FIFO queue
# ---------------------------------------------------------------------------


def test_queue_serves_requests_in_arrival_order():
    clock = FakeClock()
    # 1 request/minute: every caller after the first has to wait in line.
    gov = make_governor(
        clock, default_limits=ModelLimits(rpm=1, rpd=1000, tpm=100_000, tpd=1_000_000), max_wait_seconds=600
    )
    http = MockGroqHTTP(clock=clock)

    async def scenario():
        tasks = [
            asyncio.create_task(gov.run(["only/model"], make_attempt(http, tag=str(i)), estimated_tokens=10))
            for i in range(5)
        ]
        await asyncio.sleep(0)
        assert gov.queue_depth >= 1
        return await asyncio.gather(*tasks)

    results = run(scenario())
    assert [tag for _, tag, _ in http.calls] == ["0", "1", "2", "3", "4"]
    assert [round(t) for _, _, t in http.calls] == [0, 60, 120, 180, 240]
    assert all(model == "only/model" for model, _ in results)
    assert gov.queue_depth == 0


def test_cancelled_waiter_does_not_block_queue():
    clock = FakeClock()
    gov = make_governor(
        clock, default_limits=ModelLimits(rpm=1, rpd=100, tpm=100_000, tpd=1_000_000), max_wait_seconds=600
    )
    http = MockGroqHTTP(clock=clock)
    release = asyncio.Event()

    async def gated_sleep(seconds: float) -> None:
        await release.wait()
        clock.now += seconds

    async def scenario():
        await gov.run(["m"], make_attempt(http, "a"))
        gov._sleep = gated_sleep
        second = asyncio.create_task(gov.run(["m"], make_attempt(http, "b")))  # head, waiting for RPM
        third = asyncio.create_task(gov.run(["m"], make_attempt(http, "c")))  # queued behind
        fourth = asyncio.create_task(gov.run(["m"], make_attempt(http, "d")))
        for _ in range(3):
            await asyncio.sleep(0)
        assert gov.queue_depth == 3
        third.cancel()
        with pytest.raises(asyncio.CancelledError):
            await third
        assert gov.queue_depth == 2
        release.set()
        await second
        await fourth

    run(scenario())
    assert [tag for _, tag, _ in http.calls] == ["a", "b", "d"]
    assert gov.queue_depth == 0


# ---------------------------------------------------------------------------
# RPM limiting
# ---------------------------------------------------------------------------


def test_rpm_limit_spaces_out_requests():
    clock = FakeClock()
    gov = make_governor(
        clock, default_limits=ModelLimits(rpm=2, rpd=1000, tpm=100_000, tpd=1_000_000), max_wait_seconds=60
    )
    http = MockGroqHTTP(clock=clock)

    async def scenario():
        for _ in range(4):
            await gov.run(["m"], make_attempt(http), estimated_tokens=10)

    run(scenario())
    # Burst of 2, then one every 30s (2 per minute).
    assert [round(t) for _, _, t in http.calls] == [0, 0, 30, 60]


def test_rpm_limit_beyond_max_wait_falls_back_then_cools_down():
    clock = FakeClock()
    gov = make_governor(
        clock, default_limits=ModelLimits(rpm=1, rpd=1000, tpm=100_000, tpd=1_000_000), max_wait_seconds=5
    )
    http = MockGroqHTTP(clock=clock)

    async def scenario():
        a = await gov.run(["a", "b"], make_attempt(http))
        b = await gov.run(["a", "b"], make_attempt(http))  # a is at its RPM limit -> b
        with pytest.raises(BudgetCoolingDownError) as info:
            await gov.run(["a", "b"], make_attempt(http))
        return a, b, info.value

    a, b, error = run(scenario())
    assert (a[0], b[0]) == ("a", "b")
    assert "per-minute" in str(error)
    assert http.models_called() == ["a", "b"]
    # Once a minute has passed the circuit closes again.
    clock.now += 61
    assert run(gov.run(["a", "b"], make_attempt(http)))[0] == "a"


def test_tpm_limit_counts_tokens_and_reconciles_actual_usage():
    clock = FakeClock()
    gov = make_governor(
        clock, default_limits=ModelLimits(rpm=100, rpd=1000, tpm=1000, tpd=1_000_000), max_wait_seconds=600
    )
    http = MockGroqHTTP({"m": [ok("x", total_tokens=100), ok("y")]}, clock=clock)

    async def scenario():
        await gov.run(["m"], make_attempt(http), estimated_tokens=900)  # actual 100 -> 800 refunded
        await gov.run(["m"], make_attempt(http), estimated_tokens=900)

    run(scenario())
    assert [round(t) for _, _, t in http.calls] == [0, 0]


# ---------------------------------------------------------------------------
# RPD exhaustion -> circuit breaker
# ---------------------------------------------------------------------------


def test_rpd_exhaustion_falls_back_then_opens_circuit_breaker():
    clock = FakeClock()
    gov = make_governor(clock, default_limits=ModelLimits(rpm=30, rpd=2, tpm=100_000, tpd=1_000_000))
    http = MockGroqHTTP(clock=clock)
    models = MODELS[:2]

    async def scenario():
        used = [(await gov.run(models, make_attempt(http)))[0] for _ in range(4)]
        with pytest.raises(BudgetExhaustedError) as first:
            await gov.run(models, make_attempt(http))
        assert gov.circuit_open()
        with pytest.raises(BudgetExhaustedError) as second:
            await gov.run(models, make_attempt(http))
        return used, first.value, second.value

    used, first, second = run(scenario())
    assert used == [models[0], models[0], models[1], models[1]]
    assert "AI budget used up for today" in str(first)
    assert str(second) == groq_budget.BUDGET_EXHAUSTED_MESSAGE
    assert len(http.calls) == 4  # exhausted requests never hit the network
    assert isinstance(first, RuntimeError)  # bot code treats it like other AI errors


def test_daily_429_drains_day_budget_and_triggers_breaker():
    clock = FakeClock()
    gov = make_governor(clock)
    daily = rate_limited(retry_after="5", body="Rate limit reached for model: requests per day (RPD)")
    http = MockGroqHTTP({"a": [daily], "b": [daily]}, clock=clock)

    async def scenario():
        with pytest.raises(BudgetExhaustedError):
            await gov.run(["a", "b"], make_attempt(http))

    run(scenario())
    assert http.models_called() == ["a", "b"]
    assert gov.snapshot()["a"]["rpd"] <= 0


# ---------------------------------------------------------------------------
# Fallback on 429
# ---------------------------------------------------------------------------


def test_fallback_on_429_and_model_is_skipped_while_blocked():
    clock = FakeClock()
    gov = make_governor(clock, max_wait_seconds=5)
    http = MockGroqHTTP({MODELS[0]: [rate_limited(retry_after="30")]}, clock=clock)

    async def scenario():
        first = await gov.run(MODELS, make_attempt(http))
        second = await gov.run(MODELS, make_attempt(http))
        clock.now += 31
        third = await gov.run(MODELS, make_attempt(http))
        return first, second, third

    first, second, third = run(scenario())
    assert first == (MODELS[1], f"reply from {MODELS[1]}")
    assert second[0] == MODELS[1]  # primary still blocked by retry-after
    assert third[0] == MODELS[0]  # primary recovered
    assert http.models_called() == [MODELS[0], MODELS[1], MODELS[1], MODELS[0]]


def test_short_429_on_last_model_surfaces_retryable_error():
    clock = FakeClock()
    gov = make_governor(clock, max_wait_seconds=20)
    http = MockGroqHTTP({"only": [rate_limited(retry_after="2")]}, clock=clock)

    with pytest.raises(RuntimeError) as info:
        run(gov.run(["only"], make_attempt(http)))
    assert not isinstance(info.value, groq_budget.GroqBudgetError)
    assert "429" in str(info.value)
    # A short block is waited out on the next attempt instead of failing.
    assert run(gov.run(["only"], make_attempt(http)))[0] == "only"
    assert clock.sleeps and clock.sleeps[-1] >= 2


def test_non_retryable_error_aborts_without_fallback():
    clock = FakeClock()
    gov = make_governor(clock)
    http = MockGroqHTTP({MODELS[0]: [FakeResponse(400, {"error": "bad request"})]}, clock=clock)

    with pytest.raises(RuntimeError, match="400"):
        run(gov.run(MODELS, make_attempt(http)))
    assert http.models_called() == [MODELS[0]]


def test_server_error_falls_back_to_next_model():
    clock = FakeClock()
    gov = make_governor(clock)
    http = MockGroqHTTP({MODELS[0]: [FakeResponse(503, "unavailable")]}, clock=clock)
    assert run(gov.run(MODELS, make_attempt(http)))[0] == MODELS[1]


# ---------------------------------------------------------------------------
# Per-feature daily caps
# ---------------------------------------------------------------------------


def test_feature_daily_cap_and_reset():
    clock = FakeClock()
    day = {"key": "2026-11-05"}
    gov = make_governor(clock, feature_caps={"aicrush_explain": 2}, day_key=lambda: day["key"])
    http = MockGroqHTTP(clock=clock)

    async def scenario():
        await gov.run(MODELS, make_attempt(http), feature="aicrush_explain")
        await gov.run(MODELS, make_attempt(http), feature="AICrush_Explain")
        with pytest.raises(FeatureCapExceededError):
            await gov.run(MODELS, make_attempt(http), feature="aicrush_explain")
        await gov.run(MODELS, make_attempt(http), feature="general")  # other features unaffected

    run(scenario())
    assert len(http.calls) == 3
    day["key"] = "2026-11-06"
    run(gov.run(MODELS, make_attempt(http), feature="aicrush_explain"))
    assert gov.feature_usage("aicrush_explain") == 1


def test_failed_request_does_not_consume_feature_cap():
    clock = FakeClock()
    gov = make_governor(clock, feature_caps={"f": 1})
    http = MockGroqHTTP({"m": [FakeResponse(400, "bad")]}, clock=clock)
    with pytest.raises(RuntimeError):
        run(gov.run(["m"], make_attempt(http), feature="f"))
    assert gov.feature_usage("f") == 0
    assert run(gov.run(["m"], make_attempt(http), feature="f"))[0] == "m"


def test_estimate_tokens_includes_completion_budget():
    messages = [{"role": "user", "content": "x" * 400}]
    assert groq_budget.estimate_tokens(messages, 260) >= 100 + 260
