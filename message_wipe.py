"""Targeted message wipe engine for Bell.

Finds and deletes a single user's messages across a server, with filters for
channels, content, message type and time range. The filter parsing and the
message matching are deliberately free of Discord API calls so they can be
unit-tested; the scan/delete coroutines only use a small, duck-typed surface of
discord.py objects.
"""

from __future__ import annotations

import asyncio
import re
import shlex
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Iterable

import discord


# Discord only bulk-deletes messages younger than 14 days. Keep a safety margin
# so a scan that takes a while doesn't push a message over the edge.
BULK_DELETE_MAX_AGE = timedelta(days=13, hours=22)
BULK_CHUNK_SIZE = 100
# Rough per-message cost of deleting messages that are too old for bulk delete
# (Discord's per-channel delete rate limit). Only used for the ETA shown to mods.
SINGLE_DELETE_SECONDS_ESTIMATE = 1.1

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
INVITE_PATTERN = re.compile(
    r"(?:discord(?:app)?\.com/invite|discord\.gg|discord\.me|dsc\.gg)/[A-Za-z0-9-]+",
    re.IGNORECASE,
)
CUSTOM_EMOJI_PATTERN = re.compile(r"<a?:[A-Za-z0-9_~]{1,32}:\d{15,25}>")
CHANNEL_MENTION_PATTERN = re.compile(r"^<#(\d{15,25})>$")
DURATION_PATTERN = re.compile(r"^(\d{1,6})\s*(s|m|h|d|w|mo|y)$", re.IGNORECASE)

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".avif")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v")
AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".opus")

# Canonical message-type filters and the words people may type for them.
TYPE_ALIASES: dict[str, str] = {
    "text": "text",
    "plain": "text",
    "link": "links",
    "links": "links",
    "url": "links",
    "urls": "links",
    "invite": "invites",
    "invites": "invites",
    "attachment": "attachments",
    "attachments": "attachments",
    "file": "attachments",
    "files": "attachments",
    "image": "images",
    "images": "images",
    "img": "images",
    "photo": "images",
    "photos": "images",
    "pic": "images",
    "pics": "images",
    "gif": "images",
    "gifs": "images",
    "video": "videos",
    "videos": "videos",
    "audio": "audio",
    "voice": "audio",
    "voicenote": "audio",
    "embed": "embeds",
    "embeds": "embeds",
    "sticker": "stickers",
    "stickers": "stickers",
    "mention": "mentions",
    "mentions": "mentions",
    "ping": "mentions",
    "pings": "mentions",
    "reply": "replies",
    "replies": "replies",
    "emoji": "emoji",
    "emojis": "emoji",
    "emote": "emoji",
    "emotes": "emoji",
}
TYPE_LABELS: dict[str, str] = {
    "text": "plain text only",
    "links": "links",
    "invites": "server invites",
    "attachments": "attachments",
    "images": "images/GIFs",
    "videos": "videos",
    "audio": "audio/voice notes",
    "embeds": "embeds",
    "stickers": "stickers",
    "mentions": "mentions/pings",
    "replies": "replies",
    "emoji": "emoji-only",
}

FLAG_ALIASES: dict[str, str] = {
    "here": "here",
    "pinned": "pinned",
    "includepinned": "pinned",
    "include-pinned": "pinned",
    "archived": "archived",
    "threads": "archived",
    "preview": "preview",
    "dryrun": "preview",
    "dry-run": "preview",
    "count": "preview",
}


class WipeFilterError(ValueError):
    """Raised when a filter string can't be understood."""


@dataclass
class WipeFilters:
    channel_ids: set[int] = field(default_factory=set)
    exclude_channel_ids: set[int] = field(default_factory=set)
    only_here: bool = False
    keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    regex: re.Pattern[str] | None = None
    types: set[str] = field(default_factory=set)
    exclude_types: set[str] = field(default_factory=set)
    after: datetime | None = None
    before: datetime | None = None
    min_length: int | None = None
    max_length: int | None = None
    include_pinned: bool = False
    include_archived_threads: bool = False
    preview_only: bool = False
    scan_limit_per_channel: int | None = None

    def describe(self, channel_label: Callable[[int], str] = lambda cid: f"<#{cid}>") -> list[str]:
        lines: list[str] = []
        if self.only_here:
            lines.append("Channels: this channel only")
        elif self.channel_ids:
            lines.append("Channels: " + ", ".join(channel_label(cid) for cid in sorted(self.channel_ids)))
        else:
            lines.append("Channels: every channel I can manage")
        if self.exclude_channel_ids:
            lines.append("Skipping: " + ", ".join(channel_label(cid) for cid in sorted(self.exclude_channel_ids)))
        if self.types:
            lines.append("Only: " + " OR ".join(TYPE_LABELS[t] for t in sorted(self.types)))
        if self.exclude_types:
            lines.append("Never: " + ", ".join(TYPE_LABELS[t] for t in sorted(self.exclude_types)))
        if self.keywords:
            lines.append("Containing any of: " + ", ".join(f"`{k}`" for k in self.keywords))
        if self.exclude_keywords:
            lines.append("Not containing: " + ", ".join(f"`{k}`" for k in self.exclude_keywords))
        if self.regex is not None:
            lines.append(f"Matching regex: `{self.regex.pattern}`")
        if self.after is not None:
            lines.append(f"Sent after: {discord.utils.format_dt(self.after, 'f')}")
        if self.before is not None:
            lines.append(f"Sent before: {discord.utils.format_dt(self.before, 'f')}")
        if self.min_length is not None:
            lines.append(f"At least {self.min_length} characters")
        if self.max_length is not None:
            lines.append(f"At most {self.max_length} characters")
        lines.append("Pinned messages: " + ("included" if self.include_pinned else "kept"))
        if self.include_archived_threads:
            lines.append("Archived threads: included")
        if self.scan_limit_per_channel:
            lines.append(f"Scan depth: newest {self.scan_limit_per_channel} messages per channel")
        return lines


def parse_amount(raw: str | None, *, maximum: int) -> int | None:
    """Return a positive int cap, or None for 'all'."""
    if raw is None:
        return None
    text = str(raw).strip().lower().replace(",", "").replace("_", "")
    if text in {"", "all", "*", "everything", "max"}:
        return None
    if text.endswith("k") and text[:-1].isdigit():
        value = int(text[:-1]) * 1000
    elif text.isdigit():
        value = int(text)
    else:
        raise WipeFilterError(f"`{raw}` is not a number. Use a number like `500`, `10k`, or `all`.")
    if value < 1:
        raise WipeFilterError("Amount must be at least `1`.")
    if value > maximum:
        raise WipeFilterError(f"Amount can be at most `{maximum}` (or use `all`).")
    return value


def looks_like_amount(raw: str) -> bool:
    text = raw.strip().lower().replace(",", "").replace("_", "")
    return text in {"all", "*", "everything", "max"} or text.isdigit() or (
        text.endswith("k") and text[:-1].isdigit()
    )


def parse_duration(raw: str) -> timedelta:
    match = DURATION_PATTERN.match(raw.strip())
    if not match:
        raise WipeFilterError(
            f"`{raw}` is not a duration. Use things like `30m`, `12h`, `7d`, `2w`, `3mo`, `1y`."
        )
    value = int(match.group(1))
    unit = match.group(2).lower()
    seconds = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
        "mo": 2592000,
        "y": 31536000,
    }[unit]
    return timedelta(seconds=value * seconds)


def parse_date(raw: str) -> datetime:
    text = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise WipeFilterError(f"`{raw}` is not a date. Use `YYYY-MM-DD` (UTC).")


def _parse_int(raw: str, name: str) -> int:
    if not raw.isdigit():
        raise WipeFilterError(f"`{name}` needs a whole number, got `{raw}`.")
    return int(raw)


def parse_filters(
    text: str | None,
    *,
    resolve_channel: Callable[[str], int | None],
    now: datetime | None = None,
) -> WipeFilters:
    """Parse a filter string like `in:#general,#memes links -images newer:30d contains:"lol"`.

    Rules:
      * channel mentions / `in:` pick channels (default: all channels).
      * `-#channel` / `not-in:` / `exclude:` skip channels.
      * type words (`links`, `images`, `files`, ...) are OR'ed together.
      * `-type` / `no:type` excludes a type.
      * everything else is AND'ed.
    """
    filters = WipeFilters()
    now = now or datetime.now(timezone.utc)
    if not text or not text.strip():
        return filters
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        raise WipeFilterError(f"Could not read filters ({exc}). Check your quotes.") from exc

    def resolve_many(raw: str) -> set[int]:
        ids: set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            channel_id = resolve_channel(part)
            if channel_id is None:
                raise WipeFilterError(f"I couldn't find a channel called `{part}`.")
            ids.add(channel_id)
        return ids

    for token in tokens:
        lowered = token.lower()

        mention = CHANNEL_MENTION_PATTERN.match(token)
        if mention:
            filters.channel_ids.add(int(mention.group(1)))
            continue
        excluded = CHANNEL_MENTION_PATTERN.match(token[1:]) if token.startswith("-") else None
        if excluded:
            filters.exclude_channel_ids.add(int(excluded.group(1)))
            continue

        if lowered in FLAG_ALIASES:
            flag = FLAG_ALIASES[lowered]
            if flag == "here":
                filters.only_here = True
            elif flag == "pinned":
                filters.include_pinned = True
            elif flag == "archived":
                filters.include_archived_threads = True
            elif flag == "preview":
                filters.preview_only = True
            continue

        if lowered in TYPE_ALIASES:
            filters.types.add(TYPE_ALIASES[lowered])
            continue
        if lowered.startswith("-") and lowered[1:] in TYPE_ALIASES:
            filters.exclude_types.add(TYPE_ALIASES[lowered[1:]])
            continue

        if ":" not in token:
            raise WipeFilterError(
                f"I don't understand `{token}`. Put words to match in `contains:\"...\"`."
            )
        key, _, value = token.partition(":")
        key = key.lower().strip()
        value = value.strip()
        if not value:
            raise WipeFilterError(f"`{key}:` needs a value.")

        if key in {"in", "channel", "channels", "ch"}:
            filters.channel_ids |= resolve_many(value)
        elif key in {"not-in", "notin", "exclude", "skip", "-in"}:
            filters.exclude_channel_ids |= resolve_many(value)
        elif key in {"has", "type", "only"}:
            for part in value.split(","):
                canonical = TYPE_ALIASES.get(part.strip().lower())
                if canonical is None:
                    raise WipeFilterError(f"Unknown message type `{part}`.")
                filters.types.add(canonical)
        elif key in {"no", "not", "without", "-has"}:
            for part in value.split(","):
                canonical = TYPE_ALIASES.get(part.strip().lower())
                if canonical is None:
                    raise WipeFilterError(f"Unknown message type `{part}`.")
                filters.exclude_types.add(canonical)
        elif key in {"contains", "word", "words", "keyword", "text", "has-text"}:
            filters.keywords.append(value.lower())
        elif key in {"-contains", "notcontains", "not-contains", "except", "keep"}:
            filters.exclude_keywords.append(value.lower())
        elif key in {"regex", "re", "pattern"}:
            if len(value) > 200:
                raise WipeFilterError("Regex is too long (max 200 characters).")
            try:
                filters.regex = re.compile(value, re.IGNORECASE)
            except re.error as exc:
                raise WipeFilterError(f"Invalid regex: {exc}") from exc
        elif key in {"after", "since", "from"}:
            filters.after = parse_date(value)
        elif key in {"before", "until", "to"}:
            filters.before = parse_date(value)
        elif key in {"newer", "last", "within", "recent"}:
            filters.after = now - parse_duration(value)
        elif key in {"older", "olderthan", "older-than"}:
            filters.before = now - parse_duration(value)
        elif key in {"minlen", "min", "minlength"}:
            filters.min_length = _parse_int(value, key)
        elif key in {"maxlen", "max", "maxlength"}:
            filters.max_length = _parse_int(value, key)
        elif key in {"scan", "depth"}:
            filters.scan_limit_per_channel = max(1, _parse_int(value, key))
        else:
            raise WipeFilterError(f"Unknown filter `{key}:`.")

    if filters.after and filters.before and filters.after >= filters.before:
        raise WipeFilterError("The `after`/`newer` time must be earlier than the `before`/`older` time.")
    if (
        filters.min_length is not None
        and filters.max_length is not None
        and filters.min_length > filters.max_length
    ):
        raise WipeFilterError("`minlen` can't be bigger than `maxlen`.")
    overlap = filters.types & filters.exclude_types
    if overlap:
        raise WipeFilterError(
            "You both included and excluded: " + ", ".join(sorted(overlap)) + "."
        )
    return filters


def _attachment_kind(attachment: Any) -> str:
    content_type = (getattr(attachment, "content_type", None) or "").lower()
    filename = (getattr(attachment, "filename", "") or "").lower()
    if content_type.startswith("image/") or filename.endswith(IMAGE_EXTENSIONS):
        return "image"
    if content_type.startswith("video/") or filename.endswith(VIDEO_EXTENSIONS):
        return "video"
    if content_type.startswith("audio/") or filename.endswith(AUDIO_EXTENSIONS):
        return "audio"
    return "file"


def _is_emoji_only(content: str) -> bool:
    stripped = CUSTOM_EMOJI_PATTERN.sub("", content)
    stripped = "".join(ch for ch in stripped if not ch.isspace())
    if not content.strip():
        return False
    if not stripped:
        return True
    for ch in stripped:
        code = ord(ch)
        if unicodedata.category(ch) == "So":
            continue
        if code in (0x200D, 0xFE0F, 0x20E3) or 0x1F3FB <= code <= 0x1F3FF or 0xE0020 <= code <= 0xE007F:
            continue  # ZWJ, variation selector, keycap, skin tones, tag chars
        if 0x1F1E6 <= code <= 0x1F1FF:
            continue  # regional indicators (flags)
        return False
    return True


def message_types(message: Any) -> set[str]:
    content: str = getattr(message, "content", "") or ""
    attachments = list(getattr(message, "attachments", []) or [])
    embeds = list(getattr(message, "embeds", []) or [])
    stickers = list(getattr(message, "stickers", []) or [])
    found: set[str] = set()

    if URL_PATTERN.search(content):
        found.add("links")
    if INVITE_PATTERN.search(content):
        found.add("invites")
        found.add("links")
    if attachments:
        found.add("attachments")
        for attachment in attachments:
            kind = _attachment_kind(attachment)
            if kind == "image":
                found.add("images")
            elif kind == "video":
                found.add("videos")
            elif kind == "audio":
                found.add("audio")
    if embeds:
        found.add("embeds")
        for embed in embeds:
            embed_type = getattr(embed, "type", None)
            if embed_type in {"image", "gifv"}:
                found.add("images")
            elif embed_type == "video":
                found.add("videos")
    if stickers:
        found.add("stickers")
    if (
        getattr(message, "mentions", None)
        or getattr(message, "role_mentions", None)
        or getattr(message, "mention_everyone", False)
    ):
        found.add("mentions")
    if getattr(message, "reference", None) is not None:
        found.add("replies")
    if content.strip() and _is_emoji_only(content):
        found.add("emoji")
    if content.strip() and not attachments and not embeds and not stickers and "links" not in found:
        found.add("text")
    return found


def message_matches(message: Any, filters: WipeFilters) -> bool:
    if getattr(message, "pinned", False) and not filters.include_pinned:
        return False

    created_at: datetime | None = getattr(message, "created_at", None)
    if created_at is not None:
        if filters.after is not None and created_at <= filters.after:
            return False
        if filters.before is not None and created_at >= filters.before:
            return False

    content: str = getattr(message, "content", "") or ""
    lowered = content.lower()
    if filters.min_length is not None and len(content) < filters.min_length:
        return False
    if filters.max_length is not None and len(content) > filters.max_length:
        return False
    if filters.keywords and not any(keyword in lowered for keyword in filters.keywords):
        return False
    if filters.exclude_keywords and any(keyword in lowered for keyword in filters.exclude_keywords):
        return False
    if filters.regex is not None and not filters.regex.search(content):
        return False

    if filters.types or filters.exclude_types:
        kinds = message_types(message)
        if filters.types and not (kinds & filters.types):
            return False
        if filters.exclude_types and (kinds & filters.exclude_types):
            return False
    return True


# --------------------------------------------------------------------------------------
# Scan + delete engine
# --------------------------------------------------------------------------------------


@dataclass
class WipeMatch:
    channel_id: int
    message_id: int
    created_at: datetime


@dataclass
class WipeJob:
    guild_id: int
    target_id: int
    moderator_id: int
    self_service: bool
    filters: WipeFilters
    amount: int | None
    started_at: float = field(default_factory=time.monotonic)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    phase: str = "scanning"
    channels_total: int = 0
    channels_done: int = 0
    scanned: int = 0
    matches: list[WipeMatch] = field(default_factory=list)
    deleted: int = 0
    failed: int = 0
    skipped_channels: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def per_channel_counts(self) -> dict[int, int]:
        counts: dict[int, int] = defaultdict(int)
        for match in self.matches:
            counts[match.channel_id] += 1
        return dict(counts)

    def split_by_age(self, now: datetime | None = None) -> tuple[int, int]:
        now = now or datetime.now(timezone.utc)
        recent = sum(1 for m in self.matches if now - m.created_at < BULK_DELETE_MAX_AGE)
        return recent, len(self.matches) - recent

    def eta_seconds(self) -> float:
        recent, old = self.split_by_age()
        bulk_calls = (recent + BULK_CHUNK_SIZE - 1) // BULK_CHUNK_SIZE
        return bulk_calls * 1.0 + old * SINGLE_DELETE_SECONDS_ESTIMATE


def format_eta(seconds: float) -> str:
    seconds = int(max(seconds, 1))
    if seconds < 60:
        return f"~{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"~{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"~{hours}h {minutes}m"


ProgressCallback = Callable[[WipeJob], Awaitable[None]]


async def scan_channels(
    job: WipeJob,
    channels: Iterable[Any],
    *,
    progress: ProgressCallback | None = None,
    progress_interval: float = 3.0,
    ignore_message_ids: set[int] | None = None,
) -> None:
    """Walk channel history newest-first and collect messages that match."""
    channels = list(channels)
    job.channels_total = len(channels)
    job.phase = "scanning"
    ignore_message_ids = ignore_message_ids or set()
    filters = job.filters
    last_progress = 0.0

    for channel in channels:
        if job.cancelled:
            break
        found_here = 0
        try:
            async for message in channel.history(
                limit=filters.scan_limit_per_channel,
                before=filters.before,
                after=filters.after,
                oldest_first=False,
            ):
                if job.cancelled:
                    break
                job.scanned += 1
                author = getattr(message, "author", None)
                if author is not None and author.id == job.target_id and message.id not in ignore_message_ids:
                    if message_matches(message, filters):
                        job.matches.append(WipeMatch(channel.id, message.id, message.created_at))
                        found_here += 1
                        # Per channel we walk newest-first, so once this channel has
                        # `amount` matches, no older message here can make the global top-N.
                        if job.amount is not None and found_here >= job.amount:
                            break
                if progress is not None and time.monotonic() - last_progress >= progress_interval:
                    last_progress = time.monotonic()
                    await progress(job)
        except discord.Forbidden:
            job.skipped_channels.append(getattr(channel, "mention", str(channel)))
        except discord.HTTPException as exc:
            job.errors.append(f"{getattr(channel, 'mention', channel)}: {exc.status}")
        job.channels_done += 1

    job.matches.sort(key=lambda m: m.created_at, reverse=True)
    if job.amount is not None:
        del job.matches[job.amount :]


async def delete_matches(
    job: WipeJob,
    channels_by_id: dict[int, Any],
    *,
    progress: ProgressCallback | None = None,
    progress_interval: float = 3.0,
    reason: str | None = None,
) -> None:
    """Delete everything in job.matches. Bulk-deletes recent ones, single-deletes the rest."""
    job.phase = "deleting"
    now = datetime.now(timezone.utc)
    grouped: dict[int, list[WipeMatch]] = defaultdict(list)
    for match in job.matches:
        grouped[match.channel_id].append(match)
    last_progress = 0.0

    async def maybe_progress() -> None:
        nonlocal last_progress
        if progress is not None and time.monotonic() - last_progress >= progress_interval:
            last_progress = time.monotonic()
            await progress(job)

    for channel_id, matches in grouped.items():
        if job.cancelled:
            break
        channel = channels_by_id.get(channel_id)
        if channel is None:
            job.failed += len(matches)
            continue
        recent = [m for m in matches if now - m.created_at < BULK_DELETE_MAX_AGE]
        old = [m for m in matches if now - m.created_at >= BULK_DELETE_MAX_AGE]

        for start in range(0, len(recent), BULK_CHUNK_SIZE):
            if job.cancelled:
                break
            chunk = recent[start : start + BULK_CHUNK_SIZE]
            try:
                await channel.delete_messages(
                    [discord.Object(id=m.message_id) for m in chunk], reason=reason
                )
                job.deleted += len(chunk)
            except discord.NotFound:
                # Some were already gone; fall back to one-by-one for this chunk.
                old.extend(chunk)
            except discord.HTTPException:
                old.extend(chunk)
            await maybe_progress()

        for match in old:
            if job.cancelled:
                break
            try:
                await channel.get_partial_message(match.message_id).delete()
                job.deleted += 1
            except discord.NotFound:
                job.deleted += 1  # already gone counts as done
            except discord.Forbidden:
                job.failed += 1
            except discord.HTTPException:
                job.failed += 1
            await maybe_progress()

    job.phase = "cancelled" if job.cancelled else "done"
