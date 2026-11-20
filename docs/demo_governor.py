"""Offline demo of the Groq budget governor (no Discord, no network, no API key).

Run from the repository root:

    python docs/demo_governor.py

It uses made-up model names, a fake "attempt" that never calls Groq, and a
temporary counter file that is thrown away afterwards. It shows:

1. model fallback, then the daily budget running out;
2. a per-feature daily cap refusing work without a model call;
3. fail-closed persistence: a corrupt counter file blocks requests
   (QuotaPersistenceError) instead of silently resetting usage to zero.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import groq_budget as gb  # noqa: E402


async def fake_attempt(model: str) -> tuple[str, int]:
    return f"reply from {model}", 50  # (value, tokens used); no network call


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "groq_budget_state.json"
        gov = gb.GroqBudgetGovernor(
            default_limits=gb.ModelLimits(rpm=30, rpd=2, tpm=8000, tpd=200000),  # 2 requests/day per model
            feature_caps={"demo_capped": 1},
            state_path=state,
        )
        models = ["model-a", "model-b"]

        print("1) model fallback, then daily budget exhausted")
        for i in range(5):
            try:
                _, value = await gov.run(models, fake_attempt, feature="demo")
                print(f"   call {i + 1}: {value}")
            except gb.GroqBudgetError as error:
                print(f"   call {i + 1}: refused: {error}")

        print("2) per-feature daily cap (admission without a model call)")
        for i in range(2):
            print(f"   play {i + 1}: admitted={gov.try_admit_feature('demo_capped')}")

        print("3) fail closed: restart with a corrupt counter file")
        state.write_text("{not json", encoding="utf-8")
        restarted = gb.GroqBudgetGovernor(state_path=state)
        try:
            await restarted.run(models, fake_attempt, feature="demo")
        except gb.QuotaPersistenceError as error:
            print(f"   refused: {error}")


if __name__ == "__main__":
    asyncio.run(main())
