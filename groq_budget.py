"""Groq free-tier budget governor.

Every Groq chat-completion call made by the bot goes through
:class:`GroqBudgetGovernor`. It keeps the bot inside Groq's free-tier limits by:

* tracking per-model token buckets for requests/minute (RPM), requests/day
  (RPD), tokens/minute (TPM) and tokens/day (TPD);
* admitting requests through a FIFO queue, so callers are served in arrival
  order and a short wait for minute budgets is spent at the head of the line;
* enforcing optional per-feature daily request caps;
* falling back to the next model when a model returns HTTP 429 or its budget
  is exhausted;
* opening a circuit breaker with a clear "AI budget used up for today"
  message once every model is exhausted.

The module is stdlib-only and HTTP-agnostic: callers pass an ``attempt``
coroutine that performs the actual request for one model.
"""

from __future__ import annotations

import asyncio
import math
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------

DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_GROQ_FALLBACK_MODELS = "openai/gpt-oss-20b,qwen/qwen3.8-27b"


def _split_models(raw: str) -> list[str]:
    return [model.strip() for model in raw.split(",") if model.strip()]


def load_groq_model_config(environ: Mapping[str, str] | None = None) -> tuple[str, list[str]]:
    """Return ``(GROQ_MODEL, GROQ_FALLBACK_MODELS)`` honouring env overrides."""
    env = os.environ if environ is None else environ
    model = env.get("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
    fallbacks = _split_models(env.get("GROQ_FALLBACK_MODELS", DEFAULT_GROQ_FALLBACK_MODELS))
    return model, fallbacks


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelLimits:
    rpm: int
    rpd: int
    tpm: int
    tpd: int


# Groq free tier for the production chat models the bot uses
# (openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.8-27b). Applies to any
# model without a more specific entry and is overridable via GROQ_LIMIT_*.
FREE_TIER_DEFAULT_LIMITS = ModelLimits(rpm=30, rpd=1_000, tpm=8_000, tpd=200_000)
PROMPT_GUARD_MODEL = "meta-llama/llama-prompt-guard-2-86m"
PROMPT_GUARD_RPM = 30
PROMPT_GUARD_RPD = 14_400


def builtin_model_limits(default_limits: ModelLimits) -> dict[str, ModelLimits]:
    """Per-model limits that differ from the free-tier default."""
    # Safety classifier: higher request allowance. Token limits are not part of
    # the published numbers we rely on, so the (conservative) defaults apply.
    return {
        PROMPT_GUARD_MODEL: ModelLimits(
            rpm=PROMPT_GUARD_RPM, rpd=PROMPT_GUARD_RPD, tpm=default_limits.tpm, tpd=default_limits.tpd
        ),
    }


BUDGET_EXHAUSTED_MESSAGE = "AI budget used up for today. Please try again later."
FEATURE_CAP_MESSAGE = "Daily AI limit for this feature has been reached. Please try again tomorrow."
QUEUE_FULL_MESSAGE = "Too many AI requests are queued right now. Please try again in a minute."
COOLDOWN_MESSAGE = "AI has hit its per-minute limit. Please try again in about {seconds}s."


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GroqBudgetError(RuntimeError):
    """Base class for errors raised by the governor itself (never retried)."""


class BudgetExhaustedError(GroqBudgetError):
    def __init__(self, message: str = BUDGET_EXHAUSTED_MESSAGE) -> None:
        super().__init__(message)


class FeatureCapExceededError(GroqBudgetError):
    def __init__(self, feature: str, message: str = FEATURE_CAP_MESSAGE) -> None:
        super().__init__(message)
        self.feature = feature


class BudgetCoolingDownError(GroqBudgetError):
    def __init__(self, seconds: float) -> None:
        self.seconds = max(1, int(math.ceil(seconds)))
        super().__init__(COOLDOWN_MESSAGE.format(seconds=self.seconds))


class QueueFullError(GroqBudgetError):
    def __init__(self, message: str = QUEUE_FULL_MESSAGE) -> None:
        super().__init__(message)


class ModelRateLimited(Exception):
    """Raised by an ``attempt`` callback when the provider answered HTTP 429."""

    def __init__(self, detail: str, *, retry_after: float | None = None, daily: bool = False) -> None:
        super().__init__(detail)
        self.retry_after = retry_after
        self.daily = daily


class ModelUnavailable(Exception):
    """Raised by an ``attempt`` callback for errors where the next model should be tried."""


# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------


class TokenBucket:
    """Continuous-refill token bucket."""

    def __init__(self, capacity: float, period_seconds: float, now: float) -> None:
        self.capacity = float(max(1.0, capacity))
        self.rate = self.capacity / float(period_seconds)
        self.tokens = self.capacity
        self.updated = now

    def _refill(self, now: float) -> None:
        if now > self.updated:
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now

    def wait_time(self, amount: float, now: float) -> float:
        self._refill(now)
        amount = min(float(amount), self.capacity)
        if self.tokens >= amount:
            return 0.0
        return (amount - self.tokens) / self.rate

    def consume(self, amount: float, now: float) -> None:
        self._refill(now)
        self.tokens -= min(float(amount), self.capacity)

    def adjust(self, delta: float, now: float) -> None:
        """Charge (positive) or refund (negative) ``delta`` tokens."""
        self._refill(now)
        self.tokens = min(self.capacity, self.tokens - float(delta))

    def drain(self, now: float) -> None:
        self._refill(now)
        self.tokens = min(self.tokens, 0.0)


@dataclass
class _ModelState:
    limits: ModelLimits
    rpm: TokenBucket
    rpd: TokenBucket
    tpm: TokenBucket
    tpd: TokenBucket
    blocked_until: float = 0.0

    @classmethod
    def create(cls, limits: ModelLimits, now: float) -> "_ModelState":
        return cls(
            limits=limits,
            rpm=TokenBucket(limits.rpm, 60.0, now),
            rpd=TokenBucket(limits.rpd, 86_400.0, now),
            tpm=TokenBucket(limits.tpm, 60.0, now),
            tpd=TokenBucket(limits.tpd, 86_400.0, now),
        )

    def wait_time(self, tokens: int, now: float) -> float:
        return max(
            self.blocked_until - now,
            self.rpm.wait_time(1, now),
            self.rpd.wait_time(1, now),
            self.tpm.wait_time(tokens, now),
            self.tpd.wait_time(tokens, now),
            0.0,
        )

    def reserve(self, tokens: int, now: float) -> None:
        self.rpm.consume(1, now)
        self.rpd.consume(1, now)
        self.tpm.consume(tokens, now)
        self.tpd.consume(tokens, now)


# ---------------------------------------------------------------------------
# Env parsing helpers
# ---------------------------------------------------------------------------


def _env_int(env: Mapping[str, str], name: str, default: int, minimum: int = 0) -> int:
    raw = str(env.get(name, "")).strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(minimum, value)


def _env_float(env: Mapping[str, str], name: str, default: float, minimum: float = 0.0) -> float:
    raw = str(env.get(name, "")).strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        value = default
    return max(minimum, value)


def parse_feature_caps(raw: str) -> dict[str, int]:
    """Parse ``"ai_chat=300,aicrush_explain=50"`` into a dict."""
    caps: dict[str, int] = {}
    for chunk in raw.split(","):
        if "=" not in chunk:
            continue
        name, _, value = chunk.partition("=")
        name = name.strip().lower()
        try:
            cap = int(value.strip())
        except ValueError:
            continue
        if name and cap >= 0:
            caps[name] = cap
    return caps


def parse_model_limits(raw: str) -> dict[str, ModelLimits]:
    """Parse ``"model=rpm:rpd:tpm:tpd;other=..."`` into per-model limits."""
    parsed: dict[str, ModelLimits] = {}
    for chunk in raw.split(";"):
        if "=" not in chunk:
            continue
        model, _, values = chunk.rpartition("=")
        parts = [part.strip() for part in values.split(":")]
        if len(parts) != 4:
            continue
        try:
            rpm, rpd, tpm, tpd = (max(1, int(part)) for part in parts)
        except ValueError:
            continue
        if model.strip():
            parsed[model.strip()] = ModelLimits(rpm=rpm, rpd=rpd, tpm=tpm, tpd=tpd)
    return parsed


def estimate_tokens(messages: list[dict[str, Any]], max_tokens: int) -> int:
    """Rough upper estimate: ~4 characters per token for the prompt + completion budget."""
    chars = 0
    for message in messages:
        content = message.get("content", "")
        chars += len(content if isinstance(content, str) else str(content)) + 8
    return int(math.ceil(chars / 4.0)) + max(0, int(max_tokens))


def _utc_day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Governor
# ---------------------------------------------------------------------------


AttemptFn = Callable[[str], Awaitable[tuple[Any, int | None]]]


@dataclass
class _FeatureUsage:
    day: str = ""
    used: int = 0


class GroqBudgetGovernor:
    def __init__(
        self,
        *,
        default_limits: ModelLimits = FREE_TIER_DEFAULT_LIMITS,
        model_limits: Mapping[str, ModelLimits] | None = None,
        feature_caps: Mapping[str, int] | None = None,
        default_feature_cap: int = 0,
        max_wait_seconds: float = 20.0,
        default_retry_after: float = 60.0,
        max_queue: int = 100,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        day_key: Callable[[], str] = _utc_day_key,
    ) -> None:
        self.default_limits = default_limits
        self.model_limits = builtin_model_limits(default_limits)
        if model_limits:
            self.model_limits.update(model_limits)
        self.feature_caps = {k.strip().lower(): int(v) for k, v in (feature_caps or {}).items()}
        self.default_feature_cap = max(0, int(default_feature_cap))
        self.max_wait_seconds = max(0.0, float(max_wait_seconds))
        self.default_retry_after = max(1.0, float(default_retry_after))
        self.max_queue = max(1, int(max_queue))
        self._clock = clock
        self._sleep = sleep
        self._day_key = day_key
        self._models: dict[str, _ModelState] = {}
        self._features: dict[str, _FeatureUsage] = {}
        self._waiters: deque[asyncio.Future[None]] = deque()
        self._circuit_open_until = 0.0
        self._circuit_daily = False

    # -- construction -----------------------------------------------------

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None, **overrides: Any) -> "GroqBudgetGovernor":
        env = os.environ if environ is None else environ
        d = FREE_TIER_DEFAULT_LIMITS
        default_limits = ModelLimits(
            rpm=_env_int(env, "GROQ_LIMIT_RPM", d.rpm, 1),
            rpd=_env_int(env, "GROQ_LIMIT_RPD", d.rpd, 1),
            tpm=_env_int(env, "GROQ_LIMIT_TPM", d.tpm, 1),
            tpd=_env_int(env, "GROQ_LIMIT_TPD", d.tpd, 1),
        )
        kwargs: dict[str, Any] = dict(
            default_limits=default_limits,
            model_limits=parse_model_limits(str(env.get("GROQ_MODEL_LIMITS", ""))),
            feature_caps=parse_feature_caps(str(env.get("GROQ_FEATURE_DAILY_CAPS", ""))),
            default_feature_cap=_env_int(env, "GROQ_FEATURE_DAILY_CAP_DEFAULT", 0, 0),
            max_wait_seconds=_env_float(env, "GROQ_BUDGET_MAX_WAIT_SECONDS", 20.0, 0.0),
            default_retry_after=_env_float(env, "GROQ_DEFAULT_RETRY_AFTER_SECONDS", 60.0, 1.0),
            max_queue=_env_int(env, "GROQ_QUEUE_MAX", 100, 1),
        )
        kwargs.update(overrides)
        return cls(**kwargs)

    # -- state helpers ----------------------------------------------------

    def limits_for(self, model: str) -> ModelLimits:
        return self.model_limits.get(model, self.default_limits)

    def _state(self, model: str) -> _ModelState:
        state = self._models.get(model)
        if state is None:
            state = _ModelState.create(self.limits_for(model), self._clock())
            self._models[model] = state
        return state

    @property
    def queue_depth(self) -> int:
        return len(self._waiters)

    def circuit_open(self) -> bool:
        return self._clock() < self._circuit_open_until

    def snapshot(self) -> dict[str, dict[str, float]]:
        """Remaining budget per model (for diagnostics)."""
        now = self._clock()
        out: dict[str, dict[str, float]] = {}
        for model, state in self._models.items():
            for bucket in (state.rpm, state.rpd, state.tpm, state.tpd):
                bucket._refill(now)
            out[model] = {
                "rpm": state.rpm.tokens,
                "rpd": state.rpd.tokens,
                "tpm": state.tpm.tokens,
                "tpd": state.tpd.tokens,
                "blocked_for": max(0.0, state.blocked_until - now),
            }
        return out

    # -- per-feature caps -------------------------------------------------

    def _feature_cap(self, feature: str) -> int:
        return self.feature_caps.get(feature, self.default_feature_cap)

    def feature_usage(self, feature: str) -> int:
        usage = self._features.get(feature.strip().lower())
        if usage is None or usage.day != self._day_key():
            return 0
        return usage.used

    def _admit_feature(self, feature: str) -> None:
        cap = self._feature_cap(feature)
        today = self._day_key()
        usage = self._features.setdefault(feature, _FeatureUsage())
        if usage.day != today:
            usage.day = today
            usage.used = 0
        if cap > 0 and usage.used >= cap:
            raise FeatureCapExceededError(feature)
        usage.used += 1

    def _refund_feature(self, feature: str) -> None:
        usage = self._features.get(feature)
        if usage is not None and usage.day == self._day_key() and usage.used > 0:
            usage.used -= 1

    # -- FIFO queue -------------------------------------------------------

    async def _acquire_turn(self) -> None:
        if len(self._waiters) >= self.max_queue:
            raise QueueFullError()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        self._waiters.append(fut)
        if self._waiters[0] is fut:
            fut.set_result(None)
        try:
            await fut
        except BaseException:
            was_head = bool(self._waiters) and self._waiters[0] is fut
            try:
                self._waiters.remove(fut)
            except ValueError:
                pass
            if was_head:
                self._wake_next()
            raise

    def _release_turn(self) -> None:
        if self._waiters:
            self._waiters.popleft()
        self._wake_next()

    def _wake_next(self) -> None:
        if self._waiters and not self._waiters[0].done():
            self._waiters[0].set_result(None)

    async def _reserve(self, model: str, tokens: int) -> bool:
        """Wait at the head of the queue until ``model`` can serve ``tokens``.

        Returns False (without waiting) when the model would need longer than
        ``max_wait_seconds`` - i.e. it is exhausted for now.
        """
        await self._acquire_turn()
        try:
            state = self._state(model)
            wait = state.wait_time(tokens, self._clock())
            if wait > self.max_wait_seconds:
                return False
            if wait > 0:
                await self._sleep(wait)
            state.reserve(tokens, self._clock())
            return True
        finally:
            self._release_turn()

    # -- 429 handling -----------------------------------------------------

    def _penalize(self, model: str, error: ModelRateLimited) -> None:
        now = self._clock()
        state = self._state(model)
        retry_after = error.retry_after if error.retry_after and error.retry_after > 0 else self.default_retry_after
        state.blocked_until = max(state.blocked_until, now + retry_after)
        if error.daily:
            state.rpd.drain(now)
            state.tpd.drain(now)
        # Groq's own window is authoritative: our minute view was too optimistic.
        state.rpm.drain(now)

    def _daily_exhausted(self, state: _ModelState, tokens: int, now: float) -> bool:
        return (
            state.rpd.wait_time(1, now) > self.max_wait_seconds
            or state.tpd.wait_time(tokens, now) > self.max_wait_seconds
        )

    def _circuit_error(self) -> GroqBudgetError:
        if self._circuit_daily:
            return BudgetExhaustedError()
        return BudgetCoolingDownError(self._circuit_open_until - self._clock())

    def _open_circuit(self, models: list[str], tokens: int) -> GroqBudgetError:
        """Every model is out of budget: fail fast until the first one recovers."""
        now = self._clock()
        states = [self._state(model) for model in models]
        waits = [state.wait_time(tokens, now) for state in states]
        self._circuit_open_until = now + (min(waits) if waits else self.default_retry_after)
        self._circuit_daily = all(self._daily_exhausted(state, tokens, now) for state in states)
        return self._circuit_error()

    # -- main entry point -------------------------------------------------

    async def run(
        self,
        models: list[str],
        attempt: AttemptFn,
        *,
        feature: str = "general",
        estimated_tokens: int = 0,
    ) -> tuple[str, Any]:
        """Run ``attempt(model)`` on the first model with budget, falling back in order.

        ``attempt`` returns ``(value, total_tokens_used_or_None)`` on success,
        raises :class:`ModelRateLimited` on HTTP 429, :class:`ModelUnavailable`
        for errors that should move on to the next model, and anything else to
        abort immediately. Returns ``(model_used, value)``.
        """
        ordered: list[str] = []
        for model in models:
            cleaned = (model or "").strip()
            if cleaned and cleaned not in ordered:
                ordered.append(cleaned)
        if not ordered:
            raise RuntimeError("No Groq models configured.")

        if self.circuit_open():
            raise self._circuit_error()

        feature_key = (feature or "general").strip().lower() or "general"
        self._admit_feature(feature_key)
        try:
            return await self._run_models(ordered, attempt, max(1, int(estimated_tokens)))
        except BaseException:
            # Nothing was served, so the request does not count against the feature cap.
            self._refund_feature(feature_key)
            raise

    async def _run_models(self, ordered: list[str], attempt: AttemptFn, tokens: int) -> tuple[str, Any]:
        budget_blocked = 0
        last_error: BaseException | None = None

        for model in ordered:
            if not await self._reserve(model, tokens):
                budget_blocked += 1
                continue
            try:
                value, used = await attempt(model)
            except ModelRateLimited as error:
                self._penalize(model, error)
                last_error = error
                state = self._state(model)
                if state.blocked_until - self._clock() > self.max_wait_seconds or error.daily:
                    budget_blocked += 1
                continue
            except ModelUnavailable as error:
                last_error = error
                continue
            if used is not None and used > 0:
                state = self._state(model)
                now = self._clock()
                delta = int(used) - tokens
                state.tpm.adjust(delta, now)
                state.tpd.adjust(delta, now)
            return model, value

        if budget_blocked == len(ordered):
            raise self._open_circuit(ordered, tokens)
        raise RuntimeError(str(last_error) if last_error else "Groq request failed.")


def parse_retry_after(value: str | None) -> float | None:
    """Parse a ``retry-after`` header value in seconds (Groq sends plain seconds)."""
    if not value:
        return None
    try:
        seconds = float(str(value).strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def is_daily_limit_body(body: str) -> bool:
    text = (body or "").lower()
    return "per day" in text or "(rpd)" in text or "(tpd)" in text
