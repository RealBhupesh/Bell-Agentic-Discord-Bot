from __future__ import annotations

import json
import os
import re
import asyncio
import time
import shutil
import random
import hashlib
import copy
import unicodedata
import difflib
from typing import Any, Literal
from dataclasses import dataclass
from collections import Counter, defaultdict, deque
from datetime import timedelta, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

import agent_core
import agent_tools
import agentic_automation
import crush_game
import groq_budget
import storage

try:
    import yt_dlp
except Exception:
    yt_dlp = None

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except Exception:
    spotipy = None
    SpotifyClientCredentials = None

try:
    import imageio_ffmpeg
except Exception:
    imageio_ffmpeg = None


load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PREFIX = os.getenv("BOT_PREFIX", "&")
BOT_ACTIVITY_TEXT = os.getenv("BOT_ACTIVITY_TEXT", "with your crush").strip()
STATE_BACKEND = "disk"

def env_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int, minimum: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return max(int(raw), minimum)
    except ValueError:
        return default


def env_float(key: str, default: float, minimum: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return max(float(raw), minimum)
    except ValueError:
        return default


AUTO_MOD_ENABLED = env_bool("AUTOMOD_ENABLED", False)
BLOCK_LINKS = env_bool("AUTOMOD_BLOCK_LINKS", True)
SPAM_MSG_THRESHOLD = env_int("AUTOMOD_SPAM_MSG_THRESHOLD", 6, 2)
SPAM_INTERVAL_SECONDS = env_int("AUTOMOD_SPAM_INTERVAL_SECONDS", 8, 1)
SPAM_TIMEOUT_MINUTES = env_int("AUTOMOD_SPAM_TIMEOUT_MINUTES", 5, 1)

env_mod_log_channel = os.getenv("MOD_LOG_CHANNEL_ID", "").strip()
ENV_MOD_LOG_CHANNEL_ID = int(env_mod_log_channel) if env_mod_log_channel.isdigit() else None

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-3-4b-it:free").strip()
OPENROUTER_API_URL = os.getenv(
    "OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions"
).strip()
OPENROUTER_MODELS_URL = os.getenv("OPENROUTER_MODELS_URL", "https://openrouter.ai/api/v1/models").strip()
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "Discord Mod Bot").strip()
OPENROUTER_HTTP_REFERER = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL, GROQ_FALLBACK_MODELS = groq_budget.load_groq_model_config(os.environ)
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions").strip()
GROQ_MODELS_URL = os.getenv("GROQ_MODELS_URL", "https://api.groq.com/openai/v1/models").strip()
AI_MAX_HISTORY = env_int("AI_MAX_HISTORY", 4, 2)
AI_MAX_TOKENS = env_int("AI_MAX_TOKENS", 260, 80)
AI_SUMMARY_MAX_TOKENS = env_int("AI_SUMMARY_MAX_TOKENS", 320, 120)
AI_TIMEOUT_SECONDS = env_int("AI_TIMEOUT_SECONDS", 45, 10)
AI_MAX_INFLIGHT = env_int("AI_MAX_INFLIGHT", 3, 1)
AI_RETRY_BACKOFF_SECONDS = env_float("AI_RETRY_BACKOFF_SECONDS", 1.2, 0.1)
AI_CIRCUIT_BREAK_SECONDS = env_int("AI_CIRCUIT_BREAK_SECONDS", 45, 5)
AI_MOD_ENABLED_DEFAULT = env_bool("AI_MOD_ENABLED", False)
AI_MOD_FAST_MODEL = os.getenv("AI_MOD_FAST_MODEL", "").strip()
AI_MOD_JUDGE_MODEL = os.getenv("AI_MOD_JUDGE_MODEL", "").strip()
AI_MOD_SHADOW_DAYS = env_int("AI_MOD_SHADOW_DAYS", 7, 0)
AI_MOD_RETENTION_DAYS = env_int("AI_MOD_RETENTION_DAYS", 30, 7)
AI_MOD_MAX_CASES = env_int("AI_MOD_MAX_CASES", 6000, 200)
PSYCH_SESSION_TIMEOUT_MINUTES = env_int("PSYCH_SESSION_TIMEOUT_MINUTES", 1440, 30)
PSYCH_MAX_TOKENS = env_int("PSYCH_MAX_TOKENS", 320, 120)
PSYCH_MAX_NOTES_CHARS = env_int("PSYCH_MAX_NOTES_CHARS", 1200, 200)
PSYCH_MAX_TURNS = env_int("PSYCH_MAX_TURNS", 60, 5)
PSYCH_CRISIS_STRICT = env_bool("PSYCH_CRISIS_STRICT", True)
PSYCH_LISTEN_WINDOW_SECONDS = env_float("PSYCH_LISTEN_WINDOW_SECONDS", 12.0, 2.0)
PSYCH_SOLUTION_TRIGGER_MODE = os.getenv("PSYCH_SOLUTION_TRIGGER_MODE", "explicit").strip().lower()
if PSYCH_SOLUTION_TRIGGER_MODE not in {"explicit"}:
    PSYCH_SOLUTION_TRIGGER_MODE = "explicit"
PSYCH_MAX_BUFFERED_MESSAGES = env_int("PSYCH_MAX_BUFFERED_MESSAGES", 25, 3)
ARGUMENT_MODE_MAX_TURNS = env_int("ARGUMENT_MODE_MAX_TURNS", 14, 2)
ARGUMENT_MODE_TIMEOUT_MINUTES = env_int("ARGUMENT_MODE_TIMEOUT_MINUTES", 45, 5)
ARGUMENT_MODE_REPLY_TOKENS = env_int("ARGUMENT_MODE_REPLY_TOKENS", 180, 80)
SYNC_SLASH_COMMANDS = env_bool("SYNC_SLASH_COMMANDS", True)
VIBE_DEFAULT_MESSAGE_COUNT = env_int("VIBE_DEFAULT_MESSAGE_COUNT", 200, 20)
VIBE_MAX_MESSAGE_COUNT = env_int("VIBE_MAX_MESSAGE_COUNT", 800, 50)
VIBE_MIN_REQUIRED_MESSAGES = env_int("VIBE_MIN_REQUIRED_MESSAGES", 25, 5)
VIBE_MAX_PROMPT_MESSAGES = env_int("VIBE_MAX_PROMPT_MESSAGES", 80, 20)
VIBE_MAX_PROMPT_CHARS = env_int("VIBE_MAX_PROMPT_CHARS", 12000, 2000)
VOICE_CONNECT_RETRIES = env_int("VOICE_CONNECT_RETRIES", 4, 1)
VOICE_CONNECT_TIMEOUT = env_int("VOICE_CONNECT_TIMEOUT", 25, 10)
VOICE_INTERNAL_RECONNECT = env_bool("VOICE_INTERNAL_RECONNECT", False)
_AI_PROVIDER_RAW = os.getenv("AI_PROVIDER", "").strip().lower()
if _AI_PROVIDER_RAW in {"openrouter", "groq"}:
    AI_PROVIDER = _AI_PROVIDER_RAW
elif GROQ_API_KEY and not OPENROUTER_API_KEY:
    AI_PROVIDER = "groq"
else:
    AI_PROVIDER = "openrouter"
OPENROUTER_FALLBACK_MODELS = [
    model.strip()
    for model in os.getenv(
        "OPENROUTER_FALLBACK_MODELS",
        "google/gemma-3-4b-it:free,qwen/qwen3-4b:free,deepseek/deepseek-r1-0528:free",
    ).split(",")
    if model.strip()
]

FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg").strip() or "ffmpeg"
MUSIC_MAX_PLAYLIST_ITEMS = env_int("MUSIC_MAX_PLAYLIST_ITEMS", 50, 1)
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
CAT_API_URL = os.getenv("CAT_API_URL", "https://api.thecatapi.com/v1/images/search").strip()
MEALDB_BASE_URL = os.getenv(
    "MEALDB_BASE_URL", "https://www.themealdb.com/api/json/v1/1"
).strip().rstrip("/")
MEAL_CACHE_TTL_SECONDS = env_int("MEAL_CACHE_TTL_SECONDS", 1800, 60)
AICRUSH_FULL_HISTORY_SCAN = env_bool("AICRUSH_FULL_HISTORY_SCAN", True)
AICRUSH_SCAN_PER_CHANNEL = env_int("AICRUSH_SCAN_PER_CHANNEL", 450, 60)
_AICRUSH_MAX_CHANNELS_RAW = os.getenv("AICRUSH_MAX_CHANNELS", "0").strip()
if _AICRUSH_MAX_CHANNELS_RAW.isdigit():
    AICRUSH_MAX_CHANNELS = max(0, int(_AICRUSH_MAX_CHANNELS_RAW))
else:
    AICRUSH_MAX_CHANNELS = 0
AICRUSH_MAX_HISTORY_MESSAGES = env_int("AICRUSH_MAX_HISTORY_MESSAGES", 12000, 500)
AICRUSH_SCAN_PAUSE_EVERY = env_int("AICRUSH_SCAN_PAUSE_EVERY", 260, 50)
AICRUSH_SCAN_PAUSE_SECONDS = env_float("AICRUSH_SCAN_PAUSE_SECONDS", 0.12, 0.0)
AICRUSH_CACHE_SECONDS = env_int("AICRUSH_CACHE_SECONDS", 900, 30)
AICRUSH_CHANNEL_RECENT_WINDOW_SECONDS = env_int(
    "AICRUSH_CHANNEL_RECENT_WINDOW_SECONDS", 21600, 300
)
ALTFINDER_STATE_FLUSH_SECONDS = env_int("ALTFINDER_STATE_FLUSH_SECONDS", 30, 10)
ALTFINDER_BACKFILL_MESSAGE_BUDGET = env_int(
    "ALTFINDER_BACKFILL_MESSAGE_BUDGET", 3200, 200
)
ALTFINDER_BACKFILL_TIME_BUDGET_SECONDS = env_float(
    "ALTFINDER_BACKFILL_TIME_BUDGET_SECONDS", 10.0, 1.0
)
ALTFINDER_COMMAND_MAX_BACKFILL_MESSAGES = env_int(
    "ALTFINDER_COMMAND_MAX_BACKFILL_MESSAGES", 14000, 1000
)
ALTFINDER_COMMAND_MAX_BACKFILL_SECONDS = env_float(
    "ALTFINDER_COMMAND_MAX_BACKFILL_SECONDS", 32.0, 5.0
)
ALTFINDER_CACHE_SECONDS = env_int("ALTFINDER_CACHE_SECONDS", 900, 30)
ALTFINDER_MAX_RESULTS = env_int("ALTFINDER_MAX_RESULTS", 5, 1)
ALTFINDER_MAX_SUSPECTS = 3
ALTFINDER_RANK_MODEL = groq_budget.load_primary_model("ALTFINDER_RANK_MODEL", "openai/gpt-oss-120b")
ALTFINDER_EXPLAIN_MODEL = groq_budget.load_primary_model(
    "ALTFINDER_EXPLAIN_MODEL", "openai/gpt-oss-120b"
)
ALTFINDER_FALLBACK_MODELS = groq_budget.load_model_chain(
    "ALTFINDER_FALLBACK_MODELS", "openai/gpt-oss-20b,qwen/qwen3.8-27b"
)
SOCIALINTEL_STATE_FLUSH_SECONDS = env_int("SOCIALINTEL_STATE_FLUSH_SECONDS", 30, 10)
SOCIALINTEL_BACKFILL_MESSAGE_BUDGET = env_int(
    "SOCIALINTEL_BACKFILL_MESSAGE_BUDGET", 3200, 200
)
SOCIALINTEL_BACKFILL_TIME_BUDGET_SECONDS = env_float(
    "SOCIALINTEL_BACKFILL_TIME_BUDGET_SECONDS", 10.0, 1.0
)
SOCIALINTEL_COMMAND_MAX_BACKFILL_MESSAGES = env_int(
    "SOCIALINTEL_COMMAND_MAX_BACKFILL_MESSAGES", 14000, 1000
)
SOCIALINTEL_COMMAND_MAX_BACKFILL_SECONDS = env_float(
    "SOCIALINTEL_COMMAND_MAX_BACKFILL_SECONDS", 32.0, 5.0
)
SOCIALINTEL_CACHE_SECONDS = env_int("SOCIALINTEL_CACHE_SECONDS", 900, 30)
SOCIALINTEL_MAX_RESULTS = env_int("SOCIALINTEL_MAX_RESULTS", 5, 1)
SOCIALINTEL_RANK_MODEL = groq_budget.load_primary_model(
    "SOCIALINTEL_RANK_MODEL", "openai/gpt-oss-120b"
)
SOCIALINTEL_EXPLAIN_MODEL = groq_budget.load_primary_model(
    "SOCIALINTEL_EXPLAIN_MODEL", "openai/gpt-oss-120b"
)
SOCIALINTEL_FALLBACK_MODELS = groq_budget.load_model_chain(
    "SOCIALINTEL_FALLBACK_MODELS", "openai/gpt-oss-20b,qwen/qwen3.8-27b"
)
THREADREVIVE_PROACTIVE_ENABLED = env_bool("THREADREVIVE_PROACTIVE_ENABLED", False)
THREADREVIVE_PROACTIVE_MIN_IDLE_MINUTES = env_int(
    "THREADREVIVE_PROACTIVE_MIN_IDLE_MINUTES", 180, 15
)
THREADREVIVE_PROACTIVE_COOLDOWN_SECONDS = env_int(
    "THREADREVIVE_PROACTIVE_COOLDOWN_SECONDS", 21600, 300
)
DISCORD_ENABLE_PRESENCE_INTENT = env_bool("DISCORD_ENABLE_PRESENCE_INTENT", False)
ROAST_FULL_HISTORY_SCAN = env_bool("ROAST_FULL_HISTORY_SCAN", True)
ROAST_SCAN_PER_CHANNEL = env_int("ROAST_SCAN_PER_CHANNEL", 350, 40)
_ROAST_MAX_CHANNELS_RAW = os.getenv("ROAST_MAX_CHANNELS", "0").strip()
if _ROAST_MAX_CHANNELS_RAW.isdigit():
    ROAST_MAX_CHANNELS = max(0, int(_ROAST_MAX_CHANNELS_RAW))
else:
    ROAST_MAX_CHANNELS = 0
ROAST_MAX_HISTORY_MESSAGES = env_int("ROAST_MAX_HISTORY_MESSAGES", 8000, 500)
ROAST_SCAN_PAUSE_EVERY = env_int("ROAST_SCAN_PAUSE_EVERY", 240, 40)
ROAST_SCAN_PAUSE_SECONDS = env_float("ROAST_SCAN_PAUSE_SECONDS", 0.08, 0.0)
ROAST_MAX_CONTEXT_CHARS = env_int("ROAST_MAX_CONTEXT_CHARS", 14000, 2000)
ROAST_CACHE_SECONDS = env_int("ROAST_CACHE_SECONDS", 900, 30)
ROAST_REPEAT_COOLDOWN_HOURS = env_int("ROAST_REPEAT_COOLDOWN_HOURS", 12, 1)
ANALYZE_CACHE_SECONDS = env_int("ANALYZE_CACHE_SECONDS", 300, 30)
CATCHUP_MAX_HOURS = env_int("CATCHUP_MAX_HOURS", 168, 1)
CATCHUP_MAX_MESSAGES = env_int("CATCHUP_MAX_MESSAGES", 1200, 80)
CATCHUP_SCAN_LIMIT = env_int("CATCHUP_SCAN_LIMIT", 2500, 200)
CATCHUP_CACHE_SECONDS = env_int("CATCHUP_CACHE_SECONDS", 120, 15)
CATCHUP_MAX_PROMPT_CHARS = env_int("CATCHUP_MAX_PROMPT_CHARS", 12000, 2000)
INSIGHTS_MAX_HOURS = env_int("INSIGHTS_MAX_HOURS", 336, 6)
INSIGHTS_MAX_CHANNELS = env_int("INSIGHTS_MAX_CHANNELS", 40, 1)
INSIGHTS_MAX_MESSAGES = env_int("INSIGHTS_MAX_MESSAGES", 12000, 500)
INSIGHTS_SCAN_PER_CHANNEL = env_int("INSIGHTS_SCAN_PER_CHANNEL", 900, 100)
INSIGHTS_CACHE_SECONDS = env_int("INSIGHTS_CACHE_SECONDS", 600, 30)
FUN_USER_RATE_WINDOW_SECONDS = env_int("FUN_USER_RATE_WINDOW_SECONDS", 45, 5)
FUN_USER_RATE_MAX_CALLS = env_int("FUN_USER_RATE_MAX_CALLS", 3, 1)
FUN_CHANNEL_RATE_WINDOW_SECONDS = env_int("FUN_CHANNEL_RATE_WINDOW_SECONDS", 20, 5)
FUN_CHANNEL_RATE_MAX_CALLS = env_int("FUN_CHANNEL_RATE_MAX_CALLS", 4, 1)
ENGAGEMENT_ENABLED = env_bool("ENGAGEMENT_ENABLED", True)
ENGAGEMENT_STATE_FLUSH_SECONDS = env_int("ENGAGEMENT_STATE_FLUSH_SECONDS", 30, 10)
XP_MIN_MESSAGE_CHARS = env_int("XP_MIN_MESSAGE_CHARS", 15, 2)
XP_MESSAGE_COOLDOWN_SECONDS = env_int("XP_MESSAGE_COOLDOWN_SECONDS", 45, 5)
XP_DAILY_CAP = env_int("XP_DAILY_CAP", 220, 30)
STREAK_GRACE_HOURS = env_int("STREAK_GRACE_HOURS", 36, 12)
QUEST_DAILY_COUNT = env_int("QUEST_DAILY_COUNT", 3, 1)
AUTO_LOOPS_ENABLED = env_bool("AUTO_LOOPS_ENABLED", False)
AUTO_LOOP_MAX_POSTS_PER_HOUR = env_int("AUTO_LOOP_MAX_POSTS_PER_HOUR", 3, 1)
AUTO_LOOP_HUB_CHANNEL_ONLY = env_bool("AUTO_LOOP_HUB_CHANNEL_ONLY", True)
EVENT_DEFAULT_DURATION_MINUTES = env_int("EVENT_DEFAULT_DURATION_MINUTES", 10, 3)
STRIKE_DECAY_DAYS = env_int("STRIKE_DECAY_DAYS", 7, 1)
MOD_HEAT_THRESHOLD = env_float("MOD_HEAT_THRESHOLD", 0.72, 0.1)
MOD_HEAT_SLOWMODE_SECONDS = env_int("MOD_HEAT_SLOWMODE_SECONDS", 20, 5)
NL_ENGAGEMENT_TRIGGERS = env_bool("NL_ENGAGEMENT_TRIGGERS", True)
WELCOME_CONCIERGE_ENABLED = env_bool("WELCOME_CONCIERGE_ENABLED", True)
WELCOME_DM_TIMEOUT_MINUTES = env_int("WELCOME_DM_TIMEOUT_MINUTES", 1440, 10)
WELCOME_RECOMMENDATION_COUNT = env_int("WELCOME_RECOMMENDATION_COUNT", 5, 1)
WELCOME_INTEREST_MAX_CHARS = env_int("WELCOME_INTEREST_MAX_CHARS", 240, 40)
BUSINESS_ENABLED = env_bool("BUSINESS_ENABLED", True)
BUSINESS_STATE_FLUSH_SECONDS = env_int("BUSINESS_STATE_FLUSH_SECONDS", 30, 10)
BUSINESS_GLOBAL_MODE = env_bool("BUSINESS_GLOBAL_MODE", True)
BUSINESS_STARTER_CASH = env_int("BUSINESS_STARTER_CASH", 10000, 100)
BUSINESS_DAILY_CLAIM = env_int("BUSINESS_DAILY_CLAIM", 1500, 10)
BUSINESS_DAILY_CLAIM_STREAK_BONUS = env_int("BUSINESS_DAILY_CLAIM_STREAK_BONUS", 250, 0)
BUSINESS_HOURLY_INTEREST_RATE = env_float("BUSINESS_HOURLY_INTEREST_RATE", 0.0012, 0.0)
BUSINESS_LOAN_GRACE_HOURS = env_int("BUSINESS_LOAN_GRACE_HOURS", 24, 1)
BUSINESS_MAX_DEBT_TO_NETWORTH = env_float("BUSINESS_MAX_DEBT_TO_NETWORTH", 1.8, 0.1)
BUSINESS_STOCK_COUNT = env_int("BUSINESS_STOCK_COUNT", 16, 6)
BUSINESS_MARKET_EVENT_CHANCE = env_float("BUSINESS_MARKET_EVENT_CHANCE", 0.18, 0.0)
BUSINESS_TRANSACTION_FEE_RATE = env_float("BUSINESS_TRANSACTION_FEE_RATE", 0.01, 0.0)
BUSINESS_PROPERTY_MAINTENANCE_RATE = env_float("BUSINESS_PROPERTY_MAINTENANCE_RATE", 0.004, 0.0)
BUSINESS_PROPERTY_TAX_RATE = env_float("BUSINESS_PROPERTY_TAX_RATE", 0.006, 0.0)
BUSINESS_AUCTION_SNIPING_WINDOW_SECONDS = env_int("BUSINESS_AUCTION_SNIPING_WINDOW_SECONDS", 30, 5)
BUSINESS_AUCTION_SNIPING_EXTEND_SECONDS = env_int("BUSINESS_AUCTION_SNIPING_EXTEND_SECONDS", 60, 10)
BUSINESS_MAX_OPEN_TRADES = env_int("BUSINESS_MAX_OPEN_TRADES", 5, 1)
BUSINESS_MAX_OPEN_AUCTIONS = env_int("BUSINESS_MAX_OPEN_AUCTIONS", 3, 1)
BUSINESS_COMMAND_COOLDOWN_SECONDS = env_int("BUSINESS_COMMAND_COOLDOWN_SECONDS", 3, 1)
BUSINESS_LEDGER_MAX_ENTRIES = env_int("BUSINESS_LEDGER_MAX_ENTRIES", 50000, 1000)
BUSINESS_AI_PERSONALIZATION_ENABLED = env_bool("BUSINESS_AI_PERSONALIZATION_ENABLED", True)
BUSINESS_AI_TUNING_ENABLED = env_bool("BUSINESS_AI_TUNING_ENABLED", True)
BUSINESS_AI_MAX_TOKENS = env_int("BUSINESS_AI_MAX_TOKENS", 140, 60)
BUSINESS_AI_PERSONALIZATION_CACHE_SECONDS = env_int(
    "BUSINESS_AI_PERSONALIZATION_CACHE_SECONDS", 900, 60
)
BUSINESS_AI_DIRECTOR_INTERVAL_HOURS = env_int("BUSINESS_AI_DIRECTOR_INTERVAL_HOURS", 3, 1)
BUSINESS_SCHEMA_VERSION = env_int("BUSINESS_SCHEMA_VERSION", 2, 2)
BUSINESS_MARKET_TICK_MINUTES = env_int("BUSINESS_MARKET_TICK_MINUTES", 15, 5)
BUSINESS_WORLD_EVENT_INTERVAL_MINUTES = env_int("BUSINESS_WORLD_EVENT_INTERVAL_MINUTES", 120, 30)
BUSINESS_WEEKLY_CYCLE_DAYS = env_int("BUSINESS_WEEKLY_CYCLE_DAYS", 7, 1)
BUSINESS_EVENT_MAX_PER_DAY = env_int("BUSINESS_EVENT_MAX_PER_DAY", 6, 1)
BUSINESS_ENABLE_COMMODITIES = env_bool("BUSINESS_ENABLE_COMMODITIES", True)
BUSINESS_ENABLE_CRYPTO = env_bool("BUSINESS_ENABLE_CRYPTO", True)
BUSINESS_ENABLE_PRIVATE_BUSINESSES = env_bool("BUSINESS_ENABLE_PRIVATE_BUSINESSES", True)
BUSINESS_CIRCUIT_BREAKER_DROP_PCT = env_float("BUSINESS_CIRCUIT_BREAKER_DROP_PCT", 25.0, 5.0)
BUSINESS_MARKET_HALT_DROP_PCT = env_float("BUSINESS_MARKET_HALT_DROP_PCT", 15.0, 5.0)
BUSINESS_CAPITAL_GAINS_SHORT_RATE = env_float("BUSINESS_CAPITAL_GAINS_SHORT_RATE", 0.15, 0.0)
BUSINESS_CAPITAL_GAINS_LONG_RATE = env_float("BUSINESS_CAPITAL_GAINS_LONG_RATE", 0.10, 0.0)
BUSINESS_CAPITAL_GAINS_LONG_HOLD_DAYS = env_int("BUSINESS_CAPITAL_GAINS_LONG_HOLD_DAYS", 7, 1)
BUSINESS_INCOME_TAX_ENABLED = env_bool("BUSINESS_INCOME_TAX_ENABLED", True)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.presences = DISCORD_ENABLE_PRESENCE_INTENT

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

DATA_DIR = Path("data")
# Every JSON state document goes through the storage adapter (storage.py); these
# are its keys. File names and formats on disk are listed in storage.AREAS.
WARNINGS_KEY = "warnings"
MOD_CONFIG_KEY = "guild_settings"
AI_MOD_STATE_KEY = "mod_log"
CAPABILITIES_OVERRIDES_KEY = "capabilities_overrides"
CAPABILITIES_CATALOG_KEY = "capabilities_catalog"
BAD_WORDS_FILE = DATA_DIR / "bad_words.txt"
ENGAGEMENT_STATE_KEY = "engagement"
BUSINESS_STATE_KEY = "economy"
# Legacy data from the removed history-mining aicrush feature. Nothing reads or
# writes it any more; it is only deleted if the bot owner runs `&legacydata wipe confirm`.
LEGACY_AICRUSH_STATE_KEY = "legacy_aicrush"
CRUSH_GAME_STATE_KEY = "crush_game"
ALTFINDER_STATE_KEY = "altfinder"
SOCIALINTEL_STATE_KEY = "socialintel"
AGENTIC_STATE_KEY = "agentic_state"
GROQ_BUDGET_STATE_KEY = "groq_budget"

LINK_PATTERN = re.compile(r"(https?://|www\.|discord\.gg/)", re.IGNORECASE)
WORD_PATTERN = re.compile(r"\b[\w']+\b")
EMOJI_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
DISCORD_MESSAGE_LINK_RE = re.compile(
    r"https?://(?:canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)",
    re.IGNORECASE,
)
POLL_EMOJIS = ["1ï¸âƒ£", "2ï¸âƒ£", "3ï¸âƒ£", "4ï¸âƒ£", "5ï¸âƒ£", "6ï¸âƒ£", "7ï¸âƒ£", "8ï¸âƒ£", "9ï¸âƒ£", "ðŸ”Ÿ"]

# (guild_id, user_id) -> message timestamps for spam detection.
SPAM_CACHE: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=20))
BAD_WORDS: set[str] = set()
SNIPE_CACHE: dict[int, dict[str, str]] = {}
AI_CHAT_CACHE: dict[int, list[dict[str, str]]] = defaultdict(list)
CONVERSATIONAL_AI_CACHE: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
ARGUMENT_MODE_SESSIONS: dict[tuple[int, int], dict[str, object]] = {}
PSYCH_SESSIONS: dict[tuple[int, int], dict[str, object]] = {}
PSYCH_SESSION_LOCKS: dict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)
PSYCH_PENDING_TASKS: dict[tuple[int, int], asyncio.Task] = {}
AI_SYSTEM_PROMPT = (
    "You are a helpful Discord assistant for a community server. "
    "Answer clearly in <=120 words unless the user asks for a long response, "
    "and avoid unsafe or illegal instructions."
)
AI_MOD_FAST_SYSTEM_PROMPT = (
    "You are Bell's moderation fast classifier for Discord messages. "
    "Classify policy risk for English + Hinglish text. "
    "Return STRICT JSON only with keys: category, risk_score, confidence, rationale_tags, suggested_action, "
    "language_mix, is_raid_suspected, is_scam_suspected. "
    "Categories: safe, spam_flood, harassment_toxic, scam_phishing, raid_behavior. "
    "risk_score and confidence are 0..1 floats. rationale_tags is an array of <=6 short strings. "
    "suggested_action: none|warn|delete|timeout|kick|ban. "
    "If uncertain, prefer safer/lower risk."
)
AI_MOD_JUDGE_SYSTEM_PROMPT = (
    "You are Bell's moderation judge model. "
    "Given classifier output + message context, produce a stricter final decision for enforceable moderation. "
    "Return STRICT JSON only with keys: category, risk_score, confidence, rationale_tags, suggested_action, "
    "explanation, language_mix, is_raid_suspected, is_scam_suspected. "
    "Use conservative, auditable reasoning and avoid over-enforcement."
)
PSYCH_SYSTEM_PROMPT = (
    "You are Bell's Psych Support Mode: a supportive assistant, not a licensed psychologist, "
    "and not a substitute for professional care. "
    "Keep tone warm, calm, practical, and non-judgmental. "
    "Do not diagnose conditions, prescribe medication, or make legal/medical claims. "
    "Do not jump to conclusions; reason from what the user shared. "
    "Use hedge language for uncertainty. "
    "If self-harm/immediate danger appears, prioritize safety and emergency guidance."
)
VIBE_SYSTEM_PROMPT = (
    "You are generating a playful Discord 'vibe report' from chat messages. "
    "Keep it fun, non-judgmental, and privacy-respecting. "
    "Do not diagnose mental/medical conditions, do not infer protected traits, "
    "and avoid harsh labels. Mention uncertainty explicitly."
)
MODEL_CACHE: set[str] = set()
MODEL_CACHE_TS = 0.0
MODEL_CACHE_TTL_SECONDS = 600
AI_REQUEST_SEMAPHORE = asyncio.Semaphore(AI_MAX_INFLIGHT)
AI_CIRCUIT_OPEN_UNTIL: dict[str, float] = {}
GROQ_BUDGET_STATE_FILE = Path(
    os.getenv("GROQ_BUDGET_STATE_FILE", "").strip() or str(DATA_DIR / "groq_budget_state.json")
)
# JSON files under data/ by default; PostgreSQL only when DATABASE_URL is set.
STORAGE = storage.backend_from_env(
    os.environ, data_dir=DATA_DIR, paths={GROQ_BUDGET_STATE_KEY: GROQ_BUDGET_STATE_FILE}
)
# Usage counters survive restarts. With the JSON backend one bot process is assumed
# to own the counters; a shared backend (DATABASE_URL) makes them multi-process safe.
GROQ_BUDGET = groq_budget.GroqBudgetGovernor.from_env(
    os.environ,
    state_path=GROQ_BUDGET_STATE_FILE,
    storage_backend=STORAGE,
    storage_key=GROQ_BUDGET_STATE_KEY,
)
AI_MOD_STATE: dict[str, Any] = {}
AI_MOD_STATE_DIRTY = False
AI_MOD_STATE_LOCK = asyncio.Lock()
AI_MOD_REPORT_LAST_TS: dict[int, float] = {}
AI_MOD_RECENT_LINK_EVENTS: dict[tuple[int, str], deque[float]] = defaultdict(
    lambda: deque(maxlen=180)
)
AI_MOD_RECENT_FINGERPRINT_EVENTS: dict[tuple[int, str], deque[tuple[float, int, int]]] = defaultdict(
    lambda: deque(maxlen=220)
)
AI_MOD_RECENT_NEW_ACCOUNT_EVENTS: dict[int, deque[tuple[float, int]]] = defaultdict(
    lambda: deque(maxlen=220)
)
AI_MOD_RECENT_ACTIONS: dict[tuple[int, int], deque[float]] = defaultdict(
    lambda: deque(maxlen=35)
)
AI_MOD_CATEGORIES = {
    "safe",
    "spam_flood",
    "harassment_toxic",
    "scam_phishing",
    "raid_behavior",
}
AI_MOD_ACTIONS = {"none", "warn", "delete", "timeout", "kick", "ban"}
AI_MOD_ACTION_ORDER = ("warn", "delete", "timeout", "kick", "ban")
AI_MOD_STAGE_A_CATEGORIES = ", ".join(sorted(AI_MOD_CATEGORIES))
AI_MOD_STAGE_B_TRIGGER_BY_STRICTNESS = {
    "moderate": 0.76,
    "moderate_strict": 0.63,
    "strict": 0.56,
}
AI_MOD_THRESHOLDS_BY_STRICTNESS: dict[str, dict[str, float]] = {
    "moderate": {"high": 0.78, "very_high": 0.90, "extreme": 0.97},
    "moderate_strict": {"high": 0.72, "very_high": 0.86, "extreme": 0.95},
    "strict": {"high": 0.68, "very_high": 0.82, "extreme": 0.93},
}
AI_MOD_HINGLISH_NORMALIZE_MAP: dict[str, str] = {
    "chutiya": "abuse",
    "chutya": "abuse",
    "madarchod": "abuse",
    "mc": "abuse",
    "bhenchod": "abuse",
    "bc": "abuse",
    "gandu": "abuse",
    "bakchod": "abusive",
    "bakchodi": "abusive",
    "randi": "abuse",
    "saale": "insult",
    "sala": "insult",
    "bewakoof": "idiot",
    "bewkuf": "idiot",
    "kutte": "insult",
    "paisa": "money",
    "paise": "money",
    "bhej": "send",
    "bhejo": "send",
    "bhejna": "send",
    "otp": "otp",
    "kyc": "kyc",
    "verify": "verify",
    "verification": "verify",
    "upar": "upi",
    "upi": "upi",
}
AI_MOD_SPAM_HINTS = {
    "dm me",
    "join now",
    "limited offer",
    "click now",
    "free nitro",
    "airdrop",
    "giveaway",
}
AI_MOD_SCAM_HINTS = {
    "otp",
    "kyc",
    "wallet",
    "seed phrase",
    "verify account",
    "bank alert",
    "suspended account",
    "login now",
    "claim reward",
    "upi",
    "send money",
    "crypto transfer",
}
AI_MOD_ABUSE_HINTS = {
    "idiot",
    "stupid",
    "loser",
    "moron",
    "abuse",
    "kill yourself",
    "kys",
}
AI_MOD_DOMAIN_RE = re.compile(r"(?:https?://|www\.)([a-z0-9\.\-]+\.[a-z]{2,})(?::\d+)?", re.IGNORECASE)
AI_MOD_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
CAPABILITY_DOMAINS = {
    "moderation",
    "ai",
    "business",
    "utility",
    "fun",
    "music",
    "engagement",
}
CAPABILITY_QUERY_DOMAIN_TERMS: dict[str, set[str]] = {
    "moderation": {"moderation", "mod", "automod", "timeout", "mute", "ban", "kick", "warn", "slowmode"},
    "ai": {"ai", "assistant", "model", "summary", "psych", "argument", "debate", "translate", "translation", "hinglish"},
    "business": {"business", "economy", "market", "stock", "loan", "tax", "portfolio", "networth"},
    "utility": {"utility", "avatar", "userinfo", "serverinfo", "poll", "remind", "snipe"},
    "fun": {"fun", "roast", "crush", "vibe", "futureme", "rizz", "serverlore"},
    "music": {"music", "play", "queue", "join", "leave", "skip", "pause", "resume", "spotify", "youtube"},
    "engagement": {"xp", "rank", "leaderboard", "streak", "daily", "quests", "event", "catchup", "insights"},
}
CAPABILITY_INTENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwhat can you do\b", re.IGNORECASE),
    re.compile(r"\bcapabilit(?:y|ies)\b", re.IGNORECASE),
    re.compile(r"\bwhich commands?\b", re.IGNORECASE),
    re.compile(r"\bwhat commands?\b", re.IGNORECASE),
    re.compile(r"\bhow can (?:you|bell)\b", re.IGNORECASE),
    re.compile(r"\bhelp me (?:with|in)\b", re.IGNORECASE),
    re.compile(r"\bhow (?:do|to) (?:i|we)\b", re.IGNORECASE),
)
CAPABILITIES_OVERRIDES_CACHE: dict[str, Any] | None = None
CAPABILITIES_OVERRIDES_CACHE_TS = 0.0
CAPABILITIES_OVERRIDES_CACHE_MTIME = 0.0
CAPABILITIES_CATALOG_CACHE: dict[str, Any] | None = None
CAPABILITIES_CATALOG_CACHE_TS = 0.0
CAPABILITIES_CATALOG_CACHE_MTIME = 0.0
CAPABILITIES_CACHE_TTL_SECONDS = 600.0
SPOTIFY_CLIENT = None
FFMPEG_EXECUTABLE: str | None = None
INDIAN_VEG_MEALS_CACHE: list[dict[str, str]] = []
INDIAN_VEG_MEALS_CACHE_TS = 0.0

SPOTIFY_TRACK_RE = re.compile(
    r"(?:https?://open\.spotify\.com/track/|spotify:track:)([A-Za-z0-9]+)",
    re.IGNORECASE,
)
SPOTIFY_PLAYLIST_RE = re.compile(
    r"(?:https?://open\.spotify\.com/playlist/|spotify:playlist:)([A-Za-z0-9]+)",
    re.IGNORECASE,
)

YTDL_BASE_OPTIONS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": False,
    "source_address": "0.0.0.0",
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -loglevel warning",
}
TIMEOUT_DURATION_RE = re.compile(
    r"\b(\d{1,4})\s*(m|min|mins|minute|minutes)\b",
    re.IGNORECASE,
)
PSYCH_ACTIONS = {"start", "stop", "reset", "status"}
NATURAL_COMMAND_BLOCKLIST = {"ban", "kick"}
PSYCH_CRISIS_PATTERN = re.compile(
    r"\b("
    r"kill myself|suicide|suicidal|end my life|want to die|can't go on|"
    r"hurt myself|self harm|self-harm|cut myself|overdose|harm myself"
    r")\b",
    re.IGNORECASE,
)
PSYCH_SOLUTION_PATTERN = re.compile(
    r"\b("
    r"what should i do|give advice|solution|need a plan|help me with a plan|"
    r"give me a plan|next steps|enough info|now advise|advice please|what now"
    r")\b",
    re.IGNORECASE,
)
TRANSLATION_LOCAL_PHRASES: tuple[tuple[str, str], ...] = (
    ("hinglish sikhao use", "teach them Hinglish"),
    ("hinglish sikhao usse", "teach them Hinglish"),
    ("hinglish sikhao usko", "teach them Hinglish"),
    ("kya haal hai", "how are you"),
    ("kese ho", "how are you"),
    ("kaise ho", "how are you"),
    ("kya kar rahe ho", "what are you doing"),
    ("kya kar rha hai", "what are you doing"),
    ("kya kar rahi ho", "what are you doing"),
    ("main theek hoon", "I am fine"),
    ("mai theek hoon", "I am fine"),
    ("sab theek", "everything is fine"),
    ("theek hai", "okay"),
    ("thik hai", "okay"),
    ("nahi yaar", "no friend"),
    ("haan yaar", "yes friend"),
)
TRANSLATION_LOCAL_WORDS: dict[str, str] = {
    "bhai": "brother",
    "bhaiya": "brother",
    "bro": "brother",
    "behen": "sister",
    "didi": "sister",
    "yaar": "friend",
    "yar": "friend",
    "acha": "okay",
    "accha": "okay",
    "achha": "okay",
    "theek": "fine",
    "thik": "fine",
    "haan": "yes",
    "han": "yes",
    "nahi": "no",
    "nah": "no",
    "kaise": "how",
    "kese": "how",
    "kaisa": "how",
    "kya": "what",
    "kaun": "who",
    "kab": "when",
    "kaha": "where",
    "kahan": "where",
    "ho": "are",
    "hu": "am",
    "hun": "am",
    "main": "I",
    "mai": "I",
    "mera": "my",
    "meri": "my",
    "mere": "my",
    "tera": "your",
    "teri": "your",
    "tere": "your",
    "tum": "you",
    "tu": "you",
    "aap": "you",
    "mujhe": "to me",
    "mujhko": "to me",
    "tujhe": "to you",
    "tumhe": "to you",
    "hum": "we",
    "ham": "we",
    "sab": "everyone",
    "kaam": "work",
    "ghar": "home",
    "jaldi": "quickly",
    "abhi": "right now",
    "kal": "tomorrow",
    "aaj": "today",
    "kyun": "why",
    "kyo": "why",
    "kyon": "why",
    "bolo": "tell me",
    "bol": "say",
    "sikhao": "teach",
    "sikha": "teach",
    "sikhado": "teach",
    "sikha do": "teach",
    "naam": "name",
    "kiya": "did",
    "ki": "did",
    "firse": "again",
    "phirse": "again",
    "isse": "this person",
    "isko": "this person",
    "usse": "them",
    "use": "them",
    "usko": "them",
    "mat": "don't",
    "kar": "do",
    "karo": "do",
    "kr": "do",
    "krna": "do",
    "sun": "listen",
    "sunna": "listen",
    "chalo": "let's go",
    "chal": "go",
    "milte": "meet",
    "baad": "later",
}


@dataclass
class MusicTrack:
    title: str
    webpage_url: str
    requested_by: int


MUSIC_QUEUES: dict[int, deque[MusicTrack]] = defaultdict(deque)
MUSIC_NOW_PLAYING: dict[int, MusicTrack] = {}
MUSIC_TEXT_CHANNELS: dict[int, int] = {}
MUSIC_LOCKS: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
APP_COMMANDS_SYNCED = False
AICRUSH_MESSAGE_AUTHOR_CACHE: dict[int, tuple[int, float]] = {}
ALTFINDER_LOCKS: dict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)
ALTFINDER_RESULT_CACHE: dict[tuple[int, int], tuple[float, str]] = {}
ALTFINDER_CHANNEL_RECENT_AUTHORS: dict[tuple[int, int], deque[tuple[float, int]]] = defaultdict(
    lambda: deque(maxlen=80)
)
SOCIALINTEL_LOCKS: dict[tuple[Any, ...], asyncio.Lock] = defaultdict(asyncio.Lock)
SOCIALINTEL_RESULT_CACHE: dict[tuple[Any, ...], tuple[float, str]] = {}
SOCIALINTEL_CHANNEL_RECENT_AUTHORS: dict[tuple[int, int], deque[tuple[float, int]]] = defaultdict(
    lambda: deque(maxlen=80)
)
ROAST_LOCKS: dict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)
ROAST_RESULT_CACHE: dict[tuple[int, int, str], tuple[float, str]] = {}
CATCHUP_LOCKS: dict[tuple[int, int, int], asyncio.Lock] = defaultdict(asyncio.Lock)
CATCHUP_CACHE: dict[tuple[int, int, int], tuple[float, str]] = {}
INSIGHTS_LOCKS: dict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)
INSIGHTS_CACHE: dict[tuple[int, int], tuple[float, str]] = {}
ANALYZE_LOCKS: dict[tuple[int, int], asyncio.Lock] = defaultdict(asyncio.Lock)
ANALYZE_CACHE: dict[tuple[int, int], tuple[float, str]] = {}
MESSAGE_WINDOW_CACHE: dict[tuple, tuple[float, list["WindowMessage"]]] = {}
MESSAGE_WINDOW_LOCKS: dict[tuple, asyncio.Lock] = defaultdict(asyncio.Lock)
MESSAGE_WINDOW_CACHE_MAX_ENTRIES = 90
FUN_USER_RATE_CACHE: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=40))
FUN_CHANNEL_RATE_CACHE: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=60))
ROAST_RECENT_OUTPUTS: dict[tuple[int, int, str], deque[tuple[float, str]]] = defaultdict(
    lambda: deque(maxlen=8)
)
AUTOMOD_STRIKE_CACHE: dict[tuple[int, int], deque[float]] = defaultdict(lambda: deque(maxlen=12))
WELCOME_ONBOARDING_SESSIONS: dict[tuple[int, int], dict[str, object]] = {}
ENGAGEMENT_STATE: dict[str, object] = {"guilds": {}}
ENGAGEMENT_STATE_DIRTY = False
ENGAGEMENT_STATE_LOCK = asyncio.Lock()
ALTFINDER_STATE: dict[str, Any] = {}
ALTFINDER_STATE_DIRTY = False
ALTFINDER_STATE_LOCK = asyncio.Lock()
SOCIALINTEL_STATE: dict[str, Any] = {}
SOCIALINTEL_STATE_DIRTY = False
SOCIALINTEL_STATE_LOCK = asyncio.Lock()
BUSINESS_STATE: dict[str, Any] = {}
BUSINESS_STATE_DIRTY = False
BUSINESS_STATE_LOCK = asyncio.Lock()
BUSINESS_TICK_LOCK = asyncio.Lock()
BUSINESS_LAST_COMMAND_TS: dict[int, float] = {}
BUSINESS_TX_ROLLBACK_CACHE: dict[str, dict[str, Any]] = {}
BUSINESS_AI_TEXT_CACHE: dict[tuple[str, int, int], tuple[float, str]] = {}
BUSINESS_WORLD_EVENT_CACHE: dict[str, Any] = {"ts": 0.0, "event": None}
BUSINESS_SYMBOL_POOL: list[tuple[str, str, str]] = [
    ("ASTR", "Aster Dynamics", "tech"),
    ("NOVA", "Nova Retail", "consumer"),
    ("SURY", "Surya Energy", "energy"),
    ("KRFT", "KraftMinds", "tech"),
    ("VAAN", "Vaan Logistics", "industrial"),
    ("PRSM", "Prism Media", "media"),
    ("ANVL", "Anvil Manufacturing", "industrial"),
    ("GLDN", "Golden Harvest Foods", "consumer"),
    ("VEDA", "Veda Health", "health"),
    ("RIVR", "Riverline Infra", "infra"),
    ("BOLT", "Bolt Mobility", "auto"),
    ("NEON", "Neon Telecom", "telecom"),
    ("MINT", "Mint Finserv", "finance"),
    ("ORBT", "Orbit Aerospace", "aero"),
    ("TARA", "Tara Textiles", "consumer"),
    ("KITE", "Kite Cloud", "tech"),
    ("RAGA", "Raga Entertainment", "media"),
    ("FERN", "Fern Biotech", "health"),
    ("SPRK", "Spark Utilities", "energy"),
    ("BANY", "Banyan Realty", "realty"),
]
BUSINESS_COMMODITY_POOL: list[tuple[str, str, str, float, float]] = [
    ("GOLD", "Gold Bullion", "metals", 6600.0, 0.012),
    ("OIL", "Crude Oil", "energy", 6200.0, 0.020),
    ("WHEAT", "Wheat", "agri", 1800.0, 0.018),
    ("STEEL", "Steel", "metals", 2600.0, 0.016),
    ("LITH", "Lithium", "battery", 5200.0, 0.024),
    ("COFFEE", "Coffee Beans", "agri", 2300.0, 0.022),
    ("URAN", "Uranium", "energy", 4700.0, 0.026),
]
BUSINESS_CRYPTO_POOL: list[tuple[str, str, float, float]] = [
    ("BITV", "BitVault", 92000.0, 0.055),
    ("NEOX", "NeonX", 6200.0, 0.070),
    ("AUR", "AuroraChain", 1100.0, 0.082),
    ("SPRKX", "SparkX", 380.0, 0.095),
    ("MEMZ", "MemeZ", 42.0, 0.130),
]
ENGAGEMENT_LAST_MESSAGE_CACHE: dict[tuple[int, int], tuple[float, str]] = {}
AUTO_LOOP_POST_HISTORY: dict[int, deque[float]] = defaultdict(lambda: deque(maxlen=80))
CHANNEL_HEAT_EVENTS: dict[tuple[int, int], deque[tuple[float, float]]] = defaultdict(
    lambda: deque(maxlen=80)
)
CHANNEL_HEAT_SLOWMODE_STATE: dict[tuple[int, int], dict[str, float]] = {}
EVENT_MESSAGE_COOLDOWNS: dict[tuple[int, int], float] = {}
EVENT_SESSIONS: dict[int, dict[str, object]] = {}

QUEST_LIBRARY: list[dict[str, object]] = [
    {"id": "chat_5", "name": "Keep Chat Alive", "type": "messages", "target": 5, "reward": 32},
    {"id": "reply_3", "name": "Reply Chain", "type": "replies", "target": 3, "reward": 28},
    {"id": "mention_2", "name": "Tag Teammates", "type": "mentions", "target": 2, "reward": 26},
    {"id": "thread_2", "name": "Thread Builder", "type": "threads", "target": 2, "reward": 34},
    {"id": "long_2", "name": "Deep Thoughts", "type": "long_msgs", "target": 2, "reward": 30},
]

ICEBREAKER_PROMPTS = [
    "What is one tiny win you had today?",
    "Drop your current top 1 song and why it is stuck in your head.",
    "If today had a title, what would it be?",
    "What is one take you would defend in voice chat for 10 minutes?",
    "What is one thing you learned this week that others can use?",
]
DAILY_CHALLENGES = [
    "Share one productivity trick and react to someone else's tip.",
    "Post a screenshot/photo of something that made your day better.",
    "Drop one unpopular opinion and keep it respectful.",
    "Recommend one movie/show and give it a one-line pitch.",
    "Share one goal for today and report back later.",
]
THREAD_REVIVE_PROMPTS = [
    "Quick revive: what changed since this thread was active last time?",
    "Thread reboot: what is your current stance in one line?",
    "One follow-up question to restart this thread: what is the practical next step here?",
]
TRIVIA_PACK = [
    {
        "prompt": "Trivia: Which planet is known as the Red Planet?",
        "answers": {"mars"},
    },
    {
        "prompt": "Trivia: What is the capital city of Japan?",
        "answers": {"tokyo"},
    },
    {
        "prompt": "Trivia: Who wrote Romeo and Juliet?",
        "answers": {"william shakespeare", "shakespeare"},
    },
]
HOTTAKE_TOPICS = [
    "Pineapple belongs on pizza.",
    "Phone calls are better than texting.",
    "Short-form content ruins attention span.",
    "Night shifts are better than morning routines.",
]
CAPTION_PROMPTS = [
    "Caption challenge: describe your current mood as a movie title.",
    "Caption challenge: write the funniest one-line server ad.",
    "Caption challenge: one-liner for a chaotic group photo.",
]


def resolve_ffmpeg_executable() -> str | None:
    configured = (FFMPEG_PATH or "").strip()
    if configured:
        if os.path.isfile(configured):
            return configured
        found_configured = shutil.which(configured)
        if found_configured:
            return found_configured

    found_default = shutil.which("ffmpeg")
    if found_default:
        return found_default

    if imageio_ffmpeg is not None:
        try:
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None
    return None


def _default_capabilities_overrides_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "commands": {
            "automod": {
                "domain": "moderation",
                "summary": "Enable or disable first-line automatic moderation.",
                "mod_only": True,
                "examples": [f"{PREFIX}automod status", f"{PREFIX}automod on"],
                "nl_triggers": ["automod", "auto moderation", "moderation settings"],
            },
            "aiguard": {
                "domain": "moderation",
                "summary": "Configure AI Guard layers and rollout mode.",
                "mod_only": True,
                "examples": [f"{PREFIX}aiguard status", f"{PREFIX}aiguard layer 3"],
                "nl_triggers": ["ai guard", "ai moderation", "moderation capabilities"],
            },
            "aimodmode": {
                "domain": "moderation",
                "summary": "Switch AI moderation between shadow and enforce modes.",
                "mod_only": True,
                "examples": [f"{PREFIX}aimodmode shadow", f"{PREFIX}aimodmode enforce"],
                "nl_triggers": ["shadow mode", "enforce mode", "rollout mode"],
            },
            "mute": {
                "domain": "moderation",
                "summary": "Apply a temporary timeout to a member.",
                "mod_only": True,
                "examples": [f"{PREFIX}mute @user 10 spam"],
                "nl_triggers": ["timeout user", "mute user", "temporarily mute"],
            },
            "ban": {
                "domain": "moderation",
                "summary": "Ban a member from the server.",
                "mod_only": True,
                "examples": [f"{PREFIX}ban @user repeated abuse"],
                "nl_triggers": ["ban user", "remove permanently", "block member"],
            },
            "help": {
                "domain": "utility",
                "summary": "Show a complete command index grouped by features.",
                "mod_only": False,
                "examples": [f"{PREFIX}help"],
                "nl_triggers": ["commands list", "what commands", "show commands"],
            },
            "ai": {
                "domain": "ai",
                "summary": "Ask Bell a direct AI question with channel memory.",
                "mod_only": False,
                "examples": [f"{PREFIX}ai summarize this topic"],
                "nl_triggers": ["ask ai", "chat with bell", "assistant"],
            },
            "translate": {
                "domain": "ai",
                "summary": "Translate mixed-language or Hinglish text into natural English.",
                "mod_only": False,
                "examples": [f"{PREFIX}translate hello bhai kese ho", f"{PREFIX}translate <message link>"],
                "nl_triggers": ["translate this", "convert to english", "hinglish translation"],
            },
        },
        "system_capabilities": [
            {
                "id": "moderation_stack",
                "domain": "moderation",
                "summary": "Bell supports rule-based AutoMod and AI Guard with audit cases, queue review, and appeals.",
                "mod_only": False,
                "examples": ["Ask: bell what are your moderation capabilities"],
                "nl_triggers": ["moderation capabilities", "safety features", "how bell moderates"],
            },
            {
                "id": "capability_assistant",
                "domain": "ai",
                "summary": "Bell can explain commands in natural language and suggest the right next command for a task.",
                "mod_only": False,
                "examples": ["Ask: bell how do I timeout a user", "Ask: bell which command do I use for server insights"],
                "nl_triggers": ["how do i use", "which command", "what can you do"],
            },
        ],
    }


def _default_capabilities_catalog_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": 0.0,
        "commands": {},
        "system_capabilities": [],
    }


def _sanitize_capabilities_overrides_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    base = _default_capabilities_overrides_payload()
    result: dict[str, Any] = {
        "schema_version": int(payload.get("schema_version", base["schema_version"]) or base["schema_version"]),
        "commands": {},
        "system_capabilities": [],
    }
    raw_commands = payload.get("commands")
    if not isinstance(raw_commands, dict):
        raw_commands = {}
    for cmd_name, row in raw_commands.items():
        if not isinstance(row, dict):
            continue
        name = str(cmd_name).strip().lower()
        if not name:
            continue
        domain = str(row.get("domain", "utility")).strip().lower()
        if domain not in CAPABILITY_DOMAINS:
            domain = "utility"
        examples = row.get("examples", [])
        if not isinstance(examples, list):
            examples = []
        triggers = row.get("nl_triggers", [])
        if not isinstance(triggers, list):
            triggers = []
        result["commands"][name] = {
            "domain": domain,
            "summary": str(row.get("summary", "")).strip()[:280],
            "mod_only": bool(row.get("mod_only", False)),
            "examples": [str(item).strip()[:120] for item in examples if str(item).strip()][:5],
            "nl_triggers": [str(item).strip().lower()[:50] for item in triggers if str(item).strip()][:10],
        }
    raw_system = payload.get("system_capabilities")
    if not isinstance(raw_system, list):
        raw_system = []
    for row in raw_system:
        if not isinstance(row, dict):
            continue
        capability_id = str(row.get("id", "")).strip().lower()
        if not capability_id:
            continue
        domain = str(row.get("domain", "utility")).strip().lower()
        if domain not in CAPABILITY_DOMAINS:
            domain = "utility"
        examples = row.get("examples", [])
        if not isinstance(examples, list):
            examples = []
        triggers = row.get("nl_triggers", [])
        if not isinstance(triggers, list):
            triggers = []
        result["system_capabilities"].append(
            {
                "id": capability_id,
                "domain": domain,
                "summary": str(row.get("summary", "")).strip()[:280],
                "mod_only": bool(row.get("mod_only", False)),
                "examples": [str(item).strip()[:120] for item in examples if str(item).strip()][:5],
                "nl_triggers": [str(item).strip().lower()[:50] for item in triggers if str(item).strip()][:10],
            }
        )
    if not result["commands"] and not result["system_capabilities"]:
        return base
    return result


_STORAGE_SEEDED = False
_SEEDED_KEYS = (
    WARNINGS_KEY,
    MOD_CONFIG_KEY,
    AI_MOD_STATE_KEY,
    ENGAGEMENT_STATE_KEY,
    BUSINESS_STATE_KEY,
    ALTFINDER_STATE_KEY,
    SOCIALINTEL_STATE_KEY,
)


def ensure_data_files() -> None:
    global _STORAGE_SEEDED
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not BAD_WORDS_FILE.exists():
        BAD_WORDS_FILE.write_text(
            "# Add one blocked word per line.\n# Lines starting with # are ignored.\n",
            encoding="utf-8",
        )
    # JSON files are re-seeded on every access (as before, so a deleted file comes
    # back); a shared database backend is seeded once per process.
    if STORAGE.shared and _STORAGE_SEEDED:
        return
    for key in _SEEDED_KEYS[:3]:
        STORAGE.ensure_default(key)
    if not STORAGE.exists(CAPABILITIES_OVERRIDES_KEY):
        STORAGE.ensure_default(CAPABILITIES_OVERRIDES_KEY, _default_capabilities_overrides_payload())
    if not STORAGE.exists(CAPABILITIES_CATALOG_KEY):
        STORAGE.ensure_default(CAPABILITIES_CATALOG_KEY, _default_capabilities_catalog_payload())
    for key in _SEEDED_KEYS[3:]:
        STORAGE.ensure_default(key)
    _STORAGE_SEEDED = True


def read_state(key: str) -> dict:
    """The stored document for ``key`` (``{}`` when missing, empty or unreadable)."""
    ensure_data_files()
    return STORAGE.get(key) or {}


def write_state(key: str, payload: dict) -> bool:
    """Persist ``payload`` under ``key``; False if it could not be saved (already logged)."""
    cloned = storage.clone_json_dict(payload)
    ensure_data_files()
    return STORAGE.set(key, cloned)


def load_warnings() -> dict:
    return read_state(WARNINGS_KEY)


def save_warnings(payload: dict) -> None:
    write_state(WARNINGS_KEY, payload)


MOD_CONFIG_CACHE: dict | None = None
MOD_CONFIG_CACHE_TS = 0.0
MOD_CONFIG_CACHE_TTL_SECONDS = 6


def load_mod_config() -> dict:
    global MOD_CONFIG_CACHE, MOD_CONFIG_CACHE_TS
    now = time.monotonic()
    if MOD_CONFIG_CACHE is not None and now - MOD_CONFIG_CACHE_TS < MOD_CONFIG_CACHE_TTL_SECONDS:
        return MOD_CONFIG_CACHE
    config = read_state(MOD_CONFIG_KEY)
    MOD_CONFIG_CACHE = config
    MOD_CONFIG_CACHE_TS = now
    return config


def save_mod_config(payload: dict) -> None:
    global MOD_CONFIG_CACHE, MOD_CONFIG_CACHE_TS
    write_state(MOD_CONFIG_KEY, payload)
    MOD_CONFIG_CACHE = payload
    MOD_CONFIG_CACHE_TS = time.monotonic()


def _default_ai_mod_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "cases": {},
        "appeals": {},
        "review_actions": [],
        "user_risk": {},
        "metrics": {
            "evaluated": 0,
            "cases_created": 0,
            "enforced": 0,
            "overrides": 0,
            "appeals": 0,
        },
        "meta": {
            "next_case": 1,
            "next_appeal": 1,
            "last_prune_ts": 0.0,
        },
    }


def _sanitize_ai_mod_state(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    base = _default_ai_mod_state()
    for key in ("schema_version", "cases", "appeals", "review_actions", "user_risk", "metrics", "meta"):
        if key not in payload:
            payload[key] = base[key]
    if not isinstance(payload["cases"], dict):
        payload["cases"] = {}
    if not isinstance(payload["appeals"], dict):
        payload["appeals"] = {}
    if not isinstance(payload["review_actions"], list):
        payload["review_actions"] = []
    if not isinstance(payload["user_risk"], dict):
        payload["user_risk"] = {}
    if not isinstance(payload["metrics"], dict):
        payload["metrics"] = dict(base["metrics"])
    if not isinstance(payload["meta"], dict):
        payload["meta"] = dict(base["meta"])
    payload["meta"]["next_case"] = max(1, int(payload["meta"].get("next_case", 1) or 1))
    payload["meta"]["next_appeal"] = max(1, int(payload["meta"].get("next_appeal", 1) or 1))
    payload["meta"]["last_prune_ts"] = float(payload["meta"].get("last_prune_ts", 0.0) or 0.0)
    for key, default_value in base["metrics"].items():
        payload["metrics"][key] = int(payload["metrics"].get(key, default_value) or default_value)
    return payload


def load_ai_mod_state() -> None:
    global AI_MOD_STATE, AI_MOD_STATE_DIRTY
    payload = read_state(AI_MOD_STATE_KEY)
    AI_MOD_STATE = _sanitize_ai_mod_state(payload)
    AI_MOD_STATE_DIRTY = False


def get_ai_mod_state() -> dict[str, Any]:
    global AI_MOD_STATE
    if not AI_MOD_STATE:
        AI_MOD_STATE = _default_ai_mod_state()
        _mark_ai_mod_dirty()
    AI_MOD_STATE = _sanitize_ai_mod_state(AI_MOD_STATE)
    return AI_MOD_STATE


def _mark_ai_mod_dirty() -> None:
    global AI_MOD_STATE_DIRTY
    AI_MOD_STATE_DIRTY = True


async def flush_ai_mod_state(force: bool = False) -> None:
    global AI_MOD_STATE_DIRTY
    if not force and not AI_MOD_STATE_DIRTY:
        return
    async with AI_MOD_STATE_LOCK:
        if not force and not AI_MOD_STATE_DIRTY:
            return
        try:
            persisted = write_state(AI_MOD_STATE_KEY, AI_MOD_STATE)
            if persisted:
                AI_MOD_STATE_DIRTY = False
        except Exception:
            pass


def _ai_mod_next_case_id() -> str:
    state = get_ai_mod_state()
    current = int(state["meta"].get("next_case", 1) or 1)
    state["meta"]["next_case"] = current + 1
    _mark_ai_mod_dirty()
    return f"CASE-{current:06d}"


def _ai_mod_next_appeal_id() -> str:
    state = get_ai_mod_state()
    current = int(state["meta"].get("next_appeal", 1) or 1)
    state["meta"]["next_appeal"] = current + 1
    _mark_ai_mod_dirty()
    return f"APL-{current:06d}"


def _ai_mod_increment_metric(metric: str, amount: int = 1) -> None:
    if amount == 0:
        return
    state = get_ai_mod_state()
    metrics = state.setdefault("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
        state["metrics"] = metrics
    metrics[metric] = int(metrics.get(metric, 0) or 0) + int(amount)
    _mark_ai_mod_dirty()


def _ai_mod_normalize_category(raw: object) -> str:
    text = str(raw or "").strip().lower()
    aliases = {
        "safe_other": "safe",
        "safe/other": "safe",
        "safe": "safe",
        "none": "safe",
        "spam": "spam_flood",
        "flood": "spam_flood",
        "spam_flood": "spam_flood",
        "harassment": "harassment_toxic",
        "toxicity": "harassment_toxic",
        "toxic": "harassment_toxic",
        "harassment_toxic": "harassment_toxic",
        "scam": "scam_phishing",
        "phishing": "scam_phishing",
        "fraud": "scam_phishing",
        "scam_phishing": "scam_phishing",
        "raid": "raid_behavior",
        "raid_behavior": "raid_behavior",
    }
    normalized = aliases.get(text, text)
    if normalized not in AI_MOD_CATEGORIES:
        return "safe"
    return normalized


def _ai_mod_normalize_action(raw: object) -> str:
    text = str(raw or "").strip().lower()
    if text not in AI_MOD_ACTIONS:
        return "none"
    return text


def _ai_mod_risk_score(raw: object) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, value))


def _ai_mod_confidence_band(score: float) -> str:
    if score >= 0.95:
        return "extreme"
    if score >= 0.86:
        return "very_high"
    if score >= 0.72:
        return "high"
    if score >= 0.56:
        return "medium"
    return "low"


def _ai_mod_get_thresholds(strictness: str) -> dict[str, float]:
    normalized = strictness.strip().lower()
    if normalized not in AI_MOD_THRESHOLDS_BY_STRICTNESS:
        normalized = "moderate_strict"
    return dict(AI_MOD_THRESHOLDS_BY_STRICTNESS[normalized])


def _ai_mod_stage_b_threshold(strictness: str) -> float:
    normalized = strictness.strip().lower()
    if normalized not in AI_MOD_STAGE_B_TRIGGER_BY_STRICTNESS:
        normalized = "moderate_strict"
    return float(AI_MOD_STAGE_B_TRIGGER_BY_STRICTNESS.get(normalized, 0.63))


def _ai_mod_effective_mode(guild_id: int) -> tuple[str, bool]:
    configured = get_guild_ai_guard_mode(guild_id)
    enabled_since = get_guild_ai_guard_enabled_since(guild_id)
    if configured == "enforce" and enabled_since > 0 and AI_MOD_SHADOW_DAYS > 0:
        age = time.time() - enabled_since
        if age < (AI_MOD_SHADOW_DAYS * 86400):
            return "shadow", True
    return configured, False


def _ai_mod_trim_timestamps(queue: deque[float], window_seconds: float) -> None:
    now = time.monotonic()
    while queue and now - queue[0] > window_seconds:
        queue.popleft()


def _ai_mod_extract_domains(text: str) -> list[str]:
    found: set[str] = set()
    for match in AI_MOD_DOMAIN_RE.finditer(text):
        domain = (match.group(1) or "").strip().lower()
        if not domain:
            continue
        if domain.startswith("www."):
            domain = domain[4:]
        found.add(domain)
    return sorted(found)


def _ai_mod_message_fingerprint(text: str) -> str:
    lowered = text.lower()
    lowered = AI_MOD_URL_RE.sub(" ", lowered)
    lowered = re.sub(r"<@!?\d+>", " @user ", lowered)
    lowered = re.sub(r"<#\d+>", " #channel ", lowered)
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\d", "0", lowered)
    tokens = [tok for tok in WORD_PATTERN.findall(lowered) if len(tok) >= 2]
    basis = " ".join(tokens[:28]) if tokens else lowered.strip()[:140]
    if not basis:
        basis = "empty"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _ai_mod_normalize_hinglish(content: str) -> tuple[str, list[str]]:
    tokens = WORD_PATTERN.findall(content.lower())
    normalized: list[str] = []
    tags: list[str] = []
    for token in tokens:
        mapped = AI_MOD_HINGLISH_NORMALIZE_MAP.get(token, token)
        normalized.append(mapped)
        if mapped != token and len(tags) < 8:
            tags.append(f"hinglish:{token}->{mapped}")
    return " ".join(normalized), tags


def _ai_mod_heuristic_payload(
    content: str,
    normalized_text: str,
    *,
    corroborators: dict[str, Any],
) -> dict[str, Any]:
    lowered = content.lower()
    normalized = normalized_text.lower()
    tags: list[str] = []
    category = "safe"
    score = 0.05
    suggested = "none"

    scam_hits = sum(1 for hint in AI_MOD_SCAM_HINTS if hint in lowered or hint in normalized)
    abuse_hits = sum(1 for hint in AI_MOD_ABUSE_HINTS if hint in lowered or hint in normalized)
    spam_hits = sum(1 for hint in AI_MOD_SPAM_HINTS if hint in lowered or hint in normalized)
    has_link = bool(LINK_PATTERN.search(content))
    has_many_mentions = len(re.findall(r"<@!?\d+>", content)) >= 4
    repeated_chars = bool(re.search(r"(.)\1{6,}", content))
    upper_ratio = (sum(1 for ch in content if ch.isupper()) / max(1, len(content))) if content else 0.0

    if has_link and scam_hits >= 1:
        category = "scam_phishing"
        score = 0.78 + min(0.20, scam_hits * 0.05)
        tags.extend(["link_present", "scam_pattern"])
    elif abuse_hits >= 2 or "kill yourself" in lowered:
        category = "harassment_toxic"
        score = 0.72 + min(0.18, abuse_hits * 0.04)
        tags.append("abusive_pattern")
    elif spam_hits >= 2 or has_many_mentions or repeated_chars or upper_ratio > 0.75:
        category = "spam_flood"
        score = 0.68 + min(0.15, spam_hits * 0.03)
        tags.append("spam_pattern")

    if bool(corroborators.get("cross_channel_spread")) and bool(corroborators.get("repeated_fingerprint")):
        category = "raid_behavior"
        score = max(score, 0.88)
        tags.append("cross_channel_spread")
    if bool(corroborators.get("new_account_burst")) and (
        bool(corroborators.get("repeated_domain_cluster")) or bool(corroborators.get("repeated_fingerprint"))
    ):
        category = "raid_behavior"
        score = max(score, 0.92)
        tags.append("new_account_burst")
    if category == "scam_phishing" and bool(corroborators.get("repeated_domain_cluster")):
        score = max(score, 0.90)
        tags.append("domain_cluster")

    if category == "safe":
        suggested = "none"
    elif score >= 0.86:
        suggested = "timeout"
    elif score >= 0.72:
        suggested = "delete"
    elif score >= 0.56:
        suggested = "warn"
    return {
        "category": category,
        "risk_score": max(0.0, min(0.99, score)),
        "confidence": score,
        "confidence_band": _ai_mod_confidence_band(score),
        "rationale_tags": tags[:6],
        "suggested_action": suggested,
        "language_mix": "en_hinglish",
        "is_raid_suspected": bool(category == "raid_behavior"),
        "is_scam_suspected": bool(category == "scam_phishing"),
    }


def _ai_mod_parse_llm_payload(payload: object, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return dict(fallback)
    category = _ai_mod_normalize_category(payload.get("category"))
    risk_score = _ai_mod_risk_score(payload.get("risk_score"))
    confidence = _ai_mod_risk_score(payload.get("confidence", risk_score))
    suggested = _ai_mod_normalize_action(payload.get("suggested_action"))
    tags_raw = payload.get("rationale_tags", [])
    tags: list[str] = []
    if isinstance(tags_raw, list):
        for item in tags_raw:
            cleaned = str(item).strip().lower()
            if cleaned and cleaned not in tags:
                tags.append(cleaned[:40])
            if len(tags) >= 6:
                break
    if category == "safe":
        suggested = "none"
    if risk_score <= 0.02 and category != "safe":
        risk_score = max(risk_score, 0.08)
    return {
        "category": category,
        "risk_score": risk_score,
        "confidence": confidence,
        "confidence_band": _ai_mod_confidence_band(risk_score),
        "rationale_tags": tags or list(fallback.get("rationale_tags", [])),
        "suggested_action": suggested,
        "language_mix": str(payload.get("language_mix", "en_hinglish")).strip()[:24],
        "is_raid_suspected": bool(payload.get("is_raid_suspected", category == "raid_behavior")),
        "is_scam_suspected": bool(payload.get("is_scam_suspected", category == "scam_phishing")),
        "explanation": str(payload.get("explanation", "")).strip()[:220],
    }


def _ai_mod_layer_allowed_actions(layer: int) -> set[str]:
    if layer <= 1:
        return set()
    if layer == 2:
        return {"warn"}
    if layer == 3:
        return {"warn", "delete", "timeout"}
    if layer == 4:
        return {"warn", "delete", "timeout", "kick", "ban"}
    return {"warn", "delete", "timeout", "kick", "ban"}


def _ai_mod_trim_user_history(entries: list[dict[str, Any]], cutoff_ts: float) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for row in entries:
        if not isinstance(row, dict):
            continue
        ts = float(row.get("ts", 0.0) or 0.0)
        if ts < cutoff_ts:
            continue
        kept.append(row)
    return kept[-120:]


def _ai_mod_record_user_risk(
    guild_id: int,
    user_id: int,
    *,
    case_id: str,
    category: str,
    risk_score: float,
    confidence_band: str,
    action: str,
) -> None:
    state = get_ai_mod_state()
    key = f"{guild_id}:{user_id}"
    user_risk = state.setdefault("user_risk", {})
    if not isinstance(user_risk, dict):
        user_risk = {}
        state["user_risk"] = user_risk
    row = user_risk.get(key)
    if not isinstance(row, dict):
        row = {"history": []}
        user_risk[key] = row
    history = row.get("history")
    if not isinstance(history, list):
        history = []
        row["history"] = history
    history.append(
        {
            "ts": time.time(),
            "case_id": case_id,
            "category": category,
            "risk_score": round(float(risk_score), 4),
            "confidence_band": confidence_band,
            "action": action,
        }
    )
    cutoff = time.time() - (AI_MOD_RETENTION_DAYS * 86400)
    row["history"] = _ai_mod_trim_user_history(history, cutoff)
    _mark_ai_mod_dirty()


def _ai_mod_recent_user_incidents(
    guild_id: int,
    user_id: int,
    *,
    days: int,
) -> list[dict[str, Any]]:
    state = get_ai_mod_state()
    user_risk = state.get("user_risk", {})
    if not isinstance(user_risk, dict):
        return []
    row = user_risk.get(f"{guild_id}:{user_id}")
    if not isinstance(row, dict):
        return []
    history = row.get("history")
    if not isinstance(history, list):
        return []
    cutoff = time.time() - (max(1, days) * 86400)
    output: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        ts = float(item.get("ts", 0.0) or 0.0)
        if ts >= cutoff:
            output.append(item)
    return output


def _ai_mod_severe_repeat_offender(guild_id: int, user_id: int) -> bool:
    incidents = _ai_mod_recent_user_incidents(guild_id, user_id, days=7)
    if len(incidents) < 3:
        return False
    severe = 0
    for item in incidents:
        risk = _ai_mod_risk_score(item.get("risk_score"))
        action = str(item.get("action", "none"))
        if risk >= 0.82 or action in {"timeout", "kick", "ban"}:
            severe += 1
    return severe >= 2


def _ai_mod_case_cap_prune(state: dict[str, Any]) -> None:
    cases = state.get("cases", {})
    if not isinstance(cases, dict):
        return
    if len(cases) <= AI_MOD_MAX_CASES:
        return
    ordered = sorted(
        cases.items(),
        key=lambda item: float(item[1].get("created_ts", 0.0) if isinstance(item[1], dict) else 0.0),
    )
    overflow = len(cases) - AI_MOD_MAX_CASES
    for case_id, _ in ordered[:overflow]:
        cases.pop(case_id, None)
    _mark_ai_mod_dirty()


def _ai_mod_create_case(
    message: discord.Message,
    *,
    stage_a: dict[str, Any],
    stage_b: dict[str, Any] | None,
    category: str,
    risk_score: float,
    confidence_band: str,
    rationale_tags: list[str],
    suggested_action: str,
    final_action: str,
    mode: str,
    layer: int,
    corroborators: dict[str, Any],
    normalized_text: str,
) -> str:
    state = get_ai_mod_state()
    case_id = _ai_mod_next_case_id()
    now_ts = time.time()
    evidence_text = " ".join(message.clean_content.split()).strip()[:850]
    case_record = {
        "id": case_id,
        "guild_id": int(message.guild.id),
        "channel_id": int(message.channel.id),
        "message_id": int(message.id),
        "author_id": int(message.author.id),
        "created_ts": now_ts,
        "updated_ts": now_ts,
        "status": "open" if mode == "enforce" else "shadow",
        "category": category,
        "risk_score": round(risk_score, 4),
        "confidence_band": confidence_band,
        "rationale_tags": rationale_tags[:8],
        "suggested_action": suggested_action,
        "action": final_action,
        "mode": mode,
        "layer": int(layer),
        "language_profile": get_guild_ai_guard_language_profile(message.guild.id),
        "message_excerpt": evidence_text,
        "normalized_excerpt": normalized_text[:450],
        "message_jump_url": message.jump_url,
        "corroborators": corroborators,
        "stage_a": stage_a,
        "stage_b": stage_b,
        "review": {"override_action": None, "reviewer_id": None, "review_note": "", "updated_ts": 0.0},
        "appeal_ids": [],
    }
    state_cases = state.setdefault("cases", {})
    if not isinstance(state_cases, dict):
        state_cases = {}
        state["cases"] = state_cases
    state_cases[case_id] = case_record
    _ai_mod_increment_metric("cases_created")
    _ai_mod_record_user_risk(
        message.guild.id,
        message.author.id,
        case_id=case_id,
        category=category,
        risk_score=risk_score,
        confidence_band=confidence_band,
        action=final_action,
    )
    _ai_mod_case_cap_prune(state)
    _mark_ai_mod_dirty()
    return case_id


def _ai_mod_case(case_id: str) -> dict[str, Any] | None:
    state = get_ai_mod_state()
    cases = state.get("cases", {})
    if not isinstance(cases, dict):
        return None
    row = cases.get(case_id.upper().strip())
    if not isinstance(row, dict):
        return None
    return row


def _ai_mod_open_cases_for_guild(guild_id: int) -> list[dict[str, Any]]:
    state = get_ai_mod_state()
    cases = state.get("cases", {})
    if not isinstance(cases, dict):
        return []
    rows: list[dict[str, Any]] = []
    for case in cases.values():
        if not isinstance(case, dict):
            continue
        if int(case.get("guild_id", 0) or 0) != guild_id:
            continue
        status = str(case.get("status", "open")).lower()
        if status in {"closed", "resolved", "dismissed"}:
            continue
        rows.append(case)
    rows.sort(key=lambda row: float(row.get("created_ts", 0.0) or 0.0), reverse=True)
    return rows


def _ai_mod_register_corroborator_signals(message: discord.Message) -> dict[str, Any]:
    now_mono = time.monotonic()
    guild_id = message.guild.id
    user_id = message.author.id
    domains = _ai_mod_extract_domains(message.content)
    fingerprint = _ai_mod_message_fingerprint(message.content)

    for domain in domains:
        dq = AI_MOD_RECENT_LINK_EVENTS[(guild_id, domain)]
        dq.append(now_mono)
        _ai_mod_trim_timestamps(dq, 240.0)

    fingerprint_queue = AI_MOD_RECENT_FINGERPRINT_EVENTS[(guild_id, fingerprint)]
    fingerprint_queue.append((now_mono, user_id, message.channel.id))
    while fingerprint_queue and now_mono - fingerprint_queue[0][0] > 240.0:
        fingerprint_queue.popleft()

    new_account_days = max(
        0.0,
        (discord.utils.utcnow() - message.author.created_at).total_seconds() / 86400.0,
    )
    if new_account_days <= 7.0:
        account_dq = AI_MOD_RECENT_NEW_ACCOUNT_EVENTS[guild_id]
        account_dq.append((now_mono, user_id))
        while account_dq and now_mono - account_dq[0][0] > 180.0:
            account_dq.popleft()

    repeated_domain_cluster = False
    max_domain_count = 0
    for domain in domains:
        dq = AI_MOD_RECENT_LINK_EVENTS[(guild_id, domain)]
        _ai_mod_trim_timestamps(dq, 240.0)
        max_domain_count = max(max_domain_count, len(dq))
        if len(dq) >= 4:
            repeated_domain_cluster = True

    unique_users = {row[1] for row in fingerprint_queue}
    unique_channels = {row[2] for row in fingerprint_queue}
    repeated_fingerprint = len(fingerprint_queue) >= 4 and len(unique_users) >= 2
    cross_channel_spread = len(unique_channels) >= 2 and len(fingerprint_queue) >= 4

    account_queue = AI_MOD_RECENT_NEW_ACCOUNT_EVENTS.get(guild_id, deque())
    unique_new_users = {row[1] for row in account_queue}
    new_account_burst = len(unique_new_users) >= 4

    corroborator_count = 0
    for flag in (
        new_account_burst,
        repeated_domain_cluster,
        repeated_fingerprint,
        cross_channel_spread,
    ):
        if flag:
            corroborator_count += 1
    return {
        "domains": domains[:6],
        "fingerprint": fingerprint,
        "max_domain_count": max_domain_count,
        "fingerprint_hits": len(fingerprint_queue),
        "fingerprint_user_count": len(unique_users),
        "fingerprint_channel_count": len(unique_channels),
        "new_account_days": round(new_account_days, 2),
        "new_account_burst": new_account_burst,
        "repeated_domain_cluster": repeated_domain_cluster,
        "repeated_fingerprint": repeated_fingerprint,
        "cross_channel_spread": cross_channel_spread,
        "corroborator_count": corroborator_count,
    }


def _ai_mod_pick_matrix_actions(
    category: str,
    risk_score: float,
    *,
    strictness: str,
) -> list[str]:
    thresholds = _ai_mod_get_thresholds(strictness)
    high = thresholds["high"]
    very_high = thresholds["very_high"]
    if category in {"spam_flood", "harassment_toxic"}:
        if risk_score >= very_high:
            return ["delete", "timeout"]
        if risk_score >= high:
            return ["delete"]
    if category in {"scam_phishing", "raid_behavior"}:
        if risk_score >= high:
            return ["delete", "timeout"]
    if risk_score >= 0.56 and category != "safe":
        return ["warn"]
    return []


def _ai_mod_allow_autoban(
    *,
    category: str,
    risk_score: float,
    strictness: str,
    layer: int,
    allowed_actions: set[str],
    corroborators: dict[str, Any],
) -> bool:
    if layer < 4 or "ban" not in allowed_actions:
        return False
    if category not in {"scam_phishing", "raid_behavior"}:
        return False
    thresholds = _ai_mod_get_thresholds(strictness)
    if risk_score < thresholds["extreme"]:
        return False
    corroborator_count = int(corroborators.get("corroborator_count", 0) or 0)
    if corroborator_count < 2:
        return False
    if not (
        bool(corroborators.get("repeated_fingerprint"))
        or bool(corroborators.get("cross_channel_spread"))
        or bool(corroborators.get("repeated_domain_cluster"))
    ):
        return False
    return True


def _ai_mod_select_actions(
    *,
    guild_id: int,
    user_id: int,
    category: str,
    risk_score: float,
    strictness: str,
    layer: int,
    allowed_actions: set[str],
    corroborators: dict[str, Any],
) -> list[str]:
    if layer <= 1:
        return []
    layer_allowed = _ai_mod_layer_allowed_actions(layer)
    enabled_allowed = layer_allowed.intersection(allowed_actions)
    actions = _ai_mod_pick_matrix_actions(category, risk_score, strictness=strictness)

    if layer == 2:
        if risk_score >= 0.56 and category != "safe" and "warn" in enabled_allowed:
            return ["warn"]
        return []

    if _ai_mod_allow_autoban(
        category=category,
        risk_score=risk_score,
        strictness=strictness,
        layer=layer,
        allowed_actions=enabled_allowed,
        corroborators=corroborators,
    ):
        actions = ["delete", "ban"]
    elif layer >= 4 and _ai_mod_severe_repeat_offender(guild_id, user_id):
        thresholds = _ai_mod_get_thresholds(strictness)
        if risk_score >= thresholds["very_high"]:
            actions = ["delete", "timeout", "kick"]
    if not actions and category != "safe" and risk_score >= 0.56:
        actions = ["warn"]

    deduped: list[str] = []
    for action in AI_MOD_ACTION_ORDER:
        if action in actions and action in enabled_allowed:
            deduped.append(action)
    return deduped


def _ai_mod_timeout_minutes(category: str, confidence_band: str) -> int:
    if confidence_band == "extreme":
        return 60
    if category in {"scam_phishing", "raid_behavior"}:
        return 30 if confidence_band in {"very_high", "extreme"} else 20
    if confidence_band == "very_high":
        return 20
    if confidence_band == "high":
        return 10
    return 5


async def _ai_mod_notify_action(
    message: discord.Message,
    *,
    case_id: str,
    category: str,
    confidence_band: str,
    action_text: str,
) -> None:
    notify_policy = get_guild_ai_guard_notify_policy(message.guild.id)
    category_label = category.replace("_", "/")
    text = (
        f"AI Guard action: `{category_label}` | confidence `{confidence_band}` | "
        f"case `{case_id}` | action `{action_text}`.\n"
        f"To appeal: `{PREFIX}appeal {case_id} <reason>`."
    )
    if notify_policy in {"channel_only", "channel_and_dm"}:
        try:
            await message.channel.send(f"{message.author.mention} {text}", delete_after=20)
        except discord.HTTPException:
            pass
    if notify_policy in {"dm_only", "channel_and_dm"}:
        try:
            await message.author.send(text)
        except discord.HTTPException:
            pass


async def _ai_mod_apply_actions(
    message: discord.Message,
    *,
    case_id: str,
    category: str,
    confidence_band: str,
    actions: list[str],
) -> tuple[list[str], list[str]]:
    if not actions:
        return [], []
    guild = message.guild
    member = message.author if isinstance(message.author, discord.Member) else None
    me = guild.me
    applied: list[str] = []
    notes: list[str] = []

    if "delete" in actions:
        try:
            await message.delete()
            applied.append("delete")
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            notes.append("delete_failed")

    can_moderate_member = (
        member is not None
        and me is not None
        and member != guild.owner
        and member.top_role < me.top_role
        and not member.guild_permissions.administrator
    )

    if "timeout" in actions:
        if me is None or not me.guild_permissions.moderate_members or not can_moderate_member:
            notes.append("timeout_no_permission")
        else:
            try:
                minutes = _ai_mod_timeout_minutes(category, confidence_band)
                until = discord.utils.utcnow() + timedelta(minutes=minutes)
                await member.timeout(until, reason=f"AI Guard case {case_id}: {category}")
                applied.append("timeout")
            except discord.HTTPException:
                notes.append("timeout_failed")

    if "kick" in actions:
        if me is None or not me.guild_permissions.kick_members or not can_moderate_member:
            notes.append("kick_no_permission")
        else:
            try:
                await member.kick(reason=f"AI Guard case {case_id}: repeat severe behavior")
                applied.append("kick")
            except discord.HTTPException:
                notes.append("kick_failed")

    if "ban" in actions:
        if me is None or not me.guild_permissions.ban_members or not can_moderate_member:
            notes.append("ban_no_permission")
        else:
            try:
                await member.ban(reason=f"AI Guard case {case_id}: raid/scam extreme confidence")
                applied.append("ban")
            except discord.HTTPException:
                notes.append("ban_failed")

    if "warn" in actions:
        applied.append("warn")
        try:
            await message.channel.send(
                f"{message.author.mention} Please stop. This message is flagged by AI Guard.",
                delete_after=15,
            )
        except discord.HTTPException:
            pass

    return applied, notes


async def _ai_mod_run_stage_a(
    message: discord.Message,
    *,
    normalized_text: str,
    language_profile: str,
    corroborators: dict[str, Any],
) -> dict[str, Any]:
    fallback = _ai_mod_heuristic_payload(message.content, normalized_text, corroborators=corroborators)
    prompt = (
        "Classify this Discord message risk.\n"
        "Return JSON only.\n"
        f"Allowed categories: {AI_MOD_STAGE_A_CATEGORIES}\n"
        "Keep rationale_tags concise.\n"
        f"Language profile: {language_profile}\n"
        f"Message: {message.clean_content[:1200]}\n"
        f"Normalized message: {normalized_text[:900]}\n"
        f"Corroborators: {json.dumps(corroborators)[:600]}"
    )
    ai_messages = [
        {"role": "system", "content": AI_MOD_FAST_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    try:
        raw = await request_ai_completion(
            ai_messages,
            max_tokens=180,
            temperature=0.15,
            policy_key="ai_mod_fast",
            model_override=AI_MOD_FAST_MODEL or None,
        )
        payload = _extract_first_json_object(raw)
        parsed = _ai_mod_parse_llm_payload(payload, fallback)
        parsed["raw"] = raw[:800]
        return parsed
    except Exception:
        fallback["raw"] = ""
        return fallback


async def _ai_mod_run_stage_b(
    message: discord.Message,
    *,
    normalized_text: str,
    language_profile: str,
    stage_a: dict[str, Any],
    corroborators: dict[str, Any],
) -> dict[str, Any]:
    fallback = dict(stage_a)
    prompt = (
        "You are moderation judge pass.\n"
        "Re-evaluate with higher precision and lower false positives.\n"
        "Return JSON only.\n"
        f"Allowed categories: {AI_MOD_STAGE_A_CATEGORIES}\n"
        f"Language profile: {language_profile}\n"
        f"Message: {message.clean_content[:1400]}\n"
        f"Normalized: {normalized_text[:1000]}\n"
        f"StageA: {json.dumps(stage_a)[:900]}\n"
        f"Corroborators: {json.dumps(corroborators)[:700]}"
    )
    ai_messages = [
        {"role": "system", "content": AI_MOD_JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    try:
        raw = await request_ai_completion(
            ai_messages,
            max_tokens=260,
            temperature=0.1,
            policy_key="ai_mod_judge",
            model_override=AI_MOD_JUDGE_MODEL or None,
        )
        payload = _extract_first_json_object(raw)
        parsed = _ai_mod_parse_llm_payload(payload, fallback)
        parsed["raw"] = raw[:1000]
        return parsed
    except Exception:
        fallback["raw"] = ""
        return fallback


def _ai_mod_should_evaluate(message: discord.Message) -> bool:
    if message.guild is None or message.author.bot:
        return False
    if message.content.startswith(PREFIX):
        return False
    if not get_guild_ai_guard_enabled(message.guild.id):
        return False
    if get_guild_ai_guard_layer(message.guild.id) <= 0:
        return False
    if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
        return False
    if not message.content.strip():
        return False
    return True


async def maybe_run_ai_guard(message: discord.Message) -> bool:
    if not _ai_mod_should_evaluate(message):
        return False
    if isinstance(message.author, discord.Member) and is_moderator(message.author):
        return False

    _ai_mod_increment_metric("evaluated")
    guild_id = message.guild.id
    layer = get_guild_ai_guard_layer(guild_id)
    strictness = get_guild_ai_guard_strictness(guild_id)
    mode, forced_shadow = _ai_mod_effective_mode(guild_id)
    language_profile = get_guild_ai_guard_language_profile(guild_id)
    allowed_actions = get_guild_ai_guard_allowed_actions(guild_id)
    normalized_text, lexicon_tags = _ai_mod_normalize_hinglish(message.content)
    corroborators = _ai_mod_register_corroborator_signals(message)

    stage_a = await _ai_mod_run_stage_a(
        message,
        normalized_text=normalized_text,
        language_profile=language_profile,
        corroborators=corroborators,
    )
    stage_a_risk = _ai_mod_risk_score(stage_a.get("risk_score"))
    stage_b = None
    if stage_a_risk >= _ai_mod_stage_b_threshold(strictness):
        stage_b = await _ai_mod_run_stage_b(
            message,
            normalized_text=normalized_text,
            language_profile=language_profile,
            stage_a=stage_a,
            corroborators=corroborators,
        )

    final = stage_b or stage_a
    category = _ai_mod_normalize_category(final.get("category"))
    risk_score = _ai_mod_risk_score(final.get("risk_score"))
    confidence_band = _ai_mod_confidence_band(risk_score)
    rationale_tags = list(final.get("rationale_tags", []))
    if lexicon_tags:
        rationale_tags = [*rationale_tags, *lexicon_tags][:8]
    suggested_action = _ai_mod_normalize_action(final.get("suggested_action"))
    if category == "safe" and risk_score < 0.56:
        return False
    actions = _ai_mod_select_actions(
        guild_id=guild_id,
        user_id=message.author.id,
        category=category,
        risk_score=risk_score,
        strictness=strictness,
        layer=layer,
        allowed_actions=allowed_actions,
        corroborators=corroborators,
    )
    final_action = "+".join(actions) if actions else "none"
    if mode == "shadow":
        actions = []
    case_id = _ai_mod_create_case(
        message,
        stage_a=stage_a,
        stage_b=stage_b,
        category=category,
        risk_score=risk_score,
        confidence_band=confidence_band,
        rationale_tags=rationale_tags,
        suggested_action=suggested_action,
        final_action=final_action,
        mode=mode,
        layer=layer,
        corroborators=corroborators,
        normalized_text=normalized_text,
    )
    case = _ai_mod_case(case_id)
    if case is None:
        return False
    if forced_shadow:
        case["shadow_forced"] = True
        case["status"] = "shadow"
    applied_actions: list[str] = []
    apply_notes: list[str] = []
    if mode == "enforce" and actions:
        applied_actions, apply_notes = await _ai_mod_apply_actions(
            message,
            case_id=case_id,
            category=category,
            confidence_band=confidence_band,
            actions=actions,
        )
        if applied_actions:
            _ai_mod_increment_metric("enforced")
            action_key = (guild_id, message.author.id)
            history = AI_MOD_RECENT_ACTIONS[action_key]
            history.append(time.monotonic())
            _ai_mod_trim_timestamps(history, 86400.0)

    case["updated_ts"] = time.time()
    case["applied_actions"] = applied_actions
    case["apply_notes"] = apply_notes
    case["status"] = "actioned" if applied_actions else case.get("status", "open")
    _mark_ai_mod_dirty()

    action_text = "+".join(applied_actions) if applied_actions else ("shadow_only" if mode == "shadow" else "none")
    log_channel = message.channel.parent if isinstance(message.channel, discord.Thread) else message.channel
    if mode == "enforce" and applied_actions:
        await _ai_mod_notify_action(
            message,
            case_id=case_id,
            category=category,
            confidence_band=confidence_band,
            action_text=action_text,
        )
        await send_mod_log(
            message.guild,
            "AI Guard Enforcement",
            target=message.author,
            moderator=bot.user,
            reason=f"{category} ({confidence_band})",
            channel=log_channel,
            details=f"Case: `{case_id}` | Risk: `{risk_score:.2f}` | Actions: `{action_text}`",
        )
    elif mode == "shadow":
        await send_mod_log(
            message.guild,
            "AI Guard Shadow Case",
            target=message.author,
            moderator=bot.user,
            reason=f"{category} ({confidence_band})",
            channel=log_channel,
            details=f"Case: `{case_id}` | Risk: `{risk_score:.2f}` | Suggested: `{final_action}`",
        )

    # Unsafe messages should not continue to normal conversational fallback.
    if category != "safe" and risk_score >= 0.56:
        return True
    return False


async def prune_ai_mod_retention() -> None:
    state = get_ai_mod_state()
    now_ts = time.time()
    cutoff = now_ts - (AI_MOD_RETENTION_DAYS * 86400)
    changed = False

    cases = state.get("cases", {})
    if isinstance(cases, dict):
        for case_id in list(cases.keys()):
            case = cases.get(case_id)
            if not isinstance(case, dict):
                cases.pop(case_id, None)
                changed = True
                continue
            created_ts = float(case.get("created_ts", 0.0) or 0.0)
            if created_ts < cutoff:
                cases.pop(case_id, None)
                changed = True

    appeals = state.get("appeals", {})
    if isinstance(appeals, dict):
        for appeal_id in list(appeals.keys()):
            appeal = appeals.get(appeal_id)
            if not isinstance(appeal, dict):
                appeals.pop(appeal_id, None)
                changed = True
                continue
            created_ts = float(appeal.get("created_ts", 0.0) or 0.0)
            if created_ts < cutoff:
                appeals.pop(appeal_id, None)
                changed = True

    review_actions = state.get("review_actions", [])
    if isinstance(review_actions, list):
        fresh = []
        for row in review_actions:
            if not isinstance(row, dict):
                continue
            ts = float(row.get("ts", 0.0) or 0.0)
            if ts >= cutoff:
                fresh.append(row)
        if len(fresh) != len(review_actions):
            state["review_actions"] = fresh
            changed = True

    user_risk = state.get("user_risk", {})
    if isinstance(user_risk, dict):
        for key in list(user_risk.keys()):
            row = user_risk.get(key)
            if not isinstance(row, dict):
                user_risk.pop(key, None)
                changed = True
                continue
            history = row.get("history", [])
            if not isinstance(history, list):
                user_risk.pop(key, None)
                changed = True
                continue
            filtered = _ai_mod_trim_user_history(history, cutoff)
            if filtered:
                if filtered != history:
                    row["history"] = filtered
                    changed = True
            else:
                user_risk.pop(key, None)
                changed = True

    _ai_mod_case_cap_prune(state)
    state_meta = state.setdefault("meta", {})
    if isinstance(state_meta, dict):
        state_meta["last_prune_ts"] = now_ts
    if changed:
        _mark_ai_mod_dirty()


async def maybe_send_ai_guard_report(guild: discord.Guild) -> None:
    if not get_guild_ai_guard_enabled(guild.id):
        return
    if get_guild_ai_guard_layer(guild.id) != 1:
        return
    report_channel_id = get_guild_ai_guard_report_channel_id(guild.id)
    if not report_channel_id:
        return
    report_channel = guild.get_channel(report_channel_id)
    if not isinstance(report_channel, discord.TextChannel):
        return
    interval_minutes = get_guild_ai_guard_report_interval_minutes(guild.id)
    now_mono = time.monotonic()
    last_ts = AI_MOD_REPORT_LAST_TS.get(guild.id, 0.0)
    if now_mono - last_ts < interval_minutes * 60:
        return

    window_seconds = interval_minutes * 60
    cutoff_ts = time.time() - window_seconds
    state = get_ai_mod_state()
    cases = state.get("cases", {})
    total = 0
    severe = 0
    by_category: Counter[str] = Counter()
    if isinstance(cases, dict):
        for row in cases.values():
            if not isinstance(row, dict):
                continue
            if int(row.get("guild_id", 0) or 0) != guild.id:
                continue
            created_ts = float(row.get("created_ts", 0.0) or 0.0)
            if created_ts < cutoff_ts:
                continue
            total += 1
            category = _ai_mod_normalize_category(row.get("category"))
            by_category[category] += 1
            if _ai_mod_risk_score(row.get("risk_score")) >= 0.86:
                severe += 1
    if total == 0:
        AI_MOD_REPORT_LAST_TS[guild.id] = now_mono
        return
    category_text = ", ".join(f"{key}:{value}" for key, value in by_category.most_common(5))
    mode, forced_shadow = _ai_mod_effective_mode(guild.id)
    note = " (shadow forced by rollout window)" if forced_shadow else ""
    message_text = (
        f"AI Guard L1 report ({interval_minutes}m)\n"
        f"- Total cases: `{total}`\n"
        f"- Severe (`>=0.86`): `{severe}`\n"
        f"- Categories: {category_text or 'n/a'}\n"
        f"- Effective mode: `{mode}`{note}"
    )
    try:
        await report_channel.send(message_text)
        AI_MOD_REPORT_LAST_TS[guild.id] = now_mono
    except discord.HTTPException:
        return


async def run_ai_mod_tick() -> None:
    await prune_ai_mod_retention()
    for guild in bot.guilds:
        try:
            await maybe_send_ai_guard_report(guild)
        except Exception as error:
            print(f"[AI GUARD REPORT ERROR] guild={guild.id} error={error}")


def reload_bad_words() -> int:
    ensure_data_files()
    global BAD_WORDS
    if not BAD_WORDS_FILE.exists():
        BAD_WORDS = set()
        return 0
    try:
        lines = BAD_WORDS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        BAD_WORDS = set()
        return 0
    words: set[str] = set()
    for line in lines:
        cleaned = line.strip().lower()
        if cleaned and not cleaned.startswith("#"):
            words.add(cleaned)
    BAD_WORDS = words
    return len(BAD_WORDS)


def get_guild_mod_log_channel_id(guild_id: int) -> int | None:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    channel_id = guild_config.get("mod_log_channel_id")
    if isinstance(channel_id, int):
        return channel_id
    if isinstance(channel_id, str) and channel_id.isdigit():
        return int(channel_id)
    return ENV_MOD_LOG_CHANNEL_ID


def get_guild_automod_enabled(guild_id: int) -> bool:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    value = guild_config.get("automod_enabled")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enabled"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled"}:
            return False
    return AUTO_MOD_ENABLED


def set_guild_automod_enabled(guild_id: int, enabled: bool) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["automod_enabled"] = bool(enabled)
    save_mod_config(config)


def get_guild_fun_mode(guild_id: int) -> str:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    raw = str(guild_config.get("fun_mode", "spicy")).strip().lower()
    if raw not in {"spicy", "balanced", "wholesome"}:
        return "spicy"
    return raw


def set_guild_fun_mode(guild_id: int, mode: str) -> None:
    normalized = mode.strip().lower()
    if normalized not in {"spicy", "balanced", "wholesome"}:
        normalized = "spicy"
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["fun_mode"] = normalized
    save_mod_config(config)


def get_guild_engagement_limits_enabled(guild_id: int) -> bool:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    value = guild_config.get("engagement_limits_enabled")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enabled"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled"}:
            return False
    return True


def set_guild_engagement_limits_enabled(guild_id: int, enabled: bool) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["engagement_limits_enabled"] = bool(enabled)
    save_mod_config(config)


def get_guild_moderation_escalation_enabled(guild_id: int) -> bool:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    value = guild_config.get("moderation_escalation_enabled")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enabled"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled"}:
            return False
    return True


def set_guild_moderation_escalation_enabled(guild_id: int, enabled: bool) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["moderation_escalation_enabled"] = bool(enabled)
    save_mod_config(config)


def get_guild_ai_guard_enabled(guild_id: int) -> bool:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    parsed = _read_optional_bool(guild_config.get("ai_guard_enabled"))
    if parsed is None:
        return AI_MOD_ENABLED_DEFAULT
    return parsed


def set_guild_ai_guard_enabled(guild_id: int, enabled: bool) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["ai_guard_enabled"] = bool(enabled)
    if enabled:
        config[guild_key]["ai_guard_enabled_ts"] = time.time()
    save_mod_config(config)


def get_guild_ai_guard_enabled_since(guild_id: int) -> float:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    raw = guild_config.get("ai_guard_enabled_ts")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def get_guild_ai_guard_layer(guild_id: int) -> int:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    raw = guild_config.get("ai_guard_layer", 0)
    try:
        return max(0, min(5, int(raw)))
    except (TypeError, ValueError):
        return 0


def set_guild_ai_guard_layer(guild_id: int, layer: int) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["ai_guard_layer"] = max(0, min(5, int(layer)))
    save_mod_config(config)


def get_guild_ai_guard_mode(guild_id: int) -> str:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    raw = str(guild_config.get("ai_guard_mode", "shadow")).strip().lower()
    if raw not in {"shadow", "enforce"}:
        return "shadow"
    return raw


def set_guild_ai_guard_mode(guild_id: int, mode: str) -> None:
    normalized = mode.strip().lower()
    if normalized not in {"shadow", "enforce"}:
        normalized = "shadow"
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["ai_guard_mode"] = normalized
    save_mod_config(config)


def get_guild_ai_guard_strictness(guild_id: int) -> str:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    raw = str(guild_config.get("ai_guard_strictness", "moderate_strict")).strip().lower()
    if raw not in {"moderate", "moderate_strict", "strict"}:
        return "moderate_strict"
    return raw


def set_guild_ai_guard_strictness(guild_id: int, strictness: str) -> None:
    normalized = strictness.strip().lower()
    if normalized not in {"moderate", "moderate_strict", "strict"}:
        normalized = "moderate_strict"
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["ai_guard_strictness"] = normalized
    save_mod_config(config)


def get_guild_ai_guard_allowed_actions(guild_id: int) -> set[str]:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    raw = guild_config.get("ai_guard_allowed_actions")
    if not isinstance(raw, list):
        return {"warn", "delete", "timeout", "kick", "ban"}
    allowed: set[str] = set()
    for item in raw:
        text = str(item).strip().lower()
        if text in {"warn", "delete", "timeout", "kick", "ban"}:
            allowed.add(text)
    if not allowed:
        return {"warn", "delete", "timeout", "kick", "ban"}
    return allowed


def set_guild_ai_guard_allowed_actions(guild_id: int, actions: set[str]) -> None:
    clean = sorted(
        action
        for action in actions
        if action in {"warn", "delete", "timeout", "kick", "ban"}
    )
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["ai_guard_allowed_actions"] = clean
    save_mod_config(config)


def get_guild_ai_guard_report_channel_id(guild_id: int) -> int | None:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    channel_id = guild_config.get("ai_guard_report_channel_id")
    if isinstance(channel_id, int):
        return channel_id
    if isinstance(channel_id, str) and channel_id.isdigit():
        return int(channel_id)
    return None


def set_guild_ai_guard_report_channel_id(guild_id: int, channel_id: int | None) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    if channel_id is None:
        config[guild_key].pop("ai_guard_report_channel_id", None)
    else:
        config[guild_key]["ai_guard_report_channel_id"] = int(channel_id)
    save_mod_config(config)


def get_guild_ai_guard_report_interval_minutes(guild_id: int) -> int:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    raw = guild_config.get("ai_guard_report_interval_minutes", 30)
    try:
        return max(5, min(180, int(raw)))
    except (TypeError, ValueError):
        return 30


def set_guild_ai_guard_report_interval_minutes(guild_id: int, minutes: int) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["ai_guard_report_interval_minutes"] = max(5, min(180, int(minutes)))
    save_mod_config(config)


def get_guild_ai_guard_appeals_enabled(guild_id: int) -> bool:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    parsed = _read_optional_bool(guild_config.get("ai_guard_appeals_enabled"))
    if parsed is None:
        return True
    return parsed


def set_guild_ai_guard_appeals_enabled(guild_id: int, enabled: bool) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["ai_guard_appeals_enabled"] = bool(enabled)
    save_mod_config(config)


def get_guild_ai_guard_notify_policy(guild_id: int) -> str:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    raw = str(guild_config.get("ai_guard_notify_policy", "channel_and_dm")).strip().lower()
    if raw not in {"channel_only", "dm_only", "channel_and_dm"}:
        return "channel_and_dm"
    return raw


def set_guild_ai_guard_notify_policy(guild_id: int, policy: str) -> None:
    normalized = policy.strip().lower()
    if normalized not in {"channel_only", "dm_only", "channel_and_dm"}:
        normalized = "channel_and_dm"
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["ai_guard_notify_policy"] = normalized
    save_mod_config(config)


def get_guild_ai_guard_language_profile(guild_id: int) -> str:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    raw = str(guild_config.get("ai_guard_language_profile", "en_hinglish")).strip().lower()
    if raw not in {"en", "en_hinglish"}:
        return "en_hinglish"
    return raw


def set_guild_ai_guard_language_profile(guild_id: int, profile: str) -> None:
    normalized = profile.strip().lower()
    if normalized not in {"en", "en_hinglish"}:
        normalized = "en_hinglish"
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["ai_guard_language_profile"] = normalized
    save_mod_config(config)


def get_guild_welcome_concierge_enabled(guild_id: int) -> bool:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    value = guild_config.get("welcome_concierge_enabled")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enabled"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled"}:
            return False
    return WELCOME_CONCIERGE_ENABLED


def set_guild_welcome_concierge_enabled(guild_id: int, enabled: bool) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["welcome_concierge_enabled"] = bool(enabled)
    save_mod_config(config)


def get_guild_intro_channel_id(guild_id: int) -> int | None:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    channel_id = guild_config.get("intro_channel_id")
    if isinstance(channel_id, int):
        return channel_id
    if isinstance(channel_id, str) and channel_id.isdigit():
        return int(channel_id)
    return None


def set_guild_intro_channel_id(guild_id: int, channel_id: int | None) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    if channel_id is None:
        config[guild_key].pop("intro_channel_id", None)
    else:
        config[guild_key]["intro_channel_id"] = int(channel_id)
    save_mod_config(config)


def _read_optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enabled"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled"}:
            return False
    return None


def get_guild_engagement_hub_channel_id(guild_id: int) -> int | None:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    channel_id = guild_config.get("engagement_hub_channel_id")
    if isinstance(channel_id, int):
        return channel_id
    if isinstance(channel_id, str) and channel_id.isdigit():
        return int(channel_id)
    return None


def set_guild_engagement_hub_channel_id(guild_id: int, channel_id: int | None) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    if channel_id is None:
        config[guild_key].pop("engagement_hub_channel_id", None)
    else:
        config[guild_key]["engagement_hub_channel_id"] = int(channel_id)
    save_mod_config(config)


def get_guild_auto_loops_enabled(guild_id: int) -> bool:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    parsed = _read_optional_bool(guild_config.get("auto_loops_enabled"))
    if parsed is None:
        return AUTO_LOOPS_ENABLED
    return parsed


def set_guild_auto_loops_enabled(guild_id: int, enabled: bool) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["auto_loops_enabled"] = bool(enabled)
    save_mod_config(config)


def get_guild_engagement_timezone(guild_id: int) -> str:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    raw = str(guild_config.get("engagement_timezone", "UTC")).strip()
    if not raw:
        return "UTC"
    return raw


def set_guild_engagement_timezone(guild_id: int, tz_name: str) -> None:
    normalized = (tz_name or "UTC").strip() or "UTC"
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["engagement_timezone"] = normalized
    save_mod_config(config)


def get_guild_modguard_enabled(guild_id: int) -> bool:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    parsed = _read_optional_bool(guild_config.get("modguard_enabled"))
    if parsed is None:
        return True
    return parsed


def set_guild_modguard_enabled(guild_id: int, enabled: bool) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["modguard_enabled"] = bool(enabled)
    save_mod_config(config)


def get_guild_quest_mode_enabled(guild_id: int) -> bool:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    parsed = _read_optional_bool(guild_config.get("quest_mode_enabled"))
    if parsed is None:
        return True
    return parsed


def set_guild_quest_mode_enabled(guild_id: int, enabled: bool) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["quest_mode_enabled"] = bool(enabled)
    save_mod_config(config)


def get_guild_business_enabled(guild_id: int) -> bool:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    parsed = _read_optional_bool(guild_config.get("business_enabled"))
    if parsed is None:
        return BUSINESS_ENABLED
    return parsed


def set_guild_business_enabled(guild_id: int, enabled: bool) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["business_enabled"] = bool(enabled)
    save_mod_config(config)


def get_guild_business_market_paused(guild_id: int) -> bool:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    parsed = _read_optional_bool(guild_config.get("business_market_paused"))
    if parsed is None:
        return False
    return parsed


def set_guild_business_market_paused(guild_id: int, paused: bool) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["business_market_paused"] = bool(paused)
    save_mod_config(config)


def get_guild_business_moderation_enabled(guild_id: int) -> bool:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    parsed = _read_optional_bool(guild_config.get("business_moderation_enabled"))
    if parsed is None:
        return True
    return parsed


def set_guild_business_moderation_enabled(guild_id: int, enabled: bool) -> None:
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    config[guild_key]["business_moderation_enabled"] = bool(enabled)
    save_mod_config(config)


def get_guild_business_tax_overrides(guild_id: int) -> dict[str, float]:
    config = load_mod_config()
    guild_config = config.get(str(guild_id), {})
    raw = guild_config.get("business_tax_overrides")
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, float] = {}
    for key in ("transaction_fee_rate", "property_tax_rate", "property_maintenance_rate"):
        try:
            value = float(raw.get(key))
        except (TypeError, ValueError):
            continue
        parsed[key] = max(0.0, value)
    return parsed


def set_guild_business_tax_overrides(guild_id: int, payload: dict[str, float]) -> None:
    clean: dict[str, float] = {}
    for key in ("transaction_fee_rate", "property_tax_rate", "property_maintenance_rate"):
        if key not in payload:
            continue
        try:
            clean[key] = max(0.0, float(payload[key]))
        except (TypeError, ValueError):
            continue
    config = load_mod_config()
    guild_key = str(guild_id)
    config.setdefault(guild_key, {})
    if clean:
        config[guild_key]["business_tax_overrides"] = clean
    else:
        config[guild_key].pop("business_tax_overrides", None)
    save_mod_config(config)


def matches_bad_word(content: str) -> str | None:
    if not BAD_WORDS:
        return None
    words = WORD_PATTERN.findall(content.lower())
    for word in words:
        if word in BAD_WORDS:
            return word
    return None


async def send_mod_log(
    guild: discord.Guild,
    action: str,
    *,
    target: discord.abc.User | None = None,
    moderator: discord.abc.User | None = None,
    reason: str | None = None,
    channel: discord.abc.GuildChannel | None = None,
    details: str | None = None,
) -> None:
    channel_id = get_guild_mod_log_channel_id(guild.id)
    if not channel_id:
        return

    log_channel = guild.get_channel(channel_id)
    if not isinstance(log_channel, discord.TextChannel):
        return

    embed = discord.Embed(
        title="Moderation Log",
        color=discord.Color.orange(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Action", value=action, inline=False)
    if target is not None:
        embed.add_field(name="Target", value=f"{target} (`{target.id}`)", inline=False)
    if moderator is not None:
        embed.add_field(name="Moderator", value=f"{moderator} (`{moderator.id}`)", inline=False)
    if channel is not None:
        embed.add_field(name="Channel", value=channel.mention, inline=False)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    if details:
        embed.add_field(name="Details", value=details, inline=False)

    try:
        await log_channel.send(embed=embed)
    except discord.HTTPException:
        pass


async def fetch_json_response(session: aiohttp.ClientSession, url: str) -> dict | list:
    async with session.get(url) as response:
        raw = await response.text()
        if response.status >= 400:
            raise RuntimeError(f"API error `{response.status}` from `{url}`.")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON response from `{url}`.") from exc


async def fetch_random_cat_image_url() -> str:
    timeout = aiohttp.ClientTimeout(total=18)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        payload = await fetch_json_response(session, CAT_API_URL)

    if not isinstance(payload, list) or not payload:
        raise RuntimeError("No cat images returned from API.")
    first = payload[0]
    if not isinstance(first, dict):
        raise RuntimeError("Unexpected cat API payload format.")
    url = first.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise RuntimeError("Cat API did not return a usable image URL.")
    return url


async def get_indian_veg_meals() -> list[dict[str, str]]:
    global INDIAN_VEG_MEALS_CACHE_TS, INDIAN_VEG_MEALS_CACHE
    now = time.monotonic()
    if INDIAN_VEG_MEALS_CACHE and now - INDIAN_VEG_MEALS_CACHE_TS < MEAL_CACHE_TTL_SECONDS:
        return INDIAN_VEG_MEALS_CACHE

    indian_url = f"{MEALDB_BASE_URL}/filter.php?a=Indian"
    vegetarian_url = f"{MEALDB_BASE_URL}/filter.php?c=Vegetarian"

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        indian_payload, vegetarian_payload = await asyncio.gather(
            fetch_json_response(session, indian_url),
            fetch_json_response(session, vegetarian_url),
        )

    indian_meals = indian_payload.get("meals") if isinstance(indian_payload, dict) else None
    vegetarian_meals = (
        vegetarian_payload.get("meals") if isinstance(vegetarian_payload, dict) else None
    )
    if not isinstance(indian_meals, list) or not isinstance(vegetarian_meals, list):
        raise RuntimeError("Food API returned invalid data.")

    vegetarian_by_id: dict[str, dict] = {}
    for meal in vegetarian_meals:
        if not isinstance(meal, dict):
            continue
        meal_id = str(meal.get("idMeal") or "").strip()
        if meal_id:
            vegetarian_by_id[meal_id] = meal

    merged: list[dict[str, str]] = []
    for meal in indian_meals:
        if not isinstance(meal, dict):
            continue
        meal_id = str(meal.get("idMeal") or "").strip()
        if not meal_id or meal_id not in vegetarian_by_id:
            continue

        backup = vegetarian_by_id[meal_id]
        name = str(meal.get("strMeal") or backup.get("strMeal") or "Unknown dish").strip()
        thumb = str(meal.get("strMealThumb") or backup.get("strMealThumb") or "").strip()
        if not thumb.startswith(("http://", "https://")):
            continue
        merged.append({"id": meal_id, "name": name, "thumb": thumb})

    if not merged:
        raise RuntimeError("No Indian vegetarian meals found in API response.")

    INDIAN_VEG_MEALS_CACHE = merged
    INDIAN_VEG_MEALS_CACHE_TS = now
    return INDIAN_VEG_MEALS_CACHE


async def send_random_cat_image(channel: discord.abc.Messageable) -> None:
    try:
        image_url = await fetch_random_cat_image_url()
    except Exception:
        await channel.send("Could not fetch a cat image right now. Try again in a few seconds.")
        return

    embed = discord.Embed(title="Cute Random Cat", color=discord.Color.magenta())
    embed.set_image(url=image_url)
    await channel.send(embed=embed)


async def send_random_indian_veg_food(channel: discord.abc.Messageable) -> None:
    try:
        meals = await get_indian_veg_meals()
    except Exception:
        await channel.send("Could not fetch Indian veg food images right now. Try again in a few seconds.")
        return

    meal = random.choice(meals)
    embed = discord.Embed(
        title=f"Indian Veg Pick: {meal['name']}",
        color=discord.Color.orange(),
    )
    embed.set_image(url=meal["thumb"])
    await channel.send(embed=embed)


def has_active_timeout(member: discord.Member) -> bool:
    if hasattr(member, "is_timed_out"):
        try:
            return bool(member.is_timed_out())
        except Exception:
            pass
    until = getattr(member, "timed_out_until", None)
    return bool(until and until > discord.utils.utcnow())


async def remove_timeout_from_dm_request(user_id: int) -> tuple[int, int, int]:
    removed = 0
    active_found = 0
    failed = 0

    for guild in bot.guilds:
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue
        if not isinstance(member, discord.Member):
            continue
        if not has_active_timeout(member):
            continue

        active_found += 1
        me = guild.me
        if me is None and bot.user is not None:
            try:
                me = await guild.fetch_member(bot.user.id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                me = None

        if me is None or not me.guild_permissions.moderate_members:
            failed += 1
            continue
        if member == guild.owner or member.top_role >= me.top_role:
            failed += 1
            continue

        try:
            await member.timeout(None, reason="User requested timeout removal via DM.")
            removed += 1
            await send_mod_log(
                guild,
                "Self Unmute via DM",
                target=member,
                moderator=bot.user,
                reason="User DMed `remove timeout`.",
                details="Timeout removed by DM self-service flow.",
            )
        except discord.HTTPException:
            failed += 1

    return removed, active_found, failed


def is_moderator(member: discord.Member) -> bool:
    perms = member.guild_permissions
    return (
        perms.administrator
        or perms.manage_messages
        or perms.moderate_members
        or perms.kick_members
        or perms.ban_members
        or perms.manage_channels
    )


def resolve_style_for_fun_mode(
    guild_id: int, requested_style: Literal["soft", "friendly", "brutal"]
) -> Literal["soft", "friendly", "brutal"]:
    mode = get_guild_fun_mode(guild_id)
    if mode == "wholesome":
        return "friendly" if requested_style == "brutal" else "soft"
    if mode == "balanced":
        return "friendly" if requested_style == "brutal" else requested_style
    return requested_style


def _trim_time_queue(queue: deque[float], window_seconds: int) -> None:
    now = time.monotonic()
    while queue and now - queue[0] > window_seconds:
        queue.popleft()


def consume_fun_command_quota(
    guild_id: int,
    user_id: int,
    channel_id: int,
) -> tuple[bool, str | None]:
    if not get_guild_engagement_limits_enabled(guild_id):
        return True, None

    user_key = (guild_id, user_id)
    channel_key = (guild_id, channel_id)
    user_queue = FUN_USER_RATE_CACHE[user_key]
    channel_queue = FUN_CHANNEL_RATE_CACHE[channel_key]
    _trim_time_queue(user_queue, FUN_USER_RATE_WINDOW_SECONDS)
    _trim_time_queue(channel_queue, FUN_CHANNEL_RATE_WINDOW_SECONDS)

    if len(user_queue) >= FUN_USER_RATE_MAX_CALLS:
        return (
            False,
            f"Slow down a bit - max `{FUN_USER_RATE_MAX_CALLS}` fun commands per "
            f"`{FUN_USER_RATE_WINDOW_SECONDS}s` per user.",
        )
    if len(channel_queue) >= FUN_CHANNEL_RATE_MAX_CALLS:
        return (
            False,
            f"This channel is rate-limited for fun commands right now "
            f"(`{FUN_CHANNEL_RATE_MAX_CALLS}` per `{FUN_CHANNEL_RATE_WINDOW_SECONDS}s`).",
        )

    now = time.monotonic()
    user_queue.append(now)
    channel_queue.append(now)
    return True, None


async def enforce_fun_rate_limit_ctx(ctx: commands.Context) -> bool:
    if ctx.guild is None:
        return True
    allowed, error_text = consume_fun_command_quota(ctx.guild.id, ctx.author.id, ctx.channel.id)
    if allowed:
        return True
    try:
        await ctx.send(error_text, delete_after=5)
    except discord.HTTPException:
        pass
    return False


async def enforce_fun_rate_limit_message(message: discord.Message) -> bool:
    if message.guild is None:
        return True
    allowed, error_text = consume_fun_command_quota(
        message.guild.id, message.author.id, message.channel.id
    )
    if allowed:
        return True
    try:
        await message.channel.send(error_text, delete_after=5)
    except discord.HTTPException:
        pass
    return False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_zoneinfo(tz_name: str | None) -> ZoneInfo:
    if not tz_name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _guild_now(guild_id: int) -> datetime:
    tz_name = get_guild_engagement_timezone(guild_id)
    return _utc_now().astimezone(_safe_zoneinfo(tz_name))


def _guild_day_key(guild_id: int) -> str:
    return _guild_now(guild_id).strftime("%Y-%m-%d")


def _guild_week_key(guild_id: int) -> str:
    now = _guild_now(guild_id)
    return f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"


def _default_user_engagement_state() -> dict[str, object]:
    return {
        "xp": 0,
        "streak": 0,
        "best_streak": 0,
        "last_active_ts": 0.0,
        "daily": {"day": "", "xp": 0},
        "weekly": {"key": "", "points": 0},
        "quest": {"day": "", "progress": {}, "completed": []},
        "event_points": 0,
    }


def load_engagement_state() -> None:
    global ENGAGEMENT_STATE, ENGAGEMENT_STATE_DIRTY
    payload = read_state(ENGAGEMENT_STATE_KEY)
    if not payload:
        payload = {"guilds": {}}
    if not isinstance(payload, dict):
        payload = {"guilds": {}}
    guilds = payload.get("guilds")
    if not isinstance(guilds, dict):
        guilds = {}
    ENGAGEMENT_STATE = {"guilds": guilds}
    ENGAGEMENT_STATE_DIRTY = False


def _mark_engagement_dirty() -> None:
    global ENGAGEMENT_STATE_DIRTY
    ENGAGEMENT_STATE_DIRTY = True


async def flush_engagement_state(force: bool = False) -> None:
    global ENGAGEMENT_STATE_DIRTY
    if not force and not ENGAGEMENT_STATE_DIRTY:
        return
    async with ENGAGEMENT_STATE_LOCK:
        if not force and not ENGAGEMENT_STATE_DIRTY:
            return
        try:
            persisted = write_state(ENGAGEMENT_STATE_KEY, ENGAGEMENT_STATE)
            if persisted:
                ENGAGEMENT_STATE_DIRTY = False
        except Exception:
            pass


def _default_altfinder_state() -> dict[str, Any]:
    return {"schema_version": 1, "guilds": {}}


def _sanitize_altfinder_suspects(raw: Any) -> dict[str, list[int]]:
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, list[int]] = {}
    for key, value in raw.items():
        if not isinstance(value, list):
            continue
        suspect_ids: list[int] = []
        for item in value:
            try:
                suspect_id = int(item)
            except (TypeError, ValueError):
                continue
            if suspect_id not in suspect_ids:
                suspect_ids.append(suspect_id)
            if len(suspect_ids) >= ALTFINDER_MAX_SUSPECTS:
                break
        if suspect_ids:
            cleaned[str(key)] = suspect_ids
    return cleaned


def _sanitize_altfinder_state(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    guilds = payload.get("guilds")
    if not isinstance(guilds, dict):
        guilds = {}
    sanitized: dict[str, Any] = {"schema_version": 1, "guilds": {}}
    for guild_key, raw_guild in guilds.items():
        if not isinstance(raw_guild, dict):
            continue
        clean_guild = {
            "channels": raw_guild.get("channels", {}) if isinstance(raw_guild.get("channels"), dict) else {},
            "users": raw_guild.get("users", {}) if isinstance(raw_guild.get("users"), dict) else {},
            "meta": raw_guild.get("meta", {}) if isinstance(raw_guild.get("meta"), dict) else {},
            "suspects": _sanitize_altfinder_suspects(raw_guild.get("suspects", {})),
        }
        sanitized["guilds"][str(guild_key)] = clean_guild
    return sanitized


def load_altfinder_state() -> None:
    global ALTFINDER_STATE, ALTFINDER_STATE_DIRTY
    payload = read_state(ALTFINDER_STATE_KEY)
    if not payload:
        payload = _default_altfinder_state()
    ALTFINDER_STATE = _sanitize_altfinder_state(payload)
    ALTFINDER_STATE_DIRTY = False


def get_altfinder_state() -> dict[str, Any]:
    global ALTFINDER_STATE
    if not ALTFINDER_STATE:
        ALTFINDER_STATE = _default_altfinder_state()
        _mark_altfinder_dirty()
    ALTFINDER_STATE = _sanitize_altfinder_state(ALTFINDER_STATE)
    return ALTFINDER_STATE


def _mark_altfinder_dirty() -> None:
    global ALTFINDER_STATE_DIRTY
    ALTFINDER_STATE_DIRTY = True


async def flush_altfinder_state(force: bool = False) -> None:
    global ALTFINDER_STATE_DIRTY
    if not force and not ALTFINDER_STATE_DIRTY:
        return
    async with ALTFINDER_STATE_LOCK:
        if not force and not ALTFINDER_STATE_DIRTY:
            return
        try:
            persisted = write_state(ALTFINDER_STATE_KEY, ALTFINDER_STATE)
            if persisted:
                ALTFINDER_STATE_DIRTY = False
        except Exception:
            pass


def get_guild_altfinder_state(guild_id: int) -> dict[str, Any]:
    state = get_altfinder_state()
    guilds = state.setdefault("guilds", {})
    if not isinstance(guilds, dict):
        guilds = {}
        state["guilds"] = guilds
    key = str(guild_id)
    guild_state = guilds.get(key)
    if not isinstance(guild_state, dict):
        guild_state = {"channels": {}, "users": {}, "meta": {}, "suspects": {}}
        guilds[key] = guild_state
        _mark_altfinder_dirty()
    for field in ("channels", "users", "meta", "suspects"):
        if not isinstance(guild_state.get(field), dict):
            guild_state[field] = {}
    meta = guild_state["meta"]
    meta.setdefault("messages_indexed", 0)
    meta.setdefault("last_backfill_ts", 0.0)
    meta.setdefault("last_incremental_ts", 0.0)
    meta.setdefault("last_indexed_message_ts", 0.0)
    return guild_state


def get_altfinder_suspects(guild_id: int, target_user_id: int) -> list[int]:
    guild_state = get_guild_altfinder_state(guild_id)
    suspects = guild_state.get("suspects", {})
    if not isinstance(suspects, dict):
        return []
    raw = suspects.get(str(target_user_id), [])
    if not isinstance(raw, list):
        return []
    output: list[int] = []
    for item in raw:
        try:
            suspect_id = int(item)
        except (TypeError, ValueError):
            continue
        if suspect_id not in output:
            output.append(suspect_id)
        if len(output) >= ALTFINDER_MAX_SUSPECTS:
            break
    return output


def set_altfinder_suspects(guild_id: int, target_user_id: int, suspect_ids: list[int]) -> None:
    guild_state = get_guild_altfinder_state(guild_id)
    suspects = guild_state.setdefault("suspects", {})
    cleaned: list[int] = []
    for suspect_id in suspect_ids:
        if suspect_id == target_user_id or suspect_id in cleaned:
            continue
        cleaned.append(int(suspect_id))
        if len(cleaned) >= ALTFINDER_MAX_SUSPECTS:
            break
    if cleaned:
        suspects[str(target_user_id)] = cleaned
    else:
        suspects.pop(str(target_user_id), None)
    _mark_altfinder_dirty()
    _altfinder_invalidate_guild_cache(guild_id)


def clear_altfinder_suspects(guild_id: int, target_user_id: int) -> None:
    guild_state = get_guild_altfinder_state(guild_id)
    suspects = guild_state.setdefault("suspects", {})
    suspects.pop(str(target_user_id), None)
    _mark_altfinder_dirty()
    _altfinder_invalidate_guild_cache(guild_id)


def _default_socialintel_state() -> dict[str, Any]:
    return {"schema_version": 1, "guilds": {}}


def _sanitize_socialintel_state(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    guilds = payload.get("guilds")
    if not isinstance(guilds, dict):
        guilds = {}
    sanitized: dict[str, Any] = {"schema_version": 1, "guilds": {}}
    for guild_key, raw_guild in guilds.items():
        if not isinstance(raw_guild, dict):
            continue
        clean_guild = {
            "channels": raw_guild.get("channels", {}) if isinstance(raw_guild.get("channels"), dict) else {},
            "users": raw_guild.get("users", {}) if isinstance(raw_guild.get("users"), dict) else {},
            "pairs": raw_guild.get("pairs", {}) if isinstance(raw_guild.get("pairs"), dict) else {},
            "meta": raw_guild.get("meta", {}) if isinstance(raw_guild.get("meta"), dict) else {},
        }
        sanitized["guilds"][str(guild_key)] = clean_guild
    return sanitized


def load_socialintel_state() -> None:
    global SOCIALINTEL_STATE, SOCIALINTEL_STATE_DIRTY
    payload = read_state(SOCIALINTEL_STATE_KEY)
    if not payload:
        payload = _default_socialintel_state()
    SOCIALINTEL_STATE = _sanitize_socialintel_state(payload)
    SOCIALINTEL_STATE_DIRTY = False


def get_socialintel_state() -> dict[str, Any]:
    global SOCIALINTEL_STATE
    if not SOCIALINTEL_STATE:
        SOCIALINTEL_STATE = _default_socialintel_state()
        _mark_socialintel_dirty()
    SOCIALINTEL_STATE = _sanitize_socialintel_state(SOCIALINTEL_STATE)
    return SOCIALINTEL_STATE


def _mark_socialintel_dirty() -> None:
    global SOCIALINTEL_STATE_DIRTY
    SOCIALINTEL_STATE_DIRTY = True


async def flush_socialintel_state(force: bool = False) -> None:
    global SOCIALINTEL_STATE_DIRTY
    if not force and not SOCIALINTEL_STATE_DIRTY:
        return
    async with SOCIALINTEL_STATE_LOCK:
        if not force and not SOCIALINTEL_STATE_DIRTY:
            return
        try:
            persisted = write_state(SOCIALINTEL_STATE_KEY, SOCIALINTEL_STATE)
            if persisted:
                SOCIALINTEL_STATE_DIRTY = False
        except Exception:
            pass


def get_guild_socialintel_state(guild_id: int) -> dict[str, Any]:
    state = get_socialintel_state()
    guilds = state.setdefault("guilds", {})
    if not isinstance(guilds, dict):
        guilds = {}
        state["guilds"] = guilds
    key = str(guild_id)
    guild_state = guilds.get(key)
    if not isinstance(guild_state, dict):
        guild_state = {"channels": {}, "users": {}, "pairs": {}, "meta": {}}
        guilds[key] = guild_state
        _mark_socialintel_dirty()
    for field in ("channels", "users", "pairs", "meta"):
        if not isinstance(guild_state.get(field), dict):
            guild_state[field] = {}
    meta = guild_state["meta"]
    meta.setdefault("messages_indexed", 0)
    meta.setdefault("last_backfill_ts", 0.0)
    meta.setdefault("last_incremental_ts", 0.0)
    meta.setdefault("last_indexed_message_ts", 0.0)
    meta.setdefault("last_proactive_ts", 0.0)
    return guild_state


def get_guild_engagement_state(guild_id: int) -> dict[str, object]:
    guilds = ENGAGEMENT_STATE.setdefault("guilds", {})
    if not isinstance(guilds, dict):
        guilds = {}
        ENGAGEMENT_STATE["guilds"] = guilds
    key = str(guild_id)
    state = guilds.get(key)
    if not isinstance(state, dict):
        state = {"users": {}, "automation": {}}
        guilds[key] = state
        _mark_engagement_dirty()
    state.setdefault("users", {})
    state.setdefault("automation", {})
    return state


def get_user_engagement_state(guild_id: int, user_id: int) -> dict[str, object]:
    guild_state = get_guild_engagement_state(guild_id)
    users = guild_state.setdefault("users", {})
    if not isinstance(users, dict):
        users = {}
        guild_state["users"] = users
    key = str(user_id)
    state = users.get(key)
    if not isinstance(state, dict):
        state = _default_user_engagement_state()
        users[key] = state
        _mark_engagement_dirty()
    for field, default_value in _default_user_engagement_state().items():
        if field not in state:
            state[field] = default_value
    return state


def _pick_daily_quests(guild_id: int, day_key: str) -> list[dict[str, object]]:
    pool = list(QUEST_LIBRARY)
    if not pool:
        return []
    rng = random.Random(f"{guild_id}:{day_key}:quests")
    desired = min(len(pool), max(1, QUEST_DAILY_COUNT))
    return rng.sample(pool, desired)


def get_user_daily_quests(guild_id: int, user_state: dict[str, object]) -> tuple[list[dict[str, object]], dict[str, int], set[str]]:
    day_key = _guild_day_key(guild_id)
    quest_state = user_state.get("quest")
    if not isinstance(quest_state, dict):
        quest_state = {"day": "", "progress": {}, "completed": []}
        user_state["quest"] = quest_state
    if quest_state.get("day") != day_key:
        quest_state["day"] = day_key
        quest_state["progress"] = {}
        quest_state["completed"] = []
        _mark_engagement_dirty()
    progress_raw = quest_state.get("progress")
    if not isinstance(progress_raw, dict):
        progress_raw = {}
        quest_state["progress"] = progress_raw
    completed_raw = quest_state.get("completed")
    if isinstance(completed_raw, list):
        completed = {str(item) for item in completed_raw}
    else:
        completed = set()
        quest_state["completed"] = []
    progress: dict[str, int] = {}
    for key, value in progress_raw.items():
        try:
            progress[str(key)] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return _pick_daily_quests(guild_id, day_key), progress, completed


def _update_streak(user_state: dict[str, object], guild_id: int, now_ts: float) -> None:
    previous = float(user_state.get("last_active_ts", 0.0) or 0.0)
    previous_day = ""
    if previous > 0:
        previous_day = datetime.fromtimestamp(previous, tz=timezone.utc).astimezone(
            _safe_zoneinfo(get_guild_engagement_timezone(guild_id))
        ).strftime("%Y-%m-%d")
    current_day = _guild_day_key(guild_id)
    streak = int(user_state.get("streak", 0))
    if not previous_day:
        streak = 1
    elif previous_day != current_day:
        delta_hours = max(0.0, (now_ts - previous) / 3600.0)
        if delta_hours <= STREAK_GRACE_HOURS:
            streak = max(1, streak + 1)
        else:
            streak = 1
    user_state["streak"] = streak
    user_state["best_streak"] = max(int(user_state.get("best_streak", 0)), streak)
    user_state["last_active_ts"] = now_ts


def grant_user_xp(
    guild_id: int,
    user_id: int,
    xp_gain: int,
    *,
    apply_daily_cap: bool = True,
    include_weekly: bool = True,
) -> int:
    if xp_gain <= 0:
        return 0
    user_state = get_user_engagement_state(guild_id, user_id)
    day_key = _guild_day_key(guild_id)
    daily = user_state.get("daily")
    if not isinstance(daily, dict):
        daily = {"day": day_key, "xp": 0}
        user_state["daily"] = daily
    if daily.get("day") != day_key:
        daily["day"] = day_key
        daily["xp"] = 0

    gain = int(xp_gain)
    if apply_daily_cap:
        remaining = max(0, XP_DAILY_CAP - int(daily.get("xp", 0)))
        gain = min(gain, remaining)
    if gain <= 0:
        return 0

    user_state["xp"] = int(user_state.get("xp", 0)) + gain
    daily["xp"] = int(daily.get("xp", 0)) + gain
    if include_weekly:
        weekly = user_state.get("weekly")
        if not isinstance(weekly, dict):
            weekly = {"key": "", "points": 0}
            user_state["weekly"] = weekly
        week_key = _guild_week_key(guild_id)
        if weekly.get("key") != week_key:
            weekly["key"] = week_key
            weekly["points"] = 0
        weekly["points"] = int(weekly.get("points", 0)) + gain
    _mark_engagement_dirty()
    return gain


def _normalize_content_for_xp(text: str) -> str:
    return " ".join(text.lower().split()).strip()


def _quest_progress_for_message(message: discord.Message, content: str) -> dict[str, int]:
    return {
        "messages": 1,
        "replies": 1 if message.reference is not None else 0,
        "mentions": len([m for m in message.mentions if not m.bot]),
        "threads": 1 if isinstance(message.channel, discord.Thread) else 0,
        "long_msgs": 1 if len(content) >= 80 else 0,
    }


def apply_message_engagement_progress(message: discord.Message) -> tuple[int, int]:
    if not ENGAGEMENT_ENABLED or message.guild is None:
        return 0, 0
    if not isinstance(message.author, discord.Member) or message.author.bot:
        return 0, 0

    content = message.clean_content.strip()
    if not content or len(content) < XP_MIN_MESSAGE_CHARS:
        return 0, 0
    if message.content.startswith(PREFIX):
        return 0, 0

    key = (message.guild.id, message.author.id)
    now_mono = time.monotonic()
    normalized = _normalize_content_for_xp(content)
    last = ENGAGEMENT_LAST_MESSAGE_CACHE.get(key)
    if last is not None:
        last_ts, last_content = last
        if now_mono - last_ts < XP_MESSAGE_COOLDOWN_SECONDS:
            return 0, 0
        if normalized == last_content and now_mono - last_ts < XP_MESSAGE_COOLDOWN_SECONDS * 3:
            return 0, 0
    ENGAGEMENT_LAST_MESSAGE_CACHE[key] = (now_mono, normalized)

    user_state = get_user_engagement_state(message.guild.id, message.author.id)
    _update_streak(user_state, message.guild.id, time.time())

    base_xp = 10
    bonus = 0
    if message.reference is not None:
        bonus += 2
    if isinstance(message.channel, discord.Thread):
        bonus += 2
    if message.mentions:
        bonus += min(2, len([m for m in message.mentions if not m.bot]))
    total_gain = base_xp + bonus

    quest_bonus = 0
    if get_guild_quest_mode_enabled(message.guild.id):
        quests, progress, completed = get_user_daily_quests(message.guild.id, user_state)
        delta = _quest_progress_for_message(message, content)
        for metric, increment in delta.items():
            if increment <= 0:
                continue
            progress[metric] = int(progress.get(metric, 0)) + increment
        for quest in quests:
            quest_id = str(quest.get("id", ""))
            metric = str(quest.get("type", ""))
            target = int(quest.get("target", 1))
            reward = int(quest.get("reward", 0))
            if not quest_id or metric not in progress:
                continue
            if quest_id in completed:
                continue
            if progress.get(metric, 0) >= target:
                completed.add(quest_id)
                quest_bonus += max(0, reward)
        quest_state = user_state.setdefault("quest", {"day": _guild_day_key(message.guild.id), "progress": {}, "completed": []})
        if isinstance(quest_state, dict):
            quest_state["progress"] = progress
            quest_state["completed"] = sorted(completed)
            quest_state["day"] = _guild_day_key(message.guild.id)
            _mark_engagement_dirty()

    gained = grant_user_xp(
        message.guild.id,
        message.author.id,
        total_gain + quest_bonus,
        apply_daily_cap=True,
        include_weekly=True,
    )
    return gained, quest_bonus


def get_metric_for_user(
    user_state: dict[str, object],
    board: str,
    *,
    day_key: str,
    week_key: str,
) -> int:
    normalized = board.strip().lower()
    if normalized == "daily":
        daily = user_state.get("daily", {})
        if isinstance(daily, dict) and daily.get("day") == day_key:
            return int(daily.get("xp", 0))
        return 0
    if normalized == "weekly":
        weekly = user_state.get("weekly", {})
        if isinstance(weekly, dict) and weekly.get("key") == week_key:
            return int(weekly.get("points", 0))
        return 0
    return int(user_state.get("xp", 0))


def resolve_engagement_channel(guild: discord.Guild) -> discord.TextChannel | None:
    me = guild.me
    if me is None:
        return None
    configured = get_guild_engagement_hub_channel_id(guild.id)
    if configured:
        channel = guild.get_channel(configured)
        if isinstance(channel, discord.TextChannel):
            perms = channel.permissions_for(me)
            if perms.view_channel and perms.send_messages:
                return channel
    for channel in guild.text_channels:
        perms = channel.permissions_for(me)
        if perms.view_channel and perms.send_messages:
            return channel
    return None


def _trim_post_history(guild_id: int) -> None:
    queue = AUTO_LOOP_POST_HISTORY[guild_id]
    now = time.monotonic()
    while queue and now - queue[0] > 3600:
        queue.popleft()


def can_send_automation_post(guild_id: int) -> bool:
    _trim_post_history(guild_id)
    queue = AUTO_LOOP_POST_HISTORY[guild_id]
    if len(queue) >= AUTO_LOOP_MAX_POSTS_PER_HOUR:
        return False
    queue.append(time.monotonic())
    return True


def _build_recap_from_window(entries: list[WindowMessage]) -> str:
    if not entries:
        return "No major chat activity in the recent window."
    participants: Counter[str] = Counter(entry.author_display_name for entry in entries)
    words: list[str] = []
    for entry in entries:
        for token in WORD_PATTERN.findall(entry.content.lower()):
            cleaned = token.strip("'")
            if len(cleaned) <= 2 or cleaned in ROAST_STOP_WORDS:
                continue
            words.append(cleaned)
    top_people = ", ".join(name for name, _ in participants.most_common(3)) or "n/a"
    top_topics = ", ".join(word for word, _ in Counter(words).most_common(4)) or "general chat"
    return (
        f"- Active members: {top_people}\n"
        f"- Main topics: {top_topics}\n"
        "- Re-entry prompt: jump in with one opinion or one question."
    )


def _event_type_prompt(event_type: str) -> tuple[str, set[str]]:
    normalized = event_type.strip().lower()
    if normalized == "trivia":
        picked = random.choice(TRIVIA_PACK)
        return str(picked["prompt"]), set(picked["answers"])
    if normalized == "hottake":
        topic = random.choice(HOTTAKE_TOPICS)
        return f"Hot-take round: **{topic}**\nDrop your stance in one sharp line.", set()
    if normalized == "caption":
        return random.choice(CAPTION_PROMPTS), set()
    raise ValueError("Unsupported event type.")


async def finalize_event_session(guild: discord.Guild, *, reason: str = "timer") -> None:
    session = EVENT_SESSIONS.pop(guild.id, None)
    if not session:
        return
    channel = guild.get_channel(int(session.get("channel_id", 0)))
    if not isinstance(channel, discord.TextChannel):
        return
    scores_raw = session.get("scores")
    if not isinstance(scores_raw, dict) or not scores_raw:
        await channel.send("Event ended. Not enough participation this round.")
        return
    scored = sorted(
        ((int(user_id), int(points)) for user_id, points in scores_raw.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    winner_id, winner_score = scored[0]
    winner = guild.get_member(winner_id)

    awarded_lines: list[str] = []
    for user_id, points in scored[:12]:
        bonus = min(40, max(4, points * 4))
        granted = grant_user_xp(guild.id, user_id, bonus, apply_daily_cap=True, include_weekly=True)
        if granted > 0:
            state = get_user_engagement_state(guild.id, user_id)
            state["event_points"] = int(state.get("event_points", 0)) + granted
            _mark_engagement_dirty()
            awarded_lines.append(f"<@{user_id}> +`{granted}` XP")

    winner_text = winner.mention if winner else f"<@{winner_id}>"
    scoreboard = "\n".join(f"{idx}. <@{uid}> - `{pts}` pts" for idx, (uid, pts) in enumerate(scored[:5], start=1))
    await channel.send(
        f"Event ended ({reason}). Winner: {winner_text} with `{winner_score}` points.\n"
        f"Top scores:\n{scoreboard}\n\n"
        f"XP awards:\n{chr(10).join(awarded_lines) if awarded_lines else 'No XP awarded (daily cap reached).'}"
    )
    await flush_engagement_state()


def register_automod_strike(guild_id: int, user_id: int) -> tuple[int, int, bool]:
    strikes = AUTOMOD_STRIKE_CACHE[(guild_id, user_id)]
    _trim_time_queue(strikes, STRIKE_DECAY_DAYS * 24 * 60 * 60)
    strikes.append(time.monotonic())
    strike_count = len(strikes)
    if strike_count <= 1:
        return strike_count, 0, False
    if strike_count == 2:
        return strike_count, 2, False
    if strike_count == 3:
        return strike_count, 10, False
    if strike_count == 4:
        return strike_count, 30, True
    return strike_count, 60, True


def _heat_weight_for_action(action: str) -> float:
    lowered = action.lower()
    if "spam" in lowered:
        return 0.45
    if "blocked word" in lowered:
        return 0.35
    if "blocked link" in lowered:
        return 0.26
    return 0.22


def _channel_heat_score(guild_id: int, channel_id: int) -> float:
    queue = CHANNEL_HEAT_EVENTS[(guild_id, channel_id)]
    now = time.monotonic()
    while queue and now - queue[0][0] > 12 * 60:
        queue.popleft()
    if not queue:
        return 0.0
    score = 0.0
    for ts, weight in queue:
        age = now - ts
        if age <= 0:
            score += weight
            continue
        decay = max(0.0, 1.0 - (age / (12 * 60)))
        score += weight * decay
    return score


async def apply_channel_heat_event(
    channel: discord.TextChannel,
    *,
    action: str,
    moderator: discord.abc.User | None = None,
) -> None:
    guild = channel.guild
    if not get_guild_modguard_enabled(guild.id):
        return
    key = (guild.id, channel.id)
    queue = CHANNEL_HEAT_EVENTS[key]
    queue.append((time.monotonic(), _heat_weight_for_action(action)))
    score = _channel_heat_score(guild.id, channel.id)
    if score < MOD_HEAT_THRESHOLD:
        return

    existing = CHANNEL_HEAT_SLOWMODE_STATE.get(key)
    now = time.monotonic()
    if existing and now < float(existing.get("until", 0.0)):
        return

    old_delay = channel.slowmode_delay
    target_delay = max(old_delay, MOD_HEAT_SLOWMODE_SECONDS)
    if target_delay <= old_delay and old_delay > 0:
        CHANNEL_HEAT_SLOWMODE_STATE[key] = {
            "until": now + 10 * 60,
            "old_delay": float(old_delay),
        }
        return

    try:
        await channel.edit(
            slowmode_delay=target_delay,
            reason=f"ModGuard heat protection ({score:.2f})",
        )
    except discord.HTTPException:
        return

    CHANNEL_HEAT_SLOWMODE_STATE[key] = {
        "until": now + 10 * 60,
        "old_delay": float(old_delay),
    }
    try:
        await channel.send(
            f"ModGuard: temporary slowmode `{target_delay}s` enabled due to channel heat.",
            delete_after=8,
        )
    except discord.HTTPException:
        pass
    await send_mod_log(
        guild,
        "ModGuard: Heat Slowmode",
        moderator=moderator or bot.user,
        channel=channel,
        details=f"Score: `{score:.2f}`, delay: `{target_delay}s`.",
    )


async def release_expired_heat_slowmodes() -> None:
    now = time.monotonic()
    for (guild_id, channel_id), state in list(CHANNEL_HEAT_SLOWMODE_STATE.items()):
        until = float(state.get("until", 0.0))
        if now < until:
            continue
        guild = bot.get_guild(guild_id)
        if guild is None:
            CHANNEL_HEAT_SLOWMODE_STATE.pop((guild_id, channel_id), None)
            continue
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            CHANNEL_HEAT_SLOWMODE_STATE.pop((guild_id, channel_id), None)
            continue
        old_delay = int(state.get("old_delay", 0.0))
        try:
            await channel.edit(
                slowmode_delay=max(0, old_delay),
                reason="ModGuard heat cooldown expired",
            )
        except discord.HTTPException:
            pass
        CHANNEL_HEAT_SLOWMODE_STATE.pop((guild_id, channel_id), None)


def append_with_char_budget(bucket: list[str], text: str, current_chars: int, max_chars: int) -> int:
    if max_chars <= 0:
        return current_chars
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return current_chars
    remaining = max_chars - current_chars
    if remaining <= 0:
        return current_chars
    if len(cleaned) > remaining:
        cleaned = cleaned[: max(0, remaining - 3)].rstrip()
        if cleaned:
            cleaned += "..."
    if cleaned:
        bucket.append(cleaned)
        return current_chars + len(cleaned) + 1
    return current_chars


def lines_to_paragraph(lines: list[str], max_chars: int) -> str:
    merged = " ".join(line.strip() for line in lines if line and line.strip())
    if len(merged) > max_chars:
        merged = merged[: max(0, max_chars - 3)].rstrip() + "..."
    return merged


@dataclass
class WindowMessage:
    message_id: int
    channel_id: int
    author_id: int
    author_display_name: str
    content: str
    created_at_ts: float
    mention_ids: tuple[int, ...]
    reference_message_id: int | None
    has_attachments: bool


def prune_message_window_cache() -> None:
    if len(MESSAGE_WINDOW_CACHE) <= MESSAGE_WINDOW_CACHE_MAX_ENTRIES:
        return
    ordered = sorted(MESSAGE_WINDOW_CACHE.items(), key=lambda item: item[1][0], reverse=True)
    keep = dict(ordered[:MESSAGE_WINDOW_CACHE_MAX_ENTRIES])
    MESSAGE_WINDOW_CACHE.clear()
    MESSAGE_WINDOW_CACHE.update(keep)
    for key in list(MESSAGE_WINDOW_LOCKS.keys()):
        if key not in MESSAGE_WINDOW_CACHE:
            MESSAGE_WINDOW_LOCKS.pop(key, None)


def _window_cutoff_bucket(after) -> int:
    if after is None:
        return 0
    try:
        return int(after.timestamp() // 60)
    except Exception:
        return 0


def _build_window_entry(
    message: discord.Message,
    *,
    include_attachment_marker: bool,
) -> WindowMessage | None:
    if message.author.bot:
        return None
    content = message.clean_content.strip()
    if not content and include_attachment_marker and message.attachments:
        content = "[Attachment]"
    if not content:
        return None
    cleaned = " ".join(content.split()).strip()
    if not cleaned:
        return None
    mention_ids = tuple(mentioned.id for mentioned in message.mentions if not mentioned.bot)
    return WindowMessage(
        message_id=message.id,
        channel_id=message.channel.id,
        author_id=message.author.id,
        author_display_name=message.author.display_name,
        content=cleaned[:360],
        created_at_ts=message.created_at.timestamp(),
        mention_ids=mention_ids,
        reference_message_id=message.reference.message_id if message.reference else None,
        has_attachments=bool(message.attachments),
    )


async def _get_cached_window(
    cache_key: tuple,
    cache_ttl_seconds: int,
    loader,
) -> list[WindowMessage]:
    now = time.monotonic()
    cached = MESSAGE_WINDOW_CACHE.get(cache_key)
    if cached and now - cached[0] < cache_ttl_seconds:
        return cached[1]

    lock = MESSAGE_WINDOW_LOCKS[cache_key]
    async with lock:
        cached = MESSAGE_WINDOW_CACHE.get(cache_key)
        if cached and time.monotonic() - cached[0] < cache_ttl_seconds:
            return cached[1]
        result = await loader()
        MESSAGE_WINDOW_CACHE[cache_key] = (time.monotonic(), result)
        prune_message_window_cache()
        return result


def get_readable_text_channels(guild: discord.Guild) -> list[discord.TextChannel]:
    me = guild.me
    if me is None:
        return []
    return [
        channel
        for channel in guild.text_channels
        if channel.permissions_for(me).view_channel and channel.permissions_for(me).read_message_history
    ]


async def get_channel_window_cached(
    channel: discord.TextChannel,
    *,
    after=None,
    scan_limit: int = CATCHUP_SCAN_LIMIT,
    cache_ttl_seconds: int = CATCHUP_CACHE_SECONDS,
    include_attachment_marker: bool = True,
) -> list[WindowMessage]:
    limit = max(40, scan_limit)
    cache_key = (
        "channel_window",
        channel.guild.id,
        channel.id,
        limit,
        _window_cutoff_bucket(after),
        int(include_attachment_marker),
    )

    async def loader() -> list[WindowMessage]:
        entries: list[WindowMessage] = []
        try:
            async for msg in channel.history(limit=limit, after=after, oldest_first=True):
                entry = _build_window_entry(msg, include_attachment_marker=include_attachment_marker)
                if entry is not None:
                    entries.append(entry)
        except (discord.Forbidden, discord.HTTPException):
            return []
        return entries

    return await _get_cached_window(cache_key, cache_ttl_seconds, loader)


async def get_guild_window_cached(
    guild: discord.Guild,
    *,
    full_history_scan: bool,
    scan_per_channel: int,
    max_history_messages: int,
    pause_every: int,
    pause_seconds: float,
    after=None,
    max_channels: int = 0,
    cache_ttl_seconds: int = 120,
) -> list[WindowMessage]:
    channels = get_readable_text_channels(guild)
    if max_channels > 0:
        channels = channels[:max_channels]
    channel_signature = tuple(channel.id for channel in channels[:80])
    cache_key = (
        "guild_window",
        guild.id,
        int(full_history_scan),
        max(20, scan_per_channel),
        max(200, max_history_messages),
        _window_cutoff_bucket(after),
        max_channels,
        channel_signature,
    )

    async def loader() -> list[WindowMessage]:
        entries: list[WindowMessage] = []
        scanned = 0
        for channel in channels:
            if scanned >= max_history_messages:
                break
            history_limit = None if full_history_scan else max(20, scan_per_channel)
            try:
                async for msg in channel.history(limit=history_limit, after=after, oldest_first=True):
                    entry = _build_window_entry(msg, include_attachment_marker=True)
                    scanned += 1
                    if (
                        pause_every > 0
                        and pause_seconds > 0
                        and scanned % pause_every == 0
                    ):
                        await asyncio.sleep(pause_seconds)
                    if scanned >= max_history_messages:
                        break
                    if entry is None:
                        continue
                    entries.append(entry)
            except (discord.Forbidden, discord.HTTPException):
                continue
        entries.sort(key=lambda item: item.created_at_ts)
        return entries

    return await _get_cached_window(cache_key, cache_ttl_seconds, loader)


async def get_social_message_window(guild: discord.Guild) -> list[WindowMessage]:
    shared_full_history = AICRUSH_FULL_HISTORY_SCAN or ROAST_FULL_HISTORY_SCAN
    shared_scan_per_channel = max(AICRUSH_SCAN_PER_CHANNEL, ROAST_SCAN_PER_CHANNEL)
    shared_max_history = max(AICRUSH_MAX_HISTORY_MESSAGES, ROAST_MAX_HISTORY_MESSAGES)
    shared_pause_every = max(ROAST_SCAN_PAUSE_EVERY, AICRUSH_SCAN_PAUSE_EVERY)
    shared_pause_seconds = max(ROAST_SCAN_PAUSE_SECONDS, AICRUSH_SCAN_PAUSE_SECONDS)
    shared_max_channels = max(AICRUSH_MAX_CHANNELS, ROAST_MAX_CHANNELS)
    return await get_guild_window_cached(
        guild,
        full_history_scan=shared_full_history,
        scan_per_channel=shared_scan_per_channel,
        max_history_messages=shared_max_history,
        pause_every=shared_pause_every,
        pause_seconds=shared_pause_seconds,
        max_channels=shared_max_channels,
        cache_ttl_seconds=min(AICRUSH_CACHE_SECONDS, ROAST_CACHE_SECONDS, 180),
    )


@dataclass
class RoastContext:
    message_count: int
    replies_count: int
    scanned_messages: int
    user_lines: list[str]
    reply_lines: list[str]
    top_words: list[str]
    top_phrases: list[str]
    avg_len: float
    question_ratio: float
    exclaim_ratio: float
    emoji_per_msg: float
    punctuation_energy: float
    vocab_diversity: float


ROAST_STOP_WORDS = {
    "the", "and", "for", "that", "with", "this", "you", "are", "was", "have", "not", "but",
    "just", "your", "from", "what", "when", "where", "will", "would", "they", "them", "their",
    "about", "there", "then", "than", "into", "also", "been", "can", "could", "should", "like",
    "im", "its", "dont", "cant", "didnt", "wont", "aint", "ive", "ill",
}


def extract_roast_term_stats(messages: list[str]) -> tuple[list[str], list[str]]:
    words: list[str] = []
    for message in messages:
        for token in WORD_PATTERN.findall(message.lower()):
            cleaned = token.strip("'")
            if len(cleaned) <= 2 or cleaned in ROAST_STOP_WORDS:
                continue
            words.append(cleaned)

    top_words = [word for word, _ in Counter(words).most_common(8)]

    bigrams: list[str] = []
    for first, second in zip(words, words[1:]):
        if first == second:
            continue
        bigrams.append(f"{first} {second}")
    top_phrases = [phrase for phrase, _ in Counter(bigrams).most_common(6)]
    return top_words, top_phrases


def roast_reply_tone(reply_lines: list[str]) -> str:
    if not reply_lines:
        return "limited reply context"
    reply_text = " ".join(reply_lines).lower()
    positive_hits = sum(
        reply_text.count(word)
        for word in ("lol", "lmao", "haha", "thanks", "nice", "great", "bro", "love")
    )
    negative_hits = sum(
        reply_text.count(word)
        for word in ("stupid", "idiot", "trash", "annoying", "hate", "shut", "noob")
    )
    if positive_hits > negative_hits * 1.4:
        return "mostly playful-positive reactions"
    if negative_hits > positive_hits * 1.4:
        return "frequent pushback/teasing reactions"
    return "mixed reactions"


def roast_behavior_labels(context: RoastContext) -> list[str]:
    labels: list[str] = []
    if context.question_ratio >= 0.35:
        labels.append("asks a lot of questions")
    elif context.question_ratio >= 0.2:
        labels.append("keeps probing conversations")
    if context.exclaim_ratio >= 0.3:
        labels.append("high-energy texter")
    elif context.exclaim_ratio <= 0.08:
        labels.append("dry delivery style")
    if context.emoji_per_msg >= 1.2:
        labels.append("emoji-heavy speaker")
    elif context.emoji_per_msg >= 0.4:
        labels.append("sprinkles emojis often")
    if context.avg_len >= 110:
        labels.append("drops paragraph-sized takes")
    elif context.avg_len <= 28:
        labels.append("rapid one-liner style")
    labels.append(roast_reply_tone(context.reply_lines))
    return labels[:5]


def roast_fingerprint(context: RoastContext) -> str:
    return (
        f"punc={context.punctuation_energy:.2f}|emoji={context.emoji_per_msg:.2f}|"
        f"vocab={context.vocab_diversity:.2f}|words={','.join(context.top_words[:4])}|"
        f"phrases={','.join(context.top_phrases[:3])}|reply={roast_reply_tone(context.reply_lines)}"
    )


def get_recent_roast_outputs(guild_id: int, user_id: int, style: str) -> list[str]:
    key = (guild_id, user_id, style)
    queue = ROAST_RECENT_OUTPUTS.get(key, deque())
    if not queue:
        return []
    cutoff = time.monotonic() - (ROAST_REPEAT_COOLDOWN_HOURS * 3600)
    while queue and queue[0][0] < cutoff:
        queue.popleft()
    if not queue:
        ROAST_RECENT_OUTPUTS.pop(key, None)
        return []
    ROAST_RECENT_OUTPUTS[key] = queue
    return [item[1] for item in queue]


def remember_roast_output(guild_id: int, user_id: int, style: str, output: str) -> None:
    key = (guild_id, user_id, style)
    queue = ROAST_RECENT_OUTPUTS[key]
    queue.append((time.monotonic(), output.strip()))


def roast_engagement_cta(fun_mode: str) -> str:
    if fun_mode == "wholesome":
        return "Reply with a playful comeback and keep it friendly."
    if fun_mode == "balanced":
        return "Drop a witty comeback and let the thread decide the winner."
    return "Your turn: clap back with one savage line."


async def collect_roast_context(guild: discord.Guild, target_user_id: int) -> RoastContext:
    entries = await get_social_message_window(guild)
    if not entries:
        return RoastContext(0, 0, 0, [], [], [], [], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    recent_entries = entries[-ROAST_MAX_HISTORY_MESSAGES:]
    user_lines: list[str] = []
    reply_lines: list[str] = []
    scanned_messages = len(recent_entries)
    message_count = 0
    replies_count = 0
    user_chars = 0
    reply_chars = 0
    total_len = 0
    question_messages = 0
    exclaim_messages = 0
    emoji_count = 0
    vocab_tokens: list[str] = []
    user_budget = int(ROAST_MAX_CONTEXT_CHARS * 0.72)
    reply_budget = ROAST_MAX_CONTEXT_CHARS - user_budget
    target_message_ids: set[int] = set()
    for entry in recent_entries:
        cleaned = entry.content[:320]
        if entry.author_id == target_user_id:
            target_message_ids.add(entry.message_id)
            message_count += 1
            total_len += len(cleaned)
            if "?" in cleaned:
                question_messages += 1
            if "!" in cleaned:
                exclaim_messages += 1
            emoji_count += len(EMOJI_PATTERN.findall(cleaned))
            user_chars = append_with_char_budget(
                user_lines, cleaned, user_chars, user_budget
            )
            for token in WORD_PATTERN.findall(cleaned.lower()):
                stripped = token.strip("'")
                if len(stripped) > 2 and stripped not in ROAST_STOP_WORDS:
                    vocab_tokens.append(stripped)
            continue

        is_reply_to_target = (
            (entry.reference_message_id is not None and entry.reference_message_id in target_message_ids)
            or (target_user_id in entry.mention_ids)
        )
        if is_reply_to_target:
            replies_count += 1
            reply_chars = append_with_char_budget(
                reply_lines, cleaned, reply_chars, reply_budget
            )

    top_words, top_phrases = extract_roast_term_stats(user_lines)
    divisor = max(1, message_count)
    punctuation_energy = (question_messages + exclaim_messages) / divisor
    vocab_diversity = len(set(vocab_tokens)) / max(1, len(vocab_tokens))
    return RoastContext(
        message_count=message_count,
        replies_count=replies_count,
        scanned_messages=scanned_messages,
        user_lines=user_lines,
        reply_lines=reply_lines,
        top_words=top_words,
        top_phrases=top_phrases,
        avg_len=total_len / divisor,
        question_ratio=question_messages / divisor,
        exclaim_ratio=exclaim_messages / divisor,
        emoji_per_msg=emoji_count / divisor,
        punctuation_energy=punctuation_energy,
        vocab_diversity=vocab_diversity,
    )


def build_personal_roast_prompt(
    member: discord.Member,
    style: Literal["soft", "friendly", "brutal"],
    context: RoastContext,
    *,
    recent_outputs: list[str] | None = None,
) -> str:
    style_instruction = {
        "soft": "Tone template: playful, affectionate teasing, no harsh humiliation.",
        "friendly": "Tone template: witty medium-spice jabs with social banter energy.",
        "brutal": "Tone template: high spice and savage punchlines, but still policy-safe and non-hateful.",
    }[style]
    behavior_bits = ", ".join(roast_behavior_labels(context)) or "general chat presence"
    top_words = ", ".join(context.top_words[:6]) or "none"
    top_phrases = ", ".join(context.top_phrases[:5]) or "none"
    reply_tone = roast_reply_tone(context.reply_lines)
    anti_repeat = ""
    if recent_outputs:
        compact = [line[:120] for line in recent_outputs[-3:]]
        anti_repeat = (
            "8) Avoid repeating these prior roast structures/themes:\n"
            + "\n".join(f"- {line}" for line in compact)
            + "\n"
        )

    return (
        f"Create a {style} personal roast for a Discord member.\n"
        "Rules:\n"
        "1) No slurs, hate speech, threats, doxxing, sexual content, or protected-trait insults.\n"
        "2) Do NOT quote or reproduce exact user messages.\n"
        "3) Roast only on observable chat patterns/habits.\n"
        "4) Keep it playful and fun-only.\n"
        f"5) {style_instruction}\n"
        "6) Output exactly 5-9 short roast lines.\n"
        "7) Final line must start with `Closer:` and end positively.\n"
        f"{anti_repeat}\n"
        f"Target username: {member.name}\n"
        f"Target display name: {member.display_name}\n"
        f"Message count analyzed: {context.message_count}\n"
        f"Replies/mentions analyzed: {context.replies_count}\n"
        f"Average message length: {context.avg_len:.1f}\n"
        f"Question ratio: {context.question_ratio * 100:.0f}%\n"
        f"Exclaim ratio: {context.exclaim_ratio * 100:.0f}%\n"
        f"Emoji per message: {context.emoji_per_msg:.2f}\n"
        f"Punctuation energy: {context.punctuation_energy:.2f}\n"
        f"Vocabulary diversity: {context.vocab_diversity:.2f}\n"
        f"Dominant behavior labels: {behavior_bits}\n"
        f"Frequent words: {top_words}\n"
        f"Frequent phrase patterns: {top_phrases}\n"
        f"How others react overall: {reply_tone}\n"
    )


def generate_personal_roast_local(
    member: discord.Member, style: Literal["soft", "friendly", "brutal"], context: RoastContext
) -> str:
    intensity_tag = {
        "soft": "low heat",
        "friendly": "mid heat",
        "brutal": "max heat",
    }[style]
    roast_level_line = {
        "soft": "You are roastable, but in a wholesome way.",
        "friendly": "You walk into chat like your opinion already has a soundtrack.",
        "brutal": "Your chat energy arrives before facts do, and still demands applause.",
    }[style]
    top_word = context.top_words[0] if context.top_words else "bro"
    backup_word = context.top_words[1] if len(context.top_words) > 1 else "literally"
    top_phrase = context.top_phrases[0] if context.top_phrases else "late-night chaos"

    lines = [
        f"{member.display_name}, this is a {intensity_tag} personalized roast.",
        roast_level_line,
        f"You mention `{top_word}` and `{backup_word}` so often your keyboard probably auto-completes drama.",
        f"Signature pattern spotted: {top_phrase}. Even your typo history has a storyline.",
    ]

    if context.question_ratio >= 0.3:
        lines.append("You ask so many questions that even your statements sound like interrogations.")
    elif context.question_ratio <= 0.08:
        lines.append("You drop takes with zero question marks, like every line is final patch notes.")
    else:
        lines.append("You balance questions and takes like you are moderating your own talk show.")

    if context.exclaim_ratio >= 0.28:
        lines.append("Your exclamation marks are doing cardio every night.")
    elif context.exclaim_ratio <= 0.07:
        lines.append("Your punctuation is so calm it could lower server ping.")
    else:
        lines.append("Your punctuation swings between diplomat and chaos goblin.")

    lines.append(
        f"People react with {roast_reply_tone(context.reply_lines)}, which means you are definitely impossible to ignore."
    )
    lines.append("Closer: all jokes, still elite presence in chat.")
    return "\n".join(lines[:9])


WELCOME_INTEREST_HINTS: dict[str, set[str]] = {
    "gaming": {"game", "gaming", "fps", "moba", "valorant", "minecraft", "fortnite", "steam"},
    "coding": {"code", "coding", "dev", "developer", "python", "js", "ai", "programming"},
    "anime": {"anime", "manga", "otaku"},
    "music": {"music", "song", "songs", "playlist", "spotify"},
    "movies": {"movie", "movies", "film", "films", "series", "shows"},
    "memes": {"meme", "memes", "funny", "shitpost"},
    "study": {"study", "studies", "exam", "school", "college", "notes", "productivity"},
    "sports": {"sport", "sports", "football", "cricket", "nba", "gym", "fitness"},
}


def parse_interest_tokens(text: str) -> list[str]:
    cleaned = " ".join(text.lower().split())[:WELCOME_INTEREST_MAX_CHARS]
    tokens = [tok.strip("'") for tok in WORD_PATTERN.findall(cleaned)]
    ordered: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if len(token) < 3 or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
        if len(ordered) >= 14:
            break
    return ordered


def find_intro_channel_for_guild(guild: discord.Guild) -> discord.TextChannel | None:
    configured_id = get_guild_intro_channel_id(guild.id)
    if configured_id:
        channel = guild.get_channel(configured_id)
        if isinstance(channel, discord.TextChannel):
            return channel

    preferred = (
        "introductions",
        "introduction",
        "introduce-yourself",
        "intro",
        "welcome",
        "general",
    )
    for name_hint in preferred:
        for channel in guild.text_channels:
            if name_hint in channel.name.lower():
                return channel
    return guild.text_channels[0] if guild.text_channels else None


def recommend_channels_for_member(
    guild: discord.Guild,
    member: discord.Member,
    interest_tokens: list[str],
    limit: int,
    *,
    exclude_channel_ids: set[int] | None = None,
) -> list[discord.TextChannel]:
    exclude = exclude_channel_ids or set()
    normalized_interests = set(interest_tokens)
    inferred_topics: set[str] = set()
    for topic, hints in WELCOME_INTEREST_HINTS.items():
        if normalized_interests.intersection(hints):
            inferred_topics.add(topic)

    scored: list[tuple[int, discord.TextChannel]] = []
    for channel in guild.text_channels:
        if channel.id in exclude:
            continue
        perms = channel.permissions_for(member)
        if not perms.view_channel:
            continue
        if channel.is_nsfw():
            continue

        blob = f"{channel.name} {(channel.topic or '')}".lower()
        score = 0
        if any(keyword in channel.name.lower() for keyword in ("intro", "welcome", "general", "chat")):
            score += 1
        for token in normalized_interests:
            if token in blob:
                score += 3
        for topic in inferred_topics:
            if topic in blob:
                score += 2
        if score > 0:
            scored.append((score, channel))

    if not scored:
        fallback = []
        for channel in guild.text_channels:
            perms = channel.permissions_for(member)
            if not perms.view_channel or channel.is_nsfw() or channel.id in exclude:
                continue
            fallback.append(channel)
            if len(fallback) >= limit:
                break
        return fallback

    scored.sort(key=lambda item: (-item[0], item[1].position, item[1].name))
    return [channel for _, channel in scored[:limit]]


def _welcome_ttl_seconds() -> int:
    return max(300, WELCOME_DM_TIMEOUT_MINUTES * 60)


def prune_welcome_sessions() -> None:
    now = time.monotonic()
    ttl = _welcome_ttl_seconds()
    for key, session in list(WELCOME_ONBOARDING_SESSIONS.items()):
        last = float(session.get("last_activity", 0.0))
        if now - last > ttl:
            WELCOME_ONBOARDING_SESSIONS.pop(key, None)


def start_welcome_session(guild_id: int, user_id: int) -> dict[str, object]:
    key = (guild_id, user_id)
    now = time.monotonic()
    payload: dict[str, object] = {
        "started_at": now,
        "last_activity": now,
        "step": "awaiting_interests",
        "interest_tokens": [],
        "sent_channel_ids": [],
    }
    WELCOME_ONBOARDING_SESSIONS[key] = payload
    return payload


def get_latest_welcome_session_for_user(user_id: int) -> tuple[tuple[int, int], dict[str, object]] | None:
    prune_welcome_sessions()
    latest_key: tuple[int, int] | None = None
    latest_session: dict[str, object] | None = None
    latest_ts = -1.0
    for key, session in WELCOME_ONBOARDING_SESSIONS.items():
        if key[1] != user_id:
            continue
        last = float(session.get("last_activity", 0.0))
        if last > latest_ts:
            latest_ts = last
            latest_key = key
            latest_session = session
    if latest_key is None or latest_session is None:
        return None
    return latest_key, latest_session


async def send_welcome_concierge(member: discord.Member) -> None:
    if member.bot:
        return
    if not get_guild_welcome_concierge_enabled(member.guild.id):
        return

    session = start_welcome_session(member.guild.id, member.id)
    intro_channel = find_intro_channel_for_guild(member.guild)
    starter_channels = recommend_channels_for_member(
        member.guild, member, [], WELCOME_RECOMMENDATION_COUNT
    )
    session["sent_channel_ids"] = [channel.id for channel in starter_channels]

    interest_examples = "gaming, coding, anime, movies, memes, music, study, sports"
    channel_lines = "\n".join(f"- {channel.mention}" for channel in starter_channels[:4]) or "- (No channel suggestions yet)"
    intro_line = (
        f"First action: say hi in {intro_channel.mention}."
        if intro_channel is not None
        else "First action: introduce yourself in your server's intro/general channel."
    )

    text = (
        f"Hey {member.display_name}, welcome to **{member.guild.name}**.\n"
        "I can quickly onboard you so you find your people faster.\n\n"
        f"Reply with your interests (comma-separated), for example: `{interest_examples}`.\n"
        "You can also reply `skip` for general recommendations.\n\n"
        f"Starter channels:\n{channel_lines}\n"
        f"{intro_line}"
    )

    try:
        await member.send(text)
    except discord.HTTPException:
        WELCOME_ONBOARDING_SESSIONS.pop((member.guild.id, member.id), None)


async def handle_welcome_concierge_dm(message: discord.Message) -> bool:
    if message.guild is not None or message.author.bot:
        return False
    if message.content.startswith(PREFIX):
        return False

    found = get_latest_welcome_session_for_user(message.author.id)
    if found is None:
        return False
    key, session = found
    guild = bot.get_guild(key[0])
    if guild is None:
        WELCOME_ONBOARDING_SESSIONS.pop(key, None)
        return False

    member = guild.get_member(message.author.id)
    if member is None:
        try:
            member = await guild.fetch_member(message.author.id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            WELCOME_ONBOARDING_SESSIONS.pop(key, None)
            return False

    content = " ".join(message.content.split()).strip()
    lowered = content.lower()
    if lowered in {"stop", "cancel", "end"}:
        WELCOME_ONBOARDING_SESSIONS.pop(key, None)
        await message.channel.send("Welcome setup closed. Ping me anytime if you want recommendations.")
        return True

    if not content:
        await message.channel.send("Send a few interests like `gaming, anime, coding` or type `skip`.")
        return True

    interest_tokens = [] if lowered == "skip" else parse_interest_tokens(content)
    if not interest_tokens and lowered != "skip":
        await message.channel.send("I couldn't read interests from that. Try 2-5 keywords or type `skip`.")
        return True

    sent_ids = set(int(ch_id) for ch_id in session.get("sent_channel_ids", []))
    recommendations = recommend_channels_for_member(
        guild,
        member,
        interest_tokens,
        WELCOME_RECOMMENDATION_COUNT,
        exclude_channel_ids=sent_ids,
    )
    if not recommendations:
        recommendations = recommend_channels_for_member(
            guild,
            member,
            [],
            WELCOME_RECOMMENDATION_COUNT,
        )

    intro_channel = find_intro_channel_for_guild(guild)
    tags = ", ".join(interest_tokens[:7]) if interest_tokens else "general community chats"
    channel_lines = "\n".join(f"- {channel.mention}" for channel in recommendations[:WELCOME_RECOMMENDATION_COUNT])
    if not channel_lines:
        channel_lines = "- No tailored channel matches yet; start in general and I'll refine later."
    intro_line = (
        f"First action: introduce yourself in {intro_channel.mention}."
        if intro_channel is not None
        else "First action: introduce yourself in the server intro/general channel."
    )

    response = (
        f"Perfect â€” I mapped your interests to **{tags}**.\n\n"
        f"Best channels for you in **{guild.name}**:\n{channel_lines}\n\n"
        f"{intro_line}\n"
        "Tip: use `&catchup 24` in a channel anytime to catch up quickly."
    )
    await message.channel.send(response)

    session["last_activity"] = time.monotonic()
    session["step"] = "completed"
    WELCOME_ONBOARDING_SESSIONS.pop(key, None)
    return True


# Small text helpers originally written for the old aicrush index. The
# history-mining crush feature is gone (see crush_game.py); roast, vibe and
# translation still use these helpers.


AICRUSH_ALIAS_STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "just", "have", "your", "you",
    "are", "was", "were", "they", "them", "their", "his", "her", "bro", "sis", "king",
    "queen", "admin", "mod", "staff", "team", "general", "chat", "hello", "hi", "hey",
    "bell", "user", "member", "server", "discord", "real", "name", "nickname",
}


def normalize_aicrush_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", (text or "").lower())
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9\s]", " ", without_marks)
    return re.sub(r"\s+", " ", cleaned).strip()


def aicrush_tokenize(text: str) -> list[str]:
    normalized = normalize_aicrush_text(text)
    return [token for token in normalized.split() if token]


def _aicrush_is_valid_alias_token(token: str) -> bool:
    if len(token) < 3 or token.isdigit():
        return False
    return token not in AICRUSH_ALIAS_STOP_WORDS


def _aicrush_append_unique_sample(bucket: list[str], text: str, limit: int) -> None:
    cleaned = " ".join(text.split()).strip()[:180]
    if not cleaned or cleaned in bucket:
        return
    bucket.append(cleaned)
    if len(bucket) > limit:
        del bucket[:-limit]


def _aicrush_remember_message_author(message_id: int, author_id: int, created_ts: float) -> None:
    AICRUSH_MESSAGE_AUTHOR_CACHE[message_id] = (author_id, created_ts)
    while len(AICRUSH_MESSAGE_AUTHOR_CACHE) > 24000:
        oldest_key = next(iter(AICRUSH_MESSAGE_AUTHOR_CACHE))
        AICRUSH_MESSAGE_AUTHOR_CACHE.pop(oldest_key, None)


def _aicrush_resolve_reply_target_id(message: discord.Message) -> int | None:
    if message.reference is None or message.reference.message_id is None:
        return None
    resolved = getattr(message.reference, "resolved", None)
    if isinstance(resolved, discord.Message) and not resolved.author.bot:
        return int(resolved.author.id)
    cached = AICRUSH_MESSAGE_AUTHOR_CACHE.get(int(message.reference.message_id))
    if cached is not None:
        return int(cached[0])
    return None


def _altfinder_name_aliases(display_name: str, username: str) -> dict[str, list[str]]:
    phrases: set[str] = set()
    tokens: set[str] = set()
    for raw_name in (display_name, username):
        normalized = normalize_aicrush_text(raw_name)
        if not normalized:
            continue
        if len(normalized) >= 3 and normalized not in AICRUSH_ALIAS_STOP_WORDS:
            phrases.add(normalized)
        parts = [part for part in normalized.split() if _aicrush_is_valid_alias_token(part)]
        tokens.update(parts)
        if len(parts) >= 2:
            merged = "".join(parts)
            if len(merged) >= 4 and merged not in AICRUSH_ALIAS_STOP_WORDS:
                phrases.add(merged)
    compact = _altfinder_compact_name(display_name)
    if len(compact) >= 4:
        phrases.add(compact)
    return {"phrases": sorted(phrases), "tokens": sorted(tokens)}


def _altfinder_compact_name(text: str) -> str:
    return normalize_aicrush_text(text).replace(" ", "")


def _altfinder_asset_key(asset: object) -> str:
    if asset is None:
        return ""
    try:
        raw = str(getattr(asset, "url", "") or str(asset))
    except Exception:
        return ""
    if not raw:
        return ""
    return raw.split("?", 1)[0].strip()


def _altfinder_counter_overlap(left: dict[str, int], right: dict[str, int]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left).intersection(right)
    if not shared:
        return 0.0
    numerator = sum(min(int(left[key]), int(right[key])) for key in shared)
    denominator = max(
        1,
        sum(int(value) for value in left.values()) + sum(int(value) for value in right.values()),
    )
    return round((2.0 * numerator) / denominator, 4)


def _altfinder_set_overlap(left: set[int] | set[str], right: set[int] | set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left.union(right)
    if not union:
        return 0.0
    return round(len(left.intersection(right)) / len(union), 4)


def _altfinder_scalar_similarity(left: float, right: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    diff = abs(float(left) - float(right))
    return round(max(0.0, 1.0 - (diff / scale)), 4)


def _altfinder_time_proximity_score(left_ts: float, right_ts: float) -> float:
    if left_ts <= 0 or right_ts <= 0:
        return 0.0
    diff_days = abs(left_ts - right_ts) / 86400.0
    if diff_days <= 1:
        return 1.0
    if diff_days <= 3:
        return 0.85
    if diff_days <= 7:
        return 0.68
    if diff_days <= 30:
        return 0.42
    if diff_days <= 120:
        return 0.2
    return 0.0


def _altfinder_counter_common(
    left: dict[str, int], right: dict[str, int], limit: int
) -> list[tuple[str, float]]:
    common: list[tuple[str, float]] = []
    for key in set(left).intersection(right):
        common.append((key, float(min(int(left[key]), int(right[key])))))
    common.sort(key=lambda item: item[1], reverse=True)
    return common[:limit]


def _altfinder_counter_update(
    row: dict[str, Any], field: str, key: int | str, amount: int, limit: int
) -> None:
    if amount <= 0:
        return
    counter = row.get(field)
    if not isinstance(counter, dict):
        counter = {}
        row[field] = counter
    text_key = str(key)
    counter[text_key] = int(counter.get(text_key, 0) or 0) + int(amount)
    if len(counter) > limit:
        ordered = sorted(
            counter.items(),
            key=lambda item: int(item[1] or 0),
            reverse=True,
        )[:limit]
        row[field] = {str(name): int(value) for name, value in ordered}


def _altfinder_profile_signature(
    display_name: str,
    username: str,
    avatar_key: str,
    display_avatar_key: str,
    default_avatar_key: str,
) -> str:
    compact_display = _altfinder_compact_name(display_name)
    compact_user = _altfinder_compact_name(username)
    avatar_basis = avatar_key or display_avatar_key or default_avatar_key or "no_avatar"
    return f"{compact_display}|{compact_user}|{avatar_basis}"


def _altfinder_normalize_status(status: object) -> str:
    text = str(status or "").strip().lower()
    if text in {"online", "idle", "dnd", "offline"}:
        return text
    if text in {"do_not_disturb", "do not disturb"}:
        return "dnd"
    return "offline"


def _altfinder_apply_user_snapshot(row: dict[str, Any], user: discord.abc.User) -> None:
    display_name = get_user_display_name(user)
    username = getattr(user, "name", display_name)
    row["display_name"] = display_name
    row["username"] = username
    row["aliases"] = _altfinder_name_aliases(display_name, username)
    created_at = getattr(user, "created_at", None)
    joined_at = getattr(user, "joined_at", None)
    row["created_at_ts"] = created_at.timestamp() if created_at else 0.0
    row["joined_at_ts"] = joined_at.timestamp() if joined_at else float(row.get("joined_at_ts", 0.0) or 0.0)
    avatar_key = _altfinder_asset_key(getattr(user, "avatar", None))
    display_avatar_key = _altfinder_asset_key(getattr(user, "display_avatar", None))
    default_avatar_key = _altfinder_asset_key(getattr(user, "default_avatar", None))
    row["avatar_key"] = avatar_key
    row["display_avatar_key"] = display_avatar_key
    row["default_avatar_key"] = default_avatar_key
    signature = _altfinder_profile_signature(
        display_name,
        username,
        avatar_key,
        display_avatar_key,
        default_avatar_key,
    )
    _altfinder_counter_update(row, "profile_signatures", signature, 1, 8)


def _altfinder_sync_presence_snapshot(
    row: dict[str, Any],
    member: discord.Member,
    *,
    increment_history: bool,
) -> None:
    status_name = _altfinder_normalize_status(getattr(member, "status", None))
    row["last_status"] = status_name
    row["last_status_ts"] = time.time()
    if not increment_history:
        return
    now_dt = _utc_now().astimezone(_safe_zoneinfo(get_guild_engagement_timezone(member.guild.id)))
    _altfinder_counter_update(row, "presence_hours", now_dt.hour, 1, 24)
    _altfinder_counter_update(row, "presence_weekdays", now_dt.weekday(), 1, 7)
    _altfinder_counter_update(row, "status_counts", status_name, 1, 8)
    last_status = str(row.get("presence_prev_status", "") or "")
    if last_status and last_status != status_name:
        _altfinder_counter_update(row, "status_transitions", f"{last_status}->{status_name}", 1, 16)
    row["presence_prev_status"] = status_name


def _altfinder_get_user_row(guild_state: dict[str, Any], user_id: int) -> dict[str, Any]:
    users = guild_state.setdefault("users", {})
    key = str(user_id)
    row = users.get(key)
    if not isinstance(row, dict):
        row = {
            "display_name": f"user-{user_id}",
            "username": f"user-{user_id}",
            "aliases": {"phrases": [], "tokens": []},
            "created_at_ts": 0.0,
            "joined_at_ts": 0.0,
            "avatar_key": "",
            "display_avatar_key": "",
            "default_avatar_key": "",
            "message_count": 0,
            "last_message_ts": 0.0,
            "message_total_chars": 0,
            "message_total_words": 0,
            "question_count": 0,
            "exclaim_count": 0,
            "emoji_total": 0,
            "uppercase_chars_total": 0,
            "link_count": 0,
            "attachment_count": 0,
            "mention_message_count": 0,
            "reply_message_count": 0,
            "topic_token_total": 0,
            "topics": {},
            "bigrams": {},
            "samples": [],
            "starter_tokens": {},
            "ending_tokens": {},
            "top_channels": {},
            "active_hours": {},
            "active_weekdays": {},
            "presence_hours": {},
            "presence_weekdays": {},
            "status_counts": {},
            "status_transitions": {},
            "last_status": "offline",
            "last_status_ts": 0.0,
            "presence_prev_status": "",
            "reply_targets": {},
            "mention_targets": {},
            "copresence_targets": {},
            "profile_signatures": {},
        }
        users[key] = row
    for field in (
        "aliases",
        "topics",
        "bigrams",
        "samples",
        "starter_tokens",
        "ending_tokens",
        "top_channels",
        "active_hours",
        "active_weekdays",
        "presence_hours",
        "presence_weekdays",
        "status_counts",
        "status_transitions",
        "reply_targets",
        "mention_targets",
        "copresence_targets",
        "profile_signatures",
    ):
        current = row.get(field)
        if field == "samples":
            if not isinstance(current, list):
                row[field] = []
        elif field == "aliases":
            if not isinstance(current, dict):
                row[field] = {"phrases": [], "tokens": []}
            else:
                if not isinstance(current.get("phrases"), list):
                    current["phrases"] = []
                if not isinstance(current.get("tokens"), list):
                    current["tokens"] = []
        elif not isinstance(current, dict):
            row[field] = {}
    return row


def _altfinder_extract_valid_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for token in aicrush_tokenize(text):
        if _aicrush_is_valid_alias_token(token):
            tokens.append(token)
    return tokens


def _altfinder_extract_bigrams(tokens: list[str]) -> list[str]:
    output: list[str] = []
    for first, second in zip(tokens, tokens[1:]):
        if first == second:
            continue
        output.append(f"{first} {second}")
    return output


def _altfinder_track_recent_channel_author(
    guild_id: int,
    channel_id: int,
    author_id: int,
    created_ts: float,
) -> list[int]:
    key = (guild_id, channel_id)
    queue = ALTFINDER_CHANNEL_RECENT_AUTHORS[key]
    while queue and created_ts - queue[0][0] > AICRUSH_CHANNEL_RECENT_WINDOW_SECONDS:
        queue.popleft()
    others = {other_author for _, other_author in queue if other_author != author_id}
    queue.append((created_ts, author_id))
    return list(others)


def _altfinder_invalidate_guild_cache(guild_id: int) -> None:
    for cache_key in list(ALTFINDER_RESULT_CACHE.keys()):
        if cache_key[0] == guild_id:
            ALTFINDER_RESULT_CACHE.pop(cache_key, None)


def _altfinder_sample_texture(samples: list[str], limit: int = 2) -> str:
    if not samples:
        return "no visible sample texture"
    chosen = [" ".join(sample.split()).strip()[:120] for sample in samples[:limit]]
    chosen = [sample for sample in chosen if sample]
    return " | ".join(chosen) if chosen else "no visible sample texture"


def refresh_altfinder_member_directory(guild: discord.Guild) -> None:
    guild_state = get_guild_altfinder_state(guild.id)
    for member in guild.members:
        if member.bot:
            continue
        row = _altfinder_get_user_row(guild_state, member.id)
        _altfinder_apply_user_snapshot(row, member)
        _altfinder_sync_presence_snapshot(row, member, increment_history=False)
    _mark_altfinder_dirty()


def record_altfinder_presence(member: discord.Member) -> None:
    if member.bot:
        return
    guild_state = get_guild_altfinder_state(member.guild.id)
    row = _altfinder_get_user_row(guild_state, member.id)
    _altfinder_apply_user_snapshot(row, member)
    _altfinder_sync_presence_snapshot(row, member, increment_history=True)
    _mark_altfinder_dirty()
    _altfinder_invalidate_guild_cache(member.guild.id)


def index_altfinder_message(message: discord.Message, *, backfill: bool = False) -> set[int]:
    if message.guild is None or message.author.bot:
        return set()
    content = message.clean_content.strip()
    if not content and not message.attachments:
        return set()
    if not content and message.attachments:
        content = "[attachment]"

    guild_state = get_guild_altfinder_state(message.guild.id)
    created_ts = message.created_at.timestamp()
    meta = guild_state.setdefault("meta", {})
    channels = guild_state.setdefault("channels", {})
    channel_row = channels.setdefault(
        str(message.channel.id),
        {
            "latest_message_id": 0,
            "earliest_message_id": 0,
            "last_message_ts": 0.0,
            "before_message_id": 0,
            "fully_scanned": False,
            "last_backfill_ts": 0.0,
        },
    )
    channel_row["latest_message_id"] = max(int(channel_row.get("latest_message_id", 0) or 0), int(message.id))
    earliest = int(channel_row.get("earliest_message_id", 0) or 0)
    channel_row["earliest_message_id"] = int(message.id) if earliest <= 0 else min(earliest, int(message.id))
    channel_row["last_message_ts"] = max(float(channel_row.get("last_message_ts", 0.0) or 0.0), created_ts)
    if backfill:
        channel_row["last_backfill_ts"] = time.time()
        meta["last_backfill_ts"] = time.time()
    else:
        meta["last_incremental_ts"] = time.time()
    meta["messages_indexed"] = int(meta.get("messages_indexed", 0) or 0) + 1
    meta["last_indexed_message_ts"] = max(float(meta.get("last_indexed_message_ts", 0.0) or 0.0), created_ts)

    user = message.author
    row = _altfinder_get_user_row(guild_state, user.id)
    _altfinder_apply_user_snapshot(row, user)
    row["message_count"] = int(row.get("message_count", 0) or 0) + 1
    row["last_message_ts"] = max(float(row.get("last_message_ts", 0.0) or 0.0), created_ts)
    row["message_total_chars"] = int(row.get("message_total_chars", 0) or 0) + len(content)
    row["message_total_words"] = int(row.get("message_total_words", 0) or 0) + len(WORD_PATTERN.findall(content))
    row["question_count"] = int(row.get("question_count", 0) or 0) + (1 if "?" in content else 0)
    row["exclaim_count"] = int(row.get("exclaim_count", 0) or 0) + (1 if "!" in content else 0)
    row["emoji_total"] = int(row.get("emoji_total", 0) or 0) + len(EMOJI_PATTERN.findall(content))
    row["uppercase_chars_total"] = int(row.get("uppercase_chars_total", 0) or 0) + sum(1 for ch in content if ch.isupper())
    row["link_count"] = int(row.get("link_count", 0) or 0) + (1 if LINK_PATTERN.search(content) else 0)
    row["attachment_count"] = int(row.get("attachment_count", 0) or 0) + (1 if message.attachments else 0)
    row["mention_message_count"] = int(row.get("mention_message_count", 0) or 0) + (1 if message.mentions else 0)
    row["reply_message_count"] = int(row.get("reply_message_count", 0) or 0) + (1 if message.reference else 0)
    _altfinder_counter_update(row, "top_channels", message.channel.id, 1, 18)
    message_dt = message.created_at.astimezone(_safe_zoneinfo(get_guild_engagement_timezone(message.guild.id)))
    _altfinder_counter_update(row, "active_hours", message_dt.hour, 1, 24)
    _altfinder_counter_update(row, "active_weekdays", message_dt.weekday(), 1, 7)
    _altfinder_sync_presence_snapshot(row, user, increment_history=False)

    tokens = _altfinder_extract_valid_tokens(content)
    row["topic_token_total"] = int(row.get("topic_token_total", 0) or 0) + len(tokens)
    for token in tokens[:18]:
        _altfinder_counter_update(row, "topics", token, 1, 40)
    for bigram in _altfinder_extract_bigrams(tokens[:24])[:18]:
        _altfinder_counter_update(row, "bigrams", bigram, 1, 40)
    if tokens:
        _altfinder_counter_update(row, "starter_tokens", tokens[0], 1, 24)
        _altfinder_counter_update(row, "ending_tokens", tokens[-1], 1, 24)
    _aicrush_remember_message_author(int(message.id), int(user.id), created_ts)
    _aicrush_append_unique_sample(row["samples"], content, 12)

    impacted_ids: set[int] = {user.id}
    mention_ids = {
        int(member.id)
        for member in message.mentions
        if not member.bot and member.id != user.id
    }
    for mention_id in mention_ids:
        _altfinder_counter_update(row, "mention_targets", mention_id, 1, 40)
        impacted_ids.add(mention_id)

    reply_target_id = _aicrush_resolve_reply_target_id(message)
    if reply_target_id is not None and reply_target_id != user.id:
        _altfinder_counter_update(row, "reply_targets", reply_target_id, 1, 40)
        impacted_ids.add(reply_target_id)

    recent_others = _altfinder_track_recent_channel_author(
        message.guild.id,
        message.channel.id,
        user.id,
        created_ts,
    )
    for other_id in recent_others[:12]:
        _altfinder_counter_update(row, "copresence_targets", other_id, 1, 45)
        impacted_ids.add(other_id)

    _mark_altfinder_dirty()
    _altfinder_invalidate_guild_cache(message.guild.id)
    return impacted_ids


async def run_altfinder_backfill(
    guild: discord.Guild,
    *,
    message_budget: int | None = None,
    time_budget_seconds: float | None = None,
) -> dict[str, Any]:
    guild_state = get_guild_altfinder_state(guild.id)
    channels = get_readable_text_channels(guild)
    if AICRUSH_MAX_CHANNELS > 0:
        channels = channels[:AICRUSH_MAX_CHANNELS]
    channel_rows = guild_state.setdefault("channels", {})
    for channel in channels:
        channel_rows.setdefault(
            str(channel.id),
            {
                "latest_message_id": 0,
                "earliest_message_id": 0,
                "last_message_ts": 0.0,
                "before_message_id": 0,
                "fully_scanned": False,
                "last_backfill_ts": 0.0,
            },
        )

    remaining_budget = max(200, int(message_budget or ALTFINDER_BACKFILL_MESSAGE_BUDGET))
    deadline = time.monotonic() + float(time_budget_seconds or ALTFINDER_BACKFILL_TIME_BUDGET_SECONDS)
    fetched_messages: list[discord.Message] = []
    processed_channels = 0
    passes = 0

    while remaining_budget > 0 and time.monotonic() < deadline:
        passes += 1
        pass_scanned = 0
        channel_priority = sorted(
            channels,
            key=lambda channel: (
                1 if bool(channel_rows.get(str(channel.id), {}).get("fully_scanned")) else 0,
                float(channel_rows.get(str(channel.id), {}).get("last_backfill_ts", 0.0) or 0.0),
            ),
        )
        for channel in channel_priority:
            if remaining_budget <= 0 or time.monotonic() >= deadline:
                break
            row = channel_rows.setdefault(str(channel.id), {})
            if bool(row.get("fully_scanned")):
                continue
            per_channel_limit = min(max(50, AICRUSH_SCAN_PER_CHANNEL), remaining_budget)
            history_kwargs: dict[str, Any] = {"limit": per_channel_limit}
            before_message_id = int(row.get("before_message_id", 0) or 0)
            if before_message_id <= 0:
                before_message_id = int(row.get("earliest_message_id", 0) or 0)
            if before_message_id > 0:
                history_kwargs["before"] = discord.Object(id=before_message_id)
            batch: list[discord.Message] = []
            try:
                async for msg in channel.history(**history_kwargs):
                    if not msg.author.bot:
                        batch.append(msg)
            except (discord.Forbidden, discord.HTTPException):
                continue
            processed_channels += 1
            row["last_backfill_ts"] = time.time()
            if not batch:
                row["fully_scanned"] = True
                continue
            oldest_id = min(int(msg.id) for msg in batch)
            row["before_message_id"] = oldest_id
            earliest = int(row.get("earliest_message_id", 0) or 0)
            row["earliest_message_id"] = oldest_id if earliest <= 0 else min(earliest, oldest_id)
            if len(batch) < per_channel_limit:
                row["fully_scanned"] = True
            fetched_messages.extend(batch)
            remaining_budget -= len(batch)
            pass_scanned += len(batch)
            if (
                AICRUSH_SCAN_PAUSE_EVERY > 0
                and AICRUSH_SCAN_PAUSE_SECONDS > 0
                and pass_scanned % AICRUSH_SCAN_PAUSE_EVERY == 0
            ):
                await asyncio.sleep(AICRUSH_SCAN_PAUSE_SECONDS)
        if pass_scanned <= 0:
            break

    fetched_messages.sort(key=lambda msg: (msg.created_at.timestamp(), int(msg.id)))
    for msg in fetched_messages:
        index_altfinder_message(msg, backfill=True)

    channels_total = len(channels)
    channels_fully_scanned = sum(
        1
        for row in channel_rows.values()
        if isinstance(row, dict) and bool(row.get("fully_scanned"))
    )
    meta = guild_state.setdefault("meta", {})
    meta["last_backfill_ts"] = time.time()
    _mark_altfinder_dirty()
    return {
        "scanned_messages": len(fetched_messages),
        "channels_considered": channels_total,
        "channels_touched": processed_channels,
        "channels_fully_scanned": channels_fully_scanned,
        "messages_indexed": int(meta.get("messages_indexed", 0) or 0),
        "passes": passes,
    }


def _altfinder_user_metrics(row: dict[str, Any]) -> dict[str, Any]:
    message_count = int(row.get("message_count", 0) or 0)
    total_chars = int(row.get("message_total_chars", 0) or 0)
    total_words = int(row.get("message_total_words", 0) or 0)
    topic_total = int(row.get("topic_token_total", 0) or 0)
    topics = row.get("topics", {}) if isinstance(row.get("topics"), dict) else {}
    return {
        "message_count": message_count,
        "avg_len": (total_chars / max(1, message_count)) if message_count > 0 else 0.0,
        "avg_words": (total_words / max(1, message_count)) if message_count > 0 else 0.0,
        "question_ratio": int(row.get("question_count", 0) or 0) / max(1, message_count),
        "exclaim_ratio": int(row.get("exclaim_count", 0) or 0) / max(1, message_count),
        "emoji_per_msg": int(row.get("emoji_total", 0) or 0) / max(1, message_count),
        "uppercase_ratio": int(row.get("uppercase_chars_total", 0) or 0) / max(1, total_chars),
        "link_ratio": int(row.get("link_count", 0) or 0) / max(1, message_count),
        "attachment_ratio": int(row.get("attachment_count", 0) or 0) / max(1, message_count),
        "mention_rate": int(row.get("mention_message_count", 0) or 0) / max(1, message_count),
        "reply_rate": int(row.get("reply_message_count", 0) or 0) / max(1, message_count),
        "vocab_diversity": len(topics) / max(1, topic_total),
        "topics": topics,
        "bigrams": row.get("bigrams", {}) if isinstance(row.get("bigrams"), dict) else {},
        "starter_tokens": row.get("starter_tokens", {}) if isinstance(row.get("starter_tokens"), dict) else {},
        "ending_tokens": row.get("ending_tokens", {}) if isinstance(row.get("ending_tokens"), dict) else {},
        "top_channels": row.get("top_channels", {}) if isinstance(row.get("top_channels"), dict) else {},
        "active_hours": row.get("active_hours", {}) if isinstance(row.get("active_hours"), dict) else {},
        "active_weekdays": row.get("active_weekdays", {}) if isinstance(row.get("active_weekdays"), dict) else {},
        "presence_hours": row.get("presence_hours", {}) if isinstance(row.get("presence_hours"), dict) else {},
        "presence_weekdays": row.get("presence_weekdays", {}) if isinstance(row.get("presence_weekdays"), dict) else {},
        "status_counts": row.get("status_counts", {}) if isinstance(row.get("status_counts"), dict) else {},
        "status_transitions": row.get("status_transitions", {}) if isinstance(row.get("status_transitions"), dict) else {},
        "last_status": str(row.get("last_status", "offline") or "offline"),
        "reply_targets": row.get("reply_targets", {}) if isinstance(row.get("reply_targets"), dict) else {},
        "mention_targets": row.get("mention_targets", {}) if isinstance(row.get("mention_targets"), dict) else {},
        "copresence_targets": row.get("copresence_targets", {}) if isinstance(row.get("copresence_targets"), dict) else {},
        "samples": row.get("samples", []) if isinstance(row.get("samples"), list) else [],
        "profile_signatures": row.get("profile_signatures", {}) if isinstance(row.get("profile_signatures"), dict) else {},
    }


@dataclass
class AltFinderContext:
    target_row: dict[str, Any]
    target_metrics: dict[str, Any]
    target_message_count: int
    scan_coverage: dict[str, Any]
    candidate_rows: dict[int, dict[str, Any]]
    current_member_ids: set[int]
    suspect_ids: list[int]


def collect_altfinder_context(guild: discord.Guild, target_member: discord.Member) -> AltFinderContext:
    refresh_altfinder_member_directory(guild)
    guild_state = get_guild_altfinder_state(guild.id)
    users = guild_state.get("users", {}) if isinstance(guild_state.get("users"), dict) else {}
    target_row = _altfinder_get_user_row(guild_state, target_member.id)
    target_metrics = _altfinder_user_metrics(target_row)
    candidate_rows: dict[int, dict[str, Any]] = {}
    for user_key, row in users.items():
        if not isinstance(row, dict):
            continue
        try:
            user_id = int(user_key)
        except (TypeError, ValueError):
            continue
        if user_id == target_member.id:
            continue
        candidate_rows[user_id] = row
    current_member_ids = {member.id for member in guild.members if not member.bot}
    channels = guild_state.get("channels", {}) if isinstance(guild_state.get("channels"), dict) else {}
    channels_total = len(channels)
    channels_fully_scanned = sum(
        1
        for row in channels.values()
        if isinstance(row, dict) and bool(row.get("fully_scanned"))
    )
    meta = guild_state.get("meta", {}) if isinstance(guild_state.get("meta"), dict) else {}
    scan_coverage = {
        "channels_total": channels_total,
        "channels_fully_scanned": channels_fully_scanned,
        "messages_indexed": int(meta.get("messages_indexed", 0) or 0),
        "last_backfill_ts": float(meta.get("last_backfill_ts", 0.0) or 0.0),
        "last_indexed_message_ts": float(meta.get("last_indexed_message_ts", 0.0) or 0.0),
    }
    return AltFinderContext(
        target_row=target_row,
        target_metrics=target_metrics,
        target_message_count=int(target_row.get("message_count", 0) or 0),
        scan_coverage=scan_coverage,
        candidate_rows=candidate_rows,
        current_member_ids=current_member_ids,
        suspect_ids=get_altfinder_suspects(guild.id, target_member.id),
    )


def _altfinder_name_similarity(target_row: dict[str, Any], candidate_row: dict[str, Any]) -> float:
    target_aliases = target_row.get("aliases", {}) if isinstance(target_row.get("aliases"), dict) else {}
    candidate_aliases = candidate_row.get("aliases", {}) if isinstance(candidate_row.get("aliases"), dict) else {}
    target_tokens = set(str(item) for item in target_aliases.get("tokens", []) if item)
    candidate_tokens = set(str(item) for item in candidate_aliases.get("tokens", []) if item)
    target_phrases = set(str(item) for item in target_aliases.get("phrases", []) if item)
    candidate_phrases = set(str(item) for item in candidate_aliases.get("phrases", []) if item)
    token_overlap = _altfinder_set_overlap(target_tokens, candidate_tokens)
    phrase_overlap = _altfinder_set_overlap(target_phrases, candidate_phrases)
    display_similarity = difflib.SequenceMatcher(
        None,
        _altfinder_compact_name(str(target_row.get("display_name", ""))),
        _altfinder_compact_name(str(candidate_row.get("display_name", ""))),
    ).ratio()
    username_similarity = difflib.SequenceMatcher(
        None,
        _altfinder_compact_name(str(target_row.get("username", ""))),
        _altfinder_compact_name(str(candidate_row.get("username", ""))),
    ).ratio()
    return round(
        min(1.0, (token_overlap * 0.3) + (phrase_overlap * 0.25) + (display_similarity * 0.25) + (username_similarity * 0.2)),
        4,
    )


def _altfinder_metadata_components(target_row: dict[str, Any], candidate_row: dict[str, Any]) -> dict[str, Any]:
    name_similarity = _altfinder_name_similarity(target_row, candidate_row)
    created_proximity = _altfinder_time_proximity_score(
        float(target_row.get("created_at_ts", 0.0) or 0.0),
        float(candidate_row.get("created_at_ts", 0.0) or 0.0),
    )
    joined_proximity = _altfinder_time_proximity_score(
        float(target_row.get("joined_at_ts", 0.0) or 0.0),
        float(candidate_row.get("joined_at_ts", 0.0) or 0.0),
    )
    target_avatar_key = str(target_row.get("avatar_key", "") or "")
    candidate_avatar_key = str(candidate_row.get("avatar_key", "") or "")
    target_default_avatar_key = str(target_row.get("default_avatar_key", "") or "")
    candidate_default_avatar_key = str(candidate_row.get("default_avatar_key", "") or "")
    exact_avatar_match = bool(target_avatar_key and target_avatar_key == candidate_avatar_key)
    exact_default_avatar_match = bool(
        target_default_avatar_key
        and candidate_default_avatar_key
        and target_default_avatar_key == candidate_default_avatar_key
    )
    target_signatures = target_row.get("profile_signatures", {}) if isinstance(target_row.get("profile_signatures"), dict) else {}
    candidate_signatures = candidate_row.get("profile_signatures", {}) if isinstance(candidate_row.get("profile_signatures"), dict) else {}
    shared_signatures = set(target_signatures).intersection(candidate_signatures)
    metadata_similarity = min(
        1.0,
        (name_similarity * 0.34)
        + (created_proximity * 0.14)
        + (joined_proximity * 0.12)
        + (0.26 if exact_avatar_match else 0.0)
        + (0.12 if exact_default_avatar_match else 0.0)
        + min(0.2, len(shared_signatures) * 0.1),
    )
    return {
        "name_similarity": round(name_similarity, 4),
        "created_proximity": round(created_proximity, 4),
        "joined_proximity": round(joined_proximity, 4),
        "exact_avatar_match": exact_avatar_match,
        "exact_default_avatar_match": exact_default_avatar_match,
        "shared_signature_count": len(shared_signatures),
        "shared_signatures": sorted(shared_signatures)[:4],
        "metadata_similarity": round(metadata_similarity, 4),
    }


def _altfinder_resolve_label(
    guild: discord.Guild,
    candidate_id: int,
    candidate_row: dict[str, Any],
    current_member_ids: set[int],
) -> dict[str, str]:
    if candidate_id in current_member_ids:
        member = guild.get_member(candidate_id)
        if member is not None:
            return {
                "display": member.mention,
                "plain": member.display_name,
                "scope": "current member",
            }
    stored_name = str(candidate_row.get("display_name", "") or candidate_row.get("username", "") or "").strip()
    plain = stored_name if stored_name else f"historical user {candidate_id}"
    return {
        "display": f"{plain} (`{candidate_id}`)",
        "plain": plain,
        "scope": "historical seen",
    }


def build_altfinder_candidate_pool(
    guild: discord.Guild,
    target_member: discord.Member,
    context: AltFinderContext,
    limit: int,
) -> list[dict[str, Any]]:
    target_metrics = context.target_metrics
    target_row = context.target_row
    suspect_id_set = {int(user_id) for user_id in context.suspect_ids}
    candidates: list[dict[str, Any]] = []
    for candidate_id, candidate_row in context.candidate_rows.items():
        candidate_metrics = _altfinder_user_metrics(candidate_row)
        candidate_message_count = int(candidate_metrics.get("message_count", 0) or 0)
        if candidate_message_count <= 0:
            continue
        is_suspect = candidate_id in suspect_id_set

        style_similarity = min(
            1.0,
            (_altfinder_scalar_similarity(float(target_metrics["avg_len"]), float(candidate_metrics["avg_len"]), 80.0) * 0.25)
            + (_altfinder_scalar_similarity(float(target_metrics["avg_words"]), float(candidate_metrics["avg_words"]), 18.0) * 0.12)
            + (_altfinder_scalar_similarity(float(target_metrics["question_ratio"]), float(candidate_metrics["question_ratio"]), 0.45) * 0.18)
            + (_altfinder_scalar_similarity(float(target_metrics["exclaim_ratio"]), float(candidate_metrics["exclaim_ratio"]), 0.45) * 0.18)
            + (_altfinder_scalar_similarity(float(target_metrics["emoji_per_msg"]), float(candidate_metrics["emoji_per_msg"]), 2.0) * 0.12)
            + (_altfinder_scalar_similarity(float(target_metrics["uppercase_ratio"]), float(candidate_metrics["uppercase_ratio"]), 0.18) * 0.08)
            + (_altfinder_scalar_similarity(float(target_metrics["link_ratio"]), float(candidate_metrics["link_ratio"]), 0.4) * 0.06)
            + (_altfinder_scalar_similarity(float(target_metrics["mention_rate"]), float(candidate_metrics["mention_rate"]), 0.5) * 0.06)
            + (_altfinder_scalar_similarity(float(target_metrics["reply_rate"]), float(candidate_metrics["reply_rate"]), 0.5) * 0.06)
            + (_altfinder_scalar_similarity(float(target_metrics["vocab_diversity"]), float(candidate_metrics["vocab_diversity"]), 0.45) * 0.12)
            + (_altfinder_counter_overlap(target_metrics["starter_tokens"], candidate_metrics["starter_tokens"]) * 0.08)
            + (_altfinder_counter_overlap(target_metrics["ending_tokens"], candidate_metrics["ending_tokens"]) * 0.06)
            + (_altfinder_counter_overlap(target_metrics["bigrams"], candidate_metrics["bigrams"]) * 0.15),
        )
        message_schedule_similarity = min(
            1.0,
            (_altfinder_counter_overlap(target_metrics["active_hours"], candidate_metrics["active_hours"]) * 0.68)
            + (_altfinder_counter_overlap(target_metrics["active_weekdays"], candidate_metrics["active_weekdays"]) * 0.32),
        )
        presence_schedule_similarity = min(
            1.0,
            (_altfinder_counter_overlap(target_metrics["presence_hours"], candidate_metrics["presence_hours"]) * 0.55)
            + (_altfinder_counter_overlap(target_metrics["presence_weekdays"], candidate_metrics["presence_weekdays"]) * 0.2)
            + (_altfinder_counter_overlap(target_metrics["status_counts"], candidate_metrics["status_counts"]) * 0.15)
            + (_altfinder_counter_overlap(target_metrics["status_transitions"], candidate_metrics["status_transitions"]) * 0.1),
        )
        schedule_similarity = min(
            1.0,
            (message_schedule_similarity * 0.62) + (presence_schedule_similarity * 0.38),
        )
        channel_similarity = _altfinder_counter_overlap(
            target_metrics["top_channels"],
            candidate_metrics["top_channels"],
        )
        reply_overlap = _altfinder_counter_overlap(
            target_metrics["reply_targets"],
            candidate_metrics["reply_targets"],
        )
        mention_overlap = _altfinder_counter_overlap(
            target_metrics["mention_targets"],
            candidate_metrics["mention_targets"],
        )
        copresence_overlap = _altfinder_counter_overlap(
            target_metrics["copresence_targets"],
            candidate_metrics["copresence_targets"],
        )
        interaction_similarity = min(
            1.0,
            (reply_overlap * 0.4) + (mention_overlap * 0.35) + (copresence_overlap * 0.25),
        )
        topic_similarity = min(
            1.0,
            (_altfinder_counter_overlap(target_metrics["topics"], candidate_metrics["topics"]) * 0.72)
            + (_altfinder_counter_overlap(target_metrics["bigrams"], candidate_metrics["bigrams"]) * 0.28),
        )
        metadata = _altfinder_metadata_components(target_row, candidate_row)
        coverage_factor = min(
            1.0,
            (min(int(target_metrics["message_count"]), candidate_message_count) / 90.0),
        )
        overlap_hits = sum(
            1
            for value in (
                style_similarity,
                schedule_similarity,
                channel_similarity,
                interaction_similarity,
                topic_similarity,
                float(metadata["metadata_similarity"]),
            )
            if value >= 0.25
        )
        evidence_density = min(
            1.0,
            (coverage_factor * 0.48)
            + (overlap_hits * 0.08)
            + (min(0.25, channel_similarity + interaction_similarity) * 0.3)
            + (min(0.14, presence_schedule_similarity) if presence_schedule_similarity > 0 else 0.0),
        )

        heuristic_score = (
            (style_similarity * 2.35)
            + (message_schedule_similarity * 0.9)
            + (presence_schedule_similarity * 0.95)
            + (schedule_similarity * 0.4)
            + (channel_similarity * 1.15)
            + (interaction_similarity * 1.55)
            + (topic_similarity * 1.95)
            + (float(metadata["metadata_similarity"]) * 2.15)
            + (evidence_density * 1.25)
        )
        if bool(metadata["exact_avatar_match"]):
            heuristic_score += 0.9
        if int(metadata["shared_signature_count"]) > 0:
            heuristic_score += 0.75
        if is_suspect:
            heuristic_score += 0.18

        if not (
            heuristic_score >= 1.35
            or float(metadata["metadata_similarity"]) >= 0.62
            or (style_similarity >= 0.56 and topic_similarity >= 0.42)
            or (presence_schedule_similarity >= 0.35 and channel_similarity >= 0.28)
            or is_suspect
        ):
            continue

        label_info = _altfinder_resolve_label(
            guild,
            candidate_id,
            candidate_row,
            context.current_member_ids,
        )
        common_channel_ids = [
            int(channel_id)
            for channel_id, _ in _altfinder_counter_common(
                target_metrics["top_channels"],
                candidate_metrics["top_channels"],
                4,
            )
            if str(channel_id).isdigit()
        ]
        common_hours = [
            int(hour)
            for hour, _ in _altfinder_counter_common(
                target_metrics["active_hours"],
                candidate_metrics["active_hours"],
                4,
            )
            if str(hour).isdigit()
        ]
        common_weekdays = [
            int(day)
            for day, _ in _altfinder_counter_common(
                target_metrics["active_weekdays"],
                candidate_metrics["active_weekdays"],
                3,
            )
            if str(day).isdigit()
        ]
        shared_reply_targets = [
            int(value)
            for value, _ in _altfinder_counter_common(
                target_metrics["reply_targets"],
                candidate_metrics["reply_targets"],
                4,
            )
            if str(value).isdigit()
        ]
        shared_mention_targets = [
            int(value)
            for value, _ in _altfinder_counter_common(
                target_metrics["mention_targets"],
                candidate_metrics["mention_targets"],
                4,
            )
            if str(value).isdigit()
        ]
        shared_copresence_targets = [
            int(value)
            for value, _ in _altfinder_counter_common(
                target_metrics["copresence_targets"],
                candidate_metrics["copresence_targets"],
                4,
            )
            if str(value).isdigit()
        ]

        candidates.append(
            {
                "candidate_id": candidate_id,
                "candidate_row": candidate_row,
                "candidate_metrics": candidate_metrics,
                "display_label": label_info["display"],
                "plain_label": label_info["plain"],
                "scope_label": label_info["scope"],
                "is_suspect": is_suspect,
                "style_similarity": round(style_similarity, 4),
                "message_schedule_similarity": round(message_schedule_similarity, 4),
                "presence_schedule_similarity": round(presence_schedule_similarity, 4),
                "schedule_similarity": round(schedule_similarity, 4),
                "channel_similarity": round(channel_similarity, 4),
                "reply_overlap": round(reply_overlap, 4),
                "mention_overlap": round(mention_overlap, 4),
                "copresence_overlap": round(copresence_overlap, 4),
                "interaction_similarity": round(interaction_similarity, 4),
                "topic_similarity": round(topic_similarity, 4),
                "evidence_density": round(evidence_density, 4),
                "heuristic_score": round(heuristic_score, 4),
                "metadata_similarity": float(metadata["metadata_similarity"]),
                "metadata": metadata,
                "common_channel_ids": common_channel_ids,
                "common_hours": common_hours,
                "common_weekdays": common_weekdays,
                "shared_reply_targets": shared_reply_targets,
                "shared_mention_targets": shared_mention_targets,
                "shared_copresence_targets": shared_copresence_targets,
                "target_texture": _altfinder_sample_texture(target_metrics["samples"], limit=2),
                "candidate_texture": _altfinder_sample_texture(candidate_metrics["samples"], limit=2),
                "message_count": candidate_message_count,
            }
        )

    candidates.sort(
        key=lambda row: (
            1 if bool(row.get("is_suspect")) else 0,
            float(row.get("heuristic_score", 0.0)),
            float(row.get("evidence_density", 0.0)),
            float(row.get("metadata_similarity", 0.0)),
        ),
        reverse=True,
    )
    return candidates[: max(limit, ALTFINDER_MAX_RESULTS + 3)]


def _altfinder_rank_schema() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "altfinder_rank",
            "schema": {
                "type": "object",
                "properties": {
                    "ranked_user_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "summary": {"type": "string"},
                },
                "required": ["ranked_user_ids", "summary"],
                "additionalProperties": False,
            },
        },
    }


async def rerank_altfinder_candidates_with_ai(
    target_member: discord.Member,
    *,
    context: AltFinderContext,
    candidates: list[dict[str, Any]],
) -> list[int]:
    if len(candidates) < 2:
        return []
    candidate_lines = []
    shortlist = candidates[:7]
    for row in shortlist:
        metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
        candidate_lines.append(
            (
                f"- id={row['candidate_id']} label={row['plain_label']} scope={row['scope_label']} "
                f"suspect={bool(row.get('is_suspect'))} "
                f"score={float(row['heuristic_score']):.2f} evidence={float(row['evidence_density']):.2f} "
                f"style={float(row['style_similarity']):.2f} msg_schedule={float(row['message_schedule_similarity']):.2f} "
                f"presence={float(row['presence_schedule_similarity']):.2f} schedule={float(row['schedule_similarity']):.2f} "
                f"channels={float(row['channel_similarity']):.2f} interactions={float(row['interaction_similarity']):.2f} "
                f"topics={float(row['topic_similarity']):.2f} metadata={float(row['metadata_similarity']):.2f} "
                f"avatar_match={bool(metadata.get('exact_avatar_match'))} "
                f"texture={row['candidate_texture']}"
            )
        )
    prompt = (
        "Rank likely alt-account candidates for a Discord moderation report.\n"
        "Prioritize visible chat behavior and metadata together; metadata alone is not enough.\n"
        "Return the best ranking of candidate ids only. Do not invent ids.\n"
        f"Target: {target_member.display_name}\n"
        f"Target messages indexed: {context.target_message_count}\n"
        f"Target texture: {_altfinder_sample_texture(context.target_metrics['samples'], limit=2)}\n"
        "Candidates:\n"
        + "\n".join(candidate_lines)
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You rank alt-account evidence for Discord moderation. Use the supplied evidence only, "
                "prefer higher-confidence chat-behavior matches over cosmetic-only matches, and return JSON only."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    try:
        if GROQ_API_KEY:
            raw = await request_groq_completion(
                messages,
                max_tokens=220,
                temperature=0.1,
                model_override=ALTFINDER_RANK_MODEL or None,
                fallback_models=ALTFINDER_FALLBACK_MODELS,
                response_format=_altfinder_rank_schema(),
                include_fallback_notice=False,
                feature="altfinder_rank",
            )
        else:
            raw = await request_ai_completion(
                messages,
                max_tokens=220,
                temperature=0.1,
                policy_key="altfinder_rank",
                model_override=(ALTFINDER_RANK_MODEL or None) if AI_PROVIDER == "groq" else None,
                fallback_models=ALTFINDER_FALLBACK_MODELS if AI_PROVIDER == "groq" else None,
                response_format=_altfinder_rank_schema() if AI_PROVIDER == "groq" else None,
                include_fallback_notice=False,
            )
        payload = _extract_first_json_object(raw)
        if not isinstance(payload, dict):
            return []
        ranked_ids = payload.get("ranked_user_ids", [])
        allowed_ids = {int(row["candidate_id"]) for row in shortlist}
        output: list[int] = []
        if isinstance(ranked_ids, list):
            for item in ranked_ids:
                try:
                    candidate_id = int(item)
                except (TypeError, ValueError):
                    continue
                if candidate_id in allowed_ids and candidate_id not in output:
                    output.append(candidate_id)
        return output
    except Exception:
        return []


def _altfinder_apply_rank_order(
    candidates: list[dict[str, Any]], ranked_user_ids: list[int]
) -> list[dict[str, Any]]:
    if not ranked_user_ids:
        return list(candidates)
    mapped = {int(row["candidate_id"]): row for row in candidates}
    ordered: list[dict[str, Any]] = []
    seen: set[int] = set()
    for candidate_id in ranked_user_ids:
        row = mapped.get(int(candidate_id))
        if row is None:
            continue
        ordered.append(row)
        seen.add(int(candidate_id))
    for row in candidates:
        candidate_id = int(row["candidate_id"])
        if candidate_id not in seen:
            ordered.append(row)
    return ordered


def annotate_altfinder_confidences(
    candidates: list[dict[str, Any]],
    target_message_count: int,
) -> None:
    if not candidates:
        return
    top_score = max(float(candidates[0].get("heuristic_score", 0.0)), 0.01)
    for row in candidates:
        heuristic_score = float(row.get("heuristic_score", 0.0))
        evidence_density = float(row.get("evidence_density", 0.0))
        metadata_similarity = float(row.get("metadata_similarity", 0.0))
        style_similarity = float(row.get("style_similarity", 0.0))
        topic_similarity = float(row.get("topic_similarity", 0.0))
        relative_strength = min(1.0, heuristic_score / top_score)
        confidence = min(
            0.97,
            (min(1.0, heuristic_score / 8.0) * 0.36)
            + (evidence_density * 0.28)
            + (relative_strength * 0.18)
            + (metadata_similarity * 0.18),
        )
        if target_message_count < 18 or int(row.get("message_count", 0) or 0) < 18:
            confidence = min(confidence, 0.62)
        if target_message_count < 8 or int(row.get("message_count", 0) or 0) < 8:
            confidence = min(confidence, 0.44)
        if metadata_similarity >= 0.72 and style_similarity < 0.32 and topic_similarity < 0.25:
            confidence = min(confidence, 0.58)
        if confidence >= 0.78:
            band = "high"
        elif confidence >= 0.55:
            band = "medium"
        else:
            band = "low"
        row["confidence"] = round(max(0.06, confidence), 4)
        row["confidence_band"] = band


def _altfinder_short_evidence_summary(row: dict[str, Any]) -> str:
    metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
    tags: list[str] = []
    if bool(row.get("is_suspect")):
        tags.append("configured suspect")
    if bool(metadata.get("exact_avatar_match")):
        tags.append("exact avatar match")
    if int(metadata.get("shared_signature_count", 0) or 0) > 0:
        tags.append("shared profile signature")
    if float(row.get("style_similarity", 0.0)) >= 0.55:
        tags.append("strong style match")
    if float(row.get("presence_schedule_similarity", 0.0)) >= 0.35:
        tags.append("similar online/offline pattern")
    elif float(row.get("schedule_similarity", 0.0)) >= 0.45:
        tags.append("same activity window")
    if float(row.get("channel_similarity", 0.0)) >= 0.4:
        tags.append("same channel footprint")
    if float(row.get("interaction_similarity", 0.0)) >= 0.38:
        tags.append("shared interaction pattern")
    if float(row.get("topic_similarity", 0.0)) >= 0.42:
        tags.append("same topic vocabulary")
    if float(row.get("metadata_similarity", 0.0)) >= 0.4 and "exact avatar match" not in tags:
        tags.append("metadata overlap")
    return ", ".join(tags[:3]) if tags else "light overlap only"


def _altfinder_channel_names(guild: discord.Guild, channel_ids: list[int]) -> str:
    names: list[str] = []
    for channel_id in channel_ids[:4]:
        channel = guild.get_channel(channel_id)
        if isinstance(channel, discord.abc.GuildChannel):
            names.append(f"#{channel.name}")
        else:
            names.append(f"channel {channel_id}")
    return ", ".join(names) if names else "limited overlap"


def _altfinder_format_hours(hours: list[int]) -> str:
    if not hours:
        return "limited overlap"
    formatted = [f"{int(hour):02d}:00" for hour in hours[:4]]
    return ", ".join(formatted)


def _altfinder_format_weekdays(days: list[int]) -> str:
    mapping = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    labels = [mapping[int(day)] for day in days[:3] if 0 <= int(day) < len(mapping)]
    return ", ".join(labels) if labels else "limited overlap"


def _altfinder_shared_target_labels(
    guild: discord.Guild,
    ids: list[int],
    context: AltFinderContext,
) -> str:
    labels: list[str] = []
    for target_id in ids[:3]:
        member = guild.get_member(target_id)
        if member is not None:
            labels.append(member.display_name)
            continue
        row = context.candidate_rows.get(target_id)
        if isinstance(row, dict):
            label = str(row.get("display_name", "") or row.get("username", "") or target_id)
            labels.append(label)
        else:
            labels.append(str(target_id))
    return ", ".join(labels) if labels else "limited overlap"


def _altfinder_detailed_evidence_block(
    guild: discord.Guild,
    row: dict[str, Any],
    *,
    context: AltFinderContext,
) -> str:
    metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
    interaction_targets = row.get("shared_reply_targets", []) + row.get("shared_mention_targets", [])
    metadata_flags: list[str] = []
    if bool(metadata.get("exact_avatar_match")):
        metadata_flags.append("exact avatar")
    if bool(metadata.get("exact_default_avatar_match")):
        metadata_flags.append("same default avatar")
    if int(metadata.get("shared_signature_count", 0) or 0) > 0:
        metadata_flags.append("shared profile snapshot")
    if not metadata_flags:
        metadata_flags.append("no exact cosmetic match")
    return (
        f"{row['display_label']} [{row['scope_label']}{' | suspect' if row.get('is_suspect') else ''}]\n"
        f"- style similarity: `{float(row.get('style_similarity', 0.0)):.2f}`\n"
        f"- schedule/activity overlap: `{float(row.get('message_schedule_similarity', 0.0)):.2f}` | "
        f"hours { _altfinder_format_hours(row.get('common_hours', [])) } | "
        f"days { _altfinder_format_weekdays(row.get('common_weekdays', [])) }\n"
        f"- online/offline pattern: `{float(row.get('presence_schedule_similarity', 0.0)):.2f}` | "
        f"status overlap `{float(_altfinder_counter_overlap(context.target_metrics['status_counts'], row.get('candidate_metrics', {}).get('status_counts', {}))):.2f}`\n"
        f"- channel overlap: `{float(row.get('channel_similarity', 0.0)):.2f}` | "
        f"{_altfinder_channel_names(guild, row.get('common_channel_ids', []))}\n"
        f"- interaction overlap: `{float(row.get('interaction_similarity', 0.0)):.2f}` | "
        f"shared targets { _altfinder_shared_target_labels(guild, interaction_targets, context) }\n"
        f"- linguistic fingerprint: avg words `{float(row.get('candidate_metrics', {}).get('avg_words', 0.0)):.1f}` | "
        f"starter overlap `{float(_altfinder_counter_overlap(context.target_metrics['starter_tokens'], row.get('candidate_metrics', {}).get('starter_tokens', {}))):.2f}` | "
        f"ending overlap `{float(_altfinder_counter_overlap(context.target_metrics['ending_tokens'], row.get('candidate_metrics', {}).get('ending_tokens', {}))):.2f}`\n"
        f"- metadata similarity: `{float(row.get('metadata_similarity', 0.0)):.2f}` | "
        f"{', '.join(metadata_flags)} | name `{float(metadata.get('name_similarity', 0.0)):.2f}`\n"
        f"- sample texture: target `{row.get('target_texture', 'n/a')}` | candidate `{row.get('candidate_texture', 'n/a')}`"
    )


def _altfinder_suspect_focus_lines(
    suspect_ids: list[int],
    ranked_rows: list[dict[str, Any]],
) -> list[str]:
    if not suspect_ids:
        return []
    ranked_map = {int(row["candidate_id"]): row for row in ranked_rows}
    lines: list[str] = []
    for suspect_id in suspect_ids[:ALTFINDER_MAX_SUSPECTS]:
        row = ranked_map.get(int(suspect_id))
        if row is None:
            lines.append(f"- suspect `{suspect_id}`: limited evidence in readable history.")
            continue
        lines.append(
            (
                f"- {row['display_label']} | confidence `{int(float(row.get('confidence', 0.0)) * 100)}%` "
                f"({row.get('confidence_band', 'low')}) | {_altfinder_short_evidence_summary(row)}"
            )
        )
    return lines


async def build_altfinder_investigation_summary(
    target_member: discord.Member,
    *,
    ranked_rows: list[dict[str, Any]],
    context: AltFinderContext,
) -> str:
    local_lines: list[str] = []
    for row in ranked_rows[:3]:
        local_lines.append(
            (
                f"{row['plain_label']} ({row['scope_label']}): "
                f"confidence {int(float(row.get('confidence', 0.0)) * 100)}%, "
                f"style {float(row.get('style_similarity', 0.0)):.2f}, "
                f"presence {float(row.get('presence_schedule_similarity', 0.0)):.2f}, "
                f"topics {float(row.get('topic_similarity', 0.0)):.2f}, "
                f"metadata {float(row.get('metadata_similarity', 0.0)):.2f}, "
                f"evidence { _altfinder_short_evidence_summary(row) }."
            )
        )
    local_summary = "\n".join(local_lines)
    if not local_summary:
        return "No reliable shortlist yet."
    if not GROQ_API_KEY and not is_ai_configured():
        return local_summary

    prompt = (
        "Rewrite this into a factual Discord moderation investigation summary.\n"
        "Keep it to 3-5 short lines. Do not overstate certainty. Do not recommend action.\n"
        f"Target: {target_member.display_name}\n"
        f"Target messages indexed: {context.target_message_count}\n"
        f"Configured suspects: {', '.join(str(user_id) for user_id in context.suspect_ids) if context.suspect_ids else 'none'}\n"
        "Evidence summary:\n"
        f"{local_summary}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You write concise moderation summaries from supplied evidence only. "
                "Be factual, cautious, and avoid recommending punishment."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    try:
        if GROQ_API_KEY:
            return await request_groq_completion(
                messages,
                max_tokens=220,
                temperature=0.2,
                model_override=ALTFINDER_EXPLAIN_MODEL or None,
                fallback_models=ALTFINDER_FALLBACK_MODELS,
                include_fallback_notice=False,
                feature="altfinder_explain",
            )
        return await request_ai_completion(
            messages,
            max_tokens=220,
            temperature=0.2,
            policy_key="altfinder_explain",
            model_override=(ALTFINDER_EXPLAIN_MODEL or None) if AI_PROVIDER == "groq" else None,
            fallback_models=ALTFINDER_FALLBACK_MODELS if AI_PROVIDER == "groq" else None,
            include_fallback_notice=False,
        )
    except Exception:
        return local_summary


SOCIALINTEL_TENSION_HINTS = {
    "wrong",
    "disagree",
    "stupid",
    "hate",
    "nah",
    "never",
    "stop",
    "shut",
    "actually",
    "but",
    "however",
    "ridiculous",
    "trash",
    "idiot",
    "no way",
}
SOCIALINTEL_DEESCALATION_HINTS = {
    "fair",
    "understand",
    "sorry",
    "okay",
    "lets",
    "let's",
    "calm",
    "thanks",
    "appreciate",
    "agree to disagree",
    "all good",
    "my bad",
    "please",
}


def _socialintel_compact_excerpt(text: str, limit: int = 140) -> str:
    cleaned = " ".join((text or "").split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def _socialintel_pair_key(left_user_id: int, right_user_id: int) -> str:
    low, high = sorted((int(left_user_id), int(right_user_id)))
    return f"{low}:{high}"


def _socialintel_get_pair_row(
    guild_state: dict[str, Any],
    left_user_id: int,
    right_user_id: int,
) -> dict[str, Any]:
    pairs = guild_state.setdefault("pairs", {})
    key = _socialintel_pair_key(left_user_id, right_user_id)
    row = pairs.get(key)
    if not isinstance(row, dict):
        low, high = sorted((int(left_user_id), int(right_user_id)))
        row = {
            "user_ids": [low, high],
            "reply_counts": {},
            "mention_counts": {},
            "shared_channels": {},
            "shared_hours": {},
            "copresence_count": 0,
            "touch_count": 0,
            "last_active_ts": 0.0,
            "samples": [],
        }
        pairs[key] = row
    for field in ("reply_counts", "mention_counts", "shared_channels", "shared_hours"):
        if not isinstance(row.get(field), dict):
            row[field] = {}
    if not isinstance(row.get("samples"), list):
        row["samples"] = []
    return row


def _socialintel_increment_pair_edge(
    pair_row: dict[str, Any],
    field: str,
    from_user_id: int,
    to_user_id: int,
    amount: int,
) -> None:
    if amount <= 0:
        return
    counter = pair_row.get(field)
    if not isinstance(counter, dict):
        counter = {}
        pair_row[field] = counter
    key = f"{int(from_user_id)}->{int(to_user_id)}"
    counter[key] = int(counter.get(key, 0) or 0) + int(amount)


def _socialintel_update_pair_interaction(
    guild_state: dict[str, Any],
    left_user_id: int,
    right_user_id: int,
    *,
    kind: str,
    created_ts: float,
    channel_id: int,
    hour: int,
    sample_text: str,
) -> None:
    if left_user_id == right_user_id:
        return
    pair_row = _socialintel_get_pair_row(guild_state, left_user_id, right_user_id)
    pair_row["touch_count"] = int(pair_row.get("touch_count", 0) or 0) + 1
    pair_row["last_active_ts"] = max(float(pair_row.get("last_active_ts", 0.0) or 0.0), created_ts)
    _altfinder_counter_update(pair_row, "shared_channels", channel_id, 1, 18)
    _altfinder_counter_update(pair_row, "shared_hours", hour, 1, 24)
    if kind == "copresence":
        pair_row["copresence_count"] = int(pair_row.get("copresence_count", 0) or 0) + 1
    elif kind == "reply":
        _socialintel_increment_pair_edge(pair_row, "reply_counts", left_user_id, right_user_id, 1)
    elif kind == "mention":
        _socialintel_increment_pair_edge(pair_row, "mention_counts", left_user_id, right_user_id, 1)
    _aicrush_append_unique_sample(pair_row["samples"], sample_text, 8)


def _socialintel_track_recent_channel_author(
    guild_id: int,
    channel_id: int,
    author_id: int,
    created_ts: float,
) -> list[int]:
    key = (guild_id, channel_id)
    queue = SOCIALINTEL_CHANNEL_RECENT_AUTHORS[key]
    while queue and created_ts - queue[0][0] > AICRUSH_CHANNEL_RECENT_WINDOW_SECONDS:
        queue.popleft()
    others = {other_author for _, other_author in queue if other_author != author_id}
    queue.append((created_ts, author_id))
    return list(others)


def _socialintel_tension_score(text: str) -> float:
    lowered = " ".join((text or "").lower().split())
    if not lowered:
        return 0.0
    hint_hits = sum(1 for hint in SOCIALINTEL_TENSION_HINTS if hint in lowered)
    punctuation_score = min(0.3, lowered.count("!") * 0.05 + lowered.count("?") * 0.03)
    caps_score = min(0.18, sum(1 for ch in text if ch.isupper()) / max(1, len(text)))
    return min(1.0, (hint_hits * 0.18) + punctuation_score + caps_score)


def _socialintel_deescalation_score(text: str) -> float:
    lowered = " ".join((text or "").lower().split())
    if not lowered:
        return 0.0
    hint_hits = sum(1 for hint in SOCIALINTEL_DEESCALATION_HINTS if hint in lowered)
    return min(1.0, hint_hits * 0.22)


def _socialintel_get_channel_row(
    guild_state: dict[str, Any],
    channel: discord.abc.GuildChannel,
) -> dict[str, Any]:
    channels = guild_state.setdefault("channels", {})
    key = str(channel.id)
    row = channels.get(key)
    if not isinstance(row, dict):
        row = {
            "latest_message_id": 0,
            "earliest_message_id": 0,
            "last_message_ts": 0.0,
            "before_message_id": 0,
            "fully_scanned": False,
            "last_backfill_ts": 0.0,
            "name": getattr(channel, "name", f"channel-{channel.id}"),
            "kind": "thread" if isinstance(channel, discord.Thread) else "channel",
            "message_count": 0,
            "recent_topics": {},
            "samples": [],
            "last_open_question_ts": 0.0,
            "last_open_question_text": "",
            "last_conflict_ts": 0.0,
            "last_conflict_text": "",
            "proactive_last_ts": 0.0,
        }
        channels[key] = row
    if not isinstance(row.get("recent_topics"), dict):
        row["recent_topics"] = {}
    if not isinstance(row.get("samples"), list):
        row["samples"] = []
    row["name"] = getattr(channel, "name", row.get("name", f"channel-{channel.id}"))
    row["kind"] = "thread" if isinstance(channel, discord.Thread) else "channel"
    return row


def _socialintel_invalidate_guild_cache(guild_id: int) -> None:
    for cache_key in list(SOCIALINTEL_RESULT_CACHE.keys()):
        if cache_key and cache_key[0] == guild_id:
            SOCIALINTEL_RESULT_CACHE.pop(cache_key, None)


def refresh_socialintel_member_directory(guild: discord.Guild) -> None:
    guild_state = get_guild_socialintel_state(guild.id)
    for member in guild.members:
        if member.bot:
            continue
        row = _altfinder_get_user_row(guild_state, member.id)
        _altfinder_apply_user_snapshot(row, member)
        _altfinder_sync_presence_snapshot(row, member, increment_history=False)
    _mark_socialintel_dirty()


def record_socialintel_presence(member: discord.Member) -> None:
    if member.bot:
        return
    guild_state = get_guild_socialintel_state(member.guild.id)
    row = _altfinder_get_user_row(guild_state, member.id)
    _altfinder_apply_user_snapshot(row, member)
    _altfinder_sync_presence_snapshot(row, member, increment_history=True)
    _mark_socialintel_dirty()
    _socialintel_invalidate_guild_cache(member.guild.id)


def index_socialintel_message(message: discord.Message, *, backfill: bool = False) -> set[int]:
    if message.guild is None or message.author.bot:
        return set()
    content = message.clean_content.strip()
    if not content and not message.attachments:
        return set()
    if not content and message.attachments:
        content = "[attachment]"

    guild_state = get_guild_socialintel_state(message.guild.id)
    created_ts = message.created_at.timestamp()
    meta = guild_state.setdefault("meta", {})
    channel_row = _socialintel_get_channel_row(guild_state, message.channel)
    channel_row["latest_message_id"] = max(int(channel_row.get("latest_message_id", 0) or 0), int(message.id))
    earliest = int(channel_row.get("earliest_message_id", 0) or 0)
    channel_row["earliest_message_id"] = int(message.id) if earliest <= 0 else min(earliest, int(message.id))
    channel_row["last_message_ts"] = max(float(channel_row.get("last_message_ts", 0.0) or 0.0), created_ts)
    channel_row["message_count"] = int(channel_row.get("message_count", 0) or 0) + 1
    if backfill:
        channel_row["last_backfill_ts"] = time.time()
        meta["last_backfill_ts"] = time.time()
    else:
        meta["last_incremental_ts"] = time.time()
    meta["messages_indexed"] = int(meta.get("messages_indexed", 0) or 0) + 1
    meta["last_indexed_message_ts"] = max(float(meta.get("last_indexed_message_ts", 0.0) or 0.0), created_ts)

    row = _altfinder_get_user_row(guild_state, message.author.id)
    _altfinder_apply_user_snapshot(row, message.author)
    row["message_count"] = int(row.get("message_count", 0) or 0) + 1
    row["last_message_ts"] = max(float(row.get("last_message_ts", 0.0) or 0.0), created_ts)
    row["message_total_chars"] = int(row.get("message_total_chars", 0) or 0) + len(content)
    row["message_total_words"] = int(row.get("message_total_words", 0) or 0) + len(WORD_PATTERN.findall(content))
    row["question_count"] = int(row.get("question_count", 0) or 0) + (1 if "?" in content else 0)
    row["exclaim_count"] = int(row.get("exclaim_count", 0) or 0) + (1 if "!" in content else 0)
    row["emoji_total"] = int(row.get("emoji_total", 0) or 0) + len(EMOJI_PATTERN.findall(content))
    row["uppercase_chars_total"] = int(row.get("uppercase_chars_total", 0) or 0) + sum(1 for ch in content if ch.isupper())
    row["link_count"] = int(row.get("link_count", 0) or 0) + (1 if LINK_PATTERN.search(content) else 0)
    row["attachment_count"] = int(row.get("attachment_count", 0) or 0) + (1 if message.attachments else 0)
    row["mention_message_count"] = int(row.get("mention_message_count", 0) or 0) + (1 if message.mentions else 0)
    row["reply_message_count"] = int(row.get("reply_message_count", 0) or 0) + (1 if message.reference else 0)
    _altfinder_counter_update(row, "top_channels", message.channel.id, 1, 20)
    message_dt = message.created_at.astimezone(_safe_zoneinfo(get_guild_engagement_timezone(message.guild.id)))
    _altfinder_counter_update(row, "active_hours", message_dt.hour, 1, 24)
    _altfinder_counter_update(row, "active_weekdays", message_dt.weekday(), 1, 7)
    _altfinder_sync_presence_snapshot(row, message.author, increment_history=False)
    _aicrush_append_unique_sample(row["samples"], content, 14)
    _aicrush_append_unique_sample(channel_row["samples"], content, 10)

    tokens = _altfinder_extract_valid_tokens(content)
    row["topic_token_total"] = int(row.get("topic_token_total", 0) or 0) + len(tokens)
    for token in tokens[:18]:
        _altfinder_counter_update(row, "topics", token, 1, 42)
        _altfinder_counter_update(channel_row, "recent_topics", token, 1, 20)
    for bigram in _altfinder_extract_bigrams(tokens[:24])[:18]:
        _altfinder_counter_update(row, "bigrams", bigram, 1, 42)
    if tokens:
        _altfinder_counter_update(row, "starter_tokens", tokens[0], 1, 24)
        _altfinder_counter_update(row, "ending_tokens", tokens[-1], 1, 24)

    excerpt = _socialintel_compact_excerpt(content, 180)
    if "?" in content and len(excerpt) >= 18:
        channel_row["last_open_question_ts"] = created_ts
        channel_row["last_open_question_text"] = excerpt
    if _socialintel_tension_score(content) >= 0.2:
        channel_row["last_conflict_ts"] = created_ts
        channel_row["last_conflict_text"] = excerpt

    impacted_ids: set[int] = {message.author.id}
    mention_ids = {
        int(member.id)
        for member in message.mentions
        if not member.bot and member.id != message.author.id
    }
    for mention_id in mention_ids:
        _altfinder_counter_update(row, "mention_targets", mention_id, 1, 40)
        _socialintel_update_pair_interaction(
            guild_state,
            message.author.id,
            mention_id,
            kind="mention",
            created_ts=created_ts,
            channel_id=message.channel.id,
            hour=message_dt.hour,
            sample_text=content,
        )
        impacted_ids.add(mention_id)

    reply_target_id = _aicrush_resolve_reply_target_id(message)
    if reply_target_id is not None and reply_target_id != message.author.id:
        _altfinder_counter_update(row, "reply_targets", reply_target_id, 1, 40)
        _socialintel_update_pair_interaction(
            guild_state,
            message.author.id,
            reply_target_id,
            kind="reply",
            created_ts=created_ts,
            channel_id=message.channel.id,
            hour=message_dt.hour,
            sample_text=content,
        )
        impacted_ids.add(reply_target_id)

    recent_others = _socialintel_track_recent_channel_author(
        message.guild.id,
        message.channel.id,
        message.author.id,
        created_ts,
    )
    for other_id in recent_others[:12]:
        _altfinder_counter_update(row, "copresence_targets", other_id, 1, 45)
        _socialintel_update_pair_interaction(
            guild_state,
            message.author.id,
            other_id,
            kind="copresence",
            created_ts=created_ts,
            channel_id=message.channel.id,
            hour=message_dt.hour,
            sample_text=content,
        )
        impacted_ids.add(other_id)

    _aicrush_remember_message_author(int(message.id), int(message.author.id), created_ts)
    _mark_socialintel_dirty()
    _socialintel_invalidate_guild_cache(message.guild.id)
    return impacted_ids


def get_readable_social_channels(guild: discord.Guild) -> list[discord.abc.MessageableChannel]:
    channels: list[discord.abc.MessageableChannel] = list(get_readable_text_channels(guild))
    me = guild.me
    if me is None:
        return channels
    for thread in guild.threads:
        try:
            perms = thread.permissions_for(me)
        except Exception:
            continue
        if perms.view_channel and perms.read_message_history:
            channels.append(thread)
    return channels


async def run_socialintel_backfill(
    guild: discord.Guild,
    *,
    message_budget: int | None = None,
    time_budget_seconds: float | None = None,
) -> dict[str, Any]:
    guild_state = get_guild_socialintel_state(guild.id)
    channels = get_readable_social_channels(guild)
    channel_rows = guild_state.setdefault("channels", {})
    for channel in channels:
        _socialintel_get_channel_row(guild_state, channel)

    remaining_budget = max(200, int(message_budget or SOCIALINTEL_BACKFILL_MESSAGE_BUDGET))
    deadline = time.monotonic() + float(time_budget_seconds or SOCIALINTEL_BACKFILL_TIME_BUDGET_SECONDS)
    fetched_messages: list[discord.Message] = []
    processed_channels = 0
    passes = 0

    while remaining_budget > 0 and time.monotonic() < deadline:
        passes += 1
        pass_scanned = 0
        channel_priority = sorted(
            channels,
            key=lambda channel: (
                1 if bool(channel_rows.get(str(channel.id), {}).get("fully_scanned")) else 0,
                float(channel_rows.get(str(channel.id), {}).get("last_backfill_ts", 0.0) or 0.0),
            ),
        )
        for channel in channel_priority:
            if remaining_budget <= 0 or time.monotonic() >= deadline:
                break
            row = channel_rows.setdefault(str(channel.id), {})
            if bool(row.get("fully_scanned")):
                continue
            per_channel_limit = min(max(50, AICRUSH_SCAN_PER_CHANNEL), remaining_budget)
            history_kwargs: dict[str, Any] = {"limit": per_channel_limit}
            before_message_id = int(row.get("before_message_id", 0) or 0)
            if before_message_id <= 0:
                before_message_id = int(row.get("earliest_message_id", 0) or 0)
            if before_message_id > 0:
                history_kwargs["before"] = discord.Object(id=before_message_id)
            batch: list[discord.Message] = []
            try:
                async for msg in channel.history(**history_kwargs):
                    if not msg.author.bot:
                        batch.append(msg)
            except (discord.Forbidden, discord.HTTPException):
                continue
            processed_channels += 1
            row["last_backfill_ts"] = time.time()
            if not batch:
                row["fully_scanned"] = True
                continue
            oldest_id = min(int(msg.id) for msg in batch)
            row["before_message_id"] = oldest_id
            earliest = int(row.get("earliest_message_id", 0) or 0)
            row["earliest_message_id"] = oldest_id if earliest <= 0 else min(earliest, oldest_id)
            if len(batch) < per_channel_limit:
                row["fully_scanned"] = True
            fetched_messages.extend(batch)
            remaining_budget -= len(batch)
            pass_scanned += len(batch)
            if (
                AICRUSH_SCAN_PAUSE_EVERY > 0
                and AICRUSH_SCAN_PAUSE_SECONDS > 0
                and pass_scanned % AICRUSH_SCAN_PAUSE_EVERY == 0
            ):
                await asyncio.sleep(AICRUSH_SCAN_PAUSE_SECONDS)
        if pass_scanned <= 0:
            break

    fetched_messages.sort(key=lambda msg: (msg.created_at.timestamp(), int(msg.id)))
    for msg in fetched_messages:
        index_socialintel_message(msg, backfill=True)

    channels_total = len(channels)
    channels_fully_scanned = sum(
        1
        for row in channel_rows.values()
        if isinstance(row, dict) and bool(row.get("fully_scanned"))
    )
    meta = guild_state.setdefault("meta", {})
    meta["last_backfill_ts"] = time.time()
    _mark_socialintel_dirty()
    return {
        "scanned_messages": len(fetched_messages),
        "channels_considered": channels_total,
        "channels_touched": processed_channels,
        "channels_fully_scanned": channels_fully_scanned,
        "messages_indexed": int(meta.get("messages_indexed", 0) or 0),
        "passes": passes,
    }


def _socialintel_user_metrics(row: dict[str, Any]) -> dict[str, Any]:
    return _altfinder_user_metrics(row)


@dataclass
class SocialIntelContext:
    target_row: dict[str, Any]
    target_metrics: dict[str, Any]
    target_message_count: int
    scan_coverage: dict[str, Any]
    candidate_rows: dict[int, dict[str, Any]]
    current_member_ids: set[int]


def collect_socialintel_context(guild: discord.Guild, target_member: discord.Member) -> SocialIntelContext:
    refresh_socialintel_member_directory(guild)
    guild_state = get_guild_socialintel_state(guild.id)
    users = guild_state.get("users", {}) if isinstance(guild_state.get("users"), dict) else {}
    target_row = _altfinder_get_user_row(guild_state, target_member.id)
    target_metrics = _socialintel_user_metrics(target_row)
    current_member_ids = {member.id for member in guild.members if not member.bot}
    candidate_rows: dict[int, dict[str, Any]] = {}
    for user_key, row in users.items():
        if not isinstance(row, dict):
            continue
        try:
            user_id = int(user_key)
        except (TypeError, ValueError):
            continue
        if user_id == target_member.id or user_id not in current_member_ids:
            continue
        candidate_rows[user_id] = row
    channels = guild_state.get("channels", {}) if isinstance(guild_state.get("channels"), dict) else {}
    meta = guild_state.get("meta", {}) if isinstance(guild_state.get("meta"), dict) else {}
    scan_coverage = {
        "channels_total": len(channels),
        "channels_fully_scanned": sum(
            1
            for row in channels.values()
            if isinstance(row, dict) and bool(row.get("fully_scanned"))
        ),
        "messages_indexed": int(meta.get("messages_indexed", 0) or 0),
        "last_backfill_ts": float(meta.get("last_backfill_ts", 0.0) or 0.0),
    }
    return SocialIntelContext(
        target_row=target_row,
        target_metrics=target_metrics,
        target_message_count=int(target_row.get("message_count", 0) or 0),
        scan_coverage=scan_coverage,
        candidate_rows=candidate_rows,
        current_member_ids=current_member_ids,
    )


def _socialintel_pair_stats(
    guild_state: dict[str, Any],
    left_user_id: int,
    right_user_id: int,
) -> dict[str, Any]:
    pair_row = _socialintel_get_pair_row(guild_state, left_user_id, right_user_id)
    reply_counts = pair_row.get("reply_counts", {}) if isinstance(pair_row.get("reply_counts"), dict) else {}
    mention_counts = pair_row.get("mention_counts", {}) if isinstance(pair_row.get("mention_counts"), dict) else {}
    return {
        "pair_row": pair_row,
        "reply_forward": int(reply_counts.get(f"{left_user_id}->{right_user_id}", 0) or 0),
        "reply_back": int(reply_counts.get(f"{right_user_id}->{left_user_id}", 0) or 0),
        "mention_forward": int(mention_counts.get(f"{left_user_id}->{right_user_id}", 0) or 0),
        "mention_back": int(mention_counts.get(f"{right_user_id}->{left_user_id}", 0) or 0),
        "copresence_count": int(pair_row.get("copresence_count", 0) or 0),
        "shared_channels": pair_row.get("shared_channels", {}) if isinstance(pair_row.get("shared_channels"), dict) else {},
        "shared_hours": pair_row.get("shared_hours", {}) if isinstance(pair_row.get("shared_hours"), dict) else {},
        "samples": pair_row.get("samples", []) if isinstance(pair_row.get("samples"), list) else [],
        "touch_count": int(pair_row.get("touch_count", 0) or 0),
    }


def _socialintel_confidence_band(score: float) -> str:
    if score >= 0.78:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def _socialintel_build_duo_row(
    guild: discord.Guild,
    target_member: discord.Member,
    candidate_id: int,
    candidate_row: dict[str, Any],
    context: SocialIntelContext,
) -> dict[str, Any] | None:
    candidate_member = guild.get_member(candidate_id)
    if candidate_member is None or candidate_member.bot:
        return None
    target_metrics = context.target_metrics
    candidate_metrics = _socialintel_user_metrics(candidate_row)
    candidate_message_count = int(candidate_metrics.get("message_count", 0) or 0)
    if context.target_message_count < 8 or candidate_message_count < 8:
        return None

    style_similarity = min(
        1.0,
        (_altfinder_scalar_similarity(float(target_metrics["avg_len"]), float(candidate_metrics["avg_len"]), 80.0) * 0.2)
        + (_altfinder_scalar_similarity(float(target_metrics["avg_words"]), float(candidate_metrics["avg_words"]), 18.0) * 0.12)
        + (_altfinder_scalar_similarity(float(target_metrics["question_ratio"]), float(candidate_metrics["question_ratio"]), 0.45) * 0.12)
        + (_altfinder_scalar_similarity(float(target_metrics["exclaim_ratio"]), float(candidate_metrics["exclaim_ratio"]), 0.45) * 0.1)
        + (_altfinder_scalar_similarity(float(target_metrics["emoji_per_msg"]), float(candidate_metrics["emoji_per_msg"]), 2.0) * 0.08)
        + (_altfinder_scalar_similarity(float(target_metrics["vocab_diversity"]), float(candidate_metrics["vocab_diversity"]), 0.45) * 0.14)
        + (_altfinder_counter_overlap(target_metrics["bigrams"], candidate_metrics["bigrams"]) * 0.16)
        + (_altfinder_counter_overlap(target_metrics["starter_tokens"], candidate_metrics["starter_tokens"]) * 0.08)
    )
    schedule_overlap = min(
        1.0,
        (_altfinder_counter_overlap(target_metrics["active_hours"], candidate_metrics["active_hours"]) * 0.7)
        + (_altfinder_counter_overlap(target_metrics["active_weekdays"], candidate_metrics["active_weekdays"]) * 0.3)
    )
    presence_overlap = min(
        1.0,
        (_altfinder_counter_overlap(target_metrics["presence_hours"], candidate_metrics["presence_hours"]) * 0.55)
        + (_altfinder_counter_overlap(target_metrics["presence_weekdays"], candidate_metrics["presence_weekdays"]) * 0.2)
        + (_altfinder_counter_overlap(target_metrics["status_counts"], candidate_metrics["status_counts"]) * 0.15)
        + (_altfinder_counter_overlap(target_metrics["status_transitions"], candidate_metrics["status_transitions"]) * 0.1)
    )
    channel_overlap = _altfinder_counter_overlap(target_metrics["top_channels"], candidate_metrics["top_channels"])
    topic_overlap = min(
        1.0,
        (_altfinder_counter_overlap(target_metrics["topics"], candidate_metrics["topics"]) * 0.72)
        + (_altfinder_counter_overlap(target_metrics["bigrams"], candidate_metrics["bigrams"]) * 0.28)
    )
    question_reply_fit = _altfinder_scalar_similarity(
        float(target_metrics["question_ratio"]),
        float(candidate_metrics["reply_rate"]),
        0.55,
    )
    pacing_similarity = min(
        1.0,
        (_altfinder_scalar_similarity(float(target_metrics["avg_len"]), float(candidate_metrics["avg_len"]), 65.0) * 0.45)
        + (_altfinder_scalar_similarity(float(target_metrics["reply_rate"]), float(candidate_metrics["reply_rate"]), 0.45) * 0.2)
        + (_altfinder_scalar_similarity(float(target_metrics["mention_rate"]), float(candidate_metrics["mention_rate"]), 0.45) * 0.1)
        + (question_reply_fit * 0.25)
    )
    interaction_overlap = min(
        1.0,
        (_altfinder_counter_overlap(target_metrics["reply_targets"], candidate_metrics["reply_targets"]) * 0.4)
        + (_altfinder_counter_overlap(target_metrics["mention_targets"], candidate_metrics["mention_targets"]) * 0.3)
        + (_altfinder_counter_overlap(target_metrics["copresence_targets"], candidate_metrics["copresence_targets"]) * 0.3)
    )
    pair_stats = _socialintel_pair_stats(get_guild_socialintel_state(guild.id), target_member.id, candidate_id)
    direct_pair_score = min(
        1.0,
        ((pair_stats["reply_forward"] + pair_stats["reply_back"]) * 0.12)
        + ((pair_stats["mention_forward"] + pair_stats["mention_back"]) * 0.08)
        + (pair_stats["copresence_count"] * 0.025)
    )
    heuristic_score = (
        (style_similarity * 1.35)
        + (schedule_overlap * 1.05)
        + (presence_overlap * 0.7)
        + (channel_overlap * 1.15)
        + (topic_overlap * 1.25)
        + (pacing_similarity * 0.95)
        + (interaction_overlap * 1.2)
        + (direct_pair_score * 1.05)
    )
    if heuristic_score < 1.2 and direct_pair_score < 0.28 and topic_overlap < 0.2:
        return None

    common_channel_ids = [
        int(channel_id)
        for channel_id, _ in _altfinder_counter_common(
            target_metrics["top_channels"],
            candidate_metrics["top_channels"],
            4,
        )
        if str(channel_id).isdigit()
    ]
    common_hours = [
        int(hour)
        for hour, _ in _altfinder_counter_common(
            target_metrics["active_hours"],
            candidate_metrics["active_hours"],
            4,
        )
        if str(hour).isdigit()
    ]
    return {
        "candidate_id": candidate_id,
        "member": candidate_member,
        "display_label": candidate_member.mention,
        "plain_label": candidate_member.display_name,
        "message_count": candidate_message_count,
        "style_similarity": round(style_similarity, 4),
        "schedule_overlap": round(schedule_overlap, 4),
        "presence_overlap": round(presence_overlap, 4),
        "channel_overlap": round(channel_overlap, 4),
        "topic_overlap": round(topic_overlap, 4),
        "pacing_similarity": round(pacing_similarity, 4),
        "interaction_overlap": round(interaction_overlap, 4),
        "direct_pair_score": round(direct_pair_score, 4),
        "heuristic_score": round(heuristic_score, 4),
        "common_channel_ids": common_channel_ids,
        "common_hours": common_hours,
        "pair_stats": pair_stats,
        "target_texture": _altfinder_sample_texture(target_metrics["samples"], limit=2),
        "candidate_texture": _altfinder_sample_texture(candidate_metrics["samples"], limit=2),
    }


def build_socialintel_duo_candidate_pool(
    guild: discord.Guild,
    target_member: discord.Member,
    context: SocialIntelContext,
    limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate_id, candidate_row in context.candidate_rows.items():
        built = _socialintel_build_duo_row(guild, target_member, candidate_id, candidate_row, context)
        if built is not None:
            rows.append(built)
    rows.sort(
        key=lambda row: (
            float(row.get("heuristic_score", 0.0)),
            float(row.get("direct_pair_score", 0.0)),
            float(row.get("interaction_overlap", 0.0)),
            float(row.get("topic_overlap", 0.0)),
        ),
        reverse=True,
    )
    return rows[: max(limit, SOCIALINTEL_MAX_RESULTS + 3)]


def annotate_socialintel_duo_confidences(
    candidates: list[dict[str, Any]],
    target_message_count: int,
) -> None:
    if not candidates:
        return
    top_score = max(float(candidates[0].get("heuristic_score", 0.0)), 0.01)
    for row in candidates:
        evidence_density = min(
            1.0,
            (float(row.get("style_similarity", 0.0)) * 0.16)
            + (float(row.get("schedule_overlap", 0.0)) * 0.16)
            + (float(row.get("channel_overlap", 0.0)) * 0.14)
            + (float(row.get("topic_overlap", 0.0)) * 0.18)
            + (float(row.get("interaction_overlap", 0.0)) * 0.18)
            + (float(row.get("direct_pair_score", 0.0)) * 0.18)
        )
        confidence = min(
            0.96,
            (min(1.0, float(row.get("heuristic_score", 0.0)) / top_score) * 0.28)
            + (min(1.0, float(row.get("heuristic_score", 0.0)) / 7.0) * 0.34)
            + (evidence_density * 0.38)
        )
        if target_message_count < 18 or int(row.get("message_count", 0) or 0) < 18:
            confidence = min(confidence, 0.66)
        if target_message_count < 10 or int(row.get("message_count", 0) or 0) < 10:
            confidence = min(confidence, 0.45)
        if (
            float(row.get("direct_pair_score", 0.0)) < 0.18
            and float(row.get("interaction_overlap", 0.0)) < 0.2
            and float(row.get("topic_overlap", 0.0)) < 0.22
        ):
            confidence = min(confidence, 0.54)
        row["confidence"] = round(max(0.06, confidence), 4)
        row["confidence_band"] = _socialintel_confidence_band(confidence)


def _socialintel_rank_schema(name: str) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "schema": {
                "type": "object",
                "properties": {
                    "ranked_ids": {"type": "array", "items": {"type": "integer"}},
                    "summary": {"type": "string"},
                },
                "required": ["ranked_ids", "summary"],
                "additionalProperties": False,
            },
        },
    }


async def rerank_socialintel_duo_candidates_with_ai(
    target_member: discord.Member,
    *,
    candidates: list[dict[str, Any]],
) -> list[int]:
    shortlist = candidates[:7]
    if len(shortlist) < 2:
        return []
    lines: list[str] = []
    for row in shortlist:
        pair_stats = row.get("pair_stats", {}) if isinstance(row.get("pair_stats"), dict) else {}
        lines.append(
            f"- id={row['candidate_id']} label={row['plain_label']} "
            f"score={float(row.get('heuristic_score', 0.0)):.2f} "
            f"style={float(row.get('style_similarity', 0.0)):.2f} "
            f"schedule={float(row.get('schedule_overlap', 0.0)):.2f} "
            f"presence={float(row.get('presence_overlap', 0.0)):.2f} "
            f"channels={float(row.get('channel_overlap', 0.0)):.2f} "
            f"topics={float(row.get('topic_overlap', 0.0)):.2f} "
            f"pacing={float(row.get('pacing_similarity', 0.0)):.2f} "
            f"interactions={float(row.get('interaction_overlap', 0.0)):.2f} "
            f"direct_pair={float(row.get('direct_pair_score', 0.0)):.2f} "
            f"mutual_replies={int(pair_stats.get('reply_forward', 0) or 0) + int(pair_stats.get('reply_back', 0) or 0)}"
        )
    messages = [
        {
            "role": "system",
            "content": (
                "You rank Discord duo compatibility for friendship, teamwork, or debate chemistry. "
                "Use supplied evidence only. Shared channels alone are weak evidence. Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": "Rank these candidates for strongest communication compatibility.\n"
            f"Target: {target_member.display_name}\n"
            + "\n".join(lines),
        },
    ]
    try:
        if GROQ_API_KEY:
            raw = await request_groq_completion(
                messages,
                max_tokens=220,
                temperature=0.1,
                model_override=SOCIALINTEL_RANK_MODEL or None,
                fallback_models=SOCIALINTEL_FALLBACK_MODELS,
                response_format=_socialintel_rank_schema("socialintel_duo_rank"),
                include_fallback_notice=False,
                feature="socialintel_duo_rank",
            )
        else:
            raw = await request_ai_completion(
                messages,
                max_tokens=220,
                temperature=0.1,
                policy_key="socialintel_duo_rank",
                model_override=(SOCIALINTEL_RANK_MODEL or None) if AI_PROVIDER == "groq" else None,
                fallback_models=SOCIALINTEL_FALLBACK_MODELS if AI_PROVIDER == "groq" else None,
                response_format=_socialintel_rank_schema("socialintel_duo_rank") if AI_PROVIDER == "groq" else None,
                include_fallback_notice=False,
            )
        payload = _extract_first_json_object(raw)
        if not isinstance(payload, dict):
            return []
        ranked_ids: list[int] = []
        allowed = {int(row["candidate_id"]) for row in shortlist}
        raw_ids = payload.get("ranked_ids", [])
        if isinstance(raw_ids, list):
            for item in raw_ids:
                try:
                    candidate_id = int(item)
                except (TypeError, ValueError):
                    continue
                if candidate_id in allowed and candidate_id not in ranked_ids:
                    ranked_ids.append(candidate_id)
        return ranked_ids
    except Exception:
        return []


def _socialintel_apply_rank_order(
    candidates: list[dict[str, Any]],
    ranked_ids: list[int],
) -> list[dict[str, Any]]:
    if not ranked_ids:
        return list(candidates)
    mapped = {int(row["candidate_id"]): row for row in candidates}
    ordered: list[dict[str, Any]] = []
    seen: set[int] = set()
    for candidate_id in ranked_ids:
        row = mapped.get(int(candidate_id))
        if row is None:
            continue
        ordered.append(row)
        seen.add(int(candidate_id))
    for row in candidates:
        if int(row["candidate_id"]) not in seen:
            ordered.append(row)
    return ordered


async def collect_messageable_window(
    channel: discord.abc.MessageableChannel,
    *,
    limit: int = 180,
    after: datetime | None = None,
) -> list[WindowMessage]:
    entries: list[WindowMessage] = []
    try:
        async for msg in channel.history(limit=limit, after=after, oldest_first=True):
            entry = _build_window_entry(msg, include_attachment_marker=True)
            if entry is not None:
                entries.append(entry)
    except (discord.Forbidden, discord.HTTPException):
        return []
    return entries


def _socialintel_metrics_from_entries(
    entries: list[WindowMessage],
    user_id: int,
) -> tuple[dict[str, Any], int]:
    temp_state: dict[str, Any] = {"users": {}}
    row = _altfinder_get_user_row(temp_state, user_id)
    id_to_author = {entry.message_id: entry.author_id for entry in entries}
    for entry in entries:
        if entry.author_id != user_id:
            continue
        content = entry.content
        row["message_count"] = int(row.get("message_count", 0) or 0) + 1
        row["message_total_chars"] = int(row.get("message_total_chars", 0) or 0) + len(content)
        row["message_total_words"] = int(row.get("message_total_words", 0) or 0) + len(WORD_PATTERN.findall(content))
        row["question_count"] = int(row.get("question_count", 0) or 0) + (1 if "?" in content else 0)
        row["exclaim_count"] = int(row.get("exclaim_count", 0) or 0) + (1 if "!" in content else 0)
        row["emoji_total"] = int(row.get("emoji_total", 0) or 0) + len(EMOJI_PATTERN.findall(content))
        row["uppercase_chars_total"] = int(row.get("uppercase_chars_total", 0) or 0) + sum(1 for ch in content if ch.isupper())
        row["link_count"] = int(row.get("link_count", 0) or 0) + (1 if LINK_PATTERN.search(content) else 0)
        row["attachment_count"] = int(row.get("attachment_count", 0) or 0) + (1 if entry.has_attachments else 0)
        row["mention_message_count"] = int(row.get("mention_message_count", 0) or 0) + (1 if entry.mention_ids else 0)
        row["reply_message_count"] = int(row.get("reply_message_count", 0) or 0) + (1 if entry.reference_message_id else 0)
        _altfinder_counter_update(row, "top_channels", entry.channel_id, 1, 16)
        dt = datetime.fromtimestamp(entry.created_at_ts, tz=timezone.utc).astimezone(_safe_zoneinfo("UTC"))
        _altfinder_counter_update(row, "active_hours", dt.hour, 1, 24)
        _altfinder_counter_update(row, "active_weekdays", dt.weekday(), 1, 7)
        tokens = _altfinder_extract_valid_tokens(content)
        row["topic_token_total"] = int(row.get("topic_token_total", 0) or 0) + len(tokens)
        for token in tokens[:18]:
            _altfinder_counter_update(row, "topics", token, 1, 40)
        for bigram in _altfinder_extract_bigrams(tokens[:24])[:18]:
            _altfinder_counter_update(row, "bigrams", bigram, 1, 40)
        if tokens:
            _altfinder_counter_update(row, "starter_tokens", tokens[0], 1, 24)
            _altfinder_counter_update(row, "ending_tokens", tokens[-1], 1, 24)
        _aicrush_append_unique_sample(row["samples"], content, 10)
        for mention_id in entry.mention_ids[:6]:
            _altfinder_counter_update(row, "mention_targets", mention_id, 1, 32)
        if entry.reference_message_id and entry.reference_message_id in id_to_author:
            reply_target_id = id_to_author[entry.reference_message_id]
            if reply_target_id != user_id:
                _altfinder_counter_update(row, "reply_targets", reply_target_id, 1, 32)
    return _socialintel_user_metrics(row), int(row.get("message_count", 0) or 0)


def resolve_channel_or_thread(
    guild: discord.Guild,
    raw: str | None,
    *,
    default_channel: discord.abc.GuildChannel | None = None,
) -> discord.TextChannel | discord.Thread | None:
    if not raw:
        if isinstance(default_channel, (discord.TextChannel, discord.Thread)):
            return default_channel
        return None
    cleaned = raw.strip()
    mention_match = re.search(r"<#(\d+)>", cleaned)
    channel_id = 0
    if mention_match:
        channel_id = int(mention_match.group(1))
    elif cleaned.isdigit():
        channel_id = int(cleaned)
    if channel_id > 0:
        getter = getattr(guild, "get_channel_or_thread", None)
        if callable(getter):
            resolved = getter(channel_id)
            if isinstance(resolved, (discord.TextChannel, discord.Thread)):
                return resolved
        resolved = guild.get_channel(channel_id)
        if isinstance(resolved, (discord.TextChannel, discord.Thread)):
            return resolved
        bot_resolved = bot.get_channel(channel_id)
        if isinstance(bot_resolved, (discord.TextChannel, discord.Thread)):
            return bot_resolved
    lowered = cleaned.lower().lstrip("#")
    for channel in [*guild.text_channels, *guild.threads]:
        if lowered == channel.name.lower():
            return channel
    return None


async def resolve_message_from_context(
    ctx: commands.Context,
    message_ref: str | None,
) -> discord.Message | None:
    reference = getattr(getattr(ctx, "message", None), "reference", None)
    if reference and reference.message_id:
        resolved = getattr(reference, "resolved", None)
        if isinstance(resolved, discord.Message):
            return resolved
        if isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
            try:
                return await ctx.channel.fetch_message(reference.message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
    if not message_ref:
        return None
    match = DISCORD_MESSAGE_LINK_RE.search(message_ref.strip())
    if not match or ctx.guild is None:
        return None
    guild_id, channel_id, message_id = match.groups()
    if str(ctx.guild.id) != str(guild_id):
        return None
    channel = resolve_channel_or_thread(ctx.guild, channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return None
    try:
        return await channel.fetch_message(int(message_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


def _translation_cleanup_spacing(text: str) -> str:
    compact = " ".join((text or "").split()).strip()
    if not compact:
        return ""
    compact = re.sub(r"\s+([?.!,])", r"\1", compact)
    compact = re.sub(r"\bhinglish\b", "Hinglish", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\bi am\b", "I am", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\bi\b", "I", compact)
    if compact[:1].islower():
        compact = compact[:1].upper() + compact[1:]
    return compact


def _translation_strip_prefixes(text: str) -> str:
    compact = (text or "").strip()
    if not compact:
        return ""
    compact = re.sub(r"^\s*(translation|translated text|english)\s*:\s*", "", compact, flags=re.IGNORECASE)
    compact = compact.strip("`\"' ")
    lines = [line.strip("`\"' ") for line in compact.splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]
    # Prefer the first concise line when the model adds commentary despite instructions.
    for line in lines:
        if len(line) <= 220:
            return line
    return lines[0]


def _translation_rewrite_patterns(normalized_text: str) -> str:
    compact = " ".join((normalized_text or "").split()).strip()
    if not compact:
        return compact
    compact = re.sub(
        r"^naam change kiya firse$",
        "changed the name again",
        compact,
        flags=re.IGNORECASE,
    )
    teach_match = re.match(
        r"^(?P<object>.+?)\s+sikhao\s+(?P<target>use|usse|usko)$",
        compact,
        flags=re.IGNORECASE,
    )
    if teach_match:
        obj = teach_match.group("object").strip()
        if obj:
            return f"teach them {obj}"
    return compact


def _translate_text_local(text: str) -> tuple[str, str, str]:
    normalized = (text or "").strip()
    if not normalized:
        return "", "unknown", "No text to translate."

    working = _translation_rewrite_patterns(normalize_aicrush_text(normalized))
    replaced_hits = 0
    for source, target in TRANSLATION_LOCAL_PHRASES:
        if source in working:
            count_before = working.count(source)
            working = working.replace(source, target)
            replaced_hits += count_before

    tokens = WORD_PATTERN.findall(working)
    translated_tokens: list[str] = []
    for token in tokens:
        mapped = TRANSLATION_LOCAL_WORDS.get(token.lower())
        if mapped:
            translated_tokens.extend(mapped.split())
            replaced_hits += 1
        else:
            translated_tokens.append(token)

    if not translated_tokens:
        return normalized, "unknown", "No local translation evidence."

    translated = _translation_cleanup_spacing(" ".join(translated_tokens))
    normalized_source = normalize_aicrush_text(normalized)
    if translated.lower() == normalized_source and replaced_hits == 0:
        return normalized, "likely English", "No strong non-English markers found."
    if replaced_hits <= 1:
        return translated, "mixed/uncertain", "Light local glossary match only."
    return translated, "Hinglish/romanized Hindi", "Local glossary fallback from visible wording."


async def translate_text_to_english(text: str) -> dict[str, str]:
    local_translation, local_source, local_note = _translate_text_local(text)
    local_payload = {
        "source_language": local_source,
        "translated_text": local_translation or text.strip(),
        "confidence_note": local_note,
    }
    if not is_ai_configured():
        return local_payload

    prompt = (
        "Translate the user's message into natural English.\n"
        "Rules:\n"
        "- Input may be Hindi, Hinglish, romanized Hindi, or mixed English.\n"
        "- Keep the meaning exact.\n"
        "- Expand slang naturally when possible.\n"
        "- Return only the translated English text.\n"
        "- Do not add labels, quotes, notes, or explanations.\n\n"
        f"Input: {text[:1200]}"
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a precise translation assistant for Discord chat. "
                "You translate mixed-language text into English. "
                "Return only the translated English text."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    try:
        raw = await request_ai_completion(
            messages,
            max_tokens=140,
            temperature=0.05,
            policy_key="translate",
            include_fallback_notice=False,
        )
        ai_text = _translation_cleanup_spacing(_translation_strip_prefixes(raw))
        normalized_input = normalize_aicrush_text(text)
        normalized_local = normalize_aicrush_text(local_payload["translated_text"])
        normalized_ai = normalize_aicrush_text(ai_text)
        if not ai_text:
            return local_payload
        # If the model echoes the input back unchanged while local fallback found a translation,
        # prefer the local translation instead of pretending nothing changed.
        if normalized_ai == normalized_input and normalized_local != normalized_input:
            return local_payload
        if len(ai_text) > max(220, len(text) * 4):
            return local_payload
        return {
            "source_language": "translated via ai",
            "translated_text": ai_text[:900],
            "confidence_note": "",
        }
    except Exception:
        return local_payload


def is_message_addressed_to_bot(message: discord.Message) -> bool:
    if bot.user is None:
        return False
    raw = (message.content or "").strip()
    if not raw:
        return False
    if re.match(rf"^<@!?{bot.user.id}>(?:\s*[:,\-]?\s*)?.*$", raw, flags=re.IGNORECASE):
        return True

    lowered = raw.lower()
    names: set[str] = {"bell", bot.user.name.lower()}
    if isinstance(message.guild, discord.Guild):
        me = message.guild.me
        if me and me.display_name:
            names.add(me.display_name.lower())
    for name in sorted(names, key=len, reverse=True):
        if re.match(rf"^{re.escape(name)}\b(?:\s*[:,\-]?\s*)?.*$", lowered):
            return True
    return False


async def get_referenced_message(message: discord.Message) -> discord.Message | None:
    reference = getattr(message, "reference", None)
    if reference is None or reference.message_id is None:
        return None
    resolved = getattr(reference, "resolved", None)
    if isinstance(resolved, discord.Message):
        return resolved
    if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
        return None
    try:
        return await message.channel.fetch_message(reference.message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


def is_reply_translation_request(text: str) -> bool:
    normalized = " ".join((text or "").lower().split()).strip(" .!?")
    if not normalized:
        return True
    if normalized in {
        "translate",
        "translation",
        "meaning",
        "meaning pls",
        "meaning please",
        "english",
        "in english",
        "to english",
        "what does this mean",
        "what's the meaning",
        "what is the meaning",
        "what does this say",
    }:
        return True
    return (
        re.search(r"\btranslate\b", normalized) is not None
        or "in english" in normalized
        or "to english" in normalized
        or re.search(r"\bmeaning\b", normalized) is not None
    )


async def maybe_handle_reply_translation_request(message: discord.Message, addressed_text: str | None) -> bool:
    if not is_message_addressed_to_bot(message):
        return False
    if addressed_text and not is_reply_translation_request(addressed_text):
        return False
    referenced = await get_referenced_message(message)
    if referenced is None or referenced.author.bot:
        return False
    source_text = (referenced.clean_content or "").strip()
    if not source_text:
        await message.channel.send("The replied message has no text content to translate.")
        return True
    if not await enforce_fun_rate_limit_message(message):
        return True
    async with message.channel.typing():
        payload = await translate_text_to_english(source_text)
    translated_text = str(payload.get("translated_text", "") or "").strip() or source_text
    await send_chunked(message.channel, translated_text)
    return True


def _socialintel_author_label(guild: discord.Guild, user_id: int) -> str:
    member = guild.get_member(user_id)
    if member is not None:
        return member.display_name
    guild_state = get_guild_socialintel_state(guild.id)
    users = guild_state.get("users", {}) if isinstance(guild_state.get("users"), dict) else {}
    row = users.get(str(user_id))
    if isinstance(row, dict):
        label = str(row.get("display_name", "") or row.get("username", "") or "").strip()
        if label:
            return label
    return f"user {user_id}"


def _socialintel_recent_topic_words(entries: list[WindowMessage], limit: int = 5) -> list[str]:
    words: list[str] = []
    for entry in entries:
        for token in _altfinder_extract_valid_tokens(entry.content):
            words.append(token)
    return [token for token, _ in Counter(words).most_common(limit)]


def _socialintel_local_replycraft(
    source_message: discord.Message,
    style_text: str,
) -> dict[str, str]:
    topic_tokens = _altfinder_extract_valid_tokens(source_message.clean_content)
    topic = topic_tokens[0] if topic_tokens else "that"
    opener = "Thanks for the context"
    if "?" in source_message.clean_content:
        opener = "Fair question"
    elif "!" in source_message.clean_content:
        opener = "You make a strong point"
    return {
        "safe_tone": "measured",
        "safe_reply": f"{opener}. I think the key part is {topic}, and I’d answer it a bit more carefully.",
        "playful_tone": "light banter",
        "playful_reply": f"{opener} - low-key this whole thing hinges on {topic}, and that is where the real chaos starts.",
        "bold_tone": "direct",
        "bold_reply": f"Hot take: {topic} is the actual point here, and I’d rather say that directly than dance around it.",
        "confidence_note": f"Built from visible channel context plus your style fingerprint ({style_text}).",
    }


def _socialintel_scan_coverage(guild_id: int) -> dict[str, Any]:
    guild_state = get_guild_socialintel_state(guild_id)
    channels = guild_state.get("channels", {}) if isinstance(guild_state.get("channels"), dict) else {}
    meta = guild_state.get("meta", {}) if isinstance(guild_state.get("meta"), dict) else {}
    channels_total = len(channels)
    channels_fully_scanned = sum(
        1
        for row in channels.values()
        if isinstance(row, dict) and bool(row.get("fully_scanned"))
    )
    return {
        "channels_total": channels_total,
        "channels_fully_scanned": channels_fully_scanned,
        "messages_indexed": int(meta.get("messages_indexed", 0) or 0),
        "last_backfill_ts": float(meta.get("last_backfill_ts", 0.0) or 0.0),
        "last_incremental_ts": float(meta.get("last_incremental_ts", 0.0) or 0.0),
        "last_indexed_message_ts": float(meta.get("last_indexed_message_ts", 0.0) or 0.0),
    }


def _socialintel_needs_backfill(guild_id: int) -> bool:
    coverage = _socialintel_scan_coverage(guild_id)
    channels_total = int(coverage.get("channels_total", 0) or 0)
    channels_fully_scanned = int(coverage.get("channels_fully_scanned", 0) or 0)
    last_backfill_ts = float(coverage.get("last_backfill_ts", 0.0) or 0.0)
    if channels_total <= 0:
        return True
    if channels_fully_scanned < channels_total:
        return True
    if last_backfill_ts <= 0:
        return True
    return False


async def maybe_run_socialintel_backfill(
    guild: discord.Guild,
    *,
    force: bool = False,
    message_budget: int | None = None,
    time_budget_seconds: float | None = None,
) -> dict[str, Any]:
    coverage = _socialintel_scan_coverage(guild.id)
    if not force and not _socialintel_needs_backfill(guild.id):
        return {
            "scanned_messages": 0,
            "channels_considered": int(coverage.get("channels_total", 0) or 0),
            "channels_touched": 0,
            "channels_fully_scanned": int(coverage.get("channels_fully_scanned", 0) or 0),
            "messages_indexed": int(coverage.get("messages_indexed", 0) or 0),
            "passes": 0,
        }
    lock = SOCIALINTEL_LOCKS[(guild.id, 0)]
    async with lock:
        coverage = _socialintel_scan_coverage(guild.id)
        if not force and not _socialintel_needs_backfill(guild.id):
            return {
                "scanned_messages": 0,
                "channels_considered": int(coverage.get("channels_total", 0) or 0),
                "channels_touched": 0,
                "channels_fully_scanned": int(coverage.get("channels_fully_scanned", 0) or 0),
                "messages_indexed": int(coverage.get("messages_indexed", 0) or 0),
                "passes": 0,
            }
        return await run_socialintel_backfill(
            guild,
            message_budget=message_budget or SOCIALINTEL_COMMAND_MAX_BACKFILL_MESSAGES,
            time_budget_seconds=time_budget_seconds or SOCIALINTEL_COMMAND_MAX_BACKFILL_SECONDS,
        )


def _socialintel_duo_score_percent(heuristic_score: float) -> int:
    return max(1, min(99, int(round(min(1.0, float(heuristic_score) / 7.0) * 100))))


def _socialintel_style_text(metrics: dict[str, Any]) -> str:
    parts: list[str] = []
    avg_len = float(metrics.get("avg_len", 0.0) or 0.0)
    question_ratio = float(metrics.get("question_ratio", 0.0) or 0.0)
    exclaim_ratio = float(metrics.get("exclaim_ratio", 0.0) or 0.0)
    emoji_per_msg = float(metrics.get("emoji_per_msg", 0.0) or 0.0)
    vocab_diversity = float(metrics.get("vocab_diversity", 0.0) or 0.0)
    if avg_len >= 90:
        parts.append("long-form")
    elif avg_len <= 34:
        parts.append("short-form")
    else:
        parts.append("mid-length")
    if question_ratio >= 0.28:
        parts.append("question-heavy")
    elif exclaim_ratio >= 0.24:
        parts.append("high-energy")
    else:
        parts.append("steady")
    if emoji_per_msg >= 0.45:
        parts.append("emoji-friendly")
    if vocab_diversity >= 0.26:
        parts.append("varied vocabulary")
    return ", ".join(parts[:4]) or "light visible history"


def _socialintel_counter_current_hour_fit(counter: dict[str, Any], hour: int) -> float:
    if not isinstance(counter, dict) or not counter:
        return 0.0
    max_count = max(int(value or 0) for value in counter.values())
    if max_count <= 0:
        return 0.0
    return min(1.0, int(counter.get(str(hour), 0) or 0) / max_count)


def _socialintel_weekday_label(day_index: int) -> str:
    mapping = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if 0 <= int(day_index) < len(mapping):
        return mapping[int(day_index)]
    return str(day_index)


def _socialintel_channel_label(channel: discord.abc.GuildChannel) -> str:
    if isinstance(channel, discord.Thread):
        return f"thread:{channel.name}"
    return f"#{channel.name}"


def _socialintel_counter_labels(counter: dict[str, Any], limit: int = 3) -> list[str]:
    if not isinstance(counter, dict):
        return []
    ordered = sorted(counter.items(), key=lambda item: int(item[1] or 0), reverse=True)
    return [str(key) for key, _ in ordered[:limit]]


def _socialintel_duo_reason_bits(guild: discord.Guild, row: dict[str, Any]) -> list[str]:
    bits: list[str] = []
    if float(row.get("direct_pair_score", 0.0)) >= 0.34:
        bits.append("clear direct reply or mention chemistry")
    if float(row.get("topic_overlap", 0.0)) >= 0.34:
        bits.append("topic overlap is strong")
    if float(row.get("channel_overlap", 0.0)) >= 0.34:
        bits.append("they keep showing up in the same places")
    if float(row.get("schedule_overlap", 0.0)) >= 0.34:
        bits.append("their active hours line up well")
    if float(row.get("style_similarity", 0.0)) >= 0.42:
        bits.append("their message style is compatible")
    common_channels = row.get("common_channel_ids", [])
    if not bits and isinstance(common_channels, list) and common_channels:
        bits.append(
            "shared channels are visible, but deeper direct evidence is still limited"
        )
    return bits[:3]


def _socialintel_replycraft_schema(name: str) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "schema": {
                "type": "object",
                "properties": {
                    "safe_tone": {"type": "string"},
                    "safe_reply": {"type": "string"},
                    "playful_tone": {"type": "string"},
                    "playful_reply": {"type": "string"},
                    "bold_tone": {"type": "string"},
                    "bold_reply": {"type": "string"},
                    "confidence_note": {"type": "string"},
                },
                "required": [
                    "safe_tone",
                    "safe_reply",
                    "playful_tone",
                    "playful_reply",
                    "bold_tone",
                    "bold_reply",
                    "confidence_note",
                ],
                "additionalProperties": False,
            },
        },
    }


async def _socialintel_message_neighborhood(
    source_message: discord.Message,
    *,
    before_limit: int = 5,
    after_limit: int = 5,
) -> list[WindowMessage]:
    if not isinstance(source_message.channel, (discord.TextChannel, discord.Thread)):
        entry = _build_window_entry(source_message, include_attachment_marker=True)
        return [entry] if entry is not None else []
    before_entries: list[WindowMessage] = []
    after_entries: list[WindowMessage] = []
    try:
        async for msg in source_message.channel.history(
            limit=before_limit,
            before=discord.Object(id=source_message.id),
            oldest_first=False,
        ):
            entry = _build_window_entry(msg, include_attachment_marker=True)
            if entry is not None:
                before_entries.append(entry)
    except (discord.Forbidden, discord.HTTPException):
        before_entries = []
    try:
        async for msg in source_message.channel.history(
            limit=after_limit,
            after=discord.Object(id=source_message.id),
            oldest_first=True,
        ):
            entry = _build_window_entry(msg, include_attachment_marker=True)
            if entry is not None:
                after_entries.append(entry)
    except (discord.Forbidden, discord.HTTPException):
        after_entries = []
    center_entry = _build_window_entry(source_message, include_attachment_marker=True)
    entries = list(reversed(before_entries))
    if center_entry is not None:
        entries.append(center_entry)
    entries.extend(after_entries)
    return entries


async def _socialintel_generate_replycraft(
    source_message: discord.Message,
    *,
    requester_metrics: dict[str, Any],
    recent_entries: list[WindowMessage],
) -> dict[str, str]:
    style_text = _socialintel_style_text(requester_metrics)
    local = _socialintel_local_replycraft(source_message, style_text)
    if not is_ai_configured():
        return local
    recent_lines = [
        f"{entry.author_display_name}: {_socialintel_compact_excerpt(entry.content, 110)}"
        for entry in recent_entries[-8:]
    ]
    prompt = (
        "Draft three short Discord replies to the target message.\n"
        "Rules:\n"
        "- Use only the visible evidence below.\n"
        "- Do not invent context.\n"
        "- Do not quote long message spans.\n"
        "- Keep each reply under 180 characters.\n"
        "- Match the requester's style loosely without copying anyone verbatim.\n"
        "- Return JSON only.\n\n"
        f"Requester style: {style_text}\n"
        f"Target author: {get_user_display_name(source_message.author)}\n"
        f"Target message: {_socialintel_compact_excerpt(source_message.clean_content or '[attachment]', 180)}\n"
        "Recent visible context:\n"
        + "\n".join(recent_lines)
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You draft evidence-grounded Discord reply options. "
                "Return strict JSON only."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    try:
        raw = await request_ai_completion(
            messages,
            max_tokens=260,
            temperature=0.45,
            policy_key="replycraft",
            model_override=(SOCIALINTEL_EXPLAIN_MODEL or None) if AI_PROVIDER == "groq" else None,
            fallback_models=SOCIALINTEL_FALLBACK_MODELS if AI_PROVIDER == "groq" else None,
            response_format=_socialintel_replycraft_schema("replycraft_payload") if AI_PROVIDER == "groq" else None,
            include_fallback_notice=False,
        )
        payload = _extract_first_json_object(raw)
        if not isinstance(payload, dict):
            return local
        parsed: dict[str, str] = {}
        for key, fallback_value in local.items():
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                parsed[key] = " ".join(value.split())[:220]
            else:
                parsed[key] = fallback_value
        return parsed
    except Exception:
        return local


def _socialintel_thread_focus(channel_row: dict[str, Any]) -> tuple[str | None, str]:
    question_ts = float(channel_row.get("last_open_question_ts", 0.0) or 0.0)
    conflict_ts = float(channel_row.get("last_conflict_ts", 0.0) or 0.0)
    question_text = str(channel_row.get("last_open_question_text", "") or "").strip()
    conflict_text = str(channel_row.get("last_conflict_text", "") or "").strip()
    if conflict_ts >= question_ts and len(conflict_text) >= 18:
        return "conflict", conflict_text
    if len(question_text) >= 18:
        return "question", question_text
    return None, ""


def _socialintel_build_threadrevive_prompts(
    channel_row: dict[str, Any],
    *,
    limit: int = 3,
) -> list[str]:
    focus_kind, focus_text = _socialintel_thread_focus(channel_row)
    if not focus_text:
        return []
    topic_words = _socialintel_counter_labels(
        channel_row.get("recent_topics", {}) if isinstance(channel_row.get("recent_topics"), dict) else {},
        limit=3,
    )
    topic_text = ", ".join(topic_words) if topic_words else "the last open thread"
    if focus_kind == "conflict":
        prompts = [
            f"Quick revive: this stalled around `{focus_text}`. What has changed since then?",
            f"Reset the debate in one line: what is your strongest take on {topic_text} now?",
            f"If this moves forward today, what is the practical next step instead of repeating the same loop?",
        ]
    else:
        prompts = [
            f"Follow-up for the thread: `{focus_text}`",
            f"On {topic_text}, what is the clearest answer or example people have now?",
            f"What changed enough here that this question deserves a fresh answer today?",
        ]
    return prompts[: max(1, limit)]


def _socialintel_channel_is_sendable(
    channel: discord.TextChannel | discord.Thread,
    me: discord.Member | None,
) -> bool:
    if me is None:
        return False
    try:
        perms = channel.permissions_for(me)
    except Exception:
        return False
    if isinstance(channel, discord.Thread):
        if channel.archived:
            return False
        return bool(
            perms.view_channel
            and (
                getattr(perms, "send_messages_in_threads", False)
                or getattr(perms, "send_messages", False)
            )
        )
    return bool(perms.view_channel and perms.send_messages)


async def run_threadrevive_proactive_tick() -> None:
    if not THREADREVIVE_PROACTIVE_ENABLED:
        return
    now_ts = time.time()
    min_idle_seconds = max(60, THREADREVIVE_PROACTIVE_MIN_IDLE_MINUTES * 60)
    for guild in bot.guilds:
        guild_state = get_guild_socialintel_state(guild.id)
        channels = guild_state.get("channels", {})
        if not isinstance(channels, dict) or not channels:
            continue
        me = guild.me
        ranked_rows = sorted(
            (
                (channel_id, row)
                for channel_id, row in channels.items()
                if isinstance(row, dict)
            ),
            key=lambda item: max(
                float(item[1].get("last_conflict_ts", 0.0) or 0.0),
                float(item[1].get("last_open_question_ts", 0.0) or 0.0),
            ),
            reverse=True,
        )
        for channel_id, row in ranked_rows:
            if int(row.get("message_count", 0) or 0) < 8:
                continue
            if now_ts - float(row.get("last_message_ts", 0.0) or 0.0) < min_idle_seconds:
                continue
            if now_ts - float(row.get("proactive_last_ts", 0.0) or 0.0) < THREADREVIVE_PROACTIVE_COOLDOWN_SECONDS:
                continue
            prompts = _socialintel_build_threadrevive_prompts(row, limit=1)
            if not prompts:
                continue
            channel = resolve_channel_or_thread(guild, str(channel_id))
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                continue
            if not _socialintel_channel_is_sendable(channel, me):
                continue
            focus_kind, focus_text = _socialintel_thread_focus(row)
            if not focus_text:
                continue
            try:
                await channel.send(
                    "Thread revive:\n"
                    f"- Context hook: `{_socialintel_compact_excerpt(focus_text, 160)}`\n"
                    f"- Prompt: {prompts[0]}"
                )
            except discord.HTTPException:
                continue
            row["proactive_last_ts"] = now_ts
            _mark_socialintel_dirty()
            break


def _socialintel_jumpin_reason(
    *,
    activity_score: float,
    topic_overlap: float,
    known_contact_ratio: float,
    time_fit: float,
    contact_labels: list[str],
    topic_words: list[str],
) -> str:
    parts: list[str] = []
    if activity_score >= 0.72:
        parts.append("live activity is strong")
    if known_contact_ratio >= 0.25 and contact_labels:
        parts.append("people you already interact with are active")
    if topic_overlap >= 0.22 and topic_words:
        parts.append(f"the channel is circling around {', '.join(topic_words[:2])}")
    if time_fit >= 0.45:
        parts.append("this fits your usual active window")
    return ", ".join(parts[:3]) or "recent traffic is visible, but evidence is still light"


def _socialintel_jumpin_opener(
    *,
    topic_words: list[str],
    requester_metrics: dict[str, Any],
    contact_labels: list[str],
) -> str:
    question_ratio = float(requester_metrics.get("question_ratio", 0.0) or 0.0)
    exclaim_ratio = float(requester_metrics.get("exclaim_ratio", 0.0) or 0.0)
    if topic_words:
        topic_text = ", ".join(topic_words[:2])
        if question_ratio >= exclaim_ratio:
            return f"Quick question on {topic_text}: what changed most recently?"
        if contact_labels:
            return f"I saw {topic_text} come up here again. What is the strongest take right now?"
        return f"What is the current read on {topic_text}?"
    if contact_labels:
        return "What is the latest angle here that is actually worth replying to?"
    return "What is the one update in here that matters most right now?"


async def _socialintel_build_jumpin_rows(
    guild: discord.Guild,
    member: discord.Member,
) -> list[dict[str, Any]]:
    context = collect_socialintel_context(guild, member)
    requester_metrics = context.target_metrics
    if context.target_message_count < 8:
        return []
    now_dt = _guild_now(guild.id)
    cutoff_dt = _utc_now() - timedelta(hours=6)
    interaction_target_ids: set[int] = set()
    for field in ("reply_targets", "mention_targets", "copresence_targets"):
        counter = requester_metrics.get(field, {})
        if not isinstance(counter, dict):
            continue
        for key, _ in sorted(counter.items(), key=lambda item: int(item[1] or 0), reverse=True)[:18]:
            if str(key).isdigit():
                interaction_target_ids.add(int(key))
    guild_state = get_guild_socialintel_state(guild.id)
    channel_rows = guild_state.get("channels", {}) if isinstance(guild_state.get("channels"), dict) else {}
    candidate_rows: list[dict[str, Any]] = []
    sorted_channel_rows = sorted(
        (
            (channel_id, row)
            for channel_id, row in channel_rows.items()
            if isinstance(row, dict)
        ),
        key=lambda item: float(item[1].get("last_message_ts", 0.0) or 0.0),
        reverse=True,
    )[:14]
    for channel_id, row in sorted_channel_rows:
        channel = resolve_channel_or_thread(guild, str(channel_id))
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            continue
        if not _socialintel_channel_is_sendable(channel, guild.me):
            continue
        entries = await collect_messageable_window(channel, limit=40, after=cutoff_dt)
        if len(entries) < 3:
            continue
        unique_authors: list[int] = []
        for entry in entries:
            if entry.author_id not in unique_authors:
                unique_authors.append(entry.author_id)
        recent_contacts = [
            author_id for author_id in unique_authors
            if author_id in interaction_target_ids and author_id != member.id
        ]
        topic_words = _socialintel_recent_topic_words(entries, limit=4)
        topic_counter: dict[str, int] = {}
        for token in topic_words:
            topic_counter[str(token)] = topic_counter.get(str(token), 0) + 1
        recent_topic_counter = row.get("recent_topics", {}) if isinstance(row.get("recent_topics"), dict) else {}
        topic_overlap = _altfinder_counter_overlap(
            requester_metrics.get("topics", {}) if isinstance(requester_metrics.get("topics"), dict) else {},
            recent_topic_counter or topic_counter,
        )
        last_message_ts = float(row.get("last_message_ts", 0.0) or 0.0)
        idle_minutes = max(0.0, (now_dt.timestamp() - last_message_ts) / 60.0)
        if idle_minutes <= 10:
            activity_score = 1.0
        elif idle_minutes <= 30:
            activity_score = 0.86
        elif idle_minutes <= 120:
            activity_score = 0.66
        elif idle_minutes <= 360:
            activity_score = 0.38
        else:
            activity_score = 0.14
        activity_score = min(1.0, activity_score + min(0.22, len(entries) / 60.0))
        known_contact_ratio = len(recent_contacts) / max(1, len(unique_authors))
        time_fit = _socialintel_counter_current_hour_fit(
            requester_metrics.get("active_hours", {}) if isinstance(requester_metrics.get("active_hours"), dict) else {},
            now_dt.hour,
        )
        presence_fit = _socialintel_counter_current_hour_fit(
            requester_metrics.get("presence_hours", {}) if isinstance(requester_metrics.get("presence_hours"), dict) else {},
            now_dt.hour,
        )
        score = (
            (activity_score * 1.35)
            + (topic_overlap * 1.22)
            + (known_contact_ratio * 1.18)
            + (time_fit * 0.82)
            + (presence_fit * 0.45)
        )
        if score < 0.7:
            continue
        contact_labels = [_socialintel_author_label(guild, author_id) for author_id in recent_contacts[:3]]
        candidate_rows.append(
            {
                "channel": channel,
                "score": round(score, 4),
                "topic_words": topic_words,
                "reason": _socialintel_jumpin_reason(
                    activity_score=activity_score,
                    topic_overlap=topic_overlap,
                    known_contact_ratio=known_contact_ratio,
                    time_fit=max(time_fit, presence_fit),
                    contact_labels=contact_labels,
                    topic_words=topic_words,
                ),
                "opener": _socialintel_jumpin_opener(
                    topic_words=topic_words,
                    requester_metrics=requester_metrics,
                    contact_labels=contact_labels,
                ),
            }
        )
    candidate_rows.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return candidate_rows[:3]


def _socialintel_compare_metric(left: float, right: float, scale: float) -> float:
    return 1.0 - _altfinder_scalar_similarity(left, right, scale)


def _socialintel_recent_peak_label(counter: dict[str, Any], *, kind: str) -> str:
    labels = _socialintel_counter_labels(counter, limit=3)
    if not labels:
        return "limited data"
    if kind == "hours":
        return _altfinder_format_hours([int(label) for label in labels if str(label).isdigit()])
    if kind == "weekdays":
        return ", ".join(_socialintel_weekday_label(int(label)) for label in labels if str(label).isdigit())
    return ", ".join(labels)


def _socialintel_profile_drift_score(row: dict[str, Any]) -> tuple[float, str]:
    signatures = row.get("profile_signatures", {}) if isinstance(row.get("profile_signatures"), dict) else {}
    distinct = len(signatures)
    if distinct <= 1:
        return 0.0, "single stable visible profile signature"
    if distinct == 2:
        return 0.42, "more than one visible profile signature has appeared"
    return 0.72, "multiple visible profile signatures have appeared"


def _socialintel_channel_names_from_counter(guild: discord.Guild, counter: dict[str, Any], limit: int = 3) -> str:
    ids: list[int] = []
    if isinstance(counter, dict):
        for key, _ in sorted(counter.items(), key=lambda item: int(item[1] or 0), reverse=True)[:limit]:
            if str(key).isdigit():
                ids.append(int(key))
    return _altfinder_channel_names(guild, ids) if ids else "limited overlap"


def _socialintel_target_names_from_counter(
    guild: discord.Guild,
    counter: dict[str, Any],
    limit: int = 3,
) -> str:
    labels: list[str] = []
    if not isinstance(counter, dict):
        return "limited overlap"
    for key, _ in sorted(counter.items(), key=lambda item: int(item[1] or 0), reverse=True)[:limit]:
        if not str(key).isdigit():
            continue
        labels.append(_socialintel_author_label(guild, int(key)))
    return ", ".join(labels) if labels else "limited overlap"


async def _socialintel_build_driftcheck_report(
    guild: discord.Guild,
    member: discord.Member,
) -> dict[str, Any] | None:
    context = collect_socialintel_context(guild, member)
    baseline_metrics = context.target_metrics
    baseline_count = context.target_message_count
    recent_messages, recent_entries = await collect_recent_user_messages_guild(guild, member.id, 90)
    recent_metrics, recent_count = _socialintel_metrics_from_entries(recent_entries, member.id)
    if baseline_count < 24 or recent_count < 16:
        return None
    style_drift = min(
        1.0,
        (
            _socialintel_compare_metric(float(baseline_metrics.get("avg_len", 0.0)), float(recent_metrics.get("avg_len", 0.0)), 70.0) * 0.24
            + _socialintel_compare_metric(float(baseline_metrics.get("question_ratio", 0.0)), float(recent_metrics.get("question_ratio", 0.0)), 0.45) * 0.16
            + _socialintel_compare_metric(float(baseline_metrics.get("exclaim_ratio", 0.0)), float(recent_metrics.get("exclaim_ratio", 0.0)), 0.45) * 0.14
            + _socialintel_compare_metric(float(baseline_metrics.get("emoji_per_msg", 0.0)), float(recent_metrics.get("emoji_per_msg", 0.0)), 1.8) * 0.14
            + _socialintel_compare_metric(float(baseline_metrics.get("vocab_diversity", 0.0)), float(recent_metrics.get("vocab_diversity", 0.0)), 0.35) * 0.12
            + (1.0 - _altfinder_counter_overlap(
                baseline_metrics.get("bigrams", {}) if isinstance(baseline_metrics.get("bigrams"), dict) else {},
                recent_metrics.get("bigrams", {}) if isinstance(recent_metrics.get("bigrams"), dict) else {},
            )) * 0.2
        )
    )
    activity_drift = min(
        1.0,
        (
            (1.0 - _altfinder_counter_overlap(
                baseline_metrics.get("active_hours", {}) if isinstance(baseline_metrics.get("active_hours"), dict) else {},
                recent_metrics.get("active_hours", {}) if isinstance(recent_metrics.get("active_hours"), dict) else {},
            )) * 0.72
            + (1.0 - _altfinder_counter_overlap(
                baseline_metrics.get("active_weekdays", {}) if isinstance(baseline_metrics.get("active_weekdays"), dict) else {},
                recent_metrics.get("active_weekdays", {}) if isinstance(recent_metrics.get("active_weekdays"), dict) else {},
            )) * 0.28
        )
    )
    channel_drift = 1.0 - _altfinder_counter_overlap(
        baseline_metrics.get("top_channels", {}) if isinstance(baseline_metrics.get("top_channels"), dict) else {},
        recent_metrics.get("top_channels", {}) if isinstance(recent_metrics.get("top_channels"), dict) else {},
    )
    interaction_drift = min(
        1.0,
        (
            (1.0 - _altfinder_counter_overlap(
                baseline_metrics.get("reply_targets", {}) if isinstance(baseline_metrics.get("reply_targets"), dict) else {},
                recent_metrics.get("reply_targets", {}) if isinstance(recent_metrics.get("reply_targets"), dict) else {},
            )) * 0.4
            + (1.0 - _altfinder_counter_overlap(
                baseline_metrics.get("mention_targets", {}) if isinstance(baseline_metrics.get("mention_targets"), dict) else {},
                recent_metrics.get("mention_targets", {}) if isinstance(recent_metrics.get("mention_targets"), dict) else {},
            )) * 0.32
            + (1.0 - _altfinder_counter_overlap(
                baseline_metrics.get("copresence_targets", {}) if isinstance(baseline_metrics.get("copresence_targets"), dict) else {},
                recent_metrics.get("copresence_targets", {}) if isinstance(recent_metrics.get("copresence_targets"), dict) else {},
            )) * 0.28
        )
    )
    current_hour = _guild_now(guild.id).hour
    current_status = str(context.target_row.get("last_status", "offline") or "offline")
    presence_hour_fit = _socialintel_counter_current_hour_fit(
        baseline_metrics.get("presence_hours", {}) if isinstance(baseline_metrics.get("presence_hours"), dict) else {},
        current_hour,
    )
    presence_status_fit = 0.0
    status_counts = baseline_metrics.get("status_counts", {}) if isinstance(baseline_metrics.get("status_counts"), dict) else {}
    if isinstance(status_counts, dict) and status_counts:
        max_status = max(int(value or 0) for value in status_counts.values())
        if max_status > 0:
            presence_status_fit = min(1.0, int(status_counts.get(current_status, 0) or 0) / max_status)
    presence_drift = min(1.0, ((1.0 - presence_hour_fit) * 0.55) + ((1.0 - presence_status_fit) * 0.45))
    profile_drift, profile_note = _socialintel_profile_drift_score(context.target_row)
    anomaly_score = min(
        0.98,
        (style_drift * 0.28)
        + (activity_drift * 0.18)
        + (channel_drift * 0.18)
        + (interaction_drift * 0.18)
        + (presence_drift * 0.08)
        + (profile_drift * 0.10)
    )
    return {
        "recent_messages": recent_messages,
        "baseline_count": baseline_count,
        "recent_count": recent_count,
        "anomaly_score": round(anomaly_score, 4),
        "band": _socialintel_confidence_band(anomaly_score),
        "style_drift": round(style_drift, 4),
        "activity_drift": round(activity_drift, 4),
        "channel_drift": round(channel_drift, 4),
        "interaction_drift": round(interaction_drift, 4),
        "presence_drift": round(presence_drift, 4),
        "profile_drift": round(profile_drift, 4),
        "profile_note": profile_note,
        "baseline_metrics": baseline_metrics,
        "recent_metrics": recent_metrics,
        "current_status": current_status,
    }


def _socialintel_arc_message_score(entry: WindowMessage) -> float:
    score = _socialintel_tension_score(entry.content)
    if entry.reference_message_id is not None:
        score += 0.08
    if entry.mention_ids:
        score += min(0.18, len(entry.mention_ids) * 0.05)
    return min(1.0, score)


def _socialintel_arc_report_lines(
    guild: discord.Guild,
    entries: list[WindowMessage],
) -> dict[str, Any] | None:
    if len(entries) < 8:
        return None
    scored = [
        {
            "entry": entry,
            "tension": _socialintel_arc_message_score(entry),
            "calm": _socialintel_deescalation_score(entry.content),
        }
        for entry in entries
    ]
    hot = [row for row in scored if float(row["tension"]) >= 0.22]
    if not hot:
        return None
    starter = min(hot, key=lambda row: float(row["entry"].created_at_ts))
    starter_ts = float(starter["entry"].created_at_ts)
    escalator_scores: Counter[int] = Counter()
    deescalator_scores: Counter[int] = Counter()
    pivot_rows: list[dict[str, Any]] = []
    unresolved: list[str] = []
    evidence_lines: list[str] = []
    seen_pivots: set[int] = set()
    for row in scored:
        entry = row["entry"]
        if float(entry.created_at_ts) < starter_ts:
            continue
        escalator_scores[entry.author_id] += float(row["tension"])
        deescalator_scores[entry.author_id] += float(row["calm"])
        if row["tension"] >= 0.24 or row["calm"] >= 0.22:
            if len(evidence_lines) < 5:
                stamp = datetime.fromtimestamp(entry.created_at_ts, tz=_safe_zoneinfo(get_guild_engagement_timezone(guild.id))).strftime("%H:%M")
                evidence_lines.append(
                    f"[{stamp}] {_socialintel_author_label(guild, entry.author_id)}: `{_socialintel_compact_excerpt(entry.content, 110)}`"
                )
        if entry.message_id not in seen_pivots and (row["calm"] >= 0.22 or ("?" in entry.content and row["tension"] >= 0.18)):
            seen_pivots.add(entry.message_id)
            pivot_rows.append(row)
        if "?" in entry.content and len(unresolved) < 3:
            unresolved.append(_socialintel_compact_excerpt(entry.content, 120))
    top_escalators = [
        f"{_socialintel_author_label(guild, user_id)} ({score:.2f})"
        for user_id, score in escalator_scores.most_common(3)
        if score >= 0.24
    ]
    top_deescalators = [
        f"{_socialintel_author_label(guild, user_id)} ({score:.2f})"
        for user_id, score in deescalator_scores.most_common(3)
        if score >= 0.18
    ]
    if not unresolved:
        recent_questions = [row["entry"] for row in scored[-8:] if "?" in row["entry"].content]
        unresolved = [_socialintel_compact_excerpt(entry.content, 120) for entry in recent_questions[:2]]
    return {
        "starter": starter["entry"],
        "escalators": top_escalators,
        "deescalators": top_deescalators,
        "pivots": [
            f"{_socialintel_author_label(guild, row['entry'].author_id)}: `{_socialintel_compact_excerpt(row['entry'].content, 110)}`"
            for row in pivot_rows[:3]
        ],
        "unresolved": unresolved[:3],
        "evidence_lines": evidence_lines[:5],
    }


def strip_bot_address_prefix(message: discord.Message) -> str | None:
    if bot.user is None:
        return None

    raw = message.content.strip()
    if not raw:
        return None

    mention_pattern = rf"^<@!?{bot.user.id}>\s*[:,\-]?\s*(.*)$"
    mention_match = re.match(mention_pattern, raw, flags=re.IGNORECASE)
    if mention_match:
        remainder = mention_match.group(1).strip()
        return remainder if remainder else None

    names: set[str] = {"bell", bot.user.name.lower()}
    if isinstance(message.guild, discord.Guild):
        me = message.guild.me
        if me and me.display_name:
            names.add(me.display_name.lower())

    lowered = raw.lower()
    for name in sorted(names, key=len, reverse=True):
        name_match = re.match(rf"^{re.escape(name)}\b\s*[:,\-]?\s*(.*)$", lowered)
        if name_match:
            remainder = name_match.group(1).strip()
            return remainder if remainder else None
    return None


def parse_conversation_summary_count(text: str) -> int | None:
    lowered = text.lower()
    if re.search(r"\b(summarise|summarize|summary)\b", lowered) is None:
        return None

    count_match = re.search(r"\b(\d{1,4})\s*(?:msgs?|messages?)\b", lowered)
    if count_match is None:
        count_match = re.search(r"\b(?:of|for|last|past)\s+(\d{1,4})\b", lowered)
    if count_match is None:
        count_match = re.search(
            r"\b(?:summarise|summarize|summary)\b.*?\b(\d{1,4})\b", lowered
        )

    if count_match is not None:
        return int(count_match.group(1))
    return 100


def parse_catchup_hours_request(text: str) -> int | None:
    lowered = text.lower()
    if "catchup" not in lowered and "catch up" not in lowered:
        return None

    match = re.search(r"\b(\d{1,3})\s*(?:h|hr|hrs|hour|hours)\b", lowered)
    if match is None:
        match = re.search(r"\bcatch\s*up\b.*?\b(\d{1,3})\b", lowered)
    if match is None:
        match = re.search(r"\bcatchup\b.*?\b(\d{1,3})\b", lowered)
    hours = int(match.group(1)) if match else 24
    return max(1, min(hours, CATCHUP_MAX_HOURS))


def parse_serverinsights_hours_request(text: str) -> int | None:
    lowered = text.lower()
    if (
        "serverinsights" not in lowered
        and "server insights" not in lowered
        and "engagement insights" not in lowered
    ):
        return None
    match = re.search(r"\b(\d{1,3})\s*(?:h|hr|hrs|hour|hours)\b", lowered)
    if match is None:
        match = re.search(r"\b(?:for|last|past)\s+(\d{1,3})\b", lowered)
    hours = int(match.group(1)) if match else 72
    return max(6, min(hours, INSIGHTS_MAX_HOURS))


def parse_psych_action_and_seed(raw: str | None) -> tuple[str, str | None]:
    content = (raw or "").strip()
    if not content:
        return "start", None

    parts = content.split(maxsplit=1)
    action = parts[0].lower()
    if action in PSYCH_ACTIONS:
        seed = parts[1].strip() if len(parts) > 1 else None
        return action, (seed if seed else None)
    return "start", content


def parse_psych_alias_request(text: str) -> tuple[str | None, str | None]:
    match = re.match(r"^\s*psych(?:ologist)?\b\s*(.*)$", text, flags=re.IGNORECASE)
    if not match:
        return None, None
    return parse_psych_action_and_seed(match.group(1))


def detect_crisis_risk(text: str) -> bool:
    return bool(PSYCH_CRISIS_PATTERN.search(text))


def is_psych_solution_request(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    if not normalized:
        return False
    if normalized in {"enough", "thats enough", "that's enough"}:
        return True
    return bool(PSYCH_SOLUTION_PATTERN.search(normalized))


def psych_session_key(channel_id: int, user_id: int) -> tuple[int, int]:
    return channel_id, user_id


def get_user_display_name(user: discord.abc.User) -> str:
    return getattr(user, "display_name", getattr(user, "name", "User"))


def _psych_ttl_seconds() -> int:
    return max(60, PSYCH_SESSION_TIMEOUT_MINUTES * 60)


def cancel_psych_flush(channel_id: int, user_id: int) -> None:
    key = psych_session_key(channel_id, user_id)
    task = PSYCH_PENDING_TASKS.pop(key, None)
    current_task = asyncio.current_task()
    if task is not None and not task.done() and task is not current_task:
        task.cancel()


def get_psych_session(channel_id: int, user_id: int) -> dict[str, object] | None:
    key = psych_session_key(channel_id, user_id)
    session = PSYCH_SESSIONS.get(key)
    if session is None:
        return None
    last_activity = float(session.get("last_activity", 0.0))
    if time.monotonic() - last_activity > _psych_ttl_seconds():
        cancel_psych_flush(channel_id, user_id)
        PSYCH_SESSIONS.pop(key, None)
        PSYCH_SESSION_LOCKS.pop(key, None)
        return None
    return session


def start_psych_session(channel_id: int, user_id: int) -> dict[str, object]:
    key = psych_session_key(channel_id, user_id)
    now = time.monotonic()
    session = {
        "created_at": now,
        "last_activity": now,
        "turns": 0,
        "history": [],
        "notes": "",
        "phase": "assessment",
        "buffer": [],
        "buffer_started_at": None,
        "question_count": 0,
        "last_solution_at": None,
        "listening": True,
    }
    PSYCH_SESSIONS[key] = session
    return session


def stop_psych_session(channel_id: int, user_id: int) -> None:
    cancel_psych_flush(channel_id, user_id)
    key = psych_session_key(channel_id, user_id)
    PSYCH_SESSIONS.pop(key, None)
    PSYCH_SESSION_LOCKS.pop(key, None)


def reset_psych_session(channel_id: int, user_id: int) -> bool:
    session = get_psych_session(channel_id, user_id)
    if session is None:
        return False
    cancel_psych_flush(channel_id, user_id)
    session["history"] = []
    session["notes"] = ""
    session["turns"] = 0
    session["phase"] = "assessment"
    session["buffer"] = []
    session["buffer_started_at"] = None
    session["question_count"] = 0
    session["last_solution_at"] = None
    session["listening"] = True
    session["last_activity"] = time.monotonic()
    return True


def append_psych_buffer(channel_id: int, user_id: int, message_text: str) -> bool:
    session = get_psych_session(channel_id, user_id)
    if session is None:
        return False

    normalized = " ".join(message_text.split()).strip()
    if not normalized:
        return False
    normalized = normalized[:900]

    buffer = session.get("buffer")
    if not isinstance(buffer, list):
        buffer = []
        session["buffer"] = buffer

    if not buffer:
        session["buffer_started_at"] = time.monotonic()
    buffer.append(normalized)
    if len(buffer) > PSYCH_MAX_BUFFERED_MESSAGES:
        del buffer[: len(buffer) - PSYCH_MAX_BUFFERED_MESSAGES]

    session["last_activity"] = time.monotonic()
    return True


def _format_remaining_ttl(seconds: int) -> str:
    remaining = max(0, seconds)
    minutes = remaining // 60
    hours, mins = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def _get_psych_status_text(channel_id: int, user_id: int, display_name: str) -> str:
    session = get_psych_session(channel_id, user_id)
    if session is None:
        return (
            f"Psych support mode for **{display_name}** is currently **inactive**.\n"
            f"Start with `{PREFIX}psych start <how you feel>` or `bell psych start ...`."
        )

    ttl_seconds = _psych_ttl_seconds() - int(time.monotonic() - float(session.get("last_activity", 0.0)))
    turns = int(session.get("turns", 0))
    notes = str(session.get("notes", "")).strip()
    phase = str(session.get("phase", "assessment")).strip() or "assessment"
    buffered = session.get("buffer")
    buffered_count = len(buffered) if isinstance(buffered, list) else 0
    focus = notes.split(".")[0].strip() if notes else "getting to know your situation"
    focus = focus[:180]
    return (
        f"Psych support mode for **{display_name}** is **active**.\n"
        f"Phase: `{phase}`\n"
        f"Session TTL: `{_format_remaining_ttl(ttl_seconds)}`\n"
        f"Turns used: `{turns}/{PSYCH_MAX_TURNS}`\n"
        f"Buffered messages: `{buffered_count}/{PSYCH_MAX_BUFFERED_MESSAGES}`\n"
        f"Current focus: {focus}"
    )


def _build_crisis_psych_reply() -> str:
    return (
        "I am really glad you told me this. Your safety matters most right now.\n"
        "Please contact your local emergency services now, or go to the nearest emergency department immediately.\n"
        "Can you contact a trusted person right now and ask them to stay with you?\n"
        "While you do that, place both feet on the floor, take 5 slow breaths, and name 5 things you can see."
    )


def _parse_psych_ai_payload(raw_text: str, current_notes: str) -> tuple[str, str]:
    text = raw_text.strip()
    parsed_reply = ""
    parsed_notes = current_notes

    match = re.search(
        r"REPLY:\s*(.*?)\s*UPDATED_NOTES:\s*(.*)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        parsed_reply = match.group(1).strip()
        parsed_notes = match.group(2).strip()
    else:
        parsed_reply = re.sub(r"^REPLY:\s*", "", text, flags=re.IGNORECASE).strip()

    if not parsed_reply:
        parsed_reply = (
            "Thanks for sharing that with me.\n"
            "Try 2 gentle steps now: drink some water and take a 5-minute pause away from noise.\n"
            "What feels hardest for you right now?"
        )

    normalized_notes = " ".join(parsed_notes.split()).strip()
    if len(normalized_notes) > PSYCH_MAX_NOTES_CHARS:
        normalized_notes = normalized_notes[: PSYCH_MAX_NOTES_CHARS - 3].rstrip() + "..."

    return parsed_reply, normalized_notes


def _apply_psych_turn_update(
    session: dict[str, object],
    *,
    user_input: str,
    assistant_reply: str,
    updated_notes: str,
    asked_question: bool = False,
    solution_mode: bool = False,
) -> None:
    history = session.get("history")
    if not isinstance(history, list):
        history = []
        session["history"] = history
    history_context = history[-(AI_MAX_HISTORY * 2) :]
    session["history"] = [
        *history_context,
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": assistant_reply},
    ]
    session["notes"] = updated_notes
    session["turns"] = int(session.get("turns", 0)) + 1
    if asked_question:
        session["question_count"] = int(session.get("question_count", 0)) + 1
    if solution_mode:
        session["last_solution_at"] = time.monotonic()
        session["phase"] = "solution"
    else:
        session["phase"] = "assessment"
    session["last_activity"] = time.monotonic()


def apply_psych_crisis_reply(session: dict[str, object], user_input: str) -> str:
    current_notes = str(session.get("notes", "")).strip()
    reply = _build_crisis_psych_reply()
    updated_notes = (
        f"{current_notes} Crisis risk language detected; advised immediate emergency and trusted-person support."
    ).strip()[:PSYCH_MAX_NOTES_CHARS]
    _apply_psych_turn_update(
        session,
        user_input=user_input,
        assistant_reply=reply,
        updated_notes=updated_notes,
        asked_question=True,
        solution_mode=False,
    )
    return reply


async def _build_psych_phase_reply(
    session: dict[str, object],
    *,
    user_display_name: str,
    user_input: str,
    phase: Literal["assessment", "solution"],
) -> str:
    history = session.get("history")
    if not isinstance(history, list):
        history = []
        session["history"] = history
    history_context = history[-(AI_MAX_HISTORY * 2) :]
    current_notes = str(session.get("notes", "")).strip()

    if phase == "solution":
        phase_instructions = (
            "MODE: SOLUTION.\n"
            "The user explicitly asked for advice/plan.\n"
            "Provide practical non-medical guidance.\n"
            "Output exactly:\n"
            "Line 1: short reflection + key factors summary.\n"
            "Line 2: 3-5 concrete steps (short and actionable).\n"
            "Line 3: one check-in question.\n"
            "No diagnosis. No medication advice."
        )
    else:
        phase_instructions = (
            "MODE: ASSESSMENT.\n"
            "Listen first and collect context.\n"
            "Do not give full solution yet.\n"
            "Output exactly:\n"
            "Line 1: reflective acknowledgement.\n"
            "Line 2: concise summary of what you understood + at most one light stabilizing tip.\n"
            "Line 3: one focused follow-up question.\n"
            "Do not jump to conclusions."
        )

    prompt = (
        f"User display name: {user_display_name}\n"
        f"Session phase: {phase}\n"
        f"Current personalization notes: {current_notes or '(none)'}\n"
        f"Latest user turn (possibly multiple messages merged): {user_input[:2200]}\n\n"
        f"{phase_instructions}\n\n"
        "Return exactly this envelope:\n"
        "REPLY:\n"
        "<exactly 3 lines>\n"
        "UPDATED_NOTES:\n"
        "<max 4 short sentences capturing stressors/goals/routines/preferences; no diagnosis>"
    )
    messages = [
        {"role": "system", "content": PSYCH_SYSTEM_PROMPT},
        *history_context,
        {"role": "user", "content": prompt},
    ]
    raw = await request_ai_completion(
        messages,
        max_tokens=PSYCH_MAX_TOKENS,
        temperature=0.35,
        policy_key="psych",
    )
    reply, updated_notes = _parse_psych_ai_payload(raw, current_notes)
    _apply_psych_turn_update(
        session,
        user_input=user_input,
        assistant_reply=reply,
        updated_notes=updated_notes,
        asked_question=True,
        solution_mode=(phase == "solution"),
    )
    return reply


async def build_psych_assessment_reply(
    session: dict[str, object],
    *,
    user_display_name: str,
    user_input: str,
) -> str:
    return await _build_psych_phase_reply(
        session,
        user_display_name=user_display_name,
        user_input=user_input,
        phase="assessment",
    )


async def build_psych_solution_reply(
    session: dict[str, object],
    *,
    user_display_name: str,
    user_input: str,
) -> str:
    return await _build_psych_phase_reply(
        session,
        user_display_name=user_display_name,
        user_input=user_input,
        phase="solution",
    )


def schedule_psych_flush(
    channel_id: int,
    user_id: int,
    channel: discord.abc.Messageable,
    user_display_name: str,
) -> None:
    cancel_psych_flush(channel_id, user_id)
    key = psych_session_key(channel_id, user_id)

    async def _runner() -> None:
        try:
            await asyncio.sleep(PSYCH_LISTEN_WINDOW_SECONDS)
            await flush_psych_buffer(
                channel_id=channel_id,
                user_id=user_id,
                channel=channel,
                user_display_name=user_display_name,
            )
        except asyncio.CancelledError:
            return
        finally:
            active = PSYCH_PENDING_TASKS.get(key)
            if active is asyncio.current_task():
                PSYCH_PENDING_TASKS.pop(key, None)

    PSYCH_PENDING_TASKS[key] = asyncio.create_task(_runner())


async def flush_psych_buffer(
    *,
    channel_id: int,
    user_id: int,
    channel: discord.abc.Messageable,
    user_display_name: str,
) -> None:
    key = psych_session_key(channel_id, user_id)
    reply_to_send: str | None = None
    auto_stop = False

    lock = PSYCH_SESSION_LOCKS[key]
    async with lock:
        session = get_psych_session(channel_id, user_id)
        if session is None:
            return

        buffered = session.get("buffer")
        if not isinstance(buffered, list) or not buffered:
            return

        combined_user_turn = "\n".join(str(item) for item in buffered if str(item).strip()).strip()
        session["buffer"] = []
        session["buffer_started_at"] = None
        session["last_activity"] = time.monotonic()
        if not combined_user_turn:
            return

        if PSYCH_CRISIS_STRICT and detect_crisis_risk(combined_user_turn):
            reply_to_send = apply_psych_crisis_reply(session, combined_user_turn)
        else:
            wants_solution = (
                PSYCH_SOLUTION_TRIGGER_MODE == "explicit"
                and is_psych_solution_request(combined_user_turn)
            )
            try:
                if wants_solution:
                    reply_to_send = await build_psych_solution_reply(
                        session,
                        user_display_name=user_display_name,
                        user_input=combined_user_turn,
                    )
                else:
                    reply_to_send = await build_psych_assessment_reply(
                        session,
                        user_display_name=user_display_name,
                        user_input=combined_user_turn,
                    )
            except Exception as error:
                print(f"[PSYCH MODE FLUSH ERROR] {error}")
                reply_to_send = friendly_ai_error(error)

        auto_stop = int(session.get("turns", 0)) >= PSYCH_MAX_TURNS
        if auto_stop:
            stop_psych_session(channel_id, user_id)

    if not reply_to_send:
        return

    if auto_stop:
        await send_chunked(
            channel,
            (
                f"{reply_to_send}\n\n"
                f"_Psych session auto-stopped after `{PSYCH_MAX_TURNS}` turns. "
                "Use `&psych start` to continue._"
            ),
        )
        return

    await send_chunked(channel, reply_to_send)


async def run_psych_action_for_user(
    channel: discord.abc.Messageable,
    *,
    channel_id: int,
    user_id: int,
    user_display_name: str,
    action: str,
    seed_text: str | None,
) -> None:
    key = psych_session_key(channel_id, user_id)
    normalized_action = action.lower()

    if normalized_action == "status":
        await channel.send(_get_psych_status_text(channel_id, user_id, user_display_name))
        return

    if normalized_action == "stop":
        if get_psych_session(channel_id, user_id) is None:
            await channel.send("Psych support mode is not active for you in this channel.")
            return
        stop_psych_session(channel_id, user_id)
        await channel.send("Psych support mode stopped. Start again anytime with `&psych start`.")
        return

    if normalized_action == "reset":
        if not reset_psych_session(channel_id, user_id):
            await channel.send("No active psych session found to reset in this channel.")
            return
        await channel.send("Psych session memory reset. We can start fresh from here.")
        return

    if not is_ai_configured():
        await channel.send(ai_setup_message())
        return

    if get_argument_session(channel_id, user_id) is not None:
        stop_argument_session(channel_id, user_id)

    session = get_psych_session(channel_id, user_id)
    if session is None:
        session = start_psych_session(channel_id, user_id)
    else:
        session["last_activity"] = time.monotonic()

    opener = (
        "Psych support mode is active. I am your supportive assistant, not a substitute for professional care.\n"
        f"I will listen first and reply after `{int(PSYCH_LISTEN_WINDOW_SECONDS)}`s of silence."
    )
    if not seed_text:
        await channel.send(
            f"{opener}\n"
            "Share freely, and when you want advice say: `give advice` / `what should I do`."
        )
        return

    append_psych_buffer(channel_id, user_id, seed_text)
    schedule_psych_flush(channel_id, user_id, channel, user_display_name)
    await channel.send(
        f"{opener}\nI am listening. Keep going; I will respond once you pause."
    )


async def handle_active_psych_session_turn(message: discord.Message) -> bool:
    session = get_psych_session(message.channel.id, message.author.id)
    if session is None:
        return False

    addressed = strip_bot_address_prefix(message)
    if addressed:
        psych_action, psych_seed = parse_psych_alias_request(addressed)
        if psych_action is not None:
            await run_psych_action_for_user(
                message.channel,
                channel_id=message.channel.id,
                user_id=message.author.id,
                user_display_name=get_user_display_name(message.author),
                action=psych_action,
                seed_text=psych_seed,
            )
            return True
        if parse_argument_topic(addressed) is not None:
            stop_psych_session(message.channel.id, message.author.id)
            return False

    user_text = message.content.strip()
    if not user_text:
        return False

    if PSYCH_CRISIS_STRICT and detect_crisis_risk(user_text):
        key = psych_session_key(message.channel.id, message.author.id)
        cancel_psych_flush(message.channel.id, message.author.id)
        lock = PSYCH_SESSION_LOCKS[key]
        async with lock:
            current_session = get_psych_session(message.channel.id, message.author.id)
            if current_session is None:
                return False
            buffered = current_session.get("buffer")
            buffered_lines = buffered if isinstance(buffered, list) else []
            combined = "\n".join([*buffered_lines, user_text]).strip()
            current_session["buffer"] = []
            current_session["buffer_started_at"] = None
            reply = apply_psych_crisis_reply(current_session, combined or user_text)
            auto_stop = int(current_session.get("turns", 0)) >= PSYCH_MAX_TURNS
            if auto_stop:
                stop_psych_session(message.channel.id, message.author.id)
        if auto_stop:
            await send_chunked(
                message.channel,
                (
                    f"{reply}\n\n"
                    f"_Psych session auto-stopped after `{PSYCH_MAX_TURNS}` turns. "
                    "Use `&psych start` to continue._"
                ),
            )
            return True
        await send_chunked(message.channel, reply)
        return True

    if append_psych_buffer(message.channel.id, message.author.id, user_text):
        schedule_psych_flush(
            message.channel.id,
            message.author.id,
            message.channel,
            get_user_display_name(message.author),
        )
        return True

    return True


def parse_argument_topic(text: str) -> str | None:
    match = re.search(
        r"\b(?:argument|argue|debate)\b(?:\s+(?:about|on|over))?\s+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    topic = match.group(1).strip(" .!?")
    topic = re.sub(r"^(with me|against me)\s+", "", topic, flags=re.IGNORECASE).strip()
    if len(topic) < 3:
        return None
    return topic


def argument_stop_requested(text: str) -> bool:
    lowered = text.lower()
    return (
        re.search(r"\b(stop|end|cancel|quit|enough)\b", lowered) is not None
        and re.search(r"\b(argument|argue|debate|mode)\b", lowered) is not None
    ) or lowered.strip() in {"stop", "stop it", "to stop", "please stop"}


def get_argument_session(channel_id: int, user_id: int) -> dict[str, object] | None:
    key = (channel_id, user_id)
    session = ARGUMENT_MODE_SESSIONS.get(key)
    if session is None:
        return None

    last_activity = float(session.get("last_activity", 0.0))
    if time.monotonic() - last_activity > ARGUMENT_MODE_TIMEOUT_MINUTES * 60:
        ARGUMENT_MODE_SESSIONS.pop(key, None)
        return None
    return session


def start_argument_session(channel_id: int, user_id: int, topic: str, side: str) -> None:
    ARGUMENT_MODE_SESSIONS[(channel_id, user_id)] = {
        "topic": topic[:260],
        "side": side,
        "turns": 0,
        "history": [],
        "last_activity": time.monotonic(),
    }


def stop_argument_session(channel_id: int, user_id: int) -> None:
    ARGUMENT_MODE_SESSIONS.pop((channel_id, user_id), None)


def append_conversation_history(
    cache: dict[tuple[int, int], list[dict[str, str]]],
    key: tuple[int, int],
    user_prompt: str,
    assistant_reply: str,
) -> None:
    history = cache[key]
    history.append({"role": "user", "content": user_prompt})
    history.append({"role": "assistant", "content": assistant_reply})
    max_entries = max(2, AI_MAX_HISTORY * 2)
    if len(history) > max_entries:
        cache[key] = history[-max_entries:]


async def is_reply_to_bot_message(message: discord.Message) -> bool:
    if bot.user is None or message.reference is None or message.reference.message_id is None:
        return False

    resolved = message.reference.resolved
    if isinstance(resolved, discord.Message):
        return resolved.author.id == bot.user.id

    if not isinstance(message.channel, discord.TextChannel):
        return False
    try:
        referenced = await message.channel.fetch_message(message.reference.message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return False
    return referenced.author.id == bot.user.id


def find_member_by_name(guild: discord.Guild, query: str) -> discord.Member | None:
    cleaned = re.sub(r"[^\w\s.\-]", " ", query).strip().lower()
    if not cleaned:
        return None

    words = cleaned.split()
    noise = {
        "avatar",
        "pfp",
        "profile",
        "pic",
        "picture",
        "timeout",
        "mute",
        "remove",
        "show",
        "give",
        "please",
        "to",
        "for",
        "of",
    }
    candidate = " ".join(w for w in words if w not in noise).strip()
    if not candidate:
        return None

    exact = discord.utils.find(
        lambda m: m.display_name.lower() == candidate or m.name.lower() == candidate,
        guild.members,
    )
    if exact:
        return exact

    starts = discord.utils.find(
        lambda m: m.display_name.lower().startswith(candidate) or m.name.lower().startswith(candidate),
        guild.members,
    )
    if starts:
        return starts
    return None


def extract_conversation_target(
    message: discord.Message, text: str, *, allow_self_avatar: bool = False
) -> discord.Member | None:
    for member in message.mentions:
        if bot.user is None or member.id != bot.user.id:
            return member

    lowered = text.lower()
    if allow_self_avatar and ("my avatar" in lowered or "my pfp" in lowered):
        return message.author if isinstance(message.author, discord.Member) else None

    if not isinstance(message.guild, discord.Guild):
        return None

    avatar_match = re.search(r"show\s+(.+?)'?s\s+avatar\b", text, flags=re.IGNORECASE)
    if avatar_match:
        found = find_member_by_name(message.guild, avatar_match.group(1))
        if found:
            return found

    pfp_possessive_match = re.search(r"show\s+(.+?)'?s\s+pfp\b", text, flags=re.IGNORECASE)
    if pfp_possessive_match:
        found = find_member_by_name(message.guild, pfp_possessive_match.group(1))
        if found:
            return found

    avatar_of_match = re.search(r"avatar\s+of\s+(.+)$", text, flags=re.IGNORECASE)
    if avatar_of_match:
        found = find_member_by_name(message.guild, avatar_of_match.group(1))
        if found:
            return found

    pfp_of_match = re.search(r"pfp\s+of\s+(.+)$", text, flags=re.IGNORECASE)
    if pfp_of_match:
        found = find_member_by_name(message.guild, pfp_of_match.group(1))
        if found:
            return found

    return find_member_by_name(message.guild, text)


async def send_avatar_for_member(channel: discord.abc.Messageable, target: discord.Member) -> None:
    embed = discord.Embed(
        title=f"{target.display_name}'s Avatar",
        color=discord.Color.blurple(),
    )
    embed.set_image(url=target.display_avatar.url)
    await channel.send(embed=embed)


async def send_server_info_embed(channel: discord.abc.Messageable, guild: discord.Guild) -> None:
    embed = discord.Embed(
        title="Server Info",
        color=discord.Color.teal(),
        timestamp=discord.utils.utcnow(),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Server", value=f"{guild.name} (`{guild.id}`)", inline=False)
    embed.add_field(name="Owner", value=str(guild.owner), inline=True)
    embed.add_field(name="Members", value=str(guild.member_count), inline=True)
    embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
    embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, style="F"), inline=False)
    await channel.send(embed=embed)


def normalize_leaderboard_mode(raw: str | None) -> Literal["daily", "weekly", "alltime"]:
    normalized = (raw or "alltime").strip().lower()
    if normalized in {"day", "today", "daily"}:
        return "daily"
    if normalized in {"week", "weekly"}:
        return "weekly"
    return "alltime"


def _resolve_member_display(guild: discord.Guild, user_id: int) -> str:
    member = guild.get_member(user_id)
    if member is not None:
        return member.display_name
    return f"User {user_id}"


def build_leaderboard_rows(
    guild: discord.Guild,
    mode: Literal["daily", "weekly", "alltime"],
    *,
    limit: int = 10,
) -> list[tuple[int, str, int]]:
    guild_state = get_guild_engagement_state(guild.id)
    users = guild_state.get("users")
    if not isinstance(users, dict):
        return []
    day_key = _guild_day_key(guild.id)
    week_key = _guild_week_key(guild.id)
    rows: list[tuple[int, str, int]] = []
    for raw_user_id, state in users.items():
        if not isinstance(state, dict):
            continue
        try:
            user_id = int(raw_user_id)
        except (TypeError, ValueError):
            continue
        score = get_metric_for_user(state, mode, day_key=day_key, week_key=week_key)
        if score <= 0:
            continue
        rows.append((user_id, _resolve_member_display(guild, user_id), score))
    rows.sort(key=lambda item: item[2], reverse=True)
    return rows[: max(1, limit)]


def get_user_rank_position(guild: discord.Guild, user_id: int, mode: Literal["daily", "weekly", "alltime"]) -> tuple[int, int]:
    guild_state = get_guild_engagement_state(guild.id)
    users = guild_state.get("users")
    if not isinstance(users, dict):
        return 0, 0
    day_key = _guild_day_key(guild.id)
    week_key = _guild_week_key(guild.id)
    scored: list[tuple[int, int]] = []
    for raw_user_id, state in users.items():
        if not isinstance(state, dict):
            continue
        try:
            uid = int(raw_user_id)
        except (TypeError, ValueError):
            continue
        value = get_metric_for_user(state, mode, day_key=day_key, week_key=week_key)
        if value <= 0:
            continue
        scored.append((uid, value))
    if not scored:
        return 0, 0
    scored.sort(key=lambda item: item[1], reverse=True)
    for idx, (uid, _) in enumerate(scored, start=1):
        if uid == user_id:
            return idx, len(scored)
    return 0, len(scored)


def get_user_quest_view(guild_id: int, user_id: int) -> tuple[str, list[str], int, int]:
    user_state = get_user_engagement_state(guild_id, user_id)
    quests, progress, completed = get_user_daily_quests(guild_id, user_state)
    lines: list[str] = []
    completed_count = 0
    total_reward = 0
    for quest in quests:
        quest_id = str(quest.get("id", ""))
        metric = str(quest.get("type", ""))
        target = int(quest.get("target", 1))
        reward = int(quest.get("reward", 0))
        current = int(progress.get(metric, 0))
        done = quest_id in completed
        if done:
            completed_count += 1
            total_reward += reward
        marker = "âœ…" if done else "â–«ï¸"
        lines.append(
            f"{marker} {quest.get('name', quest_id)} - `{current}/{target}` (+{reward} XP)"
        )
    return _guild_day_key(guild_id), lines, completed_count, total_reward


def get_rank_snapshot(guild_id: int, user_id: int) -> dict[str, int]:
    state = get_user_engagement_state(guild_id, user_id)
    daily = state.get("daily", {})
    weekly = state.get("weekly", {})
    return {
        "xp": int(state.get("xp", 0)),
        "streak": int(state.get("streak", 0)),
        "best_streak": int(state.get("best_streak", 0)),
        "daily_xp": int(daily.get("xp", 0)) if isinstance(daily, dict) and daily.get("day") == _guild_day_key(guild_id) else 0,
        "weekly_points": int(weekly.get("points", 0)) if isinstance(weekly, dict) and weekly.get("key") == _guild_week_key(guild_id) else 0,
        "event_points": int(state.get("event_points", 0)),
    }


async def process_event_message(message: discord.Message) -> None:
    session = EVENT_SESSIONS.get(message.guild.id)
    if not session:
        return
    if int(session.get("channel_id", 0)) != message.channel.id:
        return
    if message.author.bot:
        return
    if message.content.startswith(PREFIX):
        return

    cooldown_key = (message.guild.id, message.author.id)
    now = time.monotonic()
    last = EVENT_MESSAGE_COOLDOWNS.get(cooldown_key, 0.0)
    if now - last < 12:
        return
    EVENT_MESSAGE_COOLDOWNS[cooldown_key] = now

    scores = session.setdefault("scores", {})
    if not isinstance(scores, dict):
        scores = {}
        session["scores"] = scores

    user_key = str(message.author.id)
    points = int(scores.get(user_key, 0))
    event_type = str(session.get("type", "hottake"))
    gained = 1
    if event_type == "trivia":
        answers = session.get("answers")
        normalized = _normalize_content_for_xp(message.content)
        if isinstance(answers, set) and any(answer in normalized for answer in answers):
            gained = 3
        else:
            gained = 1
    scores[user_key] = min(14, points + gained)
    _mark_engagement_dirty()


def _default_business_user_state() -> dict[str, Any]:
    return {
        "cash": float(BUSINESS_STARTER_CASH),
        "portfolio": {},
        "commodity_portfolio": {},
        "crypto_portfolio": {},
        "properties": [],
        "business_ids": [],
        "loans": [],
        "daily": {"day": "", "streak": 0},
        "income_total": 0.0,
        "weekly_income": 0.0,
        "weekly_realized_gains_short": 0.0,
        "weekly_realized_gains_long": 0.0,
        "tax_liability": 0.0,
        "taxes_paid_total": 0.0,
        "realized_pnl": {},
        "salary_tier": 1,
        "credit_score": 650,
        "last_networth": float(BUSINESS_STARTER_CASH),
        "cooldowns": {},
        "flags": {"trade_limited": False},
        "frozen": False,
        "created_ts": time.time(),
    }


def _default_stock_catalog() -> dict[str, dict[str, Any]]:
    stocks: dict[str, dict[str, Any]] = {}
    selected = BUSINESS_SYMBOL_POOL[: max(6, min(BUSINESS_STOCK_COUNT, len(BUSINESS_SYMBOL_POOL)))]
    for idx, (symbol, name, sector) in enumerate(selected):
        base_price = round(85 + (idx * 11.7) + random.uniform(-14, 18), 2)
        stocks[symbol] = {
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "price": max(8.0, base_price),
            "volatility": round(0.010 + random.random() * 0.02, 4),
            "trend": round(random.uniform(-0.004, 0.004), 4),
            "history": [max(8.0, base_price)],
        }
    return stocks


def _default_commodity_catalog() -> dict[str, dict[str, Any]]:
    assets: dict[str, dict[str, Any]] = {}
    for symbol, name, sector, base_price, base_vol in BUSINESS_COMMODITY_POOL:
        price = round(base_price * random.uniform(0.90, 1.12), 2)
        assets[symbol] = {
            "symbol": symbol,
            "name": name,
            "sector": sector,
            "price": max(1.0, price),
            "volatility": round(max(0.006, base_vol + random.uniform(-0.003, 0.004)), 4),
            "trend": round(random.uniform(-0.0035, 0.0035), 4),
            "history": [max(1.0, price)],
        }
    return assets


def _default_crypto_catalog() -> dict[str, dict[str, Any]]:
    assets: dict[str, dict[str, Any]] = {}
    for symbol, name, base_price, base_vol in BUSINESS_CRYPTO_POOL:
        price = round(base_price * random.uniform(0.78, 1.25), 2)
        assets[symbol] = {
            "symbol": symbol,
            "name": name,
            "sector": "crypto",
            "price": max(0.5, price),
            "volatility": round(max(0.018, base_vol + random.uniform(-0.01, 0.015)), 4),
            "trend": round(random.uniform(-0.01, 0.01), 4),
            "history": [max(0.5, price)],
        }
    return assets


def _default_business_profiles() -> dict[str, dict[str, float]]:
    return {
        "restaurant": {"revenue": 2600.0, "payroll": 320.0, "maintenance": 190.0, "expand_cost": 7800.0},
        "tech": {"revenue": 3300.0, "payroll": 420.0, "maintenance": 220.0, "expand_cost": 9200.0},
        "retail": {"revenue": 2400.0, "payroll": 280.0, "maintenance": 170.0, "expand_cost": 7000.0},
        "studio": {"revenue": 2100.0, "payroll": 250.0, "maintenance": 160.0, "expand_cost": 6400.0},
        "logistics": {"revenue": 3600.0, "payroll": 540.0, "maintenance": 260.0, "expand_cost": 10400.0},
        "farm": {"revenue": 1900.0, "payroll": 220.0, "maintenance": 140.0, "expand_cost": 5900.0},
    }


def _default_income_tax_brackets() -> list[dict[str, Any]]:
    return [
        {"up_to": 5000.0, "rate": 0.00},
        {"up_to": 25000.0, "rate": 0.08},
        {"up_to": 80000.0, "rate": 0.15},
        {"up_to": 200000.0, "rate": 0.24},
        {"up_to": None, "rate": 0.32},
    ]


def _default_plot_catalog() -> dict[str, dict[str, Any]]:
    zones: list[tuple[str, int, float]] = [
        ("urban", 12, 76000.0),
        ("suburban", 12, 46000.0),
        ("rural", 12, 23000.0),
    ]
    plots: dict[str, dict[str, Any]] = {}
    index = 1
    for zone, count, base in zones:
        for _ in range(count):
            plot_id = f"P{index:03d}"
            price = round(base * random.uniform(0.85, 1.18), 2)
            plots[plot_id] = {
                "id": plot_id,
                "zone": zone,
                "base_price": price,
                "owner_id": None,
                "tier": 0,
                "listed_price": None,
                "auction_lock": None,
            }
            index += 1
    return plots


def _default_business_state() -> dict[str, Any]:
    return {
        "schema_version": int(BUSINESS_SCHEMA_VERSION),
        "users": {},
        "market": {
            "stocks": _default_stock_catalog(),
            "history": [],
            "active_event": None,
            "last_news": "Markets opened steady.",
        },
        "commodities": {
            "assets": _default_commodity_catalog(),
            "history": [],
            "last_news": "Commodity desk opened steady.",
        },
        "crypto": {
            "assets": _default_crypto_catalog(),
            "history": [],
            "last_news": "Crypto book opened volatile.",
        },
        "real_estate": {
            "plots": _default_plot_catalog(),
            "listed_properties": {},
        },
        "businesses": {
            "profiles": _default_business_profiles(),
            "registry": {},
        },
        "auctions": {"active": {}},
        "trades": {"open": {}},
        "ledger": [],
        "tax": {
            "income_tax_enabled": bool(BUSINESS_INCOME_TAX_ENABLED),
            "income_brackets": _default_income_tax_brackets(),
            "capital_gains_short_rate": float(BUSINESS_CAPITAL_GAINS_SHORT_RATE),
            "capital_gains_long_rate": float(BUSINESS_CAPITAL_GAINS_LONG_RATE),
            "last_weekly_cycle_key": "",
        },
        "credit": {
            "min_score": 500,
            "max_score": 850,
        },
        "market_halts": {
            "assets": {},
            "market": {"remaining_ticks": 0, "reason": "", "triggered_ts": 0.0},
            "last_index_value": 0.0,
        },
        "governance": {
            "transaction_fee_rate": float(BUSINESS_TRANSACTION_FEE_RATE),
            "property_tax_rate": float(BUSINESS_PROPERTY_TAX_RATE),
            "property_maintenance_rate": float(BUSINESS_PROPERTY_MAINTENANCE_RATE),
            "market_paused": False,
            "frozen_users": [],
        },
        "meta": {
            "next_ids": {
                "tx": 1,
                "loan": 1,
                "trade": 1,
                "auction": 1,
                "biz": 1,
            },
            "last_tick_hour_key": "",
            "last_market_tick_key": "",
            "last_world_event_tick_key": "",
            "last_weekly_cycle_key": "",
            "last_tick_ts": 0.0,
            "event_count_day_key": "",
            "event_count_today": 0,
        },
    }


def _sanitize_business_state(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    base = _default_business_state()
    for key in (
        "schema_version",
        "users",
        "market",
        "commodities",
        "crypto",
        "real_estate",
        "businesses",
        "auctions",
        "trades",
        "ledger",
        "tax",
        "credit",
        "market_halts",
        "governance",
        "meta",
    ):
        if key not in payload:
            payload[key] = base[key]

    if not isinstance(payload["users"], dict):
        payload["users"] = {}
    if not isinstance(payload["market"], dict):
        payload["market"] = base["market"]
    if not isinstance(payload["market"].get("stocks"), dict) or not payload["market"]["stocks"]:
        payload["market"]["stocks"] = base["market"]["stocks"]
    if not isinstance(payload["market"].get("history"), list):
        payload["market"]["history"] = []
    if not isinstance(payload["commodities"], dict):
        payload["commodities"] = base["commodities"]
    if not isinstance(payload["commodities"].get("assets"), dict) or not payload["commodities"]["assets"]:
        payload["commodities"]["assets"] = base["commodities"]["assets"]
    if not isinstance(payload["commodities"].get("history"), list):
        payload["commodities"]["history"] = []
    if not isinstance(payload["crypto"], dict):
        payload["crypto"] = base["crypto"]
    if not isinstance(payload["crypto"].get("assets"), dict) or not payload["crypto"]["assets"]:
        payload["crypto"]["assets"] = base["crypto"]["assets"]
    if not isinstance(payload["crypto"].get("history"), list):
        payload["crypto"]["history"] = []
    if not isinstance(payload["real_estate"], dict):
        payload["real_estate"] = base["real_estate"]
    if not isinstance(payload["real_estate"].get("plots"), dict) or not payload["real_estate"]["plots"]:
        payload["real_estate"]["plots"] = base["real_estate"]["plots"]
    if not isinstance(payload["real_estate"].get("listed_properties"), dict):
        payload["real_estate"]["listed_properties"] = {}
    if not isinstance(payload["businesses"], dict):
        payload["businesses"] = base["businesses"]
    if not isinstance(payload["businesses"].get("profiles"), dict):
        payload["businesses"]["profiles"] = base["businesses"]["profiles"]
    if not isinstance(payload["businesses"].get("registry"), dict):
        payload["businesses"]["registry"] = {}
    if not isinstance(payload["auctions"], dict):
        payload["auctions"] = {"active": {}}
    if not isinstance(payload["auctions"].get("active"), dict):
        payload["auctions"]["active"] = {}
    if not isinstance(payload["trades"], dict):
        payload["trades"] = {"open": {}}
    if not isinstance(payload["trades"].get("open"), dict):
        payload["trades"]["open"] = {}
    if not isinstance(payload["ledger"], list):
        payload["ledger"] = []
    if not isinstance(payload["tax"], dict):
        payload["tax"] = base["tax"]
    if not isinstance(payload["tax"].get("income_brackets"), list):
        payload["tax"]["income_brackets"] = base["tax"]["income_brackets"]
    if not isinstance(payload["credit"], dict):
        payload["credit"] = base["credit"]
    for key, default_value in base["credit"].items():
        if key not in payload["credit"]:
            payload["credit"][key] = default_value
    if not isinstance(payload["market_halts"], dict):
        payload["market_halts"] = base["market_halts"]
    if not isinstance(payload["market_halts"].get("assets"), dict):
        payload["market_halts"]["assets"] = {}
    if not isinstance(payload["market_halts"].get("market"), dict):
        payload["market_halts"]["market"] = base["market_halts"]["market"]
    if "last_index_value" not in payload["market_halts"]:
        payload["market_halts"]["last_index_value"] = 0.0
    if not isinstance(payload["governance"], dict):
        payload["governance"] = base["governance"]
    governance = payload["governance"]
    for key, default_value in base["governance"].items():
        if key not in governance:
            governance[key] = default_value
    if not isinstance(governance.get("frozen_users"), list):
        governance["frozen_users"] = []
    if not isinstance(payload["meta"], dict):
        payload["meta"] = base["meta"]
    meta = payload["meta"]
    if not isinstance(meta.get("next_ids"), dict):
        meta["next_ids"] = base["meta"]["next_ids"]
    for key, default_value in base["meta"]["next_ids"].items():
        if key not in meta["next_ids"]:
            meta["next_ids"][key] = default_value
    if "last_tick_hour_key" not in meta:
        meta["last_tick_hour_key"] = ""
    if "last_market_tick_key" not in meta:
        meta["last_market_tick_key"] = ""
    if "last_world_event_tick_key" not in meta:
        meta["last_world_event_tick_key"] = ""
    if "last_weekly_cycle_key" not in meta:
        meta["last_weekly_cycle_key"] = ""
    if "last_tick_ts" not in meta:
        meta["last_tick_ts"] = 0.0
    if "event_count_day_key" not in meta:
        meta["event_count_day_key"] = ""
    if "event_count_today" not in meta:
        meta["event_count_today"] = 0

    defaults = _default_business_user_state()
    for user_key, user in list(payload["users"].items()):
        if not isinstance(user, dict):
            payload["users"][user_key] = _default_business_user_state()
            continue
        for field, default_value in defaults.items():
            if field not in user:
                user[field] = default_value
        if not isinstance(user.get("portfolio"), dict):
            user["portfolio"] = {}
        if not isinstance(user.get("commodity_portfolio"), dict):
            user["commodity_portfolio"] = {}
        if not isinstance(user.get("crypto_portfolio"), dict):
            user["crypto_portfolio"] = {}
        if not isinstance(user.get("properties"), list):
            user["properties"] = []
        if not isinstance(user.get("business_ids"), list):
            user["business_ids"] = []
        if not isinstance(user.get("loans"), list):
            user["loans"] = []
        if not isinstance(user.get("daily"), dict):
            user["daily"] = {"day": "", "streak": 0}
        if not isinstance(user.get("flags"), dict):
            user["flags"] = {"trade_limited": False}
        if not isinstance(user.get("cooldowns"), dict):
            user["cooldowns"] = {}
        if not isinstance(user.get("realized_pnl"), dict):
            user["realized_pnl"] = {}
        user["credit_score"] = int(max(500, min(850, int(user.get("credit_score", 650) or 650))))

    try:
        current_schema = int(payload.get("schema_version", 1) or 1)
    except (TypeError, ValueError):
        current_schema = 1
    payload["schema_version"] = int(max(BUSINESS_SCHEMA_VERSION, current_schema))
    return payload


def load_business_state() -> None:
    global BUSINESS_STATE, BUSINESS_STATE_DIRTY
    payload = read_state(BUSINESS_STATE_KEY)
    BUSINESS_STATE = _sanitize_business_state(payload)
    BUSINESS_STATE_DIRTY = False


def _mark_business_dirty() -> None:
    global BUSINESS_STATE_DIRTY
    BUSINESS_STATE_DIRTY = True


async def flush_business_state(force: bool = False) -> None:
    global BUSINESS_STATE_DIRTY
    if not force and not BUSINESS_STATE_DIRTY:
        return
    async with BUSINESS_STATE_LOCK:
        if not force and not BUSINESS_STATE_DIRTY:
            return
        try:
            persisted = write_state(BUSINESS_STATE_KEY, BUSINESS_STATE)
            if persisted:
                BUSINESS_STATE_DIRTY = False
        except Exception:
            pass


def get_business_state() -> dict[str, Any]:
    global BUSINESS_STATE
    if not BUSINESS_STATE:
        BUSINESS_STATE = _default_business_state()
        _mark_business_dirty()
    BUSINESS_STATE = _sanitize_business_state(BUSINESS_STATE)
    return BUSINESS_STATE


def _business_next_id(namespace: str) -> str:
    state = get_business_state()
    meta = state["meta"]["next_ids"]
    current = int(meta.get(namespace, 1))
    meta[namespace] = current + 1
    _mark_business_dirty()
    prefix = {
        "tx": "TX",
        "loan": "LN",
        "trade": "TRD",
        "auction": "AUC",
        "biz": "BIZ",
    }.get(namespace, "ID")
    return f"{prefix}-{current:06d}"


def _business_money(value: float) -> str:
    return f"{value:,.0f}"


def _business_now_ts() -> float:
    return time.time()


def _business_hour_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")


def _business_clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _business_get_ai_dynamic(state: dict[str, Any] | None = None) -> dict[str, Any]:
    root = state or get_business_state()
    governance = root.get("governance", {})
    dynamic = governance.get("ai_dynamic", {})
    if not isinstance(dynamic, dict):
        dynamic = {}
        governance["ai_dynamic"] = dynamic
    return dynamic


def _extract_first_json_object(raw_text: str) -> dict[str, Any] | None:
    text = (raw_text or "").strip()
    if not text:
        return None
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    candidate = match.group(0).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _build_business_local_tip(user_id: int) -> str:
    user = _business_get_user(user_id)
    cash = float(user.get("cash", 0.0))
    debt = _business_debt_total(user)
    stock_value = _business_portfolio_value(user)
    property_value = _business_property_value(user)
    if debt > max(5000.0, cash * 0.8):
        return "Advisor: prioritize debt repayment this cycle; keep at least 20% cash buffer before new buys."
    if cash < max(5000.0, (stock_value + property_value) * 0.08):
        return "Advisor: you're asset-heavy with low liquidity. Hold a stronger cash buffer before upgrading properties."
    if property_value <= 0 and stock_value <= 0:
        return "Advisor: start with a diversified base, e.g., one low-volatility stock and one suburban plot."
    if property_value > stock_value * 2.5:
        return "Advisor: rebalance a little into stocks to reduce vacancy and maintenance risk concentration."
    return "Advisor: stable position. Scale gradually and avoid single-asset exposure spikes."


async def _business_get_personalized_tip(
    guild_id: int,
    user_id: int,
    *,
    context: str,
) -> str:
    if not BUSINESS_AI_PERSONALIZATION_ENABLED or not is_ai_configured():
        return _build_business_local_tip(user_id)

    cache_key = ("biz_tip", guild_id, user_id)
    cached = BUSINESS_AI_TEXT_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < BUSINESS_AI_PERSONALIZATION_CACHE_SECONDS:
        return cached[1]

    user = _business_get_user(user_id)
    cash = float(user.get("cash", 0.0))
    debt = _business_debt_total(user)
    stock_value = _business_portfolio_value(user)
    property_value = _business_property_value(user)
    net = _business_networth(user_id)
    flags = user.get("flags", {}) if isinstance(user.get("flags"), dict) else {}
    market_news = str(get_business_state().get("market", {}).get("last_news", ""))
    prompt = (
        "Generate one short personalized advisor line for a Discord business game player.\n"
        "Rules: <= 26 words, specific and practical, fun tone, no generic fluff.\n"
        "Do not mention being an AI. No markdown.\n\n"
        f"Context: {context}\n"
        f"Cash: {cash:.2f}\n"
        f"Debt: {debt:.2f}\n"
        f"Stock value: {stock_value:.2f}\n"
        f"Property value: {property_value:.2f}\n"
        f"Net worth: {net:.2f}\n"
        f"Flags: {flags}\n"
        f"Market: {market_news[:180]}"
    )
    try:
        tip = await request_fun_ai(
            prompt,
            max_tokens=BUSINESS_AI_MAX_TOKENS,
            temperature=0.7,
            policy_key="business_tip",
            fun_mode=get_guild_fun_mode(guild_id),
        )
        tip = " ".join(str(tip).split()).strip()
        if not tip:
            raise RuntimeError("empty tip")
    except Exception:
        tip = _build_business_local_tip(user_id)

    BUSINESS_AI_TEXT_CACHE[cache_key] = (now, tip)
    if len(BUSINESS_AI_TEXT_CACHE) > 700:
        oldest = sorted(BUSINESS_AI_TEXT_CACHE.items(), key=lambda kv: kv[1][0])[:140]
        for key, _ in oldest:
            BUSINESS_AI_TEXT_CACHE.pop(key, None)
    return tip


async def _business_refresh_ai_dynamic() -> dict[str, Any] | None:
    if not BUSINESS_AI_TUNING_ENABLED or not is_ai_configured():
        return None

    now_ts = _business_now_ts()
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        dynamic = dict(_business_get_ai_dynamic(state))
        last_update = float(dynamic.get("updated_ts", 0.0) or 0.0)
        if now_ts - last_update < (BUSINESS_AI_DIRECTOR_INTERVAL_HOURS * 3600):
            return dynamic
        stocks = dict(state.get("market", {}).get("stocks", {}))
        last_news = str(state.get("market", {}).get("last_news", ""))[:180]

    sector_changes: dict[str, list[float]] = defaultdict(list)
    mover_lines: list[str] = []
    for symbol, row in stocks.items():
        if not isinstance(row, dict):
            continue
        history = row.get("history", [])
        if not isinstance(history, list) or len(history) < 2:
            continue
        prev = float(history[-2] or 0.0)
        curr = float(history[-1] or 0.0)
        if prev <= 0:
            continue
        change = (curr - prev) / prev
        sector = str(row.get("sector", "other"))
        sector_changes[sector].append(change)
        mover_lines.append(f"{symbol}:{change:+.3f}")
    mover_lines = mover_lines[:18]
    sector_summary = {
        sector: (sum(values) / max(1, len(values)))
        for sector, values in sector_changes.items()
    }

    prompt = (
        "You are an economy director for a Discord business sim.\n"
        "Return STRICT JSON only with keys:\n"
        "headline (string <= 70 chars), market_bias (-0.03..0.03), event_chance_shift (-0.08..0.08),\n"
        "transaction_fee_shift (-0.002..0.002), property_tax_shift (-0.002..0.002),\n"
        "maintenance_shift (-0.002..0.002), daily_claim_shift_pct (-0.25..0.25),\n"
        "sector_bias (object mapping sector to -0.03..0.03).\n"
        "Goal: make gameplay fun, varied, and fair.\n\n"
        f"Current market news: {last_news}\n"
        f"Recent movers: {', '.join(mover_lines) if mover_lines else 'none'}\n"
        f"Sector summary: {json.dumps(sector_summary)[:320]}\n"
    )

    try:
        raw = await request_ai_completion(
            [{"role": "user", "content": prompt}],
            max_tokens=max(140, BUSINESS_AI_MAX_TOKENS + 60),
            temperature=0.55,
            policy_key="business_director",
        )
    except Exception:
        return dynamic

    payload = _extract_first_json_object(raw)
    if payload is None:
        return dynamic

    parsed_sector_bias: dict[str, float] = {}
    raw_sector_bias = payload.get("sector_bias", {})
    if isinstance(raw_sector_bias, dict):
        for key, value in raw_sector_bias.items():
            try:
                parsed_sector_bias[str(key).lower()] = _business_clamp_float(float(value), -0.03, 0.03)
            except (TypeError, ValueError):
                continue

    updated = {
        "headline": str(payload.get("headline", "Market mood shifted")).strip()[:70],
        "market_bias": _business_clamp_float(float(payload.get("market_bias", 0.0) or 0.0), -0.03, 0.03),
        "event_chance_shift": _business_clamp_float(
            float(payload.get("event_chance_shift", 0.0) or 0.0), -0.08, 0.08
        ),
        "transaction_fee_shift": _business_clamp_float(
            float(payload.get("transaction_fee_shift", 0.0) or 0.0), -0.002, 0.002
        ),
        "property_tax_shift": _business_clamp_float(
            float(payload.get("property_tax_shift", 0.0) or 0.0), -0.002, 0.002
        ),
        "maintenance_shift": _business_clamp_float(
            float(payload.get("maintenance_shift", 0.0) or 0.0), -0.002, 0.002
        ),
        "daily_claim_shift_pct": _business_clamp_float(
            float(payload.get("daily_claim_shift_pct", 0.0) or 0.0), -0.25, 0.25
        ),
        "sector_bias": parsed_sector_bias,
        "updated_ts": now_ts,
    }
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        state["governance"]["ai_dynamic"] = updated
        _mark_business_dirty()
    return updated


def _business_get_user(user_id: int) -> dict[str, Any]:
    state = get_business_state()
    users = state["users"]
    key = str(user_id)
    user = users.get(key)
    if not isinstance(user, dict):
        user = _default_business_user_state()
        users[key] = user
        _mark_business_dirty()
    defaults = _default_business_user_state()
    for field, default_value in defaults.items():
        if field not in user:
            user[field] = default_value
    if not isinstance(user.get("portfolio"), dict):
        user["portfolio"] = {}
    if not isinstance(user.get("commodity_portfolio"), dict):
        user["commodity_portfolio"] = {}
    if not isinstance(user.get("crypto_portfolio"), dict):
        user["crypto_portfolio"] = {}
    if not isinstance(user.get("properties"), list):
        user["properties"] = []
    if not isinstance(user.get("business_ids"), list):
        user["business_ids"] = []
    if not isinstance(user.get("loans"), list):
        user["loans"] = []
    if not isinstance(user.get("daily"), dict):
        user["daily"] = {"day": "", "streak": 0}
    if not isinstance(user.get("flags"), dict):
        user["flags"] = {"trade_limited": False}
    else:
        user["flags"].setdefault("trade_limited", False)
    if not isinstance(user.get("cooldowns"), dict):
        user["cooldowns"] = {}
    if not isinstance(user.get("realized_pnl"), dict):
        user["realized_pnl"] = {}
    user["credit_score"] = int(max(500, min(850, int(user.get("credit_score", 650) or 650))))
    user["tax_liability"] = float(user.get("tax_liability", 0.0) or 0.0)
    user["weekly_income"] = float(user.get("weekly_income", 0.0) or 0.0)
    user["weekly_realized_gains_short"] = float(user.get("weekly_realized_gains_short", 0.0) or 0.0)
    user["weekly_realized_gains_long"] = float(user.get("weekly_realized_gains_long", 0.0) or 0.0)
    user["salary_tier"] = max(1, int(user.get("salary_tier", 1) or 1))
    return user


def _business_is_user_frozen(user_id: int) -> bool:
    state = get_business_state()
    user = _business_get_user(user_id)
    if bool(user.get("frozen")):
        return True
    frozen_users = state["governance"].get("frozen_users", [])
    return str(user_id) in {str(v) for v in frozen_users}


def _business_set_user_frozen(user_id: int, frozen: bool) -> None:
    state = get_business_state()
    user = _business_get_user(user_id)
    user["frozen"] = bool(frozen)
    frozen_users = {str(v) for v in state["governance"].get("frozen_users", [])}
    if frozen:
        frozen_users.add(str(user_id))
    else:
        frozen_users.discard(str(user_id))
    state["governance"]["frozen_users"] = sorted(frozen_users)
    _mark_business_dirty()


def _business_get_stock(symbol: str) -> dict[str, Any] | None:
    return _business_get_asset("stock", symbol)


def _business_holding_field(asset_type: str) -> str | None:
    normalized = asset_type.strip().lower()
    if normalized == "stock":
        return "portfolio"
    if normalized == "commodity":
        return "commodity_portfolio"
    if normalized == "crypto":
        return "crypto_portfolio"
    return None


def _business_get_asset_book(asset_type: str) -> dict[str, dict[str, Any]]:
    state = get_business_state()
    normalized = asset_type.strip().lower()
    if normalized == "stock":
        return state["market"]["stocks"]
    if normalized == "commodity":
        return state.get("commodities", {}).get("assets", {})
    if normalized == "crypto":
        return state.get("crypto", {}).get("assets", {})
    return {}


def _business_get_asset(asset_type: str, symbol: str) -> dict[str, Any] | None:
    return _business_get_asset_book(asset_type).get(symbol.upper())


def _business_resolve_trade_asset(token: str) -> tuple[str | None, str | None]:
    normalized_token = token.strip().upper()
    if not normalized_token:
        return None, None
    token_clean = re.sub(r"[^a-z0-9]", "", token.strip().lower())
    for asset_type in ("stock", "commodity", "crypto"):
        if asset_type == "commodity" and not BUSINESS_ENABLE_COMMODITIES:
            continue
        if asset_type == "crypto" and not BUSINESS_ENABLE_CRYPTO:
            continue
        book = _business_get_asset_book(asset_type)
        if normalized_token in book:
            return asset_type, normalized_token
        for symbol, row in book.items():
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", "")).lower()
            compact_name = re.sub(r"[^a-z0-9]", "", name)
            if token_clean and (token_clean == compact_name or token_clean in compact_name):
                return asset_type, str(symbol).upper()
            if token_clean and token_clean == str(symbol).lower():
                return asset_type, str(symbol).upper()
    return None, None


def _business_plot_value(plot: dict[str, Any]) -> float:
    base = float(plot.get("base_price", 0.0) or 0.0)
    tier = int(plot.get("tier", 0) or 0)
    return max(0.0, base * (1 + (tier * 0.35)))


def _business_portfolio_value(user: dict[str, Any]) -> float:
    return _business_asset_portfolio_value(user, "stock")


def _business_asset_portfolio_value(user: dict[str, Any], asset_type: str) -> float:
    total = 0.0
    field = _business_holding_field(asset_type)
    if field is None:
        return 0.0
    portfolio = user.get(field, {})
    if not isinstance(portfolio, dict):
        return 0.0
    for symbol, holding in portfolio.items():
        if not isinstance(holding, dict):
            continue
        qty = max(0, int(holding.get("qty", 0)))
        asset = _business_get_asset(asset_type, str(symbol))
        if qty <= 0 or asset is None:
            continue
        total += qty * float(asset.get("price", 0.0))
    return total


def _business_property_value(user: dict[str, Any]) -> float:
    state = get_business_state()
    plots = state["real_estate"]["plots"]
    total = 0.0
    for plot_id in user.get("properties", []):
        plot = plots.get(str(plot_id))
        if not isinstance(plot, dict):
            continue
        total += _business_plot_value(plot)
    return total


def _business_debt_total(user: dict[str, Any]) -> float:
    debt = 0.0
    for loan in user.get("loans", []):
        if not isinstance(loan, dict):
            continue
        if str(loan.get("status", "active")) in {"paid", "closed"}:
            continue
        debt += max(0.0, float(loan.get("balance", 0.0)))
    return debt


def _business_business_equity_value(user: dict[str, Any]) -> float:
    state = get_business_state()
    registry = state.get("businesses", {}).get("registry", {})
    if not isinstance(registry, dict):
        return 0.0
    total = 0.0
    for biz_id in list(user.get("business_ids", [])):
        biz = registry.get(str(biz_id))
        if not isinstance(biz, dict):
            continue
        if str(biz.get("status", "active")) != "active":
            continue
        level = max(1, int(biz.get("level", 1) or 1))
        employees = max(0, int(biz.get("employees", 0) or 0))
        base = float(biz.get("base_value", 0.0) or 0.0)
        debt = max(0.0, float(biz.get("debt", 0.0) or 0.0))
        total += max(0.0, (base * (1 + ((level - 1) * 0.45))) + (employees * 420.0) - debt)
    return total


def _business_progressive_income_tax(income: float) -> float:
    if income <= 0:
        return 0.0
    state = get_business_state()
    tax = state.get("tax", {})
    if not isinstance(tax, dict) or not bool(tax.get("income_tax_enabled", BUSINESS_INCOME_TAX_ENABLED)):
        return 0.0
    brackets = tax.get("income_brackets", [])
    if not isinstance(brackets, list) or not brackets:
        brackets = _default_income_tax_brackets()
    remaining = float(income)
    last_limit = 0.0
    owed = 0.0
    for bracket in brackets:
        if not isinstance(bracket, dict):
            continue
        up_to = bracket.get("up_to")
        rate = _business_clamp_float(float(bracket.get("rate", 0.0) or 0.0), 0.0, 0.8)
        if up_to is None:
            owed += max(0.0, remaining) * rate
            remaining = 0.0
            break
        try:
            cap = float(up_to)
        except (TypeError, ValueError):
            continue
        if cap <= last_limit:
            continue
        slab = min(max(0.0, remaining), max(0.0, cap - last_limit))
        owed += slab * rate
        remaining -= slab
        last_limit = cap
        if remaining <= 0:
            break
    return max(0.0, owed)


def _business_capital_gains_rate(held_seconds: float) -> float:
    state = get_business_state()
    tax = state.get("tax", {})
    short_rate = _business_clamp_float(
        float(tax.get("capital_gains_short_rate", BUSINESS_CAPITAL_GAINS_SHORT_RATE) or BUSINESS_CAPITAL_GAINS_SHORT_RATE),
        0.0,
        0.8,
    )
    long_rate = _business_clamp_float(
        float(tax.get("capital_gains_long_rate", BUSINESS_CAPITAL_GAINS_LONG_RATE) or BUSINESS_CAPITAL_GAINS_LONG_RATE),
        0.0,
        0.8,
    )
    long_hold_seconds = float(BUSINESS_CAPITAL_GAINS_LONG_HOLD_DAYS) * 24 * 3600
    return long_rate if held_seconds >= long_hold_seconds else short_rate


def _business_apply_credit_score_delta(user: dict[str, Any], delta: int) -> None:
    current = int(user.get("credit_score", 650) or 650)
    user["credit_score"] = int(max(500, min(850, current + int(delta))))


def _business_networth(user_id: int) -> float:
    user = _business_get_user(user_id)
    cash = max(0.0, float(user.get("cash", 0.0)))
    portfolio = _business_portfolio_value(user)
    commodities = _business_asset_portfolio_value(user, "commodity")
    crypto = _business_asset_portfolio_value(user, "crypto")
    properties = _business_property_value(user)
    businesses = _business_business_equity_value(user)
    debt = _business_debt_total(user)
    net = cash + portfolio + commodities + crypto + properties + businesses - debt
    user["last_networth"] = float(net)
    return float(net)


def _business_rates_for_guild(guild_id: int | None = None) -> dict[str, float]:
    state = get_business_state()
    governance = state.get("governance", {})
    dynamic = _business_get_ai_dynamic(state)
    rates = {
        "transaction_fee_rate": float(governance.get("transaction_fee_rate", BUSINESS_TRANSACTION_FEE_RATE))
        + float(dynamic.get("transaction_fee_shift", 0.0) or 0.0),
        "property_tax_rate": float(governance.get("property_tax_rate", BUSINESS_PROPERTY_TAX_RATE))
        + float(dynamic.get("property_tax_shift", 0.0) or 0.0),
        "property_maintenance_rate": float(
            governance.get("property_maintenance_rate", BUSINESS_PROPERTY_MAINTENANCE_RATE)
        ),
    }
    rates["property_maintenance_rate"] += float(dynamic.get("maintenance_shift", 0.0) or 0.0)
    if guild_id is not None:
        overrides = get_guild_business_tax_overrides(guild_id)
        for key, value in overrides.items():
            rates[key] = max(0.0, float(value))
    rates["transaction_fee_rate"] = _business_clamp_float(rates["transaction_fee_rate"], 0.0, 0.25)
    rates["property_tax_rate"] = _business_clamp_float(rates["property_tax_rate"], 0.0, 0.25)
    rates["property_maintenance_rate"] = _business_clamp_float(
        rates["property_maintenance_rate"], 0.0, 0.25
    )
    return rates


def _business_market_paused(guild_id: int | None = None) -> bool:
    state = get_business_state()
    global_pause = bool(state.get("governance", {}).get("market_paused", False))
    if guild_id is None:
        return global_pause
    return global_pause or get_guild_business_market_paused(guild_id)


def _business_add_ledger_entry(
    *,
    action: str,
    user_id: int | None = None,
    amount: float = 0.0,
    details: dict[str, Any] | None = None,
    rollback: dict[str, Any] | None = None,
) -> str:
    state = get_business_state()
    tx_id = _business_next_id("tx")
    entry = {
        "id": tx_id,
        "ts": _business_now_ts(),
        "action": action,
        "user_id": user_id,
        "amount": float(amount),
        "details": details or {},
    }
    ledger = state["ledger"]
    ledger.append(entry)
    if len(ledger) > BUSINESS_LEDGER_MAX_ENTRIES:
        overflow = len(ledger) - BUSINESS_LEDGER_MAX_ENTRIES
        del ledger[:overflow]
    if rollback:
        BUSINESS_TX_ROLLBACK_CACHE[tx_id] = rollback
        if len(BUSINESS_TX_ROLLBACK_CACHE) > 1500:
            oldest = sorted(BUSINESS_TX_ROLLBACK_CACHE.keys())[:250]
            for key in oldest:
                BUSINESS_TX_ROLLBACK_CACHE.pop(key, None)
    _mark_business_dirty()
    return tx_id


def _business_add_stock_to_user(user: dict[str, Any], symbol: str, qty: int, total_cost: float) -> None:
    _business_add_asset_to_user(user, "stock", symbol, qty, total_cost)


def _business_add_asset_to_user(
    user: dict[str, Any],
    asset_type: str,
    symbol: str,
    qty: int,
    total_cost: float,
) -> None:
    if qty <= 0:
        return
    field = _business_holding_field(asset_type)
    if field is None:
        return
    portfolio = user.setdefault(field, {})
    if not isinstance(portfolio, dict):
        portfolio = {}
        user[field] = portfolio
    normalized_symbol = symbol.upper().strip()
    holding = portfolio.get(normalized_symbol)
    if not isinstance(holding, dict):
        holding = {"qty": 0, "avg_cost": 0.0, "first_bought_ts": _business_now_ts(), "realized_pnl": 0.0}
        portfolio[normalized_symbol] = holding
    old_qty = max(0, int(holding.get("qty", 0)))
    old_avg = max(0.0, float(holding.get("avg_cost", 0.0)))
    new_qty = old_qty + qty
    if new_qty <= 0:
        holding["qty"] = 0
        holding["avg_cost"] = 0.0
        return
    old_total = old_qty * old_avg
    holding["qty"] = int(new_qty)
    holding["avg_cost"] = float((old_total + max(0.0, total_cost)) / new_qty)
    if old_qty <= 0:
        holding["first_bought_ts"] = _business_now_ts()
    if "realized_pnl" not in holding:
        holding["realized_pnl"] = 0.0


def _business_remove_stock_from_user(user: dict[str, Any], symbol: str, qty: int) -> bool:
    return _business_remove_asset_from_user(user, "stock", symbol, qty)


def _business_remove_asset_from_user(
    user: dict[str, Any],
    asset_type: str,
    symbol: str,
    qty: int,
) -> bool:
    if qty <= 0:
        return False
    field = _business_holding_field(asset_type)
    if field is None:
        return False
    portfolio = user.setdefault(field, {})
    if not isinstance(portfolio, dict):
        return False
    holding = portfolio.get(symbol.upper().strip())
    if not isinstance(holding, dict):
        return False
    old_qty = int(holding.get("qty", 0))
    if old_qty < qty:
        return False
    new_qty = old_qty - qty
    holding["qty"] = new_qty
    if new_qty <= 0:
        portfolio.pop(symbol.upper().strip(), None)
    return True


def _business_asset_halt_key(asset_type: str, symbol: str) -> str:
    return f"{asset_type.strip().lower()}:{symbol.strip().upper()}"


def _business_market_halt_remaining() -> int:
    state = get_business_state()
    market_halt = state.get("market_halts", {}).get("market", {})
    if not isinstance(market_halt, dict):
        return 0
    return max(0, int(market_halt.get("remaining_ticks", 0) or 0))


def _business_is_market_halted() -> bool:
    return _business_market_halt_remaining() > 0


def _business_is_asset_halted(asset_type: str, symbol: str) -> bool:
    state = get_business_state()
    halts = state.get("market_halts", {}).get("assets", {})
    if not isinstance(halts, dict):
        return False
    row = halts.get(_business_asset_halt_key(asset_type, symbol))
    if not isinstance(row, dict):
        return False
    return int(row.get("remaining_ticks", 0) or 0) > 0


def _business_register_asset_halt(asset_type: str, symbol: str, *, reason: str) -> None:
    state = get_business_state()
    market_halts = state.setdefault("market_halts", {})
    halts = market_halts.setdefault("assets", {})
    halts[_business_asset_halt_key(asset_type, symbol)] = {
        "remaining_ticks": 2,
        "reason": reason[:120],
        "triggered_ts": _business_now_ts(),
    }
    _mark_business_dirty()


def _business_register_market_halt(reason: str, *, ticks: int = 1) -> None:
    state = get_business_state()
    market_halts = state.setdefault("market_halts", {})
    market_halt = market_halts.setdefault("market", {})
    market_halt["remaining_ticks"] = max(int(market_halt.get("remaining_ticks", 0) or 0), int(max(1, ticks)))
    market_halt["reason"] = reason[:140]
    market_halt["triggered_ts"] = _business_now_ts()
    _mark_business_dirty()


def _business_decay_halts_each_tick() -> None:
    state = get_business_state()
    market_halts = state.setdefault("market_halts", {})
    changed = False
    assets = market_halts.get("assets", {})
    if isinstance(assets, dict):
        for key in list(assets.keys()):
            row = assets.get(key)
            if not isinstance(row, dict):
                assets.pop(key, None)
                changed = True
                continue
            remaining = int(row.get("remaining_ticks", 0) or 0) - 1
            if remaining <= 0:
                assets.pop(key, None)
            else:
                row["remaining_ticks"] = remaining
            changed = True
    market_halt = market_halts.get("market", {})
    if isinstance(market_halt, dict):
        remaining = int(market_halt.get("remaining_ticks", 0) or 0)
        if remaining > 0:
            market_halt["remaining_ticks"] = max(0, remaining - 1)
            changed = True
    if changed:
        _mark_business_dirty()


def _business_buy_order_spread(asset_type: str) -> float:
    normalized = asset_type.strip().lower()
    if normalized == "crypto":
        return 0.006
    if normalized == "commodity":
        return 0.004
    return 0.003


def _business_sell_order_spread(asset_type: str) -> float:
    return _business_buy_order_spread(asset_type)


def _business_trade_hold_penalty_rate(asset_type: str, held_seconds: float) -> float:
    if held_seconds >= 20 * 60:
        return 0.0
    normalized = asset_type.strip().lower()
    if normalized == "crypto":
        return 0.022
    if normalized == "commodity":
        return 0.016
    return 0.012


def _business_execute_asset_buy(
    *,
    user_id: int,
    guild_id: int | None,
    asset_type: str,
    symbol: str,
    qty: int,
    source: str,
) -> tuple[bool, str, float]:
    normalized_type = asset_type.strip().lower()
    normalized_symbol = symbol.strip().upper()
    if qty < 1:
        return False, "Quantity must be positive.", 0.0
    user = _business_get_user(user_id)
    if bool(user.get("flags", {}).get("trade_limited")):
        return False, "Trading is restricted on your account due to debt stress.", 0.0
    asset_row = _business_get_asset(normalized_type, normalized_symbol)
    if not isinstance(asset_row, dict):
        return False, f"Unknown {normalized_type} symbol `{normalized_symbol}`.", 0.0
    if _business_market_paused(guild_id):
        return False, "Market is currently paused by admins.", 0.0
    if _business_is_market_halted():
        return False, "Market is temporarily halted this tick due to volatility.", 0.0
    if _business_is_asset_halted(normalized_type, normalized_symbol):
        return False, f"`{normalized_symbol}` is temporarily halted this tick.", 0.0

    price = float(asset_row.get("price", 0.0))
    rates = _business_rates_for_guild(guild_id)
    spread = _business_buy_order_spread(normalized_type)
    gross = qty * price * (1 + spread)
    fee = gross * max(0.0, float(rates["transaction_fee_rate"]))
    total = gross + fee
    cash = float(user.get("cash", 0.0))
    if cash < total:
        return False, f"Insufficient cash. Need `{_business_money(total)}`.", 0.0
    net_before = _business_networth(user_id)
    exposure = (qty * price) / max(1.0, net_before)
    if exposure > 0.85:
        return False, "Order rejected: single order exposure too high (>85% of net worth).", 0.0

    user["cash"] = cash - total
    _business_add_asset_to_user(user, normalized_type, normalized_symbol, qty, gross)
    rollback_data = None
    if normalized_type == "stock":
        rollback_data = {
            "type": "stock_buy",
            "user_id": user_id,
            "symbol": normalized_symbol,
            "qty": qty,
            "cash_delta": total,
        }
    _business_add_ledger_entry(
        action=f"{normalized_type}_buy",
        user_id=user_id,
        amount=-total,
        details={"symbol": normalized_symbol, "qty": qty, "price": price, "fee": fee, "source": source},
        rollback=rollback_data,
    )
    _mark_business_dirty()
    return True, f"Bought `{qty}` `{normalized_symbol}`.", total


def _business_execute_asset_sell(
    *,
    user_id: int,
    guild_id: int | None,
    asset_type: str,
    symbol: str,
    qty: int,
    source: str,
) -> tuple[bool, str, float]:
    normalized_type = asset_type.strip().lower()
    normalized_symbol = symbol.strip().upper()
    if qty < 1:
        return False, "Quantity must be positive.", 0.0
    user = _business_get_user(user_id)
    asset_row = _business_get_asset(normalized_type, normalized_symbol)
    if not isinstance(asset_row, dict):
        return False, f"Unknown {normalized_type} symbol `{normalized_symbol}`.", 0.0
    if _business_market_paused(guild_id):
        return False, "Market is currently paused by admins.", 0.0
    if _business_is_market_halted():
        return False, "Market is temporarily halted this tick due to volatility.", 0.0
    if _business_is_asset_halted(normalized_type, normalized_symbol):
        return False, f"`{normalized_symbol}` is temporarily halted this tick.", 0.0

    field = _business_holding_field(normalized_type)
    if field is None:
        return False, "Unsupported asset type.", 0.0
    portfolio = user.get(field, {})
    holding = portfolio.get(normalized_symbol) if isinstance(portfolio, dict) else None
    if not isinstance(holding, dict) or int(holding.get("qty", 0)) < qty:
        return False, f"You do not hold enough `{normalized_symbol}`.", 0.0

    price = float(asset_row.get("price", 0.0))
    rates = _business_rates_for_guild(guild_id)
    spread = _business_sell_order_spread(normalized_type)
    gross = qty * price * (1 - spread)
    fee = gross * max(0.0, float(rates["transaction_fee_rate"]))
    net = max(0.0, gross - fee)
    avg_cost = max(0.0, float(holding.get("avg_cost", 0.0)))
    cost_basis = avg_cost * qty
    gain = max(0.0, gross - cost_basis)
    held_seconds = max(0.0, _business_now_ts() - float(holding.get("first_bought_ts", _business_now_ts())))
    penalty_rate = _business_trade_hold_penalty_rate(normalized_type, held_seconds)
    rapid_flip_penalty = net * penalty_rate
    capital_gains_rate = _business_capital_gains_rate(held_seconds)
    gains_tax = gain * capital_gains_rate if gain > 0 else 0.0

    if not _business_remove_asset_from_user(user, normalized_type, normalized_symbol, qty):
        return False, "Could not execute sell order.", 0.0
    user["cash"] = float(user.get("cash", 0.0)) + max(0.0, net - rapid_flip_penalty)
    if gain > 0:
        user["tax_liability"] = float(user.get("tax_liability", 0.0)) + gains_tax
        if held_seconds >= (BUSINESS_CAPITAL_GAINS_LONG_HOLD_DAYS * 24 * 3600):
            user["weekly_realized_gains_long"] = float(user.get("weekly_realized_gains_long", 0.0)) + gain
        else:
            user["weekly_realized_gains_short"] = float(user.get("weekly_realized_gains_short", 0.0)) + gain
    realized = user.setdefault("realized_pnl", {})
    if isinstance(realized, dict):
        realized_key = f"{normalized_type}:{normalized_symbol}"
        realized[realized_key] = float(realized.get(realized_key, 0.0)) + (
            gross - cost_basis - fee - rapid_flip_penalty
        )
    rollback_data = None
    if normalized_type == "stock":
        rollback_data = {
            "type": "stock_sell",
            "user_id": user_id,
            "symbol": normalized_symbol,
            "qty": qty,
            "cash_delta": -max(0.0, net - rapid_flip_penalty),
        }
    _business_add_ledger_entry(
        action=f"{normalized_type}_sell",
        user_id=user_id,
        amount=max(0.0, net - rapid_flip_penalty),
        details={
            "symbol": normalized_symbol,
            "qty": qty,
            "price": price,
            "fee": fee,
            "rapid_flip_penalty": rapid_flip_penalty,
            "gains_tax_added": gains_tax,
            "source": source,
        },
        rollback=rollback_data,
    )
    _mark_business_dirty()
    return True, f"Sold `{qty}` `{normalized_symbol}`.", max(0.0, net - rapid_flip_penalty)


def _business_user_open_trade_count(user_id: int) -> int:
    state = get_business_state()
    offers = state["trades"]["open"]
    uid = str(user_id)
    count = 0
    for offer in offers.values():
        if not isinstance(offer, dict):
            continue
        if str(offer.get("from_user_id")) == uid or str(offer.get("to_user_id")) == uid:
            count += 1
    return count


def _business_user_open_auction_count(user_id: int) -> int:
    state = get_business_state()
    auctions = state["auctions"]["active"]
    uid = str(user_id)
    count = 0
    for auc in auctions.values():
        if not isinstance(auc, dict):
            continue
        if str(auc.get("seller_id")) == uid:
            count += 1
    return count


def _business_repay_loans_from_cash(user_id: int, amount: float, *, source: str) -> tuple[float, int]:
    if amount <= 0:
        return 0.0, 0
    user = _business_get_user(user_id)
    loans = user.get("loans", [])
    if not isinstance(loans, list) or not loans:
        return 0.0, 0
    remaining = min(amount, max(0.0, float(user.get("cash", 0.0))))
    if remaining <= 0:
        return 0.0, 0
    paid = 0.0
    closed = 0
    for loan in sorted(loans, key=lambda x: float(x.get("issued_ts", 0.0)) if isinstance(x, dict) else 0.0):
        if not isinstance(loan, dict):
            continue
        if str(loan.get("status", "active")) in {"paid", "closed"}:
            continue
        balance = max(0.0, float(loan.get("balance", 0.0)))
        if balance <= 0:
            loan["status"] = "paid"
            closed += 1
            continue
        payment = min(balance, remaining)
        if payment <= 0:
            break
        loan["balance"] = round(balance - payment, 4)
        paid += payment
        remaining -= payment
        if loan["balance"] <= 0.01:
            loan["balance"] = 0.0
            loan["status"] = "paid"
            closed += 1
        else:
            if str(loan.get("status", "active")) not in {"active", "current"}:
                loan["status"] = "current"
    if paid > 0:
        user["cash"] = max(0.0, float(user.get("cash", 0.0)) - paid)
        flags = user.setdefault("flags", {})
        if isinstance(flags, dict):
            flags["trade_limited"] = _business_debt_total(user) > (_business_networth(user_id) * BUSINESS_MAX_DEBT_TO_NETWORTH)
        bonus = 1 + min(4, closed)
        _business_apply_credit_score_delta(user, bonus)
        _business_add_ledger_entry(
            action="loan_repay",
            user_id=user_id,
            amount=-paid,
            details={"source": source, "closed_loans": closed},
        )
        _mark_business_dirty()
    return paid, closed


def _business_liquidate_assets(user_id: int, needed_amount: float) -> float:
    state = get_business_state()
    user = _business_get_user(user_id)
    recovered = 0.0
    for asset_type in ("stock", "commodity", "crypto"):
        book = _business_get_asset_book(asset_type)
        field = _business_holding_field(asset_type)
        if field is None:
            continue
        portfolio = user.get(field, {})
        if not isinstance(portfolio, dict):
            continue
        holdings = sorted(
            (
                (symbol, int(holding.get("qty", 0)), float(book.get(symbol, {}).get("price", 0.0)))
                for symbol, holding in portfolio.items()
                if isinstance(holding, dict)
            ),
            key=lambda row: row[1] * row[2],
            reverse=True,
        )
        for symbol, qty, price in holdings:
            if recovered >= needed_amount:
                break
            if qty <= 0 or price <= 0:
                continue
            sell_qty = qty
            discount = 0.90 if asset_type == "crypto" else 0.92
            proceeds = sell_qty * price * discount
            if recovered + proceeds > needed_amount:
                required = max(1, int((needed_amount - recovered) / max(1.0, price * discount)))
                sell_qty = min(qty, required)
                proceeds = sell_qty * price * discount
            if _business_remove_asset_from_user(user, asset_type, symbol, sell_qty):
                recovered += proceeds
        if recovered >= needed_amount:
            break

    if recovered < needed_amount and BUSINESS_ENABLE_PRIVATE_BUSINESSES:
        registry = state.get("businesses", {}).get("registry", {})
        if isinstance(registry, dict):
            owned_ids = [str(x) for x in user.get("business_ids", [])]
            ranked_biz: list[tuple[str, float]] = []
            for biz_id in owned_ids:
                biz = registry.get(biz_id)
                if not isinstance(biz, dict):
                    continue
                if str(biz.get("status", "active")) != "active":
                    continue
                level = max(1, int(biz.get("level", 1) or 1))
                employees = max(0, int(biz.get("employees", 0) or 0))
                debt = max(0.0, float(biz.get("debt", 0.0) or 0.0))
                value = max(0.0, float(biz.get("base_value", 0.0) or 0.0) * (1 + ((level - 1) * 0.4)) + (employees * 300.0) - debt)
                ranked_biz.append((biz_id, value))
            ranked_biz.sort(key=lambda row: row[1], reverse=True)
            for biz_id, value in ranked_biz:
                if recovered >= needed_amount:
                    break
                biz = registry.get(biz_id)
                if not isinstance(biz, dict):
                    continue
                liquidation = value * 0.62
                biz["status"] = "liquidated"
                biz["cash_reserve"] = 0.0
                user["business_ids"] = [x for x in user.get("business_ids", []) if str(x) != str(biz_id)]
                recovered += liquidation

    if recovered < needed_amount:
        plots = state["real_estate"]["plots"]
        owned = sorted(
            [
                plots.get(plot_id)
                for plot_id in list(user.get("properties", []))
                if isinstance(plots.get(plot_id), dict)
            ],
            key=lambda p: _business_plot_value(p),
            reverse=True,
        )
        for plot in owned:
            if recovered >= needed_amount:
                break
            if plot is None:
                continue
            if plot.get("auction_lock"):
                continue
            value = _business_plot_value(plot) * 0.85
            plot["owner_id"] = None
            plot["tier"] = 0
            plot["listed_price"] = None
            user["properties"] = [pid for pid in user.get("properties", []) if pid != plot.get("id")]
            recovered += value
    if recovered > 0:
        user["cash"] = max(0.0, float(user.get("cash", 0.0)) + recovered)
        _business_add_ledger_entry(
            action="forced_liquidation",
            user_id=user_id,
            amount=recovered,
            details={"reason": "debt_recovery"},
        )
        _mark_business_dirty()
    return recovered


def _business_generate_world_event() -> dict[str, Any]:
    templates: list[dict[str, Any]] = [
        {
            "name": "Risk-On Rally",
            "stock_shift": random.uniform(0.006, 0.020),
            "commodity_shift": random.uniform(-0.004, 0.008),
            "crypto_shift": random.uniform(0.010, 0.050),
            "duration_ticks": random.randint(3, 8),
            "sector": None,
        },
        {
            "name": "Macro Panic",
            "stock_shift": random.uniform(-0.030, -0.010),
            "commodity_shift": random.uniform(-0.012, 0.005),
            "crypto_shift": random.uniform(-0.055, -0.020),
            "duration_ticks": random.randint(2, 5),
            "sector": None,
        },
        {
            "name": "Energy Shock",
            "stock_shift": random.uniform(-0.015, 0.006),
            "commodity_shift": random.uniform(0.012, 0.045),
            "crypto_shift": random.uniform(-0.018, 0.012),
            "duration_ticks": random.randint(3, 6),
            "sector": "energy",
        },
        {
            "name": "Tech Acceleration",
            "stock_shift": random.uniform(0.008, 0.030),
            "commodity_shift": random.uniform(-0.010, 0.008),
            "crypto_shift": random.uniform(0.005, 0.028),
            "duration_ticks": random.randint(3, 7),
            "sector": "tech",
        },
        {
            "name": "Rate Hike Wave",
            "stock_shift": random.uniform(-0.022, -0.006),
            "commodity_shift": random.uniform(-0.006, 0.006),
            "crypto_shift": random.uniform(-0.040, -0.010),
            "duration_ticks": random.randint(2, 4),
            "sector": "finance",
        },
    ]
    event = dict(random.choice(templates))
    event["created_ts"] = _business_now_ts()
    event["remaining_ticks"] = int(event.get("duration_ticks", 3))
    return event


def _business_run_world_event_tick() -> str:
    state = get_business_state()
    meta = state["meta"]
    day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if str(meta.get("event_count_day_key", "")) != day_key:
        meta["event_count_day_key"] = day_key
        meta["event_count_today"] = 0
    if int(meta.get("event_count_today", 0) or 0) >= BUSINESS_EVENT_MAX_PER_DAY:
        note = "World desk held events due to daily cap."
        state["market"]["last_news"] = note
        _mark_business_dirty()
        return note
    event = _business_generate_world_event()
    state["market"]["active_event"] = event
    meta["event_count_today"] = int(meta.get("event_count_today", 0) or 0) + 1
    note = f"World Event: {event['name']} ({event['remaining_ticks']} ticks)"
    state["market"]["last_news"] = note
    _mark_business_dirty()
    return note


def _business_apply_market_group_tick(
    *,
    asset_type: str,
    assets: dict[str, Any],
    ai_market_bias: float,
    ai_sector_bias: dict[str, float],
    event: dict[str, Any] | None,
) -> tuple[str, float, float]:
    movers: list[tuple[str, float]] = []
    prev_sum = 0.0
    curr_sum = 0.0
    count = 0

    if asset_type == "crypto":
        move_cap = 0.36
        ai_weight = 1.15
        trend_jitter = 0.008
    elif asset_type == "commodity":
        move_cap = 0.18
        ai_weight = 0.72
        trend_jitter = 0.004
    else:
        move_cap = 0.22
        ai_weight = 1.0
        trend_jitter = 0.004

    event_shift = 0.0
    event_sector = None
    if isinstance(event, dict):
        key = f"{asset_type}_shift"
        event_shift = float(event.get(key, 0.0) or 0.0)
        event_sector = event.get("sector")

    for symbol, row in assets.items():
        if not isinstance(row, dict):
            continue
        prev_price = max(0.001, float(row.get("price", 0.001)))
        drift = float(row.get("trend", 0.0) or 0.0)
        vol = max(0.001, float(row.get("volatility", 0.02) or 0.02))
        sector = str(row.get("sector", "")).lower()
        move = random.gauss(drift, vol)
        move += ai_market_bias * ai_weight
        move += float(ai_sector_bias.get(sector, 0.0))
        if event_shift != 0.0:
            if event_sector is None or str(event_sector).lower() == sector:
                move += event_shift
            else:
                move += event_shift * 0.35
        move = _business_clamp_float(move, -move_cap, move_cap)
        new_price = max(0.5 if asset_type == "crypto" else 1.0, round(prev_price * (1 + move), 2))
        row["price"] = new_price
        row["trend"] = _business_clamp_float((drift * 0.66) + random.uniform(-trend_jitter, trend_jitter), -0.05, 0.05)
        history = row.get("history")
        if not isinstance(history, list):
            history = []
            row["history"] = history
        history.append(new_price)
        if len(history) > 96:
            del history[:-96]
        change_pct = ((new_price - prev_price) / prev_price) * 100.0
        movers.append((str(symbol), change_pct))
        prev_sum += prev_price
        curr_sum += new_price
        count += 1
        if change_pct <= -float(BUSINESS_CIRCUIT_BREAKER_DROP_PCT):
            _business_register_asset_halt(asset_type, str(symbol), reason=f"Drop {change_pct:.1f}%")

    movers.sort(key=lambda row: abs(row[1]), reverse=True)
    top = ", ".join(f"{sym} {pct:+.1f}%" for sym, pct in movers[:3]) if movers else "No major moves."
    prev_avg = (prev_sum / count) if count > 0 else 0.0
    curr_avg = (curr_sum / count) if count > 0 else 0.0
    return top, prev_avg, curr_avg


def _business_tick_apply_market() -> str | None:
    state = get_business_state()
    if _business_market_paused():
        return "Market paused by admins."

    _business_decay_halts_each_tick()
    market = state["market"]
    commodities = state.get("commodities", {})
    crypto = state.get("crypto", {})
    ai_dynamic = _business_get_ai_dynamic(state)
    ai_headline = str(ai_dynamic.get("headline", "") or "").strip()
    ai_market_bias = _business_clamp_float(float(ai_dynamic.get("market_bias", 0.0) or 0.0), -0.03, 0.03)
    ai_sector_bias_raw = ai_dynamic.get("sector_bias", {})
    ai_sector_bias: dict[str, float] = {}
    if isinstance(ai_sector_bias_raw, dict):
        for key, value in ai_sector_bias_raw.items():
            try:
                ai_sector_bias[str(key).lower()] = _business_clamp_float(float(value), -0.03, 0.03)
            except (TypeError, ValueError):
                continue

    event_note = None
    event = market.get("active_event")
    if isinstance(event, dict):
        event["remaining_ticks"] = int(event.get("remaining_ticks", 0) or 0) - 1
        if int(event["remaining_ticks"]) <= 0:
            event_note = f"Event ended: {event.get('name', 'unknown')}"
            market["active_event"] = None
            event = None

    stocks = market.get("stocks", {})
    stock_top, stock_prev, stock_curr = _business_apply_market_group_tick(
        asset_type="stock",
        assets=stocks if isinstance(stocks, dict) else {},
        ai_market_bias=ai_market_bias,
        ai_sector_bias=ai_sector_bias,
        event=event if isinstance(event, dict) else None,
    )
    commodity_assets = commodities.get("assets", {})
    commodity_top = "Commodities disabled."
    if BUSINESS_ENABLE_COMMODITIES and isinstance(commodity_assets, dict):
        commodity_top, _, _ = _business_apply_market_group_tick(
            asset_type="commodity",
            assets=commodity_assets,
            ai_market_bias=ai_market_bias * 0.7,
            ai_sector_bias=ai_sector_bias,
            event=event if isinstance(event, dict) else None,
        )
    crypto_assets = crypto.get("assets", {})
    crypto_top = "Crypto disabled."
    if BUSINESS_ENABLE_CRYPTO and isinstance(crypto_assets, dict):
        crypto_top, _, _ = _business_apply_market_group_tick(
            asset_type="crypto",
            assets=crypto_assets,
            ai_market_bias=ai_market_bias * 1.2,
            ai_sector_bias=ai_sector_bias,
            event=event if isinstance(event, dict) else None,
        )

    if stock_prev > 0 and stock_curr > 0:
        index_drop_pct = ((stock_curr - stock_prev) / stock_prev) * 100.0
        state["market_halts"]["last_index_value"] = round(stock_curr, 3)
        if index_drop_pct <= -float(BUSINESS_MARKET_HALT_DROP_PCT):
            _business_register_market_halt(
                f"Index drop {index_drop_pct:.1f}% exceeded {BUSINESS_MARKET_HALT_DROP_PCT:.0f}%"
            )

    note = event_note or "Market tick settled."
    if isinstance(event, dict):
        note = f"World Event: {event.get('name', 'unknown')}"
    if ai_headline:
        note = f"{ai_headline}. {note}"
    market["last_news"] = f"{note} Stocks: {stock_top}"
    commodities["last_news"] = f"{note} Commodities: {commodity_top}"
    crypto["last_news"] = f"{note} Crypto: {crypto_top}"

    now_ts = _business_now_ts()
    market_history = market.get("history")
    if not isinstance(market_history, list):
        market_history = []
        market["history"] = market_history
    market_history.append({"ts": now_ts, "news": market["last_news"]})
    if len(market_history) > 300:
        del market_history[:-300]
    for container, key in ((commodities, "history"), (crypto, "history")):
        history = container.get(key)
        if not isinstance(history, list):
            history = []
            container[key] = history
        history.append({"ts": now_ts, "news": str(container.get("last_news", ""))[:240]})
        if len(history) > 260:
            del history[:-260]

    _mark_business_dirty()
    return market["last_news"]


def _business_tick_apply_properties_and_loans() -> None:
    state = get_business_state()
    plots = state["real_estate"]["plots"]
    users = state["users"]
    rates = _business_rates_for_guild(None)
    maintenance_rate = max(0.0, float(rates["property_maintenance_rate"]))
    tax_rate = max(0.0, float(rates["property_tax_rate"]))
    tick_hours = max(0.05, float(BUSINESS_MARKET_TICK_MINUTES) / 60.0)

    zone_yield = {"urban": 0.00165, "suburban": 0.0012, "rural": 0.00085}
    now_ts = _business_now_ts()

    for user_key, user in users.items():
        if not isinstance(user, dict):
            continue
        uid = int(user_key) if str(user_key).isdigit() else 0
        income = 0.0
        expenses = 0.0
        for plot_id in list(user.get("properties", [])):
            plot = plots.get(str(plot_id))
            if not isinstance(plot, dict):
                continue
            if str(plot.get("owner_id")) != str(user_key):
                continue
            value = _business_plot_value(plot)
            tier = int(plot.get("tier", 0))
            multiplier = 1 + (tier * 0.58)
            yield_rate = zone_yield.get(str(plot.get("zone", "rural")), 0.0008) * multiplier * tick_hours
            vacancy_roll = random.random()
            is_vacant = vacancy_roll < max(0.02, 0.11 - (tier * 0.012))
            rent = 0.0 if is_vacant else (value * yield_rate)
            maintenance = value * maintenance_rate * tick_hours
            property_tax = max(0.0, rent) * tax_rate
            delta = rent - maintenance - property_tax
            income += rent
            expenses += (maintenance + property_tax)
            user["cash"] = float(user.get("cash", 0.0)) + delta

        loans = user.get("loans", [])
        if isinstance(loans, list):
            for loan in loans:
                if not isinstance(loan, dict):
                    continue
                if str(loan.get("status", "active")) in {"paid", "closed"}:
                    continue
                balance = max(0.0, float(loan.get("balance", 0.0)))
                step_rate = max(0.0, float(loan.get("rate", BUSINESS_HOURLY_INTEREST_RATE)))
                interest_multiplier = pow(1 + step_rate, tick_hours)
                balance *= interest_multiplier
                due_ts = float(loan.get("due_ts", 0.0))
                overdue_minutes = int(loan.get("overdue_minutes", 0))
                if now_ts > due_ts > 0:
                    overdue_minutes += int(BUSINESS_MARKET_TICK_MINUTES)
                    balance *= (1 + (0.0025 * max(0.25, tick_hours)))
                overdue_hours = int(overdue_minutes // 60)
                loan["overdue_minutes"] = overdue_minutes
                loan["overdue_hours"] = overdue_hours
                if overdue_hours > BUSINESS_LOAN_GRACE_HOURS + 24:
                    loan["status"] = "default_watch"
                elif overdue_hours > BUSINESS_LOAN_GRACE_HOURS:
                    loan["status"] = "stressed"
                elif overdue_hours > 0:
                    loan["status"] = "overdue"
                else:
                    loan["status"] = "current"
                loan["balance"] = round(balance, 4)
                loan["last_tick_ts"] = now_ts

            debt = _business_debt_total(user)
            net = max(1.0, _business_networth(uid)) if uid > 0 else 1.0
            flags = user.setdefault("flags", {})
            if isinstance(flags, dict):
                flags["trade_limited"] = debt > (net * BUSINESS_MAX_DEBT_TO_NETWORTH) or any(
                    int(loan.get("overdue_hours", 0)) > BUSINESS_LOAN_GRACE_HOURS
                    for loan in loans
                    if isinstance(loan, dict) and str(loan.get("status", "active")) not in {"paid", "closed"}
                )
            if float(user.get("cash", 0.0)) < 0 and uid > 0:
                needed = abs(float(user.get("cash", 0.0))) + (debt * 0.08)
                recovered = _business_liquidate_assets(uid, needed)
                if recovered > 0:
                    _business_repay_loans_from_cash(uid, recovered * 0.45, source="auto_recovery")

        tick_net_income = max(0.0, income - expenses)
        user["income_total"] = float(user.get("income_total", 0.0)) + tick_net_income
        user["weekly_income"] = float(user.get("weekly_income", 0.0)) + tick_net_income
    _mark_business_dirty()


async def _business_expire_trades_and_auctions() -> None:
    state = get_business_state()
    now_ts = _business_now_ts()
    offers = state["trades"]["open"]
    expired_trade_ids = [
        trade_id
        for trade_id, offer in offers.items()
        if isinstance(offer, dict) and now_ts >= float(offer.get("expires_ts", 0.0))
    ]
    for trade_id in expired_trade_ids:
        offers.pop(trade_id, None)

    expired_auctions: list[tuple[str, int]] = []
    for auction_id, auc in state["auctions"]["active"].items():
        if not isinstance(auc, dict):
            continue
        if now_ts < float(auc.get("end_ts", 0.0)):
            continue
        expired_auctions.append((auction_id, int(auc.get("channel_id", 0) or 0)))
    _mark_business_dirty()
    for auction_id, channel_id in expired_auctions:
        summary = await _business_settle_auction(auction_id, reason="expired")
        channel = bot.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(f"ðŸ {summary}")
            except discord.HTTPException:
                pass


def _business_time_bucket_key(minutes: int) -> str:
    window = max(1, int(minutes))
    bucket = int(datetime.now(timezone.utc).timestamp() // (window * 60))
    return str(bucket)


def _business_cycle_bucket_key(days: int) -> str:
    window = max(1, int(days))
    bucket = int(datetime.now(timezone.utc).timestamp() // (window * 24 * 3600))
    return str(bucket)


def _business_settle_private_businesses() -> tuple[int, float]:
    if not BUSINESS_ENABLE_PRIVATE_BUSINESSES:
        return 0, 0.0
    state = get_business_state()
    registry = state.get("businesses", {}).get("registry", {})
    profiles = state.get("businesses", {}).get("profiles", {})
    if not isinstance(registry, dict) or not isinstance(profiles, dict):
        return 0, 0.0
    settled = 0
    moved_cash = 0.0
    for biz_id, biz in list(registry.items()):
        if not isinstance(biz, dict):
            continue
        if str(biz.get("status", "active")) != "active":
            continue
        owner_id = int(biz.get("owner_id", 0) or 0)
        if owner_id <= 0:
            continue
        owner = _business_get_user(owner_id)
        biz_type = str(biz.get("type", "retail")).lower()
        profile = profiles.get(biz_type) if isinstance(profiles.get(biz_type), dict) else profiles.get("retail", {})
        if not isinstance(profile, dict):
            profile = {}
        level = max(1, int(biz.get("level", 1) or 1))
        employees = max(0, int(biz.get("employees", 0) or 0))
        revenue_base = float(profile.get("revenue", 2000.0) or 2000.0)
        payroll_unit = float(profile.get("payroll", 260.0) or 260.0)
        maintenance_base = float(profile.get("maintenance", 180.0) or 180.0)
        gross = revenue_base * (1 + ((level - 1) * 0.35)) * (1 + (employees * 0.10))
        gross *= random.uniform(0.88, 1.16)
        payroll = payroll_unit * employees
        maintenance = maintenance_base * max(1, level)
        debt_interest = max(0.0, float(biz.get("debt", 0.0) or 0.0)) * 0.01
        pre_tax = gross - payroll - maintenance - debt_interest
        transfer_ratio = 0.74 if pre_tax > 0 else 0.0
        payout = pre_tax * transfer_ratio
        reserve_delta = pre_tax - payout
        owner["cash"] = float(owner.get("cash", 0.0)) + payout
        owner["weekly_income"] = float(owner.get("weekly_income", 0.0)) + max(0.0, payout)
        owner["income_total"] = float(owner.get("income_total", 0.0)) + max(0.0, payout)
        biz["cash_reserve"] = float(biz.get("cash_reserve", 0.0) or 0.0) + reserve_delta
        if pre_tax < 0:
            biz["debt"] = max(0.0, float(biz.get("debt", 0.0) or 0.0) + abs(pre_tax) * 0.75)
            biz["stress_cycles"] = int(biz.get("stress_cycles", 0) or 0) + 1
        else:
            biz["stress_cycles"] = max(0, int(biz.get("stress_cycles", 0) or 0) - 1)
            if float(biz.get("debt", 0.0) or 0.0) > 0 and float(biz.get("cash_reserve", 0.0) or 0.0) > 0:
                repay = min(float(biz["debt"]), float(biz["cash_reserve"]) * 0.35)
                biz["debt"] = max(0.0, float(biz["debt"]) - repay)
                biz["cash_reserve"] = max(0.0, float(biz["cash_reserve"]) - repay)
        threshold = max(12000.0, float(profile.get("expand_cost", 7000.0) or 7000.0) * (1 + (level * 0.5)))
        if float(biz.get("debt", 0.0) or 0.0) > threshold and int(biz.get("stress_cycles", 0) or 0) >= 2:
            biz["status"] = "liquidated"
            liquidation_cash = max(0.0, float(biz.get("cash_reserve", 0.0) or 0.0) * 0.45)
            owner["cash"] = float(owner.get("cash", 0.0)) + liquidation_cash
            owner["business_ids"] = [x for x in owner.get("business_ids", []) if str(x) != str(biz_id)]
            _business_add_ledger_entry(
                action="business_liquidation",
                user_id=owner_id,
                amount=liquidation_cash,
                details={"biz_id": str(biz_id), "debt": float(biz.get("debt", 0.0) or 0.0)},
            )
        settled += 1
        moved_cash += payout
    if settled > 0:
        _mark_business_dirty()
    return settled, moved_cash


def _business_apply_weekly_tax_credit_cycle() -> tuple[int, float]:
    state = get_business_state()
    tax_state = state.get("tax", {})
    if not isinstance(tax_state, dict):
        tax_state = {}
        state["tax"] = tax_state
    users = state.get("users", {})
    if not isinstance(users, dict):
        return 0, 0.0
    filings = 0
    total_tax_added = 0.0
    short_rate = _business_clamp_float(
        float(tax_state.get("capital_gains_short_rate", BUSINESS_CAPITAL_GAINS_SHORT_RATE) or BUSINESS_CAPITAL_GAINS_SHORT_RATE),
        0.0,
        0.8,
    )
    long_rate = _business_clamp_float(
        float(tax_state.get("capital_gains_long_rate", BUSINESS_CAPITAL_GAINS_LONG_RATE) or BUSINESS_CAPITAL_GAINS_LONG_RATE),
        0.0,
        0.8,
    )
    for user in users.values():
        if not isinstance(user, dict):
            continue
        weekly_income = float(user.get("weekly_income", 0.0) or 0.0)
        short_gains = float(user.get("weekly_realized_gains_short", 0.0) or 0.0)
        long_gains = float(user.get("weekly_realized_gains_long", 0.0) or 0.0)
        income_tax = _business_progressive_income_tax(max(0.0, weekly_income))
        gains_tax = max(0.0, short_gains) * short_rate + max(0.0, long_gains) * long_rate
        added = income_tax + gains_tax
        if added > 0:
            user["tax_liability"] = float(user.get("tax_liability", 0.0)) + added
            total_tax_added += added
            filings += 1
        loans = user.get("loans", [])
        has_overdue = False
        severe = False
        if isinstance(loans, list):
            for loan in loans:
                if not isinstance(loan, dict):
                    continue
                status = str(loan.get("status", "current"))
                if status in {"overdue", "stressed", "default_watch"}:
                    has_overdue = True
                if status in {"stressed", "default_watch"}:
                    severe = True
        if severe:
            _business_apply_credit_score_delta(user, -8)
        elif has_overdue:
            _business_apply_credit_score_delta(user, -4)
        elif _business_debt_total(user) > 0:
            _business_apply_credit_score_delta(user, 2)
        user["weekly_income"] = 0.0
        user["weekly_realized_gains_short"] = 0.0
        user["weekly_realized_gains_long"] = 0.0
    tax_state["last_weekly_cycle_key"] = _business_cycle_bucket_key(BUSINESS_WEEKLY_CYCLE_DAYS)
    if filings > 0:
        _mark_business_dirty()
    return filings, total_tax_added


async def run_business_hourly_tick(force: bool = False) -> bool:
    if not BUSINESS_ENABLED:
        return False
    async with BUSINESS_TICK_LOCK:
        market_key = _business_time_bucket_key(BUSINESS_MARKET_TICK_MINUTES)
        event_key = _business_time_bucket_key(BUSINESS_WORLD_EVENT_INTERVAL_MINUTES)
        weekly_key = _business_cycle_bucket_key(BUSINESS_WEEKLY_CYCLE_DAYS)
        async with BUSINESS_STATE_LOCK:
            state = get_business_state()
            meta = state["meta"]
            should_market = force or str(meta.get("last_market_tick_key", "")) != market_key
            should_event = force or str(meta.get("last_world_event_tick_key", "")) != event_key
            should_weekly = force or str(meta.get("last_weekly_cycle_key", "")) != weekly_key
            if not should_market and not should_event and not should_weekly:
                return False
        if should_event:
            try:
                await _business_refresh_ai_dynamic()
            except Exception as error:
                print(f"[BUSINESS AI DIRECTOR ERROR] {error}")
        async with BUSINESS_STATE_LOCK:
            state = get_business_state()
            meta = state["meta"]
            if should_event and str(meta.get("last_world_event_tick_key", "")) != event_key:
                meta["last_world_event_tick_key"] = event_key
                _business_run_world_event_tick()
            if should_market and str(meta.get("last_market_tick_key", "")) != market_key:
                meta["last_market_tick_key"] = market_key
                meta["last_tick_hour_key"] = _business_hour_key()
                meta["last_tick_ts"] = _business_now_ts()
                _business_tick_apply_market()
                _business_tick_apply_properties_and_loans()
            if should_weekly and str(meta.get("last_weekly_cycle_key", "")) != weekly_key:
                meta["last_weekly_cycle_key"] = weekly_key
                _business_settle_private_businesses()
                _business_apply_weekly_tax_credit_cycle()
            _mark_business_dirty()
    return True


def _business_take_daily_claim(user_id: int, guild_id: int | None = None) -> tuple[bool, float, int]:
    user = _business_get_user(user_id)
    now_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = user.get("daily")
    if not isinstance(daily, dict):
        daily = {"day": "", "streak": 0}
        user["daily"] = daily
    if str(daily.get("day", "")) == now_day:
        return False, 0.0, int(daily.get("streak", 0))
    prev_day = str(daily.get("day", ""))
    streak = int(daily.get("streak", 0))
    if prev_day:
        try:
            prev_dt = datetime.strptime(prev_day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            delta_days = (datetime.now(timezone.utc).date() - prev_dt.date()).days
            if delta_days == 1:
                streak += 1
            else:
                streak = 1
        except Exception:
            streak = 1
    else:
        streak = 1
    dynamic = _business_get_ai_dynamic(get_business_state())
    shift_pct = _business_clamp_float(
        float(dynamic.get("daily_claim_shift_pct", 0.0) or 0.0),
        -0.25,
        0.25,
    )
    base_claim = float(BUSINESS_DAILY_CLAIM) * (1 + shift_pct)
    bonus_base = float(BUSINESS_DAILY_CLAIM_STREAK_BONUS) * (1 + (shift_pct * 0.45))
    bonus = max(0.0, (streak - 1) * bonus_base)
    amount = float(max(200.0, base_claim + bonus))
    user["cash"] = float(user.get("cash", 0.0)) + amount
    daily["day"] = now_day
    daily["streak"] = streak
    _business_add_ledger_entry(
        action="daily_claim",
        user_id=user_id,
        amount=amount,
        details={"streak": streak, "claim_shift_pct": shift_pct, "guild_id": guild_id},
    )
    _mark_business_dirty()
    return True, amount, streak


def _business_issue_loan(user_id: int, amount: float) -> tuple[bool, str]:
    if amount <= 0:
        return False, "Loan amount must be positive."
    user = _business_get_user(user_id)
    debt = _business_debt_total(user)
    net = max(1.0, _business_networth(user_id))
    credit_score = int(user.get("credit_score", 650) or 650)
    debt_ratio = (debt + amount) / net
    if debt_ratio > BUSINESS_MAX_DEBT_TO_NETWORTH:
        return False, (
            f"Loan denied. Debt ratio would be `{debt_ratio:.2f}` "
            f"(max `{BUSINESS_MAX_DEBT_TO_NETWORTH:.2f}`)."
        )
    cap_multiplier = _business_clamp_float(0.60 + ((credit_score - 500) / 500), 0.55, 1.35)
    cap = max(15000.0, net * cap_multiplier)
    if amount > cap:
        return False, f"Loan denied. Your current max is `{_business_money(cap)}`."
    if credit_score < 540 and amount > (cap * 0.65):
        return False, "Loan denied for risk. Repay current debt and improve credit score first."

    score_penalty = max(0.0, (680 - credit_score) / 900)
    loan_rate = float(BUSINESS_HOURLY_INTEREST_RATE) * (1 + score_penalty)
    loan_rate = _business_clamp_float(loan_rate, 0.0004, 0.01)

    loan_id = _business_next_id("loan")
    issued = _business_now_ts()
    loan = {
        "id": loan_id,
        "principal": float(amount),
        "balance": float(amount),
        "rate": float(loan_rate),
        "issued_ts": issued,
        "due_ts": issued + (7 * 24 * 3600),
        "status": "current",
        "overdue_hours": 0,
        "overdue_minutes": 0,
        "last_tick_ts": issued,
    }
    user.setdefault("loans", []).append(loan)
    user["cash"] = float(user.get("cash", 0.0)) + amount
    _business_apply_credit_score_delta(user, -2)
    _business_add_ledger_entry(
        action="loan_take",
        user_id=user_id,
        amount=amount,
        details={"loan_id": loan_id},
    )
    _mark_business_dirty()
    return True, loan_id


async def _business_settle_auction(auction_id: str, *, reason: str) -> str:
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        auctions = state["auctions"]["active"]
        auction = auctions.get(auction_id)
        if not isinstance(auction, dict):
            return "Auction not found."

        seller_id = int(auction.get("seller_id", 0))
        seller = _business_get_user(seller_id)
        winner_id = int(auction.get("highest_bidder", 0) or 0)
        bid_amount = float(auction.get("highest_bid", 0.0) or 0.0)
        asset_type = str(auction.get("asset_type", ""))
        asset_ref = str(auction.get("asset_ref", ""))
        qty = int(auction.get("qty", 0) or 0)

        winner_ok = winner_id > 0
        if winner_ok:
            winner = _business_get_user(winner_id)
            winner_ok = float(winner.get("cash", 0.0)) >= bid_amount
        else:
            winner = None

        summary = ""
        if winner_ok and winner is not None and bid_amount > 0:
            rates = _business_rates_for_guild(int(auction.get("guild_id", 0) or 0))
            fee = bid_amount * max(0.0, float(rates["transaction_fee_rate"]))
            winner["cash"] = float(winner.get("cash", 0.0)) - bid_amount
            seller["cash"] = float(seller.get("cash", 0.0)) + max(0.0, bid_amount - fee)

            if asset_type == "stock":
                _business_add_stock_to_user(winner, asset_ref, qty, bid_amount)
            elif asset_type == "property":
                plot = state["real_estate"]["plots"].get(asset_ref)
                if isinstance(plot, dict):
                    plot["owner_id"] = str(winner_id)
                    plot["listed_price"] = None
                    plot["auction_lock"] = None
                    winner_props = winner.setdefault("properties", [])
                    if asset_ref not in winner_props:
                        winner_props.append(asset_ref)
                    seller["properties"] = [pid for pid in seller.get("properties", []) if pid != asset_ref]
            _business_add_ledger_entry(
                action="auction_settle",
                user_id=winner_id,
                amount=-bid_amount,
                details={
                    "auction_id": auction_id,
                    "seller_id": seller_id,
                    "asset_type": asset_type,
                    "asset_ref": asset_ref,
                    "qty": qty,
                    "reason": reason,
                },
            )
            summary = (
                f"Auction `{auction_id}` won by <@{winner_id}> for `{_business_money(bid_amount)}`."
            )
        else:
            if asset_type == "stock":
                _business_add_stock_to_user(seller, asset_ref, qty, 0.0)
            elif asset_type == "property":
                plot = state["real_estate"]["plots"].get(asset_ref)
                if isinstance(plot, dict):
                    plot["owner_id"] = str(seller_id)
                    plot["auction_lock"] = None
                    seller_props = seller.setdefault("properties", [])
                    if asset_ref not in seller_props:
                        seller_props.append(asset_ref)
            summary = f"Auction `{auction_id}` ended with no valid winner."

        auctions.pop(auction_id, None)
        _mark_business_dirty()
        return summary


async def _business_require_access(
    ctx: commands.Context,
    *,
    require_mod: bool = False,
    check_cooldown: bool = True,
    mutate: bool = False,
    allow_when_disabled: bool = False,
) -> bool:
    if ctx.guild is None:
        await ctx.send("Business commands can only be used in a server.")
        return False
    if not allow_when_disabled and not get_guild_business_enabled(ctx.guild.id):
        await ctx.send("Business mode is disabled in this server.")
        return False
    if require_mod:
        if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
            await ctx.send("Only moderators can use this command.")
            return False
    elif check_cooldown:
        now = time.monotonic()
        last = BUSINESS_LAST_COMMAND_TS.get(ctx.author.id, 0.0)
        if now - last < BUSINESS_COMMAND_COOLDOWN_SECONDS:
            await ctx.send(
                f"Slow down. Business command cooldown: `{BUSINESS_COMMAND_COOLDOWN_SECONDS}`s.",
                delete_after=4,
            )
            return False
        BUSINESS_LAST_COMMAND_TS[ctx.author.id] = now

    if mutate and _business_is_user_frozen(ctx.author.id):
        await ctx.send("Your business account is frozen by moderators.")
        return False
    return True


async def purge_recent_bot_webhook_messages(
    channel: discord.TextChannel, trigger_message: discord.Message | None = None
) -> int:
    if trigger_message is not None:
        try:
            await trigger_message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

    deleted_messages = await channel.purge(
        limit=20,
        check=lambda m: m.author.bot or m.webhook_id is not None,
        bulk=False,
    )
    return len(deleted_messages)


async def generate_argument_opening(topic: str, side: Literal["PRO", "ANTI"]) -> str:
    prompt = (
        "Argue aggressively but playfully for a Discord debate topic.\n"
        "No hate speech or threats.\n"
        "Output: a short opening statement + 4 bullet arguments + one savage closer.\n\n"
        f"Topic: {topic}\n"
        f"Side: {side}"
    )
    return await request_fun_ai(
        prompt,
        max_tokens=260,
        temperature=0.85,
        policy_key="argument",
    )


BUSINESS_HELP_KB: list[dict[str, object]] = [
    {
        "id": "quickstart",
        "title": "Quickstart: First 15 Minutes",
        "keywords": (
            "start game",
            "beginner",
            "how to start",
            "new player",
            "quickstart",
            "first steps",
        ),
        "content": (
            "1. Run `{PREFIX}balance` to initialize and check your wallet.\n"
            "2. Run `{PREFIX}dailyclaim` for daily income.\n"
            "3. Run `{PREFIX}stocks` and `{PREFIX}market` to see live prices and trend.\n"
            "4. Start small: `{PREFIX}buy <symbol> <qty>` with low qty so you learn volatility.\n"
            "5. Keep cash buffer (10-20%) instead of spending everything.\n"
            "6. Check `{PREFIX}portfolio`, `{PREFIX}networth`, and `{PREFIX}credit` after each move.\n"
            "7. When stable, add property with `{PREFIX}plots` + `{PREFIX}buyplot <id>`.\n"
            "8. Optional growth: use `{PREFIX}takeloan <amount>` only if repayment is clear."
        ),
    },
    {
        "id": "market-basics",
        "title": "Stocks, Commodities, and Crypto",
        "keywords": (
            "stocks",
            "market",
            "buy",
            "sell",
            "commodities",
            "crypto",
            "price",
            "volatility",
        ),
        "content": (
            "Use `{PREFIX}stocks` for stock list, `{PREFIX}commodities` for raw assets, and `{PREFIX}crypto` for high-risk assets.\n"
            "Buy commands: `{PREFIX}buy`, `{PREFIX}buycommodity`, `{PREFIX}buycrypto`.\n"
            "Sell commands: `{PREFIX}sell`, `{PREFIX}sellcommodity`, `{PREFIX}sellcrypto`.\n"
            "Rules to remember: spread + fee on each order, exposure limits, and temporary halts during large crashes."
        ),
    },
    {
        "id": "real-estate",
        "title": "Plots and Properties",
        "keywords": (
            "plot",
            "property",
            "real estate",
            "buyplot",
            "upgrade",
            "sellproperty",
            "rent",
        ),
        "content": (
            "Discover land with `{PREFIX}plots`, then buy with `{PREFIX}buyplot <plot_id>`.\n"
            "View owned assets using `{PREFIX}properties`.\n"
            "Grow value using `{PREFIX}upgrade <plot_id>`.\n"
            "Trade property using `{PREFIX}sellproperty <id> <price>` and `{PREFIX}buyproperty <id>`.\n"
            "Properties add passive upside but also maintenance/tax pressure each cycle."
        ),
    },
    {
        "id": "loans-credit",
        "title": "Loans, Debt, and Credit Score",
        "keywords": (
            "loan",
            "takeloan",
            "repay",
            "debt",
            "credit",
            "interest",
        ),
        "content": (
            "Check debt snapshot with `{PREFIX}loan` or `{PREFIX}debts`.\n"
            "Borrow with `{PREFIX}takeloan <amount>`.\n"
            "Repay with `{PREFIX}repay <amount>`.\n"
            "Use `{PREFIX}credit` to track score and borrowing quality.\n"
            "Late debt can trigger restrictions and liquidation; consistent repayment improves credit over time."
        ),
    },
    {
        "id": "taxes-income",
        "title": "Taxes, Salary, and Filing",
        "keywords": (
            "tax",
            "taxes",
            "filetax",
            "salary",
            "income tax",
            "capital gains",
        ),
        "content": (
            "Check salary with `{PREFIX}salary` and tax status with `{PREFIX}taxes`.\n"
            "Pay manually with `{PREFIX}filetax [amount]`.\n"
            "Tax liability grows from gains/weekly cycles; leaving it too long hurts cashflow and risk profile.\n"
            "Track broad economy pressure using `{PREFIX}economystatus`."
        ),
    },
    {
        "id": "private-businesses",
        "title": "Private Businesses",
        "keywords": (
            "startbiz",
            "business",
            "mybiz",
            "bizhire",
            "bizfire",
            "bizexpand",
            "profit",
        ),
        "content": (
            "Create with `{PREFIX}startbiz <type> <name>`.\n"
            "View operations with `{PREFIX}mybiz`.\n"
            "Manage team using `{PREFIX}bizhire` / `{PREFIX}bizfire`.\n"
            "Scale with `{PREFIX}bizexpand`.\n"
            "Weekly settlement applies revenue, payroll, maintenance, debt pressure, and tax effects."
        ),
    },
    {
        "id": "p2p-trading",
        "title": "Player Trade and Auctions",
        "keywords": (
            "trade",
            "auction",
            "bid",
            "trade_accept",
            "trade_decline",
            "auction_start",
            "auctions",
        ),
        "content": (
            "Direct trade: `{PREFIX}trade <@user> <cash|stock|property> <asset> <amount> [request_cash]`.\n"
            "Finalize/deny with `{PREFIX}trade_accept <id>` or `{PREFIX}trade_decline <id>`.\n"
            "Auction flow: `{PREFIX}auction_start ...`, `{PREFIX}bid <id> <amount>`, `{PREFIX}auctions`.\n"
            "Auctions include anti-sniping extensions near close."
        ),
    },
    {
        "id": "status-analysis",
        "title": "How to Track Progress",
        "keywords": (
            "status",
            "progress",
            "portfolio",
            "networth",
            "leaderboard",
            "bizprofile",
            "marketnews",
            "ledger",
        ),
        "content": (
            "Core health checks: `{PREFIX}portfolio`, `{PREFIX}networth`, `{PREFIX}credit`, `{PREFIX}taxes`.\n"
            "Economy-level view: `{PREFIX}marketnews`, `{PREFIX}markethalt`, `{PREFIX}economystatus`.\n"
            "Competitive stats: `{PREFIX}bizleaderboard [cash|networth|income]` and `{PREFIX}bizprofile [@user]`.\n"
            "Audit recent transactions with `{PREFIX}ledger [@user]`."
        ),
    },
    {
        "id": "risk-controls",
        "title": "Risk and Safety Controls",
        "keywords": (
            "halt",
            "circuit breaker",
            "frozen",
            "admin",
            "bizadmin",
            "risk",
            "liquidation",
        ),
        "content": (
            "Circuit breakers pause severe drops (asset-level and market-level).\n"
            "If debt escalates, the game can restrict trading and liquidate assets in a controlled order.\n"
            "Moderators can use `{PREFIX}bizadmin ...` for freeze/grant/audit/reverse and market control actions."
        ),
    },
]

BUSINESS_HELP_QUERY_TERMS: tuple[str, ...] = (
    "game",
    "business",
    "economy",
    "market",
    "buy",
    "sell",
    "trade",
    "stock",
    "stocks",
    "commodity",
    "commodities",
    "crypto",
    "plot",
    "property",
    "loan",
    "debt",
    "credit",
    "tax",
    "taxes",
    "balance",
    "dailyclaim",
    "portfolio",
    "networth",
    "debts",
    "salary",
    "biz",
    "auction",
    "takeloan",
    "repay",
)

BUSINESS_HELP_INTENT_TERMS: tuple[str, ...] = (
    "help",
    "guide",
    "how",
    "explain",
    "tell",
    "tutorial",
    "walkthrough",
    "setup",
    "configure",
    "start",
    "begin",
    "commands",
    "cmd",
    "tips",
)


def _help_tokenize(text: str) -> list[str]:
    return [tok.lower() for tok in WORD_PATTERN.findall(text.lower()) if len(tok) >= 2]


def parse_business_help_query(text: str) -> str | None:
    normalized = " ".join(text.lower().split()).strip()
    if not normalized:
        return None

    if re.match(r"^(buy|sell)\s+[a-z0-9._-]+\s+\d+\b", normalized):
        return None
    if re.match(r"^(bid|repay|takeloan)\s+\d+\b", normalized):
        return None
    if re.match(r"^(buyplot|buyproperty)\s+[a-z0-9._-]+\b", normalized):
        return None
    if re.match(r"^sellproperty\s+[a-z0-9._-]+\s+\d+\b", normalized):
        return None

    has_domain = any(term in normalized for term in BUSINESS_HELP_QUERY_TERMS)
    has_intent = any(term in normalized for term in BUSINESS_HELP_INTENT_TERMS)
    asks_explanatory_what = bool(
        re.search(r"^(what(?:'s| is| are)|tell me about)\b", normalized)
    )
    asks_personal_status = bool(re.search(r"\bwhat(?:'s| is)?\s+my\b", normalized))
    asks_question = normalized.endswith("?")
    question_has_help_cue = bool(
        re.search(r"\b(how|what|why|when|where|can|should)\b", normalized)
    )
    if not has_domain:
        return None
    if asks_personal_status:
        return None
    if has_intent or asks_explanatory_what or (asks_question and question_has_help_cue):
        return normalized
    return None


def retrieve_business_help_chunks(query: str, *, limit: int = 3) -> list[dict[str, object]]:
    normalized = " ".join(query.lower().split()).strip()
    query_tokens = set(_help_tokenize(normalized))
    ranked: list[tuple[float, dict[str, object]]] = []

    for chunk in BUSINESS_HELP_KB:
        score = 0.0
        keywords = chunk.get("keywords", ())
        if isinstance(keywords, tuple):
            for keyword in keywords:
                kw = str(keyword).lower().strip()
                if not kw:
                    continue
                if " " in kw:
                    if kw in normalized:
                        score += 6.0
                    kw_tokens = set(_help_tokenize(kw))
                    if kw_tokens and kw_tokens.issubset(query_tokens):
                        score += 3.0
                elif kw in query_tokens:
                    score += 2.5

        doc_text = f"{chunk.get('title', '')} {chunk.get('content', '')}"
        overlap = len(query_tokens.intersection(_help_tokenize(doc_text)))
        score += min(6.0, overlap * 0.8)

        if str(chunk.get("id")) == "quickstart":
            if {"start", "begin", "new", "first"}.intersection(query_tokens):
                score += 8.0
            if {"game", "economy", "business"}.intersection(query_tokens):
                score += 2.0

        if score > 0:
            ranked.append((score, chunk))

    if not ranked:
        fallback = next((entry for entry in BUSINESS_HELP_KB if entry.get("id") == "quickstart"), None)
        return [fallback] if fallback else []

    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = [item[1] for item in ranked[: max(1, limit)]]
    if str(selected[0].get("id")) != "quickstart" and (
        "start" in normalized or "begin" in normalized or "new player" in normalized
    ):
        quickstart = next((entry for entry in BUSINESS_HELP_KB if entry.get("id") == "quickstart"), None)
        if quickstart is not None:
            selected = [quickstart, *selected]
    deduped: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for entry in selected:
        entry_id = str(entry.get("id", ""))
        if entry_id in seen_ids:
            continue
        seen_ids.add(entry_id)
        deduped.append(entry)
    return deduped[: max(1, limit)]


def build_business_help_response(query: str, chunks: list[dict[str, object]]) -> str:
    if not chunks:
        return (
            "Business help is available, but I could not map this query.\n"
            f"Try `{PREFIX}help` and see the Business Commands section."
        )

    lines = [
        f"Business guide for: `{query}`",
        "",
    ]
    for chunk in chunks:
        title = str(chunk.get("title", "Guide")).strip()
        content = str(chunk.get("content", "")).strip().replace("{PREFIX}", PREFIX)
        lines.append(f"**{title}**")
        lines.append(content)
        lines.append("")
    lines.append(
        f"Ask follow-ups naturally, for example: `bell explain loans`, "
        f"`bell how do taxes work`, `bell how to grow faster safely`."
    )
    return "\n".join(lines).strip()


async def send_business_help_query_response(
    target: discord.abc.Messageable, query: str
) -> None:
    chunks = retrieve_business_help_chunks(query, limit=4)
    response = build_business_help_response(query, chunks)
    await send_chunked(target, response)


def _sanitize_capabilities_catalog_payload(payload: Any) -> dict[str, Any]:
    base = _default_capabilities_catalog_payload()
    if not isinstance(payload, dict):
        return base
    commands_raw = payload.get("commands", {})
    if not isinstance(commands_raw, dict):
        commands_raw = {}
    system_raw = payload.get("system_capabilities", [])
    if not isinstance(system_raw, list):
        system_raw = []
    sanitized: dict[str, Any] = {
        "schema_version": int(payload.get("schema_version", 1) or 1),
        "generated_at": float(payload.get("generated_at", 0.0) or 0.0),
        "commands": {},
        "system_capabilities": [],
    }
    for name, row in commands_raw.items():
        if not isinstance(row, dict):
            continue
        cmd_name = str(name).strip().lower()
        if not cmd_name:
            continue
        aliases = row.get("aliases", [])
        if not isinstance(aliases, list):
            aliases = []
        examples = row.get("examples", [])
        if not isinstance(examples, list):
            examples = []
        triggers = row.get("nl_triggers", [])
        if not isinstance(triggers, list):
            triggers = []
        permission_hints = row.get("permission_hints", [])
        if not isinstance(permission_hints, list):
            permission_hints = []
        domain = str(row.get("domain", "utility")).strip().lower()
        if domain not in CAPABILITY_DOMAINS:
            domain = "utility"
        sanitized["commands"][cmd_name] = {
            "name": cmd_name,
            "aliases": sorted({str(item).strip().lower() for item in aliases if str(item).strip()})[:10],
            "domain": domain,
            "summary": str(row.get("summary", "")).strip()[:280],
            "mod_only": bool(row.get("mod_only", False)),
            "examples": [str(item).strip()[:140] for item in examples if str(item).strip()][:6],
            "nl_triggers": [str(item).strip().lower()[:50] for item in triggers if str(item).strip()][:12],
            "usage": str(row.get("usage", f"{PREFIX}{cmd_name}")).strip()[:180],
            "signature": str(row.get("signature", "")).strip()[:160],
            "hidden": bool(row.get("hidden", False)),
            "command_type": str(row.get("command_type", "prefix")).strip().lower()[:20],
            "permission_hints": [str(item).strip().lower()[:30] for item in permission_hints if str(item).strip()][:8],
        }
    for row in system_raw:
        if not isinstance(row, dict):
            continue
        capability_id = str(row.get("id", "")).strip().lower()
        if not capability_id:
            continue
        domain = str(row.get("domain", "utility")).strip().lower()
        if domain not in CAPABILITY_DOMAINS:
            domain = "utility"
        examples = row.get("examples", [])
        if not isinstance(examples, list):
            examples = []
        triggers = row.get("nl_triggers", [])
        if not isinstance(triggers, list):
            triggers = []
        sanitized["system_capabilities"].append(
            {
                "id": capability_id,
                "domain": domain,
                "summary": str(row.get("summary", "")).strip()[:280],
                "mod_only": bool(row.get("mod_only", False)),
                "examples": [str(item).strip()[:140] for item in examples if str(item).strip()][:6],
                "nl_triggers": [str(item).strip().lower()[:50] for item in triggers if str(item).strip()][:12],
            }
        )
    return sanitized


def load_capabilities_overrides(*, force: bool = False) -> dict[str, Any]:
    global CAPABILITIES_OVERRIDES_CACHE
    global CAPABILITIES_OVERRIDES_CACHE_TS
    global CAPABILITIES_OVERRIDES_CACHE_MTIME
    ensure_data_files()
    now = time.monotonic()
    mtime = STORAGE.version(CAPABILITIES_OVERRIDES_KEY)
    mtime_unchanged = abs(mtime - CAPABILITIES_OVERRIDES_CACHE_MTIME) < 1e-6
    if (
        not force
        and CAPABILITIES_OVERRIDES_CACHE is not None
        and mtime_unchanged
        and (now - CAPABILITIES_OVERRIDES_CACHE_TS) < CAPABILITIES_CACHE_TTL_SECONDS
    ):
        return CAPABILITIES_OVERRIDES_CACHE
    raw = STORAGE.get(CAPABILITIES_OVERRIDES_KEY)
    if raw is None:
        print("[CAPABILITY OVERRIDES LOAD ERROR] stored overrides are missing or unreadable; using defaults")
        raw = _default_capabilities_overrides_payload()
        STORAGE.set(CAPABILITIES_OVERRIDES_KEY, raw)
    payload = _sanitize_capabilities_overrides_payload(raw)
    CAPABILITIES_OVERRIDES_CACHE = payload
    CAPABILITIES_OVERRIDES_CACHE_TS = now
    CAPABILITIES_OVERRIDES_CACHE_MTIME = STORAGE.version(CAPABILITIES_OVERRIDES_KEY)
    return payload


def _capability_domain_from_command(command_name: str, aliases: list[str]) -> str:
    name = command_name.lower().strip()
    alias_set = {item.lower().strip() for item in aliases}
    token_set = {name, *alias_set}

    moderation = {
        "pb", "pba", "clear", "bulkdelete", "kick", "ban", "unban", "mute", "unmute",
        "lock", "unlock", "slowmode", "warn", "warnings", "clearwarns", "setmodlog",
        "clearmodlog", "reloadbadwords", "automod", "aiguard", "aimodmode", "modqueue",
        "case", "override", "appeal", "modguard", "escalation",
    }
    music = {"join", "leave", "play", "skip", "pause", "resume", "stop", "queue", "nowplaying"}
    business = {
        "balance", "dailyclaim", "portfolio", "networth", "stocks", "market", "commodities",
        "crypto", "buycommodity", "sellcommodity", "buycrypto", "sellcrypto", "startbiz",
        "mybiz", "bizhire", "bizfire", "bizexpand", "salary", "taxes", "filetax", "credit",
        "markethalt", "economystatus", "bizhelp", "guide", "buy", "sell", "plots", "buyplot",
        "upgrade", "properties", "sellproperty", "buyproperty", "loan", "takeloan", "repay",
        "debts", "trade", "trade_accept", "trade_decline", "auction_start", "bid", "auctions",
        "bizleaderboard", "bizprofile", "marketnews", "ledger",
    }
    ai = {
        "aimodel", "aimodels", "aireset", "psych", "myvibe", "vibe", "vibecheck", "roast",
        "serverlore", "crush", "analyze", "lie_detector", "futureme", "rizzcoach", "argument",
        "debate", "ai", "ask", "aisummary", "catchup", "catchupchannel", "serverinsights",
    }
    engagement = {"rank", "leaderboard", "streak", "daily", "quests", "event", "engagementhub", "autoloops", "questmode", "engagementtz", "engagementlimits"}
    utility = {"help", "say", "cat", "cats", "food", "ping", "avatar", "userinfo", "serverinfo", "poll", "snipe", "remind", "exclude", "wipe", "welcomeconcierge", "setintrochannel", "clearintrochannel"}

    if token_set.intersection(moderation):
        return "moderation"
    if token_set.intersection(music):
        return "music"
    if token_set.intersection(business):
        return "business"
    if token_set.intersection(engagement):
        return "engagement"
    if token_set.intersection(ai):
        return "ai"
    if token_set.intersection(utility):
        return "utility"
    if any(term in name for term in ("roast", "vibe", "rizz", "crush")):
        return "fun"
    return "utility"


def _capability_mod_only_from_command(command: commands.Command, command_name: str) -> bool:
    known_mod_only = {
        "pb", "pba", "clear", "bulkdelete", "kick", "ban", "unban", "mute", "unmute",
        "lock", "unlock", "slowmode", "warn", "warnings", "clearwarns", "setmodlog",
        "clearmodlog", "reloadbadwords", "automod", "aiguard", "aimodmode", "modqueue",
        "case", "override", "modguard", "escalation", "crushgame",
        "welcomeconcierge", "setintrochannel", "clearintrochannel",
        "engagementlimits", "engagementhub", "autoloops", "questmode", "engagementtz",
        "markethalt", "serverinsights", "say",
    }
    if command_name in known_mod_only:
        return True
    checks_blob = " ".join(str(check).lower() for check in getattr(command, "checks", []))
    permission_markers = (
        "manage_guild", "manage_messages", "moderate_members", "kick_members",
        "ban_members", "administrator", "has_permissions",
    )
    return any(marker in checks_blob for marker in permission_markers)


def _capability_permission_hints(command: commands.Command, mod_only: bool) -> list[str]:
    checks_blob = " ".join(str(check).lower() for check in getattr(command, "checks", []))
    hints: list[str] = []
    marker_to_hint = {
        "manage_guild": "manage_guild",
        "manage_messages": "manage_messages",
        "moderate_members": "moderate_members",
        "kick_members": "kick_members",
        "ban_members": "ban_members",
        "administrator": "administrator",
    }
    for marker, hint in marker_to_hint.items():
        if marker in checks_blob and hint not in hints:
            hints.append(hint)
    if mod_only and not hints:
        hints.append("moderator")
    return hints


def _command_usage(command: commands.Command, name: str) -> tuple[str, str]:
    signature = " ".join((command.signature or "").split()).strip()
    usage = f"{PREFIX}{name}"
    if signature:
        usage = f"{usage} {signature}"
    return usage.strip(), signature


def _default_capability_summary(command_name: str, domain: str) -> str:
    readable = command_name.replace("_", " ")
    if domain == "moderation":
        return f"Moderation command for {readable} actions."
    if domain == "music":
        return f"Music control command for {readable}."
    if domain == "business":
        return f"Business economy command for {readable}."
    if domain == "ai":
        return f"AI feature command for {readable}."
    if domain == "engagement":
        return f"Engagement and activity command for {readable}."
    if domain == "fun":
        return f"Fun/social feature command for {readable}."
    return f"Utility command for {readable}."


def _discover_capability_commands() -> dict[str, dict[str, Any]]:
    discovered: dict[str, dict[str, Any]] = {}
    for command in bot.commands:
        if not isinstance(command, commands.Command):
            continue
        name = str(command.name).strip().lower()
        if not name:
            continue
        aliases = sorted(
            {
                str(alias).strip().lower()
                for alias in getattr(command, "aliases", [])
                if str(alias).strip()
            }
        )
        usage, signature = _command_usage(command, name)
        domain = _capability_domain_from_command(name, aliases)
        mod_only = _capability_mod_only_from_command(command, name)
        permission_hints = _capability_permission_hints(command, mod_only)
        help_text = (getattr(command, "help", "") or "").strip()
        summary = help_text.splitlines()[0].strip()[:280] if help_text else _default_capability_summary(name, domain)
        nl_triggers = sorted(
            {
                name,
                name.replace("_", " "),
                domain,
                *aliases,
            }
        )[:12]
        discovered[name] = {
            "name": name,
            "aliases": aliases,
            "domain": domain,
            "summary": summary,
            "mod_only": mod_only,
            "examples": [usage],
            "nl_triggers": nl_triggers,
            "usage": usage,
            "signature": signature,
            "hidden": bool(getattr(command, "hidden", False)),
            "command_type": "hybrid" if isinstance(command, commands.HybridCommand) else "prefix",
            "permission_hints": permission_hints,
        }
    return discovered


def _merge_capability_commands(
    discovered: dict[str, dict[str, Any]],
    overrides: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    override_commands = overrides.get("commands", {})
    if not isinstance(override_commands, dict):
        override_commands = {}

    for name, base in discovered.items():
        row = dict(base)
        override = override_commands.get(name)
        if isinstance(override, dict):
            if "domain" in override:
                domain = str(override.get("domain", row["domain"])).strip().lower()
                row["domain"] = domain if domain in CAPABILITY_DOMAINS else row["domain"]
            if "summary" in override and str(override.get("summary", "")).strip():
                row["summary"] = str(override.get("summary", "")).strip()[:280]
            if "mod_only" in override:
                row["mod_only"] = bool(override.get("mod_only"))
            override_examples = override.get("examples", [])
            if isinstance(override_examples, list) and override_examples:
                row["examples"] = [str(item).strip()[:140] for item in override_examples if str(item).strip()][:6]
            override_triggers = override.get("nl_triggers", [])
            if isinstance(override_triggers, list) and override_triggers:
                row["nl_triggers"] = sorted(
                    {
                        *row.get("nl_triggers", []),
                        *[str(item).strip().lower()[:50] for item in override_triggers if str(item).strip()],
                    }
                )[:16]
        merged[name] = row

    for name, override in override_commands.items():
        if name in merged or not isinstance(override, dict):
            continue
        domain = str(override.get("domain", "utility")).strip().lower()
        if domain not in CAPABILITY_DOMAINS:
            domain = "utility"
        usage = f"{PREFIX}{name}"
        examples = override.get("examples", [])
        if not isinstance(examples, list):
            examples = []
        triggers = override.get("nl_triggers", [])
        if not isinstance(triggers, list):
            triggers = []
        merged[name] = {
            "name": name,
            "aliases": [],
            "domain": domain,
            "summary": str(override.get("summary", _default_capability_summary(name, domain))).strip()[:280],
            "mod_only": bool(override.get("mod_only", False)),
            "examples": [str(item).strip()[:140] for item in examples if str(item).strip()] or [usage],
            "nl_triggers": [str(item).strip().lower()[:50] for item in triggers if str(item).strip()][:12],
            "usage": usage,
            "signature": "",
            "hidden": False,
            "command_type": "manual",
            "permission_hints": ["moderator"] if bool(override.get("mod_only", False)) else [],
        }
    return merged


def rebuild_capabilities_catalog(*, force_overrides_reload: bool = False) -> dict[str, Any]:
    global CAPABILITIES_CATALOG_CACHE
    global CAPABILITIES_CATALOG_CACHE_TS
    global CAPABILITIES_CATALOG_CACHE_MTIME
    try:
        overrides = load_capabilities_overrides(force=force_overrides_reload)
        discovered = _discover_capability_commands()
        merged_commands = _merge_capability_commands(discovered, overrides)
        system_caps = overrides.get("system_capabilities", [])
        if not isinstance(system_caps, list):
            system_caps = []
        payload = _sanitize_capabilities_catalog_payload(
            {
                "schema_version": 1,
                "generated_at": time.time(),
                "commands": merged_commands,
                "system_capabilities": system_caps,
            }
        )
        if not STORAGE.set(CAPABILITIES_CATALOG_KEY, payload):
            print("[CAPABILITY CATALOG WRITE ERROR] could not persist the rebuilt catalog")
        CAPABILITIES_CATALOG_CACHE = payload
        CAPABILITIES_CATALOG_CACHE_TS = time.monotonic()
        CAPABILITIES_CATALOG_CACHE_MTIME = STORAGE.version(CAPABILITIES_CATALOG_KEY)
        return payload
    except Exception as error:
        print(f"[CAPABILITY CATALOG REBUILD ERROR] {error}")
        fallback = _default_capabilities_catalog_payload()
        CAPABILITIES_CATALOG_CACHE = fallback
        CAPABILITIES_CATALOG_CACHE_TS = time.monotonic()
        return fallback


def get_capabilities_catalog(*, force_refresh: bool = False) -> dict[str, Any]:
    global CAPABILITIES_CATALOG_CACHE
    global CAPABILITIES_CATALOG_CACHE_TS
    global CAPABILITIES_CATALOG_CACHE_MTIME
    ensure_data_files()
    now = time.monotonic()
    mtime = STORAGE.version(CAPABILITIES_CATALOG_KEY)
    mtime_unchanged = abs(mtime - CAPABILITIES_CATALOG_CACHE_MTIME) < 1e-6
    cache_fresh = (
        CAPABILITIES_CATALOG_CACHE is not None
        and mtime_unchanged
        and (now - CAPABILITIES_CATALOG_CACHE_TS) < CAPABILITIES_CACHE_TTL_SECONDS
    )
    if not force_refresh and cache_fresh:
        return CAPABILITIES_CATALOG_CACHE

    overrides_mtime = STORAGE.version(CAPABILITIES_OVERRIDES_KEY)
    should_rebuild = (
        force_refresh
        or CAPABILITIES_CATALOG_CACHE is None
        or not mtime_unchanged
        or abs(overrides_mtime - CAPABILITIES_OVERRIDES_CACHE_MTIME) > 1e-6
    )
    if should_rebuild:
        return rebuild_capabilities_catalog(
            force_overrides_reload=(abs(overrides_mtime - CAPABILITIES_OVERRIDES_CACHE_MTIME) > 1e-6)
        )

    payload = STORAGE.get(CAPABILITIES_CATALOG_KEY)
    if payload is None:
        print("[CAPABILITY CATALOG LOAD ERROR] stored catalog is missing or unreadable; rebuilding")
        return rebuild_capabilities_catalog(force_overrides_reload=True)
    sanitized = _sanitize_capabilities_catalog_payload(payload)
    CAPABILITIES_CATALOG_CACHE = sanitized
    CAPABILITIES_CATALOG_CACHE_TS = now
    CAPABILITIES_CATALOG_CACHE_MTIME = mtime
    return sanitized


def parse_capability_query(text: str, catalog: dict[str, Any]) -> dict[str, Any] | None:
    normalized = " ".join(text.lower().split()).strip()
    if not normalized:
        return None
    tokens = set(_help_tokenize(normalized))
    has_intent = any(pattern.search(normalized) is not None for pattern in CAPABILITY_INTENT_PATTERNS)
    commands_raw = catalog.get("commands", {})
    if not isinstance(commands_raw, dict):
        commands_raw = {}
    command_hits: set[str] = set()
    for name, row in commands_raw.items():
        if not isinstance(row, dict):
            continue
        if name in tokens:
            command_hits.add(name)
        for alias in row.get("aliases", []):
            if str(alias).strip().lower() in tokens:
                command_hits.add(name)
    domain_focus: str | None = None
    domain_score = -1
    for domain, terms in CAPABILITY_QUERY_DOMAIN_TERMS.items():
        score = len(tokens.intersection(terms))
        if score > domain_score:
            domain_score = score
            domain_focus = domain
    if domain_score <= 0:
        domain_focus = None

    if not has_intent:
        if command_hits:
            has_intent = bool(re.search(r"\bhow\b|\buse\b|\bcommand\b|\bcmd\b|\bdo i\b", normalized))
        elif domain_focus is not None:
            has_intent = bool(re.search(r"\bhelp\b|\bcommands?\b|\bcapabilit(?:y|ies)\b|\bhow\b", normalized))
    if not has_intent:
        return None

    return {
        "query": normalized,
        "tokens": tokens,
        "domain_focus": domain_focus,
        "command_hits": sorted(command_hits),
    }


def _capability_score_command(
    entry: dict[str, Any],
    query: dict[str, Any],
) -> float:
    score = 0.0
    tokens: set[str] = query["tokens"]
    query_text = str(query.get("query", ""))
    domain_focus: str | None = query["domain_focus"]
    command_hits: set[str] = set(query["command_hits"])
    name = str(entry.get("name", "")).lower()
    aliases = {str(item).lower() for item in entry.get("aliases", [])}
    domain = str(entry.get("domain", "utility")).lower()
    triggers = {str(item).lower() for item in entry.get("nl_triggers", [])}
    summary_tokens = set(_help_tokenize(str(entry.get("summary", ""))))
    entry_tokens = {name, *aliases, *triggers, domain, *summary_tokens}

    if name in command_hits:
        score += 8.0
    elif aliases.intersection(command_hits):
        score += 6.0
    overlap = len(tokens.intersection(entry_tokens))
    score += min(9.0, overlap * 0.9)
    for trigger in triggers:
        if " " in trigger and trigger and trigger in query_text:
            score += 2.2
    if domain_focus is not None:
        if domain == domain_focus:
            score += 3.5
        else:
            score -= 0.8
    if bool(entry.get("hidden", False)):
        score -= 1.5
    return score


def _capability_score_system(
    entry: dict[str, Any],
    query: dict[str, Any],
) -> float:
    score = 0.0
    tokens: set[str] = query["tokens"]
    query_text = str(query.get("query", ""))
    domain_focus: str | None = query["domain_focus"]
    domain = str(entry.get("domain", "utility")).lower()
    summary_tokens = set(_help_tokenize(str(entry.get("summary", ""))))
    triggers = {str(item).lower() for item in entry.get("nl_triggers", [])}
    overlap = len(tokens.intersection({domain, *summary_tokens, *triggers}))
    score += min(8.0, overlap * 1.0)
    for trigger in triggers:
        if " " in trigger and trigger and trigger in query_text:
            score += 2.0
    if domain_focus is not None:
        if domain == domain_focus:
            score += 3.0
        else:
            score -= 0.6
    return score


def build_capability_query_response(
    query: dict[str, Any],
    catalog: dict[str, Any],
    *,
    requester_is_mod: bool,
) -> str:
    commands_raw = catalog.get("commands", {})
    if not isinstance(commands_raw, dict) or not commands_raw:
        return (
            "I couldn't load my capability catalog right now. "
            f"Use `{PREFIX}help` for the full command list."
        )
    system_raw = catalog.get("system_capabilities", [])
    if not isinstance(system_raw, list):
        system_raw = []

    scored_commands: list[tuple[float, dict[str, Any]]] = []
    for row in commands_raw.values():
        if not isinstance(row, dict):
            continue
        score = _capability_score_command(row, query)
        if score > 0:
            scored_commands.append((score, row))
    scored_commands.sort(key=lambda item: item[0], reverse=True)

    scored_system: list[tuple[float, dict[str, Any]]] = []
    for row in system_raw:
        if not isinstance(row, dict):
            continue
        score = _capability_score_system(row, query)
        if score > 0:
            scored_system.append((score, row))
    scored_system.sort(key=lambda item: item[0], reverse=True)

    domain_focus = query.get("domain_focus")
    title = "Bell Capabilities"
    if isinstance(domain_focus, str) and domain_focus:
        title = f"Bell {domain_focus.title()} Capabilities"

    lines = [f"**{title}**"]
    if scored_system:
        lines.append("")
        for _, row in scored_system[:2]:
            if bool(row.get("mod_only", False)) and not requester_is_mod:
                lines.append("- Moderator-only capability available. Ask a moderator for command-level details.")
                continue
            summary = str(row.get("summary", "")).strip()
            if summary:
                lines.append(f"- {summary}")
    lines.append("")
    lines.append("**Recommended Commands**")

    recommended = scored_commands[:8]
    if not recommended:
        lines.append(f"- Use `{PREFIX}help` to browse all commands.")
        return "\n".join(lines)

    visible_recommendations = 0
    redacted_count = 0
    for _, row in recommended:
        name = str(row.get("name", "")).strip()
        usage = str(row.get("usage", f"{PREFIX}{name}")).strip()
        summary = str(row.get("summary", "")).strip()
        mod_only = bool(row.get("mod_only", False))
        if mod_only and not requester_is_mod:
            if redacted_count >= 3:
                continue
            high_level = summary or "This action is available to moderators."
            lines.append(f"- Moderator-only capability: {high_level}")
            redacted_count += 1
            visible_recommendations += 1
            if visible_recommendations >= 6:
                break
            continue
        line = f"- `{usage}`"
        if summary:
            line += f" - {summary}"
        lines.append(line)
        examples = row.get("examples", [])
        if isinstance(examples, list) and examples:
            example = str(examples[0]).strip()
            if example and example != usage:
                lines.append(f"  Example: `{example}`")
        visible_recommendations += 1
        if visible_recommendations >= 6:
            break

    command_hits = query.get("command_hits", [])
    best_next: dict[str, Any] | None = None
    if isinstance(command_hits, list) and command_hits:
        hit_set = {str(item).strip().lower() for item in command_hits}
        for _, row in scored_commands:
            if str(row.get("name", "")).lower() in hit_set:
                best_next = row
                break
    if best_next is None and scored_commands:
        best_next = scored_commands[0][1]

    if isinstance(best_next, dict):
        mod_only = bool(best_next.get("mod_only", False))
        lines.append("")
        if mod_only and not requester_is_mod:
            lines.append("Best next step: ask a moderator to run the relevant moderation command.")
        else:
            usage = str(best_next.get("usage", "")).strip()
            if usage:
                lines.append(f"Best next command: `{usage}`")
            permission_hints = best_next.get("permission_hints", [])
            if isinstance(permission_hints, list) and permission_hints:
                lines.append(f"Permission note: `{', '.join(str(item) for item in permission_hints[:4])}`")

    lines.append("")
    lines.append(
        "Ask a follow-up like: `bell how do I use this command step by step` or "
        f"`bell show {domain_focus or 'moderation'} commands`."
    )
    return "\n".join(lines)


async def send_capability_query_response(
    target: discord.abc.Messageable,
    text: str,
    *,
    requester_is_mod: bool,
) -> bool:
    try:
        catalog = get_capabilities_catalog()
    except Exception as error:
        print(f"[CAPABILITY CATALOG ACCESS ERROR] {error}")
        return False
    commands_raw = catalog.get("commands", {})
    if not isinstance(commands_raw, dict) or not commands_raw:
        print("[CAPABILITY CATALOG RECOVERY] Missing or empty catalog, falling back to guide handler.")
        return False
    query = parse_capability_query(text, catalog)
    if query is None:
        return False
    response = build_capability_query_response(
        query,
        catalog,
        requester_is_mod=requester_is_mod,
    )
    await send_chunked(target, response)
    return True


BOT_GUIDE_KB: list[dict[str, object]] = [
    {
        "id": "bot-start",
        "title": "Start Using Bell",
        "keywords": (
            "start",
            "begin",
            "how to use",
            "commands",
            "prefix",
            "help",
            "what can you do",
        ),
        "content": (
            f"Bell uses prefix `{PREFIX}`.\n"
            f"Run `{PREFIX}help` for the full command list.\n"
            "You can also talk naturally by addressing Bell (mention Bell or start with `bell ...`).\n"
            f"Examples: `{PREFIX}ping`, `bell show my avatar`, `bell how do I start the game`."
        ),
    },
    {
        "id": "moderation",
        "title": "Moderation Features (Mod-Only)",
        "keywords": (
            "moderation",
            "mod",
            "timeout",
            "mute",
            "ban",
            "kick",
            "clear",
            "purge",
            "pb",
            "pba",
            "automod",
        ),
        "content": (
            f"Cleanup: `{PREFIX}pb`, `{PREFIX}pba`, `{PREFIX}clear <amount>`, `{PREFIX}bulkdelete <#channel> <amount>`.\n"
            f"Member actions: `{PREFIX}mute`, `{PREFIX}unmute`, `{PREFIX}kick`, `{PREFIX}ban`, `{PREFIX}unban`.\n"
            f"Channel controls: `{PREFIX}lock`, `{PREFIX}unlock`, `{PREFIX}slowmode`.\n"
            f"AutoMod controls: `{PREFIX}automod <on|off|status>` and conversational `bell turn on automod`."
        ),
    },
    {
        "id": "ai-chat",
        "title": "AI Chat and Summaries",
        "keywords": (
            "ai",
            "chatgpt",
            "ask",
            "summary",
            "summarize",
            "aisummary",
            "aimodel",
        ),
        "content": (
            f"Direct AI: `{PREFIX}ai <prompt>`.\n"
            f"Channel summary: `{PREFIX}aisummary [count]` or natural `bell summarise 50 msgs`.\n"
            f"Model checks: `{PREFIX}aimodel` and `{PREFIX}aimodels`.\n"
            f"Reset memory: `{PREFIX}aireset`."
        ),
    },
    {
        "id": "psych-mode",
        "title": "Psych Support Mode",
        "keywords": (
            "psych",
            "psychologist",
            "mental support",
            "listen mode",
            "counseling",
        ),
        "content": (
            f"Use `{PREFIX}psych start` to begin a listen-first support session.\n"
            f"Control with `{PREFIX}psych status`, `{PREFIX}psych reset`, `{PREFIX}psych stop`.\n"
            "In active mode Bell waits for a pause, then replies with context-aware support."
        ),
    },
    {
        "id": "music",
        "title": "Music Playback",
        "keywords": (
            "music",
            "play",
            "song",
            "spotify",
            "youtube",
            "voice",
            "queue",
        ),
        "content": (
            f"Join with `{PREFIX}join`, play with `{PREFIX}play <query/link>`, leave with `{PREFIX}leave`.\n"
            f"Playback controls: `{PREFIX}pause`, `{PREFIX}resume`, `{PREFIX}skip`, `{PREFIX}stop`, `{PREFIX}queue`.\n"
            "Spotify links are resolved to playable sources. Host must have ffmpeg and PyNaCl installed."
        ),
    },
    {
        "id": "fun-social",
        "title": "Fun Social Features",
        "keywords": (
            "roast",
            "crush",
            "analyze",
            "vibe",
            "vibecheck",
            "serverlore",
            "futureme",
            "rizz",
            "debate",
            "argument",
        ),
        "content": (
            f"Popular commands: `{PREFIX}roast`, `{PREFIX}crush`, `{PREFIX}analyze`, `{PREFIX}vibe`, `{PREFIX}vibecheck`.\n"
            f"Other AI fun: `{PREFIX}serverlore`, `{PREFIX}futureme`, `{PREFIX}rizzcoach`, `{PREFIX}debate`, `{PREFIX}argument`.\n"
            "Most fun commands also work conversationally when you address Bell.\n"
            f"Opt out of fun features any time with `{PREFIX}exclude`; delete your stored fun data with `{PREFIX}wipe`."
        ),
    },
    {
        "id": "engagement",
        "title": "Engagement and XP",
        "keywords": (
            "xp",
            "rank",
            "leaderboard",
            "daily",
            "quests",
            "streak",
            "event",
            "catchup",
            "serverinsights",
        ),
        "content": (
            f"Progress commands: `{PREFIX}rank`, `{PREFIX}leaderboard`, `{PREFIX}streak`, `{PREFIX}daily`, `{PREFIX}quests`.\n"
            f"Events: `{PREFIX}event start <trivia|hottake|caption>`, `{PREFIX}event status`, `{PREFIX}event stop`.\n"
            f"Recap/insights: `{PREFIX}catchup [hours]`, `{PREFIX}serverinsights [hours]` (mods only)."
        ),
    },
    {
        "id": "business",
        "title": "Business Economy Guidance",
        "keywords": (
            "business",
            "economy",
            "stocks",
            "loan",
            "tax",
            "plot",
            "portfolio",
            "networth",
            "bizhelp",
        ),
        "content": (
            f"Use `{PREFIX}bizhelp <question>` for detailed economy walkthroughs.\n"
            "Natural examples: `bell how do I start the game`, `bell explain loans`, `bell how taxes work`.\n"
            f"Core economy commands include `{PREFIX}balance`, `{PREFIX}dailyclaim`, `{PREFIX}portfolio`, `{PREFIX}buy`, `{PREFIX}sell`."
        ),
    },
]

BOT_GUIDE_INTENT_TERMS: tuple[str, ...] = (
    "help",
    "guide",
    "how",
    "explain",
    "tell",
    "tutorial",
    "walkthrough",
    "setup",
    "configure",
    "start",
    "begin",
    "commands",
    "command",
    "use",
    "tips",
)

BOT_GUIDE_DOMAIN_TERMS: tuple[str, ...] = (
    "bell",
    "bot",
    "command",
    "commands",
    "moderation",
    "automod",
    "timeout",
    "mute",
    "clear",
    "music",
    "play",
    "avatar",
    "pfp",
    "ai",
    "summary",
    "catchup",
    "insights",
    "psych",
    "vibe",
    "crush",
    "roast",
    "analyze",
    "xp",
    "rank",
    "leaderboard",
    "quest",
    "business",
    "economy",
    "stock",
    "loan",
    "tax",
    "property",
    "plot",
    "auction",
    "trade",
)


def parse_general_guide_query(text: str) -> str | None:
    normalized = " ".join(text.lower().split()).strip()
    if not normalized:
        return None

    if re.match(
        r"^(clear|mute|ban|kick|buy|sell|repay|takeloan|bid)\b\s+\d",
        normalized,
    ):
        return None

    if normalized in {"help", "commands", "what can you do", "show commands"}:
        return normalized

    asks_explanatory_what = bool(
        re.search(r"^(what(?:'s| is| are)|tell me about)\b", normalized)
    )
    asks_personal_status = bool(
        re.search(
            r"\b(what(?:'s| is)?|show|check|get)\s+my\b.*\b(rank|leaderboard|streak|daily|quest|balance|portfolio|networth|debt|tax)\b",
            normalized,
        )
    )
    asks_question = normalized.endswith("?")
    question_has_help_cue = bool(
        re.search(r"\b(how|what|why|when|where|can|should)\b", normalized)
    )
    has_intent = any(term in normalized for term in BOT_GUIDE_INTENT_TERMS)
    has_domain = any(term in normalized for term in BOT_GUIDE_DOMAIN_TERMS)
    if asks_personal_status:
        return None
    if has_domain and (
        has_intent or asks_explanatory_what or (asks_question and question_has_help_cue)
    ):
        return normalized
    return None


def retrieve_general_guide_chunks(query: str, *, limit: int = 3) -> list[dict[str, object]]:
    normalized = " ".join(query.lower().split()).strip()
    query_tokens = set(_help_tokenize(normalized))
    ranked: list[tuple[float, dict[str, object]]] = []

    for chunk in BOT_GUIDE_KB:
        score = 0.0
        keywords = chunk.get("keywords", ())
        if isinstance(keywords, tuple):
            for keyword in keywords:
                kw = str(keyword).lower().strip()
                if not kw:
                    continue
                if " " in kw:
                    if kw in normalized:
                        score += 4.2
                elif kw in query_tokens or kw in normalized:
                    score += 2.2
        doc_text = f"{chunk.get('title', '')} {chunk.get('content', '')}"
        overlap = len(query_tokens.intersection(_help_tokenize(doc_text)))
        score += min(5.0, overlap * 0.7)

        if str(chunk.get("id")) == "bot-start":
            if {"start", "begin", "help", "commands"}.intersection(query_tokens):
                score += 5.0
        if str(chunk.get("id")) == "business":
            if {"business", "economy", "stock", "loan", "tax", "plot"}.intersection(query_tokens):
                score += 3.0

        if score > 0:
            ranked.append((score, chunk))

    if not ranked:
        default_chunks: list[dict[str, object]] = []
        for wanted in ("bot-start", "business"):
            found = next((entry for entry in BOT_GUIDE_KB if entry.get("id") == wanted), None)
            if found is not None:
                default_chunks.append(found)
        return default_chunks[: max(1, limit)]

    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = [item[1] for item in ranked[: max(1, limit)]]
    deduped: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for entry in selected:
        entry_id = str(entry.get("id", ""))
        if entry_id in seen_ids:
            continue
        seen_ids.add(entry_id)
        deduped.append(entry)
    return deduped


def build_general_guide_response(query: str, chunks: list[dict[str, object]]) -> str:
    if not chunks:
        return (
            f"I could not map that request yet. Use `{PREFIX}help` for the full command list, "
            f"or ask `bell how do I start the game`."
        )

    lines = [f"Guide for: `{query}`", ""]
    for chunk in chunks:
        title = str(chunk.get("title", "Guide")).strip()
        content = str(chunk.get("content", "")).strip().replace("{PREFIX}", PREFIX)
        lines.append(f"**{title}**")
        lines.append(content)
        lines.append("")
    lines.append(
        f"Ask follow-ups naturally, for example: `bell how does automod work`, "
        f"`bell explain music setup`, `bell explain business loans`."
    )
    return "\n".join(lines).strip()


async def send_general_guide_query_response(
    target: discord.abc.Messageable, query: str
) -> None:
    chunks = retrieve_general_guide_chunks(query, limit=4)
    response = build_general_guide_response(query, chunks)
    await send_chunked(target, response)


async def handle_active_argument_mode_turn(message: discord.Message) -> bool:
    if message.guild is None or not isinstance(message.author, discord.Member):
        return False
    if not isinstance(message.channel, discord.TextChannel):
        return False

    session = get_argument_session(message.channel.id, message.author.id)
    if session is None:
        return False

    addressed_text = strip_bot_address_prefix(message)
    if addressed_text and argument_stop_requested(addressed_text):
        stop_argument_session(message.channel.id, message.author.id)
        await message.channel.send("Argument mode stopped. Say `bell argument <topic>` to start again.")
        return True

    user_point = message.content.strip()
    if not user_point:
        return False

    topic = str(session.get("topic", "the topic"))
    side = str(session.get("side", "PRO"))
    history = session.get("history")
    if not isinstance(history, list):
        history = []
        session["history"] = history

    history_text = "\n".join(str(line)[:260] for line in history[-8:])
    prompt = (
        "You are in an ongoing Discord argument mode.\n"
        "Counter the user's latest point directly.\n"
        "Tone: sharp, witty, non-hateful, no slurs, no threats.\n"
        "Output: one compact rebuttal paragraph + 2 quick bullet counters.\n\n"
        f"Topic: {topic}\n"
        f"Your side: {side}\n"
        f"User latest point: {user_point[:420]}\n"
        f"Recent debate context:\n{history_text or '(none yet)'}"
    )

    async with message.channel.typing():
        try:
            reply = await request_fun_ai(
                prompt,
                max_tokens=ARGUMENT_MODE_REPLY_TOKENS,
                temperature=0.82,
                policy_key="argument",
            )
        except Exception as error:
            print(f"[ARGUMENT MODE TURN ERROR] {error}")
            await message.channel.send(friendly_ai_error(error))
            return True

    history.append(f"User: {user_point[:220]}")
    history.append(f"Bell: {reply[:220]}")
    session["turns"] = int(session.get("turns", 0)) + 1
    session["last_activity"] = time.monotonic()

    if int(session["turns"]) >= ARGUMENT_MODE_MAX_TURNS:
        stop_argument_session(message.channel.id, message.author.id)
        await send_chunked(
            message.channel,
            f"{reply}\n\n_(Argument mode auto-stopped after `{ARGUMENT_MODE_MAX_TURNS}` turns. "
            "Say `bell argument <topic>` to restart.)_",
        )
        return True

    await send_chunked(message.channel, reply)
    return True


async def handle_business_conversational_request(message: discord.Message, text: str) -> bool:
    if message.guild is None or not isinstance(message.author, discord.Member):
        return False
    if not get_guild_business_enabled(message.guild.id):
        return False

    lowered = " ".join(text.lower().split())

    async def _cooldown_ok() -> bool:
        now = time.monotonic()
        last = BUSINESS_LAST_COMMAND_TS.get(message.author.id, 0.0)
        if now - last < BUSINESS_COMMAND_COOLDOWN_SECONDS:
            await message.channel.send(
                f"Slow down. Business cooldown: `{BUSINESS_COMMAND_COOLDOWN_SECONDS}`s.",
                delete_after=4,
            )
            return False
        BUSINESS_LAST_COMMAND_TS[message.author.id] = now
        return True

    if re.search(r"\b(show|my)\b.*\bportfolio\b", lowered) or lowered in {"portfolio", "show portfolio"}:
        if not await _cooldown_ok():
            return True
        async with BUSINESS_STATE_LOCK:
            user = _business_get_user(message.author.id)
            lines = _business_portfolio_lines(user)
            cash = float(user.get("cash", 0.0))
            stock_value = _business_portfolio_value(user)
            commodity_value = _business_asset_portfolio_value(user, "commodity")
            crypto_value = _business_asset_portfolio_value(user, "crypto")
            total_assets = stock_value + commodity_value + crypto_value
        owner_label = f"{message.author.mention} ({message.author.display_name})"
        if not lines:
            await message.channel.send(
                f"**Portfolio - {owner_label}**\n"
                f"Cash: `{_business_money(cash)}`\nNo stock holdings yet."
            )
        else:
            await message.channel.send(
                f"**Portfolio - {owner_label}**\n"
                f"Cash: `{_business_money(cash)}` | Asset value: `{_business_money(total_assets)}`\n"
                + "\n".join(lines)
            )
        return True

    if "market summary" in lowered or lowered in {"market", "show market"}:
        if not await _cooldown_ok():
            return True
        async with BUSINESS_STATE_LOCK:
            news = str(get_business_state()["market"].get("last_news", "No market update yet."))
        await message.channel.send(f"ðŸ“° **Market Summary**\n{news}")
        return True

    if re.search(r"\b(balance|net worth|networth)\b", lowered):
        if not await _cooldown_ok():
            return True
        async with BUSINESS_STATE_LOCK:
            user = _business_get_user(message.author.id)
            cash = float(user.get("cash", 0.0))
            debt = _business_debt_total(user)
            net = _business_networth(message.author.id)
        await message.channel.send(
            f"ðŸ’¼ Cash `{_business_money(cash)}` | Debt `{_business_money(debt)}` | Net worth `{_business_money(net)}`"
        )
        return True

    trade_match = re.search(r"\b(buy|sell)\s+(\d{1,6})\s+([a-z0-9]{2,14})\b", lowered)
    if trade_match:
        if _business_is_user_frozen(message.author.id):
            await message.channel.send("Your business account is frozen by moderators.")
            return True
        if not await _cooldown_ok():
            return True
        action = trade_match.group(1).lower()
        qty = int(trade_match.group(2))
        token = trade_match.group(3)
        asset_type, symbol = _business_resolve_trade_asset(token)
        if asset_type is None or symbol is None:
            await message.channel.send(f"Unknown asset `{token}`.")
            return True
        if _business_market_paused(message.guild.id):
            await message.channel.send("Market is currently paused by admins.")
            return True
        async with BUSINESS_STATE_LOCK:
            if action == "buy":
                ok, msg, total = _business_execute_asset_buy(
                    user_id=message.author.id,
                    guild_id=message.guild.id,
                    asset_type=asset_type,
                    symbol=symbol,
                    qty=qty,
                    source="conversational",
                )
                if not ok:
                    await message.channel.send(msg)
                    return True
                await message.channel.send(f"✅ {msg} Total `{_business_money(total)}`.")
            else:
                ok, msg, net = _business_execute_asset_sell(
                    user_id=message.author.id,
                    guild_id=message.guild.id,
                    asset_type=asset_type,
                    symbol=symbol,
                    qty=qty,
                    source="conversational",
                )
                if not ok:
                    await message.channel.send(msg)
                    return True
                await message.channel.send(f"✅ {msg} Net `{_business_money(net)}`.")
        return True

    if "show my taxes" in lowered or lowered in {"taxes", "show taxes"}:
        if not await _cooldown_ok():
            return True
        async with BUSINESS_STATE_LOCK:
            user = _business_get_user(message.author.id)
            liability = float(user.get("tax_liability", 0.0) or 0.0)
            paid_total = float(user.get("taxes_paid_total", 0.0) or 0.0)
        await message.channel.send(
            f"🧾 Tax liability: `{_business_money(liability)}` | Paid total: `{_business_money(paid_total)}`"
        )
        return True

    file_tax_match = re.search(r"\bfile\s*tax(?:es)?(?:\s+(\d{1,9}))?\b", lowered)
    if file_tax_match:
        if _business_is_user_frozen(message.author.id):
            await message.channel.send("Your business account is frozen by moderators.")
            return True
        if not await _cooldown_ok():
            return True
        requested = float(file_tax_match.group(1)) if file_tax_match.group(1) else None
        async with BUSINESS_STATE_LOCK:
            user = _business_get_user(message.author.id)
            liability = float(user.get("tax_liability", 0.0) or 0.0)
            cash = float(user.get("cash", 0.0) or 0.0)
            if liability <= 0:
                await message.channel.send("You have no outstanding tax liability.")
                return True
            amount = liability if requested is None else max(0.0, requested)
            paid = min(amount, liability, cash)
            if paid <= 0:
                await message.channel.send("Not enough cash to file taxes.")
                return True
            user["cash"] = cash - paid
            user["tax_liability"] = max(0.0, liability - paid)
            user["taxes_paid_total"] = float(user.get("taxes_paid_total", 0.0)) + paid
            _business_add_ledger_entry(
                action="tax_filing",
                user_id=message.author.id,
                amount=-paid,
                details={"source": "conversational", "remaining_liability": float(user.get("tax_liability", 0.0))},
            )
            _mark_business_dirty()
            remaining_liability = float(user.get("tax_liability", 0.0))
        await message.channel.send(
            f"✅ Tax payment recorded: `{_business_money(paid)}` | Remaining: `{_business_money(remaining_liability)}`"
        )
        return True

    if "show my credit" in lowered or lowered in {"credit", "show credit"}:
        if not await _cooldown_ok():
            return True
        async with BUSINESS_STATE_LOCK:
            user = _business_get_user(message.author.id)
            score = int(user.get("credit_score", 650) or 650)
            debt = _business_debt_total(user)
            net = _business_networth(message.author.id)
        await message.channel.send(
            f"📊 Credit score: `{score}` | Debt: `{_business_money(debt)}` | Net worth: `{_business_money(net)}`"
        )
        return True

    start_biz_match = re.search(r"\bstart\s+(?:a\s+)?business\s+([a-z]+)(?:\s+(.+))?$", lowered)
    if start_biz_match:
        if not BUSINESS_ENABLE_PRIVATE_BUSINESSES:
            await message.channel.send("Private businesses are disabled.")
            return True
        if _business_is_user_frozen(message.author.id):
            await message.channel.send("Your business account is frozen by moderators.")
            return True
        if not await _cooldown_ok():
            return True
        biz_type = start_biz_match.group(1).strip().lower()
        explicit_name = start_biz_match.group(2).strip() if start_biz_match.group(2) else ""
        biz_name = explicit_name[:60] if explicit_name else f"{message.author.display_name}'s {biz_type.title()}"
        async with BUSINESS_STATE_LOCK:
            state = get_business_state()
            profiles = state.get("businesses", {}).get("profiles", {})
            profile = profiles.get(biz_type) if isinstance(profiles, dict) else None
            if not isinstance(profile, dict):
                await message.channel.send("Unknown business type.")
                return True
            user = _business_get_user(message.author.id)
            setup_cost = float(profile.get("expand_cost", 7000.0) or 7000.0) * 0.65
            if float(user.get("cash", 0.0)) < setup_cost:
                await message.channel.send(f"Insufficient cash. Need `{_business_money(setup_cost)}`.")
                return True
            biz_id = _business_next_id("biz")
            state["businesses"]["registry"][biz_id] = {
                "id": biz_id,
                "owner_id": message.author.id,
                "name": biz_name,
                "type": biz_type,
                "level": 1,
                "employees": 0,
                "status": "active",
                "debt": 0.0,
                "cash_reserve": 0.0,
                "base_value": setup_cost * 1.15,
                "stress_cycles": 0,
                "created_ts": _business_now_ts(),
            }
            user["cash"] = float(user.get("cash", 0.0)) - setup_cost
            ids = list(user.get("business_ids", []))
            ids.append(biz_id)
            user["business_ids"] = ids
            _business_add_ledger_entry(
                action="business_start",
                user_id=message.author.id,
                amount=-setup_cost,
                details={"biz_id": biz_id, "source": "conversational"},
            )
            _mark_business_dirty()
        await message.channel.send(
            f"🏢 Business started: **{biz_name}** (`{biz_id}`) | Cost `{_business_money(setup_cost)}`"
        )
        return True

    loan_match = re.search(r"\b(take loan|takeloan|loan)\s+(\d{2,9})\b", lowered)
    if loan_match:
        if _business_is_user_frozen(message.author.id):
            await message.channel.send("Your business account is frozen by moderators.")
            return True
        if not await _cooldown_ok():
            return True
        amount = float(loan_match.group(2))
        loan_rate = None
        async with BUSINESS_STATE_LOCK:
            ok, data = _business_issue_loan(message.author.id, amount)
            if ok:
                user = _business_get_user(message.author.id)
                for loan in user.get("loans", []):
                    if isinstance(loan, dict) and str(loan.get("id")) == str(data):
                        loan_rate = float(loan.get("rate", BUSINESS_HOURLY_INTEREST_RATE) or BUSINESS_HOURLY_INTEREST_RATE)
                        break
        if not ok:
            await message.channel.send(data)
            return True
        await message.channel.send(
            f"🏦 Loan approved (`{data}`) for `{_business_money(amount)}` at "
            f"`{(loan_rate if loan_rate is not None else BUSINESS_HOURLY_INTEREST_RATE) * 100:.3f}%` hourly."
        )
        return True

    repay_match = re.search(r"\brepay\s+(\d{2,9})\b", lowered)
    if repay_match:
        if _business_is_user_frozen(message.author.id):
            await message.channel.send("Your business account is frozen by moderators.")
            return True
        if not await _cooldown_ok():
            return True
        amount = float(repay_match.group(1))
        async with BUSINESS_STATE_LOCK:
            paid, closed = _business_repay_loans_from_cash(
                message.author.id,
                amount,
                source="conversational",
            )
        if paid <= 0:
            await message.channel.send("No repayment executed.")
        else:
            await message.channel.send(
                f"âœ… Repaid `{_business_money(paid)}`. Closed loans: `{closed}`."
            )
        return True

    return False


def _normalize_addressed_command_text(text: str) -> tuple[str, str]:
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return "", ""
    head, *rest = normalized.split(maxsplit=1)
    cleaned_head = re.sub(r"^[^\w]+|[^\w]+$", "", head).strip().lower()
    if not cleaned_head:
        return "", ""
    rebuilt = f"{cleaned_head} {rest[0]}".strip() if rest else cleaned_head
    return cleaned_head, rebuilt


async def try_invoke_addressed_command(message: discord.Message, addressed_text: str) -> bool:
    command_name, normalized_text = _normalize_addressed_command_text(addressed_text)
    if not command_name or not normalized_text:
        return False

    command = bot.all_commands.get(command_name)
    if command is None:
        return False

    canonical = str(getattr(command, "name", command_name)).strip().lower()
    root = str(getattr(command, "qualified_name", canonical)).split()[0].strip().lower()
    if canonical in NATURAL_COMMAND_BLOCKLIST or root in NATURAL_COMMAND_BLOCKLIST:
        await message.channel.send(
            f"For safety, natural-language command mode does not allow `{canonical}`. "
            f"Use `{PREFIX}{canonical}` explicitly."
        )
        return True

    proxy = copy.copy(message)
    proxy.content = f"{PREFIX}{normalized_text}"
    ctx = await bot.get_context(proxy)
    if ctx.command is None:
        return False

    invoked_name = str(getattr(ctx.command, "name", "")).strip().lower()
    invoked_root = str(getattr(ctx.command, "qualified_name", invoked_name)).split()[0].strip().lower()
    if invoked_name in NATURAL_COMMAND_BLOCKLIST or invoked_root in NATURAL_COMMAND_BLOCKLIST:
        await message.channel.send(
            f"For safety, natural-language command mode does not allow `{invoked_name}`. "
            f"Use `{PREFIX}{invoked_name}` explicitly."
        )
        return True

    await bot.invoke(ctx)
    return True


async def handle_conversational_request(message: discord.Message) -> bool:
    if message.guild is None or not isinstance(message.author, discord.Member):
        return False

    addressed_text = strip_bot_address_prefix(message)
    text = addressed_text
    if not text and await is_reply_to_bot_message(message):
        text = message.content.strip()
    if not text:
        return False

    lowered = text.lower()

    psych_action, psych_seed = parse_psych_alias_request(text)
    if psych_action is not None:
        await run_psych_action_for_user(
            message.channel,
            channel_id=message.channel.id,
            user_id=message.author.id,
            user_display_name=message.author.display_name,
            action=psych_action,
            seed_text=psych_seed,
        )
        return True

    if addressed_text:
        try:
            if await try_invoke_addressed_command(message, addressed_text):
                return True
        except Exception as error:
            print(f"[NATURAL COMMAND ROUTER ERROR] {error}")

    try:
        if await maybe_handle_reply_translation_request(message, addressed_text):
            return True
    except Exception as error:
        print(f"[REPLY TRANSLATION ROUTER ERROR] {error}")

    business_help_query = parse_business_help_query(text)
    if business_help_query is not None:
        if not await enforce_fun_rate_limit_message(message):
            return True
        await send_business_help_query_response(message.channel, business_help_query)
        return True

    try:
        if await handle_business_conversational_request(message, text):
            return True
    except Exception as error:
        print(f"[BUSINESS CONVERSATIONAL ERROR] {error}")

    capability_query_detected = False
    try:
        capability_catalog = get_capabilities_catalog()
        capability_query_detected = parse_capability_query(text, capability_catalog) is not None
    except Exception as error:
        print(f"[CAPABILITY ROUTER ERROR] {error}")
    if capability_query_detected:
        if not await enforce_fun_rate_limit_message(message):
            return True
        if await send_capability_query_response(
            message.channel,
            text,
            requester_is_mod=is_moderator(message.author),
        ):
            return True

    general_guide_query = parse_general_guide_query(text)
    if general_guide_query is not None:
        if not await enforce_fun_rate_limit_message(message):
            return True
        await send_general_guide_query_response(message.channel, general_guide_query)
        return True

    if re.search(r"\bcats?\b", lowered):
        if not await enforce_fun_rate_limit_message(message):
            return True
        await send_random_cat_image(message.channel)
        return True

    if re.search(r"\bfood\b", lowered):
        if not await enforce_fun_rate_limit_message(message):
            return True
        await send_random_indian_veg_food(message.channel)
        return True

    if argument_stop_requested(text):
        if get_argument_session(message.channel.id, message.author.id) is None:
            await message.channel.send("You don't have an active argument mode in this channel.")
            return True
        stop_argument_session(message.channel.id, message.author.id)
        await message.channel.send("Argument mode stopped.")
        return True

    argument_topic = parse_argument_topic(text)
    if argument_topic is not None:
        if not await enforce_fun_rate_limit_message(message):
            return True
        if not is_ai_configured():
            await message.channel.send(ai_setup_message())
            return True
        side: Literal["PRO", "ANTI"] = random.choice(["PRO", "ANTI"])
        async with message.channel.typing():
            try:
                opening = await generate_argument_opening(argument_topic, side)
            except Exception as error:
                print(f"[CONVERSATIONAL ARGUMENT START ERROR] {error}")
                await message.channel.send(friendly_ai_error(error))
                return True
        stop_psych_session(message.channel.id, message.author.id)
        start_argument_session(message.channel.id, message.author.id, argument_topic, side)
        await send_chunked(
            message.channel,
            f"âš”ï¸ **Argument Mode** ({side}) on **{argument_topic}**\n"
            f"{opening}\n\n"
            "Reply with your points normally in this channel and I'll counter each one. "
            "Say `bell stop argument` to end.",
        )
        return True

    catchup_hours = parse_catchup_hours_request(text)
    if catchup_hours is not None:
        if not await enforce_fun_rate_limit_message(message):
            return True
        await run_catchup_for_channel(message.channel, message.channel, catchup_hours)
        return True

    insights_hours = parse_serverinsights_hours_request(text)
    if insights_hours is not None:
        if not isinstance(message.author, discord.Member) or not is_moderator(message.author):
            await message.channel.send("Only moderators can request server insights.")
            return True
        if not await enforce_fun_rate_limit_message(message):
            return True
        await run_server_insights(message.channel, message.guild, insights_hours)
        return True

    if NL_ENGAGEMENT_TRIGGERS:
        missed_summary = (
            re.search(r"\b(summarise|summarize|summary)\b", lowered) is not None
            and re.search(r"\b(what i missed|missed)\b", lowered) is not None
        )
        if missed_summary:
            if not await enforce_fun_rate_limit_message(message):
                return True
            await run_catchup_for_channel(message.channel, message.channel, 24)
            return True

        if "rank" in lowered:
            snapshot = get_rank_snapshot(message.guild.id, message.author.id)
            all_pos, all_total = get_user_rank_position(message.guild, message.author.id, "alltime")
            await message.channel.send(
                f"ðŸ… **Your Rank Snapshot**\n"
                f"XP: `{snapshot['xp']}` (`{all_pos or '-'} / {all_total or '-'}`)\n"
                f"Daily XP: `{snapshot['daily_xp']}` | Weekly: `{snapshot['weekly_points']}`\n"
                f"Streak: `{snapshot['streak']}` (Best `{snapshot['best_streak']}`)"
            )
            return True

        if "leaderboard" in lowered:
            if not await enforce_fun_rate_limit_message(message):
                return True
            mode = "alltime"
            if "daily" in lowered or "today" in lowered or "day" in lowered:
                mode = "daily"
            elif "weekly" in lowered or "week" in lowered:
                mode = "weekly"
            rows = build_leaderboard_rows(message.guild, normalize_leaderboard_mode(mode), limit=10)
            if not rows:
                await message.channel.send("Leaderboard is empty for now. Start chatting to earn XP.")
                return True
            title = {"daily": "Daily", "weekly": "Weekly", "alltime": "All-time"}[
                normalize_leaderboard_mode(mode)
            ]
            lines = [
                f"{idx}. **{name}** - `{score}`"
                for idx, (_, name, score) in enumerate(rows, start=1)
            ]
            await message.channel.send(f"ðŸ“Š **{title} Leaderboard**\n" + "\n".join(lines))
            return True

        if re.search(r"\bstreak\b", lowered):
            snapshot = get_rank_snapshot(message.guild.id, message.author.id)
            await message.channel.send(
                f"ðŸ”¥ **Your Streak**\n"
                f"Current: `{snapshot['streak']}` day(s)\n"
                f"Best: `{snapshot['best_streak']}` day(s)"
            )
            return True

        if re.search(r"\b(daily|quests?)\b", lowered):
            day_key, lines, completed_count, total_reward = get_user_quest_view(
                message.guild.id, message.author.id
            )
            if not lines:
                await message.channel.send("No quests configured right now.")
                return True
            await message.channel.send(
                f"ðŸ—“ï¸ **Daily Quests ({day_key})**\n"
                + "\n".join(lines)
                + f"\n\nCompleted: `{completed_count}/{len(lines)}` | Potential reward: `{total_reward}` XP"
            )
            return True

    summary_count = parse_conversation_summary_count(text)
    if summary_count is not None:
        if not await enforce_fun_rate_limit_message(message):
            return True
        if not is_ai_configured():
            await message.channel.send(ai_setup_message())
            return True
        if summary_count < 5 or summary_count > 100:
            await message.channel.send("Summary count must be between `5` and `100`.")
            return True

        transcript = await collect_recent_channel_transcript(
            message.channel,
            summary_count,
            exclude_message_ids={message.id},
        )
        if not transcript:
            await message.channel.send("Not enough recent user messages to summarize.")
            return True

        summary_prompt = (
            "Summarize this Discord chat in short bullet points.\n"
            "Include: key topics, decisions, and any action items.\n\n"
            + "\n".join(transcript)
        )
        ai_messages = [
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            {"role": "user", "content": summary_prompt},
        ]

        async with message.channel.typing():
            try:
                summary = await request_ai_completion(
                    ai_messages,
                    max_tokens=AI_SUMMARY_MAX_TOKENS,
                    temperature=0.2,
                    policy_key="summary",
                )
            except Exception as error:
                print(f"[CONVERSATIONAL SUMMARY ERROR] {error}")
                await message.channel.send(friendly_ai_error(error))
                return True

        await send_chunked(
            message.channel,
            f"Summary of last `{len(transcript)}` messages:\n{summary}",
        )
        return True

    if "automod" in lowered:
        if not is_moderator(message.author):
            await message.channel.send("Only moderators can use moderation actions in conversational mode.")
            return True

        if re.search(r"\b(on|enable|enabled|start)\b", lowered) or "turn on" in lowered:
            enabled = True
        elif re.search(r"\b(off|disable|disabled|stop)\b", lowered) or "turn off" in lowered:
            enabled = False
        else:
            enabled = not get_guild_automod_enabled(message.guild.id)

        set_guild_automod_enabled(message.guild.id, enabled)
        state_text = "enabled" if enabled else "disabled"
        await message.channel.send(f"Auto moderation is now **{state_text}** in this server.")
        await send_mod_log(
            message.guild,
            "Config: AutoMod Updated (Conversational)",
            moderator=message.author,
            channel=message.channel,
            details=f"New state: `{state_text}`",
        )
        return True

    if "modguard" in lowered:
        if not is_moderator(message.author):
            await message.channel.send("Only moderators can use moderation actions in conversational mode.")
            return True
        if re.search(r"\b(on|enable|enabled|start)\b", lowered) or "turn on" in lowered:
            enabled = True
        elif re.search(r"\b(off|disable|disabled|stop)\b", lowered) or "turn off" in lowered:
            enabled = False
        else:
            enabled = not get_guild_modguard_enabled(message.guild.id)
        set_guild_modguard_enabled(message.guild.id, enabled)
        await message.channel.send(f"ModGuard is now **{'enabled' if enabled else 'disabled'}**.")
        return True

    if "ping" in lowered:
        latency_ms = round(bot.latency * 1000)
        await message.channel.send(f"Pong! `{latency_ms}ms`")
        return True

    if "server info" in lowered or "serverinfo" in lowered or "show server details" in lowered:
        await send_server_info_embed(message.channel, message.guild)
        return True

    clear_match = re.search(r"\bclear\b.*?\b(\d{1,3})\b.*\bmessages?\b", lowered)
    if clear_match:
        if not is_moderator(message.author):
            await message.channel.send("Only moderators can use moderation actions in conversational mode.")
            return True
        amount = int(clear_match.group(1))
        if amount < 1 or amount > 500:
            await message.channel.send("Amount must be between `1` and `500`.")
            return True
        deleted = await message.channel.purge(limit=amount + 1)
        total_deleted = max(len(deleted) - 1, 0)
        await message.channel.send(f"Deleted `{total_deleted}` messages.", delete_after=6)
        await send_mod_log(
            message.guild,
            "Clear Messages (Conversational)",
            moderator=message.author,
            channel=message.channel,
            details=f"Deleted: `{total_deleted}`",
        )
        return True

    clean_chat_requested = (
        re.search(r"\b(clean|clear)\b", lowered) is not None
        and (
            re.search(r"\b(chat|msgs?|messages?|mess)\b", lowered) is not None
            or lowered in {"clean", "clear"}
        )
    )
    if clean_chat_requested:
        if not is_moderator(message.author):
            await message.channel.send("Only moderators can use moderation actions in conversational mode.")
            return True
        deleted = await purge_recent_bot_webhook_messages(message.channel, trigger_message=message)
        await message.channel.send(f"`{deleted}` messages have been deleted.", delete_after=3)
        await send_mod_log(
            message.guild,
            "Purge Bot Messages (Conversational)",
            moderator=message.author,
            channel=message.channel,
            details=f"Deleted: `{deleted}`",
        )
        return True

    if re.search(r"\b(avatar|pfp)\b", lowered):
        target = extract_conversation_target(message, text, allow_self_avatar=True)
        if target is None:
            await message.channel.send("I could not find that user. Mention them or use an exact name.")
            return True
        await send_avatar_for_member(message.channel, target)
        return True

    is_timeout_action = (
        "timeout" in lowered
        or "mute" in lowered
        or "unmute" in lowered
        or "untimeout" in lowered
    )
    if is_timeout_action:
        if not is_moderator(message.author):
            await message.channel.send("Only moderators can use moderation actions in conversational mode.")
            return True

        target = extract_conversation_target(message, text)
        if target is None:
            await message.channel.send("Mention the user for timeout actions.")
            return True
        if target.bot:
            await message.channel.send("I will not apply timeout actions to bot accounts.")
            return True

        me = message.guild.me
        if me is None:
            await message.channel.send("Could not verify my permissions right now.")
            return True
        if not me.guild_permissions.moderate_members:
            await message.channel.send("I need `Moderate Members` permission to manage timeouts.")
            return True
        if target == message.guild.owner or target.top_role >= me.top_role:
            await message.channel.send("I cannot manage timeout for that member due to role hierarchy.")
            return True

        is_remove = (
            "remove" in lowered
            or "unmute" in lowered
            or "untimeout" in lowered
        )
        if is_remove:
            try:
                await target.timeout(None, reason=f"Conversational unmute by {message.author}")
            except discord.HTTPException:
                await message.channel.send("Failed to remove timeout for that user.")
                return True
            await message.channel.send(f"Removed timeout for {target.mention}.")
            await send_mod_log(
                message.guild,
                "Unmute (Conversational)",
                target=target,
                moderator=message.author,
                channel=message.channel,
                reason="Natural language request",
            )
            return True

        duration_match = TIMEOUT_DURATION_RE.search(lowered)
        if duration_match is None:
            await message.channel.send("Please include timeout duration, e.g. `20 mins`.")
            return True

        minutes = int(duration_match.group(1))
        if minutes < 1 or minutes > 40320:
            await message.channel.send("Minutes must be between `1` and `40320`.")
            return True

        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        try:
            await target.timeout(until, reason=f"Conversational mute by {message.author}")
        except discord.HTTPException:
            await message.channel.send("Failed to apply timeout for that user.")
            return True

        await message.channel.send(f"Timed out {target.mention} for `{minutes}` minute(s).")
        await send_mod_log(
            message.guild,
            "Mute (Conversational)",
            target=target,
            moderator=message.author,
            channel=message.channel,
            reason="Natural language request",
            details=f"Duration: `{minutes}` minute(s)",
        )
        return True

    if not is_ai_configured():
        await message.channel.send(ai_setup_message())
        return True

    chat_key = (message.channel.id, message.author.id)
    history = CONVERSATIONAL_AI_CACHE.get(chat_key, [])[-(AI_MAX_HISTORY * 2) :]
    ai_messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}, *history]
    ai_messages.append({"role": "user", "content": text})
    async with message.channel.typing():
        try:
            reply = await request_ai_completion(
                ai_messages,
                max_tokens=AI_MAX_TOKENS,
                temperature=0.5,
                policy_key="chat",
            )
        except Exception as error:
            print(f"[CONVERSATIONAL AI ERROR] {error}")
            await message.channel.send(friendly_ai_error(error))
            return True

    append_conversation_history(CONVERSATIONAL_AI_CACHE, chat_key, text, reply)
    await send_chunked(message.channel, reply)
    return True


def get_spotify_client():
    global SPOTIFY_CLIENT
    if SPOTIFY_CLIENT is not None:
        return SPOTIFY_CLIENT
    if (
        spotipy is None
        or SpotifyClientCredentials is None
        or not SPOTIFY_CLIENT_ID
        or not SPOTIFY_CLIENT_SECRET
    ):
        return None
    SPOTIFY_CLIENT = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
        )
    )
    return SPOTIFY_CLIENT


def is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


async def ytdlp_extract(query: str) -> dict:
    if yt_dlp is None:
        raise RuntimeError("`yt-dlp` is not installed. Install requirements first.")

    options = dict(YTDL_BASE_OPTIONS)

    def _extract() -> dict:
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(query, download=False)

    return await asyncio.to_thread(_extract)


async def ytdlp_extract_stream(query: str) -> dict:
    if yt_dlp is None:
        raise RuntimeError("`yt-dlp` is not installed. Install requirements first.")

    option_sets = [
        {
            **YTDL_BASE_OPTIONS,
            "format": "bestaudio/best",
            "noplaylist": True,
            "extractor_args": {"youtube": {"player_client": ["web"]}},
        },
        {
            **YTDL_BASE_OPTIONS,
            "format": "bestaudio/best",
            "noplaylist": True,
            "extractor_args": {"youtube": {"player_client": ["ios"]}},
        },
        {
            **YTDL_BASE_OPTIONS,
            "format": "best",
            "noplaylist": True,
        },
    ]

    last_error: Exception | None = None
    for options in option_sets:
        try:
            def _extract() -> dict:
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(query, download=False)

            return await asyncio.to_thread(_extract)
        except Exception as error:
            last_error = error
            continue

    raise RuntimeError(last_error or "yt-dlp could not extract stream data.")


def track_from_ytdlp_entry(entry: dict, requester_id: int) -> MusicTrack | None:
    if not entry:
        return None
    title = entry.get("title") or "Unknown title"
    webpage_url = entry.get("webpage_url") or entry.get("url") or ""

    if webpage_url and not str(webpage_url).startswith("http"):
        video_id = entry.get("id")
        if video_id:
            webpage_url = f"https://www.youtube.com/watch?v={video_id}"
    if not webpage_url:
        return None

    return MusicTrack(
        title=title[:200],
        webpage_url=str(webpage_url),
        requested_by=requester_id,
    )


async def youtube_query_to_tracks(query: str, requester_id: int) -> list[MusicTrack]:
    info = await ytdlp_extract(query)
    entries = info.get("entries")
    tracks: list[MusicTrack] = []

    if isinstance(entries, list):
        for entry in entries:
            track = track_from_ytdlp_entry(entry, requester_id)
            if track is None:
                continue
            tracks.append(track)
            if len(tracks) >= MUSIC_MAX_PLAYLIST_ITEMS:
                break
    else:
        track = track_from_ytdlp_entry(info, requester_id)
        if track is not None:
            tracks.append(track)

    if not tracks:
        raise RuntimeError("No playable results found for that query.")
    return tracks


async def spotify_url_to_search_queries(url: str) -> tuple[list[str], str]:
    client = get_spotify_client()
    if client is None:
        raise RuntimeError(
            "Spotify is not configured. Set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` in `.env`."
        )

    track_match = SPOTIFY_TRACK_RE.search(url)
    if track_match:
        track_id = track_match.group(1)

        def _fetch_track():
            return client.track(track_id)

        track_obj = await asyncio.to_thread(_fetch_track)
        name = (track_obj or {}).get("name", "Unknown track")
        artists = ", ".join(a.get("name", "") for a in (track_obj or {}).get("artists", []) if a)
        query = f"{name} {artists} audio".strip()
        return [query], f"Spotify track: {name}"

    playlist_match = SPOTIFY_PLAYLIST_RE.search(url)
    if playlist_match:
        playlist_id = playlist_match.group(1)

        def _fetch_playlist_queries():
            queries: list[str] = []
            offset = 0
            playlist_name = f"Spotify playlist {playlist_id}"
            while True:
                try:
                    payload = client.playlist_items(
                        playlist_id,
                        offset=offset,
                        limit=100,
                        fields="items(track(name,artists(name))),next",
                        additional_types=("track",),
                    )
                except Exception as error:
                    message = str(error).lower()
                    if "http status: 403" in message or "forbidden" in message:
                        raise RuntimeError(
                            "Spotify playlist is not accessible (403). Make it Public and try again."
                        ) from error
                    raise RuntimeError(f"Spotify API error while reading playlist: {error}") from error
                if offset == 0:
                    playlist_meta = client.playlist(playlist_id, fields="name")
                    if playlist_meta and playlist_meta.get("name"):
                        playlist_name = playlist_meta["name"]
                items = payload.get("items", [])
                for item in items:
                    track_obj = (item or {}).get("track")
                    if not track_obj:
                        continue
                    name = track_obj.get("name")
                    if not name:
                        continue
                    artists = ", ".join(
                        a.get("name", "") for a in track_obj.get("artists", []) if a
                    )
                    queries.append(f"{name} {artists} audio".strip())
                    if len(queries) >= MUSIC_MAX_PLAYLIST_ITEMS:
                        return queries, playlist_name
                if not payload.get("next"):
                    break
                offset += len(items)
            return queries, playlist_name

        queries, playlist_name = await asyncio.to_thread(_fetch_playlist_queries)
        if not queries:
            raise RuntimeError("Spotify playlist has no playable tracks.")
        return queries, f"Spotify playlist: {playlist_name}"

    raise RuntimeError("Only Spotify track/playlist links are supported.")


async def source_to_tracks(source: str, requester_id: int) -> tuple[list[MusicTrack], str | None]:
    if SPOTIFY_TRACK_RE.search(source) or SPOTIFY_PLAYLIST_RE.search(source):
        queries, label = await spotify_url_to_search_queries(source)
        tracks: list[MusicTrack] = []
        for q in queries:
            result = await youtube_query_to_tracks(f"ytsearch1:{q}", requester_id)
            if result:
                tracks.append(result[0])
        if not tracks:
            raise RuntimeError("Could not map Spotify tracks to YouTube sources.")
        return tracks, label

    query = source if is_url(source) else f"ytsearch1:{source}"
    tracks = await youtube_query_to_tracks(query, requester_id)
    return tracks, None


def extract_stream_url(info: dict) -> str | None:
    direct_url = info.get("url")
    if isinstance(direct_url, str) and direct_url.startswith(("http://", "https://")):
        return direct_url

    requested_formats = info.get("requested_formats") or []
    for fmt in requested_formats:
        fmt_url = (fmt or {}).get("url")
        if not fmt_url:
            continue
        if (fmt or {}).get("acodec") not in (None, "none"):
            return str(fmt_url)

    formats = info.get("formats") or []
    best_url = None
    best_score = None
    for fmt in formats:
        if not isinstance(fmt, dict):
            continue
        fmt_url = fmt.get("url")
        if not fmt_url:
            continue
        acodec = fmt.get("acodec")
        if acodec in (None, "none"):
            continue
        audio_only = 1 if fmt.get("vcodec") in (None, "none") else 0
        score = (
            audio_only,
            float(fmt.get("abr") or 0),
            float(fmt.get("tbr") or 0),
            float(fmt.get("asr") or 0),
        )
        if best_score is None or score > best_score:
            best_score = score
            best_url = str(fmt_url)
    return best_url


async def resolve_stream(track: MusicTrack) -> tuple[str, str, str]:
    current_url = track.webpage_url
    info: dict | None = None

    for _ in range(3):
        info = await ytdlp_extract_stream(current_url)
        entries = info.get("entries")
        if isinstance(entries, list) and entries:
            info = entries[0]

        stream_url = extract_stream_url(info)
        title = info.get("title") or track.title
        webpage_url = info.get("webpage_url") or current_url
        if stream_url:
            return str(stream_url), str(title), str(webpage_url)

        fallback_url = info.get("webpage_url") or info.get("url")
        if (
            isinstance(fallback_url, str)
            and fallback_url.startswith(("http://", "https://"))
            and fallback_url != current_url
        ):
            current_url = fallback_url
            continue
        break

    raise RuntimeError(
        "Could not resolve a stream URL for this track. Try another source/query "
        "or update yt-dlp on the host."
    )


async def ensure_voice_connection(ctx: commands.Context) -> discord.VoiceClient | None:
    if not isinstance(ctx.author, discord.Member) or not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("Join a voice channel first.")
        return None

    target_channel = ctx.author.voice.channel
    last_error: Exception | None = None

    for attempt in range(1, VOICE_CONNECT_RETRIES + 1):
        vc = ctx.guild.voice_client
        try:
            if vc is not None and not vc.is_connected():
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass
                vc = None
                await asyncio.sleep(0.35)

            if vc is None:
                vc = await asyncio.wait_for(
                    target_channel.connect(
                        timeout=VOICE_CONNECT_TIMEOUT,
                        reconnect=VOICE_INTERNAL_RECONNECT,
                    ),
                    timeout=VOICE_CONNECT_TIMEOUT + 5,
                )
            elif vc.channel != target_channel:
                await asyncio.wait_for(
                    vc.move_to(target_channel),
                    timeout=VOICE_CONNECT_TIMEOUT,
                )

            if vc is not None and vc.is_connected():
                return vc
            raise RuntimeError("Voice client did not stay connected after handshake.")
        except Exception as error:
            last_error = error
            print(
                f"[VOICE CONNECT] attempt {attempt}/{VOICE_CONNECT_RETRIES} failed in guild "
                f"{ctx.guild.id}: {error!r}"
            )
            stale = ctx.guild.voice_client
            if stale is not None:
                try:
                    await stale.disconnect(force=True)
                except Exception:
                    pass
            if attempt < VOICE_CONNECT_RETRIES:
                await asyncio.sleep(min(2.5, 0.75 * attempt))

    error_text = str(last_error).lower() if last_error else ""
    if "4006" in error_text or "voice handshake" in error_text:
        await ctx.send(
            "Voice connect failed (`4006`). This is usually a hosting/network issue (Discord voice UDP). "
            "Try again once; if it keeps failing, switch node/provider."
        )
    else:
        await ctx.send(
            f"Could not join/move voice channel after `{VOICE_CONNECT_RETRIES}` tries: "
            f"`{last_error or 'unknown error'}`"
        )
    return None


def in_same_voice_channel(ctx: commands.Context) -> bool:
    vc = ctx.guild.voice_client
    if vc is None:
        return False
    author = ctx.author
    return isinstance(author, discord.Member) and author.voice and author.voice.channel == vc.channel


def get_music_text_channel(guild: discord.Guild) -> discord.TextChannel | None:
    channel_id = MUSIC_TEXT_CHANNELS.get(guild.id)
    if channel_id is None:
        return None
    channel = guild.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel
    return None


def music_after_playback(guild: discord.Guild, error: Exception | None) -> None:
    if error is not None:
        print(f"[MUSIC PLAYBACK ERROR] {error}")
    future = asyncio.run_coroutine_threadsafe(play_next_track(guild), bot.loop)
    try:
        future.result()
    except Exception as follow_err:
        print(f"[MUSIC FOLLOWUP ERROR] {follow_err}")


async def play_next_track(guild: discord.Guild) -> None:
    global FFMPEG_EXECUTABLE
    lock = MUSIC_LOCKS[guild.id]
    async with lock:
        vc = guild.voice_client
        if vc is None or not vc.is_connected():
            MUSIC_NOW_PLAYING.pop(guild.id, None)
            return
        if vc.is_playing() or vc.is_paused():
            return

        if not FFMPEG_EXECUTABLE:
            FFMPEG_EXECUTABLE = resolve_ffmpeg_executable()
        if not FFMPEG_EXECUTABLE:
            channel = get_music_text_channel(guild)
            if channel is not None:
                await channel.send(
                    "Playback failed: ffmpeg not found on host. "
                    "Install ffmpeg or add `imageio-ffmpeg` dependency."
                )
            return

        queue = MUSIC_QUEUES[guild.id]
        while queue:
            track = queue.popleft()
            try:
                stream_url, title, webpage_url = await resolve_stream(track)
            except Exception as error:
                channel = get_music_text_channel(guild)
                if channel is not None:
                    await channel.send(f"Skipping `{track.title}`: {error}")
                continue

            track.title = title[:200]
            track.webpage_url = webpage_url
            channel = get_music_text_channel(guild)
            try:
                source = discord.FFmpegPCMAudio(
                    stream_url,
                    executable=FFMPEG_EXECUTABLE,
                    **FFMPEG_OPTIONS,
                )
                vc.play(source, after=lambda e: music_after_playback(guild, e))
                MUSIC_NOW_PLAYING[guild.id] = track
                if channel is not None:
                    await channel.send(f"Now playing: **{track.title}**")
                return
            except Exception as error:
                if channel is not None:
                    await channel.send(f"Playback failed for `{track.title}`: {error}")
                continue

        MUSIC_NOW_PLAYING.pop(guild.id, None)


def split_message(content: str, max_len: int = 1900) -> list[str]:
    text = content.strip()
    if not text:
        return ["(empty response)"]
    parts: list[str] = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        parts.append(text)
    return parts


async def send_chunked(
    target: discord.abc.Messageable | commands.Context, content: str
) -> None:
    chunks = split_message(content)
    if isinstance(target, commands.Context):
        for index, chunk in enumerate(chunks):
            if index == 0:
                await target.send(chunk)
            else:
                await target.channel.send(chunk)
        return

    for chunk in chunks:
        await target.send(chunk)


async def fetch_openrouter_models(session: aiohttp.ClientSession) -> set[str]:
    global MODEL_CACHE_TS, MODEL_CACHE
    now = time.monotonic()
    if MODEL_CACHE and now - MODEL_CACHE_TS < MODEL_CACHE_TTL_SECONDS:
        return MODEL_CACHE

    async with session.get(OPENROUTER_MODELS_URL) as response:
        text = await response.text()
        if response.status >= 400:
            raise RuntimeError(f"Could not fetch models (`{response.status}`): {text[:200]}")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Model list response is not valid JSON.") from exc

    models = {
        item.get("id", "")
        for item in payload.get("data", [])
        if isinstance(item, dict) and item.get("id")
    }
    if models:
        MODEL_CACHE = models
        MODEL_CACHE_TS = now
    return models


async def fetch_groq_models(session: aiohttp.ClientSession) -> set[str]:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing in .env")
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    async with session.get(GROQ_MODELS_URL, headers=headers) as response:
        text = await response.text()
        if response.status >= 400:
            raise RuntimeError(f"Could not fetch Groq models (`{response.status}`): {text[:200]}")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Groq model list response is not valid JSON.") from exc

    return {
        item.get("id", "")
        for item in payload.get("data", [])
        if isinstance(item, dict) and item.get("id")
    }


def get_model_try_order(provider: str) -> list[str]:
    models: list[str] = []
    seen: set[str] = set()
    if provider == "groq":
        ordered = [GROQ_MODEL, *GROQ_FALLBACK_MODELS]
    else:
        ordered = [OPENROUTER_MODEL, *OPENROUTER_FALLBACK_MODELS]
    for model in ordered:
        cleaned = model.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        models.append(cleaned)
    return models


def should_try_fallback(status: int, raw_text: str, provider: str) -> bool:
    body = raw_text.lower()
    if status in {404, 429, 500, 502, 503, 504}:
        return True
    if provider == "groq":
        return "rate limit" in body or "model_decommissioned" in body or "unavailable" in body
    return (
        "no endpoints found" in body
        or "temporarily unavailable" in body
        or "provider returned error" in body
    )


def friendly_ai_error(error: Exception | str) -> str:
    if isinstance(error, groq_budget.GroqBudgetError):
        return str(error)
    text = str(error).lower()
    if "circuit open" in text:
        return "AI is cooling down briefly after provider errors. Try again in under a minute."
    if "429" in text or "rate-limit" in text or "provider returned error" in text:
        return "AI providers are busy right now (rate-limited). Try again in 10-20 seconds."
    if "timeout" in text:
        return "AI provider timed out. Try again in a few seconds."
    if "data policy" in text:
        if AI_PROVIDER == "groq":
            return "Model blocked by provider policy. Try `&aimodel` or switch model."
        return "Model blocked by OpenRouter data policy. Use `&aimodels` and choose another free model."
    if "401" in text or "unauthorized" in text or "invalid api key" in text:
        if AI_PROVIDER == "groq":
            return "Groq API key looks invalid. Update `GROQ_API_KEY` in `.env` and restart."
        return "OpenRouter API key looks invalid. Update `OPENROUTER_API_KEY` in `.env` and restart."
    return "AI request failed temporarily. Please try again in a few seconds."


def is_ai_configured() -> bool:
    if AI_PROVIDER == "groq":
        return bool(GROQ_API_KEY)
    return bool(OPENROUTER_API_KEY)


def ai_setup_message() -> str:
    if AI_PROVIDER == "groq":
        return "Groq is not configured. Add `GROQ_API_KEY` in `.env`, then restart the bot."
    return "OpenRouter is not configured. Add `OPENROUTER_API_KEY` in `.env`, then restart the bot."


def current_ai_model() -> str:
    return GROQ_MODEL if AI_PROVIDER == "groq" else OPENROUTER_MODEL


def current_ai_fallback_models() -> list[str]:
    return GROQ_FALLBACK_MODELS if AI_PROVIDER == "groq" else OPENROUTER_FALLBACK_MODELS


async def request_openrouter_completion(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 260,
    temperature: float = 0.6,
    model_override: str | None = None,
    fallback_models: list[str] | None = None,
    response_format: dict[str, Any] | None = None,
    include_fallback_notice: bool = True,
) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is missing in .env")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": OPENROUTER_APP_NAME or "Discord Mod Bot",
    }
    if OPENROUTER_HTTP_REFERER:
        headers["HTTP-Referer"] = OPENROUTER_HTTP_REFERER

    timeout = aiohttp.ClientTimeout(total=AI_TIMEOUT_SECONDS)
    models_to_try = get_model_try_order("openrouter")
    if model_override:
        forced = model_override.strip()
        if forced:
            models_to_try = [forced, *[m for m in models_to_try if m != forced]]
    if fallback_models:
        ordered_fallbacks = [model.strip() for model in fallback_models if model.strip()]
        models_to_try = [
            *models_to_try[:1],
            *[model for model in ordered_fallbacks if model not in models_to_try[:1]],
            *[model for model in models_to_try[1:] if model not in ordered_fallbacks],
        ]
    last_error = "OpenRouter request failed."
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for index, model_to_use in enumerate(models_to_try):
            payload = {
                "model": model_to_use,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if response_format is not None:
                payload["response_format"] = response_format
            try:
                async with session.post(
                    OPENROUTER_API_URL, headers=headers, json=payload
                ) as response:
                    raw_text = await response.text()
                    if response.status >= 400:
                        last_error = (
                            f"OpenRouter API error `{response.status}` for `{model_to_use}`: "
                            f"{raw_text[:220]}"
                        )
                        if index < len(models_to_try) - 1 and should_try_fallback(
                            response.status, raw_text, "openrouter"
                        ):
                            continue
                        raise RuntimeError(last_error)
                    try:
                        data = json.loads(raw_text)
                    except json.JSONDecodeError:
                        last_error = f"Invalid JSON response from `{model_to_use}`."
                        if index < len(models_to_try) - 1:
                            continue
                        raise RuntimeError(last_error)
            except asyncio.TimeoutError:
                last_error = f"Timeout from `{model_to_use}`."
                if index < len(models_to_try) - 1:
                    continue
                raise RuntimeError(last_error)
            except aiohttp.ClientError as exc:
                last_error = f"Network error from `{model_to_use}`: {exc}"
                if index < len(models_to_try) - 1:
                    continue
                raise RuntimeError(last_error)

            choices = data.get("choices", [])
            if not choices:
                last_error = f"No choices returned from `{model_to_use}`."
                if index < len(models_to_try) - 1:
                    continue
                raise RuntimeError(last_error)

            message = choices[0].get("message", {})
            content = message.get("content", "")

            if isinstance(content, list):
                text_parts: list[str] = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                content = "\n".join(part for part in text_parts if part).strip()
            elif not isinstance(content, str):
                content = str(content)

            if not content:
                last_error = f"Empty text response from `{model_to_use}`."
                if index < len(models_to_try) - 1:
                    continue
                raise RuntimeError(last_error)

            if include_fallback_notice and model_to_use != models_to_try[0]:
                return f"[Fallback model: `{model_to_use}`]\n\n{content.strip()}"
            return content.strip()

    raise RuntimeError(last_error)


async def request_groq_completion(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 260,
    temperature: float = 0.6,
    model_override: str | None = None,
    fallback_models: list[str] | None = None,
    response_format: dict[str, Any] | None = None,
    include_fallback_notice: bool = True,
    feature: str = "general",
) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing in .env")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    timeout = aiohttp.ClientTimeout(total=AI_TIMEOUT_SECONDS)
    models_to_try = get_model_try_order("groq")
    if model_override:
        forced = model_override.strip()
        if forced:
            models_to_try = [forced, *[m for m in models_to_try if m != forced]]
    if fallback_models:
        ordered_fallbacks = [model.strip() for model in fallback_models if model.strip()]
        models_to_try = [
            *models_to_try[:1],
            *[model for model in ordered_fallbacks if model not in models_to_try[:1]],
            *[model for model in models_to_try[1:] if model not in ordered_fallbacks],
        ]
    models_to_try = list(dict.fromkeys(models_to_try))
    last_model = models_to_try[-1] if models_to_try else ""

    async with aiohttp.ClientSession(timeout=timeout) as session:

        async def attempt(model_to_use: str) -> tuple[str, int | None]:
            # Errors raised as ModelUnavailable/ModelRateLimited make the budget
            # governor move on to the next model; anything else aborts.
            is_last = model_to_use == last_model
            payload = {
                "model": model_to_use,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if response_format is not None:
                payload["response_format"] = response_format
            try:
                async with session.post(GROQ_API_URL, headers=headers, json=payload) as response:
                    raw_text = await response.text()
                    if response.status >= 400:
                        error_text = (
                            f"Groq API error `{response.status}` for `{model_to_use}`: "
                            f"{raw_text[:220]}"
                        )
                        if response.status == 429:
                            raise groq_budget.ModelRateLimited(
                                error_text,
                                retry_after=groq_budget.parse_retry_after(
                                    response.headers.get("retry-after")
                                ),
                                daily=groq_budget.is_daily_limit_body(raw_text),
                            )
                        if not is_last and should_try_fallback(response.status, raw_text, "groq"):
                            raise groq_budget.ModelUnavailable(error_text)
                        raise RuntimeError(error_text)
                    try:
                        data = json.loads(raw_text)
                    except json.JSONDecodeError:
                        raise groq_budget.ModelUnavailable(
                            f"Invalid JSON response from `{model_to_use}`."
                        )
            except asyncio.TimeoutError:
                raise groq_budget.ModelUnavailable(f"Timeout from `{model_to_use}`.")
            except aiohttp.ClientError as exc:
                raise groq_budget.ModelUnavailable(f"Network error from `{model_to_use}`: {exc}")

            choices = data.get("choices", [])
            if not choices:
                raise groq_budget.ModelUnavailable(f"No choices returned from `{model_to_use}`.")

            message = choices[0].get("message", {})
            content = message.get("content", "")

            if isinstance(content, list):
                text_parts: list[str] = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                content = "\n".join(part for part in text_parts if part).strip()
            elif not isinstance(content, str):
                content = str(content)

            if not content:
                raise groq_budget.ModelUnavailable(f"Empty text response from `{model_to_use}`.")

            usage = data.get("usage") if isinstance(data, dict) else None
            total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
            return content.strip(), total_tokens if isinstance(total_tokens, int) else None

        model_used, content = await GROQ_BUDGET.run(
            models_to_try,
            attempt,
            feature=feature,
            estimated_tokens=groq_budget.estimate_tokens(messages, max_tokens),
        )

    if include_fallback_notice and models_to_try and model_used != models_to_try[0]:
        return f"[Fallback model: `{model_used}`]\n\n{content}"
    return content


def should_retry_ai_error(error: Exception | str) -> bool:
    if isinstance(error, groq_budget.GroqBudgetError):
        return False
    text = str(error).lower()
    markers = (
        "429",
        "rate",
        "timeout",
        "temporarily unavailable",
        "provider returned error",
        "network error",
        "connection",
        "503",
        "502",
        "504",
        "busy",
        "unavailable",
    )
    return any(marker in text for marker in markers)


async def request_ai_completion(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 260,
    temperature: float = 0.6,
    policy_key: str = "general",
    model_override: str | None = None,
    fallback_models: list[str] | None = None,
    response_format: dict[str, Any] | None = None,
    include_fallback_notice: bool = True,
) -> str:
    normalized_key = (policy_key or "general").strip().lower()
    circuit_until = AI_CIRCUIT_OPEN_UNTIL.get(normalized_key, 0.0)
    now = time.monotonic()
    if now < circuit_until:
        wait_seconds = int(max(1.0, circuit_until - now))
        raise RuntimeError(f"AI circuit open for `{normalized_key}` for {wait_seconds}s.")

    async with AI_REQUEST_SEMAPHORE:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                if AI_PROVIDER == "groq":
                    output = await request_groq_completion(
                        messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        model_override=model_override,
                        fallback_models=fallback_models,
                        response_format=response_format,
                        include_fallback_notice=include_fallback_notice,
                        feature=normalized_key,
                    )
                else:
                    output = await request_openrouter_completion(
                        messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        model_override=model_override,
                        fallback_models=fallback_models,
                        response_format=response_format,
                        include_fallback_notice=include_fallback_notice,
                    )
                AI_CIRCUIT_OPEN_UNTIL.pop(normalized_key, None)
                return output
            except Exception as error:
                last_error = error
                can_retry = attempt == 0 and should_retry_ai_error(error)
                if can_retry:
                    await asyncio.sleep(AI_RETRY_BACKOFF_SECONDS)
                    continue
                if should_retry_ai_error(error):
                    AI_CIRCUIT_OPEN_UNTIL[normalized_key] = (
                        time.monotonic() + AI_CIRCUIT_BREAK_SECONDS
                    )
                raise

        if last_error is not None:
            raise last_error
    raise RuntimeError("AI completion failed.")


def append_ai_history(channel_id: int, user_prompt: str, assistant_reply: str) -> None:
    history = AI_CHAT_CACHE[channel_id]
    history.append({"role": "user", "content": user_prompt})
    history.append({"role": "assistant", "content": assistant_reply})
    max_entries = max(2, AI_MAX_HISTORY * 2)
    if len(history) > max_entries:
        AI_CHAT_CACHE[channel_id] = history[-max_entries:]


async def collect_vibe_context(
    channel: discord.TextChannel,
    user_id: int,
    target_messages: int,
) -> tuple[list[str], list[str]]:
    desired = max(1, target_messages)
    scan_limit = min(max(desired * 12, desired + 160), 7000)

    user_messages: list[str] = []
    replies_received: list[str] = []
    target_message_ids: set[int] = set()

    async for msg in channel.history(limit=scan_limit, oldest_first=True):
        if msg.author.bot:
            continue
        content = msg.clean_content.strip()
        if not content:
            continue
        content = content[:420]

        if msg.author.id == user_id:
            user_messages.append(content)
            target_message_ids.add(msg.id)
            continue

        is_reply_to_target = False
        if msg.reference and msg.reference.message_id in target_message_ids:
            is_reply_to_target = True
        elif any(getattr(m, "id", None) == user_id for m in msg.mentions):
            is_reply_to_target = True

        if is_reply_to_target:
            replies_received.append(content)

    user_messages = user_messages[-desired:]
    max_replies = min(max(desired, 30), desired * 2)
    replies_received = replies_received[-max_replies:]
    return user_messages, replies_received


def trim_context_lines(source: list[str], max_lines: int, max_chars: int) -> list[str]:
    selected: list[str] = []
    total = 0
    for raw in reversed(source[-max_lines:]):
        line = " ".join(raw.split()).strip()
        if not line:
            continue
        if len(line) > 220:
            line = line[:220].rstrip() + "..."
        projected = total + len(line) + 4
        if projected > max_chars:
            break
        selected.append(line)
        total = projected
    selected.reverse()
    return selected


def build_vibe_prompt_lines(
    user_messages: list[str], replies_received: list[str]
) -> tuple[list[str], list[str]]:
    total_budget = max(VIBE_MAX_PROMPT_CHARS, 2000)
    user_budget = int(total_budget * 0.62)
    reply_budget = total_budget - user_budget
    user_lines = trim_context_lines(user_messages, VIBE_MAX_PROMPT_MESSAGES, user_budget)
    reply_lines = trim_context_lines(replies_received, VIBE_MAX_PROMPT_MESSAGES, reply_budget)
    return user_lines, reply_lines


def generate_vibe_report_local(
    member: discord.Member, user_messages: list[str], replies_received: list[str]
) -> str:
    msg_count = len(user_messages)
    joined = " ".join(user_messages).lower()
    words = [w for w in WORD_PATTERN.findall(joined) if len(w) > 2]
    stop = {
        "the", "and", "for", "that", "with", "this", "you", "are", "was", "have", "not", "but",
        "just", "your", "from", "what", "when", "where", "will", "would", "they", "them", "their",
        "about", "there", "then", "than", "into", "also", "been", "can", "could", "should",
    }
    filtered = [w for w in words if w not in stop]
    common = [w for w, _ in Counter(filtered).most_common(6)]
    topic_text = ", ".join(common[:5]) if common else "general chat"

    question_ratio = sum(1 for m in user_messages if "?" in m) / max(msg_count, 1)
    exclaim_ratio = sum(1 for m in user_messages if "!" in m) / max(msg_count, 1)

    reply_text = " ".join(replies_received).lower()
    pos_markers = ["thanks", "thank", "love", "nice", "great", "good", "haha", "lol", "bro", "best"]
    neg_markers = ["stupid", "idiot", "hate", "shut", "noob", "trash", "bad", "annoying", "toxic", "loser"]
    pos_hits = sum(reply_text.count(w) for w in pos_markers)
    neg_hits = sum(reply_text.count(w) for w in neg_markers)

    style_bits = []
    if exclaim_ratio > 0.18:
        style_bits.append("high-energy and expressive")
    if question_ratio > 0.22:
        style_bits.append("question-driven and curious")
    if not style_bits:
        style_bits.append("casual and conversational")

    if not replies_received:
        response_read = "There is limited visible reply context in this channel snapshot."
    elif pos_hits > neg_hits * 1.3:
        response_read = "People mostly respond with positive and engaged reactions."
    elif neg_hits > pos_hits * 1.3:
        response_read = "Replies show noticeable pushback or teasing around their messages."
    else:
        response_read = "Replies are mixed, with both positive engagement and occasional friction."

    return (
        f"Behavior Snapshot: {member.display_name} tends to communicate in a {style_bits[0]} way, "
        f"and their recent messages revolve around topics like {topic_text}. Their wording suggests a "
        "social, active presence in chat, with tone shifting based on context.\n\n"
        f"How Others Respond: {response_read} This read is based on recent direct replies/mentions in the "
        "same channel and can vary heavily across different channels or days.\n\n"
        "Balanced Take: They come across as engaged and visible in conversation, and depending on the moment, "
        "their style may feel either fun/hyped or sharp/blunt to others. This is a lightweight estimate from "
        "recent chat behavior, not a factual judgment."
    )


def generate_vibecheck_local(user_messages: list[str], replies_received: list[str]) -> str:
    message_count = max(1, len(user_messages))
    text = " ".join(user_messages).lower()
    replies_text = " ".join(replies_received).lower()

    exclaim_ratio = sum(1 for m in user_messages if "!" in m) / message_count
    question_ratio = sum(1 for m in user_messages if "?" in m) / message_count

    chaos_percent = int(min(95, max(15, 30 + exclaim_ratio * 280 + question_ratio * 120)))
    if chaos_percent >= 75:
        mood_label = "chaotic"
    elif chaos_percent >= 55:
        mood_label = "hyped"
    elif chaos_percent >= 35:
        mood_label = "balanced"
    else:
        mood_label = "calm"

    supportive_hits = sum(text.count(w) for w in ["thanks", "love", "bro", "help", "nice", "great"])
    roast_hits = sum(text.count(w) for w in ["noob", "stupid", "idiot", "trash", "roast", "shut"])
    question_hits = sum(m.count("?") for m in user_messages)
    mention_hits = sum(m.count("@") for m in user_messages) + replies_text.count("@")

    if supportive_hits > roast_hits and supportive_hits > question_hits:
        dominant_trait = "supportive hype friend"
    elif question_hits > supportive_hits and question_hits > roast_hits:
        dominant_trait = "curious conversation starter"
    elif roast_hits >= 3:
        dominant_trait = "playful instigator"
    else:
        dominant_trait = "social chatter spark"

    roast_score = roast_hits + int(exclaim_ratio * 6)
    if roast_score >= 7:
        roast_level = "unhinged roast machine"
    elif roast_score >= 4:
        roast_level = "medium spice"
    elif roast_score >= 2:
        roast_level = "light teasing"
    else:
        roast_level = "mostly wholesome"

    energy_score = exclaim_ratio * 5 + question_ratio * 3 + (mention_hits / max(message_count, 1))
    if energy_score >= 3.8:
        social_energy = "main character mode"
    elif energy_score >= 2.3:
        social_energy = "active and loud"
    elif energy_score >= 1.2:
        social_energy = "steady participant"
    else:
        social_energy = "low-key presence"

    return (
        "ðŸ”¥ Vibe Check Result\n"
        f"Mood: {chaos_percent}% {mood_label}\n"
        f"Dominant trait: {dominant_trait}\n"
        f"Roast level: {roast_level}\n"
        f"Social energy: {social_energy}\n\n"
        "âš ï¸ For fun only."
    )


def normalize_vibecheck_output(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        text = "ðŸ”¥ Vibe Check Result"
    if "vibe check result" not in text.lower():
        text = "ðŸ”¥ Vibe Check Result\n" + text
    if "for fun only" not in text.lower():
        text = text.rstrip() + "\n\nâš ï¸ For fun only."
    return text


async def generate_vibecheck_report(
    member: discord.Member, user_messages: list[str], replies_received: list[str]
) -> str:
    user_lines, reply_lines = build_vibe_prompt_lines(user_messages, replies_received)
    user_transcript = "\n".join(f"- {line}" for line in user_lines) or "- (none)"
    reply_transcript = "\n".join(f"- {line}" for line in reply_lines) if reply_lines else "- (none)"
    prompt = (
        "Create a short playful Discord vibe check.\n"
        "Rules:\n"
        "1) Fun only, do not diagnose.\n"
        "2) No slurs, no hate, no protected-trait inferences.\n"
        "3) Keep each value concise (2-6 words).\n"
        "4) Return EXACTLY this format:\n"
        "ðŸ”¥ Vibe Check Result\n"
        "Mood: <0-100>% <descriptor>\n"
        "Dominant trait: <descriptor>\n"
        "Roast level: <descriptor>\n"
        "Social energy: <descriptor>\n"
        "âš ï¸ For fun only.\n\n"
        f"Target user: {member.display_name}\n"
        f"User messages analyzed: {len(user_messages)}\n"
        f"Replies considered: {len(replies_received)}\n\n"
        "User message sample:\n"
        f"{user_transcript}\n\n"
        "Replies from others sample:\n"
        f"{reply_transcript}"
    )
    ai_messages = [
        {"role": "system", "content": VIBE_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    output = await request_ai_completion(
        ai_messages,
        max_tokens=180,
        temperature=0.45,
        policy_key="vibecheck",
    )
    return normalize_vibecheck_output(output)


async def collect_recent_channel_transcript(
    channel: discord.TextChannel,
    limit: int,
    *,
    exclude_message_ids: set[int] | None = None,
) -> list[str]:
    scan_limit = min(max(limit * 3, limit + 30), 2500)
    entries = await get_channel_window_cached(
        channel,
        scan_limit=scan_limit,
        cache_ttl_seconds=90,
        include_attachment_marker=True,
    )
    lines = []
    for entry in reversed(entries):
        if exclude_message_ids and entry.message_id in exclude_message_ids:
            continue
        lines.append(f"{entry.author_display_name}: {entry.content[:260]}")
        if len(lines) >= limit:
            break
    lines.reverse()
    return lines


async def collect_channel_messages_since(
    channel: discord.TextChannel,
    cutoff,
    *,
    max_messages: int,
) -> list[str]:
    scan_limit = min(CATCHUP_SCAN_LIMIT, max(max_messages * 3, 200))
    entries = await get_channel_window_cached(
        channel,
        after=cutoff,
        scan_limit=scan_limit,
        cache_ttl_seconds=CATCHUP_CACHE_SECONDS,
        include_attachment_marker=True,
    )
    lines = [f"{entry.author_display_name}: {entry.content[:280]}" for entry in entries]
    return lines[:max_messages]


def generate_catchup_local_summary(transcript: list[str], hours: int) -> str:
    if not transcript:
        return "No meaningful messages found in that range."

    authors = Counter()
    words: list[str] = []
    for line in transcript:
        author, _, content = line.partition(": ")
        if author:
            authors[author] += 1
        for token in WORD_PATTERN.findall(content.lower()):
            cleaned = token.strip("'")
            if len(cleaned) < 3 or cleaned in ROAST_STOP_WORDS:
                continue
            words.append(cleaned)

    decision_markers = ("decide", "decided", "final", "approved", "ship", "confirmed", "agreed")
    action_markers = ("todo", "to do", "next", "follow up", "need to", "please", "let's")
    decision_lines = [
        line.split(": ", 1)[1][:140]
        for line in transcript
        if any(marker in line.lower() for marker in decision_markers)
    ][:3]
    action_lines = [
        line.split(": ", 1)[1][:140]
        for line in transcript
        if any(marker in line.lower() for marker in action_markers)
    ][:4]
    top_authors = ", ".join(f"{name} ({count})" for name, count in authors.most_common(3)) or "N/A"
    top_topics = ", ".join(word for word, _ in Counter(words).most_common(6)) or "general chat"
    reentry_prompt = (
        f"Jump back in by asking about `{top_topics.split(',')[0]}` in one line."
        if top_topics != "general chat"
        else "Jump back in by asking for a quick status update."
    )
    return (
        f"Key topics:\n- Message volume: `{len(transcript)}`\n"
        f"- Most active people: {top_authors}\n"
        f"- Main topics: {top_topics}\n"
        "Decisions:\n"
        + ("\n".join(f"- {line}" for line in decision_lines) if decision_lines else "- No clear decisions detected.")
        + "\nAction items:\n"
        + ("\n".join(f"- {line}" for line in action_lines) if action_lines else "- No clear action items detected.")
        + "\nRe-entry prompt:\n"
        + f"- {reentry_prompt}"
    )


async def build_catchup_summary(channel: discord.TextChannel, hours: int, transcript: list[str]) -> str:
    clipped_lines = trim_context_lines(transcript, max_lines=190, max_chars=CATCHUP_MAX_PROMPT_CHARS)
    prompt = (
        "Summarize missed Discord chat in concise bullet points.\n"
        "Output format exactly:\n"
        "Key topics:\n"
        "- 3-6 bullets\n"
        "Decisions:\n"
        "- bullets or `No clear decisions`\n"
        "Action items:\n"
        "- bullets or `No clear action items`\n"
        "Re-entry prompt:\n"
        "- one practical line to rejoin conversation\n"
        "Keep it compact and practical.\n\n"
        f"Window: last {hours} hours\n"
        f"Channel: #{channel.name}\n"
        "Transcript:\n"
        + "\n".join(clipped_lines)
    )
    messages = [
        {"role": "system", "content": AI_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    return await request_ai_completion(
        messages,
        max_tokens=AI_SUMMARY_MAX_TOKENS,
        temperature=0.2,
        policy_key="catchup",
    )


@dataclass
class ServerInsightsSnapshot:
    total_messages: int
    scanned_messages: int
    unique_users: int
    channel_counts: dict[int, int]
    day_counts: Counter[str]
    hour_counts: Counter[int]


async def collect_server_insights_snapshot(guild: discord.Guild, hours: int) -> ServerInsightsSnapshot:
    cutoff = discord.utils.utcnow() - timedelta(hours=hours)
    entries = await get_guild_window_cached(
        guild,
        full_history_scan=False,
        scan_per_channel=INSIGHTS_SCAN_PER_CHANNEL,
        max_history_messages=INSIGHTS_MAX_MESSAGES,
        pause_every=220,
        pause_seconds=0.05,
        after=cutoff,
        max_channels=INSIGHTS_MAX_CHANNELS,
        cache_ttl_seconds=min(INSIGHTS_CACHE_SECONDS, 180),
    )
    if not entries:
        return ServerInsightsSnapshot(0, 0, 0, {}, Counter(), Counter())

    total_messages = len(entries)
    users: set[int] = set()
    channel_counts: dict[int, int] = defaultdict(int)
    day_counts: Counter[str] = Counter()
    hour_counts: Counter[int] = Counter()
    for entry in entries:
        users.add(entry.author_id)
        channel_counts[entry.channel_id] += 1
        created_dt = discord.utils.snowflake_time(entry.message_id)
        day_counts[created_dt.strftime("%a")] += 1
        hour_counts[created_dt.hour] += 1

    return ServerInsightsSnapshot(
        total_messages=total_messages,
        scanned_messages=len(entries),
        unique_users=len(users),
        channel_counts=dict(channel_counts),
        day_counts=day_counts,
        hour_counts=hour_counts,
    )


def generate_server_insights_local(guild: discord.Guild, hours: int, snapshot: ServerInsightsSnapshot) -> str:
    if snapshot.total_messages <= 0:
        return "No user message activity was found in the selected window."

    top_channels = sorted(snapshot.channel_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    channel_lines: list[str] = []
    for channel_id, count in top_channels:
        channel = guild.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            channel_lines.append(f"- {channel.mention}: `{count}` messages")

    peak_hour = max(snapshot.hour_counts.items(), key=lambda item: item[1])[0] if snapshot.hour_counts else None
    weekday_total = sum(snapshot.day_counts.get(day, 0) for day in ("Mon", "Tue", "Wed", "Thu", "Fri"))
    weekend_total = snapshot.day_counts.get("Sat", 0) + snapshot.day_counts.get("Sun", 0)
    weekend_ratio = (weekend_total / max(1, weekday_total + weekend_total)) * 100

    suggestions = [
        "- Run one lightweight poll in the top-active channel during peak hours (expected: +10-20% conversation starts).",
        "- Start one recurring weekly prompt in a medium-activity channel (expected: stronger cross-channel retention).",
        "- Highlight quality threads once daily instead of extra announcements (expected: better depth, less noise).",
    ]
    if weekend_ratio < 20:
        suggestions[0] = "- Weekend engagement is low; schedule a Friday poll to seed weekend discussion (expected: higher weekend DAU)."

    hour_text = f"`{peak_hour:02d}:00 UTC`" if peak_hour is not None else "N/A"
    return (
        f"Server insights for last `{hours}` hour(s):\n"
        f"- Total user messages: `{snapshot.total_messages}`\n"
        f"- Active users: `{snapshot.unique_users}`\n"
        f"- Peak hour: {hour_text}\n"
        f"- Weekend share: `{weekend_ratio:.0f}%`\n"
        "Top channels:\n"
        + ("\n".join(channel_lines) if channel_lines else "- N/A")
        + "\nRecommendations:\n"
        + "\n".join(suggestions)
    )


async def build_server_insights_report(guild: discord.Guild, hours: int, snapshot: ServerInsightsSnapshot) -> str:
    top_channels = sorted(snapshot.channel_counts.items(), key=lambda item: item[1], reverse=True)[:8]
    top_channel_lines: list[str] = []
    for channel_id, count in top_channels:
        channel = guild.get_channel(channel_id)
        label = channel.name if isinstance(channel, discord.TextChannel) else str(channel_id)
        top_channel_lines.append(f"- #{label}: {count}")

    top_days = ", ".join(f"{day}:{count}" for day, count in snapshot.day_counts.most_common(7)) or "none"
    top_hours = ", ".join(f"{hour:02d}:00={count}" for hour, count in snapshot.hour_counts.most_common(8)) or "none"
    prompt = (
        "You are a Discord community engagement analyst.\n"
        "Generate concise, practical insights for moderators.\n"
        "Do not suggest spammy tactics.\n"
        "Output sections exactly:\n"
        "Snapshot:\n"
        "Trend diagnosis:\n"
        "What is working:\n"
        "Risks:\n"
        "Recommendations:\n"
        "Recommendations must be concrete, low-noise, and include expected effect.\n\n"
        f"Server: {guild.name}\n"
        f"Window hours: {hours}\n"
        f"Total user messages: {snapshot.total_messages}\n"
        f"Unique users: {snapshot.unique_users}\n"
        f"Scanned messages: {snapshot.scanned_messages}\n"
        f"Top channels:\n{chr(10).join(top_channel_lines) if top_channel_lines else '- none'}\n"
        f"Day distribution: {top_days}\n"
        f"Hour distribution: {top_hours}\n"
    )
    messages = [
        {"role": "system", "content": AI_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    return await request_ai_completion(
        messages,
        max_tokens=AI_SUMMARY_MAX_TOKENS,
        temperature=0.25,
        policy_key="serverinsights",
    )


async def run_catchup_for_channel(
    target: discord.abc.Messageable | commands.Context,
    channel: discord.TextChannel,
    hours: int,
) -> None:
    cache_key = (channel.guild.id, channel.id, hours)
    now = time.monotonic()
    cached = CATCHUP_CACHE.get(cache_key)
    if cached and now - cached[0] < CATCHUP_CACHE_SECONDS:
        await send_chunked(target, cached[1] + "\n\n_(Cached for faster response)_")
        return

    lock = CATCHUP_LOCKS[cache_key]
    async with lock:
        latest_cached = CATCHUP_CACHE.get(cache_key)
        if latest_cached and time.monotonic() - latest_cached[0] < CATCHUP_CACHE_SECONDS:
            await send_chunked(target, latest_cached[1] + "\n\n_(Cached for faster response)_")
            return

        cutoff = discord.utils.utcnow() - timedelta(hours=hours)
        transcript = await collect_channel_messages_since(
            channel,
            cutoff,
            max_messages=CATCHUP_MAX_MESSAGES,
        )
        if not transcript:
            await send_chunked(target, f"No recent user messages found in {channel.mention} for the last `{hours}` hour(s).")
            return

        try:
            summary = await build_catchup_summary(channel, hours, transcript)
        except Exception as error:
            print(f"[CATCHUP ERROR] {error}")
            summary = generate_catchup_local_summary(transcript, hours)

        payload = (
            f"â±ï¸ Catch-up for {channel.mention} (last `{hours}` hour(s), `{len(transcript)}` messages)\n"
            f"{summary}"
        )
        CATCHUP_CACHE[cache_key] = (time.monotonic(), payload)
    await send_chunked(target, payload)


async def run_server_insights(
    target: discord.abc.Messageable | commands.Context,
    guild: discord.Guild,
    hours: int,
) -> None:
    cache_key = (guild.id, hours)
    now = time.monotonic()
    cached = INSIGHTS_CACHE.get(cache_key)
    if cached and now - cached[0] < INSIGHTS_CACHE_SECONDS:
        await send_chunked(target, cached[1] + "\n\n_(Cached for faster response)_")
        return

    lock = INSIGHTS_LOCKS[cache_key]
    async with lock:
        latest_cached = INSIGHTS_CACHE.get(cache_key)
        if latest_cached and time.monotonic() - latest_cached[0] < INSIGHTS_CACHE_SECONDS:
            await send_chunked(target, latest_cached[1] + "\n\n_(Cached for faster response)_")
            return

        snapshot = await collect_server_insights_snapshot(guild, hours)
        if snapshot.total_messages <= 0:
            await send_chunked(
                target,
                f"No meaningful user activity found in **{guild.name}** for the last `{hours}` hour(s).",
            )
            return

        try:
            report = await build_server_insights_report(guild, hours, snapshot)
        except Exception as error:
            print(f"[SERVER INSIGHTS ERROR] {error}")
            report = generate_server_insights_local(guild, hours, snapshot)

        payload = (
            f"ðŸ“Š Server insights for **{guild.name}** (last `{hours}` hour(s))\n"
            f"{report}"
        )
        INSIGHTS_CACHE[cache_key] = (time.monotonic(), payload)
    await send_chunked(target, payload)


async def collect_recent_user_messages(
    channel: discord.TextChannel, user_id: int, limit: int
) -> list[str]:
    scan_limit = min(5000, max(limit * 8, limit + 120))
    entries = await get_channel_window_cached(
        channel,
        scan_limit=scan_limit,
        cache_ttl_seconds=90,
        include_attachment_marker=True,
    )
    messages = [entry.content[:260] for entry in entries if entry.author_id == user_id]
    return messages[-limit:]


async def collect_recent_user_messages_guild(
    guild: discord.Guild, user_id: int, limit: int
) -> tuple[list[str], list[WindowMessage]]:
    entries = await get_social_message_window(guild)
    user_entries = [entry for entry in entries if entry.author_id == user_id]
    if not user_entries:
        return [], []
    selected = user_entries[-limit:]
    return [entry.content[:260] for entry in selected], selected


def user_style_stats(user_messages: list[str]) -> dict[str, str]:
    if not user_messages:
        return {
            "avg_len": "0",
            "question_ratio": "0%",
            "exclaim_ratio": "0%",
            "emoji_per_msg": "0.00",
            "top_words": "none",
        }

    joined = " ".join(user_messages).lower()
    words = [w for w in WORD_PATTERN.findall(joined) if len(w) > 2]
    stop = {
        "the", "and", "for", "that", "with", "this", "you", "are", "was", "have", "not", "but",
        "just", "your", "from", "what", "when", "where", "will", "would", "they", "them", "their",
        "about", "there", "then", "than", "into", "also", "been", "can", "could", "should",
    }
    filtered = [w for w in words if w not in stop]
    common = [w for w, _ in Counter(filtered).most_common(5)]
    avg_len = sum(len(m) for m in user_messages) / max(1, len(user_messages))
    question_ratio = sum(1 for m in user_messages if "?" in m) / max(1, len(user_messages))
    exclaim_ratio = sum(1 for m in user_messages if "!" in m) / max(1, len(user_messages))
    emoji_count = sum(len(EMOJI_PATTERN.findall(m)) for m in user_messages)
    emoji_per_msg = emoji_count / max(1, len(user_messages))
    return {
        "avg_len": f"{avg_len:.1f}",
        "question_ratio": f"{question_ratio * 100:.0f}%",
        "exclaim_ratio": f"{exclaim_ratio * 100:.0f}%",
        "emoji_per_msg": f"{emoji_per_msg:.2f}",
        "top_words": ", ".join(common) if common else "none",
    }


def analyze_confidence_band(message_count: int, vocab_diversity: float) -> str:
    if message_count >= 180 and vocab_diversity >= 0.42:
        return "High"
    if message_count >= 90 and vocab_diversity >= 0.3:
        return "Medium"
    return "Low"


def derive_analyze_actionables(
    guild: discord.Guild,
    user_entries: list[WindowMessage],
    top_words: list[str],
    question_ratio: float,
    exclaim_ratio: float,
) -> tuple[str, str, str]:
    channel_counts: Counter[int] = Counter(entry.channel_id for entry in user_entries)
    hour_counts: Counter[int] = Counter(
        discord.utils.snowflake_time(entry.message_id).hour for entry in user_entries
    )
    best_channel_fit = "General discussion"
    if channel_counts:
        top_channel_id, _ = channel_counts.most_common(1)[0]
        top_channel = guild.get_channel(top_channel_id)
        if isinstance(top_channel, discord.TextChannel):
            best_channel_fit = f"#{top_channel.name}"

    if question_ratio >= 0.3:
        trigger = "Respond when they ask direct questions or ask for opinions."
    elif exclaim_ratio >= 0.22:
        trigger = "High-energy threads and hype moments get their best engagement."
    else:
        trigger = "They engage best on clear prompts and structured topics."

    if hour_counts:
        peak_hour = hour_counts.most_common(1)[0][0]
        best_time = f"{peak_hour:02d}:00 UTC"
    else:
        best_time = "No clear pattern"

    if top_words:
        trigger += f" Top recurring keywords: {', '.join(top_words[:3])}."

    return best_channel_fit, trigger, best_time


async def request_fun_ai(
    user_prompt: str,
    *,
    max_tokens: int = 220,
    temperature: float = 0.8,
    policy_key: str = "fun",
    fun_mode: str = "spicy",
    model_override: str | None = None,
    fallback_models: list[str] | None = None,
) -> str:
    mode_instruction = {
        "wholesome": "Keep tone warm and playful with very low insult intensity.",
        "balanced": "Keep tone witty with medium spice and avoid excessive aggression.",
        "spicy": "Keep tone bold and spicy, but still safe and non-hateful.",
    }.get(fun_mode, "Keep tone witty and playful.")
    messages = [
        {
            "role": "system",
            "content": (
                "You are a witty Discord assistant for fun community features. "
                "Keep outputs entertaining but avoid hate speech, slurs, sexual content about minors, "
                "or severe harassment. Keep responses compact and readable. "
                f"{mode_instruction}"
            ),
        },
        {"role": "user", "content": user_prompt},
    ]
    return await request_ai_completion(
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        policy_key=policy_key,
        model_override=model_override,
        fallback_models=fallback_models,
    )


async def generate_vibe_report(
    member: discord.Member, user_messages: list[str], replies_received: list[str]
) -> str:
    user_lines, reply_lines = build_vibe_prompt_lines(user_messages, replies_received)
    user_transcript = "\n".join(f"- {line}" for line in user_lines)
    replies_transcript = "\n".join(f"- {line}" for line in reply_lines) if reply_lines else "- (No clear replies found in range)"
    prompt = (
        "Create a Discord behavior snapshot in a paragraph format.\n"
        "Rules:\n"
        "1) Fun-only, non-diagnostic.\n"
        "2) No mental health or medical labels.\n"
        "3) Include balanced positives and rough edges only if observable.\n"
        "4) Use hedge words (e.g., seems, appears) for uncertain claims.\n"
        "5) No direct quotes from messages.\n"
        "6) Keep output under 240 words.\n\n"
        "Output format (exact headings, paragraph under each):\n"
        "Behavior Snapshot:\n"
        "How Others Respond:\n"
        "Balanced Take:\n"
        "Disclaimer:\n\n"
        f"User: {member.display_name}\n"
        f"Total user messages analyzed: {len(user_messages)}\n"
        f"Messages included in prompt: {len(user_lines)}\n"
        f"Replies included in prompt: {len(reply_lines)}\n\n"
        "User messages:\n"
        f"{user_transcript}\n\n"
        "Replies from others to this user:\n"
        f"{replies_transcript}"
    )
    ai_messages = [
        {"role": "system", "content": VIBE_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    return await request_ai_completion(
        ai_messages,
        max_tokens=260,
        temperature=0.35,
        policy_key="vibe",
    )


async def delete_recent_user_messages(
    channel: discord.TextChannel | discord.Thread, user_id: int, limit: int
) -> int:
    deleted = 0
    async for msg in channel.history(limit=120):
        if msg.author.id != user_id:
            continue
        try:
            await msg.delete()
            deleted += 1
        except (discord.NotFound, discord.HTTPException):
            continue
        if deleted >= limit:
            break
    return deleted


async def apply_automod_action(
    message: discord.Message,
    action: str,
    reason: str,
    *,
    timeout_minutes: int = 0,
    delete_count: int = 1,
) -> None:
    deleted_count = await delete_recent_user_messages(
        message.channel, message.author.id, max(delete_count, 1)
    )
    strike_count = 1
    escalation_timeout = 0
    review_flag = False
    if get_guild_moderation_escalation_enabled(message.guild.id):
        strike_count, escalation_timeout, review_flag = register_automod_strike(
            message.guild.id, message.author.id
        )
    effective_timeout = max(timeout_minutes, escalation_timeout)
    timeout_applied = False

    if effective_timeout > 0 and isinstance(message.author, discord.Member):
        me = message.guild.me
        if me and me.guild_permissions.moderate_members:
            can_timeout = (
                message.author != message.guild.owner
                and message.author.top_role < me.top_role
                and not message.author.guild_permissions.administrator
            )
            if can_timeout:
                try:
                    until = discord.utils.utcnow() + timedelta(minutes=effective_timeout)
                    await message.author.timeout(until, reason=f"AutoMod: {reason}")
                    timeout_applied = True
                except discord.HTTPException:
                    timeout_applied = False

    reply = f"{message.author.mention}, message removed (`strike {strike_count}`)."
    if timeout_applied:
        reply += f" Timeout: `{effective_timeout}`m."
    if review_flag:
        reply += " Flagged for moderator review."

    try:
        await message.channel.send(reply, delete_after=5)
    except discord.HTTPException:
        pass

    details = f"Deleted messages: `{deleted_count}`. Strike: `{strike_count}`."
    if timeout_applied:
        details += f" Timeout: `{effective_timeout}` minute(s)."
    if review_flag:
        details += " Review flag: `yes`."
    log_channel = message.channel
    if isinstance(message.channel, discord.Thread) and isinstance(message.channel.parent, discord.TextChannel):
        log_channel = message.channel.parent
    await send_mod_log(
        message.guild,
        action,
        target=message.author,
        moderator=bot.user,
        reason=reason,
        channel=log_channel,
        details=details,
    )
    if isinstance(log_channel, discord.TextChannel):
        await apply_channel_heat_event(
            log_channel,
            action=action,
            moderator=bot.user,
        )
    await agentic_on_automod_violation(message, action, reason)


async def _send_automation_message(
    guild: discord.Guild,
    content: str,
    *,
    prefer_channel: discord.TextChannel | None = None,
) -> bool:
    if not get_guild_auto_loops_enabled(guild.id):
        return False
    if not can_send_automation_post(guild.id):
        return False
    me = guild.me
    if me is None:
        return False

    channel: discord.TextChannel | None = None
    if AUTO_LOOP_HUB_CHANNEL_ONLY:
        channel = resolve_engagement_channel(guild)
    else:
        channel = prefer_channel or resolve_engagement_channel(guild)
    if channel is None:
        return False
    perms = channel.permissions_for(me)
    if not perms.view_channel or not perms.send_messages:
        channel = resolve_engagement_channel(guild)
        if channel is None:
            return False
        perms = channel.permissions_for(me)
        if not perms.view_channel or not perms.send_messages:
            return False
    try:
        await channel.send(content)
        return True
    except discord.HTTPException:
        return False


async def maybe_run_daily_engagement_posts(guild: discord.Guild) -> None:
    if not ENGAGEMENT_ENABLED:
        return
    if not get_guild_auto_loops_enabled(guild.id):
        return
    guild_state = get_guild_engagement_state(guild.id)
    automation = guild_state.setdefault("automation", {})
    day_key = _guild_day_key(guild.id)

    if str(automation.get("icebreaker_day", "")) != day_key:
        icebreaker = random.choice(ICEBREAKER_PROMPTS)
        posted = await _send_automation_message(
            guild,
            f"ðŸ§Š **Daily Icebreaker**\n{icebreaker}",
        )
        if posted:
            automation["icebreaker_day"] = day_key
            _mark_engagement_dirty()

    if str(automation.get("challenge_day", "")) != day_key:
        challenge = random.choice(DAILY_CHALLENGES)
        posted = await _send_automation_message(
            guild,
            f"ðŸŽ¯ **Daily Challenge**\n{challenge}\nUse `&daily` to track quest progress.",
        )
        if posted:
            automation["challenge_day"] = day_key
            _mark_engagement_dirty()


async def maybe_run_recap_nudge(guild: discord.Guild) -> None:
    if not ENGAGEMENT_ENABLED:
        return
    if not get_guild_auto_loops_enabled(guild.id):
        return
    guild_state = get_guild_engagement_state(guild.id)
    automation = guild_state.setdefault("automation", {})
    now = time.monotonic()
    last_recap = float(automation.get("last_recap_ts", 0.0))
    if now - last_recap < 6 * 60 * 60:
        return

    cutoff = _utc_now() - timedelta(hours=6)
    active_channel: discord.TextChannel | None = None
    best_window: list[WindowMessage] = []
    for channel in get_readable_text_channels(guild)[:18]:
        window = await get_channel_window_cached(
            channel,
            after=cutoff,
            scan_limit=180,
            cache_ttl_seconds=90,
        )
        if len(window) > len(best_window):
            best_window = window
            active_channel = channel
    if active_channel is None or len(best_window) < 8:
        return
    recap = _build_recap_from_window(best_window[-120:])
    target = active_channel if not AUTO_LOOP_HUB_CHANNEL_ONLY else None
    posted = await _send_automation_message(
        guild,
        f"ðŸ§¾ **Mini Catch-up** (`#{active_channel.name}`)\n{recap}\nUse `&catchup 24` for full summary.",
        prefer_channel=target,
    )
    if posted:
        automation["last_recap_ts"] = now
        _mark_engagement_dirty()


async def maybe_run_thread_reviver(guild: discord.Guild) -> None:
    if AUTO_LOOP_HUB_CHANNEL_ONLY:
        return
    if not ENGAGEMENT_ENABLED:
        return
    if not get_guild_auto_loops_enabled(guild.id):
        return
    guild_state = get_guild_engagement_state(guild.id)
    automation = guild_state.setdefault("automation", {})
    now = time.monotonic()
    last_revive = float(automation.get("last_thread_revive_ts", 0.0))
    if now - last_revive < 10 * 60 * 60:
        return

    me = guild.me
    if me is None:
        return
    candidate: discord.Thread | None = None
    for thread in list(guild.threads)[:25]:
        if thread.locked or thread.archived:
            continue
        if not thread.permissions_for(me).send_messages:
            continue
        if getattr(thread, "message_count", 0) < 8:
            continue
        last_id = getattr(thread, "last_message_id", None)
        if last_id is None:
            continue
        last_ts = discord.utils.snowflake_time(last_id).replace(tzinfo=timezone.utc).timestamp()
        if time.time() - last_ts < 6 * 60 * 60:
            continue
        candidate = thread
        break
    if candidate is None:
        return

    if not can_send_automation_post(guild.id):
        return
    try:
        await candidate.send(random.choice(THREAD_REVIVE_PROMPTS))
    except discord.HTTPException:
        return
    automation["last_thread_revive_ts"] = now
    _mark_engagement_dirty()


async def run_engagement_automation_tick() -> None:
    for guild in bot.guilds:
        try:
            await maybe_run_daily_engagement_posts(guild)
            await maybe_run_recap_nudge(guild)
            await maybe_run_thread_reviver(guild)
        except Exception as error:
            print(f"[ENGAGEMENT LOOP ERROR] guild={guild.id} error={error}")


async def finalize_expired_events() -> None:
    now = time.monotonic()
    expired: list[int] = []
    for guild_id, session in EVENT_SESSIONS.items():
        ends_at = float(session.get("ends_at", 0.0))
        if ends_at > 0 and now >= ends_at:
            expired.append(guild_id)
    for guild_id in expired:
        guild = bot.get_guild(guild_id)
        if guild is None:
            EVENT_SESSIONS.pop(guild_id, None)
            continue
        await finalize_event_session(guild, reason="timer")


@tasks.loop(seconds=float(ENGAGEMENT_STATE_FLUSH_SECONDS))
async def engagement_state_flush_loop() -> None:
    await flush_engagement_state()


@tasks.loop(seconds=float(ALTFINDER_STATE_FLUSH_SECONDS))
async def altfinder_state_flush_loop() -> None:
    await flush_altfinder_state()


@tasks.loop(seconds=float(SOCIALINTEL_STATE_FLUSH_SECONDS))
async def socialintel_state_flush_loop() -> None:
    await flush_socialintel_state()


@tasks.loop(minutes=1.0)
async def engagement_tick_loop() -> None:
    await finalize_expired_events()
    await release_expired_heat_slowmodes()
    await run_engagement_automation_tick()


@tasks.loop(seconds=30.0)
async def ai_mod_state_flush_loop() -> None:
    await flush_ai_mod_state()


@tasks.loop(minutes=1.0)
async def ai_mod_tick_loop() -> None:
    await run_ai_mod_tick()


@tasks.loop(minutes=5.0)
async def capabilities_catalog_refresh_loop() -> None:
    try:
        get_capabilities_catalog(force_refresh=False)
    except Exception as error:
        print(f"[CAPABILITY CATALOG REFRESH ERROR] {error}")


@tasks.loop(seconds=float(BUSINESS_STATE_FLUSH_SECONDS))
async def business_state_flush_loop() -> None:
    await flush_business_state()


@tasks.loop(minutes=1.0)
async def business_tick_loop() -> None:
    if not BUSINESS_ENABLED:
        return
    try:
        await _business_expire_trades_and_auctions()
        await run_business_hourly_tick()
    except Exception as error:
        print(f"[BUSINESS TICK ERROR] {error}")


@tasks.loop(minutes=3.0)
async def threadrevive_proactive_loop() -> None:
    try:
        await run_threadrevive_proactive_tick()
    except Exception as error:
        print(f"[THREADREVIVE PROACTIVE ERROR] {error}")


@engagement_state_flush_loop.before_loop
async def _before_engagement_flush_loop() -> None:
    await bot.wait_until_ready()


@altfinder_state_flush_loop.before_loop
async def _before_altfinder_flush_loop() -> None:
    await bot.wait_until_ready()


@socialintel_state_flush_loop.before_loop
async def _before_socialintel_flush_loop() -> None:
    await bot.wait_until_ready()


@engagement_tick_loop.before_loop
async def _before_engagement_tick_loop() -> None:
    await bot.wait_until_ready()


@ai_mod_state_flush_loop.before_loop
async def _before_ai_mod_state_flush_loop() -> None:
    await bot.wait_until_ready()


@ai_mod_tick_loop.before_loop
async def _before_ai_mod_tick_loop() -> None:
    await bot.wait_until_ready()


@capabilities_catalog_refresh_loop.before_loop
async def _before_capabilities_catalog_refresh_loop() -> None:
    await bot.wait_until_ready()


@business_state_flush_loop.before_loop
async def _before_business_flush_loop() -> None:
    await bot.wait_until_ready()


@business_tick_loop.before_loop
async def _before_business_tick_loop() -> None:
    await bot.wait_until_ready()


@threadrevive_proactive_loop.before_loop
async def _before_threadrevive_proactive_loop() -> None:
    await bot.wait_until_ready()


@bot.event
async def on_ready() -> None:
    global FFMPEG_EXECUTABLE, APP_COMMANDS_SYNCED
    count = reload_bad_words()
    capabilities_catalog = rebuild_capabilities_catalog()
    capabilities_count = 0
    if isinstance(capabilities_catalog, dict):
        commands_raw = capabilities_catalog.get("commands", {})
        if isinstance(commands_raw, dict):
            capabilities_count = len(commands_raw)
    FFMPEG_EXECUTABLE = resolve_ffmpeg_executable()
    if BOT_ACTIVITY_TEXT:
        try:
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.playing,
                    name=BOT_ACTIVITY_TEXT,
                )
            )
        except discord.HTTPException:
            pass
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Bot is online. Loaded {count} blocked words.")
    print(f"Capability catalog ready with {capabilities_count} commands.")
    if FFMPEG_EXECUTABLE:
        print(f"FFmpeg executable: {FFMPEG_EXECUTABLE}")
    else:
        print("FFmpeg executable not found. Music playback commands will fail.")
    if SYNC_SLASH_COMMANDS and not APP_COMMANDS_SYNCED:
        try:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} slash commands.")
        except Exception as error:
            print(f"[SLASH SYNC ERROR] {error}")
        APP_COMMANDS_SYNCED = True
    if ENGAGEMENT_ENABLED:
        if not engagement_state_flush_loop.is_running():
            engagement_state_flush_loop.start()
        if not engagement_tick_loop.is_running():
            engagement_tick_loop.start()
    if not altfinder_state_flush_loop.is_running():
        altfinder_state_flush_loop.start()
    if not socialintel_state_flush_loop.is_running():
        socialintel_state_flush_loop.start()
    if not ai_mod_state_flush_loop.is_running():
        ai_mod_state_flush_loop.start()
    if not ai_mod_tick_loop.is_running():
        ai_mod_tick_loop.start()
    if not capabilities_catalog_refresh_loop.is_running():
        capabilities_catalog_refresh_loop.start()
    if not agentic_tick_loop.is_running():
        agentic_tick_loop.start()
    if DISCORD_ENABLE_PRESENCE_INTENT:
        for guild in bot.guilds:
            try:
                refresh_altfinder_member_directory(guild)
                refresh_socialintel_member_directory(guild)
                for member in guild.members:
                    if member.bot:
                        continue
                    guild_state = get_guild_altfinder_state(guild.id)
                    row = _altfinder_get_user_row(guild_state, member.id)
                    _altfinder_sync_presence_snapshot(row, member, increment_history=False)
            except Exception as error:
                print(f"[ALTFINDER PRESENCE BOOTSTRAP ERROR] guild={guild.id} error={error}")
    if THREADREVIVE_PROACTIVE_ENABLED and not threadrevive_proactive_loop.is_running():
        threadrevive_proactive_loop.start()
    if BUSINESS_ENABLED:
        if not business_state_flush_loop.is_running():
            business_state_flush_loop.start()
        if not business_tick_loop.is_running():
            business_tick_loop.start()


@bot.event
async def on_member_join(member: discord.Member) -> None:
    try:
        await send_welcome_concierge(member)
    except Exception as error:
        print(f"[WELCOME CONCIERGE ERROR] {error}")


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    if after.bot:
        return
    try:
        guild_state = get_guild_altfinder_state(after.guild.id)
        row = _altfinder_get_user_row(guild_state, after.id)
        _altfinder_apply_user_snapshot(row, after)
        _altfinder_sync_presence_snapshot(row, after, increment_history=False)
        _mark_altfinder_dirty()
        _altfinder_invalidate_guild_cache(after.guild.id)
    except Exception as error:
        print(f"[ALTFINDER MEMBER UPDATE ERROR] guild={after.guild.id} user={after.id} error={error}")
    try:
        guild_state = get_guild_socialintel_state(after.guild.id)
        row = _altfinder_get_user_row(guild_state, after.id)
        _altfinder_apply_user_snapshot(row, after)
        _altfinder_sync_presence_snapshot(row, after, increment_history=False)
        _mark_socialintel_dirty()
        _socialintel_invalidate_guild_cache(after.guild.id)
    except Exception as error:
        print(f"[SOCIALINTEL MEMBER UPDATE ERROR] guild={after.guild.id} user={after.id} error={error}")


@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member) -> None:
    if after.bot:
        return
    try:
        record_altfinder_presence(after)
    except Exception as error:
        print(f"[ALTFINDER PRESENCE ERROR] guild={after.guild.id} user={after.id} error={error}")
    try:
        record_socialintel_presence(after)
    except Exception as error:
        print(f"[SOCIALINTEL PRESENCE ERROR] guild={after.guild.id} user={after.id} error={error}")


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    if message.guild is None:
        normalized_dm = " ".join(message.content.strip().lower().split())
        if normalized_dm == "remove timeout":
            removed, active_found, failed = await remove_timeout_from_dm_request(message.author.id)
            if removed > 0:
                await message.channel.send(
                    f"Done. Your timeout was removed in `{removed}` server(s)."
                )
            elif active_found > 0 and failed > 0:
                await message.channel.send(
                    "I found your timeout, but I couldn't remove it due to role/permission limits."
                )
            else:
                await message.channel.send("You do not currently have an active timeout.")
            return

        try:
            if await handle_welcome_concierge_dm(message):
                return
        except Exception as error:
            print(f"[WELCOME DM HANDLER ERROR] {error}")

        if message.content.startswith(PREFIX):
            await bot.process_commands(message)
            return

        try:
            if await handle_active_psych_session_turn(message):
                return
        except Exception as error:
            print(f"[PSYCH MODE DM ERROR] {error}")

        try:
            addressed_text = strip_bot_address_prefix(message)
            if addressed_text:
                psych_action, psych_seed = parse_psych_alias_request(addressed_text)
                if psych_action is not None:
                    await run_psych_action_for_user(
                        message.channel,
                        channel_id=message.channel.id,
                        user_id=message.author.id,
                        user_display_name=get_user_display_name(message.author),
                        action=psych_action,
                        seed_text=psych_seed,
                    )
                    return
        except Exception as error:
            print(f"[PSYCH MODE DM ALIAS ERROR] {error}")

        await bot.process_commands(message)
        return

    if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
        await bot.process_commands(message)
        return

    if message.content.startswith(PREFIX):
        await bot.process_commands(message)
        return

    try:
        if await handle_active_psych_session_turn(message):
            return
    except Exception as error:
        print(f"[PSYCH MODE ERROR] {error}")

    try:
        if await handle_active_argument_mode_turn(message):
            return
    except Exception as error:
        print(f"[ARGUMENT MODE ERROR] {error}")

    member = message.author
    is_mod_member = isinstance(member, discord.Member) and (
        member.guild_permissions.administrator or member.guild_permissions.manage_messages
    )
    automod_enabled = get_guild_automod_enabled(message.guild.id)

    if automod_enabled and not is_mod_member:
        bad_word = matches_bad_word(message.content)
        if bad_word:
            await apply_automod_action(
                message,
                "AutoMod: Blocked Word",
                f"Blocked word detected: `{bad_word}`.",
            )
            return

        if BLOCK_LINKS and LINK_PATTERN.search(message.content):
            await apply_automod_action(
                message,
                "AutoMod: Blocked Link",
                "Links are not allowed in this server.",
            )
            return

        key = (message.guild.id, message.author.id)
        queue = SPAM_CACHE[key]
        queue.append(message.created_at.timestamp())
        if (
            len(queue) >= SPAM_MSG_THRESHOLD
            and queue[-1] - queue[-SPAM_MSG_THRESHOLD] <= SPAM_INTERVAL_SECONDS
        ):
            queue.clear()
            await apply_automod_action(
                message,
                "AutoMod: Spam",
                "Spam detected.",
                timeout_minutes=SPAM_TIMEOUT_MINUTES,
                delete_count=SPAM_MSG_THRESHOLD,
            )
            return

    try:
        if await maybe_run_ai_guard(message):
            return
    except Exception as error:
        print(f"[AI GUARD PIPELINE ERROR] {error}")

    try:
        index_altfinder_message(message, backfill=False)
    except Exception as error:
        print(f"[ALTFINDER INDEX ERROR] {error}")
    try:
        index_socialintel_message(message, backfill=False)
    except Exception as error:
        print(f"[SOCIALINTEL INDEX ERROR] {error}")

    try:
        if await handle_conversational_request(message):
            return
    except Exception as error:
        print(f"[CONVERSATIONAL COMMAND ERROR] {error}")

    try:
        await process_event_message(message)
    except Exception as error:
        print(f"[EVENT TRACK ERROR] {error}")
    try:
        apply_message_engagement_progress(message)
    except Exception as error:
        print(f"[ENGAGEMENT TRACK ERROR] {error}")

    await bot.process_commands(message)


@bot.event
async def on_message_delete(message: discord.Message) -> None:
    if message.guild is None or message.author.bot:
        return

    content = message.content.strip() if message.content else ""
    if not content and message.attachments:
        content = "[Attachment only]"
    if not content:
        return

    SNIPE_CACHE[message.channel.id] = {
        "author": str(message.author),
        "author_id": str(message.author.id),
        "content": content[:1800],
        "created_at": message.created_at.isoformat(),
    }


def _ai_mod_case_brief(case: dict[str, Any]) -> str:
    case_id = str(case.get("id", "CASE-?"))
    category = _ai_mod_normalize_category(case.get("category")).replace("_", "/")
    risk = _ai_mod_risk_score(case.get("risk_score"))
    status = str(case.get("status", "open"))
    action = str(case.get("action", "none"))
    return f"`{case_id}` | `{category}` | risk `{risk:.2f}` | action `{action}` | status `{status}`"


def _ai_mod_append_review_action(
    *,
    guild_id: int,
    case_id: str,
    reviewer_id: int,
    action: str,
    note: str,
) -> None:
    state = get_ai_mod_state()
    review_actions = state.setdefault("review_actions", [])
    if not isinstance(review_actions, list):
        review_actions = []
        state["review_actions"] = review_actions
    review_actions.append(
        {
            "ts": time.time(),
            "guild_id": int(guild_id),
            "case_id": case_id,
            "reviewer_id": int(reviewer_id),
            "action": action,
            "note": note[:220],
        }
    )
    if len(review_actions) > 20000:
        del review_actions[: (len(review_actions) - 20000)]
    _ai_mod_increment_metric("overrides")
    _mark_ai_mod_dirty()


async def _ai_mod_apply_override_action(
    ctx: commands.Context,
    case: dict[str, Any],
    action: str,
) -> tuple[bool, str]:
    guild = ctx.guild
    if guild is None:
        return False, "Guild context required."
    author_id = int(case.get("author_id", 0) or 0)
    member = guild.get_member(author_id)
    if member is None:
        try:
            member = await guild.fetch_member(author_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            member = None
    channel = guild.get_channel(int(case.get("channel_id", 0) or 0))
    if action == "none":
        if isinstance(member, discord.Member):
            me = guild.me
            if (
                me is not None
                and me.guild_permissions.moderate_members
                and member != guild.owner
                and member.top_role < me.top_role
            ):
                try:
                    await member.timeout(None, reason=f"AI Guard override none {case.get('id')}")
                    return True, "Timeout removed (if active)."
                except discord.HTTPException:
                    return True, "Override recorded (could not remove timeout due API error)."
        return True, "Override recorded."
    if action == "warn":
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            try:
                await channel.send(f"<@{author_id}> Moderator override: warning on case `{case.get('id')}`.")
                return True, "Warn message sent."
            except discord.HTTPException:
                return False, "Could not send warning message."
        return False, "Source channel not found for warning."
    if action == "timeout":
        if not isinstance(member, discord.Member):
            return False, "Target member not found in guild."
        me = guild.me
        if (
            me is None
            or not me.guild_permissions.moderate_members
            or member == guild.owner
            or member.top_role >= me.top_role
        ):
            return False, "Missing permission/role hierarchy for timeout."
        try:
            until = discord.utils.utcnow() + timedelta(minutes=20)
            await member.timeout(until, reason=f"AI Guard override timeout {case.get('id')}")
            return True, "Timeout applied (20m)."
        except discord.HTTPException:
            return False, "Timeout API call failed."
    if action == "ban":
        if not isinstance(member, discord.Member):
            return False, "Target member not found in guild."
        me = guild.me
        if (
            me is None
            or not me.guild_permissions.ban_members
            or member == guild.owner
            or member.top_role >= me.top_role
        ):
            return False, "Missing permission/role hierarchy for ban."
        try:
            await member.ban(reason=f"AI Guard override ban {case.get('id')}")
            return True, "Ban applied."
        except discord.HTTPException:
            return False, "Ban API call failed."
    return False, "Unsupported override action."


@bot.command(name="help")
async def help_command(ctx: commands.Context) -> None:
    text = (
        f"**Prefix:** `{PREFIX}`\n"
        "**Moderation Commands**\n"
        f"`{PREFIX}pb` - Delete bot/webhook messages from the most recent 20 messages in this channel.\n"
        f"`{PREFIX}pba` - Delete all bot/webhook messages from this channel.\n"
        f"`{PREFIX}clear <amount>` - Delete recent messages.\n"
        f"`{PREFIX}bulkdelete <#channel> <amount>` - Bulk delete from a specific channel.\n"
        f"`{PREFIX}kick <@member> [reason]`\n"
        f"`{PREFIX}ban <@member> [reason]`\n"
        f"`{PREFIX}unban <user_id> [reason]`\n"
        f"`{PREFIX}mute <@member> <minutes> [reason]` - Timeout a member.\n"
        f"`{PREFIX}unmute <@member> [reason]`\n"
        f"`{PREFIX}lock [reason]` / `{PREFIX}unlock [reason]`\n"
        f"`{PREFIX}slowmode <seconds>` - `0` disables.\n"
        f"`{PREFIX}warn <@member> <reason>`\n"
        f"`{PREFIX}warnings <@member>`\n"
        f"`{PREFIX}clearwarns <@member>`\n"
        f"`{PREFIX}setmodlog [#channel]` - Set mod-log channel (defaults to current channel).\n"
        f"`{PREFIX}clearmodlog` - Disable mod-log for this server.\n"
        f"`{PREFIX}crushgame <on|off|status> [#channel]` - Enable the Crush-o-Meter game (posts a one-time notice).\n"
        f"`{PREFIX}welcomeconcierge <on|off|status>` - Control AI welcome onboarding DMs.\n"
        f"`{PREFIX}setintrochannel [#channel]` / `{PREFIX}clearintrochannel`\n"
        f"`{PREFIX}automod <on|off|toggle|status>` - Enable or disable AutoMod in this server.\n"
        f"`{PREFIX}aiguard <on|off|status>`, `{PREFIX}aiguard layer <0-5>`\n"
        f"`{PREFIX}aiguard report <#channel|clear|status>` - Layer 1 periodic report destination.\n"
        f"`{PREFIX}aimodmode <shadow|enforce>` - AI guard rollout mode.\n"
        f"`{PREFIX}modqueue [open|mine|stats]`, `{PREFIX}case <case_id>`\n"
        f"`{PREFIX}override <case_id> <none|warn|timeout|ban>`, `{PREFIX}appeal <case_id> <reason>`\n"
        f"`{PREFIX}funmode <spicy|balanced|wholesome|status>`\n"
        f"`{PREFIX}engagementlimits <on|off|status>`\n"
        f"`{PREFIX}escalation <on|off|status>` - AutoMod warn/timeout ladder.\n"
        f"`{PREFIX}modguard <on|off|status>` - Heat-based temporary slowmode protection.\n"
        f"`{PREFIX}engagementhub <#channel|status|clear>`\n"
        f"`{PREFIX}autoloops <on|off|status>` - Daily icebreaker/challenge and recap loops.\n"
        f"`{PREFIX}questmode <on|off|status>` - Enable/disable daily quest tracking.\n"
        f"`{PREFIX}engagementtz <IANA timezone>` - Example: `Asia/Kolkata`.\n"
        f"`{PREFIX}reloadbadwords` - Reload `data/bad_words.txt`.\n"
        f"`{PREFIX}say <message>` - Moderator echo command (deletes your command message).\n"
        "\n"
        "**Utility/Fun Commands**\n"
        f"`{PREFIX}ping`\n"
        f"`{PREFIX}avatar [@member]`\n"
        f"`{PREFIX}userinfo [@member]`\n"
        f"`{PREFIX}serverinfo`\n"
        f"`{PREFIX}poll <question | option1 | option2 ...>` (2-10 options)\n"
        f"`{PREFIX}snipe` - Show last deleted non-bot message in this channel.\n"
        f"`{PREFIX}remind <minutes> <text>` - Sends you a DM reminder.\n"
        f"`{PREFIX}guide [question]` - Natural-language guide for using Bell features.\n"
        f"`{PREFIX}catchup [hours]` - Summarize what you missed in this channel.\n"
        f"`{PREFIX}catchupchannel <#channel> [hours]` - Catch up another channel.\n"
        f"`{PREFIX}cat` / `{PREFIX}food` - Send random cat or Indian veg food image.\n"
        f"`{PREFIX}rank`, `{PREFIX}leaderboard [daily|weekly|alltime]`\n"
        f"`{PREFIX}streak`, `{PREFIX}daily`, `{PREFIX}quests`\n"
        f"`{PREFIX}event start <trivia|hottake|caption>`, `{PREFIX}event stop`, `{PREFIX}event status`\n"
        "\n"
        "**Business Commands**\n"
        f"`{PREFIX}balance`, `{PREFIX}dailyclaim`, `{PREFIX}portfolio`, `{PREFIX}networth`\n"
        f"`{PREFIX}stocks`, `{PREFIX}market [symbol]`, `{PREFIX}buy <symbol> <qty>`, `{PREFIX}sell <symbol> <qty>`\n"
        f"`{PREFIX}commodities`, `{PREFIX}buycommodity <symbol> <qty>`, `{PREFIX}sellcommodity <symbol> <qty>`\n"
        f"`{PREFIX}crypto`, `{PREFIX}buycrypto <symbol> <qty>`, `{PREFIX}sellcrypto <symbol> <qty>`\n"
        f"`{PREFIX}plots`, `{PREFIX}buyplot <plot_id>`, `{PREFIX}upgrade <property_id>`, `{PREFIX}properties`\n"
        f"`{PREFIX}sellproperty <id> <price>`, `{PREFIX}buyproperty <id>`\n"
        f"`{PREFIX}loan`, `{PREFIX}takeloan <amount>`, `{PREFIX}repay <amount>`, `{PREFIX}debts`\n"
        f"`{PREFIX}startbiz <type> <name>`, `{PREFIX}mybiz`, `{PREFIX}bizhire <id> <count>`, `{PREFIX}bizfire <id> <count>`, `{PREFIX}bizexpand <id>`\n"
        f"`{PREFIX}salary`, `{PREFIX}taxes`, `{PREFIX}filetax [amount]`, `{PREFIX}credit`, `{PREFIX}markethalt`, `{PREFIX}economystatus`\n"
        f"`{PREFIX}trade <@user> <cash|stock|property> <asset> <amount> [request_cash]`\n"
        f"`{PREFIX}trade_accept <id>`, `{PREFIX}trade_decline <id>`\n"
        f"`{PREFIX}auction_start <stock|property> <id> <start_price> <duration_min> [qty]`, `{PREFIX}bid <id> <amount>`, `{PREFIX}auctions`\n"
        f"`{PREFIX}bizleaderboard [cash|networth|income]`, `{PREFIX}bizprofile [@user]`, `{PREFIX}marketnews`, `{PREFIX}ledger [@user]`\n"
        f"`{PREFIX}bizhelp [question]` - Game guide in natural language (example: `how do I start`).\n"
        f"`{PREFIX}bizadmin <...>` - mod-only economy controls.\n"
        "Conversational examples: `bell how do I start the game`, `bell explain loans`, `bell how taxes work`.\n"
        "\n"
        "**AI Commands**\n"
        f"`{PREFIX}ai <prompt>` - Ask AI with per-channel memory.\n"
        f"`{PREFIX}aireset` - Clear AI memory for this channel.\n"
        f"`{PREFIX}aimodel` - Show active AI provider/model.\n"
        f"`{PREFIX}aimodels [limit]` - List currently available models from active provider.\n"
        f"`{PREFIX}aisummary [count]` - Summarize recent channel messages.\n"
        f"`{PREFIX}translate [text|message link]` - Translate mixed-language chat into English, or reply to a message and run it.\n"
        f"`{PREFIX}serverinsights [hours]` - Mod-only engagement insights across channels.\n"
        f"`{PREFIX}psych [start|stop|reset|status] [message]` - Listen-first psych mode (replies after pause, asks before advice).\n"
        f"`{PREFIX}roast <@user> [soft|friendly|brutal]` - Personal roast from server-wide chat patterns.\n"
        f"`{PREFIX}serverlore`, `{PREFIX}crush [@user] [answer]` (a joke game about you), `{PREFIX}analyze <@user>`\n"
        f"`{PREFIX}exclude` / `{PREFIX}include` - Opt out of (or back into) fun features. `{PREFIX}wipe` - Delete your stored fun data.\n"
        f"`{PREFIX}lie_detector <@user> <message>`, `{PREFIX}futureme`\n"
        f"`{PREFIX}rizzcoach [smooth|funny|mysterious] <message>`\n"
        f"`{PREFIX}argument <topic>` - starts persistent argument mode (`bell stop argument` to end).\n"
        f"`{PREFIX}debate <@user> <topic>`\n"
        "\n"
        "**Vibe Commands**\n"
        f"`{PREFIX}myvibe [count]` - Analyze your own recent messages in this channel.\n"
        f"`{PREFIX}vibe <@user> [count]` - Analyze user messages in this channel.\n"
        f"`{PREFIX}vibecheck <@user>` - Fun short vibe stats from last 200 messages.\n"
        "\n"
        "**Music Commands**\n"
        f"`{PREFIX}join` / `{PREFIX}leave`\n"
        f"`{PREFIX}play <youtube/spotify link or search>`\n"
        f"`{PREFIX}skip`, `{PREFIX}pause`, `{PREFIX}resume`, `{PREFIX}stop`\n"
        f"`{PREFIX}queue`, `{PREFIX}nowplaying`\n"
    )
    await send_chunked(ctx, text)


@bot.command(name="setmodlog")
@commands.has_permissions(manage_guild=True)
async def set_modlog_channel(
    ctx: commands.Context, channel: discord.TextChannel | None = None
) -> None:
    target_channel = channel or ctx.channel
    config = load_mod_config()
    guild_key = str(ctx.guild.id)
    config.setdefault(guild_key, {})
    config[guild_key]["mod_log_channel_id"] = target_channel.id
    save_mod_config(config)

    await ctx.send(f"Mod-log channel set to {target_channel.mention}.")
    await send_mod_log(
        ctx.guild,
        "Config: Mod Log Set",
        moderator=ctx.author,
        channel=target_channel,
        details=f"Channel ID: `{target_channel.id}`",
    )


@bot.command(name="clearmodlog")
@commands.has_permissions(manage_guild=True)
async def clear_modlog_channel(ctx: commands.Context) -> None:
    config = load_mod_config()
    guild_key = str(ctx.guild.id)
    if guild_key in config and "mod_log_channel_id" in config[guild_key]:
        del config[guild_key]["mod_log_channel_id"]
        save_mod_config(config)
    await ctx.send("Mod-log channel disabled for this server.")


@bot.command(name="welcomeconcierge")
@commands.has_permissions(manage_guild=True)
async def welcome_concierge_command(ctx: commands.Context, mode: str | None = None) -> None:
    current = get_guild_welcome_concierge_enabled(ctx.guild.id)
    normalized = (mode or "").strip().lower()

    if normalized in {"", "status", "state"}:
        state_text = "enabled" if current else "disabled"
        intro_channel = find_intro_channel_for_guild(ctx.guild)
        intro_text = intro_channel.mention if intro_channel else "(not found)"
        await ctx.send(
            f"Welcome concierge is currently **{state_text}**.\n"
            f"Intro/default channel: {intro_text}"
        )
        return

    if normalized in {"on", "enable", "enabled", "true", "1"}:
        new_state = True
    elif normalized in {"off", "disable", "disabled", "false", "0"}:
        new_state = False
    else:
        await ctx.send(f"Usage: `{PREFIX}welcomeconcierge <on|off|status>`")
        return

    set_guild_welcome_concierge_enabled(ctx.guild.id, new_state)
    state_text = "enabled" if new_state else "disabled"
    await ctx.send(f"Welcome concierge is now **{state_text}**.")


@bot.command(name="setintrochannel")
@commands.has_permissions(manage_guild=True)
async def set_intro_channel(
    ctx: commands.Context, channel: discord.TextChannel | None = None
) -> None:
    target = channel or ctx.channel
    set_guild_intro_channel_id(ctx.guild.id, target.id)
    await ctx.send(f"Intro channel set to {target.mention}.")


@bot.command(name="clearintrochannel")
@commands.has_permissions(manage_guild=True)
async def clear_intro_channel(ctx: commands.Context) -> None:
    set_guild_intro_channel_id(ctx.guild.id, None)
    await ctx.send("Cleared custom intro channel. Bell will auto-detect intro/general channel.")


@bot.command(name="reloadbadwords")
@commands.has_permissions(manage_guild=True)
async def reload_bad_words_command(ctx: commands.Context) -> None:
    count = reload_bad_words()
    await ctx.send(f"Reloaded blocked words. Active entries: `{count}`.")


@bot.command(name="automod")
@commands.guild_only()
async def automod_command(ctx: commands.Context, mode: str | None = None) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can change AutoMod settings.")
        return

    current = get_guild_automod_enabled(ctx.guild.id)
    normalized = (mode or "").strip().lower()

    if normalized in {"", "toggle"}:
        new_state = not current
    elif normalized in {"on", "enable", "enabled", "true", "1"}:
        new_state = True
    elif normalized in {"off", "disable", "disabled", "false", "0"}:
        new_state = False
    elif normalized in {"status", "state"}:
        state_text = "enabled" if current else "disabled"
        await ctx.send(f"Auto moderation is currently **{state_text}** in this server.")
        return
    else:
        await ctx.send(f"Usage: `{PREFIX}automod <on|off|toggle|status>`")
        return

    set_guild_automod_enabled(ctx.guild.id, new_state)
    state_text = "enabled" if new_state else "disabled"
    await ctx.send(f"Auto moderation is now **{state_text}** in this server.")
    await send_mod_log(
        ctx.guild,
        "Config: AutoMod Updated",
        moderator=ctx.author,
        channel=ctx.channel,
        details=f"New state: `{state_text}`",
    )


@bot.hybrid_command(name="aiguard")
@commands.guild_only()
async def aiguard_command(
    ctx: commands.Context,
    action: str | None = None,
    value: str | None = None,
) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can manage AI Guard settings.")
        return
    normalized_action = (action or "status").strip().lower()
    if normalized_action in {"status", "state", ""}:
        enabled = get_guild_ai_guard_enabled(ctx.guild.id)
        layer = get_guild_ai_guard_layer(ctx.guild.id)
        configured_mode = get_guild_ai_guard_mode(ctx.guild.id)
        effective_mode, forced_shadow = _ai_mod_effective_mode(ctx.guild.id)
        strictness = get_guild_ai_guard_strictness(ctx.guild.id)
        report_channel_id = get_guild_ai_guard_report_channel_id(ctx.guild.id)
        report_channel = ctx.guild.get_channel(report_channel_id) if report_channel_id else None
        await ctx.send(
            "AI Guard status:\n"
            f"- Enabled: `{'yes' if enabled else 'no'}`\n"
            f"- Layer: `{layer}`\n"
            f"- Mode: configured `{configured_mode}`, effective `{effective_mode}`"
            + (" (shadow-forced)" if forced_shadow else "")
            + "\n"
            f"- Strictness: `{strictness}`\n"
            f"- Report channel: {report_channel.mention if isinstance(report_channel, discord.TextChannel) else '(not set)'}"
        )
        return
    if normalized_action in {"on", "enable", "enabled", "true", "1"}:
        set_guild_ai_guard_enabled(ctx.guild.id, True)
        if get_guild_ai_guard_layer(ctx.guild.id) == 0:
            set_guild_ai_guard_layer(ctx.guild.id, 1)
        await ctx.send("AI Guard enabled.")
        return
    if normalized_action in {"off", "disable", "disabled", "false", "0"}:
        set_guild_ai_guard_enabled(ctx.guild.id, False)
        await ctx.send("AI Guard disabled.")
        return
    if normalized_action == "layer":
        if value is None:
            await ctx.send(f"Usage: `{PREFIX}aiguard layer <0-5>`")
            return
        try:
            layer = max(0, min(5, int(value)))
        except ValueError:
            await ctx.send(f"Layer must be `0` to `5`. Usage: `{PREFIX}aiguard layer <0-5>`")
            return
        set_guild_ai_guard_layer(ctx.guild.id, layer)
        if layer == 0:
            set_guild_ai_guard_enabled(ctx.guild.id, False)
        else:
            set_guild_ai_guard_enabled(ctx.guild.id, True)
        await ctx.send(f"AI Guard layer set to `{layer}`.")
        return
    if normalized_action == "report":
        raw = (value or "").strip().lower()
        if raw in {"", "status", "state"}:
            report_id = get_guild_ai_guard_report_channel_id(ctx.guild.id)
            report_channel = ctx.guild.get_channel(report_id) if report_id else None
            await ctx.send(
                "AI Guard report channel: "
                + (report_channel.mention if isinstance(report_channel, discord.TextChannel) else "(not set)")
            )
            return
        if raw in {"clear", "none", "off"}:
            set_guild_ai_guard_report_channel_id(ctx.guild.id, None)
            await ctx.send("AI Guard report channel cleared.")
            return
        candidate: discord.TextChannel | None = None
        if ctx.message is not None and ctx.message.channel_mentions:
            mention = ctx.message.channel_mentions[0]
            if isinstance(mention, discord.TextChannel):
                candidate = mention
        if candidate is None:
            match = re.search(r"\d+", value or "")
            if match:
                maybe_channel = ctx.guild.get_channel(int(match.group(0)))
                if isinstance(maybe_channel, discord.TextChannel):
                    candidate = maybe_channel
        if candidate is None:
            cleaned = raw.replace("#", "").strip()
            maybe_channel = discord.utils.find(lambda c: c.name.lower() == cleaned, ctx.guild.text_channels)
            if isinstance(maybe_channel, discord.TextChannel):
                candidate = maybe_channel
        if candidate is None:
            await ctx.send(f"Usage: `{PREFIX}aiguard report <#channel|clear|status>`")
            return
        set_guild_ai_guard_report_channel_id(ctx.guild.id, candidate.id)
        await ctx.send(f"AI Guard report channel set to {candidate.mention}.")
        return
    await ctx.send(
        f"Usage: `{PREFIX}aiguard <on|off|status>`, `{PREFIX}aiguard layer <0-5>`, "
        f"or `{PREFIX}aiguard report <#channel|clear|status>`"
    )


@bot.hybrid_command(name="aimodmode")
@commands.guild_only()
async def aimodmode_command(ctx: commands.Context, mode: str) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can change AI Guard mode.")
        return
    normalized = (mode or "").strip().lower()
    if normalized not in {"shadow", "enforce"}:
        await ctx.send(f"Usage: `{PREFIX}aimodmode <shadow|enforce>`")
        return
    set_guild_ai_guard_mode(ctx.guild.id, normalized)
    effective, forced = _ai_mod_effective_mode(ctx.guild.id)
    forced_text = " (temporarily shadow-forced by rollout window)" if forced else ""
    await ctx.send(f"AI Guard mode set to `{normalized}`. Effective mode: `{effective}`{forced_text}.")


@bot.hybrid_command(name="modqueue")
@commands.guild_only()
async def modqueue_command(ctx: commands.Context, scope: str | None = None) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can access the AI moderation queue.")
        return
    normalized = (scope or "open").strip().lower()
    state = get_ai_mod_state()
    if normalized == "stats":
        open_cases = _ai_mod_open_cases_for_guild(ctx.guild.id)
        metrics = state.get("metrics", {}) if isinstance(state.get("metrics"), dict) else {}
        await ctx.send(
            "AI Guard queue stats:\n"
            f"- Open cases: `{len(open_cases)}`\n"
            f"- Evaluated: `{int(metrics.get('evaluated', 0) or 0)}`\n"
            f"- Cases created: `{int(metrics.get('cases_created', 0) or 0)}`\n"
            f"- Enforced: `{int(metrics.get('enforced', 0) or 0)}`\n"
            f"- Overrides: `{int(metrics.get('overrides', 0) or 0)}`\n"
            f"- Appeals: `{int(metrics.get('appeals', 0) or 0)}`"
        )
        return
    if normalized == "mine":
        review_actions = state.get("review_actions", [])
        mine: list[dict[str, Any]] = []
        if isinstance(review_actions, list):
            for row in reversed(review_actions):
                if not isinstance(row, dict):
                    continue
                if int(row.get("guild_id", 0) or 0) != ctx.guild.id:
                    continue
                if int(row.get("reviewer_id", 0) or 0) != ctx.author.id:
                    continue
                mine.append(row)
                if len(mine) >= 10:
                    break
        if not mine:
            await ctx.send("No review actions found for you in this guild.")
            return
        lines = [
            f"`{row.get('case_id', 'CASE-?')}` -> `{row.get('action', 'none')}` ({int(max(0.0, time.time() - float(row.get('ts', 0.0) or 0.0)) // 60)}m ago)"
            for row in mine
        ]
        await send_chunked(ctx, "Your recent queue actions:\n" + "\n".join(lines))
        return
    if normalized not in {"open", ""}:
        await ctx.send(f"Usage: `{PREFIX}modqueue [open|mine|stats]`")
        return
    rows = _ai_mod_open_cases_for_guild(ctx.guild.id)[:12]
    if not rows:
        await ctx.send("No open AI Guard cases.")
        return
    lines = [_ai_mod_case_brief(row) for row in rows]
    await send_chunked(ctx, "Open AI Guard cases:\n" + "\n".join(lines))


@bot.hybrid_command(name="case")
@commands.guild_only()
async def case_command(ctx: commands.Context, case_id: str) -> None:
    row = _ai_mod_case(case_id)
    if row is None or int(row.get("guild_id", 0) or 0) != ctx.guild.id:
        await ctx.send("Case not found in this guild.")
        return
    is_owner = int(row.get("author_id", 0) or 0) == ctx.author.id
    is_mod = isinstance(ctx.author, discord.Member) and is_moderator(ctx.author)
    if not is_owner and not is_mod:
        await ctx.send("You can only view your own case unless you are a moderator.")
        return
    category = _ai_mod_normalize_category(row.get("category")).replace("_", "/")
    risk = _ai_mod_risk_score(row.get("risk_score"))
    confidence = str(row.get("confidence_band", "low"))
    action = str(row.get("action", "none"))
    applied = "+".join(str(item) for item in row.get("applied_actions", []) if str(item).strip()) or "none"
    excerpt = str(row.get("message_excerpt", "")).strip()[:500] or "(no excerpt)"
    rationale_tags = row.get("rationale_tags", [])
    tag_text = ", ".join(str(tag) for tag in rationale_tags[:8]) if isinstance(rationale_tags, list) else "n/a"
    appeal_ids = row.get("appeal_ids", [])
    appeal_count = len(appeal_ids) if isinstance(appeal_ids, list) else 0
    text = (
        f"Case `{row.get('id', case_id.upper())}`\n"
        f"- User: <@{int(row.get('author_id', 0) or 0)}>\n"
        f"- Category: `{category}`\n"
        f"- Risk: `{risk:.2f}` (`{confidence}`)\n"
        f"- Suggested action: `{action}`\n"
        f"- Applied action: `{applied}`\n"
        f"- Status: `{row.get('status', 'open')}`\n"
        f"- Appeals: `{appeal_count}`\n"
        f"- Rationale: {tag_text}\n"
        f"- Excerpt: {excerpt}\n"
        f"- Jump: {row.get('message_jump_url', 'n/a')}"
    )
    await send_chunked(ctx, text)


@bot.hybrid_command(name="override")
@commands.guild_only()
async def override_command(ctx: commands.Context, case_id: str, action: str) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can override AI Guard cases.")
        return
    normalized_action = (action or "").strip().lower()
    if normalized_action not in {"none", "warn", "timeout", "ban"}:
        await ctx.send(f"Usage: `{PREFIX}override <case_id> <none|warn|timeout|ban>`")
        return
    row = _ai_mod_case(case_id)
    if row is None or int(row.get("guild_id", 0) or 0) != ctx.guild.id:
        await ctx.send("Case not found in this guild.")
        return
    ok, detail = await _ai_mod_apply_override_action(ctx, row, normalized_action)
    if not ok:
        await ctx.send(f"Override failed: {detail}")
        return
    review = row.setdefault("review", {})
    if not isinstance(review, dict):
        review = {}
        row["review"] = review
    review["override_action"] = normalized_action
    review["reviewer_id"] = int(ctx.author.id)
    review["review_note"] = detail[:220]
    review["updated_ts"] = time.time()
    row["status"] = "overridden"
    row["updated_ts"] = time.time()
    _ai_mod_append_review_action(
        guild_id=ctx.guild.id,
        case_id=str(row.get("id", case_id.upper())),
        reviewer_id=ctx.author.id,
        action=normalized_action,
        note=detail,
    )
    await send_mod_log(
        ctx.guild,
        "AI Guard Override",
        moderator=ctx.author,
        target=ctx.guild.get_member(int(row.get("author_id", 0) or 0)),
        channel=ctx.channel,
        reason=f"Case `{row.get('id')}` override `{normalized_action}`",
        details=detail,
    )
    await ctx.send(f"Case `{row.get('id')}` override applied: `{normalized_action}`. {detail}")


@bot.hybrid_command(name="appeal")
@commands.guild_only()
async def appeal_command(ctx: commands.Context, case_id: str, *, reason: str) -> None:
    row = _ai_mod_case(case_id)
    if row is None or int(row.get("guild_id", 0) or 0) != ctx.guild.id:
        await ctx.send("Case not found in this guild.")
        return
    if not get_guild_ai_guard_appeals_enabled(ctx.guild.id):
        await ctx.send("Appeals are disabled in this server.")
        return
    is_owner = int(row.get("author_id", 0) or 0) == ctx.author.id
    is_mod = isinstance(ctx.author, discord.Member) and is_moderator(ctx.author)
    if not is_owner and not is_mod:
        await ctx.send("You can only appeal your own case.")
        return
    clean_reason = " ".join(reason.split()).strip()
    if len(clean_reason) < 8:
        await ctx.send("Appeal reason is too short. Add a little more context.")
        return
    appeal_id = _ai_mod_next_appeal_id()
    state = get_ai_mod_state()
    appeals = state.setdefault("appeals", {})
    if not isinstance(appeals, dict):
        appeals = {}
        state["appeals"] = appeals
    appeals[appeal_id] = {
        "id": appeal_id,
        "case_id": str(row.get("id", case_id.upper())),
        "guild_id": int(ctx.guild.id),
        "user_id": int(ctx.author.id),
        "reason": clean_reason[:1200],
        "created_ts": time.time(),
        "status": "open",
        "reviewer_id": None,
        "decision_note": "",
    }
    appeal_ids = row.get("appeal_ids")
    if not isinstance(appeal_ids, list):
        appeal_ids = []
        row["appeal_ids"] = appeal_ids
    appeal_ids.append(appeal_id)
    row["status"] = "appealed"
    row["updated_ts"] = time.time()
    _ai_mod_increment_metric("appeals")
    _mark_ai_mod_dirty()
    await send_mod_log(
        ctx.guild,
        "AI Guard Appeal Submitted",
        moderator=ctx.author,
        target=ctx.guild.get_member(int(row.get("author_id", 0) or 0)),
        channel=ctx.channel,
        reason=f"Case `{row.get('id')}`",
        details=f"Appeal `{appeal_id}`: {clean_reason[:180]}",
    )
    await ctx.send(
        f"Appeal submitted: `{appeal_id}` for case `{row.get('id')}`. "
        "A moderator will review and decide."
    )


@bot.command(name="funmode")
@commands.guild_only()
async def funmode_command(ctx: commands.Context, mode: str | None = None) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can change fun mode.")
        return
    normalized = (mode or "").strip().lower()
    if normalized in {"", "status", "state"}:
        await ctx.send(f"Current fun mode: `{get_guild_fun_mode(ctx.guild.id)}`.")
        return
    if normalized not in {"spicy", "balanced", "wholesome"}:
        await ctx.send(f"Usage: `{PREFIX}funmode <spicy|balanced|wholesome|status>`")
        return
    set_guild_fun_mode(ctx.guild.id, normalized)
    await ctx.send(f"Fun mode set to `{normalized}`.")


@bot.command(name="engagementlimits")
@commands.guild_only()
async def engagement_limits_command(ctx: commands.Context, mode: str | None = None) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can change engagement limits.")
        return
    normalized = (mode or "").strip().lower()
    current = get_guild_engagement_limits_enabled(ctx.guild.id)
    if normalized in {"", "status", "state"}:
        await ctx.send(
            f"Engagement limits are currently **{'enabled' if current else 'disabled'}**."
        )
        return
    if normalized in {"on", "enable", "enabled", "true", "1"}:
        new_state = True
    elif normalized in {"off", "disable", "disabled", "false", "0"}:
        new_state = False
    else:
        await ctx.send(f"Usage: `{PREFIX}engagementlimits <on|off|status>`")
        return
    set_guild_engagement_limits_enabled(ctx.guild.id, new_state)
    await ctx.send(f"Engagement limits are now **{'enabled' if new_state else 'disabled'}**.")


@bot.command(name="escalation")
@commands.guild_only()
async def moderation_escalation_command(ctx: commands.Context, mode: str | None = None) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can change moderation escalation.")
        return
    normalized = (mode or "").strip().lower()
    current = get_guild_moderation_escalation_enabled(ctx.guild.id)
    if normalized in {"", "status", "state"}:
        await ctx.send(
            f"Moderation escalation is currently **{'enabled' if current else 'disabled'}**."
        )
        return
    if normalized in {"on", "enable", "enabled", "true", "1"}:
        new_state = True
    elif normalized in {"off", "disable", "disabled", "false", "0"}:
        new_state = False
    else:
        await ctx.send(f"Usage: `{PREFIX}escalation <on|off|status>`")
        return
    set_guild_moderation_escalation_enabled(ctx.guild.id, new_state)
    await ctx.send(f"Moderation escalation is now **{'enabled' if new_state else 'disabled'}**.")


@bot.command(name="modguard")
@commands.guild_only()
async def modguard_command(ctx: commands.Context, mode: str | None = None) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can change ModGuard settings.")
        return
    normalized = (mode or "").strip().lower()
    current = get_guild_modguard_enabled(ctx.guild.id)
    if normalized in {"", "status", "state"}:
        await ctx.send(f"ModGuard is currently **{'enabled' if current else 'disabled'}**.")
        return
    if normalized in {"on", "enable", "enabled", "true", "1"}:
        new_state = True
    elif normalized in {"off", "disable", "disabled", "false", "0"}:
        new_state = False
    else:
        await ctx.send(f"Usage: `{PREFIX}modguard <on|off|status>`")
        return
    set_guild_modguard_enabled(ctx.guild.id, new_state)
    await ctx.send(f"ModGuard is now **{'enabled' if new_state else 'disabled'}**.")


@bot.command(name="engagementhub")
@commands.guild_only()
async def engagementhub_command(
    ctx: commands.Context, *, target: str | None = None
) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can set engagement hub channel.")
        return

    raw = (target or "").strip().lower()
    if raw in {"", "status", "state"}:
        configured_id = get_guild_engagement_hub_channel_id(ctx.guild.id)
        configured = ctx.guild.get_channel(configured_id) if configured_id else None
        if isinstance(configured, discord.TextChannel):
            await ctx.send(f"Engagement hub: {configured.mention}")
        else:
            await ctx.send("Engagement hub is not set. Bell will fallback to first writable channel.")
        return
    if raw in {"clear", "none", "off"}:
        set_guild_engagement_hub_channel_id(ctx.guild.id, None)
        await ctx.send("Cleared engagement hub channel.")
        return

    candidate: discord.TextChannel | None = None
    if ctx.message.channel_mentions:
        mention = ctx.message.channel_mentions[0]
        if isinstance(mention, discord.TextChannel):
            candidate = mention
    else:
        cleaned = raw.replace("#", "").strip()
        candidate = discord.utils.find(lambda c: c.name.lower() == cleaned, ctx.guild.text_channels)

    if candidate is None:
        await ctx.send(f"Usage: `{PREFIX}engagementhub <#channel|status|clear>`")
        return
    set_guild_engagement_hub_channel_id(ctx.guild.id, candidate.id)
    await ctx.send(f"Engagement hub set to {candidate.mention}.")


@bot.command(name="autoloops")
@commands.guild_only()
async def autoloops_command(ctx: commands.Context, mode: str | None = None) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can change automation loops.")
        return
    normalized = (mode or "").strip().lower()
    current = get_guild_auto_loops_enabled(ctx.guild.id)
    if normalized in {"", "status", "state"}:
        await ctx.send(f"Automation loops are currently **{'enabled' if current else 'disabled'}**.")
        return
    if normalized in {"on", "enable", "enabled", "true", "1"}:
        new_state = True
    elif normalized in {"off", "disable", "disabled", "false", "0"}:
        new_state = False
    else:
        await ctx.send(f"Usage: `{PREFIX}autoloops <on|off|status>`")
        return
    set_guild_auto_loops_enabled(ctx.guild.id, new_state)
    await ctx.send(f"Automation loops are now **{'enabled' if new_state else 'disabled'}**.")


@bot.command(name="questmode")
@commands.guild_only()
async def questmode_command(ctx: commands.Context, mode: str | None = None) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can change quest mode.")
        return
    normalized = (mode or "").strip().lower()
    current = get_guild_quest_mode_enabled(ctx.guild.id)
    if normalized in {"", "status", "state"}:
        await ctx.send(f"Quest mode is currently **{'enabled' if current else 'disabled'}**.")
        return
    if normalized in {"on", "enable", "enabled", "true", "1"}:
        new_state = True
    elif normalized in {"off", "disable", "disabled", "false", "0"}:
        new_state = False
    else:
        await ctx.send(f"Usage: `{PREFIX}questmode <on|off|status>`")
        return
    set_guild_quest_mode_enabled(ctx.guild.id, new_state)
    await ctx.send(f"Quest mode is now **{'enabled' if new_state else 'disabled'}**.")


@bot.command(name="engagementtz")
@commands.guild_only()
async def engagementtz_command(ctx: commands.Context, *, tz_name: str | None = None) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can change engagement timezone.")
        return
    value = (tz_name or "").strip()
    if not value:
        await ctx.send(f"Current engagement timezone: `{get_guild_engagement_timezone(ctx.guild.id)}`")
        return
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError:
        await ctx.send("Invalid timezone. Use IANA format, e.g. `Asia/Kolkata` or `UTC`.")
        return
    set_guild_engagement_timezone(ctx.guild.id, value)
    await ctx.send(f"Engagement timezone set to `{value}`.")


@bot.command(name="say")
@commands.guild_only()
async def say_command(ctx: commands.Context, *, text: str | None = None) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can use this command.")
        return

    message_text = (text or "").strip()
    if not message_text:
        await ctx.send(f"Usage: `{PREFIX}say <message>`")
        return

    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass

    await ctx.send(message_text)


@bot.command(name="cat", aliases=["cats"])
async def cat_command(ctx: commands.Context) -> None:
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    await send_random_cat_image(ctx.channel)


@bot.command(name="food")
async def food_command(ctx: commands.Context) -> None:
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    await send_random_indian_veg_food(ctx.channel)


@bot.command(name="ping")
async def ping_command(ctx: commands.Context) -> None:
    latency_ms = round(bot.latency * 1000)
    await ctx.send(f"Pong! `{latency_ms}ms`")


@bot.command(name="avatar")
async def avatar_command(
    ctx: commands.Context, member: discord.Member | None = None
) -> None:
    target = member or ctx.author
    embed = discord.Embed(
        title=f"{target.display_name}'s Avatar",
        color=discord.Color.blurple(),
    )
    embed.set_image(url=target.display_avatar.url)
    await ctx.send(embed=embed)


@bot.command(name="userinfo")
async def userinfo_command(
    ctx: commands.Context, member: discord.Member | None = None
) -> None:
    target = member or ctx.author
    embed = discord.Embed(
        title="User Info",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="User", value=f"{target} (`{target.id}`)", inline=False)
    embed.add_field(
        name="Created",
        value=discord.utils.format_dt(target.created_at, style="F"),
        inline=False,
    )
    if target.joined_at:
        embed.add_field(
            name="Joined Server",
            value=discord.utils.format_dt(target.joined_at, style="F"),
            inline=False,
        )
    roles = [role.mention for role in target.roles[1:][-8:]]
    embed.add_field(name="Top Role", value=target.top_role.mention, inline=True)
    embed.add_field(name="Roles (max 8)", value=", ".join(roles) if roles else "None", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="serverinfo")
async def serverinfo_command(ctx: commands.Context) -> None:
    guild = ctx.guild
    embed = discord.Embed(
        title="Server Info",
        color=discord.Color.teal(),
        timestamp=discord.utils.utcnow(),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Server", value=f"{guild.name} (`{guild.id}`)", inline=False)
    embed.add_field(name="Owner", value=str(guild.owner), inline=True)
    embed.add_field(name="Members", value=str(guild.member_count), inline=True)
    embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
    embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, style="F"), inline=False)
    await ctx.send(embed=embed)


@bot.command(name="poll")
async def poll_command(ctx: commands.Context, *, text: str) -> None:
    parts = [part.strip() for part in text.split("|") if part.strip()]
    if len(parts) < 3:
        await ctx.send(
            f"Usage: `{PREFIX}poll Question | Option 1 | Option 2` (2-10 options)."
        )
        return

    question = parts[0]
    options = parts[1:]
    if len(options) > 10:
        await ctx.send("You can add a maximum of `10` options.")
        return

    lines = [f"{POLL_EMOJIS[i]} {opt}" for i, opt in enumerate(options)]
    embed = discord.Embed(
        title="Poll",
        description=f"**{question}**\n\n" + "\n".join(lines),
        color=discord.Color.gold(),
    )
    embed.set_footer(text=f"Poll by {ctx.author}")

    poll_message = await ctx.send(embed=embed)
    for i in range(len(options)):
        await poll_message.add_reaction(POLL_EMOJIS[i])


@bot.command(name="snipe")
async def snipe_command(ctx: commands.Context) -> None:
    payload = SNIPE_CACHE.get(ctx.channel.id)
    if not payload:
        await ctx.send("Nothing to snipe in this channel.")
        return

    embed = discord.Embed(
        title="Sniped Message",
        description=payload["content"],
        color=discord.Color.dark_teal(),
    )
    embed.set_author(name=f"{payload['author']} ({payload['author_id']})")
    await ctx.send(embed=embed)


@bot.command(name="remind")
async def remind_command(ctx: commands.Context, minutes: int, *, reminder_text: str) -> None:
    if minutes < 1 or minutes > 10080:
        await ctx.send("Minutes must be between `1` and `10080`.")
        return

    await ctx.send(f"Reminder set. I will DM you in `{minutes}` minute(s).")

    async def fire_reminder() -> None:
        await asyncio.sleep(minutes * 60)
        try:
            await ctx.author.send(f"Reminder from **{ctx.guild.name}**: {reminder_text}")
        except discord.HTTPException:
            try:
                await ctx.send(
                    f"{ctx.author.mention} reminder: {reminder_text}",
                    delete_after=20,
                )
            except discord.HTTPException:
                pass

    asyncio.create_task(fire_reminder())


@bot.hybrid_command(name="rank")
@commands.cooldown(3, 25, commands.BucketType.user)
@commands.guild_only()
async def rank_command(ctx: commands.Context, member: discord.Member | None = None) -> None:
    target = member or ctx.author
    snapshot = get_rank_snapshot(ctx.guild.id, target.id)
    all_pos, all_total = get_user_rank_position(ctx.guild, target.id, "alltime")
    day_pos, day_total = get_user_rank_position(ctx.guild, target.id, "daily")
    week_pos, week_total = get_user_rank_position(ctx.guild, target.id, "weekly")

    await ctx.send(
        f"ðŸ… **Rank for {target.display_name}**\n"
        f"XP: `{snapshot['xp']}` (Rank: `{all_pos or '-'} / {all_total or '-'}`)\n"
        f"Daily XP: `{snapshot['daily_xp']}` (Rank: `{day_pos or '-'} / {day_total or '-'}`)\n"
        f"Weekly points: `{snapshot['weekly_points']}` (Rank: `{week_pos or '-'} / {week_total or '-'}`)\n"
        f"Streak: `{snapshot['streak']}` days (Best: `{snapshot['best_streak']}`)\n"
        f"Event points: `{snapshot['event_points']}`"
    )


@bot.hybrid_command(name="leaderboard")
@commands.cooldown(2, 30, commands.BucketType.user)
@commands.guild_only()
async def leaderboard_command(ctx: commands.Context, mode: str = "alltime") -> None:
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    normalized = normalize_leaderboard_mode(mode)
    rows = build_leaderboard_rows(ctx.guild, normalized, limit=10)
    if not rows:
        await ctx.send("Leaderboard is empty for now. Start chatting to earn XP.")
        return

    title = {"daily": "Daily", "weekly": "Weekly", "alltime": "All-time"}[normalized]
    lines = [
        f"{idx}. **{name}** - `{score}`"
        for idx, (_, name, score) in enumerate(rows, start=1)
    ]
    await ctx.send(
        f"ðŸ“Š **{title} Leaderboard**\n" + "\n".join(lines)
    )


@bot.hybrid_command(name="streak")
@commands.cooldown(3, 20, commands.BucketType.user)
@commands.guild_only()
async def streak_command(ctx: commands.Context, member: discord.Member | None = None) -> None:
    target = member or ctx.author
    snapshot = get_rank_snapshot(ctx.guild.id, target.id)
    await ctx.send(
        f"ðŸ”¥ **Streak for {target.display_name}**\n"
        f"Current streak: `{snapshot['streak']}` day(s)\n"
        f"Best streak: `{snapshot['best_streak']}` day(s)"
    )


@bot.hybrid_command(name="daily")
@commands.cooldown(2, 20, commands.BucketType.user)
@commands.guild_only()
async def daily_command(ctx: commands.Context) -> None:
    if not ENGAGEMENT_ENABLED:
        await ctx.send("Engagement mode is currently disabled.")
        return
    if not get_guild_quest_mode_enabled(ctx.guild.id):
        await ctx.send("Quest mode is disabled in this server.")
        return
    day_key, lines, completed_count, total_reward = get_user_quest_view(ctx.guild.id, ctx.author.id)
    if not lines:
        await ctx.send("No quests configured right now.")
        return
    await ctx.send(
        f"ðŸ—“ï¸ **Daily Quests ({day_key})**\n"
        + "\n".join(lines)
        + f"\n\nCompleted: `{completed_count}/{len(lines)}` | Potential reward: `{total_reward}` XP"
    )


@bot.hybrid_command(name="quests")
@commands.cooldown(2, 20, commands.BucketType.user)
@commands.guild_only()
async def quests_command(ctx: commands.Context) -> None:
    if not ENGAGEMENT_ENABLED:
        await ctx.send("Engagement mode is currently disabled.")
        return
    if not get_guild_quest_mode_enabled(ctx.guild.id):
        await ctx.send("Quest mode is disabled in this server.")
        return
    day_key, lines, completed_count, total_reward = get_user_quest_view(ctx.guild.id, ctx.author.id)
    if not lines:
        await ctx.send("No quests configured right now.")
        return
    await ctx.send(
        f"ðŸ—“ï¸ **Daily Quests ({day_key})**\n"
        + "\n".join(lines)
        + f"\n\nCompleted: `{completed_count}/{len(lines)}` | Potential reward: `{total_reward}` XP"
    )


@bot.hybrid_command(name="event")
@commands.cooldown(2, 15, commands.BucketType.user)
@commands.guild_only()
async def event_command(
    ctx: commands.Context,
    action: str = "status",
    event_type: str | None = None,
) -> None:
    normalized = action.strip().lower()
    session = EVENT_SESSIONS.get(ctx.guild.id)

    if normalized in {"status", "state"}:
        if not session:
            await ctx.send("No active event in this server.")
            return
        channel = ctx.guild.get_channel(int(session.get("channel_id", 0)))
        ends_at = float(session.get("ends_at", 0.0))
        remaining = max(0, int(ends_at - time.monotonic()))
        await ctx.send(
            f"Active event: `{session.get('type', 'unknown')}` in "
            f"{channel.mention if isinstance(channel, discord.TextChannel) else 'unknown channel'}.\n"
            f"Time remaining: `{remaining}s` | Participants: `{len(session.get('scores', {}))}`"
        )
        return

    if normalized == "stop":
        if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
            await ctx.send("Only moderators can stop events.")
            return
        if not session:
            await ctx.send("No active event to stop.")
            return
        await finalize_event_session(ctx.guild, reason="manual stop")
        return

    if normalized != "start":
        await ctx.send(f"Usage: `{PREFIX}event <start|stop|status> [trivia|hottake|caption]`")
        return

    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can start events.")
        return
    if session:
        await ctx.send("An event is already running. Use `&event stop` first.")
        return

    chosen_type = (event_type or "trivia").strip().lower()
    if chosen_type not in {"trivia", "hottake", "caption"}:
        await ctx.send("Event type must be one of: `trivia`, `hottake`, `caption`.")
        return

    prompt, answers = _event_type_prompt(chosen_type)
    if is_ai_configured():
        try:
            prompt = await request_fun_ai(
                (
                    "Rewrite this Discord event prompt to be more engaging but still concise.\n"
                    "Keep meaning same, <= 2 lines.\n"
                    f"Event type: {chosen_type}\n"
                    f"Prompt: {prompt}"
                ),
                max_tokens=80,
                temperature=0.8,
                policy_key="eventhost",
                fun_mode=get_guild_fun_mode(ctx.guild.id),
            )
        except Exception as error:
            print(f"[EVENT HOST AI ERROR] {error}")
    EVENT_SESSIONS[ctx.guild.id] = {
        "type": chosen_type,
        "channel_id": ctx.channel.id,
        "started_at": time.monotonic(),
        "ends_at": time.monotonic() + (EVENT_DEFAULT_DURATION_MINUTES * 60),
        "host_id": ctx.author.id,
        "scores": {},
        "answers": answers,
    }
    await ctx.send(
        f"ðŸŽ® **Event started:** `{chosen_type}` (duration: `{EVENT_DEFAULT_DURATION_MINUTES}` min)\n"
        f"{prompt}\n\n"
        "Drop your replies in this channel to earn points."
    )


def _business_active_loans(user: dict[str, Any]) -> list[dict[str, Any]]:
    loans = user.get("loans", [])
    if not isinstance(loans, list):
        return []
    return [
        loan
        for loan in loans
        if isinstance(loan, dict) and str(loan.get("status", "active")) not in {"paid", "closed"}
    ]


def _business_portfolio_lines(user: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    ranked: list[tuple[str, str, int, float, float]] = []
    for asset_type, label in (("stock", "STK"), ("commodity", "CMD"), ("crypto", "CRY")):
        field = _business_holding_field(asset_type)
        if field is None:
            continue
        portfolio = user.get(field, {})
        if not isinstance(portfolio, dict):
            continue
        for symbol, holding in portfolio.items():
            if not isinstance(holding, dict):
                continue
            qty = int(holding.get("qty", 0))
            avg = float(holding.get("avg_cost", 0.0))
            if qty <= 0:
                continue
            asset = _business_get_asset(asset_type, str(symbol))
            if asset is None:
                continue
            price = float(asset.get("price", 0.0))
            value = qty * price
            pnl = (price - avg) * qty
            ranked.append((label, str(symbol), qty, value, pnl))
    ranked.sort(key=lambda row: row[3], reverse=True)
    for label, symbol, qty, value, pnl in ranked[:16]:
        lines.append(
            f"`{label}` `{symbol}` x `{qty}` | Value: `{_business_money(value)}` | P/L: `{pnl:+,.0f}`"
        )
    return lines


@bot.hybrid_command(name="balance")
@commands.cooldown(3, 12, commands.BucketType.user)
@commands.guild_only()
async def business_balance_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    async with BUSINESS_STATE_LOCK:
        user = _business_get_user(ctx.author.id)
        cash = float(user.get("cash", 0.0))
        debt = _business_debt_total(user)
        net = _business_networth(ctx.author.id)
        tax_liability = float(user.get("tax_liability", 0.0) or 0.0)
        credit_score = int(user.get("credit_score", 650) or 650)
        frozen = _business_is_user_frozen(ctx.author.id)
    tip = await _business_get_personalized_tip(
        ctx.guild.id,
        ctx.author.id,
        context="balance_overview",
    )
    await ctx.send(
        f"ðŸ’¼ **Business Balance - {ctx.author.display_name}**\n"
        f"Cash: `{_business_money(cash)}`\n"
        f"Debt: `{_business_money(debt)}`\n"
        f"Net worth: `{_business_money(net)}`\n"
        f"Tax liability: `{_business_money(tax_liability)}` | Credit: `{credit_score}`\n"
        f"Status: `{'frozen' if frozen else 'active'}`\n"
        f"{tip}"
    )


@bot.hybrid_command(name="dailyclaim")
@commands.cooldown(2, 8, commands.BucketType.user)
@commands.guild_only()
async def business_dailyclaim_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    async with BUSINESS_STATE_LOCK:
        success, amount, streak = _business_take_daily_claim(ctx.author.id, ctx.guild.id)
    if not success:
        await ctx.send("You already claimed today. Come back after UTC reset.")
        return
    tip = await _business_get_personalized_tip(
        ctx.guild.id,
        ctx.author.id,
        context="daily_claim",
    )
    await ctx.send(
        f"âœ… Daily claim received: `{_business_money(amount)}` cash.\n"
        f"Current claim streak: `{streak}` day(s).\n"
        f"{tip}"
    )


@bot.hybrid_command(name="portfolio")
@commands.cooldown(3, 12, commands.BucketType.user)
@commands.guild_only()
async def business_portfolio_command(
    ctx: commands.Context, member: discord.Member | None = None
) -> None:
    if not await _business_require_access(ctx, check_cooldown=True):
        return
    target = member or ctx.author
    async with BUSINESS_STATE_LOCK:
        user = _business_get_user(target.id)
        cash = float(user.get("cash", 0.0))
        lines = _business_portfolio_lines(user)
        stock_value = _business_portfolio_value(user)
        commodity_value = _business_asset_portfolio_value(user, "commodity")
        crypto_value = _business_asset_portfolio_value(user, "crypto")
        total_assets = stock_value + commodity_value + crypto_value
    owner_label = f"{target.mention} ({target.display_name})"
    if not lines:
        await ctx.send(
            f"**Portfolio - {owner_label}**\n"
            f"Cash: `{_business_money(cash)}`\n"
            "No stock holdings yet."
        )
        return
    await ctx.send(
        f"**Portfolio - {owner_label}**\n"
        f"Cash: `{_business_money(cash)}` | Asset value: `{_business_money(total_assets)}`\n"
        + "\n".join(lines)
    )


@bot.hybrid_command(name="networth")
@commands.cooldown(3, 12, commands.BucketType.user)
@commands.guild_only()
async def business_networth_command(
    ctx: commands.Context, member: discord.Member | None = None
) -> None:
    if not await _business_require_access(ctx):
        return
    target = member or ctx.author
    async with BUSINESS_STATE_LOCK:
        user = _business_get_user(target.id)
        cash = float(user.get("cash", 0.0))
        stocks = _business_portfolio_value(user)
        commodities = _business_asset_portfolio_value(user, "commodity")
        crypto = _business_asset_portfolio_value(user, "crypto")
        props = _business_property_value(user)
        biz_value = _business_business_equity_value(user)
        debt = _business_debt_total(user)
        net = _business_networth(target.id)
    await ctx.send(
        f"🏦 **Net Worth - {target.display_name}**\n"
        f"Cash: `{_business_money(cash)}`\n"
        f"Stocks: `{_business_money(stocks)}`\n"
        f"Commodities: `{_business_money(commodities)}`\n"
        f"Crypto: `{_business_money(crypto)}`\n"
        f"Properties: `{_business_money(props)}`\n"
        f"Businesses: `{_business_money(biz_value)}`\n"
        f"Debt: `-{_business_money(debt)}`\n"
        f"**Total Net Worth:** `{_business_money(net)}`"
    )


@bot.hybrid_command(name="stocks")
@commands.cooldown(3, 10, commands.BucketType.user)
@commands.guild_only()
async def business_stocks_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        stocks = list(state["market"]["stocks"].values())
    stocks = [s for s in stocks if isinstance(s, dict)]
    stocks.sort(key=lambda item: float(item.get("price", 0.0)), reverse=True)
    lines = [
        f"`{stock.get('symbol')}` - {stock.get('name')} | `{_business_money(float(stock.get('price', 0.0)))}`"
        for stock in stocks[: min(20, len(stocks))]
    ]
    await ctx.send("ðŸ“ˆ **Market Symbols**\n" + "\n".join(lines))


@bot.hybrid_command(name="market")
@commands.cooldown(3, 8, commands.BucketType.user)
@commands.guild_only()
async def business_market_command(ctx: commands.Context, stock: str | None = None) -> None:
    if not await _business_require_access(ctx):
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        if stock:
            symbol = stock.strip().upper()
            row = state["market"]["stocks"].get(symbol)
            if not isinstance(row, dict):
                await ctx.send(f"Unknown stock symbol `{symbol}`.")
                return
            history = row.get("history", [])
            day_change = 0.0
            if isinstance(history, list) and len(history) >= 2 and float(history[-2]) > 0:
                day_change = ((float(history[-1]) - float(history[-2])) / float(history[-2])) * 100.0
            await ctx.send(
                f"ðŸ“Š **{row.get('name')} ({symbol})**\n"
                f"Price: `{_business_money(float(row.get('price', 0.0)))}`\n"
                f"Sector: `{row.get('sector', 'n/a')}`\n"
                f"Volatility: `{float(row.get('volatility', 0.0)):.3f}`\n"
                f"Trend: `{float(row.get('trend', 0.0)):+.3f}`\n"
                f"1-tick change: `{day_change:+.2f}%`"
            )
            return
        market_note = str(state["market"].get("last_news", "No market news yet."))
    await ctx.send(f"ðŸ“° **Market Summary**\n{market_note}")


@bot.hybrid_command(name="commodities")
@commands.cooldown(3, 10, commands.BucketType.user)
@commands.guild_only()
async def business_commodities_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    if not BUSINESS_ENABLE_COMMODITIES:
        await ctx.send("Commodities market is disabled.")
        return
    async with BUSINESS_STATE_LOCK:
        assets = list(get_business_state().get("commodities", {}).get("assets", {}).values())
    assets = [row for row in assets if isinstance(row, dict)]
    assets.sort(key=lambda row: float(row.get("price", 0.0)), reverse=True)
    if not assets:
        await ctx.send("No commodity symbols configured.")
        return
    lines: list[str] = []
    for row in assets[:20]:
        history = row.get("history", [])
        change = 0.0
        if isinstance(history, list) and len(history) >= 2 and float(history[-2] or 0.0) > 0:
            change = ((float(history[-1]) - float(history[-2])) / float(history[-2])) * 100.0
        lines.append(
            f"`{row.get('symbol')}` {row.get('name')} | `{_business_money(float(row.get('price', 0.0)))}` ({change:+.2f}%)"
        )
    await ctx.send("🛢️ **Commodities Desk**\n" + "\n".join(lines))


@bot.hybrid_command(name="crypto")
@commands.cooldown(3, 10, commands.BucketType.user)
@commands.guild_only()
async def business_crypto_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    if not BUSINESS_ENABLE_CRYPTO:
        await ctx.send("Crypto market is disabled.")
        return
    async with BUSINESS_STATE_LOCK:
        assets = list(get_business_state().get("crypto", {}).get("assets", {}).values())
    assets = [row for row in assets if isinstance(row, dict)]
    assets.sort(key=lambda row: float(row.get("price", 0.0)), reverse=True)
    if not assets:
        await ctx.send("No crypto symbols configured.")
        return
    lines: list[str] = []
    for row in assets[:20]:
        history = row.get("history", [])
        change = 0.0
        if isinstance(history, list) and len(history) >= 2 and float(history[-2] or 0.0) > 0:
            change = ((float(history[-1]) - float(history[-2])) / float(history[-2])) * 100.0
        lines.append(
            f"`{row.get('symbol')}` {row.get('name')} | `{_business_money(float(row.get('price', 0.0)))}` ({change:+.2f}%)"
        )
    await ctx.send("🪙 **Crypto Desk**\n" + "\n".join(lines))


@bot.hybrid_command(name="buycommodity")
@commands.cooldown(2, 4, commands.BucketType.user)
@commands.guild_only()
async def business_buy_commodity_command(ctx: commands.Context, name: str, qty: int) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    if not BUSINESS_ENABLE_COMMODITIES:
        await ctx.send("Commodities market is disabled.")
        return
    symbol = name.strip().upper()
    if qty < 1 or qty > 50000:
        await ctx.send("Quantity must be between `1` and `50000`.")
        return
    async with BUSINESS_STATE_LOCK:
        ok, text, total = _business_execute_asset_buy(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            asset_type="commodity",
            symbol=symbol,
            qty=qty,
            source="command",
        )
    if not ok:
        await ctx.send(text)
        return
    await ctx.send(f"✅ {text}\nTotal cost: `{_business_money(total)}`")


@bot.hybrid_command(name="sellcommodity")
@commands.cooldown(2, 4, commands.BucketType.user)
@commands.guild_only()
async def business_sell_commodity_command(ctx: commands.Context, name: str, qty: int) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    if not BUSINESS_ENABLE_COMMODITIES:
        await ctx.send("Commodities market is disabled.")
        return
    symbol = name.strip().upper()
    if qty < 1 or qty > 50000:
        await ctx.send("Quantity must be between `1` and `50000`.")
        return
    async with BUSINESS_STATE_LOCK:
        ok, text, net = _business_execute_asset_sell(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            asset_type="commodity",
            symbol=symbol,
            qty=qty,
            source="command",
        )
    if not ok:
        await ctx.send(text)
        return
    await ctx.send(f"✅ {text}\nNet after fees/penalties: `{_business_money(net)}`")


@bot.hybrid_command(name="buycrypto")
@commands.cooldown(2, 4, commands.BucketType.user)
@commands.guild_only()
async def business_buy_crypto_command(ctx: commands.Context, symbol: str, qty: int) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    if not BUSINESS_ENABLE_CRYPTO:
        await ctx.send("Crypto market is disabled.")
        return
    code = symbol.strip().upper()
    if qty < 1 or qty > 200000:
        await ctx.send("Quantity must be between `1` and `200000`.")
        return
    async with BUSINESS_STATE_LOCK:
        ok, text, total = _business_execute_asset_buy(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            asset_type="crypto",
            symbol=code,
            qty=qty,
            source="command",
        )
    if not ok:
        await ctx.send(text)
        return
    await ctx.send(f"✅ {text}\nTotal cost: `{_business_money(total)}`")


@bot.hybrid_command(name="sellcrypto")
@commands.cooldown(2, 4, commands.BucketType.user)
@commands.guild_only()
async def business_sell_crypto_command(ctx: commands.Context, symbol: str, qty: int) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    if not BUSINESS_ENABLE_CRYPTO:
        await ctx.send("Crypto market is disabled.")
        return
    code = symbol.strip().upper()
    if qty < 1 or qty > 200000:
        await ctx.send("Quantity must be between `1` and `200000`.")
        return
    async with BUSINESS_STATE_LOCK:
        ok, text, net = _business_execute_asset_sell(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            asset_type="crypto",
            symbol=code,
            qty=qty,
            source="command",
        )
    if not ok:
        await ctx.send(text)
        return
    await ctx.send(f"✅ {text}\nNet after fees/penalties: `{_business_money(net)}`")


@bot.hybrid_command(name="startbiz")
@commands.cooldown(2, 6, commands.BucketType.user)
@commands.guild_only()
async def business_start_biz_command(ctx: commands.Context, biz_type: str, *, name: str) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    if not BUSINESS_ENABLE_PRIVATE_BUSINESSES:
        await ctx.send("Private businesses are disabled.")
        return
    normalized = biz_type.strip().lower()
    clean_name = " ".join(name.split()).strip()[:60]
    if not clean_name:
        await ctx.send("Business name cannot be empty.")
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        profiles = state.get("businesses", {}).get("profiles", {})
        profile = profiles.get(normalized) if isinstance(profiles, dict) else None
        if not isinstance(profile, dict):
            available = ", ".join(sorted(profiles.keys())[:8]) if isinstance(profiles, dict) else "restaurant, tech, retail"
            await ctx.send(f"Unknown business type. Available: `{available}`")
            return
        user = _business_get_user(ctx.author.id)
        current = [biz_id for biz_id in user.get("business_ids", []) if str(biz_id)]
        if len(current) >= 6:
            await ctx.send("You already run the max number of businesses (`6`).")
            return
        setup_cost = float(profile.get("expand_cost", 7000.0) or 7000.0) * 0.65
        if float(user.get("cash", 0.0)) < setup_cost:
            await ctx.send(f"Insufficient cash. Need `{_business_money(setup_cost)}`.")
            return
        user["cash"] = float(user.get("cash", 0.0)) - setup_cost
        biz_id = _business_next_id("biz")
        entry = {
            "id": biz_id,
            "owner_id": ctx.author.id,
            "name": clean_name,
            "type": normalized,
            "level": 1,
            "employees": 0,
            "status": "active",
            "debt": 0.0,
            "cash_reserve": 0.0,
            "base_value": setup_cost * 1.15,
            "stress_cycles": 0,
            "created_ts": _business_now_ts(),
        }
        state["businesses"]["registry"][biz_id] = entry
        user["business_ids"] = current + [biz_id]
        user["salary_tier"] = max(int(user.get("salary_tier", 1) or 1), 1 + (len(user["business_ids"]) // 2))
        _business_add_ledger_entry(
            action="business_start",
            user_id=ctx.author.id,
            amount=-setup_cost,
            details={"biz_id": biz_id, "type": normalized},
        )
        _mark_business_dirty()
    await ctx.send(
        f"🏢 Business started: **{clean_name}** (`{biz_id}`)\n"
        f"Type: `{normalized}` | Setup cost: `{_business_money(setup_cost)}`"
    )


@bot.hybrid_command(name="mybiz")
@commands.cooldown(3, 8, commands.BucketType.user)
@commands.guild_only()
async def business_mybiz_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        user = _business_get_user(ctx.author.id)
        registry = state.get("businesses", {}).get("registry", {})
        if not isinstance(registry, dict):
            registry = {}
        lines: list[str] = []
        for biz_id in user.get("business_ids", [])[:10]:
            biz = registry.get(str(biz_id))
            if not isinstance(biz, dict):
                continue
            lines.append(
                f"`{biz.get('id')}` **{biz.get('name')}** | `{biz.get('type')}` | "
                f"Lvl `{biz.get('level', 1)}` | Staff `{biz.get('employees', 0)}` | "
                f"Debt `{_business_money(float(biz.get('debt', 0.0) or 0.0))}` | `{biz.get('status', 'active')}`"
            )
    if not lines:
        await ctx.send("You do not own any private businesses yet. Use `&startbiz <type> <name>`.")
        return
    await ctx.send("🏬 **Your Businesses**\n" + "\n".join(lines))


def _business_get_owned_biz_or_error(state: dict[str, Any], user_id: int, biz_id: str) -> tuple[dict[str, Any] | None, str | None]:
    registry = state.get("businesses", {}).get("registry", {})
    if not isinstance(registry, dict):
        return None, "Business registry is unavailable."
    biz = registry.get(biz_id)
    if not isinstance(biz, dict):
        return None, "Business ID not found."
    if int(biz.get("owner_id", 0) or 0) != user_id:
        return None, "You do not own this business."
    if str(biz.get("status", "active")) != "active":
        return None, "This business is not active."
    return biz, None


@bot.hybrid_command(name="bizhire")
@commands.cooldown(2, 5, commands.BucketType.user)
@commands.guild_only()
async def business_bizhire_command(ctx: commands.Context, biz_id: str, count: int) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    if count < 1 or count > 30:
        await ctx.send("Hire count must be between `1` and `30`.")
        return
    target_id = biz_id.strip().upper()
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        biz, error = _business_get_owned_biz_or_error(state, ctx.author.id, target_id)
        if error:
            await ctx.send(error)
            return
        user = _business_get_user(ctx.author.id)
        cost = float(count) * 420.0
        if float(user.get("cash", 0.0)) < cost:
            await ctx.send(f"Insufficient cash. Need `{_business_money(cost)}`.")
            return
        user["cash"] = float(user.get("cash", 0.0)) - cost
        biz["employees"] = max(0, int(biz.get("employees", 0) or 0) + count)
        _business_add_ledger_entry(
            action="business_hire",
            user_id=ctx.author.id,
            amount=-cost,
            details={"biz_id": target_id, "count": count},
        )
        _mark_business_dirty()
    await ctx.send(f"👥 Hired `{count}` staff for `{target_id}`. Cost: `{_business_money(cost)}`.")


@bot.hybrid_command(name="bizfire")
@commands.cooldown(2, 5, commands.BucketType.user)
@commands.guild_only()
async def business_bizfire_command(ctx: commands.Context, biz_id: str, count: int) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    if count < 1 or count > 30:
        await ctx.send("Fire count must be between `1` and `30`.")
        return
    target_id = biz_id.strip().upper()
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        biz, error = _business_get_owned_biz_or_error(state, ctx.author.id, target_id)
        if error:
            await ctx.send(error)
            return
        employees = int(biz.get("employees", 0) or 0)
        if employees < count:
            await ctx.send("You do not have that many employees to fire.")
            return
        biz["employees"] = employees - count
        _business_add_ledger_entry(
            action="business_fire",
            user_id=ctx.author.id,
            amount=0.0,
            details={"biz_id": target_id, "count": count},
        )
        _mark_business_dirty()
    await ctx.send(f"🧹 Fired `{count}` staff from `{target_id}`.")


@bot.hybrid_command(name="bizexpand")
@commands.cooldown(2, 6, commands.BucketType.user)
@commands.guild_only()
async def business_bizexpand_command(ctx: commands.Context, biz_id: str) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    target_id = biz_id.strip().upper()
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        profiles = state.get("businesses", {}).get("profiles", {})
        biz, error = _business_get_owned_biz_or_error(state, ctx.author.id, target_id)
        if error:
            await ctx.send(error)
            return
        level = max(1, int(biz.get("level", 1) or 1))
        if level >= 12:
            await ctx.send("Business is already at max level (`12`).")
            return
        biz_type = str(biz.get("type", "retail"))
        profile = profiles.get(biz_type) if isinstance(profiles, dict) else None
        if not isinstance(profile, dict):
            profile = {"expand_cost": 7000.0}
        cost = float(profile.get("expand_cost", 7000.0) or 7000.0) * (1 + ((level - 1) * 0.62))
        user = _business_get_user(ctx.author.id)
        if float(user.get("cash", 0.0)) < cost:
            await ctx.send(f"Insufficient cash. Need `{_business_money(cost)}`.")
            return
        user["cash"] = float(user.get("cash", 0.0)) - cost
        biz["level"] = level + 1
        biz["base_value"] = float(biz.get("base_value", 0.0) or 0.0) + (cost * 0.75)
        user["salary_tier"] = max(int(user.get("salary_tier", 1) or 1), 1 + ((level + 1) // 3))
        _business_add_ledger_entry(
            action="business_expand",
            user_id=ctx.author.id,
            amount=-cost,
            details={"biz_id": target_id, "new_level": int(biz["level"])},
        )
        _mark_business_dirty()
    await ctx.send(f"📈 Expanded `{target_id}` to level `{level + 1}`. Cost: `{_business_money(cost)}`.")


@bot.hybrid_command(name="salary")
@commands.cooldown(2, 6, commands.BucketType.user)
@commands.guild_only()
async def business_salary_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    async with BUSINESS_STATE_LOCK:
        user = _business_get_user(ctx.author.id)
        cooldowns = user.setdefault("cooldowns", {})
        if not isinstance(cooldowns, dict):
            cooldowns = {}
            user["cooldowns"] = cooldowns
        now_ts = _business_now_ts()
        last_claim = float(cooldowns.get("salary_claim_ts", 0.0) or 0.0)
        wait_seconds = 20 * 3600
        remaining = (last_claim + wait_seconds) - now_ts
        if remaining > 0:
            await ctx.send(f"Salary already claimed. Try again in `{int(remaining // 3600)}h`.")
            return
        tier = max(1, int(user.get("salary_tier", 1) or 1))
        business_count = len(list(user.get("business_ids", [])))
        credit_score = int(user.get("credit_score", 650) or 650)
        base = 700.0 + (tier * 380.0) + (business_count * 180.0) + max(0, credit_score - 600)
        payout = max(400.0, base * random.uniform(0.9, 1.15))
        user["cash"] = float(user.get("cash", 0.0)) + payout
        user["weekly_income"] = float(user.get("weekly_income", 0.0)) + payout
        user["income_total"] = float(user.get("income_total", 0.0)) + payout
        cooldowns["salary_claim_ts"] = now_ts
        _business_add_ledger_entry(
            action="salary_claim",
            user_id=ctx.author.id,
            amount=payout,
            details={"tier": tier, "business_count": business_count},
        )
        _mark_business_dirty()
    await ctx.send(f"💸 Salary credited: `{_business_money(payout)}`.")


@bot.hybrid_command(name="taxes")
@commands.cooldown(2, 8, commands.BucketType.user)
@commands.guild_only()
async def business_taxes_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    async with BUSINESS_STATE_LOCK:
        user = _business_get_user(ctx.author.id)
        tax_state = get_business_state().get("tax", {})
        liability = float(user.get("tax_liability", 0.0) or 0.0)
        paid_total = float(user.get("taxes_paid_total", 0.0) or 0.0)
        weekly_income = float(user.get("weekly_income", 0.0) or 0.0)
        short_gain = float(user.get("weekly_realized_gains_short", 0.0) or 0.0)
        long_gain = float(user.get("weekly_realized_gains_long", 0.0) or 0.0)
        short_rate = float(tax_state.get("capital_gains_short_rate", BUSINESS_CAPITAL_GAINS_SHORT_RATE) or BUSINESS_CAPITAL_GAINS_SHORT_RATE)
        long_rate = float(tax_state.get("capital_gains_long_rate", BUSINESS_CAPITAL_GAINS_LONG_RATE) or BUSINESS_CAPITAL_GAINS_LONG_RATE)
    projected_income_tax = _business_progressive_income_tax(weekly_income)
    projected_gains_tax = max(0.0, short_gain) * short_rate + max(0.0, long_gain) * long_rate
    await ctx.send(
        "🧾 **Tax Desk**\n"
        f"Outstanding liability: `{_business_money(liability)}`\n"
        f"Taxes paid (lifetime): `{_business_money(paid_total)}`\n"
        f"Projected this cycle: income `{_business_money(projected_income_tax)}`, gains `{_business_money(projected_gains_tax)}`"
    )


@bot.hybrid_command(name="filetax")
@commands.cooldown(2, 6, commands.BucketType.user)
@commands.guild_only()
async def business_filetax_command(ctx: commands.Context, amount: float | None = None) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    async with BUSINESS_STATE_LOCK:
        user = _business_get_user(ctx.author.id)
        liability = float(user.get("tax_liability", 0.0) or 0.0)
        if liability <= 0:
            await ctx.send("You have no outstanding tax liability.")
            return
        cash = float(user.get("cash", 0.0) or 0.0)
        target = liability if amount is None else float(amount)
        if target <= 0:
            await ctx.send("Amount must be positive.")
            return
        paid = min(target, liability, cash)
        if paid <= 0:
            await ctx.send("Not enough cash to file taxes.")
            return
        user["cash"] = cash - paid
        user["tax_liability"] = max(0.0, liability - paid)
        user["taxes_paid_total"] = float(user.get("taxes_paid_total", 0.0)) + paid
        if user["tax_liability"] <= 1.0:
            _business_apply_credit_score_delta(user, 3)
        _business_add_ledger_entry(
            action="tax_filing",
            user_id=ctx.author.id,
            amount=-paid,
            details={"remaining_liability": float(user.get("tax_liability", 0.0))},
        )
        _mark_business_dirty()
    await ctx.send(
        f"✅ Tax payment recorded: `{_business_money(paid)}`\n"
        f"Remaining liability: `{_business_money(float(user.get('tax_liability', 0.0)))}`"
    )


@bot.hybrid_command(name="credit")
@commands.cooldown(2, 8, commands.BucketType.user)
@commands.guild_only()
async def business_credit_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    async with BUSINESS_STATE_LOCK:
        user = _business_get_user(ctx.author.id)
        debt = _business_debt_total(user)
        net = _business_networth(ctx.author.id)
        score = int(user.get("credit_score", 650) or 650)
        cap_multiplier = _business_clamp_float(0.60 + ((score - 500) / 500), 0.55, 1.35)
        approx_cap = max(15000.0, net * cap_multiplier)
    await ctx.send(
        "📊 **Credit Report**\n"
        f"Score: `{score}` (range 500-850)\n"
        f"Debt: `{_business_money(debt)}` | Net worth: `{_business_money(net)}`\n"
        f"Approx loan cap: `{_business_money(approx_cap)}`"
    )


@bot.hybrid_command(name="markethalt")
@commands.cooldown(2, 6, commands.BucketType.user)
@commands.guild_only()
async def business_markethalt_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        market_halt = state.get("market_halts", {}).get("market", {})
        assets = state.get("market_halts", {}).get("assets", {})
        remaining = int(market_halt.get("remaining_ticks", 0) or 0) if isinstance(market_halt, dict) else 0
        reason = str(market_halt.get("reason", "n/a")) if isinstance(market_halt, dict) else "n/a"
        halted_assets = []
        if isinstance(assets, dict):
            for key, row in assets.items():
                if not isinstance(row, dict):
                    continue
                ticks = int(row.get("remaining_ticks", 0) or 0)
                if ticks > 0:
                    halted_assets.append(f"`{key}` `{ticks}` tick(s)")
    lines = [
        "⛔ **Market Halt Status**",
        f"Global halt ticks remaining: `{remaining}`",
        f"Reason: `{reason}`",
        "Asset halts: " + (", ".join(halted_assets[:8]) if halted_assets else "`none`"),
    ]
    await ctx.send("\n".join(lines))


@bot.hybrid_command(name="economystatus")
@commands.cooldown(2, 8, commands.BucketType.user)
@commands.guild_only()
async def business_economystatus_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        meta = state.get("meta", {})
        users = state.get("users", {})
        market_note = str(state.get("market", {}).get("last_news", "No market update yet."))
        event = state.get("market", {}).get("active_event")
        event_name = str(event.get("name")) if isinstance(event, dict) else "none"
        event_left = int(event.get("remaining_ticks", 0) or 0) if isinstance(event, dict) else 0
        global_halt = _business_market_halt_remaining()
    await ctx.send(
        "🌐 **Economy Status (v1.5)**\n"
        f"Schema: `{state.get('schema_version', 1)}` | Users: `{len(users)}`\n"
        f"Tick pace: market `{BUSINESS_MARKET_TICK_MINUTES}m`, world `{BUSINESS_WORLD_EVENT_INTERVAL_MINUTES}m`, weekly `{BUSINESS_WEEKLY_CYCLE_DAYS}d`\n"
        f"Current event: `{event_name}` (`{event_left}` tick(s) left)\n"
        f"Global halt ticks: `{global_halt}`\n"
        f"Last market key: `{meta.get('last_market_tick_key', '-')}` | Last world key: `{meta.get('last_world_event_tick_key', '-')}`\n"
        f"Market note: {market_note}"
    )


@bot.hybrid_command(name="bizhelp")
@commands.cooldown(2, 5, commands.BucketType.user)
@commands.guild_only()
async def business_help_command(ctx: commands.Context, *, query: str | None = None) -> None:
    if not await _business_require_access(
        ctx,
        check_cooldown=False,
        mutate=False,
        allow_when_disabled=True,
    ):
        return
    prompt = (query or "").strip() or "how do i start the game"
    await send_business_help_query_response(ctx, prompt)


@bot.hybrid_command(name="guide")
@commands.cooldown(2, 5, commands.BucketType.user)
async def guide_command(ctx: commands.Context, *, query: str | None = None) -> None:
    prompt = (query or "").strip() or "what can you do"
    if parse_business_help_query(prompt) is not None:
        await send_business_help_query_response(ctx, prompt)
        return
    await send_general_guide_query_response(ctx, prompt)


@bot.hybrid_command(name="buy")
@commands.cooldown(2, 4, commands.BucketType.user)
@commands.guild_only()
async def business_buy_stock_command(ctx: commands.Context, stock: str, qty: int) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    symbol = stock.strip().upper()
    if qty < 1 or qty > 50000:
        await ctx.send("Quantity must be between `1` and `50000`.")
        return
    if _business_market_paused(ctx.guild.id):
        await ctx.send("Market is currently paused by admins.")
        return

    async with BUSINESS_STATE_LOCK:
        ok, text, total = _business_execute_asset_buy(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            asset_type="stock",
            symbol=symbol,
            qty=qty,
            source="command",
        )
    if not ok:
        await ctx.send(text)
        return

    await ctx.send(f"✅ {text}\nTotal cost (incl fee): `{_business_money(total)}`")
@bot.hybrid_command(name="sell")
@commands.cooldown(2, 4, commands.BucketType.user)
@commands.guild_only()
async def business_sell_stock_command(ctx: commands.Context, stock: str, qty: int) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    symbol = stock.strip().upper()
    if qty < 1 or qty > 50000:
        await ctx.send("Quantity must be between `1` and `50000`.")
        return
    if _business_market_paused(ctx.guild.id):
        await ctx.send("Market is currently paused by admins.")
        return

    async with BUSINESS_STATE_LOCK:
        ok, text, net = _business_execute_asset_sell(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id,
            asset_type="stock",
            symbol=symbol,
            qty=qty,
            source="command",
        )
    if not ok:
        await ctx.send(text)
        return

    await ctx.send(f"✅ {text}\nNet after fees/penalties: `{_business_money(net)}`")
@bot.hybrid_command(name="plots")
@commands.cooldown(3, 12, commands.BucketType.user)
@commands.guild_only()
async def business_plots_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        plots = list(state["real_estate"]["plots"].values())
    open_plots = [p for p in plots if isinstance(p, dict) and not p.get("owner_id")]
    open_plots.sort(key=lambda p: float(p.get("base_price", 0.0)))
    lines = []
    for plot in open_plots[:15]:
        lines.append(
            f"`{plot.get('id')}` | `{plot.get('zone')}` | Price `{_business_money(float(plot.get('base_price', 0.0)))}`"
        )
    if not lines:
        await ctx.send("No open plots right now. Check property listings or auctions.")
        return
    await ctx.send("ðŸ˜ï¸ **Available Plots**\n" + "\n".join(lines))


@bot.hybrid_command(name="buyplot")
@commands.cooldown(2, 6, commands.BucketType.user)
@commands.guild_only()
async def business_buy_plot_command(ctx: commands.Context, plot_id: str) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    pid = plot_id.strip().upper()
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        plot = state["real_estate"]["plots"].get(pid)
        if not isinstance(plot, dict):
            await ctx.send("Unknown plot id.")
            return
        if plot.get("owner_id"):
            await ctx.send("This plot already has an owner.")
            return
        user = _business_get_user(ctx.author.id)
        price = float(plot.get("base_price", 0.0))
        rates = _business_rates_for_guild(ctx.guild.id)
        fee = price * max(0.0, float(rates["transaction_fee_rate"]))
        total = price + fee
        cash = float(user.get("cash", 0.0))
        if cash < total:
            await ctx.send(f"Insufficient cash. Need `{_business_money(total)}`.")
            return
        user["cash"] = cash - total
        plot["owner_id"] = str(ctx.author.id)
        plot["tier"] = 0
        plot["listed_price"] = None
        plot["auction_lock"] = None
        props = user.setdefault("properties", [])
        if pid not in props:
            props.append(pid)
        tx_id = _business_add_ledger_entry(
            action="plot_buy",
            user_id=ctx.author.id,
            amount=-total,
            details={"plot_id": pid, "price": price, "fee": fee},
        )
        _mark_business_dirty()
    await ctx.send(
        f"âœ… You bought plot `{pid}` for `{_business_money(price)}` (+fee `{_business_money(fee)}`). "
        f"Tx: `{tx_id}`"
    )


@bot.hybrid_command(name="upgrade")
@commands.cooldown(2, 6, commands.BucketType.user)
@commands.guild_only()
async def business_upgrade_property_command(ctx: commands.Context, property_id: str) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    pid = property_id.strip().upper()
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        plot = state["real_estate"]["plots"].get(pid)
        if not isinstance(plot, dict):
            await ctx.send("Unknown property id.")
            return
        if str(plot.get("owner_id")) != str(ctx.author.id):
            await ctx.send("You do not own this property.")
            return
        if plot.get("auction_lock"):
            await ctx.send("This property is locked in an active auction.")
            return
        tier = int(plot.get("tier", 0))
        if tier >= 5:
            await ctx.send("Property is already max tier (`5`).")
            return
        user = _business_get_user(ctx.author.id)
        base_price = float(plot.get("base_price", 0.0))
        cost = base_price * (0.46 + (tier * 0.24))
        rates = _business_rates_for_guild(ctx.guild.id)
        fee = cost * max(0.0, float(rates["transaction_fee_rate"]))
        total = cost + fee
        if float(user.get("cash", 0.0)) < total:
            await ctx.send(f"Insufficient cash. Need `{_business_money(total)}`.")
            return
        user["cash"] = float(user.get("cash", 0.0)) - total
        plot["tier"] = tier + 1
        tx_id = _business_add_ledger_entry(
            action="property_upgrade",
            user_id=ctx.author.id,
            amount=-total,
            details={"property_id": pid, "new_tier": tier + 1},
        )
        _mark_business_dirty()
    await ctx.send(
        f"ðŸ—ï¸ Upgraded `{pid}` to tier `{tier + 1}`.\n"
        f"Upgrade spend: `{_business_money(total)}` | Tx: `{tx_id}`"
    )


@bot.hybrid_command(name="properties")
@commands.cooldown(3, 12, commands.BucketType.user)
@commands.guild_only()
async def business_properties_command(
    ctx: commands.Context, member: discord.Member | None = None
) -> None:
    if not await _business_require_access(ctx):
        return
    target = member or ctx.author
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        user = _business_get_user(target.id)
        plots = state["real_estate"]["plots"]
        lines: list[str] = []
        for plot_id in list(user.get("properties", []))[:20]:
            plot = plots.get(str(plot_id))
            if not isinstance(plot, dict):
                continue
            value = _business_plot_value(plot)
            listed_price = plot.get("listed_price")
            listed_text = f" | Listed `{_business_money(float(listed_price))}`" if listed_price else ""
            lines.append(
                f"`{plot_id}` `{plot.get('zone')}` Tier `{int(plot.get('tier', 0))}` "
                f"| Value `{_business_money(value)}`{listed_text}"
            )
    if not lines:
        await ctx.send(f"{target.display_name} does not own properties yet.")
        return
    await ctx.send(f"ðŸ  **Properties - {target.display_name}**\n" + "\n".join(lines))


@bot.hybrid_command(name="sellproperty")
@commands.cooldown(2, 6, commands.BucketType.user)
@commands.guild_only()
async def business_sell_property_command(ctx: commands.Context, property_id: str, price: float) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    pid = property_id.strip().upper()
    if price <= 0:
        await ctx.send("Price must be positive.")
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        plot = state["real_estate"]["plots"].get(pid)
        if not isinstance(plot, dict):
            await ctx.send("Unknown property id.")
            return
        if str(plot.get("owner_id")) != str(ctx.author.id):
            await ctx.send("You do not own this property.")
            return
        if plot.get("auction_lock"):
            await ctx.send("This property is locked by an active auction.")
            return
        plot["listed_price"] = float(price)
        state["real_estate"]["listed_properties"][pid] = {
            "owner_id": str(ctx.author.id),
            "price": float(price),
            "listed_ts": _business_now_ts(),
        }
        _mark_business_dirty()
    await ctx.send(f"ðŸ·ï¸ Property `{pid}` listed for `{_business_money(price)}`.")


@bot.hybrid_command(name="buyproperty")
@commands.cooldown(2, 6, commands.BucketType.user)
@commands.guild_only()
async def business_buy_property_command(ctx: commands.Context, property_id: str) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    pid = property_id.strip().upper()
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        listing = state["real_estate"]["listed_properties"].get(pid)
        plot = state["real_estate"]["plots"].get(pid)
        if not isinstance(listing, dict) or not isinstance(plot, dict):
            await ctx.send("This property is not listed.")
            return
        seller_id = int(listing.get("owner_id", 0))
        if seller_id == ctx.author.id:
            await ctx.send("You cannot buy your own listing.")
            return
        seller = _business_get_user(seller_id)
        buyer = _business_get_user(ctx.author.id)
        price = float(listing.get("price", 0.0))
        rates = _business_rates_for_guild(ctx.guild.id)
        fee = price * max(0.0, float(rates["transaction_fee_rate"]))
        transfer_tax = price * max(0.0, float(rates["property_tax_rate"]))
        total = price + fee + transfer_tax
        if float(buyer.get("cash", 0.0)) < total:
            await ctx.send(
                f"Insufficient cash. Need `{_business_money(total)}` including fee/tax."
            )
            return
        buyer["cash"] = float(buyer.get("cash", 0.0)) - total
        seller["cash"] = float(seller.get("cash", 0.0)) + max(0.0, price - fee)
        plot["owner_id"] = str(ctx.author.id)
        plot["listed_price"] = None
        seller["properties"] = [x for x in seller.get("properties", []) if x != pid]
        buyer_props = buyer.setdefault("properties", [])
        if pid not in buyer_props:
            buyer_props.append(pid)
        state["real_estate"]["listed_properties"].pop(pid, None)
        tx_id = _business_add_ledger_entry(
            action="property_transfer",
            user_id=ctx.author.id,
            amount=-total,
            details={"property_id": pid, "seller_id": seller_id, "price": price},
        )
        _mark_business_dirty()
    await ctx.send(
        f"âœ… You bought property `{pid}` for `{_business_money(price)}`.\n"
        f"Total spend: `{_business_money(total)}` | Tx: `{tx_id}`"
    )


@bot.hybrid_command(name="loan")
@commands.cooldown(3, 10, commands.BucketType.user)
@commands.guild_only()
async def business_loan_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    async with BUSINESS_STATE_LOCK:
        user = _business_get_user(ctx.author.id)
        active = _business_active_loans(user)
        debt = _business_debt_total(user)
        net = _business_networth(ctx.author.id)
    if not active:
        await ctx.send(
            f"ðŸ’³ No active loans.\n"
            f"Debt: `{_business_money(debt)}` | Net worth: `{_business_money(net)}`"
        )
        return
    lines = []
    for loan in active[:8]:
        due_hours = max(0, int((float(loan.get('due_ts', 0.0)) - _business_now_ts()) / 3600))
        lines.append(
            f"`{loan.get('id')}` balance `{_business_money(float(loan.get('balance', 0.0)))}` "
            f"| status `{loan.get('status', 'current')}` | due in `{due_hours}h`"
        )
    await ctx.send(
        f"ðŸ’³ **Active Loans**\nDebt total: `{_business_money(debt)}`\n" + "\n".join(lines)
    )


@bot.hybrid_command(name="takeloan")
@commands.cooldown(2, 6, commands.BucketType.user)
@commands.guild_only()
async def business_take_loan_command(ctx: commands.Context, amount: float) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    if amount <= 0:
        await ctx.send("Amount must be positive.")
        return
    loan_rate = None
    async with BUSINESS_STATE_LOCK:
        ok, data = _business_issue_loan(ctx.author.id, float(amount))
        if ok:
            user = _business_get_user(ctx.author.id)
            for loan in user.get("loans", []):
                if isinstance(loan, dict) and str(loan.get("id")) == str(data):
                    loan_rate = float(loan.get("rate", BUSINESS_HOURLY_INTEREST_RATE) or BUSINESS_HOURLY_INTEREST_RATE)
                    break
    if not ok:
        await ctx.send(data)
        return
    await ctx.send(
        f"ðŸ¦ Loan approved. Loan ID: `{data}` | Amount: `{_business_money(float(amount))}`\n"
        f"Interest accrues hourly at `{(loan_rate if loan_rate is not None else BUSINESS_HOURLY_INTEREST_RATE) * 100:.3f}%`."
    )


@bot.hybrid_command(name="repay")
@commands.cooldown(2, 4, commands.BucketType.user)
@commands.guild_only()
async def business_repay_loan_command(ctx: commands.Context, amount: float) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    if amount <= 0:
        await ctx.send("Amount must be positive.")
        return
    async with BUSINESS_STATE_LOCK:
        paid, closed = _business_repay_loans_from_cash(
            ctx.author.id,
            float(amount),
            source="manual",
        )
    if paid <= 0:
        await ctx.send("No repayment executed. Check your debt and cash balance.")
        return
    await ctx.send(
        f"âœ… Repaid `{_business_money(paid)}`. Closed loans: `{closed}`."
    )


@bot.hybrid_command(name="debts")
@commands.cooldown(3, 10, commands.BucketType.user)
@commands.guild_only()
async def business_debts_command(ctx: commands.Context, member: discord.Member | None = None) -> None:
    if not await _business_require_access(ctx):
        return
    target = member or ctx.author
    async with BUSINESS_STATE_LOCK:
        user = _business_get_user(target.id)
        active = _business_active_loans(user)
        debt = _business_debt_total(user)
    if not active:
        await ctx.send(f"{target.display_name} has no active debt.")
        return
    lines = []
    for loan in active[:10]:
        lines.append(
            f"`{loan.get('id')}` `{loan.get('status', 'current')}` | "
            f"balance `{_business_money(float(loan.get('balance', 0.0)))}` | "
            f"overdue `{int(loan.get('overdue_hours', 0))}h`"
        )
    await ctx.send(
        f"ðŸ“‰ **Debt Status - {target.display_name}**\n"
        f"Total debt: `{_business_money(debt)}`\n" + "\n".join(lines)
    )


@bot.hybrid_command(name="trade")
@commands.cooldown(2, 5, commands.BucketType.user)
@commands.guild_only()
async def business_trade_command(
    ctx: commands.Context,
    member: discord.Member,
    offer_type: str,
    asset: str,
    amount: int,
    request_cash: float = 0.0,
) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    if member.bot or member.id == ctx.author.id:
        await ctx.send("Choose a valid user for trading.")
        return
    if amount <= 0:
        await ctx.send("Amount must be positive.")
        return
    normalized = offer_type.strip().lower()
    if normalized not in {"cash", "stock", "property"}:
        await ctx.send("offer_type must be `cash`, `stock`, or `property`.")
        return

    async with BUSINESS_STATE_LOCK:
        if _business_user_open_trade_count(ctx.author.id) >= BUSINESS_MAX_OPEN_TRADES:
            await ctx.send(f"You already have `{BUSINESS_MAX_OPEN_TRADES}` open trades.")
            return
        if _business_user_open_trade_count(member.id) >= BUSINESS_MAX_OPEN_TRADES:
            await ctx.send(f"{member.mention} already has too many open trades.")
            return
        sender = _business_get_user(ctx.author.id)
        recipient = _business_get_user(member.id)
        if normalized == "cash":
            if float(sender.get("cash", 0.0)) < float(amount):
                await ctx.send("Insufficient cash for this trade offer.")
                return
        elif normalized == "stock":
            symbol = asset.strip().upper()
            holding = sender.get("portfolio", {}).get(symbol)
            if not isinstance(holding, dict) or int(holding.get("qty", 0)) < amount:
                await ctx.send(f"You do not have `{amount}` shares of `{symbol}`.")
                return
        elif normalized == "property":
            property_id = asset.strip().upper()
            state = get_business_state()
            plot = state["real_estate"]["plots"].get(property_id)
            if not isinstance(plot, dict) or str(plot.get("owner_id")) != str(ctx.author.id):
                await ctx.send("You do not own that property.")
                return
            if plot.get("auction_lock"):
                await ctx.send("Property is locked by an active auction.")
                return

        trade_id = _business_next_id("trade")
        offer = {
            "id": trade_id,
            "from_user_id": ctx.author.id,
            "to_user_id": member.id,
            "offer_type": normalized,
            "asset": asset.strip().upper(),
            "amount": int(amount),
            "request_cash": max(0.0, float(request_cash)),
            "created_ts": _business_now_ts(),
            "expires_ts": _business_now_ts() + (20 * 60),
            "guild_id": ctx.guild.id,
            "channel_id": ctx.channel.id,
        }
        get_business_state()["trades"]["open"][trade_id] = offer
        _mark_business_dirty()

    await ctx.send(
        f"ðŸ¤ Trade offer `{trade_id}` created for {member.mention}.\n"
        f"Offer: `{normalized} {asset.upper()} x {amount}` | Request cash: `{_business_money(float(request_cash))}`\n"
        f"Use `{PREFIX}trade_accept {trade_id}` or `{PREFIX}trade_decline {trade_id}`."
    )


@bot.hybrid_command(name="trade_accept")
@commands.cooldown(2, 5, commands.BucketType.user)
@commands.guild_only()
async def business_trade_accept_command(ctx: commands.Context, trade_id: str) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    tid = trade_id.strip().upper()
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        offer = state["trades"]["open"].get(tid)
        if not isinstance(offer, dict):
            await ctx.send("Trade not found or expired.")
            return
        if int(offer.get("to_user_id", 0)) != ctx.author.id:
            await ctx.send("This trade is not addressed to you.")
            return
        if _business_now_ts() >= float(offer.get("expires_ts", 0.0)):
            state["trades"]["open"].pop(tid, None)
            _mark_business_dirty()
            await ctx.send("Trade offer expired.")
            return

        sender_id = int(offer.get("from_user_id", 0))
        sender = _business_get_user(sender_id)
        receiver = _business_get_user(ctx.author.id)
        kind = str(offer.get("offer_type", ""))
        asset = str(offer.get("asset", ""))
        amount = int(offer.get("amount", 0))
        request_cash = float(offer.get("request_cash", 0.0))
        rates = _business_rates_for_guild(ctx.guild.id)
        fee_rate = max(0.0, float(rates["transaction_fee_rate"]))

        if float(receiver.get("cash", 0.0)) < request_cash:
            await ctx.send("You do not have enough cash to accept this trade.")
            return

        if kind == "cash":
            if float(sender.get("cash", 0.0)) < amount:
                await ctx.send("Trade failed: sender no longer has enough cash.")
                return
            sender["cash"] = float(sender.get("cash", 0.0)) - amount
            receiver["cash"] = float(receiver.get("cash", 0.0)) + amount
        elif kind == "stock":
            holding = sender.get("portfolio", {}).get(asset)
            if not isinstance(holding, dict) or int(holding.get("qty", 0)) < amount:
                await ctx.send("Trade failed: sender no longer has those shares.")
                return
            if not _business_remove_stock_from_user(sender, asset, amount):
                await ctx.send("Trade failed while transferring stock.")
                return
            _business_add_stock_to_user(receiver, asset, amount, 0.0)
        elif kind == "property":
            plot = state["real_estate"]["plots"].get(asset)
            if not isinstance(plot, dict) or str(plot.get("owner_id")) != str(sender_id):
                await ctx.send("Trade failed: property is no longer owned by sender.")
                return
            if plot.get("auction_lock"):
                await ctx.send("Trade failed: property is locked in auction.")
                return
            plot["owner_id"] = str(ctx.author.id)
            plot["listed_price"] = None
            sender["properties"] = [pid for pid in sender.get("properties", []) if pid != asset]
            receiver_props = receiver.setdefault("properties", [])
            if asset not in receiver_props:
                receiver_props.append(asset)
        else:
            await ctx.send("Unsupported trade type.")
            return

        if request_cash > 0:
            fee = request_cash * fee_rate
            receiver["cash"] = float(receiver.get("cash", 0.0)) - request_cash
            sender["cash"] = float(sender.get("cash", 0.0)) + max(0.0, request_cash - fee)

        state["trades"]["open"].pop(tid, None)
        _business_add_ledger_entry(
            action="trade_accept",
            user_id=ctx.author.id,
            amount=-request_cash,
            details={"trade_id": tid, "from_user_id": sender_id, "offer_type": kind, "asset": asset, "amount": amount},
        )
        _mark_business_dirty()
    await ctx.send(f"âœ… Trade `{tid}` accepted.")
    if request_cash >= max(50000.0, BUSINESS_STARTER_CASH * 15) and get_guild_business_moderation_enabled(ctx.guild.id):
        await send_mod_log(
            ctx.guild,
            "Business Suspicious Transfer",
            moderator=ctx.author,
            target=ctx.author,
            channel=ctx.channel,
            details=(
                f"Trade `{tid}` settled with high requested cash `{_business_money(request_cash)}` "
                f"from `<@{sender_id}>` to `<@{ctx.author.id}>`."
            ),
        )


@bot.hybrid_command(name="trade_decline")
@commands.cooldown(2, 5, commands.BucketType.user)
@commands.guild_only()
async def business_trade_decline_command(ctx: commands.Context, trade_id: str) -> None:
    if not await _business_require_access(ctx, mutate=False):
        return
    tid = trade_id.strip().upper()
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        offer = state["trades"]["open"].get(tid)
        if not isinstance(offer, dict):
            await ctx.send("Trade not found.")
            return
        if int(offer.get("to_user_id", 0)) != ctx.author.id and int(offer.get("from_user_id", 0)) != ctx.author.id:
            await ctx.send("You cannot decline this trade.")
            return
        state["trades"]["open"].pop(tid, None)
        _mark_business_dirty()
    await ctx.send(f"âŒ Trade `{tid}` declined.")


@bot.hybrid_command(name="auction_start")
@commands.cooldown(2, 8, commands.BucketType.user)
@commands.guild_only()
async def business_auction_start_command(
    ctx: commands.Context,
    asset_type: str,
    asset_id: str,
    start_price: float,
    duration_minutes: int,
    qty: int = 1,
) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    if start_price <= 0:
        await ctx.send("Start price must be positive.")
        return
    if duration_minutes < 1 or duration_minutes > 240:
        await ctx.send("Duration must be between `1` and `240` minutes.")
        return
    normalized = asset_type.strip().lower()
    if normalized not in {"stock", "property"}:
        await ctx.send("asset_type must be `stock` or `property`.")
        return

    async with BUSINESS_STATE_LOCK:
        if _business_user_open_auction_count(ctx.author.id) >= BUSINESS_MAX_OPEN_AUCTIONS:
            await ctx.send(f"You already have `{BUSINESS_MAX_OPEN_AUCTIONS}` open auctions.")
            return
        state = get_business_state()
        seller = _business_get_user(ctx.author.id)
        ref = asset_id.strip().upper()
        if normalized == "stock":
            if qty < 1:
                await ctx.send("Quantity must be at least `1`.")
                return
            holding = seller.get("portfolio", {}).get(ref)
            if not isinstance(holding, dict) or int(holding.get("qty", 0)) < qty:
                await ctx.send(f"You do not have `{qty}` `{ref}` shares.")
                return
            if not _business_remove_stock_from_user(seller, ref, qty):
                await ctx.send("Failed to lock stock for auction.")
                return
        else:
            plot = state["real_estate"]["plots"].get(ref)
            if not isinstance(plot, dict) or str(plot.get("owner_id")) != str(ctx.author.id):
                await ctx.send("You do not own this property.")
                return
            if plot.get("auction_lock"):
                await ctx.send("This property is already in an auction.")
                return
            plot["auction_lock"] = True
            qty = 1

        auction_id = _business_next_id("auction")
        auction = {
            "id": auction_id,
            "seller_id": ctx.author.id,
            "asset_type": normalized,
            "asset_ref": ref,
            "qty": int(qty),
            "start_price": float(start_price),
            "highest_bid": 0.0,
            "highest_bidder": None,
            "bids": [],
            "start_ts": _business_now_ts(),
            "end_ts": _business_now_ts() + (duration_minutes * 60),
            "guild_id": ctx.guild.id,
            "channel_id": ctx.channel.id,
        }
        state["auctions"]["active"][auction_id] = auction
        _mark_business_dirty()
    await ctx.send(
        f"ðŸ“£ Auction `{auction_id}` started.\n"
        f"Asset: `{normalized} {asset_id.upper()} x{qty}` | Start: `{_business_money(start_price)}` | "
        f"Duration: `{duration_minutes}` min"
    )


@bot.hybrid_command(name="bid")
@commands.cooldown(2, 4, commands.BucketType.user)
@commands.guild_only()
async def business_bid_command(ctx: commands.Context, auction_id: str, amount: float) -> None:
    if not await _business_require_access(ctx, mutate=True):
        return
    aid = auction_id.strip().upper()
    if amount <= 0:
        await ctx.send("Bid amount must be positive.")
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        auction = state["auctions"]["active"].get(aid)
        if not isinstance(auction, dict):
            await ctx.send("Auction not found.")
            return
        if _business_now_ts() >= float(auction.get("end_ts", 0.0)):
            pass
    if _business_now_ts() >= float(auction.get("end_ts", 0.0)):
        summary = await _business_settle_auction(aid, reason="late_bid")
        await ctx.send(f"Auction already ended. {summary}")
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        auction = state["auctions"]["active"].get(aid)
        if not isinstance(auction, dict):
            await ctx.send("Auction not found.")
            return
        if int(auction.get("seller_id", 0)) == ctx.author.id:
            await ctx.send("You cannot bid on your own auction.")
            return
        user = _business_get_user(ctx.author.id)
        if float(user.get("cash", 0.0)) < amount:
            await ctx.send("Insufficient cash for this bid.")
            return
        minimum = float(auction.get("highest_bid", 0.0))
        if minimum <= 0:
            minimum = float(auction.get("start_price", 0.0))
        else:
            minimum += max(50.0, minimum * 0.02)
        if amount < minimum:
            await ctx.send(f"Bid too low. Minimum required: `{_business_money(minimum)}`.")
            return

        auction["highest_bid"] = float(amount)
        auction["highest_bidder"] = ctx.author.id
        bids = auction.setdefault("bids", [])
        if isinstance(bids, list):
            bids.append({"user_id": ctx.author.id, "amount": float(amount), "ts": _business_now_ts()})
            if len(bids) > 40:
                del bids[:-40]
        remaining = float(auction.get("end_ts", 0.0)) - _business_now_ts()
        if remaining <= BUSINESS_AUCTION_SNIPING_WINDOW_SECONDS:
            auction["end_ts"] = float(auction.get("end_ts", 0.0)) + BUSINESS_AUCTION_SNIPING_EXTEND_SECONDS
        _mark_business_dirty()
    await ctx.send(f"âœ… Bid accepted on `{aid}`: `{_business_money(amount)}`.")


@bot.hybrid_command(name="auctions")
@commands.cooldown(3, 8, commands.BucketType.user)
@commands.guild_only()
async def business_auctions_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        active = list(state["auctions"]["active"].values())
    if not active:
        await ctx.send("No active auctions right now.")
        return
    lines = []
    now_ts = _business_now_ts()
    for auction in sorted(active, key=lambda a: float(a.get("end_ts", 0.0)))[:15]:
        if not isinstance(auction, dict):
            continue
        left = max(0, int((float(auction.get("end_ts", 0.0)) - now_ts) / 60))
        price = float(auction.get("highest_bid", 0.0) or 0.0)
        if price <= 0:
            price = float(auction.get("start_price", 0.0))
        lines.append(
            f"`{auction.get('id')}` {auction.get('asset_type')} `{auction.get('asset_ref')}` "
            f"x{auction.get('qty')} | bid `{_business_money(price)}` | `{left}m` left"
        )
    await ctx.send("ðŸ **Active Auctions**\n" + "\n".join(lines))


@bot.hybrid_command(name="bizleaderboard")
@commands.cooldown(2, 10, commands.BucketType.user)
@commands.guild_only()
async def business_leaderboard_command(ctx: commands.Context, metric: str = "networth") -> None:
    if not await _business_require_access(ctx):
        return
    normalized = metric.strip().lower()
    if normalized not in {"cash", "networth", "income"}:
        await ctx.send("Metric must be `cash`, `networth`, or `income`.")
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        rows: list[tuple[int, float]] = []
        for uid_text, payload in state["users"].items():
            if not str(uid_text).isdigit() or not isinstance(payload, dict):
                continue
            uid = int(uid_text)
            if normalized == "cash":
                score = float(payload.get("cash", 0.0))
            elif normalized == "income":
                score = float(payload.get("income_total", 0.0))
            else:
                score = _business_networth(uid)
            rows.append((uid, score))
    rows.sort(key=lambda item: item[1], reverse=True)
    if not rows:
        await ctx.send("Business leaderboard is empty.")
        return
    lines: list[str] = []
    for idx, (uid, score) in enumerate(rows[:10], start=1):
        member = ctx.guild.get_member(uid)
        name = member.display_name if isinstance(member, discord.Member) else str(uid)
        lines.append(f"{idx}. **{name}** - `{_business_money(score)}`")
    await ctx.send(f"ðŸ† **Business Leaderboard ({normalized})**\n" + "\n".join(lines))


@bot.hybrid_command(name="bizprofile")
@commands.cooldown(3, 12, commands.BucketType.user)
@commands.guild_only()
async def business_profile_command(ctx: commands.Context, member: discord.Member | None = None) -> None:
    if not await _business_require_access(ctx):
        return
    target = member or ctx.author
    async with BUSINESS_STATE_LOCK:
        user = _business_get_user(target.id)
        cash = float(user.get("cash", 0.0))
        net = _business_networth(target.id)
        debt = _business_debt_total(user)
        properties = len(list(user.get("properties", [])))
        stock_holdings = len(list(user.get("portfolio", {}).keys())) if isinstance(user.get("portfolio"), dict) else 0
        commodity_holdings = (
            len(list(user.get("commodity_portfolio", {}).keys()))
            if isinstance(user.get("commodity_portfolio"), dict)
            else 0
        )
        crypto_holdings = (
            len(list(user.get("crypto_portfolio", {}).keys()))
            if isinstance(user.get("crypto_portfolio"), dict)
            else 0
        )
        businesses = len(list(user.get("business_ids", [])))
        credit_score = int(user.get("credit_score", 650) or 650)
        tax_liability = float(user.get("tax_liability", 0.0) or 0.0)
        income_total = float(user.get("income_total", 0.0))
        claim_streak = int(user.get("daily", {}).get("streak", 0)) if isinstance(user.get("daily"), dict) else 0
    tip = ""
    if target.id == ctx.author.id:
        tip = await _business_get_personalized_tip(
            ctx.guild.id,
            ctx.author.id,
            context="profile_review",
        )
    await ctx.send(
        f"ðŸ‘¤ **Business Profile - {target.display_name}**\n"
        f"Cash: `{_business_money(cash)}`\n"
        f"Net worth: `{_business_money(net)}`\n"
        f"Debt: `{_business_money(debt)}`\n"
        f"Holdings: stocks `{stock_holdings}` | commodities `{commodity_holdings}` | crypto `{crypto_holdings}`\n"
        f"Properties: `{properties}` | Businesses: `{businesses}`\n"
        f"Credit score: `{credit_score}` | Tax liability: `{_business_money(tax_liability)}`\n"
        f"Total passive income earned: `{_business_money(income_total)}`\n"
        f"Daily claim streak: `{claim_streak}`"
        + (f"\n{tip}" if tip else "")
    )


@bot.hybrid_command(name="marketnews")
@commands.cooldown(3, 8, commands.BucketType.user)
@commands.guild_only()
async def business_market_news_command(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx):
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        news = str(state["market"].get("last_news", "No market update yet."))
        commodity_news = str(state.get("commodities", {}).get("last_news", ""))
        crypto_news = str(state.get("crypto", {}).get("last_news", ""))
        history = state["market"].get("history", [])
        recent = history[-3:] if isinstance(history, list) else []
        dynamic = _business_get_ai_dynamic(state)
        headline = str(dynamic.get("headline", "")).strip()
    lines = [f"- {item.get('news', '')}" for item in recent if isinstance(item, dict)]
    if not lines:
        lines = ["- No recent events."]
    headline_line = f"\nAI mood: `{headline}`" if headline else ""
    await ctx.send(
        "ðŸ—žï¸ **Market News**\n"
        + news
        + (f"\n{commodity_news}" if commodity_news else "")
        + (f"\n{crypto_news}" if crypto_news else "")
        + headline_line
        + "\n\nRecent updates:\n"
        + "\n".join(lines)
    )


@bot.hybrid_command(name="ledger")
@commands.cooldown(3, 10, commands.BucketType.user)
@commands.guild_only()
async def business_ledger_command(ctx: commands.Context, member: discord.Member | None = None) -> None:
    if not await _business_require_access(ctx):
        return
    target_id = member.id if member else None
    async with BUSINESS_STATE_LOCK:
        entries = list(get_business_state().get("ledger", []))
    entries = [entry for entry in entries if isinstance(entry, dict)]
    if target_id is not None:
        entries = [entry for entry in entries if int(entry.get("user_id", 0) or 0) == target_id]
    if not entries:
        await ctx.send("No ledger entries found.")
        return
    entries = entries[-12:]
    lines = []
    for entry in entries:
        amount = float(entry.get("amount", 0.0))
        lines.append(
            f"`{entry.get('id')}` `{entry.get('action')}` `{amount:+,.0f}` "
            f"user `{entry.get('user_id')}`"
        )
    await ctx.send("ðŸ“’ **Business Ledger (latest)**\n" + "\n".join(lines))


@bot.hybrid_group(name="bizadmin", invoke_without_command=True)
@commands.guild_only()
async def bizadmin_group(ctx: commands.Context) -> None:
    if not await _business_require_access(ctx, require_mod=True, check_cooldown=False):
        return
    await ctx.send(
        f"Usage: `{PREFIX}bizadmin <freeze|unfreeze|grant|setcash|reverse|settax|marketpause|audit>` ..."
    )


@bizadmin_group.command(name="freeze")
async def bizadmin_freeze(ctx: commands.Context, member: discord.Member) -> None:
    if not await _business_require_access(ctx, require_mod=True, check_cooldown=False):
        return
    async with BUSINESS_STATE_LOCK:
        _business_set_user_frozen(member.id, True)
    await ctx.send(f"ðŸ”’ Froze business account for {member.mention}.")


@bizadmin_group.command(name="unfreeze")
async def bizadmin_unfreeze(ctx: commands.Context, member: discord.Member) -> None:
    if not await _business_require_access(ctx, require_mod=True, check_cooldown=False):
        return
    async with BUSINESS_STATE_LOCK:
        _business_set_user_frozen(member.id, False)
    await ctx.send(f"ðŸ”“ Unfroze business account for {member.mention}.")


@bizadmin_group.command(name="grant")
async def bizadmin_grant(ctx: commands.Context, member: discord.Member, amount: float) -> None:
    if not await _business_require_access(ctx, require_mod=True, check_cooldown=False):
        return
    if amount <= 0:
        await ctx.send("Amount must be positive.")
        return
    async with BUSINESS_STATE_LOCK:
        user = _business_get_user(member.id)
        user["cash"] = float(user.get("cash", 0.0)) + amount
        tx_id = _business_add_ledger_entry(
            action="admin_grant",
            user_id=member.id,
            amount=amount,
            details={"moderator_id": ctx.author.id},
        )
        _mark_business_dirty()
    await ctx.send(f"Granted `{_business_money(amount)}` to {member.mention}. Tx: `{tx_id}`")
    if amount >= max(50000.0, BUSINESS_STARTER_CASH * 15) and get_guild_business_moderation_enabled(ctx.guild.id):
        await send_mod_log(
            ctx.guild,
            "Business Suspicious Transfer",
            moderator=ctx.author,
            target=member,
            channel=ctx.channel,
            details=f"Large grant `{_business_money(amount)}` | tx `{tx_id}`",
        )


@bizadmin_group.command(name="setcash")
async def bizadmin_setcash(ctx: commands.Context, member: discord.Member, amount: float) -> None:
    if not await _business_require_access(ctx, require_mod=True, check_cooldown=False):
        return
    if amount < 0:
        await ctx.send("Cash cannot be negative.")
        return
    async with BUSINESS_STATE_LOCK:
        user = _business_get_user(member.id)
        old_cash = float(user.get("cash", 0.0))
        user["cash"] = float(amount)
        tx_id = _business_add_ledger_entry(
            action="admin_setcash",
            user_id=member.id,
            amount=float(amount) - old_cash,
            details={"moderator_id": ctx.author.id, "old_cash": old_cash, "new_cash": amount},
        )
        _mark_business_dirty()
    await ctx.send(
        f"Set cash for {member.mention} from `{_business_money(old_cash)}` to `{_business_money(amount)}`. "
        f"Tx: `{tx_id}`"
    )


@bizadmin_group.command(name="reverse")
async def bizadmin_reverse(ctx: commands.Context, tx_id: str) -> None:
    if not await _business_require_access(ctx, require_mod=True, check_cooldown=False):
        return
    tid = tx_id.strip().upper()
    async with BUSINESS_STATE_LOCK:
        rollback = BUSINESS_TX_ROLLBACK_CACHE.get(tid)
        if not isinstance(rollback, dict):
            await ctx.send("Rollback data not available for this transaction.")
            return
        rollback_type = str(rollback.get("type", ""))
        user_id = int(rollback.get("user_id", 0))
        user = _business_get_user(user_id)
        if rollback_type == "stock_buy":
            symbol = str(rollback.get("symbol", ""))
            qty = int(rollback.get("qty", 0))
            if qty > 0:
                _business_remove_stock_from_user(user, symbol, qty)
            user["cash"] = float(user.get("cash", 0.0)) + float(rollback.get("cash_delta", 0.0))
        elif rollback_type == "stock_sell":
            symbol = str(rollback.get("symbol", ""))
            qty = int(rollback.get("qty", 0))
            user["cash"] = float(user.get("cash", 0.0)) + float(rollback.get("cash_delta", 0.0))
            _business_add_stock_to_user(user, symbol, qty, 0.0)
        else:
            await ctx.send("This transaction type is not reversible automatically.")
            return
        _business_add_ledger_entry(
            action="admin_reverse",
            user_id=user_id,
            amount=0.0,
            details={"moderator_id": ctx.author.id, "source_tx_id": tid, "rollback_type": rollback_type},
        )
        _mark_business_dirty()
    await ctx.send(f"Reversed transaction `{tid}`.")


@bizadmin_group.command(name="settax")
async def bizadmin_settax(ctx: commands.Context, key: str, value: float) -> None:
    if not await _business_require_access(ctx, require_mod=True, check_cooldown=False):
        return
    key_map = {
        "transaction": "transaction_fee_rate",
        "transaction_fee_rate": "transaction_fee_rate",
        "property_tax": "property_tax_rate",
        "property_tax_rate": "property_tax_rate",
        "maintenance": "property_maintenance_rate",
        "property_maintenance_rate": "property_maintenance_rate",
        "gains_short": "capital_gains_short_rate",
        "capital_gains_short_rate": "capital_gains_short_rate",
        "gains_long": "capital_gains_long_rate",
        "capital_gains_long_rate": "capital_gains_long_rate",
    }
    normalized = key_map.get(key.strip().lower())
    if normalized is None:
        await ctx.send("Key must be transaction/property_tax/maintenance/gains_short/gains_long.")
        return
    if value < 0 or value > 0.5:
        await ctx.send("Value must be between `0` and `0.5`.")
        return
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        if normalized in {"capital_gains_short_rate", "capital_gains_long_rate"}:
            tax_state = state.setdefault("tax", {})
            tax_state[normalized] = float(value)
        else:
            state["governance"][normalized] = float(value)
            set_guild_business_tax_overrides(ctx.guild.id, {normalized: float(value)})
        _mark_business_dirty()
    await ctx.send(f"Updated `{normalized}` to `{value:.4f}`.")


@bizadmin_group.command(name="marketpause")
async def bizadmin_marketpause(ctx: commands.Context, mode: str) -> None:
    if not await _business_require_access(ctx, require_mod=True, check_cooldown=False):
        return
    normalized = mode.strip().lower()
    if normalized not in {"on", "off"}:
        await ctx.send(f"Usage: `{PREFIX}bizadmin marketpause <on|off>`")
        return
    paused = normalized == "on"
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        state["governance"]["market_paused"] = paused
        set_guild_business_market_paused(ctx.guild.id, paused)
        _mark_business_dirty()
    await ctx.send(f"Market pause is now **{'on' if paused else 'off'}**.")


@bizadmin_group.command(name="enable")
async def bizadmin_enable(ctx: commands.Context, mode: str) -> None:
    if not await _business_require_access(
        ctx,
        require_mod=True,
        check_cooldown=False,
        allow_when_disabled=True,
    ):
        return
    normalized = mode.strip().lower()
    if normalized not in {"on", "off"}:
        await ctx.send(f"Usage: `{PREFIX}bizadmin enable <on|off>`")
        return
    enabled = normalized == "on"
    set_guild_business_enabled(ctx.guild.id, enabled)
    await ctx.send(f"Business mode is now **{'enabled' if enabled else 'disabled'}** in this server.")


@bizadmin_group.command(name="moderation")
async def bizadmin_moderation(ctx: commands.Context, mode: str) -> None:
    if not await _business_require_access(ctx, require_mod=True, check_cooldown=False):
        return
    normalized = mode.strip().lower()
    if normalized not in {"on", "off"}:
        await ctx.send(f"Usage: `{PREFIX}bizadmin moderation <on|off>`")
        return
    enabled = normalized == "on"
    set_guild_business_moderation_enabled(ctx.guild.id, enabled)
    await ctx.send(f"Business moderation hooks are now **{'enabled' if enabled else 'disabled'}**.")


@bizadmin_group.command(name="audit")
async def bizadmin_audit(ctx: commands.Context, audit_type: str = "user", value: str | None = None) -> None:
    if not await _business_require_access(ctx, require_mod=True, check_cooldown=False):
        return
    kind = audit_type.strip().lower()
    async with BUSINESS_STATE_LOCK:
        state = get_business_state()
        if kind == "tx" and value:
            tx = next((entry for entry in state["ledger"] if str(entry.get("id")) == value.upper()), None)
            if not isinstance(tx, dict):
                await ctx.send("Transaction not found.")
                return
            await ctx.send(
                f"Audit tx `{tx.get('id')}`: action `{tx.get('action')}`, user `{tx.get('user_id')}`, "
                f"amount `{float(tx.get('amount', 0.0)):+,.0f}`."
            )
            return

        target: discord.Member | None = None
        if value:
            if value.isdigit():
                target = ctx.guild.get_member(int(value))
            if target is None:
                target = discord.utils.find(lambda m: m.display_name.lower() == value.lower(), ctx.guild.members)
        if target is None:
            target = ctx.author
        user = _business_get_user(target.id)
        await ctx.send(
            f"Audit user **{target.display_name}**:\n"
            f"Cash `{_business_money(float(user.get('cash', 0.0)))}`\n"
            f"Net worth `{_business_money(_business_networth(target.id))}`\n"
            f"Debt `{_business_money(_business_debt_total(user))}`\n"
            f"Flags `{user.get('flags', {})}` | Frozen `{_business_is_user_frozen(target.id)}`"
        )


@bot.command(name="join")
async def join_voice(ctx: commands.Context) -> None:
    vc = await ensure_voice_connection(ctx)
    if vc is None:
        return
    MUSIC_TEXT_CHANNELS[ctx.guild.id] = ctx.channel.id
    await ctx.send(f"Joined voice channel: {vc.channel.mention}")


@bot.command(name="leave", aliases=["dc", "disconnect"])
async def leave_voice(ctx: commands.Context) -> None:
    vc = ctx.guild.voice_client
    if vc is None:
        await ctx.send("I am not in a voice channel.")
        return
    if not in_same_voice_channel(ctx):
        await ctx.send("You must be in my voice channel to use this command.")
        return

    MUSIC_QUEUES[ctx.guild.id].clear()
    MUSIC_NOW_PLAYING.pop(ctx.guild.id, None)
    MUSIC_TEXT_CHANNELS.pop(ctx.guild.id, None)
    await vc.disconnect(force=True)
    await ctx.send("Disconnected and cleared music queue.")


@bot.command(name="play", aliases=["p"])
async def play_music(ctx: commands.Context, *, source: str) -> None:
    global FFMPEG_EXECUTABLE
    vc = await ensure_voice_connection(ctx)
    if vc is None:
        return
    if yt_dlp is None:
        await ctx.send("Music features require `yt-dlp`. Install dependencies first.")
        return
    if not FFMPEG_EXECUTABLE:
        FFMPEG_EXECUTABLE = resolve_ffmpeg_executable()
    if not FFMPEG_EXECUTABLE:
        await ctx.send(
            "ffmpeg was not found. Install ffmpeg on host, or install `imageio-ffmpeg` in requirements and restart."
        )
        return

    source = source.strip()
    if not source:
        await ctx.send(f"Usage: `{PREFIX}play <youtube/spotify link or search>`")
        return

    MUSIC_TEXT_CHANNELS[ctx.guild.id] = ctx.channel.id

    async with ctx.typing():
        try:
            tracks, label = await source_to_tracks(source, ctx.author.id)
        except Exception as error:
            await ctx.send(f"Could not queue track(s): `{error}`")
            return

    queue = MUSIC_QUEUES[ctx.guild.id]
    queue.extend(tracks)

    if len(tracks) == 1:
        await ctx.send(f"Queued: **{tracks[0].title}**")
    else:
        extra = f" from **{label}**" if label else ""
        await ctx.send(f"Queued `{len(tracks)}` tracks{extra}.")

    if not vc.is_playing() and not vc.is_paused():
        await play_next_track(ctx.guild)


@bot.command(name="skip")
async def skip_music(ctx: commands.Context) -> None:
    vc = ctx.guild.voice_client
    if vc is None or not vc.is_connected():
        await ctx.send("I am not in a voice channel.")
        return
    if not in_same_voice_channel(ctx):
        await ctx.send("You must be in my voice channel to use this command.")
        return
    if not vc.is_playing() and not vc.is_paused():
        await ctx.send("Nothing is currently playing.")
        return
    vc.stop()
    await ctx.send("Skipped current track.")


@bot.command(name="pause")
async def pause_music(ctx: commands.Context) -> None:
    vc = ctx.guild.voice_client
    if vc is None or not vc.is_playing():
        await ctx.send("Nothing is currently playing.")
        return
    if not in_same_voice_channel(ctx):
        await ctx.send("You must be in my voice channel to use this command.")
        return
    vc.pause()
    await ctx.send("Paused playback.")


@bot.command(name="resume")
async def resume_music(ctx: commands.Context) -> None:
    vc = ctx.guild.voice_client
    if vc is None or not vc.is_paused():
        await ctx.send("Playback is not paused.")
        return
    if not in_same_voice_channel(ctx):
        await ctx.send("You must be in my voice channel to use this command.")
        return
    vc.resume()
    await ctx.send("Resumed playback.")


@bot.command(name="stop")
async def stop_music(ctx: commands.Context) -> None:
    vc = ctx.guild.voice_client
    if vc is None or not vc.is_connected():
        await ctx.send("I am not in a voice channel.")
        return
    if not in_same_voice_channel(ctx):
        await ctx.send("You must be in my voice channel to use this command.")
        return
    MUSIC_QUEUES[ctx.guild.id].clear()
    MUSIC_NOW_PLAYING.pop(ctx.guild.id, None)
    if vc.is_playing() or vc.is_paused():
        vc.stop()
    await ctx.send("Stopped playback and cleared queue.")


@bot.command(name="queue", aliases=["q"])
async def queue_music(ctx: commands.Context) -> None:
    now_playing = MUSIC_NOW_PLAYING.get(ctx.guild.id)
    queue = MUSIC_QUEUES.get(ctx.guild.id, deque())
    if not now_playing and not queue:
        await ctx.send("Queue is empty.")
        return

    lines: list[str] = []
    if now_playing:
        lines.append(f"Now: **{now_playing.title}**")
    if queue:
        for i, track in enumerate(list(queue)[:10], start=1):
            lines.append(f"{i}. {track.title}")
        if len(queue) > 10:
            lines.append(f"...and {len(queue) - 10} more.")
    await ctx.send("\n".join(lines))


@bot.command(name="nowplaying", aliases=["np"])
async def now_playing_music(ctx: commands.Context) -> None:
    current = MUSIC_NOW_PLAYING.get(ctx.guild.id)
    if current is None:
        await ctx.send("Nothing is currently playing.")
        return
    await ctx.send(f"Now playing: **{current.title}**\n{current.webpage_url}")


@bot.command(name="aimodel")
async def aimodel_command(ctx: commands.Context) -> None:
    provider = "Groq" if AI_PROVIDER == "groq" else "OpenRouter"
    model_text = current_ai_model() or "(not set)"
    fallbacks = current_ai_fallback_models()
    fallback_text = ", ".join(fallbacks) if fallbacks else "(none)"
    await ctx.send(
        f"Provider: `{provider}`\n"
        f"Configured model: `{model_text}`\n"
        f"Fallbacks: `{fallback_text}`"
    )


@bot.command(name="aimodels")
async def aimodels_command(ctx: commands.Context, limit: int = 15) -> None:
    if limit < 1 or limit > 40:
        await ctx.send("`limit` must be between `1` and `40`.")
        return
    if not is_ai_configured():
        await ctx.send(ai_setup_message())
        return

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            if AI_PROVIDER == "groq":
                available = await fetch_groq_models(session)
            else:
                available = await fetch_openrouter_models(session)
        except Exception as error:
            await ctx.send(f"Failed to fetch models: `{error}`")
            return

    listed = sorted(available)
    if AI_PROVIDER == "openrouter":
        listed = [model for model in listed if model.endswith(":free")]
        if not listed:
            await ctx.send("No `:free` OpenRouter models found right now.")
            return

    if not listed:
        await ctx.send("No models found right now.")
        return

    shown = listed[:limit]
    provider_label = "Groq" if AI_PROVIDER == "groq" else "OpenRouter free"
    text = f"Available {provider_label} models:\n" + "\n".join(f"- `{model}`" for model in shown)
    if len(listed) > limit:
        text += f"\n...and `{len(listed) - limit}` more."
    await send_chunked(ctx, text)


@bot.command(name="aireset")
async def aireset_command(ctx: commands.Context) -> None:
    AI_CHAT_CACHE.pop(ctx.channel.id, None)
    for key in list(CONVERSATIONAL_AI_CACHE.keys()):
        if key[0] == ctx.channel.id:
            CONVERSATIONAL_AI_CACHE.pop(key, None)
    for key in list(PSYCH_SESSIONS.keys()):
        if key[0] == ctx.channel.id:
            stop_psych_session(key[0], key[1])
    for key in list(PSYCH_PENDING_TASKS.keys()):
        if key[0] == ctx.channel.id:
            cancel_psych_flush(key[0], key[1])
    await ctx.send("AI memory has been cleared for this channel.", delete_after=6)


@bot.command(name="psych")
async def psych_command(ctx: commands.Context, *, input_text: str | None = None) -> None:
    action, seed = parse_psych_action_and_seed(input_text)
    await run_psych_action_for_user(
        ctx.channel,
        channel_id=ctx.channel.id,
        user_id=ctx.author.id,
        user_display_name=get_user_display_name(ctx.author),
        action=action,
        seed_text=seed,
    )


@bot.command(name="myvibe")
@commands.cooldown(2, 60, commands.BucketType.user)
@commands.guild_only()
async def my_vibe_command(ctx: commands.Context, count: int = VIBE_DEFAULT_MESSAGE_COUNT) -> None:
    if await refuse_fun_excluded(ctx, ctx.author):
        return
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    if not is_ai_configured():
        await ctx.send(ai_setup_message())
        return
    if count < VIBE_MIN_REQUIRED_MESSAGES or count > VIBE_MAX_MESSAGE_COUNT:
        await ctx.send(
            f"`count` must be between `{VIBE_MIN_REQUIRED_MESSAGES}` and `{VIBE_MAX_MESSAGE_COUNT}`."
        )
        return

    async with ctx.typing():
        user_messages, replies_received = await collect_vibe_context(ctx.channel, ctx.author.id, count)
        if len(user_messages) < VIBE_MIN_REQUIRED_MESSAGES:
            await ctx.send(
                f"Need at least `{VIBE_MIN_REQUIRED_MESSAGES}` of your recent messages in this channel."
            )
            return
        try:
            report = await generate_vibe_report(ctx.author, user_messages, replies_received)
        except Exception as error:
            print(f"[VIBE ERROR] {error}")
            report = generate_vibe_report_local(ctx.author, user_messages, replies_received)
            report = (
                f"{report}\n\n"
                "_AI model timed out, so this report is from local heuristics._"
            )

    await send_chunked(
        ctx,
        (
            f"**Vibe Report for {ctx.author.display_name}**\n"
            f"(Fun feature, may be inaccurate. Based on `{len(user_messages)}` user messages "
            f"and `{len(replies_received)}` replies in this channel.)\n\n"
            f"{report}"
        ),
    )


@bot.command(name="vibe")
@commands.cooldown(2, 60, commands.BucketType.user)
@commands.guild_only()
async def vibe_command(
    ctx: commands.Context, member: discord.Member, count: int = VIBE_DEFAULT_MESSAGE_COUNT
) -> None:
    if await refuse_fun_excluded(ctx, member):
        return
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    if member.bot:
        await ctx.send("Bot accounts are not supported for vibe reports.")
        return
    if not is_ai_configured():
        await ctx.send(ai_setup_message())
        return
    if count < VIBE_MIN_REQUIRED_MESSAGES or count > VIBE_MAX_MESSAGE_COUNT:
        await ctx.send(
            f"`count` must be between `{VIBE_MIN_REQUIRED_MESSAGES}` and `{VIBE_MAX_MESSAGE_COUNT}`."
        )
        return

    async with ctx.typing():
        user_messages, replies_received = await collect_vibe_context(ctx.channel, member.id, count)
        if len(user_messages) < VIBE_MIN_REQUIRED_MESSAGES:
            await ctx.send(
                f"Need at least `{VIBE_MIN_REQUIRED_MESSAGES}` recent messages from {member.mention} "
                "in this channel."
            )
            return
        try:
            report = await generate_vibe_report(member, user_messages, replies_received)
        except Exception as error:
            print(f"[VIBE ERROR] {error}")
            report = generate_vibe_report_local(member, user_messages, replies_received)
            report = (
                f"{report}\n\n"
                "_AI model timed out, so this report is from local heuristics._"
            )

    await send_chunked(
        ctx,
        (
            f"**Vibe Report for {member.display_name}**\n"
            f"(Fun feature, may be inaccurate. Based on `{len(user_messages)}` user messages "
            f"and `{len(replies_received)}` replies in this channel.)\n\n"
            f"{report}"
        ),
    )


@bot.command(name="vibecheck")
@commands.cooldown(2, 60, commands.BucketType.user)
@commands.guild_only()
async def vibecheck_command(ctx: commands.Context, member: discord.Member) -> None:
    if await refuse_fun_excluded(ctx, member):
        return
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    if member.bot:
        await ctx.send("Bot accounts are not supported for vibe checks.")
        return
    if not is_ai_configured():
        await ctx.send(ai_setup_message())
        return

    target_count = 200
    async with ctx.typing():
        user_messages, replies_received = await collect_vibe_context(ctx.channel, member.id, target_count)
        if len(user_messages) < VIBE_MIN_REQUIRED_MESSAGES:
            await ctx.send(
                f"Need at least `{VIBE_MIN_REQUIRED_MESSAGES}` recent messages from {member.mention} "
                "in this channel."
            )
            return

        try:
            report = await generate_vibecheck_report(member, user_messages, replies_received)
        except Exception as error:
            print(f"[VIBECHECK ERROR] {error}")
            report = generate_vibecheck_local(user_messages, replies_received)
            report = normalize_vibecheck_output(report)

    await send_chunked(ctx, report)


@bot.hybrid_command(name="roast")
@commands.cooldown(2, 45, commands.BucketType.user)
@commands.guild_only()
async def roast_command(
    ctx: commands.Context,
    member: discord.Member,
    style: Literal["soft", "friendly", "brutal"] = "friendly",
) -> None:
    if await refuse_fun_excluded(ctx, member):
        return
    if member.bot:
        await ctx.send("I do not roast bot accounts.")
        return
    if not await enforce_fun_rate_limit_ctx(ctx):
        return

    requested_style = style
    effective_style = resolve_style_for_fun_mode(ctx.guild.id, requested_style)
    cache_key = (ctx.guild.id, member.id, effective_style)
    now = time.monotonic()
    cached = ROAST_RESULT_CACHE.get(cache_key)
    if cached and now - cached[0] < ROAST_CACHE_SECONDS:
        await send_chunked(ctx, cached[1] + "\n\n_(Cached result to reduce API load)_")
        return

    scan_lock = ROAST_LOCKS[(ctx.guild.id, member.id)]
    if scan_lock.locked():
        await ctx.send("Personal roast scan already running for that user. Try again in a few seconds.")
        return

    async with ctx.typing():
        async with scan_lock:
            fresh_cached = ROAST_RESULT_CACHE.get(cache_key)
            if fresh_cached and time.monotonic() - fresh_cached[0] < ROAST_CACHE_SECONDS:
                await send_chunked(ctx, fresh_cached[1] + "\n\n_(Cached result to reduce API load)_")
                return

            context = await collect_roast_context(ctx.guild, member.id)
            if context.message_count < 6:
                await ctx.send(
                    f"Not enough visible history for {member.mention}. I need a few more messages across readable channels."
                )
                return

            recent_outputs = get_recent_roast_outputs(ctx.guild.id, member.id, effective_style)
            prompt = build_personal_roast_prompt(
                member,
                effective_style,
                context,
                recent_outputs=recent_outputs,
            )

            if is_ai_configured():
                fun_mode = get_guild_fun_mode(ctx.guild.id)
                try:
                    roast = await request_fun_ai(
                        prompt,
                        max_tokens=240,
                        temperature=0.9,
                        policy_key="roast",
                        fun_mode=fun_mode,
                    )
                    if any(roast.strip() == previous.strip() for previous in recent_outputs):
                        roast = await request_fun_ai(
                            prompt
                            + "\nGenerate a clearly different roast structure from prior outputs.",
                            max_tokens=240,
                            temperature=0.95,
                            policy_key="roast",
                            fun_mode=fun_mode,
                        )
                except Exception as error:
                    print(f"[ROAST ERROR] {error}")
                    roast = generate_personal_roast_local(member, effective_style, context)
            else:
                roast = generate_personal_roast_local(member, effective_style, context)

            remember_roast_output(ctx.guild.id, member.id, effective_style, roast)
            style_label = effective_style
            if effective_style != requested_style:
                style_label += " (auto-adjusted by fun mode)"
            cta = roast_engagement_cta(get_guild_fun_mode(ctx.guild.id))
            result = (
                f"[ROAST] mode: **{style_label}** for {member.mention}\n"
                f"{roast}\n\n"
                f"Based on `{context.message_count}` messages across readable channels.\n"
                f"Engagement prompt: {cta}\n"
                "[For fun only]"
            )
            ROAST_RESULT_CACHE[cache_key] = (time.monotonic(), result)

    await send_chunked(ctx, result)

@bot.hybrid_command(name="serverlore")
@commands.cooldown(2, 60, commands.BucketType.user)
@commands.guild_only()
async def serverlore_command(ctx: commands.Context) -> None:
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    if not is_ai_configured():
        await ctx.send(ai_setup_message())
        return

    async with ctx.typing():
        transcript = await collect_recent_channel_transcript(ctx.channel, 140)
        if len(transcript) < 12:
            await ctx.send("Need more recent chat context in this channel for server lore.")
            return
        prompt = (
            "Write a dramatic fake mythology story for this Discord server.\n"
            "Include title, a rise/fall arc, and 3 mythic events. Make it addictive and funny.\n"
            "Keep it under 260 words.\n\n"
            f"Server: {ctx.guild.name}\n"
            "Recent chat context:\n"
            + "\n".join(transcript[-90:])
        )
        try:
            lore = await request_fun_ai(
                prompt,
                max_tokens=320,
                temperature=0.95,
                policy_key="serverlore",
            )
        except Exception as error:
            print(f"[SERVERLORE ERROR] {error}")
            await ctx.send(friendly_ai_error(error))
            return
    await send_chunked(ctx, f"ðŸ“œ **Server Lore**\n{lore}\n\nâš ï¸ For fun only.")


@bot.hybrid_command(name="replycraft")
@commands.cooldown(2, 25, commands.BucketType.user)
@commands.guild_only()
async def replycraft_command(ctx: commands.Context, message_link: str | None = None) -> None:
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    source_message = await resolve_message_from_context(ctx, message_link)
    if source_message is None:
        await ctx.send(
            f"Reply to a message and run `{PREFIX}replycraft`, or pass a Discord message link."
        )
        return

    cache_key = (ctx.guild.id, "replycraft", ctx.author.id, source_message.id)
    cached = SOCIALINTEL_RESULT_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < SOCIALINTEL_CACHE_SECONDS:
        await send_chunked(ctx, cached[1] + "\n\n_(Cached result for speed)_")
        return

    async with ctx.typing():
        requester_context = collect_socialintel_context(ctx.guild, ctx.author)
        if requester_context.target_message_count < 10 or _socialintel_needs_backfill(ctx.guild.id):
            await maybe_run_socialintel_backfill(ctx.guild)
            requester_context = collect_socialintel_context(ctx.guild, ctx.author)
        requester_metrics = requester_context.target_metrics
        recent_entries = await _socialintel_message_neighborhood(source_message)
        payload = await _socialintel_generate_replycraft(
            source_message,
            requester_metrics=requester_metrics,
            recent_entries=recent_entries,
        )

    sparse_reasons: list[str] = []
    if requester_context.target_message_count < 12:
        sparse_reasons.append("limited visible history for your style fingerprint")
    if len(recent_entries) < 4:
        sparse_reasons.append("very little nearby channel context")
    confidence_note = payload.get("confidence_note", "").strip() or "Built from visible evidence only."
    if sparse_reasons:
        confidence_note += " Sparse-evidence note: " + "; ".join(sparse_reasons) + "."
    source_excerpt = _socialintel_compact_excerpt(source_message.clean_content or "[attachment]", 150)
    result = (
        f"[REPLYCRAFT]\n"
        f"Target: {get_user_display_name(source_message.author)} in {_socialintel_channel_label(source_message.channel)}\n"
        f"Context seed: `{source_excerpt}`\n"
        f"1. safe [{payload.get('safe_tone', 'measured')}]: {payload.get('safe_reply', '').strip()}\n"
        f"2. playful [{payload.get('playful_tone', 'light banter')}]: {payload.get('playful_reply', '').strip()}\n"
        f"3. bold [{payload.get('bold_tone', 'direct')}]: {payload.get('bold_reply', '').strip()}\n"
        f"Confidence: {confidence_note}"
    )
    SOCIALINTEL_RESULT_CACHE[cache_key] = (time.monotonic(), result)
    await send_chunked(ctx, result)


@bot.hybrid_command(name="duofit")
@commands.cooldown(2, 35, commands.BucketType.user)
@commands.guild_only()
async def duofit_command(
    ctx: commands.Context,
    member_one: discord.Member,
    member_two: discord.Member,
) -> None:
    if member_one.bot or member_two.bot or member_one.id == member_two.id:
        await ctx.send("Choose two different non-bot members.")
        return
    if not await enforce_fun_rate_limit_ctx(ctx):
        return

    left_id, right_id = sorted((member_one.id, member_two.id))
    cache_key = (ctx.guild.id, "duofit", left_id, right_id)
    cached = SOCIALINTEL_RESULT_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < SOCIALINTEL_CACHE_SECONDS:
        await send_chunked(ctx, cached[1] + "\n\n_(Cached result for speed)_")
        return

    async with ctx.typing():
        await maybe_run_socialintel_backfill(ctx.guild)
        context = collect_socialintel_context(ctx.guild, member_one)
        candidate_row = context.candidate_rows.get(member_two.id)
        if candidate_row is None:
            guild_state = get_guild_socialintel_state(ctx.guild.id)
            users = guild_state.get("users", {}) if isinstance(guild_state.get("users"), dict) else {}
            candidate_row = users.get(str(member_two.id)) if isinstance(users.get(str(member_two.id)), dict) else None
        duo_row = (
            _socialintel_build_duo_row(ctx.guild, member_one, member_two.id, candidate_row, context)
            if isinstance(candidate_row, dict)
            else None
        )
        if duo_row is None:
            await ctx.send(
                "Not enough evidence yet. I need more visible history from both members across readable channels."
            )
            return
        annotate_socialintel_duo_confidences([duo_row], context.target_message_count)

    score_pct = _socialintel_duo_score_percent(float(duo_row.get("heuristic_score", 0.0)))
    pair_stats = duo_row.get("pair_stats", {}) if isinstance(duo_row.get("pair_stats"), dict) else {}
    reasons = _socialintel_duo_reason_bits(ctx.guild, duo_row)
    common_channels = _altfinder_channel_names(ctx.guild, duo_row.get("common_channel_ids", []))
    common_hours = _altfinder_format_hours(duo_row.get("common_hours", []))
    coverage = _socialintel_scan_coverage(ctx.guild.id)
    result = (
        f"[DUOFIT] {member_one.mention} x {member_two.mention}\n"
        f"Compatibility score: `{score_pct}%` | confidence `{int(float(duo_row.get('confidence', 0.0)) * 100)}%` ({duo_row.get('confidence_band', 'low')})\n"
        f"- Style fit: `{float(duo_row.get('style_similarity', 0.0)):.2f}`\n"
        f"- Schedule overlap: `{float(duo_row.get('schedule_overlap', 0.0)):.2f}` | common hours `{common_hours}`\n"
        f"- Channel overlap: `{float(duo_row.get('channel_overlap', 0.0)):.2f}` | common channels `{common_channels}`\n"
        f"- Topic fit: `{float(duo_row.get('topic_overlap', 0.0)):.2f}`\n"
        f"- Pacing fit: `{float(duo_row.get('pacing_similarity', 0.0)):.2f}`\n"
        f"- Reply chemistry: `{int(pair_stats.get('reply_forward', 0) or 0) + int(pair_stats.get('reply_back', 0) or 0)}` mutual replies | "
        f"`{int(pair_stats.get('mention_forward', 0) or 0) + int(pair_stats.get('mention_back', 0) or 0)}` mutual mentions\n"
        f"- Presence overlap: `{float(duo_row.get('presence_overlap', 0.0)):.2f}`\n"
        f"Evidence summary: {', '.join(reasons) if reasons else 'light overlap only'}\n"
        f"Coverage: channels `{coverage.get('channels_fully_scanned', 0)}/{coverage.get('channels_total', 0)}` | indexed msgs `{coverage.get('messages_indexed', 0)}`\n"
        "Guardrail: this is a friendship, teamwork, or debate-chemistry fit signal only; not romance inference."
    )
    SOCIALINTEL_RESULT_CACHE[cache_key] = (time.monotonic(), result)
    await send_chunked(ctx, result)


@bot.hybrid_command(name="duofind")
@commands.cooldown(2, 45, commands.BucketType.user)
@commands.guild_only()
async def duofind_command(ctx: commands.Context, member: discord.Member | None = None) -> None:
    target = member or ctx.author
    if target.bot:
        await ctx.send("Choose a non-bot member.")
        return
    if not await enforce_fun_rate_limit_ctx(ctx):
        return

    cache_key = (ctx.guild.id, "duofind", target.id)
    cached = SOCIALINTEL_RESULT_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < SOCIALINTEL_CACHE_SECONDS:
        await send_chunked(ctx, cached[1] + "\n\n_(Cached result for speed)_")
        return

    async with ctx.typing():
        await maybe_run_socialintel_backfill(ctx.guild)
        context = collect_socialintel_context(ctx.guild, target)
        if context.target_message_count < 8:
            await ctx.send(
                f"Not enough evidence yet for {target.mention}. I need more visible history first."
            )
            return
        candidate_pool = build_socialintel_duo_candidate_pool(
            ctx.guild,
            target,
            context,
            limit=max(7, SOCIALINTEL_MAX_RESULTS),
        )
        if not candidate_pool:
            await ctx.send(
                f"Not enough evidence yet for {target.mention}. No strong compatibility candidates were visible."
            )
            return
        annotate_socialintel_duo_confidences(candidate_pool, context.target_message_count)
        ranked_ids = await rerank_socialintel_duo_candidates_with_ai(
            target,
            candidates=candidate_pool,
        )
        ranked_rows = _socialintel_apply_rank_order(candidate_pool, ranked_ids)[:SOCIALINTEL_MAX_RESULTS]

    lines: list[str] = []
    for index, row in enumerate(ranked_rows[:5], start=1):
        reasons = _socialintel_duo_reason_bits(ctx.guild, row)
        lines.append(
            f"{index}. {row['display_label']} | score `{_socialintel_duo_score_percent(float(row.get('heuristic_score', 0.0)))}%` | "
            f"confidence `{int(float(row.get('confidence', 0.0)) * 100)}%` ({row.get('confidence_band', 'low')}) | "
            f"{', '.join(reasons) if reasons else 'light overlap only'}"
        )
    coverage = _socialintel_scan_coverage(ctx.guild.id)
    result = (
        f"[DUOFIND] for {target.mention}\n"
        + "\n".join(lines)
        + f"\nCoverage: channels `{coverage.get('channels_fully_scanned', 0)}/{coverage.get('channels_total', 0)}` | indexed msgs `{coverage.get('messages_indexed', 0)}`\n"
        + "Guardrail: this ranks friendship, teamwork, or debate compatibility only. Shared-channel-only overlap is capped to low or medium confidence."
    )
    SOCIALINTEL_RESULT_CACHE[cache_key] = (time.monotonic(), result)
    await send_chunked(ctx, result)


@bot.hybrid_command(name="threadrevive")
@commands.cooldown(2, 30, commands.BucketType.user)
@commands.guild_only()
async def threadrevive_command(ctx: commands.Context, target: str | None = None) -> None:
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    resolved = resolve_channel_or_thread(ctx.guild, target, default_channel=ctx.channel)
    if not isinstance(resolved, (discord.TextChannel, discord.Thread)):
        await ctx.send(
            f"Usage: `{PREFIX}threadrevive`, `{PREFIX}threadrevive #channel`, or `{PREFIX}threadrevive <thread-name>`."
        )
        return

    cache_key = (ctx.guild.id, "threadrevive", resolved.id)
    cached = SOCIALINTEL_RESULT_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < SOCIALINTEL_CACHE_SECONDS:
        await send_chunked(ctx, cached[1] + "\n\n_(Cached result for speed)_")
        return

    async with ctx.typing():
        guild_state = get_guild_socialintel_state(ctx.guild.id)
        row = _socialintel_get_channel_row(guild_state, resolved)
        prompts = _socialintel_build_threadrevive_prompts(row, limit=3)
        if not prompts and _socialintel_needs_backfill(ctx.guild.id):
            await maybe_run_socialintel_backfill(ctx.guild)
            guild_state = get_guild_socialintel_state(ctx.guild.id)
            row = _socialintel_get_channel_row(guild_state, resolved)
            prompts = _socialintel_build_threadrevive_prompts(row, limit=3)
        if not prompts:
            await ctx.send(
                f"Not enough evidence yet in {_socialintel_channel_label(resolved)}. I could not find a grounded unresolved question or conflict."
            )
            return

    focus_kind, focus_text = _socialintel_thread_focus(row)
    topic_words = _socialintel_counter_labels(
        row.get("recent_topics", {}) if isinstance(row.get("recent_topics"), dict) else {},
        limit=4,
    )
    evidence_note = (
        f"Built from the last {focus_kind or 'visible'} signal plus recent topics: "
        f"{', '.join(topic_words) if topic_words else 'limited topic evidence'}."
    )
    result = (
        f"[THREADREVIVE] {_socialintel_channel_label(resolved)}\n"
        f"Focus: `{_socialintel_compact_excerpt(focus_text, 160)}`\n"
        f"1. {prompts[0]}\n"
        f"2. {prompts[1] if len(prompts) > 1 else prompts[0]}\n"
        f"3. {prompts[2] if len(prompts) > 2 else prompts[-1]}\n"
        f"Evidence note: {evidence_note}"
    )
    SOCIALINTEL_RESULT_CACHE[cache_key] = (time.monotonic(), result)
    await send_chunked(ctx, result)


@bot.hybrid_command(name="jumpin")
@commands.cooldown(2, 35, commands.BucketType.user)
@commands.guild_only()
async def jumpin_command(ctx: commands.Context, member: discord.Member | None = None) -> None:
    target = member or ctx.author
    if target.bot:
        await ctx.send("Choose a non-bot member.")
        return
    if not await enforce_fun_rate_limit_ctx(ctx):
        return

    cache_key = (ctx.guild.id, "jumpin", target.id)
    cached = SOCIALINTEL_RESULT_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < 90:
        await send_chunked(ctx, cached[1] + "\n\n_(Cached result for speed)_")
        return

    async with ctx.typing():
        if _socialintel_needs_backfill(ctx.guild.id):
            await maybe_run_socialintel_backfill(ctx.guild)
        rows = await _socialintel_build_jumpin_rows(ctx.guild, target)
        if not rows:
            await ctx.send(
                f"Not enough evidence yet for {target.mention}. I need more visible history or more active channels."
            )
            return

    lines: list[str] = []
    for index, row in enumerate(rows, start=1):
        channel = row["channel"]
        lines.append(
            f"{index}. {_socialintel_channel_label(channel)} | score `{int(min(99, float(row.get('score', 0.0)) * 20))}`\n"
            f"Reason: {row['reason']}\n"
            f"Opener: {row['opener']}"
        )
    result = f"[JUMPIN] for {target.mention}\n" + "\n".join(lines)
    SOCIALINTEL_RESULT_CACHE[cache_key] = (time.monotonic(), result)
    await send_chunked(ctx, result)


@bot.hybrid_command(name="driftcheck")
@commands.cooldown(2, 45, commands.BucketType.user)
@commands.guild_only()
async def driftcheck_command(ctx: commands.Context, member: discord.Member) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can use `driftcheck`.")
        return
    if member.bot:
        await ctx.send("Choose a non-bot member.")
        return

    cache_key = (ctx.guild.id, "driftcheck", member.id)
    cached = SOCIALINTEL_RESULT_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < SOCIALINTEL_CACHE_SECONDS:
        await send_chunked(ctx, cached[1] + "\n\n_(Cached result for speed)_")
        return

    async with ctx.typing():
        await maybe_run_socialintel_backfill(ctx.guild)
        report = await _socialintel_build_driftcheck_report(ctx.guild, member)
        if report is None:
            await ctx.send(
                f"Not enough evidence yet for {member.mention}. I need a stronger recent-vs-baseline sample."
            )
            return

    baseline_metrics = report["baseline_metrics"]
    recent_metrics = report["recent_metrics"]
    result = (
        f"[DRIFTCHECK] for {member.mention}\n"
        f"Anomaly score: `{int(float(report['anomaly_score']) * 100)}%` ({report['band']})\n"
        f"Comparison windows: recent `{report['recent_count']}` msgs vs baseline `{report['baseline_count']}` msgs\n"
        f"- Style drift: `{float(report['style_drift']):.2f}` | avg len `{float(baseline_metrics.get('avg_len', 0.0)):.1f} -> {float(recent_metrics.get('avg_len', 0.0)):.1f}` | emoji/msg `{float(baseline_metrics.get('emoji_per_msg', 0.0)):.2f} -> {float(recent_metrics.get('emoji_per_msg', 0.0)):.2f}`\n"
        f"- Activity-time drift: `{float(report['activity_drift']):.2f}` | baseline hours `{_socialintel_recent_peak_label(baseline_metrics.get('active_hours', {}), kind='hours')}` | recent `{_socialintel_recent_peak_label(recent_metrics.get('active_hours', {}), kind='hours')}`\n"
        f"- Channel drift: `{float(report['channel_drift']):.2f}` | baseline `{_socialintel_channel_names_from_counter(ctx.guild, baseline_metrics.get('top_channels', {}))}` | recent `{_socialintel_channel_names_from_counter(ctx.guild, recent_metrics.get('top_channels', {}))}`\n"
        f"- Interaction-target drift: `{float(report['interaction_drift']):.2f}` | baseline `{_socialintel_target_names_from_counter(ctx.guild, baseline_metrics.get('reply_targets', {}))}` | recent `{_socialintel_target_names_from_counter(ctx.guild, recent_metrics.get('reply_targets', {}))}`\n"
        f"- Presence drift: `{float(report['presence_drift']):.2f}` | current status `{report['current_status']}`\n"
        f"- Profile drift: `{float(report['profile_drift']):.2f}` | {report['profile_note']}\n"
        "Caution: Behavioral anomaly only from visible activity; not proof of compromise or account sharing."
    )
    SOCIALINTEL_RESULT_CACHE[cache_key] = (time.monotonic(), result)
    await send_chunked(ctx, result)


@bot.hybrid_command(name="arcreport")
@commands.cooldown(2, 45, commands.BucketType.user)
@commands.guild_only()
async def arcreport_command(
    ctx: commands.Context,
    target: str | None = None,
    hours: int = 6,
) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can use `arcreport`.")
        return
    resolved = resolve_channel_or_thread(ctx.guild, target, default_channel=ctx.channel)
    if not isinstance(resolved, (discord.TextChannel, discord.Thread)):
        await ctx.send(
            f"Usage: `{PREFIX}arcreport #channel` or `{PREFIX}arcreport #channel 6`."
        )
        return
    hours = max(1, min(hours, 72))

    cache_key = (ctx.guild.id, "arcreport", resolved.id, hours)
    cached = SOCIALINTEL_RESULT_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < 120:
        await send_chunked(ctx, cached[1] + "\n\n_(Cached result for speed)_")
        return

    cutoff_dt = _utc_now() - timedelta(hours=hours)
    async with ctx.typing():
        if isinstance(resolved, discord.TextChannel):
            entries = await get_channel_window_cached(
                resolved,
                after=cutoff_dt,
                scan_limit=max(120, min(720, hours * 120)),
                cache_ttl_seconds=90,
                include_attachment_marker=True,
            )
        else:
            entries = await collect_messageable_window(
                resolved,
                limit=max(120, min(720, hours * 120)),
                after=cutoff_dt,
            )
        report = _socialintel_arc_report_lines(ctx.guild, entries)
        if report is None:
            await ctx.send(
                f"Not enough evidence yet in {_socialintel_channel_label(resolved)} over the last `{hours}` hour(s)."
            )
            return

    starter = report["starter"]
    stamp = datetime.fromtimestamp(starter.created_at_ts, tz=_safe_zoneinfo(get_guild_engagement_timezone(ctx.guild.id))).strftime("%H:%M")
    guild_state = get_guild_socialintel_state(ctx.guild.id)
    channel_row = _socialintel_get_channel_row(guild_state, resolved)
    focus_kind, focus_text = _socialintel_thread_focus(channel_row)
    unresolved = list(report["unresolved"])
    if focus_text and all(focus_text not in item for item in unresolved):
        unresolved.insert(0, _socialintel_compact_excerpt(focus_text, 120))
    result = (
        f"[ARCREPORT] {_socialintel_channel_label(resolved)} over last `{hours}`h\n"
        f"Likely starter: {_socialintel_author_label(ctx.guild, starter.author_id)} at `{stamp}` - `{_socialintel_compact_excerpt(starter.content, 120)}`\n"
        f"Escalators: {', '.join(report['escalators']) if report['escalators'] else 'none strong enough to call'}\n"
        f"De-escalators: {', '.join(report['deescalators']) if report['deescalators'] else 'none clearly visible'}\n"
        f"Conversation pivots:\n" + ("\n".join(f"- {line}" for line in report["pivots"]) if report["pivots"] else "- none clearly visible")
        + "\nUnresolved points:\n"
        + ("\n".join(f"- `{item}`" for item in unresolved[:3]) if unresolved else "- none clearly visible")
        + "\nEvidence snippets:\n"
        + ("\n".join(f"- {line}" for line in report["evidence_lines"]) if report["evidence_lines"] else "- none captured")
        + "\nTone: factual moderation summary only; not a punishment recommendation."
    )
    SOCIALINTEL_RESULT_CACHE[cache_key] = (time.monotonic(), result)
    await send_chunked(ctx, result)


@bot.hybrid_command(name="altfinder")
@commands.cooldown(2, 90, commands.BucketType.user)
@commands.guild_only()
async def altfinder_command(ctx: commands.Context, member: discord.Member) -> None:
    if member.bot:
        await ctx.send("Bot accounts are not valid AltFinder targets.")
        return
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can use `altfinder`.")
        return

    cache_key = (ctx.guild.id, member.id)
    guild_altfinder_state = get_guild_altfinder_state(ctx.guild.id)
    channels_state = guild_altfinder_state.get("channels", {})
    channels_total = len(channels_state) if isinstance(channels_state, dict) else 0
    channels_fully_scanned = 0
    if isinstance(channels_state, dict):
        channels_fully_scanned = sum(
            1
            for row in channels_state.values()
            if isinstance(row, dict) and bool(row.get("fully_scanned"))
        )
    meta = guild_altfinder_state.get("meta", {})
    last_backfill_ts = float(meta.get("last_backfill_ts", 0.0) or 0.0) if isinstance(meta, dict) else 0.0
    cache_allowed = channels_total > 0 and channels_fully_scanned >= channels_total and last_backfill_ts > 0
    cached = ALTFINDER_RESULT_CACHE.get(cache_key)
    if cache_allowed and cached and time.monotonic() - cached[0] < ALTFINDER_CACHE_SECONDS:
        await send_chunked(ctx, cached[1] + "\n\n_(Cached result after full-history scan)_")
        return

    scan_lock = ALTFINDER_LOCKS[cache_key]
    if scan_lock.locked():
        await ctx.send("`altfinder` scan already running for that user. Try again shortly.")
        return

    async with ctx.typing():
        async with scan_lock:
            fresh_cached = ALTFINDER_RESULT_CACHE.get(cache_key)
            if cache_allowed and fresh_cached and time.monotonic() - fresh_cached[0] < ALTFINDER_CACHE_SECONDS:
                await send_chunked(ctx, fresh_cached[1] + "\n\n_(Cached result after full-history scan)_")
                return

            backfill_summary = await run_altfinder_backfill(
                ctx.guild,
                message_budget=ALTFINDER_COMMAND_MAX_BACKFILL_MESSAGES,
                time_budget_seconds=ALTFINDER_COMMAND_MAX_BACKFILL_SECONDS,
            )
            context = collect_altfinder_context(ctx.guild, member)
            candidate_pool = build_altfinder_candidate_pool(
                ctx.guild,
                member,
                context,
                limit=max(ALTFINDER_MAX_RESULTS, 5),
            )
            ranked_ids = await rerank_altfinder_candidates_with_ai(
                member,
                context=context,
                candidates=candidate_pool,
            )
            ranked_rows = _altfinder_apply_rank_order(candidate_pool, ranked_ids)
            annotate_altfinder_confidences(ranked_rows, context.target_message_count)
            ranked_rows = ranked_rows[: max(ALTFINDER_MAX_RESULTS, 5)]

            coverage = context.scan_coverage
            coverage_line = (
                f"Coverage: channels `{coverage.get('channels_fully_scanned', 0)}/{coverage.get('channels_total', 0)}` | "
                f"indexed msgs `{coverage.get('messages_indexed', 0)}` | "
                f"target msgs `{context.target_message_count}` | "
                f"freshly scanned `{backfill_summary.get('scanned_messages', 0)}` in `{backfill_summary.get('passes', 0)}` passes"
            )
            weak_evidence = (
                not ranked_rows
                or float(ranked_rows[0].get("confidence", 0.0)) < 0.38
                or float(ranked_rows[0].get("evidence_density", 0.0)) < 0.18
                or context.target_message_count < 4
            )
            if weak_evidence:
                suspect_focus_lines = _altfinder_suspect_focus_lines(context.suspect_ids, ranked_rows)
                result = (
                    f"[ALT FINDER] for {member.display_name}\n"
                    "Not enough evidence yet after deep scan.\n"
                    + (
                        ("Suspect focus:\n" + "\n".join(suspect_focus_lines) + "\n")
                        if suspect_focus_lines
                        else ""
                    )
                    +
                    f"{coverage_line}\n"
                    "Inference only from visible metadata and chat behavior; not proof of shared ownership."
                )
                ALTFINDER_RESULT_CACHE[cache_key] = (time.monotonic(), result)
                await send_chunked(ctx, result)
                return

            summary = await build_altfinder_investigation_summary(
                member,
                ranked_rows=ranked_rows,
                context=context,
            )
            suspect_focus_lines = _altfinder_suspect_focus_lines(context.suspect_ids, ranked_rows)
            ranking_lines = [
                (
                    f"{index}. {row['display_label']} | confidence "
                    f"`{int(float(row.get('confidence', 0.0)) * 100)}%` ({row.get('confidence_band', 'low')}) | "
                    f"{row['scope_label']} | {_altfinder_short_evidence_summary(row)}"
                )
                for index, row in enumerate(ranked_rows[:ALTFINDER_MAX_RESULTS], start=1)
            ]
            detail_blocks = "\n\n".join(
                _altfinder_detailed_evidence_block(ctx.guild, row, context=context)
                for row in ranked_rows[:3]
            )
            result = (
                f"[ALT FINDER] for {member.display_name}\n"
                + (
                    ("Suspect focus:\n" + "\n".join(suspect_focus_lines) + "\n\n")
                    if suspect_focus_lines
                    else ""
                )
                + "Ranked shortlist:\n"
                + "\n".join(ranking_lines)
                + "\n\nInvestigation summary:\n"
                + summary
                + "\n\nDetailed evidence:\n"
                + detail_blocks
                + f"\n\n{coverage_line}\n"
                + "Inference only from visible metadata and chat behavior; not proof of shared ownership."
            )
            ALTFINDER_RESULT_CACHE[cache_key] = (time.monotonic(), result)

    await send_chunked(ctx, result)


@bot.hybrid_command(name="suspect")
@commands.cooldown(2, 20, commands.BucketType.user)
@commands.guild_only()
async def suspect_command(
    ctx: commands.Context,
    target: discord.Member,
    suspect1: discord.Member,
    suspect2: discord.Member | None = None,
    suspect3: discord.Member | None = None,
) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can use `suspect`.")
        return
    if target.bot:
        await ctx.send("Target must be a non-bot member.")
        return
    suspects_raw = [suspect1, suspect2, suspect3]
    suspects: list[discord.Member] = []
    for member in suspects_raw:
        if member is None or member.bot or member.id == target.id:
            continue
        if all(existing.id != member.id for existing in suspects):
            suspects.append(member)
        if len(suspects) >= ALTFINDER_MAX_SUSPECTS:
            break
    if not suspects:
        await ctx.send("Provide at least one valid non-bot suspect different from the target.")
        return
    set_altfinder_suspects(ctx.guild.id, target.id, [member.id for member in suspects])
    suspect_labels = ", ".join(member.mention for member in suspects)
    await ctx.send(
        f"Stored `{len(suspects)}` suspect account(s) for {target.mention}: {suspect_labels}\n"
        "AltFinder will compare these accounts first before the wider shortlist."
    )


@bot.hybrid_command(name="suspectshow")
@commands.cooldown(2, 10, commands.BucketType.user)
@commands.guild_only()
async def suspectshow_command(ctx: commands.Context, target: discord.Member) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can use `suspectshow`.")
        return
    suspect_ids = get_altfinder_suspects(ctx.guild.id, target.id)
    if not suspect_ids:
        await ctx.send(f"No suspects stored for {target.mention}.")
        return
    labels: list[str] = []
    for suspect_id in suspect_ids:
        suspect_member = ctx.guild.get_member(suspect_id)
        if suspect_member is not None:
            labels.append(suspect_member.mention)
        else:
            labels.append(f"`{suspect_id}`")
    await ctx.send(f"Suspects for {target.mention}: {', '.join(labels)}")


@bot.hybrid_command(name="suspectclear")
@commands.cooldown(2, 10, commands.BucketType.user)
@commands.guild_only()
async def suspectclear_command(ctx: commands.Context, target: discord.Member) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_moderator(ctx.author):
        await ctx.send("Only moderators can use `suspectclear`.")
        return
    clear_altfinder_suspects(ctx.guild.id, target.id)
    await ctx.send(f"Cleared stored suspects for {target.mention}.")


@bot.hybrid_command(name="analyze")
@commands.cooldown(2, 60, commands.BucketType.user)
@commands.guild_only()
async def analyze_command(ctx: commands.Context, member: discord.Member) -> None:
    if await refuse_fun_excluded(ctx, member):
        return
    if member.bot:
        await ctx.send("Bot accounts are not supported for analysis.")
        return
    if not await enforce_fun_rate_limit_ctx(ctx):
        return

    cache_key = (ctx.guild.id, member.id)
    now = time.monotonic()
    cached = ANALYZE_CACHE.get(cache_key)
    if cached and now - cached[0] < ANALYZE_CACHE_SECONDS:
        await send_chunked(ctx, cached[1] + "\n\n_(Cached result for speed)_")
        return

    lock = ANALYZE_LOCKS[cache_key]
    if lock.locked():
        await ctx.send("Analyze scan already running for that user. Try again in a few seconds.")
        return

    async with ctx.typing():
        async with lock:
            fresh_cached = ANALYZE_CACHE.get(cache_key)
            if fresh_cached and time.monotonic() - fresh_cached[0] < ANALYZE_CACHE_SECONDS:
                await send_chunked(ctx, fresh_cached[1] + "\n\n_(Cached result for speed)_")
                return

            user_messages, user_entries = await collect_recent_user_messages_guild(
                ctx.guild,
                member.id,
                260,
            )
            if len(user_messages) < 20:
                await ctx.send(
                    f"Need more visible messages from {member.mention} across readable channels."
                )
                return

            joined = " ".join(user_messages).lower()
            tokens = [tok.strip("'") for tok in WORD_PATTERN.findall(joined) if len(tok) > 2]
            filtered = [tok for tok in tokens if tok not in ROAST_STOP_WORDS]
            top_words = [word for word, _ in Counter(filtered).most_common(8)]
            avg_len = sum(len(msg) for msg in user_messages) / max(1, len(user_messages))
            question_ratio = sum(1 for msg in user_messages if "?" in msg) / max(1, len(user_messages))
            exclaim_ratio = sum(1 for msg in user_messages if "!" in msg) / max(1, len(user_messages))
            emoji_per_msg = sum(len(EMOJI_PATTERN.findall(msg)) for msg in user_messages) / max(1, len(user_messages))
            vocab_diversity = len(set(filtered)) / max(1, len(filtered))
            confidence = analyze_confidence_band(len(user_messages), vocab_diversity)
            best_channel_fit, trigger, best_time = derive_analyze_actionables(
                ctx.guild,
                user_entries,
                top_words,
                question_ratio,
                exclaim_ratio,
            )

            deterministic_block = (
                f"Communication style: {'high-energy conversationalist' if exclaim_ratio >= 0.22 else 'measured conversationalist'}\n"
                f"Confidence level: {confidence} ({len(user_messages)} messages)\n"
                f"Hidden trait: {'asks to validate ideas quickly' if question_ratio >= 0.3 else 'prefers statement-led conversation'}\n"
                f"Emoji frequency: {emoji_per_msg:.2f} per message\n"
                f"Word-usage signature: {', '.join(top_words[:5]) if top_words else 'general chat vocabulary'}\n"
                f"Best channel fit: {best_channel_fit}\n"
                f"Communication trigger: {trigger}\n"
                f"Best time to engage: {best_time}"
            )

            narrative = ""
            if is_ai_configured():
                prompt = (
                    "You are writing a concise Discord user behavior analysis.\n"
                    "Use the deterministic metrics below as source of truth.\n"
                    "No diagnosis, no medical claims.\n"
                    "Return only 4 short bullets:\n"
                    "- Core communication vibe\n"
                    "- Confidence interpretation\n"
                    "- Best way to engage this user\n"
                    "- Risk to avoid\n\n"
                    f"User: {member.display_name}\n"
                    f"Message count: {len(user_messages)}\n"
                    f"Avg length: {avg_len:.1f}\n"
                    f"Question ratio: {question_ratio:.2f}\n"
                    f"Exclaim ratio: {exclaim_ratio:.2f}\n"
                    f"Emoji per message: {emoji_per_msg:.2f}\n"
                    f"Vocab diversity: {vocab_diversity:.2f}\n"
                    f"Top words: {', '.join(top_words[:7]) if top_words else 'none'}\n"
                    f"Best channel fit: {best_channel_fit}\n"
                    f"Best time to engage: {best_time}\n"
                    "Message sample:\n"
                    + "\n".join(f"- {line}" for line in user_messages[-35:])
                )
                try:
                    narrative = await request_fun_ai(
                        prompt,
                        max_tokens=230,
                        temperature=0.45,
                        policy_key="analyze",
                    )
                except Exception as error:
                    print(f"[ANALYZE ERROR] {error}")
                    narrative = "- AI narrative unavailable; showing deterministic analysis only."

            result = (
                f"[ANALYSIS] for {member.display_name}\n"
                f"{deterministic_block}"
            )
            if narrative:
                result += f"\n\nAI narrative layer:\n{narrative}"
            result += (
                "\n\nEngagement prompt: Tag this user and test the suggested communication trigger.\n"
                "[For fun only]"
            )
            ANALYZE_CACHE[cache_key] = (time.monotonic(), result)

    await send_chunked(ctx, result)

@bot.hybrid_command(name="lie_detector")
@commands.cooldown(3, 45, commands.BucketType.user)
@commands.guild_only()
async def lie_detector_command(
    ctx: commands.Context, member: discord.Member, *, statement: str
) -> None:
    if await refuse_fun_excluded(ctx, member):
        return
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    if not is_ai_configured():
        await ctx.send(ai_setup_message())
        return
    statement = statement.strip()
    if len(statement) < 5:
        await ctx.send(f"Usage: `{PREFIX}lie_detector @user <message>`")
        return

    async with ctx.typing():
        prompt = (
            "Act as a playful lie detector for Discord.\n"
            "No factual certainty claims; this is entertainment only.\n"
            "Return exactly:\n"
            "Truth probability: <0-100>%\n"
            "Suspicious phrases detected: <comma-separated>\n"
            "Read: <one-line playful verdict>\n\n"
            f"User: {member.display_name}\n"
            f"Statement: {statement[:350]}"
        )
        try:
            result = await request_fun_ai(
                prompt,
                max_tokens=160,
                temperature=0.6,
                policy_key="liedetector",
            )
        except Exception as error:
            print(f"[LIE_DETECTOR ERROR] {error}")
            await ctx.send(friendly_ai_error(error))
            return
    await send_chunked(ctx, f"ðŸ•µï¸ **Lie Detector for {member.display_name}**\n{result}\n\nâš ï¸ For fun only.")


@bot.hybrid_command(name="futureme")
@commands.cooldown(2, 60, commands.BucketType.user)
@commands.guild_only()
async def futureme_command(ctx: commands.Context) -> None:
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    if not is_ai_configured():
        await ctx.send(ai_setup_message())
        return

    async with ctx.typing():
        user_messages = await collect_recent_user_messages(ctx.channel, ctx.author.id, 120)
        prompt = (
            "Predict a playful 5-year future snapshot for this user.\n"
            "Must include these headings:\n"
            "Career path:\n"
            "Drama level:\n"
            "Wealth potential:\n"
            "Main plot twist:\n"
            "Keep it witty and under 170 words.\n\n"
            f"User: {ctx.author.display_name}\n"
            "Recent message sample:\n"
            + "\n".join(f"- {m}" for m in user_messages[-24:])
        )
        try:
            result = await request_fun_ai(
                prompt,
                max_tokens=220,
                temperature=0.85,
                policy_key="futureme",
            )
        except Exception as error:
            print(f"[FUTUREME ERROR] {error}")
            await ctx.send(friendly_ai_error(error))
            return
    await send_chunked(ctx, f"ðŸ”® **FutureMe for {ctx.author.display_name}**\n{result}\n\nâš ï¸ For fun only.")


@bot.hybrid_command(name="rizzcoach")
@commands.cooldown(3, 45, commands.BucketType.user)
@commands.guild_only()
async def rizzcoach_command(
    ctx: commands.Context,
    style: str = "smooth",
    *,
    draft: str | None = None,
) -> None:
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    if not is_ai_configured():
        await ctx.send(ai_setup_message())
        return

    normalized_style = style.strip().lower()
    if draft is None:
        draft_text = style
        normalized_style = "smooth"
    elif normalized_style in {"smooth", "funny", "mysterious"}:
        draft_text = draft
    else:
        draft_text = f"{style} {draft}".strip()
        normalized_style = "smooth"

    draft_text = draft_text.strip()
    if len(draft_text) < 4:
        await ctx.send(f"Usage: `{PREFIX}rizzcoach [smooth|funny|mysterious] <message>`")
        return

    async with ctx.typing():
        prompt = (
            "You are a rizz coach for Discord.\n"
            "Rewrite the user's draft into 3 alternatives:\n"
            "1) smooth\n"
            "2) funny\n"
            "3) mysterious\n"
            "Then recommend one best option based on requested style.\n"
            "Keep it clean and non-explicit.\n\n"
            f"Requested style: {normalized_style}\n"
            f"Original draft: {draft_text[:350]}"
        )
        try:
            result = await request_fun_ai(
                prompt,
                max_tokens=260,
                temperature=0.85,
                policy_key="rizzcoach",
            )
        except Exception as error:
            print(f"[RIZZCOACH ERROR] {error}")
            await ctx.send(friendly_ai_error(error))
            return
    await send_chunked(ctx, f"ðŸ’¬ **RizzCoach ({normalized_style})**\n{result}")


@bot.hybrid_command(name="argument")
@commands.cooldown(3, 45, commands.BucketType.user)
@commands.guild_only()
async def argument_command(ctx: commands.Context, *, topic: str) -> None:
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    if not is_ai_configured():
        await ctx.send(ai_setup_message())
        return
    topic = topic.strip()
    if len(topic) < 3:
        await ctx.send(f"Usage: `{PREFIX}argument <topic>`")
        return

    side: Literal["PRO", "ANTI"] = random.choice(["PRO", "ANTI"])
    async with ctx.typing():
        try:
            result = await generate_argument_opening(topic, side)
        except Exception as error:
            print(f"[ARGUMENT ERROR] {error}")
            await ctx.send(friendly_ai_error(error))
            return
    stop_psych_session(ctx.channel.id, ctx.author.id)
    start_argument_session(ctx.channel.id, ctx.author.id, topic, side)
    await send_chunked(
        ctx,
        f"âš”ï¸ **Argument Mode** ({side}) on **{topic}**\n"
        f"{result}\n\n"
        "Reply with your points normally in this channel and I'll counter each one. "
        "Say `bell stop argument` to end.",
    )


@bot.hybrid_command(name="debate")
@commands.cooldown(2, 75, commands.BucketType.user)
@commands.guild_only()
async def debate_command(ctx: commands.Context, member: discord.Member, *, topic: str) -> None:
    if await refuse_fun_excluded(ctx, member):
        return
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    if member.bot or member.id == ctx.author.id:
        await ctx.send("Pick another non-bot member for debate.")
        return
    if not is_ai_configured():
        await ctx.send(ai_setup_message())
        return
    topic = topic.strip()
    if len(topic) < 3:
        await ctx.send(f"Usage: `{PREFIX}debate @user <topic>`")
        return

    async with ctx.typing():
        author_msgs = await collect_recent_user_messages(ctx.channel, ctx.author.id, 50)
        member_msgs = await collect_recent_user_messages(ctx.channel, member.id, 50)
        prompt = (
            "Moderate a playful debate between two users and declare a winner.\n"
            "No hate speech. Keep it entertaining.\n"
            "Output format:\n"
            "Round 1:\n"
            "Round 2:\n"
            "Round 3:\n"
            "Scoreboard: <user A score> - <user B score>\n"
            "Winner: ...\n"
            "Why: ...\n\n"
            f"Topic: {topic}\n"
            f"User A: {ctx.author.display_name}\n"
            f"User B: {member.display_name}\n"
            f"User A style sample:\n" + "\n".join(f"- {m}" for m in author_msgs[-14:]) + "\n\n"
            f"User B style sample:\n" + "\n".join(f"- {m}" for m in member_msgs[-14:])
        )
        try:
            result = await request_fun_ai(
                prompt,
                max_tokens=320,
                temperature=0.88,
                policy_key="debate",
            )
        except Exception as error:
            print(f"[DEBATE ERROR] {error}")
            await ctx.send(friendly_ai_error(error))
            return
    await send_chunked(
        ctx,
        f"ðŸ›ï¸ **Debate Arena**: {ctx.author.mention} vs {member.mention}\nTopic: **{topic}**\n\n{result}",
    )


@bot.hybrid_command(name="translate")
@commands.cooldown(3, 20, commands.BucketType.user)
async def translate_command(ctx: commands.Context, *, text_or_link: str | None = None) -> None:
    raw_input = (text_or_link or "").strip()
    source_message = await resolve_message_from_context(ctx, raw_input)
    source_text = ""

    if source_message is not None:
        source_text = (source_message.clean_content or "").strip()
        if not source_text and source_message.attachments:
            await ctx.send("That message has no text content to translate.")
            return
    else:
        if raw_input and DISCORD_MESSAGE_LINK_RE.search(raw_input):
            await ctx.send(
                "I could not read that Discord message link here. Reply to the message, or pass a readable link from this server."
            )
            return
        source_text = raw_input

    if not source_text:
        await ctx.send(
            f"Usage: reply to a message and run `{PREFIX}translate`, or use `{PREFIX}translate <text>`."
        )
        return
    if len(source_text) > 1600:
        await ctx.send("Translation input is too long. Keep it under `1600` characters.")
        return

    async with ctx.typing():
        payload = await translate_text_to_english(source_text)

    translated_text = str(payload.get("translated_text", "") or "").strip() or source_text
    await send_chunked(ctx, translated_text)


@bot.command(name="ai", aliases=["ask"])
@commands.cooldown(3, 30, commands.BucketType.user)
async def ai_command(ctx: commands.Context, *, prompt: str | None = None) -> None:
    if not is_ai_configured():
        await ctx.send(ai_setup_message())
        return

    prompt = (prompt or "").strip()
    if not prompt:
        await ctx.send(f"Usage: `{PREFIX}ai <prompt>` or `{PREFIX}aisummary 25`")
        return

    history = AI_CHAT_CACHE.get(ctx.channel.id, [])[-(AI_MAX_HISTORY * 2) :]
    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}, *history]
    messages.append({"role": "user", "content": prompt})

    async with ctx.typing():
        try:
            reply = await request_ai_completion(
                messages,
                max_tokens=AI_MAX_TOKENS,
                temperature=0.5,
                policy_key="chat",
            )
        except Exception as error:
            print(f"[AI ERROR] {error}")
            await ctx.send(friendly_ai_error(error))
            return

    append_ai_history(ctx.channel.id, prompt, reply)
    await send_chunked(ctx, reply)


@bot.command(name="aisummary", aliases=["aisummarise", "summary"])
@commands.cooldown(2, 45, commands.BucketType.user)
async def aisummary_command(ctx: commands.Context, count: int = 25) -> None:
    if not is_ai_configured():
        await ctx.send(ai_setup_message())
        return

    if count < 5 or count > 100:
        await ctx.send("`count` must be between `5` and `100`.")
        return

    transcript: list[str] = []
    async for msg in ctx.channel.history(limit=count):
        if msg.author.bot:
            continue
        content = msg.clean_content.strip()
        if not content:
            continue
        transcript.append(f"{msg.author.display_name}: {content[:280]}")

    if not transcript:
        await ctx.send("Not enough recent user messages to summarize.")
        return

    transcript.reverse()
    summary_prompt = (
        "Summarize this Discord chat in short bullet points.\n"
        "Include: key topics, decisions, and any action items.\n\n"
        + "\n".join(transcript)
    )
    messages = [
        {"role": "system", "content": AI_SYSTEM_PROMPT},
        {"role": "user", "content": summary_prompt},
    ]

    async with ctx.typing():
        try:
            summary = await request_ai_completion(
                messages,
                max_tokens=AI_SUMMARY_MAX_TOKENS,
                temperature=0.2,
                policy_key="summary",
            )
        except Exception as error:
            print(f"[AI SUMMARY ERROR] {error}")
            await ctx.send(friendly_ai_error(error))
            return

    await send_chunked(ctx, f"Summary of last `{len(transcript)}` messages:\n{summary}")


@bot.hybrid_command(name="catchup")
@commands.cooldown(2, 30, commands.BucketType.user)
@commands.guild_only()
async def catchup_command(ctx: commands.Context, hours: int = 24) -> None:
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    if hours < 1 or hours > CATCHUP_MAX_HOURS:
        await ctx.send(f"`hours` must be between `1` and `{CATCHUP_MAX_HOURS}`.")
        return
    await run_catchup_for_channel(ctx, ctx.channel, hours)


@bot.hybrid_command(name="catchupchannel")
@commands.cooldown(2, 35, commands.BucketType.user)
@commands.guild_only()
async def catchup_channel_command(
    ctx: commands.Context, channel: discord.TextChannel, hours: int = 24
) -> None:
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    if hours < 1 or hours > CATCHUP_MAX_HOURS:
        await ctx.send(f"`hours` must be between `1` and `{CATCHUP_MAX_HOURS}`.")
        return
    if not channel.permissions_for(ctx.author).view_channel:
        await ctx.send("You do not have access to that channel.")
        return
    me = ctx.guild.me
    if me is None or not channel.permissions_for(me).read_message_history:
        await ctx.send("I cannot read that channel's history.")
        return
    await run_catchup_for_channel(ctx, channel, hours)


@bot.hybrid_command(name="serverinsights")
@commands.cooldown(2, 90, commands.BucketType.user)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def serverinsights_command(ctx: commands.Context, hours: int = 72) -> None:
    if not await enforce_fun_rate_limit_ctx(ctx):
        return
    if hours < 6 or hours > INSIGHTS_MAX_HOURS:
        await ctx.send(f"`hours` must be between `6` and `{INSIGHTS_MAX_HOURS}`.")
        return
    await run_server_insights(ctx, ctx.guild, hours)


@bot.command(name="pb")
@commands.has_permissions(manage_messages=True)
async def purge_bot_messages(ctx: commands.Context) -> None:
    deleted = await purge_recent_bot_webhook_messages(ctx.channel, trigger_message=ctx.message)

    await ctx.send(f"`{deleted}` messages have been deleted.", delete_after=3)
    await send_mod_log(
        ctx.guild,
        "Purge Bot Messages",
        moderator=ctx.author,
        channel=ctx.channel,
        details=f"Deleted: `{deleted}`",
    )


@bot.command(name="pba")
@commands.has_permissions(manage_messages=True)
async def purge_bot_messages_all(ctx: commands.Context) -> None:
    deleted_messages = await ctx.channel.purge(
        limit=None,
        check=lambda m: m.author.bot or m.webhook_id is not None,
        bulk=False,
    )
    deleted = len(deleted_messages)

    await ctx.send(f"`{deleted}` messages have been deleted.", delete_after=3)
    await send_mod_log(
        ctx.guild,
        "Purge Bot Messages (All)",
        moderator=ctx.author,
        channel=ctx.channel,
        details=f"Deleted: `{deleted}`",
    )


@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx: commands.Context, amount: int) -> None:
    if amount < 1 or amount > 500:
        await ctx.send("Amount must be between `1` and `500`.")
        return
    deleted = await ctx.channel.purge(limit=amount + 1)
    total_deleted = max(len(deleted) - 1, 0)
    await ctx.send(f"Deleted `{total_deleted}` messages.", delete_after=6)
    await send_mod_log(
        ctx.guild,
        "Clear Messages",
        moderator=ctx.author,
        channel=ctx.channel,
        details=f"Deleted: `{total_deleted}`",
    )


@bot.command(name="bulkdelete", aliases=["bd"])
@commands.has_permissions(manage_messages=True)
async def bulk_delete_messages(
    ctx: commands.Context, channel: discord.TextChannel, amount: int
) -> None:
    if amount < 1 or amount > 1000:
        await ctx.send("Amount must be between `1` and `1000`.")
        return

    if not channel.permissions_for(ctx.author).manage_messages:
        await ctx.send("You do not have permission to manage messages in that channel.")
        return

    me = ctx.guild.me
    if me is None:
        await ctx.send("Could not verify bot permissions in that channel.")
        return
    bot_perms = channel.permissions_for(me)
    if not bot_perms.manage_messages or not bot_perms.read_message_history:
        await ctx.send("I need `Manage Messages` and `Read Message History` in that channel.")
        return

    deleted = await channel.purge(limit=amount)
    total_deleted = len(deleted)

    await ctx.send(
        f"Deleted `{total_deleted}` messages in {channel.mention}.",
        delete_after=6,
    )
    await send_mod_log(
        ctx.guild,
        "Bulk Delete Messages",
        moderator=ctx.author,
        channel=channel,
        details=f"Deleted: `{total_deleted}`",
    )


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_member(
    ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided."
) -> None:
    await member.kick(reason=reason)
    await ctx.send(f"Kicked {member.mention}. Reason: {reason}")
    await send_mod_log(
        ctx.guild,
        "Kick",
        target=member,
        moderator=ctx.author,
        reason=reason,
        channel=ctx.channel,
    )


@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_member(
    ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided."
) -> None:
    await member.ban(reason=reason)
    await ctx.send(f"Banned {member.mention}. Reason: {reason}")
    await send_mod_log(
        ctx.guild,
        "Ban",
        target=member,
        moderator=ctx.author,
        reason=reason,
        channel=ctx.channel,
    )


@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban_member(
    ctx: commands.Context, user_id: int, *, reason: str = "No reason provided."
) -> None:
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user, reason=reason)
    await ctx.send(f"Unbanned `{user}`. Reason: {reason}")
    await send_mod_log(
        ctx.guild,
        "Unban",
        target=user,
        moderator=ctx.author,
        reason=reason,
        channel=ctx.channel,
    )


@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute_member(
    ctx: commands.Context,
    member: discord.Member,
    minutes: int,
    *,
    reason: str = "No reason provided.",
) -> None:
    if minutes < 1 or minutes > 40320:
        await ctx.send("Minutes must be between `1` and `40320` (28 days).")
        return
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    await member.timeout(until, reason=reason)
    await ctx.send(f"Muted {member.mention} for `{minutes}` minute(s). Reason: {reason}")
    await send_mod_log(
        ctx.guild,
        "Mute",
        target=member,
        moderator=ctx.author,
        reason=reason,
        channel=ctx.channel,
        details=f"Duration: `{minutes}` minute(s)",
    )


@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute_member(
    ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided."
) -> None:
    await member.timeout(None, reason=reason)
    await ctx.send(f"Unmuted {member.mention}. Reason: {reason}")
    await send_mod_log(
        ctx.guild,
        "Unmute",
        target=member,
        moderator=ctx.author,
        reason=reason,
        channel=ctx.channel,
    )


async def set_channel_send_locked(
    channel: discord.abc.GuildChannel, guild: discord.Guild, locked: bool, reason: str
) -> None:
    overwrite = channel.overwrites_for(guild.default_role)
    overwrite.send_messages = False if locked else None
    await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)


@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock_channel(ctx: commands.Context, *, reason: str = "No reason provided.") -> None:
    await set_channel_send_locked(ctx.channel, ctx.guild, True, reason)
    await ctx.send(f"Locked {ctx.channel.mention}. Reason: {reason}")
    await send_mod_log(
        ctx.guild,
        "Lock Channel",
        moderator=ctx.author,
        reason=reason,
        channel=ctx.channel,
    )


@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock_channel(ctx: commands.Context, *, reason: str = "No reason provided.") -> None:
    await set_channel_send_locked(ctx.channel, ctx.guild, False, reason)
    await ctx.send(f"Unlocked {ctx.channel.mention}. Reason: {reason}")
    await send_mod_log(
        ctx.guild,
        "Unlock Channel",
        moderator=ctx.author,
        reason=reason,
        channel=ctx.channel,
    )


@bot.command(name="slowmode")
@commands.has_permissions(manage_channels=True)
async def slowmode_channel(ctx: commands.Context, seconds: int) -> None:
    if seconds < 0 or seconds > 21600:
        await ctx.send("Seconds must be between `0` and `21600`.")
        return
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"Set slowmode in {ctx.channel.mention} to `{seconds}` second(s).")
    await send_mod_log(
        ctx.guild,
        "Slowmode",
        moderator=ctx.author,
        channel=ctx.channel,
        details=f"Delay: `{seconds}` second(s)",
    )


def add_member_warning(guild_id: int, member_id: int, reason: str, moderator_id: int) -> int:
    """Record a warning and return the member's new total."""
    warnings = load_warnings()
    guild_key = str(guild_id)
    user_key = str(member_id)

    warnings.setdefault(guild_key, {}).setdefault(user_key, [])
    warnings[guild_key][user_key].append(
        {
            "reason": reason,
            "moderator_id": moderator_id,
            "timestamp": discord.utils.utcnow().isoformat(),
        }
    )
    save_warnings(warnings)
    return len(warnings[guild_key][user_key])


@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn_member(
    ctx: commands.Context, member: discord.Member, *, reason: str
) -> None:
    total = add_member_warning(ctx.guild.id, member.id, reason, ctx.author.id)
    await ctx.send(f"Warned {member.mention}. Total warnings: `{total}`.")
    await send_mod_log(
        ctx.guild,
        "Warn",
        target=member,
        moderator=ctx.author,
        reason=reason,
        channel=ctx.channel,
        details=f"Total warnings: `{total}`",
    )


@bot.command(name="warnings")
@commands.has_permissions(manage_messages=True)
async def list_warnings(ctx: commands.Context, member: discord.Member) -> None:
    warnings = load_warnings()
    guild_key = str(ctx.guild.id)
    user_key = str(member.id)
    user_warnings = warnings.get(guild_key, {}).get(user_key, [])

    if not user_warnings:
        await ctx.send(f"{member.mention} has no warnings.")
        return

    lines = []
    for i, entry in enumerate(user_warnings[-10:], start=max(1, len(user_warnings) - 9)):
        lines.append(
            f"{i}. Reason: {entry['reason']} | Mod ID: {entry['moderator_id']} | Time: {entry['timestamp']}"
        )
    await ctx.send(
        f"Warnings for {member.mention} (`{len(user_warnings)}` total):\n" + "\n".join(lines)
    )


@bot.command(name="clearwarns")
@commands.has_permissions(manage_messages=True)
async def clear_warnings(ctx: commands.Context, member: discord.Member) -> None:
    warnings = load_warnings()
    guild_key = str(ctx.guild.id)
    user_key = str(member.id)

    if guild_key in warnings and user_key in warnings[guild_key]:
        del warnings[guild_key][user_key]
        save_warnings(warnings)
        await ctx.send(f"Cleared all warnings for {member.mention}.")
        await send_mod_log(
            ctx.guild,
            "Clear Warnings",
            target=member,
            moderator=ctx.author,
            channel=ctx.channel,
        )
        return

    await ctx.send(f"{member.mention} has no warnings.")


# ---------------------------------------------------------------------------
# Agent (&agent): tool registry over existing bot functions + plan-act-check loop
# ---------------------------------------------------------------------------

AGENT_LIMITS = agent_core.load_agent_limits(os.environ)
AGENT_MAX_TOKENS = env_int("AGENT_MAX_TOKENS", 500, 150)
AGENT_WITHHELD_MESSAGE = "The agent's reply was withheld by this server's safety filter."
AGENT_BLOCKED_CATEGORIES = {"scam_phishing", "harassment_toxic"}
AGENT_FOLLOWUP_TASKS: set[asyncio.Task] = set()
AGENT_NO_MENTIONS = discord.AllowedMentions.none()


def screen_agent_text(text: str) -> tuple[str, str | None]:
    """Run agent output through the bot's existing screening (bad words + AI-guard heuristics).

    Returns ``(text_safe_to_post, problem_or_None)``.
    """
    content = str(text or "")
    if matches_bad_word(content):
        return AGENT_WITHHELD_MESSAGE, "Text contains a blocked word."
    normalized, _ = _ai_mod_normalize_hinglish(content)
    verdict = _ai_mod_heuristic_payload(content, normalized, corroborators={})
    if verdict.get("category") in AGENT_BLOCKED_CATEGORIES:
        return AGENT_WITHHELD_MESSAGE, f"Text was flagged as `{verdict.get('category')}`."
    safe = content.replace("@everyone", "@​everyone").replace("@here", "@​here")
    return safe, None


def _agent_screen_text_args(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> str | None:
    for name, value in args.items():
        if not isinstance(value, str):
            continue
        if "@everyone" in value or "@here" in value:
            return f"`{name}` must not contain @everyone/@here."
        _, problem = screen_agent_text(value)
        if problem:
            return f"`{name}` was rejected by the safety filter: {problem}"
    return None


async def _agent_member_info(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    member: discord.Member = args["member"]
    roles = [role.name for role in reversed(member.roles) if role != ctx.guild.default_role]
    return {
        "id": member.id,
        "name": str(member),
        "display_name": member.display_name,
        "bot": member.bot,
        "joined_at": member.joined_at.isoformat() if member.joined_at else None,
        "account_created_at": member.created_at.isoformat(),
        "top_role": member.top_role.name,
        "roles": roles[:10],
        "timed_out": has_active_timeout(member),
        "is_moderator": is_moderator(member),
    }


async def _agent_channel_info(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    channel = args["channel"]
    overwrite = (
        channel.overwrites_for(ctx.guild.default_role) if hasattr(channel, "overwrites_for") else None
    )
    return {
        "id": channel.id,
        "name": channel.name,
        "type": str(channel.type),
        "category": channel.category.name if getattr(channel, "category", None) else None,
        "topic": getattr(channel, "topic", None),
        "slowmode_seconds": getattr(channel, "slowmode_delay", 0),
        "locked_for_everyone": bool(overwrite is not None and overwrite.send_messages is False),
        "nsfw": bool(getattr(channel, "nsfw", False)),
    }


async def _agent_warn_count(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    member: discord.Member = args["member"]
    entries = load_warnings().get(str(ctx.guild.id), {}).get(str(member.id), [])
    return {
        "member_id": member.id,
        "total": len(entries),
        "recent": [
            {"reason": str(e.get("reason", ""))[:200], "timestamp": e.get("timestamp")}
            for e in entries[-3:]
            if isinstance(e, dict)
        ],
    }


async def _agent_modlog_tail(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    channel_id = get_guild_mod_log_channel_id(ctx.guild.id)
    log_channel = ctx.guild.get_channel(channel_id) if channel_id else None
    if not isinstance(log_channel, discord.TextChannel):
        return {"entries": [], "note": "No mod-log channel is configured."}
    entries: list[dict[str, Any]] = []
    async for message in log_channel.history(limit=int(args["limit"])):
        for embed in message.embeds:
            fields = {field.name: str(field.value)[:200] for field in embed.fields}
            entries.append({"time": message.created_at.isoformat(), **fields})
    return {"entries": entries}


async def _agent_xp_lookup(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    member: discord.Member = args["member"]
    snapshot = get_rank_snapshot(ctx.guild.id, member.id)
    position, total = get_user_rank_position(ctx.guild, member.id, "alltime")
    return {"member_id": member.id, **snapshot, "alltime_rank": position, "ranked_members": total}


async def _agent_economy_lookup(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    member: discord.Member = args["member"]
    users = get_business_state().get("users", {})
    row = users.get(str(member.id)) if isinstance(users, dict) else None
    if not isinstance(row, dict):
        return {"member_id": member.id, "has_profile": False}
    return {
        "member_id": member.id,
        "has_profile": True,
        "cash": round(float(row.get("cash", 0.0)), 2),
        "networth": round(_business_networth(member.id), 2),
        "credit_score": row.get("credit_score"),
        "businesses": len(row.get("business_ids", []) or []),
        "frozen": bool(row.get("frozen", False)),
    }


async def _agent_search_messages(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> dict[str, Any]:
    """Search the bot's in-memory message windows; never reads channels the requester cannot."""
    query = str(args["query"]).lower()
    limit = int(args["limit"])
    readable: dict[int, bool] = {}
    seen: set[int] = set()
    hits: list[WindowMessage] = []
    for _, window in list(MESSAGE_WINDOW_CACHE.values()):
        for entry in window:
            if entry.message_id in seen or query not in entry.content.lower():
                continue
            if entry.channel_id not in readable:
                channel = ctx.guild.get_channel(entry.channel_id)
                readable[entry.channel_id] = bool(
                    channel is not None and channel.permissions_for(ctx.author).read_messages
                )
            if not readable[entry.channel_id]:
                continue
            seen.add(entry.message_id)
            hits.append(entry)
    hits.sort(key=lambda entry: entry.created_at_ts, reverse=True)
    return {
        "matches": [
            {
                "channel_id": entry.channel_id,
                "author": entry.author_display_name,
                "author_id": entry.author_id,
                "content": entry.content[:300],
                "time": datetime.fromtimestamp(entry.created_at_ts, timezone.utc).isoformat(),
            }
            for entry in hits[:limit]
        ],
        "note": None if hits else "No matches in the bot's recent message buffers.",
    }


async def _agent_do_warn(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> str:
    member: discord.Member = args["member"]
    total = add_member_warning(ctx.guild.id, member.id, args["reason"], ctx.actor.id)
    return f"Warned {member.mention}. Total warnings: {total}."


async def _agent_do_timeout(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> str:
    member: discord.Member = args["member"]
    minutes = int(args["minutes"])
    until = discord.utils.utcnow() + timedelta(minutes=minutes)
    await member.timeout(until, reason=f"{args['reason']} (agent action confirmed by {ctx.actor})")
    return f"Timed out {member.mention} for {minutes} minute(s)."


async def _agent_do_lock(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> str:
    channel = args["channel"]
    await set_channel_send_locked(channel, ctx.guild, True, args["reason"])
    return f"Locked {channel.mention}."


async def _agent_do_unlock(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> str:
    channel = args["channel"]
    await set_channel_send_locked(channel, ctx.guild, False, args["reason"])
    return f"Unlocked {channel.mention}."


async def _agent_do_post_message(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> str:
    channel = args["channel"]
    if not channel.permissions_for(ctx.actor).send_messages:
        raise agent_tools.ToolError(f"You cannot send messages in {channel.mention}.")
    text, problem = screen_agent_text(args["text"])
    if problem:
        raise agent_tools.ToolError(problem)
    await channel.send(text, allowed_mentions=AGENT_NO_MENTIONS)
    return f"Posted a message in {channel.mention}."


async def _agent_do_schedule_followup(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> str:
    minutes = int(args["minutes"])
    text, problem = screen_agent_text(args["text"])
    if problem:
        raise agent_tools.ToolError(problem)
    channel = ctx.channel  # follow-ups go only to the channel where &agent was invoked

    async def fire_followup() -> None:
        await asyncio.sleep(minutes * 60)
        try:
            await channel.send(f"Follow-up: {text}", allowed_mentions=AGENT_NO_MENTIONS)
        except discord.HTTPException:
            pass

    task = asyncio.create_task(fire_followup())
    AGENT_FOLLOWUP_TASKS.add(task)
    task.add_done_callback(AGENT_FOLLOWUP_TASKS.discard)
    return f"Follow-up scheduled in {channel.mention} in {minutes} minute(s)."


def build_agent_registry() -> agent_tools.ToolRegistry:
    A = agent_tools.ArgSpec
    T = agent_tools.AgentTool
    RO, CQ = agent_tools.READ_ONLY, agent_tools.CONSEQUENTIAL
    member_arg = A("member", "member", "Member mention or ID.")
    channel_opt = A("channel", "channel", "Channel mention or ID (defaults to the current channel).", required=False)
    reason_arg = A("reason", "str", "Reason recorded in the mod-log.", max_length=300)
    registry = agent_tools.ToolRegistry(is_moderator=is_moderator)
    for tool in (
        T("member_info", "Look up a member's profile, roles and timeout state.", (member_arg,), RO, _agent_member_info),
        T("channel_info", "Look up a channel's topic, slowmode and lock state.", (channel_opt,), RO, _agent_channel_info),
        T("warn_count", "Count a member's warnings and show the latest reasons.", (member_arg,), RO,
          _agent_warn_count, requires_moderator=True),
        T("modlog_tail", "Read the most recent mod-log entries.",
          (A("limit", "int", "How many log messages to read.", required=False, default=5, minimum=1, maximum=10),),
          RO, _agent_modlog_tail, requires_moderator=True),
        T("xp_lookup", "Read a member's XP, streak and rank.", (member_arg,), RO, _agent_xp_lookup),
        T("economy_lookup", "Read a member's economy profile (cash, net worth).", (member_arg,), RO, _agent_economy_lookup),
        T("search_messages", "Search the bot's recent in-memory message buffers for text.",
          (A("query", "str", "Case-insensitive text to find.", max_length=100),
           A("limit", "int", "Max matches.", required=False, default=5, minimum=1, maximum=10)),
          RO, _agent_search_messages),
        T("warn", "Warn a member (needs moderator confirmation).", (member_arg, reason_arg), CQ, _agent_do_warn,
          required_permission="manage_messages", modlog_action="Warn", validate=_agent_screen_text_args),
        T("timeout", "Time out a member (needs moderator confirmation).",
          (member_arg, A("minutes", "int", "Timeout length in minutes.", minimum=1, maximum=40320), reason_arg),
          CQ, _agent_do_timeout, required_permission="moderate_members", modlog_action="Mute",
          validate=_agent_screen_text_args),
        T("lock_channel", "Stop @everyone from sending messages in a channel (needs confirmation).",
          (channel_opt, reason_arg), CQ, _agent_do_lock, required_permission="manage_channels",
          modlog_action="Lock Channel", validate=_agent_screen_text_args),
        T("unlock_channel", "Re-allow @everyone to send messages in a channel (needs confirmation).",
          (channel_opt, reason_arg), CQ, _agent_do_unlock, required_permission="manage_channels",
          modlog_action="Unlock Channel", validate=_agent_screen_text_args),
        T("post_message", "Post a message as the bot (needs confirmation).",
          (A("text", "str", "Message text.", max_length=1500), channel_opt), CQ, _agent_do_post_message,
          modlog_action="Post Message", validate=_agent_screen_text_args),
        T("schedule_followup", "Post a follow-up note in this channel after a delay (needs confirmation).",
          (A("minutes", "int", "Delay in minutes.", minimum=1, maximum=1440),
           A("text", "str", "Follow-up text.", max_length=500)),
          CQ, _agent_do_schedule_followup, modlog_action="Schedule Follow-up", validate=_agent_screen_text_args),
    ):
        registry.register(tool)
    return registry


async def _agent_complete(messages: list[dict[str, str]]) -> str:
    # Existing governor-routed completion path (Groq goes through GROQ_BUDGET).
    return await request_ai_completion(
        messages,
        max_tokens=AGENT_MAX_TOKENS,
        temperature=0.2,
        policy_key="agent",
        include_fallback_notice=False,
    )


AGENT_REGISTRY = build_agent_registry()
AGENT_PENDING = agent_tools.PendingActionManager(is_moderator=is_moderator, mod_log=send_mod_log)
AGENT_RUNNER = agent_core.AgentRunner(
    registry=AGENT_REGISTRY,
    pending=AGENT_PENDING,
    complete=_agent_complete,
    limits=AGENT_LIMITS,
)


@bot.command(name="agent")
@commands.guild_only()
@commands.cooldown(2, 20, commands.BucketType.user)
async def agent_command(ctx: commands.Context, *, request: str | None = None) -> None:
    if not is_ai_configured():
        await ctx.channel.send(ai_setup_message())
        return
    request = (request or "").strip()
    if not request:
        await ctx.channel.send(f"Usage: `{PREFIX}agent <what you need>`")
        return
    if len(request) > 1500:
        await ctx.channel.send("Agent requests must be under `1500` characters.")
        return

    agent_ctx = agent_tools.AgentContext(guild=ctx.guild, channel=ctx.channel, author=ctx.author)
    async with ctx.typing():
        result = await AGENT_RUNNER.run(request, agent_ctx)

    reply, _ = screen_agent_text(result.reply)
    for chunk in split_message(reply):
        await ctx.channel.send(chunk, allowed_mentions=AGENT_NO_MENTIONS)

    for action in result.pending_actions:
        if action.status != agent_tools.PENDING:
            continue
        card, problem = screen_agent_text(agent_tools.render_card(action))
        if problem:
            AGENT_PENDING.expire(action.id)
            await ctx.channel.send(f"Agent action #{action.id} was withheld by the safety filter.")
            continue
        view = agent_tools.build_pending_action_view(AGENT_PENDING, action)
        view.message = await ctx.channel.send(card, view=view, allowed_mentions=AGENT_NO_MENTIONS)


# ---------------------------------------------------------------------------
# Agentic automation (phase 3): scheduled agent tasks, escalation proposals,
# engagement nudges. All OFF by default; enabled per server via the "agentic"
# block in mod_config.json (see `&agentic`).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Crush-o-Meter game (phase 4). Replaces the old history-mining aicrush.
# ---------------------------------------------------------------------------

CRUSH_GAME_STATE = crush_game.CrushGameState()
GROQ_BUDGET.feature_caps.setdefault(
    crush_game.FEATURE, env_int("CRUSH_GAME_DAILY_CAP", crush_game.DEFAULT_DAILY_CAP, 1)
)
GROQ_BUDGET.feature_caps.setdefault(
    crush_game.FLAVOR_FEATURE, env_int("CRUSH_GAME_FLAVOR_DAILY_CAP", crush_game.DEFAULT_DAILY_CAP, 1)
)


async def _crush_game_flavor(prompt: str) -> str:
    # Optional one-line joke. Only on Groq, so it always goes through the budget
    # governor (with its own per-feature cap); otherwise the game is template-only.
    if AI_PROVIDER != "groq" or not GROQ_API_KEY:
        return ""
    return await request_groq_completion(
        [
            {"role": "system", "content": "You write one short, wholesome joke line for a party game."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=80,
        temperature=0.9,
        include_fallback_notice=False,
        feature=crush_game.FLAVOR_FEATURE,
    )


CRUSH_GAME = crush_game.CrushGame(
    state=CRUSH_GAME_STATE,
    admit_feature=GROQ_BUDGET.try_admit_feature,
    prefix=PREFIX,
    flavor=_crush_game_flavor,
)


def load_crush_game_state() -> None:
    global CRUSH_GAME_STATE
    # The legacy aicrush file is deliberately neither read nor deleted here.
    CRUSH_GAME_STATE = crush_game.CrushGameState(read_state(CRUSH_GAME_STATE_KEY))
    CRUSH_GAME.state = CRUSH_GAME_STATE


def save_crush_game_state(force: bool = False) -> None:
    if (force or CRUSH_GAME_STATE.dirty) and write_state(CRUSH_GAME_STATE_KEY, CRUSH_GAME_STATE.data):
        CRUSH_GAME_STATE.dirty = False


async def refuse_fun_excluded(ctx: commands.Context, member: Any) -> bool:
    """True (and a reply sent) if ``member`` used &exclude; fun features must skip them."""
    if ctx.guild is None or member is None:
        return False
    if CRUSH_GAME.is_excluded(ctx.guild.id, member.id):
        await ctx.send(CRUSH_GAME.excluded_text())
        return True
    return False


@bot.hybrid_command(name="crush")
@commands.cooldown(3, 60, commands.BucketType.user)
@commands.guild_only()
async def crush_command(
    ctx: commands.Context, member: discord.Member | None = None, *, answer: str = ""
) -> None:
    """Crush-o-Meter joke game about you. Naming a member is only a random pairing."""
    if member is not None and getattr(member, "bot", False):
        await ctx.send("Bots are too busy beeping to play the Crush-o-Meter. 🤖")
        return
    # Inputs are only what the invoker deliberately gives the game: their answer,
    # or one of their OWN messages they reply to. Nobody else's messages are read.
    supplied = answer
    reference = getattr(ctx.message, "reference", None) if ctx.message is not None else None
    resolved = getattr(reference, "resolved", None)
    if not supplied and isinstance(resolved, discord.Message):
        supplied = crush_game.pointed_input(ctx.author.id, resolved.author.id, resolved.content)
    result = await CRUSH_GAME.play(ctx.guild, ctx.author, member, answer=supplied)
    save_crush_game_state()
    await ctx.send(result, allowed_mentions=discord.AllowedMentions.none())


@bot.command(name="crushgame")
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def crush_game_admin_command(
    ctx: commands.Context, mode: str = "status", channel: discord.TextChannel | None = None
) -> None:
    mode = (mode or "status").strip().lower()
    if mode in {"on", "enable"}:
        target_channel = channel or ctx.channel
        posted = await CRUSH_GAME.enable(ctx.guild.id, target_channel)
        save_crush_game_state(force=True)
        note = f" Notice posted in {target_channel.mention}." if posted else " (The one-time notice was already posted.)"
        await ctx.send(f"Crush-o-Meter game enabled.{note}")
    elif mode in {"off", "disable"}:
        CRUSH_GAME.disable(ctx.guild.id)
        save_crush_game_state(force=True)
        await ctx.send("Crush-o-Meter game disabled.")
    else:
        state = "on" if CRUSH_GAME.is_enabled(ctx.guild.id) else "off"
        await ctx.send(f"Crush-o-Meter game is **{state}**. Use `{PREFIX}crushgame on [#channel]` or `off`.")


def _legacy_aicrush_paths() -> list[Path]:
    # The legacy data only ever existed as files under data/, whatever backend is active.
    legacy_files = storage.JsonFileBackend(DATA_DIR)
    path = legacy_files.path_for(LEGACY_AICRUSH_STATE_KEY)
    return [path, legacy_files.backup_path(path)]


@bot.command(name="legacydata")
@commands.is_owner()
async def legacy_data_command(ctx: commands.Context, action: str = "status", confirm: str = "") -> None:
    """Owner-only: inspect or delete the old aicrush data file (never read by the bot)."""
    paths = _legacy_aicrush_paths()
    action = (action or "status").strip().lower()
    if action == "wipe":
        if confirm.strip().lower() != "confirm":
            await ctx.send(
                f"This permanently deletes the old aicrush data file(s). Run `{PREFIX}legacydata wipe confirm` to proceed."
            )
            return
        removed = crush_game.delete_legacy_files(paths)
        await ctx.send(
            f"Deleted {len(removed)} legacy aicrush file(s)." if removed else "No legacy aicrush files found."
        )
        return
    present = crush_game.legacy_files_present(paths)
    if present:
        await ctx.send(
            f"{len(present)} legacy aicrush file(s) are still on disk. The bot does not read them. "
            f"Delete with `{PREFIX}legacydata wipe confirm`."
        )
    else:
        await ctx.send("No legacy aicrush files are on disk.")


@bot.command(name="exclude")
@commands.guild_only()
async def exclude_command(ctx: commands.Context) -> None:
    CRUSH_GAME.exclude(ctx.guild.id, ctx.author.id)
    save_crush_game_state(force=True)
    await ctx.send(
        "Done. You're excluded from fun features: you will never be analyzed or named in a game "
        f"result, and your stored fun-feature data was deleted. Changed your mind? `{PREFIX}include`."
    )


@bot.command(name="include")
@commands.guild_only()
async def include_command(ctx: commands.Context) -> None:
    CRUSH_GAME.include(ctx.guild.id, ctx.author.id)
    save_crush_game_state(force=True)
    await ctx.send("You're back in the fun features. 🎉")


@bot.command(name="wipe")
@commands.guild_only()
async def wipe_command(ctx: commands.Context) -> None:
    CRUSH_GAME.wipe(ctx.guild.id, ctx.author.id)
    save_crush_game_state(force=True)
    await ctx.send(
        f"Your stored fun-feature data was deleted. To also opt out of fun features, use `{PREFIX}exclude`."
    )


AGENTIC_STATE = agentic_automation.AgenticState()
AGENTIC_RECENT_CASES: dict[tuple[int, int], deque[str]] = defaultdict(lambda: deque(maxlen=10))
# Per-feature daily caps in the budget governor (GROQ_FEATURE_DAILY_CAPS overrides these).
for _agentic_feature, _agentic_env, _agentic_default in (
    (agentic_automation.FEATURE_SCHEDULED, "AGENTIC_SCHEDULED_DAILY_CAP", 50),
    (agentic_automation.FEATURE_ESCALATION, "AGENTIC_ESCALATION_DAILY_CAP", 50),
    (agentic_automation.FEATURE_NUDGE, "AGENTIC_NUDGE_DAILY_CAP", 100),
):
    GROQ_BUDGET.feature_caps.setdefault(_agentic_feature, env_int(_agentic_env, _agentic_default, 1))


def load_agentic_state() -> None:
    global AGENTIC_STATE
    AGENTIC_STATE = agentic_automation.AgenticState(read_state(AGENTIC_STATE_KEY))
    AGENTIC_SCHEDULER.state = AGENTIC_STATE
    AGENTIC_ESCALATION.state = AGENTIC_STATE
    AGENTIC_NUDGES.state = AGENTIC_STATE


def flush_agentic_state() -> None:
    if AGENTIC_STATE.dirty and write_state(AGENTIC_STATE_KEY, AGENTIC_STATE.data):
        AGENTIC_STATE.dirty = False


def get_guild_agentic_config(guild_id: int) -> agentic_automation.AgenticConfig:
    return agentic_automation.config_for_guild(load_mod_config(), guild_id)


def _agentic_raw_block(config: dict, guild_id: int) -> dict:
    guild_cfg = config.setdefault(str(guild_id), {})
    block = guild_cfg.get(agentic_automation.CONFIG_KEY)
    if not isinstance(block, dict):
        block = {}
        guild_cfg[agentic_automation.CONFIG_KEY] = block
    return block


def _agentic_complete(policy_key: str):
    async def complete(messages: list[dict[str, str]]) -> str:
        # Same governor-routed path as &agent, under its own feature cap.
        return await request_ai_completion(
            messages,
            max_tokens=AGENT_MAX_TOKENS,
            temperature=0.2,
            policy_key=policy_key,
            include_fallback_notice=False,
        )

    return complete


async def _agentic_post(channel: Any, text: str) -> None:
    safe, _ = screen_agent_text(text)
    for chunk in split_message(safe):
        await channel.send(chunk, allowed_mentions=AGENT_NO_MENTIONS)


async def _agentic_post_card(channel: Any, action: agent_tools.PendingAction) -> None:
    card, problem = screen_agent_text(agent_tools.render_card(action))
    if problem:
        AGENT_PENDING.expire(action.id)
        await channel.send(f"Agent action #{action.id} was withheld by the safety filter.")
        return
    view = agent_tools.build_pending_action_view(AGENT_PENDING, action)
    view.message = await channel.send(card, view=view, allowed_mentions=AGENT_NO_MENTIONS)


async def _agentic_case_history(guild: discord.Guild, member: Any) -> list[str]:
    # Read-only: stored warnings plus the recent AutoMod cases seen this session.
    lines: list[str] = []
    for entry in load_warnings().get(str(guild.id), {}).get(str(member.id), [])[-5:]:
        if isinstance(entry, dict):
            lines.append(f"Warning: {str(entry.get('reason', ''))[:150]} ({entry.get('timestamp', '?')})")
    lines.extend(AGENTIC_RECENT_CASES.get((guild.id, member.id), []))
    return lines


def _agentic_mod_channel(guild: discord.Guild) -> discord.TextChannel | None:
    channel_id = get_guild_mod_log_channel_id(guild.id)
    channel = guild.get_channel(channel_id) if channel_id else None
    return channel if isinstance(channel, discord.TextChannel) else None


def _agentic_on_escalation_accept(ctx: agent_tools.AgentContext, args: dict[str, Any]) -> None:
    if str(args.get("recommendation")) == "watch":
        member = args.get("member")
        watch = AGENTIC_STATE.guild(ctx.guild.id)["watchlist"]
        watch[str(getattr(member, "id", 0))] = time.time()
        AGENTIC_STATE.mark()


async def _agentic_send_nudge(channel: Any, member_id: int, text: str) -> bool:
    try:
        await channel.send(
            f"<@{member_id}> {text}",
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=[discord.Object(id=member_id)]),
        )
        return True
    except discord.HTTPException:
        return False


AGENTIC_SCHEDULER = agentic_automation.ScheduledTaskScheduler(
    state=AGENTIC_STATE,
    registry=AGENT_REGISTRY,
    pending=AGENT_PENDING,
    complete=_agentic_complete(agentic_automation.FEATURE_SCHEDULED),
    post=_agentic_post,
    post_card=_agentic_post_card,
    limits=AGENT_LIMITS,
)
AGENTIC_ESCALATION = agentic_automation.EscalationMonitor(
    state=AGENTIC_STATE,
    pending=AGENT_PENDING,
    post_card=_agentic_post_card,
    case_history=_agentic_case_history,
    complete=_agentic_complete(agentic_automation.FEATURE_ESCALATION),
    resolve_mod_channel=_agentic_mod_channel,
    on_accept=_agentic_on_escalation_accept,
)
AGENTIC_NUDGES = agentic_automation.NudgeEngine(
    state=AGENTIC_STATE,
    admit_feature=GROQ_BUDGET.try_admit_feature,
    send=_agentic_send_nudge,
)


async def agentic_on_automod_violation(message: discord.Message, action: str, reason: str) -> None:
    if message.guild is None or not isinstance(message.author, discord.Member):
        return
    config = get_guild_agentic_config(message.guild.id)
    if not config.escalation.enabled:
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    AGENTIC_RECENT_CASES[(message.guild.id, message.author.id)].append(
        f"AutoMod: {action} - {reason[:120]} ({stamp} UTC)"
    )
    try:
        await AGENTIC_ESCALATION.on_violation(message.guild, message.author, config)
    except Exception as error:
        print(f"[AGENTIC ESCALATION ERROR] guild={message.guild.id} error={error}")


def _agentic_nudge_candidates(guild: discord.Guild, config: agentic_automation.AgenticConfig):
    opted_in = AGENTIC_NUDGES.opted_in(guild.id)
    if not opted_in:
        return []
    users = get_guild_engagement_state(guild.id).get("users", {})
    if not isinstance(users, dict):
        return []
    tz = _safe_zoneinfo(get_guild_engagement_timezone(guild.id))
    quests_on = config.nudges.quests and get_guild_quest_mode_enabled(guild.id)

    def day_of(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz).strftime("%Y-%m-%d")

    def open_quests(member_id: int) -> int:
        row = users.get(str(member_id))
        if not isinstance(row, dict):
            return 0
        quests, _, completed = get_user_daily_quests(guild.id, row)
        return sum(1 for q in quests if str(q.get("id", "")) not in completed)

    return agentic_automation.build_nudge_candidates(
        {k: v for k, v in users.items() if str(k).isdigit() and int(k) in set(opted_in)},
        opted_in=opted_in,
        today=_guild_day_key(guild.id),
        day_of=day_of,
        open_quests=open_quests if quests_on else None,
    )


async def run_agentic_tick() -> None:
    for guild in bot.guilds:
        config = get_guild_agentic_config(guild.id)
        try:
            if config.scheduled_enabled and is_ai_configured():
                await AGENTIC_SCHEDULER.tick(guild, config)
            if config.nudges.enabled:
                channel = guild.get_channel(config.nudges.channel_id) if config.nudges.channel_id else None
                if channel is None:
                    channel = resolve_engagement_channel(guild)
                await AGENTIC_NUDGES.tick(guild, config, _agentic_nudge_candidates(guild, config), channel)
        except Exception as error:
            print(f"[AGENTIC TICK ERROR] guild={guild.id} error={error}")
    flush_agentic_state()


@tasks.loop(minutes=1.0)
async def agentic_tick_loop() -> None:
    await run_agentic_tick()


@agentic_tick_loop.before_loop
async def _before_agentic_tick_loop() -> None:
    await bot.wait_until_ready()


def _agentic_status_lines(guild: discord.Guild) -> list[str]:
    config = get_guild_agentic_config(guild.id)
    esc, ndg = config.escalation, config.nudges
    lines = [
        f"Scheduled tasks: `{'on' if config.scheduled_enabled else 'off'}`",
    ]
    for task in config.tasks:
        used = AGENTIC_SCHEDULER.calls_today(guild.id, task.name)
        lines.append(
            f"- `{task.name}` [{'enabled' if task.enabled else 'disabled'}] `{task.schedule}` UTC -> "
            f"<#{task.channel_id}> (calls today {used}/{task.daily_cap})"
        )
    lines.append(
        f"Escalation proposals: `{'on' if esc.enabled else 'off'}` (threshold {esc.threshold} in "
        f"{esc.window_hours:g}h, channel {f'<#{esc.mod_channel_id}>' if esc.mod_channel_id else 'mod-log'})"
    )
    lines.append(
        f"Engagement nudges: `{'on' if ndg.enabled else 'off'}` (sent today "
        f"{AGENTIC_NUDGES.sent_today(guild.id)}/{ndg.server_daily_cap}, opted in "
        f"{len(AGENTIC_NUDGES.opted_in(guild.id))})"
    )
    return lines


AGENTIC_USAGE = (
    f"`{PREFIX}agentic status`\n"
    f"`{PREFIX}agentic scheduled on|off`\n"
    f"`{PREFIX}agentic task add <name> | <cron or @daily/@weekly> | #channel | <prompt>`\n"
    f"`{PREFIX}agentic task enable|disable|remove <name>`\n"
    f"`{PREFIX}agentic task cap <name> <calls per day>`\n"
    f"`{PREFIX}agentic escalation on|off [threshold] [#mod-channel]`\n"
    f"`{PREFIX}agentic nudges on|off [#channel] [server daily cap]`\n"
    "New tasks start disabled. Schedules are evaluated in UTC."
)


@bot.command(name="agentic")
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def agentic_command(ctx: commands.Context, *, args: str | None = None) -> None:
    text = (args or "").strip()
    words = text.split()
    sub = words[0].lower() if words else "status"
    if sub == "status":
        await ctx.send("\n".join(_agentic_status_lines(ctx.guild)), allowed_mentions=AGENT_NO_MENTIONS)
        return

    config = load_mod_config()
    block = _agentic_raw_block(config, ctx.guild.id)
    channel_ids = [c.id for c in ctx.message.channel_mentions]

    def toggle(word: str) -> bool | None:
        return {"on": True, "off": False}.get(word.lower())

    if sub in {"scheduled", "escalation", "nudges"} and len(words) >= 2 and toggle(words[1]) is not None:
        key = "scheduled_tasks" if sub == "scheduled" else sub
        section = block.setdefault(key, {})
        section["enabled"] = toggle(words[1])
        numbers = [int(w) for w in words[2:] if w.isdigit()]
        if sub == "escalation":
            if numbers:
                section["threshold"] = max(1, min(100, numbers[0]))
            if channel_ids:
                section["mod_channel_id"] = channel_ids[0]
        if sub == "nudges":
            if numbers:
                section["server_daily_cap"] = max(0, min(agentic_automation.MAX_NUDGE_SERVER_DAILY_CAP, numbers[0]))
            if channel_ids:
                section["channel_id"] = channel_ids[0]
        save_mod_config(config)
        await ctx.send(f"Agentic `{sub}` is now `{words[1].lower()}`.")
        return

    if sub == "task" and len(words) >= 2:
        action = words[1].lower()
        section = block.setdefault("scheduled_tasks", {})
        tasks_raw = section.setdefault("tasks", [])
        if action == "add":
            parts = [p.strip() for p in text.split(None, 2)[2].split("|")] if len(words) > 2 else []
            if len(parts) != 4 or not channel_ids:
                await ctx.send(f"Usage: `{PREFIX}agentic task add <name> | <schedule> | #channel | <prompt>`")
                return
            name, schedule, _, prompt = parts
            try:
                agentic_automation.CronSchedule(schedule)
            except ValueError as error:
                await ctx.send(f"Invalid schedule: {error}")
                return
            if any(str(t.get("name", "")).lower() == name.lower() for t in tasks_raw if isinstance(t, dict)):
                await ctx.send(f"A task named `{name}` already exists.")
                return
            if len(tasks_raw) >= agentic_automation.MAX_TASKS_PER_GUILD:
                await ctx.send(f"At most {agentic_automation.MAX_TASKS_PER_GUILD} tasks per server.")
                return
            task = {"name": name[:50], "schedule": schedule, "channel_id": channel_ids[0],
                    "prompt": prompt[: agentic_automation.MAX_PROMPT_CHARS], "enabled": False,
                    "daily_cap": agentic_automation.DEFAULT_TASK_DAILY_CAP}
            if agentic_automation.parse_task(task) is None:
                await ctx.send("That task is incomplete; name, schedule, channel and prompt are required.")
                return
            tasks_raw.append(task)
            save_mod_config(config)
            await ctx.send(f"Task `{name}` added (disabled). Enable it with `{PREFIX}agentic task enable {name}`.")
            return
        if action in {"enable", "disable", "remove", "cap"} and len(words) >= 3:
            name = words[2]
            match = next((t for t in tasks_raw if isinstance(t, dict) and str(t.get("name", "")).lower() == name.lower()), None)
            if match is None:
                await ctx.send(f"No task named `{name}`.")
                return
            if action == "remove":
                tasks_raw.remove(match)
            elif action == "cap":
                if len(words) < 4 or not words[3].isdigit():
                    await ctx.send(f"Usage: `{PREFIX}agentic task cap <name> <calls per day>`")
                    return
                match["daily_cap"] = max(0, min(agentic_automation.MAX_TASK_DAILY_CAP, int(words[3])))
            else:
                match["enabled"] = action == "enable"
            save_mod_config(config)
            await ctx.send(f"Task `{name}`: {action} done.")
            return

    await ctx.send(AGENTIC_USAGE)


@bot.command(name="nudges")
@commands.guild_only()
async def nudges_command(ctx: commands.Context, setting: str | None = None) -> None:
    choice = (setting or "").strip().lower()
    if choice not in {"on", "off"}:
        state = "on" if AGENTIC_NUDGES.is_opted_in(ctx.guild.id, ctx.author.id) else "off"
        await ctx.send(f"Your streak/quest reminders are `{state}`. Use `{PREFIX}nudges on|off`.")
        return
    AGENTIC_NUDGES.set_opt_in(ctx.guild.id, ctx.author.id, choice == "on")
    flush_agentic_state()
    note = "" if get_guild_agentic_config(ctx.guild.id).nudges.enabled else " (reminders are currently off on this server)"
    await ctx.send(f"Streak/quest reminders `{choice}`{note}.")


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    original_error = getattr(error, "original", error)
    original_text = str(original_error)

    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"Command cooldown active. Try again in `{error.retry_after:.1f}`s.")
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to use this command.")
        return
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send("This command can only be used inside a server channel.")
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing argument: `{error.param.name}`. Use `{PREFIX}help`.")
        return
    if isinstance(error, (commands.BadArgument, commands.MemberNotFound, commands.UserNotFound)):
        await ctx.send("Invalid argument. Use the correct mention/id format.")
        return
    if "pynacl library needed in order to use voice" in original_text.lower():
        await ctx.send(
            "Voice dependency missing on host. Install `PyNaCl` and restart the bot."
        )
        return
    lowered = original_text.lower()
    if "websocket closed with 4006" in lowered or "voice handshake" in lowered:
        await ctx.send(
            "Voice connection failed (`4006`). This is usually a host UDP/network issue, not your command."
        )
        return
    await ctx.send(f"Error: `{error}`")


def main() -> None:
    if not TOKEN:
        raise RuntimeError("DISCORD_BOT_TOKEN is missing. Put it in your .env file.")
    ensure_data_files()
    reload_bad_words()
    load_ai_mod_state()
    load_engagement_state()
    load_crush_game_state()
    load_altfinder_state()
    load_socialintel_state()
    load_business_state()
    load_agentic_state()
    bot.run(TOKEN)


if __name__ == "__main__":
    main()




