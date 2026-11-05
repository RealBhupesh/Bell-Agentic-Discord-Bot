"""Phase 3 agentic automation: scheduler, escalation proposals, engagement nudges.

Fake model, fake Discord objects and a fake clock; no network.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import agent_tools as at
import agentic_automation as aa
from groq_budget import GroqBudgetGovernor
from tests.fakes import FakeChannel, FakeGuild, FakeInteraction, FakeMember, ModLogRecorder, is_moderator

ROOT = Path(__file__).resolve().parent.parent
T0 = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)  # a Thursday


def run(coro):
    return asyncio.run(coro)


class FakeClock:
    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def ts(self) -> float:
        return self.now.timestamp()

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


class ScriptedModel:
    def __init__(self, replies=None, default=None):
        self.replies = list(replies or [])
        self.default = default if default is not None else json.dumps({"final": "done"})
        self.calls = []

    async def __call__(self, messages):
        self.calls.append(messages)
        return self.replies.pop(0) if self.replies else self.default


def tool_call(name, **args):
    return json.dumps({"thought": "plan", "tool": name, "args": args})


def final(text):
    return json.dumps({"thought": "done", "final": text})


class Poster:
    def __init__(self):
        self.messages = []
        self.cards = []

    async def post(self, channel, text):
        self.messages.append((channel.id, text))

    async def post_card(self, channel, action):
        self.cards.append((channel.id, action))


def make_world():
    guild = FakeGuild()
    bot_member = FakeMember(999, guild, "bell", administrator=True)
    guild.me = bot_member
    channel = FakeChannel(10, guild, "general")
    mod_channel = FakeChannel(20, guild, "mod-log")
    return guild, channel, mod_channel


def agentic_config(**sections):
    return aa.parse_agentic_config(sections)


# ---------------------------------------------------------------------------
# Defaults: everything off when config is absent
# ---------------------------------------------------------------------------


def test_missing_config_is_all_off():
    for raw in (None, {}, {"agentic": None}, "garbage", {"scheduled_tasks": {}, "escalation": {}, "nudges": {}}):
        cfg = aa.parse_agentic_config(raw)
        assert cfg.scheduled_enabled is False
        assert cfg.escalation.enabled is False
        assert cfg.nudges.enabled is False
    assert aa.config_for_guild({}, 1) == aa.AgenticConfig()
    assert aa.config_for_guild({"1": {"automod_enabled": True}}, 1) == aa.AgenticConfig()
    task = aa.parse_task({"name": "digest", "schedule": "@daily", "channel_id": 10, "prompt": "x"})
    assert task is not None and task.enabled is False  # tasks default to disabled


def test_everything_noops_without_config():
    guild, channel, mod_channel = make_world()
    clock = FakeClock(T0.replace(hour=0, minute=0))
    state = aa.AgenticState()
    model = ScriptedModel()
    poster = Poster()
    pending = at.PendingActionManager(is_moderator=is_moderator, mod_log=ModLogRecorder())
    registry = at.ToolRegistry(is_moderator=is_moderator)
    cfg = aa.AgenticConfig()

    scheduler = aa.ScheduledTaskScheduler(state=state, registry=registry, pending=pending, complete=model,
                                          post=poster.post, post_card=poster.post_card, now=clock)
    assert run(scheduler.tick(guild, cfg)) == []

    escalation = aa.EscalationMonitor(state=state, pending=pending, post_card=poster.post_card,
                                      case_history=_no_history, complete=model,
                                      resolve_mod_channel=lambda g: mod_channel, clock=clock.ts)
    member = FakeMember(5, guild, "spammer")
    for _ in range(10):
        assert run(escalation.on_violation(guild, member, cfg)) is None

    admitted = []
    nudges = aa.NudgeEngine(state=state, admit_feature=lambda f: admitted.append(f) or True,
                            send=_never_send, now=clock)
    nudges.set_opt_in(guild.id, 5, True)
    cands = [aa.NudgeCandidate(5, "streak", "hi")]
    assert run(nudges.tick(guild, cfg, cands, channel)) == 0

    assert model.calls == [] and poster.messages == [] and poster.cards == [] and admitted == []
    assert state.guild(guild.id)["violations"] == {}


async def _no_history(guild, member):
    return []


async def _never_send(channel, member_id, text):
    raise AssertionError("must not send")


# ---------------------------------------------------------------------------
# Cron
# ---------------------------------------------------------------------------


def test_cron_matching():
    daily = aa.CronSchedule("@daily")
    assert daily.matches(T0.replace(hour=0, minute=0))
    assert not daily.matches(T0.replace(hour=0, minute=1))
    weekly = aa.CronSchedule("30 18 * * 5")  # Fridays 18:30
    friday = datetime(2026, 11, 6, 18, 30, tzinfo=timezone.utc)
    assert weekly.matches(friday)
    assert not weekly.matches(friday - timedelta(days=1))
    every15 = aa.CronSchedule("*/15 9-10 * * 1-5")
    assert every15.matches(T0.replace(minute=45))
    assert not every15.matches(T0.replace(minute=50))
    assert aa.CronSchedule("0 0 * * 7").matches(datetime(2026, 11, 8, 0, 0, tzinfo=timezone.utc))  # Sunday
    for bad in ("", "* * *", "60 * * * *", "* 24 * * *", "*/0 * * * *", "a b c d e"):
        with pytest.raises(ValueError):
            aa.CronSchedule(bad)


# ---------------------------------------------------------------------------
# 1. Scheduled tasks
# ---------------------------------------------------------------------------


def make_scheduler(model, clock, state=None):
    guild, channel, mod_channel = make_world()
    target = FakeMember(2, guild, "target")
    executed = []

    async def lookup(ctx, args):
        executed.append("lookup")
        return {"members": 2}

    async def timeout(ctx, args):
        executed.append("timeout")
        return "timed out"

    registry = at.ToolRegistry(is_moderator=is_moderator)
    registry.register(at.AgentTool("server_stats", "Stats", (), at.READ_ONLY, lookup))
    registry.register(at.AgentTool(
        "timeout", "Timeout",
        (at.ArgSpec("member", "member", "m"), at.ArgSpec("minutes", "int", "n", minimum=1)),
        at.CONSEQUENTIAL, timeout, required_permission="moderate_members"))
    mod_log = ModLogRecorder()
    pending = at.PendingActionManager(is_moderator=is_moderator, mod_log=mod_log)
    poster = Poster()
    scheduler = aa.ScheduledTaskScheduler(
        state=state or aa.AgenticState(), registry=registry, pending=pending, complete=model,
        post=poster.post, post_card=poster.post_card, now=clock)
    return scheduler, guild, channel, poster, executed, pending, target


def tasks_config(*tasks, enabled=True):
    return agentic_config(scheduled_tasks={"enabled": enabled, "tasks": list(tasks)})


DIGEST = {"name": "digest", "schedule": "0 9 * * *", "channel_id": 10, "prompt": "Post a server digest.",
          "enabled": True}
RECAP_OFF = {"name": "recap", "schedule": "0 9 * * *", "channel_id": 10, "prompt": "Weekly recap.",
             "enabled": False}


def test_scheduler_fires_enabled_task_and_skips_disabled():
    clock = FakeClock(T0)
    model = ScriptedModel([tool_call("server_stats"), final("Digest: 2 members.")])
    scheduler, guild, channel, poster, executed, _, _ = make_scheduler(model, clock)
    cfg = tasks_config(DIGEST, RECAP_OFF)

    reports = run(scheduler.tick(guild, cfg))
    assert [r.task for r in reports] == ["digest"]
    assert reports[0].status == "ok"
    assert executed == ["lookup"]
    assert poster.messages == [(10, "**Scheduled task: digest**\nDigest: 2 members.")]
    assert "Post a server digest." in model.calls[0][1]["content"]
    assert "recap" not in json.dumps([m for call in model.calls for m in call])

    # Same minute again: does not fire twice. Off-schedule minute: does not fire.
    assert run(scheduler.tick(guild, cfg)) == []
    clock.advance(minutes=1)
    assert run(scheduler.tick(guild, cfg)) == []
    # Next day at 09:00 it fires again.
    clock.now = T0 + timedelta(days=1)
    assert [r.task for r in run(scheduler.tick(guild, cfg))] == ["digest"]


def test_scheduler_section_disabled_skips_everything():
    clock = FakeClock(T0)
    model = ScriptedModel()
    scheduler, guild, *_ = make_scheduler(model, clock)
    assert run(scheduler.tick(guild, tasks_config(DIGEST, enabled=False))) == []
    assert model.calls == []


def test_scheduled_run_cannot_execute_consequential_tools():
    clock = FakeClock(T0)
    model = ScriptedModel([tool_call("timeout", member="<@2>", minutes=10), final("Proposed a timeout.")])
    scheduler, guild, channel, poster, executed, pending, target = make_scheduler(model, clock)

    reports = run(scheduler.tick(guild, tasks_config(DIGEST)))
    assert executed == []  # the timeout handler never ran
    [action] = reports[0].pending_actions
    assert action.status == at.PENDING
    assert action.tool.name == "timeout"
    assert poster.cards == [(10, action)]  # surfaced as a Confirm card
    assert action.ctx.extras["scheduled_task"] == "digest"

    # The bot itself (the scheduled run's author) still needs a human: only a
    # moderator with the right permission can confirm.
    plain = FakeMember(3, guild, "plain")
    denied = run(pending.confirm(action.id, plain))
    assert not denied.ok and executed == []
    mod = FakeMember(4, guild, "mod", moderate_members=True)
    assert run(pending.confirm(action.id, mod)).ok
    assert executed == ["timeout"]


def test_scheduled_task_daily_call_cap():
    clock = FakeClock(T0)
    # A model that keeps calling tools: each step is one model call.
    model = ScriptedModel(default=tool_call("server_stats"))
    task = dict(DIGEST, schedule="* * * * *", daily_cap=3)
    scheduler, guild, *_ = make_scheduler(model, clock)
    cfg = tasks_config(task)

    first = run(scheduler.tick(guild, cfg))[0]
    assert first.status == "error" and "daily call cap" in first.reply
    assert len(model.calls) == 3
    clock.advance(minutes=1)
    second = run(scheduler.tick(guild, cfg))[0]
    assert second.status == "daily_cap"
    assert len(model.calls) == 3  # no further model calls today
    assert scheduler.calls_today(guild.id, "digest") == 3

    clock.now = T0 + timedelta(days=1)
    run(scheduler.tick(guild, cfg))
    assert len(model.calls) == 6  # cap resets at the UTC day boundary


def test_scheduled_task_without_channel_does_not_call_model():
    clock = FakeClock(T0)
    model = ScriptedModel()
    scheduler, guild, *_ = make_scheduler(model, clock)
    report = run(scheduler.tick(guild, tasks_config(dict(DIGEST, channel_id=12345))))[0]
    assert report.status == "no_channel" and model.calls == []


# ---------------------------------------------------------------------------
# 2. Escalation proposals
# ---------------------------------------------------------------------------


def make_escalation(clock, model=None, history=None):
    guild, channel, mod_channel = make_world()
    member = FakeMember(5, guild, "spammer")
    mod_log = ModLogRecorder()
    pending = at.PendingActionManager(is_moderator=is_moderator, mod_log=mod_log, ttl_seconds=10**9)
    poster = Poster()
    seen_history = []

    async def case_history(g, m):
        seen_history.append(m.id)
        return list(history or [])

    monitor = aa.EscalationMonitor(state=aa.AgenticState(), pending=pending, post_card=poster.post_card,
                                   case_history=case_history, complete=model,
                                   resolve_mod_channel=lambda g: mod_channel, clock=clock.ts)
    return monitor, guild, member, poster, pending, mod_log, seen_history


ESC_ON = agentic_config(escalation={"enabled": True})


def test_escalation_posts_once_per_member_per_day_at_threshold():
    clock = FakeClock()
    model = ScriptedModel(default=json.dumps(
        {"recommendation": "timeout", "minutes": 30, "rationale": "Repeated spam."}))
    monitor, guild, member, poster, pending, mod_log, seen = make_escalation(clock, model)

    assert run(monitor.on_violation(guild, member, ESC_ON)) is None
    clock.advance(minutes=5)
    assert run(monitor.on_violation(guild, member, ESC_ON)) is None
    assert poster.cards == [] and model.calls == []
    clock.advance(minutes=5)
    action = run(monitor.on_violation(guild, member, ESC_ON))  # 3rd violation = default threshold
    assert action is not None and poster.cards == [(20, action)]
    assert action.tool is aa.ESCALATION_TOOL and action.tool.consequential
    assert action.args["recommendation"] == "timeout" and action.args["minutes"] == 30
    assert action.status == at.PENDING and seen == [member.id]

    # More violations the same day: no second proposal, no extra model calls.
    for _ in range(5):
        clock.advance(minutes=10)
        assert run(monitor.on_violation(guild, member, ESC_ON)) is None
    assert len(poster.cards) == 1 and len(model.calls) == 1

    # Another member is tracked independently.
    other = FakeMember(6, guild, "other")
    for _ in range(3):
        run(monitor.on_violation(guild, other, ESC_ON))
    assert len(poster.cards) == 2

    # After 24h the member can get a new proposal (once they hit the threshold again).
    clock.advance(hours=25)
    results = [run(monitor.on_violation(guild, member, ESC_ON)) for _ in range(3)]
    assert results[:2] == [None, None] and results[2] is not None
    assert len(poster.cards) == 3


def test_escalation_never_executes_moderation():
    clock = FakeClock()
    model = ScriptedModel(default=json.dumps({"recommendation": "ban", "rationale": "Persistent abuse."}))
    monitor, guild, member, poster, pending, mod_log, _ = make_escalation(clock, model)
    member.timeouts = []
    member.banned = False
    for _ in range(3):
        action = run(monitor.on_violation(guild, member, ESC_ON))
    assert action.status == at.PENDING
    assert mod_log.entries == []

    # Even a moderator's Confirm only acknowledges it; nothing is applied.
    mod = FakeMember(4, guild, "mod", moderate_members=True)
    interaction = FakeInteraction(mod)
    decision = run(pending.handle_interaction(interaction, action.id, confirm=True))
    assert decision.ok
    assert "Nothing was applied automatically" in action.result
    assert member.timeouts == [] and member.banned is False
    assert [e["action"] for e in mod_log.entries] == ["Agent: Escalation Acknowledged"]


def test_escalation_falls_back_to_heuristic_and_reads_history_only():
    clock = FakeClock()

    async def broken(messages):
        raise RuntimeError("model down")

    history = ["Warning: spam (2026-11-01)", "Warning: links (2026-11-02)", "Warning: abuse (2026-11-03)"]
    monitor, guild, member, poster, *_ = make_escalation(clock, broken, history)
    for _ in range(3):
        action = run(monitor.on_violation(guild, member, ESC_ON))
    assert action.args["recommendation"] == "timeout"  # 3 violations + 3 warnings = 2x threshold
    assert aa.parse_recommendation('{"recommendation": "nuke"}') is None
    assert aa.parse_recommendation('x {"recommendation": "watch", "rationale": "ok"}')["recommendation"] == "watch"


def test_escalation_threshold_and_window_from_config():
    clock = FakeClock()
    monitor, guild, member, poster, *_ = make_escalation(clock)
    cfg = agentic_config(escalation={"enabled": True, "threshold": 2, "window_hours": 1})
    run(monitor.on_violation(guild, member, cfg))
    clock.advance(hours=2)  # first violation leaves the window
    assert run(monitor.on_violation(guild, member, cfg)) is None
    clock.advance(minutes=1)
    assert run(monitor.on_violation(guild, member, cfg)) is not None


def test_escalation_without_mod_channel_does_nothing():
    clock = FakeClock()
    monitor, guild, member, poster, *_ = make_escalation(clock)
    monitor.resolve_mod_channel = lambda g: None
    for _ in range(5):
        assert run(monitor.on_violation(guild, member, ESC_ON)) is None
    assert poster.cards == []


# ---------------------------------------------------------------------------
# 3. Engagement nudges
# ---------------------------------------------------------------------------


class NudgeSink:
    def __init__(self):
        self.sent = []

    async def __call__(self, channel, member_id, text):
        self.sent.append((member_id, text))
        return True


def make_nudges(clock, feature_cap=100):
    guild, channel, _ = make_world()
    governor = GroqBudgetGovernor(feature_caps={aa.FEATURE_NUDGE: feature_cap}, day_key=lambda: aa.day_key(clock()))
    sink = NudgeSink()
    engine = aa.NudgeEngine(state=aa.AgenticState(), admit_feature=governor.try_admit_feature, send=sink, now=clock)
    return engine, guild, channel, sink, governor


def nudge_cfg(**overrides):
    return agentic_config(nudges={"enabled": True, **overrides})


def test_nudges_once_per_member_per_day():
    clock = FakeClock()
    engine, guild, channel, sink, governor = make_nudges(clock)
    for uid in (1, 2):
        engine.set_opt_in(guild.id, uid, True)
    cands = [aa.NudgeCandidate(1, "streak", "s"), aa.NudgeCandidate(1, "quest", "q"),
             aa.NudgeCandidate(2, "quest", "q"), aa.NudgeCandidate(3, "streak", "not opted in")]
    assert run(engine.tick(guild, nudge_cfg(), cands, channel)) == 2
    assert sink.sent == [(1, "s"), (2, "q")]
    clock.advance(hours=3)
    assert run(engine.tick(guild, nudge_cfg(), cands, channel)) == 0
    assert governor.feature_usage(aa.FEATURE_NUDGE) == 2
    clock.advance(days=1)
    assert run(engine.tick(guild, nudge_cfg(), cands, channel)) == 2


def test_nudges_respect_server_daily_cap():
    clock = FakeClock()
    engine, guild, channel, sink, _ = make_nudges(clock)
    for uid in range(1, 11):
        engine.set_opt_in(guild.id, uid, True)
    cands = [aa.NudgeCandidate(uid, "streak", "s") for uid in range(1, 11)]
    cfg = nudge_cfg(server_daily_cap=3)
    assert run(engine.tick(guild, cfg, cands, channel)) == 3
    clock.advance(hours=1)
    assert run(engine.tick(guild, cfg, cands, channel)) == 0
    assert engine.sent_today(guild.id) == 3
    clock.advance(days=1)
    assert run(engine.tick(guild, cfg, cands, channel)) == 3
    assert [m for m, _ in sink.sent] == [1, 2, 3, 1, 2, 3]  # new day: caps reset


def test_nudges_respect_governor_feature_cap():
    clock = FakeClock()
    engine, guild, channel, sink, governor = make_nudges(clock, feature_cap=2)
    for uid in range(1, 6):
        engine.set_opt_in(guild.id, uid, True)
    cands = [aa.NudgeCandidate(uid, "streak", "s") for uid in range(1, 6)]
    assert run(engine.tick(guild, nudge_cfg(server_daily_cap=50), cands, channel)) == 2
    assert governor.try_admit_feature(aa.FEATURE_NUDGE) is False


def test_nudge_kinds_and_opt_out():
    clock = FakeClock()
    engine, guild, channel, sink, _ = make_nudges(clock)
    engine.set_opt_in(guild.id, 1, True)
    engine.set_opt_in(guild.id, 2, True)
    engine.set_opt_in(guild.id, 2, False)
    cands = [aa.NudgeCandidate(1, "streak", "s"), aa.NudgeCandidate(1, "quest", "q"), aa.NudgeCandidate(2, "quest", "q")]
    assert run(engine.tick(guild, nudge_cfg(streaks=False), cands, channel)) == 1
    assert sink.sent == [(1, "q")]


def test_build_nudge_candidates():
    today = "2026-11-05"
    day_of = lambda ts: datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    yesterday = (T0 - timedelta(days=1)).timestamp()
    users = {
        "1": {"streak": 4, "last_active_ts": yesterday},  # streak at risk
        "2": {"streak": 4, "last_active_ts": T0.timestamp()},  # already active today
        "3": {"streak": 0, "last_active_ts": yesterday},  # no streak
        "4": {"streak": 9, "last_active_ts": yesterday},  # not opted in
    }
    cands = aa.build_nudge_candidates(users, opted_in=[1, 2, 3], today=today, day_of=day_of,
                                      open_quests=lambda uid: 2 if uid == 3 else 0)
    assert [(c.member_id, c.kind) for c in cands] == [(1, "streak"), (3, "quest")]
    assert "4-day streak" in cands[0].text


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_bot_wiring():
    source = (ROOT / "bot.py").read_text(encoding="utf-8-sig")
    assert "import agentic_automation" in source
    assert "await agentic_on_automod_violation(message, action, reason)" in source
    assert "agentic_tick_loop.start()" in source
    assert "admit_feature=GROQ_BUDGET.try_admit_feature" in source
    # Scheduled runs reuse the same registry and pending-action manager as &agent.
    assert "registry=AGENT_REGISTRY,\n    pending=AGENT_PENDING,\n    complete=_agentic_complete" in source


def test_governor_try_admit_feature_uncapped_by_default():
    gov = GroqBudgetGovernor()
    assert all(gov.try_admit_feature("anything") for _ in range(5))
    assert gov.feature_usage("anything") == 5
