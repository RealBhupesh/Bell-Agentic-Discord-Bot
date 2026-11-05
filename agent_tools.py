"""Tool registry for the ``&agent`` command.

Each tool has a name, description, argument spec, permission level and an
async handler. Handlers are thin adapters onto functions that already exist in
``bot.py``; bot.py builds the registry and injects them, so this module has no
dependency on bot.py and does not import discord at module level (tests run
without discord installed).

Permission levels:

* ``READ_ONLY`` tools run immediately when the agent calls them.
* ``CONSEQUENTIAL`` tools never run from the agent loop. Calling one creates a
  :class:`PendingAction`; bot.py posts it as a card with Confirm / Cancel
  buttons and only a member who passes the bot's moderator check (plus the
  tool's own Discord permission, if declared) can confirm it. Every confirmed
  execution is written to the mod-log.
"""

from __future__ import annotations

import itertools
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping

READ_ONLY = "read_only"
CONSEQUENTIAL = "consequential"
PERMISSION_LEVELS = (READ_ONLY, CONSEQUENTIAL)

ARG_TYPES = ("str", "int", "member", "channel")

_ID_PATTERN = re.compile(r"^<?[@#]?[!&]?(\d{1,25})>?$")


class ToolError(Exception):
    """Raised for invalid arguments or a handler failure; the message is shown to the model/user."""


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArgSpec:
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    minimum: int | None = None
    maximum: int | None = None
    max_length: int | None = None

    def __post_init__(self) -> None:
        if self.type not in ARG_TYPES:
            raise ValueError(f"Unknown arg type `{self.type}` for `{self.name}`.")

    def to_prompt(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type, "description": self.description, "required": self.required}
        if self.minimum is not None:
            out["min"] = self.minimum
        if self.maximum is not None:
            out["max"] = self.maximum
        if self.max_length is not None:
            out["max_length"] = self.max_length
        return out


@dataclass
class AgentContext:
    """Where and for whom the agent is running.

    ``author`` is the member who invoked ``&agent``. ``actor`` is set to the
    confirming moderator when a consequential action executes.
    """

    guild: Any
    channel: Any
    author: Any
    actor: Any = None
    extras: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[AgentContext, dict[str, Any]], Awaitable[Any]]
Validator = Callable[[AgentContext, dict[str, Any]], "str | None"]


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    args: tuple[ArgSpec, ...]
    permission: str
    handler: Handler
    # Discord permission attribute the confirming moderator must also hold
    # (e.g. "moderate_members"), on top of the bot's is_moderator check.
    required_permission: str | None = None
    # Read-only tools that expose moderation data are limited to moderators.
    requires_moderator: bool = False
    modlog_action: str = ""
    # Extra pre-proposal check (e.g. safety screening of text); returns an error or None.
    validate: Validator | None = None

    def __post_init__(self) -> None:
        if self.permission not in PERMISSION_LEVELS:
            raise ValueError(f"Unknown permission level `{self.permission}` for `{self.name}`.")

    @property
    def consequential(self) -> bool:
        return self.permission == CONSEQUENTIAL

    def to_prompt(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "permission": self.permission,
            "args": {spec.name: spec.to_prompt() for spec in self.args},
        }


@dataclass
class ToolResult:
    tool: str
    ok: bool
    output: Any = None
    error: str | None = None
    pending_action: "PendingAction | None" = None

    def to_observation(self) -> dict[str, Any]:
        if not self.ok:
            return {"tool": self.tool, "ok": False, "error": self.error}
        data: dict[str, Any] = {"tool": self.tool, "ok": True, "result": self.output}
        if self.pending_action is not None:
            data["pending_action_id"] = self.pending_action.id
            data["status"] = "awaiting_moderator_confirmation"
        return data


# ---------------------------------------------------------------------------
# Argument coercion
# ---------------------------------------------------------------------------


def parse_snowflake(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    match = _ID_PATTERN.match(str(value or "").strip())
    return int(match.group(1)) if match else None


def _coerce(spec: ArgSpec, value: Any, ctx: AgentContext) -> Any:
    if spec.type == "str":
        text = str(value).strip()
        if not text and spec.required:
            raise ToolError(f"`{spec.name}` must not be empty.")
        if spec.max_length is not None and len(text) > spec.max_length:
            raise ToolError(f"`{spec.name}` is longer than {spec.max_length} characters.")
        return text
    if spec.type == "int":
        if isinstance(value, bool):
            raise ToolError(f"`{spec.name}` must be an integer.")
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            raise ToolError(f"`{spec.name}` must be an integer.") from None
        if spec.minimum is not None and number < spec.minimum:
            raise ToolError(f"`{spec.name}` must be at least {spec.minimum}.")
        if spec.maximum is not None and number > spec.maximum:
            raise ToolError(f"`{spec.name}` must be at most {spec.maximum}.")
        return number
    snowflake = parse_snowflake(value)
    if snowflake is None:
        raise ToolError(f"`{spec.name}` must be a {spec.type} mention or ID.")
    if spec.type == "member":
        member = ctx.guild.get_member(snowflake)
        if member is None:
            raise ToolError(f"Member `{snowflake}` was not found in this server.")
        return member
    channel = ctx.guild.get_channel(snowflake)
    if channel is None:
        raise ToolError(f"Channel `{snowflake}` was not found in this server.")
    return channel


def validate_args(tool: AgentTool, raw: Mapping[str, Any] | None, ctx: AgentContext) -> dict[str, Any]:
    raw = dict(raw or {})
    known = {spec.name for spec in tool.args}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ToolError(f"Unknown argument(s) for `{tool.name}`: {', '.join(unknown)}.")
    args: dict[str, Any] = {}
    for spec in tool.args:
        value = raw.get(spec.name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if spec.required:
                raise ToolError(f"Missing required argument `{spec.name}` for `{tool.name}`.")
            if spec.type == "channel" and spec.default is None:
                args[spec.name] = ctx.channel
            else:
                args[spec.name] = spec.default
            continue
        args[spec.name] = _coerce(spec, value, ctx)
    return args


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


IsModeratorFn = Callable[[Any], bool]


def member_has_permission(member: Any, permission: str | None) -> bool:
    if not permission:
        return True
    perms = getattr(member, "guild_permissions", None)
    if perms is None:
        return False
    return bool(getattr(perms, "administrator", False) or getattr(perms, permission, False))


class ToolRegistry:
    def __init__(self, *, is_moderator: IsModeratorFn) -> None:
        self._tools: dict[str, AgentTool] = {}
        self._is_moderator = is_moderator

    def register(self, tool: AgentTool) -> AgentTool:
        if tool.name in self._tools:
            raise ValueError(f"Tool `{tool.name}` is already registered.")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get((name or "").strip())

    def names(self) -> list[str]:
        return list(self._tools)

    def tools(self) -> list[AgentTool]:
        return list(self._tools.values())

    def prompt_spec(self) -> list[dict[str, Any]]:
        return [tool.to_prompt() for tool in self._tools.values()]

    def is_moderator(self, member: Any) -> bool:
        try:
            return bool(self._is_moderator(member))
        except Exception:
            return False

    async def invoke(
        self,
        name: str,
        raw_args: Mapping[str, Any] | None,
        ctx: AgentContext,
        pending: "PendingActionManager",
    ) -> ToolResult:
        """Run a read-only tool, or turn a consequential one into a pending action."""
        tool = self.get(name)
        if tool is None:
            return ToolResult(tool=str(name), ok=False, error=f"Unknown tool `{name}`.")
        try:
            args = validate_args(tool, raw_args, ctx)
        except ToolError as error:
            return ToolResult(tool=tool.name, ok=False, error=str(error))
        if tool.requires_moderator and not self.is_moderator(ctx.author):
            return ToolResult(tool=tool.name, ok=False, error="This lookup is limited to moderators.")
        if tool.validate is not None:
            problem = tool.validate(ctx, args)
            if problem:
                return ToolResult(tool=tool.name, ok=False, error=problem)

        if tool.consequential:
            action = pending.propose(tool, args, ctx)
            return ToolResult(
                tool=tool.name,
                ok=True,
                output=f"Proposed as pending action #{action.id}: {action.summary}. "
                "It will only run if a moderator presses Confirm.",
                pending_action=action,
            )

        try:
            output = await tool.handler(ctx, args)
        except ToolError as error:
            return ToolResult(tool=tool.name, ok=False, error=str(error))
        except Exception as error:  # handler bug or Discord error: report, never crash the loop
            return ToolResult(tool=tool.name, ok=False, error=f"{type(error).__name__}: {error}")
        return ToolResult(tool=tool.name, ok=True, output=output)


# ---------------------------------------------------------------------------
# Pending actions (consequential tools)
# ---------------------------------------------------------------------------

PENDING = "pending"
EXECUTING = "executing"
CONFIRMED = "confirmed"
FAILED = "failed"
CANCELLED = "cancelled"
EXPIRED = "expired"


def _describe_value(value: Any) -> str:
    mention = getattr(value, "mention", None)
    if isinstance(mention, str):
        return mention
    return str(value)


def describe_action(tool: AgentTool, args: Mapping[str, Any]) -> str:
    parts = [f"{key}={_describe_value(value)}" for key, value in args.items() if value is not None]
    return f"{tool.name}({', '.join(parts)})"


@dataclass
class PendingAction:
    id: int
    tool: AgentTool
    args: dict[str, Any]
    ctx: AgentContext
    created_at: float
    summary: str
    status: str = PENDING
    resolved_by: int | None = None
    result: str | None = None

    @property
    def requester_id(self) -> int:
        return int(getattr(self.ctx.author, "id", 0))

    @property
    def guild_id(self) -> int:
        return int(getattr(self.ctx.guild, "id", 0))


@dataclass
class Decision:
    ok: bool
    message: str
    action: PendingAction | None = None


ModLogFn = Callable[..., Awaitable[Any]]


class PendingActionManager:
    def __init__(
        self,
        *,
        is_moderator: IsModeratorFn,
        mod_log: ModLogFn,
        ttl_seconds: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
        max_pending: int = 200,
    ) -> None:
        self._is_moderator = is_moderator
        self._mod_log = mod_log
        self.ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._max_pending = max(1, int(max_pending))
        self._ids = itertools.count(1)
        self._actions: dict[int, PendingAction] = {}

    # -- lifecycle ----------------------------------------------------------

    def propose(self, tool: AgentTool, args: dict[str, Any], ctx: AgentContext) -> PendingAction:
        if not tool.consequential:
            raise ValueError(f"`{tool.name}` is read-only and needs no confirmation.")
        self._prune()
        action = PendingAction(
            id=next(self._ids),
            tool=tool,
            args=dict(args),
            ctx=ctx,
            created_at=self._clock(),
            summary=describe_action(tool, args),
        )
        self._actions[action.id] = action
        return action

    def get(self, action_id: int) -> PendingAction | None:
        action = self._actions.get(action_id)
        if action is not None:
            self._refresh_expiry(action)
        return action

    def _refresh_expiry(self, action: PendingAction) -> None:
        if action.status == PENDING and self._clock() - action.created_at >= self.ttl_seconds:
            action.status = EXPIRED

    def expire(self, action_id: int) -> None:
        action = self._actions.get(action_id)
        if action is not None and action.status == PENDING:
            action.status = EXPIRED

    def _prune(self) -> None:
        for action in list(self._actions.values()):
            self._refresh_expiry(action)
        if len(self._actions) < self._max_pending:
            return
        for action_id in sorted(self._actions):
            if len(self._actions) < self._max_pending:
                break
            if self._actions[action_id].status not in (PENDING, EXECUTING):
                del self._actions[action_id]

    # -- permission ---------------------------------------------------------

    def _same_guild(self, member: Any, action: PendingAction) -> bool:
        member_guild = getattr(getattr(member, "guild", None), "id", None)
        return member_guild is None or member_guild == action.guild_id

    def _is_mod(self, member: Any) -> bool:
        try:
            return bool(self._is_moderator(member))
        except Exception:
            return False

    def can_confirm(self, member: Any, action: PendingAction) -> tuple[bool, str]:
        if not self._same_guild(member, action):
            return False, "This action belongs to a different server."
        if not self._is_mod(member):
            return False, "Only moderators can confirm agent actions."
        if not member_has_permission(member, action.tool.required_permission):
            return False, f"You need the `{action.tool.required_permission}` permission to confirm this."
        return True, ""

    def can_cancel(self, member: Any, action: PendingAction) -> bool:
        # Cancelling is harmless: the requester or any moderator of that server may cancel.
        if not self._same_guild(member, action):
            return False
        return int(getattr(member, "id", 0)) == action.requester_id or self._is_mod(member)

    # -- decisions ----------------------------------------------------------

    async def confirm(self, action_id: int, member: Any) -> Decision:
        action = self.get(action_id)
        if action is None:
            return Decision(False, "This action no longer exists.")
        if action.status != PENDING:
            return Decision(False, f"This action is already {action.status}.", action)
        allowed, reason = self.can_confirm(member, action)
        if not allowed:
            return Decision(False, reason, action)

        # Claim the action before awaiting so a second click cannot run it twice.
        action.status = EXECUTING
        action.resolved_by = int(getattr(member, "id", 0))
        exec_ctx = AgentContext(
            guild=action.ctx.guild,
            channel=action.ctx.channel,
            author=action.ctx.author,
            actor=member,
            extras=dict(action.ctx.extras),
        )
        try:
            outcome = await action.tool.handler(exec_ctx, dict(action.args))
        except Exception as error:
            action.status = FAILED
            action.result = str(error) if isinstance(error, ToolError) else f"{type(error).__name__}: {error}"
            await self._write_mod_log(action, member, failed=True)
            return Decision(False, f"Action #{action.id} failed: {action.result}", action)

        action.status = CONFIRMED
        action.result = str(outcome) if outcome is not None else "done"
        await self._write_mod_log(action, member, failed=False)
        return Decision(True, f"Action #{action.id} confirmed by {_describe_value(member)}: {action.result}", action)

    async def cancel(self, action_id: int, member: Any) -> Decision:
        action = self.get(action_id)
        if action is None:
            return Decision(False, "This action no longer exists.")
        if action.status != PENDING:
            return Decision(False, f"This action is already {action.status}.", action)
        if not self.can_cancel(member, action):
            return Decision(False, "Only the requester or a moderator can cancel this action.", action)
        action.status = CANCELLED
        action.resolved_by = int(getattr(member, "id", 0))
        return Decision(True, f"Action #{action.id} cancelled by {_describe_value(member)}.", action)

    async def _write_mod_log(self, action: PendingAction, moderator: Any, *, failed: bool) -> None:
        target = next((v for v in action.args.values() if getattr(v, "guild_permissions", None) is not None), None)
        channel = action.args.get("channel") or action.ctx.channel
        reason = action.args.get("reason")
        label = action.tool.modlog_action or action.tool.name
        details = (
            f"Agent action #{action.id} `{action.summary}`"
            f"\nRequested by: {_describe_value(action.ctx.author)} (`{action.requester_id}`)"
            f"\nResult: {'FAILED - ' if failed else ''}{action.result}"
        )
        try:
            await self._mod_log(
                action.ctx.guild,
                f"Agent: {label}{' (failed)' if failed else ''}",
                target=target,
                moderator=moderator,
                reason=str(reason) if reason else None,
                channel=channel,
                details=details[:1000],
            )
        except Exception as error:
            print(f"[AGENT MODLOG ERROR] {error}")

    # -- Discord glue -------------------------------------------------------

    async def handle_interaction(self, interaction: Any, action_id: int, *, confirm: bool) -> Decision:
        """Button callback body. Denials are ephemeral; outcomes replace the card."""
        member = interaction.user
        action = self.get(action_id)
        if confirm and action is not None and action.status == PENDING:
            allowed, reason = self.can_confirm(member, action)
            if not allowed:
                await interaction.response.send_message(reason, ephemeral=True)
                return Decision(False, reason, action)
            # Acknowledge within Discord's 3s window, then execute.
            await interaction.response.defer()
            decision = await self.confirm(action_id, member)
            await interaction.edit_original_response(content=render_card(decision.action), view=None)
            return decision

        decision = await (self.confirm(action_id, member) if confirm else self.cancel(action_id, member))
        if decision.ok:
            await interaction.response.edit_message(content=render_card(decision.action), view=None)
        else:
            await interaction.response.send_message(decision.message, ephemeral=True)
        return decision


def render_card(action: PendingAction | None) -> str:
    if action is None:
        return "Agent action no longer available."
    status_line = {
        PENDING: "Waiting for a moderator to **Confirm** or **Cancel**.",
        EXECUTING: "Running...",
        CONFIRMED: f"Confirmed by <@{action.resolved_by}>. Result: {action.result}",
        FAILED: f"Confirmed by <@{action.resolved_by}> but failed: {action.result}",
        CANCELLED: f"Cancelled by <@{action.resolved_by}>.",
        EXPIRED: "Expired without confirmation.",
    }.get(action.status, action.status)
    return (
        f"**Agent action #{action.id}** (requested by <@{action.requester_id}>)\n"
        f"`{action.summary[:900]}`\n{status_line}"
    )


def build_pending_action_view(manager: PendingActionManager, action: PendingAction) -> Any:
    """Discord view with Confirm / Cancel buttons for ``action`` (imports discord lazily)."""
    import discord

    class PendingActionView(discord.ui.View):
        def __init__(self) -> None:
            super().__init__(timeout=manager.ttl_seconds)
            self.message: Any = None

        @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
        async def confirm_button(self, interaction: Any, _button: Any) -> None:
            decision = await manager.handle_interaction(interaction, action.id, confirm=True)
            if decision.action is not None and decision.action.status != PENDING:
                self.stop()

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_button(self, interaction: Any, _button: Any) -> None:
            decision = await manager.handle_interaction(interaction, action.id, confirm=False)
            if decision.action is not None and decision.action.status != PENDING:
                self.stop()

        async def on_timeout(self) -> None:
            manager.expire(action.id)
            if self.message is not None and action.status == EXPIRED:
                try:
                    await self.message.edit(content=render_card(action), view=None)
                except Exception:
                    pass

    return PendingActionView()
