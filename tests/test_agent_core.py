"""Plan-act-check loop: max tool calls, daily cap and timeout (fake model, no network)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import agent_core as ac
import agent_tools as at
from tests.fakes import FakeChannel, FakeGuild, FakeMember, ModLogRecorder, is_moderator

ROOT = Path(__file__).resolve().parent.parent


def run(coro):
    return asyncio.run(coro)


class ScriptedModel:
    """Fake completion function: returns scripted replies, records every prompt."""

    def __init__(self, replies=None, default=None, delay=0.0):
        self.replies = list(replies or [])
        self.default = default
        self.delay = delay
        self.calls: list[list[dict]] = []

    async def __call__(self, messages):
        self.calls.append(messages)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.replies:
            return self.replies.pop(0)
        return self.default


def tool_call(name, **args):
    return json.dumps({"thought": "plan", "tool": name, "args": args})


def final(text):
    return json.dumps({"thought": "done", "final": text})


def make_runner(model, *, limits=None, usage=None):
    guild = FakeGuild()
    channel = FakeChannel(10, guild)
    author = FakeMember(1, guild, "asker")
    FakeMember(2, guild, "target")
    executed: list[str] = []

    async def lookup(ctx, args):
        executed.append("lookup")
        return {"warns": 2}

    async def warn(ctx, args):
        executed.append("warn")
        return "warned"

    registry = at.ToolRegistry(is_moderator=is_moderator)
    registry.register(at.AgentTool("lookup", "Look up", (), at.READ_ONLY, lookup))
    registry.register(
        at.AgentTool("warn", "Warn", (at.ArgSpec("member", "member", "m"), at.ArgSpec("reason", "str", "r")),
                     at.CONSEQUENTIAL, warn)
    )
    pending = at.PendingActionManager(is_moderator=is_moderator, mod_log=ModLogRecorder())
    runner = ac.AgentRunner(registry=registry, pending=pending, complete=model, limits=limits, usage=usage)
    ctx = at.AgentContext(guild=guild, channel=channel, author=author)
    return runner, ctx, executed


def test_plan_act_check_then_final():
    model = ScriptedModel([tool_call("lookup"), final("They have 2 warnings.")])
    runner, ctx, executed = make_runner(model)
    result = run(runner.run("how many warns?", ctx))
    assert result.status == "ok"
    assert result.reply == "They have 2 warnings."
    assert executed == ["lookup"]
    assert len(result.tool_calls) == 1 and result.model_calls == 2
    # CHECK step: the second prompt carries the tool observation, marked untrusted.
    last = model.calls[1][-1]["content"]
    assert last.startswith("Tool result (untrusted data):") and '"warns": 2' in last
    # The system prompt lists the registry tools with their permission levels.
    system = model.calls[0][0]["content"]
    assert '"name": "warn"' in system and '"permission": "consequential"' in system


def test_loop_stops_after_max_tool_calls():
    model = ScriptedModel(default=tool_call("lookup"))
    runner, ctx, executed = make_runner(model)
    result = run(runner.run("loop forever", ctx))
    assert result.status == "max_steps"
    assert len(result.tool_calls) == 5 and executed == ["lookup"] * 5
    assert result.model_calls == 6  # 5 tool turns + 1 forced final turn, no 6th tool call
    assert "limit of 5 tool calls" in result.reply
    assert "Tool budget used up" in model.calls[-1][-1]["content"]


def test_max_tool_calls_is_configurable():
    model = ScriptedModel(default=tool_call("lookup"))
    runner, ctx, executed = make_runner(model, limits=ac.AgentLimits(max_tool_calls=2))
    result = run(runner.run("x", ctx))
    assert result.status == "max_steps" and len(executed) == 2


def test_consequential_call_in_loop_only_creates_pending_action():
    model = ScriptedModel([tool_call("warn", member="<@2>", reason="spam"), final("Awaiting a moderator.")])
    runner, ctx, executed = make_runner(model)
    result = run(runner.run("warn them", ctx))
    assert executed == []
    assert [a.status for a in result.pending_actions] == [at.PENDING]


def test_unknown_tool_is_reported_back_to_model():
    model = ScriptedModel([tool_call("rm_rf"), final("sorry")])
    runner, ctx, _ = make_runner(model)
    result = run(runner.run("x", ctx))
    assert result.status == "ok" and not result.tool_calls[0].ok
    assert "Unknown tool" in model.calls[1][-1]["content"]


def test_prose_reply_is_treated_as_final():
    model = ScriptedModel(["Sure, here is a plain answer."])
    runner, ctx, _ = make_runner(model)
    result = run(runner.run("x", ctx))
    assert result.status == "ok" and result.reply == "Sure, here is a plain answer."


def test_parse_decision_tolerates_fences_and_prose():
    raw = 'Thinking...\n```json\n{"thought": "a", "tool": "lookup", "args": {}}\n```'
    assert ac.parse_decision(raw)["tool"] == "lookup"
    assert ac.parse_decision('{"unrelated": 1} then {"final": "ok"}') == {"final": "ok"}
    assert ac.parse_decision("no json here") is None


def test_daily_cap_per_user():
    day = {"key": "2026-11-05"}
    usage = ac.DailyUsage(2, day_key=lambda: day["key"])
    model = ScriptedModel(default=final("hi"))
    runner, ctx, _ = make_runner(model, usage=usage)
    assert run(runner.run("1", ctx)).status == "ok"
    assert run(runner.run("2", ctx)).status == "ok"
    capped = run(runner.run("3", ctx))
    assert capped.status == "daily_cap" and "all 2 agent requests" in capped.reply
    assert len(model.calls) == 2  # no model call once capped

    other = at.AgentContext(guild=ctx.guild, channel=ctx.channel, author=FakeMember(77, ctx.guild))
    assert run(runner.run("other user", other)).status == "ok"

    day["key"] = "2026-11-06"
    assert run(runner.run("next day", ctx)).status == "ok"


def test_daily_cap_env_default_and_override():
    assert ac.load_agent_limits({}).daily_cap == 20
    assert ac.load_agent_limits({"AGENT_DAILY_CAP": "3"}).daily_cap == 3
    assert ac.load_agent_limits({"AGENT_DAILY_CAP": "junk"}).daily_cap == 20
    limits = ac.load_agent_limits({})
    assert limits.max_tool_calls == 5 and limits.timeout_seconds == 60.0


def test_overall_timeout():
    model = ScriptedModel(default=tool_call("lookup"), delay=0.05)
    runner, ctx, _ = make_runner(model, limits=ac.AgentLimits(timeout_seconds=0.12))
    result = run(runner.run("slow", ctx))
    assert result.status == "timeout"
    assert "ran out of time" in result.reply
    assert 1 <= len(result.tool_calls) < 5


def test_timeout_keeps_pending_actions_created_so_far():
    model = ScriptedModel([tool_call("warn", member="2", reason="spam")], default=final("x"), delay=0.05)
    runner, ctx, _ = make_runner(model, limits=ac.AgentLimits(timeout_seconds=0.08))
    result = run(runner.run("warn then hang", ctx))
    assert result.status == "timeout"
    assert len(result.pending_actions) == 1


def test_bot_wires_agent_to_existing_completion_path():
    source = (ROOT / "bot.py").read_text(encoding="utf-8-sig")
    start = source.index("async def _agent_complete(")
    body = source[start : source.index("\n\n\n", start)]
    assert "request_ai_completion(" in body and "session.post" not in body
    assert '@bot.command(name="agent")' in source
    # Replies and cards go only to the invoking channel, through the safety screen.
    cmd = source[source.index("async def agent_command(") :]
    cmd = cmd[: cmd.index("\n\n\n")]
    assert "screen_agent_text(" in cmd
    assert "ctx.channel.send(" in cmd and "ctx.author.send(" not in cmd
    # Confirmations reuse the bot's moderator check and mod-log.
    assert "PendingActionManager(is_moderator=is_moderator, mod_log=send_mod_log)" in source
