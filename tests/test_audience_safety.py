import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from tests.fakes import FakeChannel, FakeGuild, FakeMember, FakePerms


class AudienceChannel(FakeChannel):
    def __init__(self, channel_id, guild, viewers, readers):
        super().__init__(channel_id, guild)
        self.viewers = set(viewers)
        self.readers = set(readers)
        self.topic = "restricted topic"
        self.type = "text"
        self.history_calls = 0

    def permissions_for(self, member):
        return FakePerms(
            view_channel=member.id in self.viewers,
            read_message_history=member.id in self.readers,
        )

    async def history(self, *, limit):
        self.history_calls += 1
        field = SimpleNamespace(name="Details", value="restricted case")
        embed = SimpleNamespace(fields=[field])
        yield SimpleNamespace(embeds=[embed], created_at=datetime.now(timezone.utc))


def cached_message(channel, message_id, content):
    return SimpleNamespace(
        channel_id=channel.id,
        message_id=message_id,
        content=content,
        author_display_name="Test member",
        author_id=1,
        created_at_ts=float(message_id),
    )


@pytest.mark.parametrize("tool", ["channel_info", "modlog_tail", "search_messages"])
@pytest.mark.parametrize(
    ("viewers", "readers", "destination_viewers", "chunked", "allowed"),
    [
        ({1}, {1}, {1, 2}, True, False),
        ({1, 2}, {1}, {1, 2}, True, False),
        ({1}, {1}, {1}, True, True),
        ({1, 2}, {1, 2}, {1}, True, True),
        ({1}, {1}, {1}, False, False),
    ],
    ids=["wider", "history-denied", "equal", "narrower", "incomplete-cache"],
)
def test_agent_source_covers_destination(
    monkeypatch, tool, viewers, readers, destination_viewers, chunked, allowed
):
    import agent_tools
    import bot

    guild = FakeGuild()
    guild.chunked = chunked
    author = FakeMember(1, guild, manage_messages=True)
    FakeMember(2, guild)
    guild.members = list(guild.members.values())
    source = AudienceChannel(10, guild, viewers, readers)
    destination = AudienceChannel(11, guild, destination_viewers, destination_viewers)
    ctx = agent_tools.AgentContext(guild=guild, channel=destination, author=author)
    monkeypatch.setattr(bot.discord, "TextChannel", AudienceChannel)
    monkeypatch.setattr(bot, "get_guild_mod_log_channel_id", lambda _: source.id)
    monkeypatch.setattr(
        bot, "MESSAGE_WINDOW_CACHE",
        {source.id: (0, [cached_message(source, 20, "restricted message")])},
    )
    args = {
        "channel_info": {"channel": source.id},
        "modlog_tail": {"limit": 1},
        "search_messages": {"query": "restricted", "limit": 1},
    }
    result = asyncio.run(
        bot.AGENT_REGISTRY.invoke(tool, args[tool], ctx, bot.AGENT_PENDING)
    )
    if tool == "search_messages":
        assert result.ok
        matches = result.output["matches"]
        if allowed:
            assert [item["content"] for item in matches] == ["restricted message"]
            assert result.output["note"] is None
        else:
            assert matches == []
            assert "withheld" in result.output["note"]
            assert "audience" in result.output["note"]
    elif allowed:
        assert result.ok
        if tool == "channel_info":
            assert result.output["topic"] == "restricted topic"
        else:
            assert result.output["entries"][0]["Details"] == "restricted case"
            assert source.history_calls == 1
    else:
        assert not result.ok
        assert "audience" in result.error
        assert result.output is None
        assert source.history_calls == 0


def test_agent_search_withholds_restricted_entries_before_limiting(monkeypatch):
    import agent_tools
    import bot

    guild = FakeGuild()
    guild.chunked = True
    author = FakeMember(1, guild)
    FakeMember(2, guild)
    guild.members = list(guild.members.values())
    public = AudienceChannel(10, guild, {1, 2}, {1, 2})
    restricted = AudienceChannel(11, guild, {1}, {1})
    monkeypatch.setattr(
        bot, "MESSAGE_WINDOW_CACHE",
        {
            public.id: (0, [cached_message(public, 20, "match public")]),
            restricted.id: (0, [cached_message(restricted, 21, "match restricted")]),
        },
    )
    ctx = agent_tools.AgentContext(guild=guild, channel=public, author=author)
    result = asyncio.run(bot.AGENT_REGISTRY.invoke(
        "search_messages", {"query": "match", "limit": 1}, ctx, bot.AGENT_PENDING
    ))
    assert result.ok
    assert [item["content"] for item in result.output["matches"]] == ["match public"]
    assert "withheld" in result.output["note"]



@pytest.mark.parametrize("change", ["none", "requester", "audience", "error", "withheld"])
def test_agent_revalidates_at_reply_send(monkeypatch, change):
    from contextlib import asynccontextmanager

    import bot

    guild = FakeGuild()
    guild.chunked = True
    author = FakeMember(1, guild, manage_messages=True)
    FakeMember(2, guild)
    guild.get_member = guild.members.get
    guild.members = list(guild.members.values())
    readers = {1, 2} if change == "withheld" else {1}
    source = AudienceChannel(10, guild, readers, readers)
    destination = AudienceChannel(11, guild, readers, readers)
    unrelated = AudienceChannel(12, guild, {1}, {1})
    monkeypatch.setattr(bot, "is_ai_configured", lambda: True)
    monkeypatch.setattr(bot, "MESSAGE_WINDOW_CACHE", {
        source.id: (0, [cached_message(source, 20, "match shared text")]),
        unrelated.id: (0, [cached_message(unrelated, 21, "match withheld text")]),
    })

    async def run(request, agent_ctx):
        tool, args = (
            ("search_messages", {"query": "match", "limit": 5})
            if change == "withheld" else ("channel_info", {"channel": source.id})
        )
        result = await bot.AGENT_REGISTRY.invoke(tool, args, agent_ctx, bot.AGENT_PENDING)
        assert result.ok
        assert agent_ctx.source_channel_ids == {source.id}
        if change == "withheld":
            assert [row["content"] for row in result.output["matches"]] == ["match shared text"]
            assert "withheld" in result.output["note"]
            unrelated.readers.clear()
        elif change == "requester":
            source.readers.remove(author.id)
        elif change == "audience":
            destination.viewers.add(2)
        elif change == "error":
            def broken_permissions(_):
                raise RuntimeError("permission lookup failed")
            source.permissions_for = broken_permissions
        return SimpleNamespace(reply="Source-derived answer", pending_actions=[])

    @asynccontextmanager
    async def typing():
        yield

    monkeypatch.setattr(bot, "AGENT_RUNNER", SimpleNamespace(run=run))
    ctx = SimpleNamespace(guild=guild, channel=destination, author=author, typing=typing)
    asyncio.run(bot.agent_command.callback(ctx, request="Read the source"))
    if change in {"none", "withheld"}:
        assert destination.sent == ["Source-derived answer"]
    else:
        assert destination.sent == [bot.agent_tools.AGENT_ACCESS_CHANGED]


def test_agent_reply_rechecks_between_chunks(monkeypatch):
    import bot

    guild = FakeGuild()
    guild.chunked = True
    author = FakeMember(1, guild)
    FakeMember(2, guild)
    guild.get_member = guild.members.get
    guild.members = list(guild.members.values())
    source = AudienceChannel(10, guild, {1}, {1})
    destination = AudienceChannel(11, guild, {1}, {1})
    ctx = bot.agent_tools.AgentContext(guild=guild, channel=destination, author=author)
    original_send = destination.send

    async def send(content, **kwargs):
        await original_send(content, **kwargs)
        destination.viewers.add(2)

    monkeypatch.setattr(destination, "send", send)
    monkeypatch.setattr(bot, "split_message", lambda _: ["first", "second"])

    async def run():
        await bot._agent_channel_info(ctx, {"channel": source})
        assert not await bot._agent_send_reply(ctx, "Source-derived answer")

    asyncio.run(run())
    assert destination.sent == ["first", bot.agent_tools.AGENT_ACCESS_CHANGED]


def test_agent_delayed_followup_revalidates_original_requester(monkeypatch):
    import bot
    from tests.fakes import ModLogRecorder

    guild = FakeGuild()
    guild.chunked = True
    author = FakeMember(1, guild)
    moderator = FakeMember(2, guild, manage_messages=True)
    guild.get_member = guild.members.get
    guild.members = list(guild.members.values())
    source = AudienceChannel(10, guild, {1, 2}, {1, 2})
    destination = AudienceChannel(11, guild, {1, 2}, {1, 2})
    destination.permissions_for = lambda _: FakePerms(
        view_channel=True, read_message_history=True, send_messages=True
    )
    pending = bot.agent_tools.PendingActionManager(
        is_moderator=bot.is_moderator, mod_log=ModLogRecorder()
    )
    ctx = bot.agent_tools.AgentContext(guild=guild, channel=destination, author=author)
    monkeypatch.setattr(bot, "AGENT_FOLLOWUP_TASKS", set())

    async def run():
        release = asyncio.Event()

        async def wait(_seconds):
            await release.wait()

        monkeypatch.setattr(bot.asyncio, "sleep", wait)
        await bot._agent_channel_info(ctx, {"channel": source})
        result = await bot.AGENT_REGISTRY.invoke(
            "schedule_followup", {"minutes": 1, "text": "Source-derived note"}, ctx, pending
        )
        decision = await pending.confirm(result.pending_action.id, moderator)
        assert decision.ok
        task, = bot.AGENT_FOLLOWUP_TASKS
        source.readers.remove(author.id)
        release.set()
        await task

    asyncio.run(run())
    assert destination.sent == [bot.agent_tools.AGENT_ACCESS_CHANGED]



def test_scheduled_agent_reply_revalidates_before_post(monkeypatch):
    import json

    import bot
    from tests.fakes import ModLogRecorder

    guild = FakeGuild()
    guild.chunked = True
    guild.me = FakeMember(1, guild)
    FakeMember(2, guild)
    guild.get_member = guild.members.get
    guild.members = list(guild.members.values())
    source = AudienceChannel(10, guild, {1}, {1})
    destination = AudienceChannel(11, guild, {1}, {1})
    pending = bot.agent_tools.PendingActionManager(
        is_moderator=bot.is_moderator, mod_log=ModLogRecorder()
    )
    calls = 0

    async def complete(messages):
        nonlocal calls
        calls += 1
        if calls == 1:
            return json.dumps({"tool": "channel_info", "args": {"channel": source.id}})
        assert "restricted topic" in messages[-1]["content"]
        destination.viewers.add(2)
        return json.dumps({"final": "Source-derived digest"})

    async def unexpected_post(*args):
        pytest.fail("Used the post callback without access to invocation provenance")

    scheduler = bot.agentic_automation.ScheduledTaskScheduler(
        state=bot.agentic_automation.AgenticState(), registry=bot.AGENT_REGISTRY,
        pending=pending, complete=complete, post=unexpected_post,
        post_card=unexpected_post, post_reply=bot._agent_send_reply,
    )
    task = bot.agentic_automation.parse_task({
        "name": "digest", "schedule": "@daily", "channel_id": destination.id,
        "prompt": "Read the source", "enabled": True,
    })
    report = asyncio.run(scheduler.run_task(guild, task))
    assert calls == 2
    assert destination.sent == [bot.agent_tools.AGENT_ACCESS_CHANGED]
    assert report.reply == bot.agent_tools.AGENT_ACCESS_CHANGED
