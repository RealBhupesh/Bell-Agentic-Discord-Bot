"""Phase 4: the rebuilt Crush-o-Meter game.

Fake Discord objects, synthetic made-up inputs, a real budget governor with a
fake day; no network and no discord import.
"""

from __future__ import annotations

import ast
import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import crush_game as cg
from groq_budget import GroqBudgetGovernor
from tests.fakes import FakeChannel, FakeGuild, FakeMember

ROOT = Path(__file__).resolve().parent.parent
T0 = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


def bot_source() -> str:
    return (ROOT / "bot.py").read_text(encoding="utf-8-sig")


def crush_section() -> str:
    source = bot_source()
    start = source.index("# Crush-o-Meter game (phase 4)")
    end = source.index('AGENTIC_STATE_FILE = DATA_DIR / "agentic_state.json"')
    return source[start:end]


class FailingChannel(FakeChannel):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fail = True

    async def send(self, content: str, **kwargs) -> None:
        if self.fail:
            raise RuntimeError("missing permissions")
        await super().send(content, **kwargs)


class SpyMember(FakeMember):
    """A member whose every attribute read (other than identity/name) is recorded."""

    SAFE = {"id", "display_name", "name", "guild", "mention", "guild_permissions", "bot", "_reads", "__class__", "__dict__"}

    def __init__(self, *args, **kwargs) -> None:
        object.__setattr__(self, "_reads", [])
        super().__init__(*args, **kwargs)

    def __getattribute__(self, item):
        if not item.startswith("__") and item not in SpyMember.SAFE:
            object.__getattribute__(self, "_reads").append(item)
        return object.__getattribute__(self, item)

    async def history(self, *args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("history() must never be read")


class Setup:
    def __init__(self, cap: int = 100, flavor=None) -> None:
        self.day = ["2026-11-05"]
        self.governor = GroqBudgetGovernor(feature_caps={cg.FEATURE: cap}, day_key=lambda: self.day[0])
        self.now = T0
        self.state = cg.CrushGameState()
        self.game = cg.CrushGame(
            state=self.state,
            admit_feature=self.governor.try_admit_feature,
            prefix="&",
            flavor=flavor,
            now=lambda: self.now,
        )
        self.guild = FakeGuild(1000)
        self.channel = FakeChannel(10, self.guild, "fun")
        self.alice = FakeMember(1, self.guild, "Alice")
        self.bob = FakeMember(2, self.guild, "Bob")
        self.carol = FakeMember(3, self.guild, "Carol")

    def enable(self) -> None:
        run(self.game.enable(self.guild.id, self.channel))

    def play(self, invoker, partner=None, answer=None) -> str:
        return run(self.game.play(self.guild, invoker, partner, answer=answer))


# -- voluntary invocation ---------------------------------------------------------


def test_self_invocation_works():
    s = Setup()
    s.enable()
    result = s.play(s.alice, answer="pizza and lo-fi beats")
    assert "Crush-o-Meter" in result and "Alice" in result
    assert re.search(r"\d+%", result)
    assert "fictional match" in result
    assert result.rstrip().endswith(cg.DISCLAIMER)
    assert s.governor.feature_usage(cg.FEATURE) == 1


def test_self_invocation_without_answer_offers_fun_prompt():
    s = Setup()
    s.enable()
    result = s.play(s.alice)
    assert cg.FUN_PROMPT in result
    assert cg.LABEL_MYSTERY in result


def test_naming_another_member_is_a_labelled_random_pairing():
    s = Setup()
    s.enable()
    result = s.play(s.alice, s.bob, answer="tacos")
    assert "Random pairing with **Bob**" in result
    assert "pure dice roll" in result and "nothing about Bob was looked at" in result
    assert cg.DISCLAIMER in result


def test_no_join_or_opt_in_command_exists():
    assert "crushjoin" not in bot_source()
    assert "crushjoin" not in (ROOT / "crush_game.py").read_text(encoding="utf-8")
    assert not hasattr(cg.CrushGame, "join")


def test_game_disabled_by_default_and_does_not_consume_budget():
    s = Setup()
    assert s.play(s.alice) == s.game.disabled_text()
    assert s.governor.feature_usage(cg.FEATURE) == 0


# -- no analysis of a target member ------------------------------------------------


def test_no_code_path_analyzes_a_target_members_messages():
    """Crush results never come from a target member's messages or activity."""
    tree = ast.parse((ROOT / "crush_game.py").read_text(encoding="utf-8"))
    attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for forbidden in ("history", "fetch_message", "fetch_messages", "messages", "activity",
                      "activities", "last_message", "create_dm", "dm_channel", "channels"):
        assert forbidden not in attrs, forbidden
    assert "discord" not in names
    # The module has no hook that receives server messages at all.
    assert not hasattr(cg.CrushGame, "record_message")
    assert not any(n.startswith("index_") for n in dir(cg))

    section = crush_section()
    for forbidden in (".history(", "fetch_message", "CRUSH_GAME.record", "member.activity", "DMChannel", "create_dm"):
        assert forbidden not in section, forbidden
    # Nothing in the passive message pipeline feeds the game.
    on_message = bot_source().split("async def on_message(", 1)[1].split("\nasync def ", 1)[0]
    assert "CRUSH_GAME" not in on_message and "crush_game" not in on_message
    # A pointed-at message is only used if the invoker wrote it.
    assert "pointed_input(ctx.author.id, resolved.author.id, resolved.content)" in section


def test_target_member_is_only_used_for_identity_and_name():
    s = Setup()
    s.enable()
    spy = SpyMember(42, s.guild, "Dana")
    result = s.play(s.alice, spy, answer="ramen")
    assert spy._reads == []  # no messages, activity, roles, history... were touched
    assert "Dana" in result


def test_pairing_result_ignores_anything_about_the_target():
    a, b = Setup(), Setup()
    for s in (a, b):
        s.enable()
    # In b, Bob has "said" lots of things in the made-up world; it must not matter.
    b.bob.messages = ["I love Alice!!!"] * 50
    b.bob.activity = "chatting with Alice"
    assert a.play(a.alice, a.bob, answer="tea") == b.play(b.alice, b.bob, answer="tea")


def test_pointed_message_is_used_only_if_the_invoker_wrote_it():
    assert cg.pointed_input(1, 1, "MY OWN MESSAGE WOW") == "MY OWN MESSAGE WOW"
    assert cg.pointed_input(1, 2, "someone else's words") == ""
    assert cg.pointed_input(1, None, "no author") == ""


def test_answer_mentions_are_stripped():
    assert "<@2>" not in cg.clean_answer("I pick <@2> and <@!3> lol")


# -- exclusion -------------------------------------------------------------------------


def test_excluded_member_cannot_be_named():
    s = Setup()
    s.enable()
    s.game.exclude(s.guild.id, s.bob.id)
    result = s.play(s.alice, s.bob)
    assert result == s.game.excluded_text()
    assert "Bob" not in result
    assert s.governor.feature_usage(cg.FEATURE) == 0


def test_excluded_member_cannot_play():
    s = Setup()
    s.enable()
    s.game.exclude(s.guild.id, s.alice.id)
    assert s.play(s.alice) == s.game.excluded_text()


def test_excluded_member_is_never_named_even_by_flavor_text():
    async def flavor(prompt: str) -> str:
        assert "Bob" not in prompt
        return "Bob would totally approve of this chaos."

    s = Setup(flavor=flavor)
    s.enable()
    s.game.exclude(s.guild.id, s.bob.id)
    for day in range(20):
        s.now = T0 + timedelta(days=day)
        for invoker, partner in ((s.alice, None), (s.alice, s.carol), (s.carol, None)):
            result = s.play(invoker, partner, answer="nachos")
            assert "Bob" not in result
            assert cg.DISCLAIMER in result


def test_exclude_deletes_stored_data_and_works_when_game_is_off():
    s = Setup()
    s.enable()
    s.play(s.alice, answer="cookies")
    assert str(s.alice.id) in s.state.guild(s.guild.id)["answers"]
    s.game.disable(s.guild.id)
    s.game.exclude(s.guild.id, s.alice.id)
    assert str(s.alice.id) not in s.state.guild(s.guild.id)["answers"]
    assert s.game.is_excluded(s.guild.id, s.alice.id)
    s.game.include(s.guild.id, s.alice.id)
    assert not s.game.is_excluded(s.guild.id, s.alice.id)


def test_fun_commands_refuse_excluded_targets():
    source = bot_source()
    for fn in ("roast_command", "analyze_command", "vibe_command", "vibecheck_command",
               "lie_detector_command", "debate_command", "my_vibe_command"):
        body = source.split(f"async def {fn}(", 1)[1][:400]
        assert "refuse_fun_excluded(ctx," in body, fn


# -- wipe / data -----------------------------------------------------------------------


def test_wipe_deletes_stored_data():
    s = Setup()
    s.enable()
    s.play(s.alice, answer="WOW!!! 😀😀")
    s.play(s.bob, answer="soup")
    assert s.game.wipe(s.guild.id, s.alice.id) is True
    answers = s.state.guild(s.guild.id)["answers"]
    assert str(s.alice.id) not in answers
    assert str(s.bob.id) in answers  # only the caller's data
    assert s.game.wipe(s.guild.id, s.alice.id) is False


def test_stored_data_is_minimal():
    s = Setup()
    s.enable()
    s.play(s.alice, s.bob, answer="x" * 500)
    g = s.state.guild(s.guild.id)
    assert set(g) == {"enabled", "notice_posted", "notice_channel_id", "excluded", "answers"}
    assert list(g["answers"]) == [str(s.alice.id)]  # nothing stored about Bob
    assert len(g["answers"][str(s.alice.id)]) <= cg.ANSWER_MAX_CHARS


def test_saved_answer_is_reused_until_wiped():
    s = Setup()
    s.enable()
    first = s.play(s.alice, answer="WHY IS THE SKY BLUE?")
    again = s.play(s.alice)
    assert cg.STYLE_LABELS["caps"] in first and cg.STYLE_LABELS["caps"] in again
    s.game.wipe(s.guild.id, s.alice.id)
    assert cg.LABEL_MYSTERY in s.play(s.alice)


# -- notice ----------------------------------------------------------------------------


def test_notice_posts_once_on_enable():
    s = Setup()
    assert run(s.game.enable(s.guild.id, s.channel)) is True
    assert run(s.game.enable(s.guild.id, s.channel)) is False
    s.game.disable(s.guild.id)
    other = FakeChannel(11, s.guild, "general")
    assert run(s.game.enable(s.guild.id, other)) is False
    assert len(s.channel.sent) == 1 and other.sent == []
    notice = s.channel.sent[0]
    assert "`&exclude`" in notice and "`&wipe`" in notice
    assert "can read messages in server channels the bot can see" in notice


def test_notice_retries_if_first_send_failed():
    s = Setup()
    bad = FailingChannel(12, s.guild, "locked")
    try:
        run(s.game.enable(s.guild.id, bad))
    except RuntimeError:
        pass
    assert s.state.guild(s.guild.id)["notice_posted"] is False
    bad.fail = False
    assert run(s.game.enable(s.guild.id, bad)) is True
    assert len(bad.sent) == 1


# -- DMs / old path ----------------------------------------------------------------------


def test_no_code_path_reads_dms():
    source = (ROOT / "crush_game.py").read_text(encoding="utf-8")
    for forbidden in ("DMChannel", "create_dm", "dm_channel", "import discord"):
        assert forbidden not in source
    section = crush_section()
    for forbidden in ("DMChannel", "create_dm", "dm_channel", "ctx.author.send"):
        assert forbidden not in section
    # Every crush/exclude/wipe command is server-only.
    assert section.count("@commands.guild_only()") == 5


def test_old_history_mining_path_is_removed():
    source = bot_source()
    for gone in (
        'name="aicrush"',
        "index_aicrush_message",
        "run_aicrush_backfill",
        "collect_aicrush_interactions",
        "build_aicrush_directional_candidate_pool",
        "rerank_aicrush_candidates_with_ai",
        "detect_member_gender_from_roles",
        "setgenderroles",
    ):
        assert gone not in source, gone


def test_legacy_aicrush_file_is_purged(tmp_path):
    legacy = tmp_path / "aicrush_state.json"
    legacy.write_text('{"guilds": {"1": {"users": {"5": {"samples": ["made-up old text"]}}}}}', encoding="utf-8")
    missing = tmp_path / "aicrush_state.json.bak"
    assert cg.purge_legacy_files([legacy, missing]) == [str(legacy)]
    assert not legacy.exists()


# -- framing ----------------------------------------------------------------------------


def test_disclaimer_present_in_every_result():
    async def flavor(prompt: str) -> str:
        return "The dice have spoken and they demand snacks."

    for fl in (None, flavor):
        s = Setup(flavor=fl)
        s.enable()
        for day in range(10):
            s.now = T0 + timedelta(days=day)
            for invoker, partner, answer in (
                (s.alice, None, None), (s.alice, s.bob, "tea"), (s.carol, s.alice, "😀😀"), (s.bob, None, "HELLO THERE"),
            ):
                assert s.play(invoker, partner, answer).rstrip().endswith(cg.DISCLAIMER)
    lowered = cg.DISCLAIMER.lower()
    assert "joke" in lowered and "not anyone's real" in lowered and "orientation" in lowered


def test_romantic_or_orientation_flavor_is_dropped():
    async def flavor(prompt: str) -> str:
        return "Alice secretly likes Bob and is in love, judging by how she chats with him."

    s = Setup(flavor=flavor)
    s.enable()
    result = s.play(s.alice, s.bob)
    assert "secretly likes" not in result and "in love" not in result
    assert cg.DISCLAIMER in result


def test_flavor_failure_still_returns_a_result():
    async def flavor(prompt: str) -> str:
        raise RuntimeError("AI budget used up for today.")

    s = Setup(flavor=flavor)
    s.enable()
    assert cg.DISCLAIMER in s.play(s.alice)


# -- budget ------------------------------------------------------------------------------


def test_daily_cap_enforced_through_governor():
    s = Setup(cap=2)
    s.enable()
    assert cg.DISCLAIMER in s.play(s.alice)
    assert cg.DISCLAIMER in s.play(s.bob, s.alice)
    capped = s.play(s.carol)
    assert capped == s.game.cap_text()
    assert cg.DISCLAIMER not in capped and "Carol" not in capped
    assert s.governor.feature_usage(cg.FEATURE) == 2
    s.day[0] = "2026-11-06"  # a new UTC day resets the cap
    assert cg.DISCLAIMER in s.play(s.carol)


def test_refusals_do_not_consume_the_daily_cap():
    s = Setup(cap=1)
    s.enable()
    s.game.exclude(s.guild.id, s.bob.id)
    for _ in range(5):
        s.play(s.alice, s.bob)
    assert cg.DISCLAIMER in s.play(s.alice)


def test_bot_registers_a_default_daily_cap_for_the_feature():
    section = crush_section()
    assert "GROQ_BUDGET.feature_caps.setdefault(\n    crush_game.FEATURE" in section
    assert "admit_feature=GROQ_BUDGET.try_admit_feature" in section


def test_state_round_trips_through_json_shape():
    s = Setup()
    s.enable()
    s.play(s.alice, answer="dumplings")
    s.game.exclude(s.guild.id, s.bob.id)
    g = cg.CrushGameState(s.state.data).guild(s.guild.id)
    assert g["enabled"] and g["notice_posted"] and g["excluded"] == [s.bob.id]
    assert g["answers"][str(s.alice.id)] == "dumplings"
