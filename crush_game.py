"""Crush-o-Meter: a playful party game about the person who runs it (phase 4).

This replaces the old ``aicrush`` command, which mined every member's message
history to guess who likes whom. The rebuilt game follows these rules:

* It is about the invoker. ``&crush`` only uses inputs the invoker
  deliberately hands to the game: their answer to a fun prompt
  (``&crush <answer>``) or one of *their own* messages they reply to while
  running the command. A pointed-at message written by anyone else is
  ignored.
* Naming someone else is a random pairing. ``&crush @member`` pairs the
  invoker with that member by a seeded daily dice roll, and the result says
  so. The named member's messages and activity are never read, and they are
  never assigned real feelings. Without a member, the partner is a fictional
  character, so nobody else is named.
* Nothing is mined. There is no passive message tallying, no history scan,
  no backfill and no DM access anywhere in this module.
* One server notice. The first time a moderator enables the game, one notice
  naming ``&exclude`` and ``&wipe`` is posted in the configured channel.
* ``&exclude`` / ``&wipe`` work at any time. Excluded members can't be named
  in a pairing and can't play; ``&wipe`` deletes the member's saved answer.
* The old aicrush data file is never read. It is left untouched unless the
  bot owner explicitly runs ``&legacydata wipe confirm``.
* Minimal data: the per-member record is only the member's own saved answer
  (at most :data:`ANSWER_MAX_CHARS` characters) plus the exclusion list.
* Every result ends with a fixed joke disclaimer, and every play is admitted
  through the budget governor's per-feature daily cap (``admit_feature``).

Like :mod:`agentic_automation`, this module does not import the Discord
library, so the tests run with plain fake objects; bot.py injects the rest.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Mapping

FEATURE = "crush_game"
FLAVOR_FEATURE = "crush_game_flavor"
DEFAULT_DAILY_CAP = 50
ANSWER_MAX_CHARS = 120

DISCLAIMER = (
    "🎲 Just a joke game! These results are random silly fun, NOT anyone's real "
    "feelings, relationships or orientation. Nobody's messages were analyzed."
)

FUN_PROMPT = "What snack, song or emoji sums up your vibe today?"

FICTIONAL_PARTNERS = (
    "a suspiciously confident houseplant 🪴",
    "a raccoon who runs a lemonade stand 🦝",
    "the last slice of pizza 🍕",
    "a dramatic pigeon named Gerald 🐦",
    "a sentient lava lamp 🌋",
    "a cat who only speaks in memes 🐱",
    "a haunted rubber duck 🦆",
    "the moon (it waved first) 🌙",
)

PAIR_LABELS = (
    (90, "Cosmic Snack-Sharing Duo"),
    (75, "Two Chaotic Gremlins"),
    (60, "Meme Exchange Partners"),
    (45, "Certified Side Quest Buddies"),
    (30, "Mildly Compatible Houseplants"),
    (15, "Rival Pigeons"),
    (0, "Two Ships Passing in the Group Chat"),
)

LABEL_MYSTERY = "Mysterious Enigma (answer a prompt to reveal more)"
STYLE_LABELS = {
    "emoji": "Certified Emoji Goblin",
    "questions": "Professional Question Asker",
    "hype": "Official Hype Machine",
    "caps": "CAPS LOCK ENJOYER",
}
WORD_LABELS = (
    "Snack Philosopher",
    "Chaos Coordinator",
    "Vibe Architect",
    "Professional Daydreamer",
    "Main Character Energy",
    "Chief Meme Officer",
)

# Model flavor text is dropped if it strays into what the game must never claim.
FLAVOR_BLOCKLIST = (
    "orientation", "gay", "lesbian", "straight", "bisexual", "queer", "sexual",
    "in love", "real feelings", "secretly likes", "attracted", "romantic",
    "talks to you", "messages you", "chats with", "dating", "has a crush on",
)
FLAVOR_MAX_CHARS = 220

_CUSTOM_EMOJI = re.compile(r"<a?:\w+:\d+>")
_MENTION = re.compile(r"<[@#][!&]?\d+>")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _day_key(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _seeded(*parts: Any) -> int:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def count_emoji(text: str) -> int:
    count = len(_CUSTOM_EMOJI.findall(text))
    for ch in _CUSTOM_EMOJI.sub("", text):
        cp = ord(ch)
        if 0x1F300 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF:
            count += 1
    return count


def clean_answer(text: str | None) -> str:
    """The invoker's own answer, trimmed; mentions are stripped so nobody else is pulled in."""
    cleaned = _MENTION.sub("", str(text or ""))
    return " ".join(cleaned.split())[:ANSWER_MAX_CHARS]


def pointed_input(invoker_id: int, pointed_author_id: int | None, pointed_content: str | None) -> str:
    """Use a replied-to message only if the invoker wrote it themselves."""
    if pointed_author_id is None or int(pointed_author_id) != int(invoker_id):
        return ""
    return clean_answer(pointed_content)


def style_label(answer: str) -> str:
    """A silly label computed only from text the invoker gave the game."""
    if not answer:
        return LABEL_MYSTERY
    letters = [c for c in answer if c.isalpha()]
    if count_emoji(answer) >= 2:
        return STYLE_LABELS["emoji"]
    if len(letters) >= 5 and all(c.isupper() for c in letters):
        return STYLE_LABELS["caps"]
    if answer.count("!") >= 2:
        return STYLE_LABELS["hype"]
    if "?" in answer:
        return STYLE_LABELS["questions"]
    return WORD_LABELS[_seeded("label", answer.lower()) % len(WORD_LABELS)]


def pair_label(percent: int) -> str:
    for floor, label in PAIR_LABELS:
        if percent >= floor:
            return label
    return PAIR_LABELS[-1][1]


def _name(member: Any) -> str:
    return str(getattr(member, "display_name", None) or getattr(member, "name", None) or "someone")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class CrushGameState:
    """Plain-dict state that bot.py persists as JSON."""

    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        guilds = data.get("guilds") if isinstance(data, Mapping) else None
        self.data: dict[str, Any] = {"guilds": dict(guilds) if isinstance(guilds, Mapping) else {}}
        self.dirty = False

    def guild(self, guild_id: int) -> dict[str, Any]:
        guilds = self.data["guilds"]
        state = guilds.get(str(guild_id))
        if not isinstance(state, dict):
            state = {}
            guilds[str(guild_id)] = state
        state["enabled"] = bool(state.get("enabled", False))
        state["notice_posted"] = bool(state.get("notice_posted", False))
        if not isinstance(state.get("notice_channel_id"), int):
            state["notice_channel_id"] = None
        if not isinstance(state.get("excluded"), list):
            state["excluded"] = []
        if not isinstance(state.get("answers"), dict):
            state["answers"] = {}
        return state

    def mark(self) -> None:
        self.dirty = True


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

FlavorFn = Callable[[str], Awaitable[str]]


class CrushGame:
    def __init__(
        self,
        *,
        state: CrushGameState,
        admit_feature: Callable[[str], bool],
        prefix: str = "&",
        flavor: FlavorFn | None = None,
        now: Callable[[], datetime] = _utc_now,
        feature: str = FEATURE,
    ) -> None:
        self.state = state
        self.admit_feature = admit_feature
        self.prefix = prefix
        self.flavor = flavor
        self.now = now
        self.feature = feature

    # -- texts --------------------------------------------------------------

    def notice_text(self) -> str:
        p = self.prefix
        return (
            "📢 **Fun features notice**\n"
            "This server turned on the bot's fun features. Fun features can read messages in "
            "server channels the bot can see (never DMs). The Crush-o-Meter game itself only uses "
            f"what you give it: your answer (`{p}crush <answer>`) or your own message you reply to. "
            "If it names someone else, that pairing is a random dice roll, not an analysis.\n"
            f"• Opt out at any time: `{p}exclude` (you will never be analyzed or named, "
            "and your stored fun-feature data is deleted)\n"
            f"• Delete your stored data at any time: `{p}wipe`\n"
            "This notice is posted once."
        )

    def excluded_text(self) -> str:
        return "🙈 That member has opted out of fun features, so the game can't include them."

    def disabled_text(self) -> str:
        return (
            "The Crush-o-Meter game is not enabled in this server. A moderator can turn it "
            f"on with `{self.prefix}crushgame on #channel`."
        )

    def cap_text(self) -> str:
        return "💤 The Crush-o-Meter has used up its daily fun budget. Try again tomorrow!"

    # -- controls ----------------------------------------------------------------

    def is_enabled(self, guild_id: int) -> bool:
        return bool(self.state.guild(guild_id)["enabled"])

    def is_excluded(self, guild_id: int, member_id: int) -> bool:
        return int(member_id) in self.state.guild(guild_id)["excluded"]

    def wipe(self, guild_id: int, member_id: int) -> bool:
        """Delete the member's stored game data. Returns True if anything was removed."""
        g = self.state.guild(guild_id)
        removed = g["answers"].pop(str(int(member_id)), None) is not None
        self.state.mark()
        return removed

    def exclude(self, guild_id: int, member_id: int) -> None:
        self.wipe(guild_id, member_id)
        g = self.state.guild(guild_id)
        if int(member_id) not in g["excluded"]:
            g["excluded"].append(int(member_id))
        self.state.mark()

    def include(self, guild_id: int, member_id: int) -> None:
        g = self.state.guild(guild_id)
        if int(member_id) in g["excluded"]:
            g["excluded"].remove(int(member_id))
            self.state.mark()

    # -- enable / notice ---------------------------------------------------------

    async def enable(self, guild_id: int, channel: Any) -> bool:
        """Enable the game; post the one-time notice. Returns True if the notice was posted now."""
        g = self.state.guild(guild_id)
        g["enabled"] = True
        if channel is not None:
            g["notice_channel_id"] = int(channel.id)
        self.state.mark()
        if g["notice_posted"] or channel is None:
            return False
        await channel.send(self.notice_text())
        g["notice_posted"] = True  # only after the send succeeded
        self.state.mark()
        return True

    def disable(self, guild_id: int) -> None:
        self.state.guild(guild_id)["enabled"] = False
        self.state.mark()

    # -- the game ---------------------------------------------------------------

    def _excluded_names(self, guild: Any) -> list[str]:
        names = []
        for member_id in self.state.guild(int(guild.id))["excluded"]:
            member = guild.get_member(member_id)
            if member is None:
                continue
            for raw in (getattr(member, "display_name", None), getattr(member, "name", None)):
                if raw and len(str(raw)) >= 3:
                    names.append(str(raw).lower())
        return names

    def _clean_flavor(self, text: str, guild: Any) -> str:
        cleaned = " ".join(str(text or "").split())[:FLAVOR_MAX_CHARS].strip()
        lowered = cleaned.lower()
        if not cleaned or "<@" in cleaned:
            return ""
        if any(term in lowered for term in FLAVOR_BLOCKLIST):
            return ""
        if any(name in lowered for name in self._excluded_names(guild)):
            return ""
        return cleaned

    async def play(
        self,
        guild: Any,
        invoker: Any,
        partner: Any | None = None,
        *,
        answer: str | None = None,
    ) -> str:
        """Run the game for ``invoker``.

        ``answer`` is text the invoker deliberately supplied (a prompt answer, or
        their own message they pointed at; see :func:`pointed_input`). ``partner``
        is only ever used for its display name in a random pairing.
        """
        guild_id = int(guild.id)
        invoker_id = int(invoker.id)
        g = self.state.guild(guild_id)
        if not g["enabled"]:
            return self.disabled_text()
        if invoker_id in g["excluded"]:
            return self.excluded_text()
        if partner is not None and int(partner.id) == invoker_id:
            partner = None
        if partner is not None and int(partner.id) in g["excluded"]:
            return self.excluded_text()
        if not self.admit_feature(self.feature):
            return self.cap_text()

        cleaned = clean_answer(answer)
        if cleaned:
            g["answers"][str(invoker_id)] = cleaned  # the invoker's own input, wipe-able
            self.state.mark()
        else:
            cleaned = str(g["answers"].get(str(invoker_id), "") or "")

        today = _day_key(self.now())
        invoker_name = _name(invoker)
        if partner is not None:
            partner_name = _name(partner)
            seed = (guild_id, *sorted((invoker_id, int(partner.id))), today)
        else:
            partner_name = FICTIONAL_PARTNERS[_seeded(guild_id, invoker_id, today, "fic") % len(FICTIONAL_PARTNERS)]
            seed = (guild_id, invoker_id, partner_name, today)
        percent = 1 + _seeded(*seed, "pct") % 100
        label = style_label(cleaned)

        lines = [f"💘 **Crush-o-Meter** (a game!) for {invoker_name}"]
        if partner is not None:
            lines.append(
                f"🎲 Random pairing with **{partner_name}**: {percent}% \"{pair_label(percent)}\" "
                f"(pure dice roll, nothing about {partner_name} was looked at)"
            )
        else:
            lines.append(
                f"🎲 Today's fictional match: **{partner_name}** — {percent}% \"{pair_label(percent)}\""
            )
        lines.append(f"🏷️ {invoker_name}'s silly game label: \"{label}\"")
        if not cleaned:
            lines.append(f"💬 Fun prompt: {FUN_PROMPT} Try `{self.prefix}crush <your answer>`.")

        if self.flavor is not None:
            prompt = (
                "Write ONE short, wholesome, silly sentence for a Discord party game result. "
                "It is a joke: do not mention real feelings, romance, dating, attraction, "
                "sexuality, or anyone's chat activity. Only use the names given.\n"
                f"Player: {invoker_name}\nPlayer's own fun answer: {cleaned or '(none)'}\n"
                f"Player's silly label: {label}\n"
                f"Random game partner: {partner_name}\n"
                f"Random game score: {percent}% ({pair_label(percent)})"
            )
            try:
                extra = self._clean_flavor(await self.flavor(prompt), guild)
            except Exception:
                extra = ""
            if extra:
                lines.append(f"✨ {extra}")

        lines.append(f"-# {DISCLAIMER}")
        return "\n".join(lines)


def legacy_files_present(paths: Iterable[Any]) -> list[str]:
    """Which legacy files exist (existence only; their contents are never read)."""
    return [str(path) for path in paths if path.exists()]


def delete_legacy_files(paths: Iterable[Any]) -> list[str]:
    """Delete data left by the removed history-mining crush feature.

    Only ever called from the owner-run ``&legacydata wipe confirm`` command;
    nothing deletes it automatically.
    """
    removed = []
    for path in paths:
        try:
            if path.exists():
                path.unlink()
                removed.append(str(path))
        except OSError:
            continue
    return removed
