"""Registry permission gating, pending-action confirm/cancel flow and mod-log writes."""

from __future__ import annotations

import asyncio

import pytest

import agent_tools as at
from tests.fakes import (
    FakeChannel,
    FakeGuild,
    FakeInteraction,
    FakeMember,
    ModLogRecorder,
    is_moderator,
)


def run(coro):
    return asyncio.run(coro)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def env():
    guild = FakeGuild()
    channel = FakeChannel(10, guild)
    requester = FakeMember(1, guild, "requester")
    target = FakeMember(2, guild, "target")
    helper = FakeMember(3, guild, "helper", manage_messages=True)  # moderator, no moderate_members
    mod = FakeMember(4, guild, "mod", moderate_members=True, manage_messages=True)
    calls: dict[str, list] = {"lookup": [], "warn": [], "timeout": []}

    async def lookup(ctx, args):
        calls["lookup"].append(args)
        return {"id": args["member"].id}

    async def warn(ctx, args):
        calls["warn"].append((ctx.actor.id, args))
        return f"warned {args['member'].mention}"

    async def timeout(ctx, args):
        calls["timeout"].append((ctx.actor.id, args))
        return "timed out"

    registry = at.ToolRegistry(is_moderator=is_moderator)
    member_arg = at.ArgSpec("member", "member", "who")
    reason_arg = at.ArgSpec("reason", "str", "why", max_length=50)
    registry.register(at.AgentTool("member_info", "info", (member_arg,), at.READ_ONLY, lookup))
    registry.register(
        at.AgentTool("warn_count", "warns", (member_arg,), at.READ_ONLY, lookup, requires_moderator=True)
    )
    registry.register(
        at.AgentTool(
            "warn", "warn", (member_arg, reason_arg), at.CONSEQUENTIAL, warn,
            required_permission="manage_messages", modlog_action="Warn",
        )
    )
    registry.register(
        at.AgentTool(
            "timeout", "timeout",
            (member_arg, at.ArgSpec("minutes", "int", "m", minimum=1, maximum=60), reason_arg),
            at.CONSEQUENTIAL, timeout, required_permission="moderate_members", modlog_action="Mute",
            validate=lambda ctx, args: "blocked text" if "badword" in args["reason"] else None,
        )
    )
    modlog = ModLogRecorder()
    clock = Clock()
    pending = at.PendingActionManager(is_moderator=is_moderator, mod_log=modlog, ttl_seconds=600, clock=clock)
    ctx = at.AgentContext(guild=guild, channel=channel, author=requester)
    return {
        "guild": guild, "channel": channel, "requester": requester, "target": target, "helper": helper,
        "mod": mod, "registry": registry, "pending": pending, "modlog": modlog, "calls": calls,
        "ctx": ctx, "clock": clock,
    }


def propose_timeout(env, minutes=5, reason="spam"):
    result = run(
        env["registry"].invoke(
            "timeout", {"member": "<@2>", "minutes": minutes, "reason": reason}, env["ctx"], env["pending"]
        )
    )
    assert result.ok, result.error
    return result.pending_action


# ---------------------------------------------------------------------------
# Registry permission gating
# ---------------------------------------------------------------------------


def test_tool_spec_has_name_description_args_and_permission(env):
    spec = {tool["name"]: tool for tool in env["registry"].prompt_spec()}
    assert spec["member_info"]["permission"] == at.READ_ONLY
    assert spec["warn"]["permission"] == at.CONSEQUENTIAL
    assert spec["timeout"]["args"]["minutes"] == {
        "type": "int", "description": "m", "required": True, "min": 1, "max": 60,
    }
    with pytest.raises(ValueError):
        at.AgentTool("x", "d", (), "superuser", env["calls"].get)
    with pytest.raises(ValueError):
        env["registry"].register(at.AgentTool("warn", "dup", (), at.READ_ONLY, env["calls"].get))


def test_read_only_tool_runs_immediately(env):
    result = run(env["registry"].invoke("member_info", {"member": "2"}, env["ctx"], env["pending"]))
    assert result.ok and result.output == {"id": 2}
    assert result.pending_action is None
    assert len(env["calls"]["lookup"]) == 1


def test_consequential_tool_never_executes_directly(env):
    result = run(
        env["registry"].invoke("warn", {"member": "<@!2>", "reason": "rude"}, env["ctx"], env["pending"])
    )
    assert result.ok
    assert env["calls"]["warn"] == []  # handler not called
    action = result.pending_action
    assert action is not None and action.status == at.PENDING
    assert action.args["member"] is env["target"]
    assert result.to_observation()["status"] == "awaiting_moderator_confirmation"
    assert env["modlog"].entries == []


def test_moderator_only_lookup_is_gated(env):
    result = run(env["registry"].invoke("warn_count", {"member": "2"}, env["ctx"], env["pending"]))
    assert not result.ok and "moderators" in result.error
    mod_ctx = at.AgentContext(guild=env["guild"], channel=env["channel"], author=env["mod"])
    result = run(env["registry"].invoke("warn_count", {"member": "2"}, mod_ctx, env["pending"]))
    assert result.ok


@pytest.mark.parametrize(
    "name,args,fragment",
    [
        ("nope", {}, "Unknown tool"),
        ("member_info", {}, "Missing required"),
        ("member_info", {"member": "999999"}, "not found"),
        ("member_info", {"member": "2", "extra": 1}, "Unknown argument"),
        ("timeout", {"member": "2", "minutes": "0", "reason": "x"}, "at least 1"),
        ("timeout", {"member": "2", "minutes": "abc", "reason": "x"}, "integer"),
        ("timeout", {"member": "2", "minutes": 5, "reason": "x" * 51}, "longer than"),
        ("timeout", {"member": "2", "minutes": 5, "reason": "a badword"}, "blocked text"),
    ],
)
def test_invalid_calls_are_rejected_without_side_effects(env, name, args, fragment):
    result = run(env["registry"].invoke(name, args, env["ctx"], env["pending"]))
    assert not result.ok and fragment in result.error
    assert result.pending_action is None
    assert env["calls"]["timeout"] == [] and env["calls"]["lookup"] == []


def test_read_only_handler_errors_are_reported_not_raised(env):
    async def boom(ctx, args):
        raise RuntimeError("discord down")

    env["registry"].register(at.AgentTool("boom", "d", (), at.READ_ONLY, boom))
    result = run(env["registry"].invoke("boom", {}, env["ctx"], env["pending"]))
    assert not result.ok and "discord down" in result.error


# ---------------------------------------------------------------------------
# Confirm / cancel flow
# ---------------------------------------------------------------------------


def test_non_moderator_cannot_confirm(env):
    action = propose_timeout(env)
    decision = run(env["pending"].confirm(action.id, env["requester"]))
    assert not decision.ok and "Only moderators" in decision.message
    assert action.status == at.PENDING
    assert env["calls"]["timeout"] == []


def test_moderator_without_tool_permission_cannot_confirm(env):
    action = propose_timeout(env)
    decision = run(env["pending"].confirm(action.id, env["helper"]))  # manage_messages only
    assert not decision.ok and "moderate_members" in decision.message
    assert env["calls"]["timeout"] == []


def test_moderator_confirms_once(env):
    action = propose_timeout(env)
    decision = run(env["pending"].confirm(action.id, env["mod"]))
    assert decision.ok
    assert action.status == at.CONFIRMED and action.resolved_by == env["mod"].id
    assert env["calls"]["timeout"] == [(env["mod"].id, action.args)]
    again = run(env["pending"].confirm(action.id, env["mod"]))
    assert not again.ok and "already confirmed" in again.message
    assert len(env["calls"]["timeout"]) == 1


def test_concurrent_confirms_execute_once(env):
    action = propose_timeout(env)

    async def both():
        return await asyncio.gather(
            env["pending"].confirm(action.id, env["mod"]), env["pending"].confirm(action.id, env["mod"])
        )

    results = run(both())
    assert sorted(d.ok for d in results) == [False, True]
    assert len(env["calls"]["timeout"]) == 1


def test_requester_can_cancel_but_bystander_cannot(env):
    bystander = FakeMember(9, env["guild"], "bystander")
    action = propose_timeout(env)
    denied = run(env["pending"].cancel(action.id, bystander))
    assert not denied.ok and action.status == at.PENDING
    ok = run(env["pending"].cancel(action.id, env["requester"]))
    assert ok.ok and action.status == at.CANCELLED
    late = run(env["pending"].confirm(action.id, env["mod"]))
    assert not late.ok and "cancelled" in late.message
    assert env["calls"]["timeout"] == []
    assert env["modlog"].entries == []


def test_moderator_can_cancel(env):
    action = propose_timeout(env)
    assert run(env["pending"].cancel(action.id, env["helper"])).ok


def test_pending_action_expires(env):
    action = propose_timeout(env)
    env["clock"].now = 601
    decision = run(env["pending"].confirm(action.id, env["mod"]))
    assert not decision.ok and "expired" in decision.message
    assert env["calls"]["timeout"] == []


def test_confirm_from_other_guild_is_rejected(env):
    other = FakeMember(4, FakeGuild(guild_id=2000), "mod-elsewhere", administrator=True)
    action = propose_timeout(env)
    decision = run(env["pending"].confirm(action.id, other))
    assert not decision.ok and "different server" in decision.message


def test_interaction_denial_is_ephemeral_and_confirm_edits_card(env):
    action = propose_timeout(env)
    denied = FakeInteraction(env["requester"])
    run(env["pending"].handle_interaction(denied, action.id, confirm=True))
    assert denied.response.sent and denied.response.sent[0][1] is True
    assert action.status == at.PENDING

    allowed = FakeInteraction(env["mod"])
    run(env["pending"].handle_interaction(allowed, action.id, confirm=True))
    assert allowed.response.deferred
    assert "Confirmed by <@4>" in allowed.original_edits[-1]

    action2 = propose_timeout(env)
    cancel = FakeInteraction(env["requester"])
    run(env["pending"].handle_interaction(cancel, action2.id, confirm=False))
    assert "Cancelled by <@1>" in cancel.response.edited[-1]


# ---------------------------------------------------------------------------
# Mod-log writes
# ---------------------------------------------------------------------------


def test_confirmed_execution_is_written_to_modlog(env):
    action = propose_timeout(env, minutes=7, reason="spamming links")
    run(env["pending"].confirm(action.id, env["mod"]))
    assert len(env["modlog"].entries) == 1
    entry = env["modlog"].entries[0]
    assert entry["guild"] is env["guild"]
    assert entry["action"] == "Agent: Mute"
    assert entry["target"] is env["target"]
    assert entry["moderator"] is env["mod"]
    assert entry["reason"] == "spamming links"
    assert entry["channel"] is env["channel"]
    assert f"#{action.id}" in entry["details"] and "Requested by" in entry["details"]


def test_failed_execution_is_also_logged(env):
    async def broken(ctx, args):
        raise at.ToolError("Missing Permissions")

    env["registry"].register(
        at.AgentTool("lock_channel", "lock", (at.ArgSpec("channel", "channel", "c", required=False),),
                     at.CONSEQUENTIAL, broken, modlog_action="Lock Channel")
    )
    result = run(env["registry"].invoke("lock_channel", {}, env["ctx"], env["pending"]))
    assert result.pending_action.args["channel"] is env["channel"]  # defaults to invoking channel
    decision = run(env["pending"].confirm(result.pending_action.id, env["mod"]))
    assert not decision.ok and result.pending_action.status == at.FAILED
    assert env["modlog"].entries[0]["action"] == "Agent: Lock Channel (failed)"
    assert "Missing Permissions" in env["modlog"].entries[0]["details"]


def test_modlog_failure_does_not_break_confirmation(env):
    async def bad_log(*args, **kwargs):
        raise RuntimeError("log channel gone")

    pending = at.PendingActionManager(is_moderator=is_moderator, mod_log=bad_log)
    result = run(env["registry"].invoke("warn", {"member": "2", "reason": "x"}, env["ctx"], pending))
    assert run(pending.confirm(result.pending_action.id, env["mod"])).ok
