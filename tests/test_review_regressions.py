import asyncio
from types import SimpleNamespace

import pytest

from tests.fakes import FakeChannel, FakeGuild, FakeMember, FakePerms


@pytest.mark.parametrize("tool", ["channel_info", "modlog_tail", "search_messages"])
def test_agent_source_channel_permissions(monkeypatch, tool):
    import agent_tools
    import bot

    guild = FakeGuild()
    member = FakeMember(1, guild, manage_messages=True)
    source = FakeChannel(2, guild)
    source.permissions_for = lambda _: FakePerms(
        view_channel=tool == "search_messages", read_message_history=False
    )
    ctx = agent_tools.AgentContext(guild=guild, channel=source, author=member)
    monkeypatch.setattr(bot.discord, "TextChannel", FakeChannel)
    monkeypatch.setattr(bot, "get_guild_mod_log_channel_id", lambda _: source.id)
    cached = SimpleNamespace(message_id=3, channel_id=source.id, content="private")
    monkeypatch.setattr(bot, "MESSAGE_WINDOW_CACHE", {source.id: (0, [cached])})
    args = {
        "channel_info": {"channel": source.id},
        "modlog_tail": {"limit": 1},
        "search_messages": {"query": "private", "limit": 1},
    }
    result = asyncio.run(
        bot.AGENT_REGISTRY.invoke(tool, args[tool], ctx, bot.AGENT_PENDING)
    )
    if tool == "search_messages":
        assert result.ok and result.output["matches"] == []
        assert "channels you can view and read" in result.output["note"]
    else:
        assert not result.ok and "cannot view" in result.error


def test_save_mod_config_does_not_publish_failed_write(monkeypatch):
    import bot

    old = {"1000": {"self_wipe_enabled": True}}
    monkeypatch.setattr(bot, "MOD_CONFIG_CACHE", old)
    monkeypatch.setattr(bot, "MOD_CONFIG_CACHE_TS", bot.time.monotonic())
    monkeypatch.setattr(bot, "ensure_data_files", lambda: None)
    monkeypatch.setattr(bot, "STORAGE", SimpleNamespace(set=lambda *_: False))
    proposed = bot.load_mod_config()
    proposed["1000"]["self_wipe_enabled"] = False
    with pytest.raises(bot.commands.CommandError, match="not saved"):
        bot.save_mod_config(proposed)
    assert bot.load_mod_config() == {"1000": {"self_wipe_enabled": True}}


@pytest.mark.parametrize(
    ("audit_ok", "revoke", "expected"),
    [
        (True, False, ["audit", "delete", "result"]),
        (False, False, ["audit"]),
        (True, True, ["audit"]),
    ],
)
def test_wipe_audits_and_rechecks_permissions_before_delete(
    monkeypatch, audit_ok, revoke, expected
):
    import bot

    guild = FakeGuild()
    guild.owner_id = 99
    actor = FakeMember(10, guild, manage_messages=True)
    target = FakeMember(11, guild)
    actor.top_role, target.top_role = 2, 1
    channel = FakeChannel(20, guild)
    guild.get_channel_or_thread = guild.get_channel
    allowed = True
    events, summaries = [], []
    channel.permissions_for = lambda _: FakePerms(
        view_channel=True, read_message_history=True, manage_messages=allowed
    )

    async def collect(*args, **kwargs):
        return [channel], []

    async def scan(job, channels, **kwargs):
        job.matches.append(
            bot.message_wipe.WipeMatch(channel.id, 30, bot.discord.utils.utcnow())
        )

    class Confirm:
        def __init__(self, *_):
            self.confirmed = True

        async def wait(self):
            nonlocal allowed
            allowed = not revoke

    async def log(guild, action, **kwargs):
        events.append("audit" if action.endswith("confirmed") else "result")
        return audit_ok

    async def delete(job, channels, **kwargs):
        events.append("delete")
        job.deleted = 1
        job.phase = "done"

    async def edit(**kwargs):
        summaries.append(kwargs["embed"])

    async def send(*args, **kwargs):
        return SimpleNamespace(id=40, edit=edit)

    monkeypatch.setattr(bot.discord, "Member", FakeMember)
    monkeypatch.setattr(bot, "WIPE_JOBS", {})
    monkeypatch.setattr(bot, "collect_wipe_channels", collect)
    monkeypatch.setattr(bot, "WipeStopView", lambda *_: None)
    monkeypatch.setattr(bot, "WipeConfirmView", Confirm)
    monkeypatch.setattr(bot, "send_mod_log", log)
    monkeypatch.setattr(bot.message_wipe, "scan_channels", scan)
    monkeypatch.setattr(bot.message_wipe, "delete_matches", delete)
    ctx = SimpleNamespace(
        guild=guild, author=actor, channel=channel, interaction=None,
        message=None, send=send,
    )
    asyncio.run(bot.run_message_wipe(ctx, target, "all", "", self_service=False))
    assert events == expected
    assert bot.WIPE_JOBS == {}
    if not audit_ok:
        assert any("Could not write the confirmation" in f.value for f in summaries[-1].fields)
    elif revoke:
        assert any("no longer has permission" in f.value for f in summaries[-1].fields)



@pytest.mark.parametrize("tool", ["lock_channel", "timeout"])
def test_agent_confirmation_checks_target_permissions(monkeypatch, tool):
    import agent_tools
    import bot

    guild = FakeGuild()
    guild.owner_id = 99
    actor = FakeMember(1, guild, manage_channels=True, moderate_members=True)
    target = FakeMember(2, guild)
    actor.top_role, target.top_role = 1, 2
    channel = FakeChannel(3, guild)
    channel.permissions_for = lambda _: FakePerms(view_channel=True)

    async def unexpected(*args, **kwargs):
        pytest.fail("Unauthorized action reached Discord")

    target.timeout = unexpected
    monkeypatch.setattr(bot, "set_channel_send_locked", unexpected)
    ctx = agent_tools.AgentContext(guild=guild, channel=channel, author=actor)
    pending = agent_tools.PendingActionManager(
        is_moderator=bot.is_moderator, mod_log=_ignore_log
    )
    args = {"reason": "test"}
    args.update({"member": target.id, "minutes": 1} if tool == "timeout" else {})
    result = asyncio.run(bot.AGENT_REGISTRY.invoke(tool, args, ctx, pending))
    assert result.ok and result.pending_action is not None
    decision = asyncio.run(pending.confirm(result.pending_action.id, actor))
    assert not decision.ok
    expected = "top role" if tool == "timeout" else "manage_channels"
    assert expected in decision.message


async def _ignore_log(*args, **kwargs):
    pass
