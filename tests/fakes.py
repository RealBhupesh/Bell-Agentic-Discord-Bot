"""Minimal stand-ins for discord.py objects used by the agent tests (no discord import)."""

from __future__ import annotations

from typing import Any


class FakePerms:
    def __init__(self, **flags: bool) -> None:
        self.administrator = False
        self.manage_messages = False
        self.moderate_members = False
        self.kick_members = False
        self.ban_members = False
        self.manage_channels = False
        for name, value in flags.items():
            setattr(self, name, value)


class FakeGuild:
    def __init__(self, guild_id: int = 1000, name: str = "Test Guild") -> None:
        self.id = guild_id
        self.name = name
        self.members: dict[int, FakeMember] = {}
        self.channels: dict[int, FakeChannel] = {}

    def get_member(self, member_id: int) -> "FakeMember | None":
        return self.members.get(member_id)

    def get_channel(self, channel_id: int) -> "FakeChannel | None":
        return self.channels.get(channel_id)


class FakeMember:
    def __init__(self, member_id: int, guild: FakeGuild, name: str = "user", **perms: bool) -> None:
        self.id = member_id
        self.name = name
        self.display_name = name
        self.guild = guild
        self.guild_permissions = FakePerms(**perms)
        self.mention = f"<@{member_id}>"
        guild.members[member_id] = self

    def __str__(self) -> str:
        return self.name


class FakeChannel:
    def __init__(self, channel_id: int, guild: FakeGuild, name: str = "general") -> None:
        self.id = channel_id
        self.name = name
        self.guild = guild
        self.mention = f"<#{channel_id}>"
        self.sent: list[str] = []
        guild.channels[channel_id] = self

    async def send(self, content: str, **_: Any) -> None:
        self.sent.append(content)


def is_moderator(member: Any) -> bool:
    """Same rule as bot.is_moderator."""
    perms = member.guild_permissions
    return bool(
        perms.administrator
        or perms.manage_messages
        or perms.moderate_members
        or perms.kick_members
        or perms.ban_members
        or perms.manage_channels
    )


class ModLogRecorder:
    """Records calls made with bot.send_mod_log's signature."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def __call__(self, guild: Any, action: str, **kwargs: Any) -> None:
        self.entries.append({"guild": guild, "action": action, **kwargs})


class FakeResponse:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bool]] = []
        self.edited: list[str] = []
        self.deferred = False

    async def send_message(self, content: str, *, ephemeral: bool = False) -> None:
        self.sent.append((content, ephemeral))

    async def edit_message(self, *, content: str, view: Any = None) -> None:
        self.edited.append(content)

    async def defer(self) -> None:
        self.deferred = True


class FakeInteraction:
    def __init__(self, user: FakeMember) -> None:
        self.user = user
        self.response = FakeResponse()
        self.original_edits: list[str] = []

    async def edit_original_response(self, *, content: str, view: Any = None) -> None:
        self.original_edits.append(content)
