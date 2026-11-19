"""Flirt scoring and crush ranking for Bell's /crush command.

Pure functions with no Discord calls, so they can be unit-tested. bot.py calls
`flirt_score` while indexing every message and stores the totals on the saved
interaction graph; `rank_crush_candidates` reads that graph to answer /crush
without re-reading chat history.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

MAX_SCORE_PER_MESSAGE = 3.0

# Phrase -> weight. Matched as whole words/phrases on lowercased text.
FLIRT_PHRASES: dict[str, float] = {
    # strong
    "i love you": 1.4, "love you": 1.2, "love u": 1.2, "luv you": 1.2, "luv u": 1.2, "ily": 1.0,
    "i like you": 1.2, "i like u": 1.2, "miss you": 1.0, "miss u": 1.0, "marry me": 1.2,
    "date me": 1.2, "go on a date": 1.0, "be mine": 1.2, "my love": 1.0, "kiss": 1.0, "kisses": 1.0,
    "babe": 1.0, "bae": 1.0, "baby": 0.9, "darling": 1.0, "sweetheart": 1.0, "cutie": 1.0,
    "hottie": 1.0, "gorgeous": 1.0, "beautiful": 0.9, "handsome": 0.9, "my crush": 1.2,
    "wifey": 1.0, "hubby": 1.0, "my girl": 0.9, "my boy": 0.9,
    # hinglish
    "jaan": 1.2, "jaanu": 1.2, "meri jaan": 1.4, "babu": 1.0, "sona": 0.9, "shona": 1.0,
    "pyaar": 1.0, "pyar": 1.0, "pyaar karta": 1.3, "pyaar karti": 1.3, "tumse pyaar": 1.4,
    "mera bacha": 1.0, "meri bachi": 1.0, "dil": 0.5, "tum cute ho": 1.2, "bahut cute": 1.0,
    "yaad aa rahi": 1.0, "yaad aati": 1.0,
    # medium
    "cute": 0.5, "so cute": 0.7, "sweet": 0.4, "hot": 0.4, "sexy": 0.8, "pretty": 0.4,
    "hug": 0.6, "hugs": 0.6, "cuddle": 1.0, "blush": 0.7, "blushing": 0.7, "flirt": 0.6,
    "thinking of you": 1.0, "thinking about you": 1.0, "sleep well": 0.4, "sweet dreams": 0.8,
    "good night": 0.3, "good morning": 0.3, "hehe": 0.3, "hehehe": 0.4, "uwu": 0.4,
    "call me": 0.4, "text me": 0.4,
    # weak
    "gn": 0.15, "gm": 0.15,
}

FLIRT_EMOJIS: dict[str, float] = {
    "😘": 1.0, "😍": 0.9, "🥰": 1.0, "😚": 0.8, "😙": 0.6, "💋": 1.0, "😻": 0.7,
    "❤️": 0.7, "❤": 0.7, "♥️": 0.6, "♥": 0.6, "💕": 0.8, "💖": 0.8, "💗": 0.8, "💓": 0.8,
    "💞": 0.8, "💘": 0.9, "💝": 0.7, "❣️": 0.7, "🫶": 0.7, "🌹": 0.6,
    "🥺": 0.4, "👉👈": 0.8, "🙈": 0.4, "😊": 0.25, "☺️": 0.3, "😳": 0.3,
}

_PHRASE_PATTERN = re.compile(
    r"(?<![a-z0-9])("
    + "|".join(re.escape(p) for p in sorted(FLIRT_PHRASES, key=len, reverse=True))
    + r")(?![a-z0-9])"
)


def flirt_score(text: str) -> float:
    """How flirty one message reads, from 0 to MAX_SCORE_PER_MESSAGE."""
    if not text:
        return 0.0
    lowered = text.lower()
    score = 0.0
    seen: set[str] = set()
    for match in _PHRASE_PATTERN.finditer(lowered):
        phrase = match.group(1)
        if phrase in seen:
            continue
        seen.add(phrase)
        score += FLIRT_PHRASES[phrase]
    for emoji, weight in FLIRT_EMOJIS.items():
        if emoji in text:
            # A row of hearts counts a bit more than one, but not linearly.
            score += weight * min(2.0, 1.0 + 0.25 * (text.count(emoji) - 1))
    return round(min(MAX_SCORE_PER_MESSAGE, score), 3)


@dataclass
class CrushCandidate:
    user_id: int
    score: float
    flirts_sent: int
    flirts_received: int
    flirt_sent_score: float
    flirt_received_score: float
    interactions: float
    gender: str | None

    @property
    def mutual(self) -> bool:
        return self.flirts_sent > 0 and self.flirts_received > 0


def _edge_num(edge: Any, key: str) -> float:
    if not isinstance(edge, dict):
        return 0.0
    try:
        return float(edge.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def opposite_gender(gender: str | None) -> str | None:
    if gender == "male":
        return "female"
    if gender == "female":
        return "male"
    return None


def rank_crush_candidates(
    target_id: int,
    target_gender: str | None,
    edges: dict[str, dict[str, Any]],
    gender_of: Callable[[int], str | None],
    *,
    is_eligible: Callable[[int], bool] = lambda _uid: True,
    limit: int = 3,
) -> tuple[list[CrushCandidate], dict[str, int]]:
    """Rank who `target_id` flirts with most, keeping only the opposite gender when known.

    `edges` is the saved graph: edges[str(source)][str(dest)] -> counters, including
    `flirt_score` / `flirt_count` written by the indexer.
    """
    outgoing = edges.get(str(target_id), {}) if isinstance(edges, dict) else {}
    if not isinstance(outgoing, dict):
        outgoing = {}
    candidate_ids: set[int] = set()
    for key in outgoing:
        if str(key).isdigit():
            candidate_ids.add(int(key))
    incoming: dict[int, dict[str, Any]] = {}
    for source_key, row in (edges or {}).items():
        if not isinstance(row, dict) or not str(source_key).isdigit():
            continue
        edge = row.get(str(target_id))
        if isinstance(edge, dict):
            incoming[int(source_key)] = edge
            candidate_ids.add(int(source_key))
    candidate_ids.discard(target_id)

    wanted_gender = opposite_gender(target_gender)
    stats = {"considered": 0, "wrong_gender": 0, "unknown_gender": 0}
    ranked: list[CrushCandidate] = []
    for uid in candidate_ids:
        if not is_eligible(uid):
            continue
        out_edge = outgoing.get(str(uid))
        in_edge = incoming.get(uid)
        sent = _edge_num(out_edge, "flirt_score")
        received = _edge_num(in_edge, "flirt_score")
        if sent <= 0 and received <= 0:
            continue
        stats["considered"] += 1
        gender = gender_of(uid)
        if wanted_gender is not None:
            if gender is None:
                stats["unknown_gender"] += 1
                continue
            if gender != wanted_gender:
                stats["wrong_gender"] += 1
                continue
        interactions = _edge_num(out_edge, "score") + _edge_num(in_edge, "score")
        score = (
            sent * 1.0
            + received * 0.45
            + (0.75 if sent > 0 and received > 0 else 0.0)
            + min(15.0, interactions) * 0.04
        )
        ranked.append(
            CrushCandidate(
                user_id=uid,
                score=round(score, 3),
                flirts_sent=int(_edge_num(out_edge, "flirt_count")),
                flirts_received=int(_edge_num(in_edge, "flirt_count")),
                flirt_sent_score=round(sent, 3),
                flirt_received_score=round(received, 3),
                interactions=round(interactions, 3),
                gender=gender,
            )
        )
    # Their crush is who *they* flirt with, so people they never flirted back at rank last.
    ranked.sort(key=lambda c: (c.flirt_sent_score > 0, c.score, c.interactions), reverse=True)
    return ranked[: max(1, limit)], stats


def crush_confidence(candidates: list[CrushCandidate]) -> int:
    """Rough 0-100 confidence from how far the leader is ahead and how much evidence exists."""
    if not candidates:
        return 0
    top = candidates[0].score
    second = candidates[1].score if len(candidates) > 1 else 0.0
    lead = top / max(0.1, top + second)
    evidence = min(1.0, (candidates[0].flirts_sent + candidates[0].flirts_received) / 15)
    return int(round(100 * max(0.1, min(0.97, lead * 0.6 + evidence * 0.4))))
