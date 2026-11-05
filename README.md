# Discord Moderation Bot

Discord moderation bot with prefix commands (default: `&`).

## Features

- `&pb`: deletes bot/webhook messages from the most recent 20 messages in the current channel.
- `&pba`: deletes all bot/webhook messages from the current channel.
- `&clear <amount>`: bulk deletes recent messages.
- `&bulkdelete <#channel> <amount>`: bulk deletes messages in a specific channel.
- `&kick`, `&ban`, `&unban`
- `&mute`, `&unmute` (Discord timeout based)
- `&lock`, `&unlock`, `&slowmode`
- `&warn`, `&warnings`, `&clearwarns` (stored in `data/warnings.json`)
- `&automod <on|off|toggle|status>` (moderators can control AutoMod per server)
- `&crushgame <on|off|status> [#channel]` (Manage Server) enables the Crush-o-Meter game and posts a one-time fun-features notice
- `&exclude` / `&include` opt out of (or back into) fun features; `&wipe` deletes your stored fun-feature data
- Auto moderation:
  - blocked words from `data/bad_words.txt`
  - link blocking
  - spam detection + automatic timeout
- Mod-log channel support:
  - `&setmodlog [#channel]`
  - `&clearmodlog`
  - logs both manual moderation actions and automod actions
- `&reloadbadwords` to reload bad word entries without restarting the bot
- Utility/fun commands:
  - `&ping`
  - `&avatar [@member]`
  - `&userinfo [@member]`
  - `&serverinfo`
  - `&poll Question | Option 1 | Option 2`
  - `&snipe`
  - `&remind <minutes> <text>`
  - DM the bot with `remove timeout` to remove your active timeout (if bot has permission)
- AI commands:
  - `&ai <prompt>` or `&ask <prompt>`
  - `&agent <request>` (tool-using moderation assistant; see "Agent" below)
  - `&aisummary [count]`
  - `&catchup [hours]`
  - `&catchupchannel <#channel> [hours]`
  - `&serverinsights [hours]` (Manage Server permission required)
  - `&aireset`
  - `&aimodel`
  - `&aimodels [limit]`
  - `&roast @user [soft|friendly|brutal]`
  - `&serverlore`
  - `&crush [@user] [answer]` (Crush-o-Meter joke game, see below)
  - `&analyze @user`
  - `&lie_detector @user <message>`
  - `&futureme`
  - `&rizzcoach [smooth|funny|mysterious] <message>`
  - `&argument <topic>`
  - `&debate @user <topic>`
- Business Empire commands:
  - `&balance`, `&dailyclaim`, `&portfolio`, `&networth`
  - `&stocks`, `&market [symbol]`, `&buy <symbol> <qty>`, `&sell <symbol> <qty>`
  - `&commodities`, `&buycommodity <symbol> <qty>`, `&sellcommodity <symbol> <qty>`
  - `&crypto`, `&buycrypto <symbol> <qty>`, `&sellcrypto <symbol> <qty>`
  - `&plots`, `&buyplot <plot_id>`, `&upgrade <property_id>`, `&properties`
  - `&sellproperty <id> <price>`, `&buyproperty <id>`
  - `&loan`, `&takeloan <amount>`, `&repay <amount>`, `&debts`
  - `&startbiz <type> <name>`, `&mybiz`, `&bizhire <id> <count>`, `&bizfire <id> <count>`, `&bizexpand <id>`
  - `&salary`, `&taxes`, `&filetax [amount]`, `&credit`, `&markethalt`, `&economystatus`
  - `&trade ...`, `&trade_accept <id>`, `&trade_decline <id>`
  - `&auction_start ...`, `&bid <auction_id> <amount>`, `&auctions`
  - `&bizleaderboard [cash|networth|income]`, `&bizprofile [@user]`, `&marketnews`, `&ledger [@user]`
  - `&bizadmin ...` (moderator-only economy controls)
- Vibe commands:
  - `&myvibe [count]`
  - `&vibe @user [count]`
  - `&vibecheck @user`
- Music commands:
  - `&join`, `&leave`
  - `&play <youtube/spotify link or search>`
  - `&skip`, `&pause`, `&resume`, `&stop`
  - `&queue`, `&nowplaying`
  - Spotify playlist links are supported
- `&help`

Most new AI fun commands are hybrid, so you can use both prefix (`&...`) and slash (`/...`) after command sync.

## Setup

1. Create and activate a virtual environment (recommended).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and set `DISCORD_BOT_TOKEN`.
4. If using AI features, set one provider:
   - OpenRouter:
     - `AI_PROVIDER=openrouter`
     - `OPENROUTER_API_KEY=...`
   - Groq:
     - `AI_PROVIDER=groq`
     - `GROQ_API_KEY=...`
5. If using music features:
   - Make sure `ffmpeg` is installed on your host.
   - For Spotify links/playlists, set:
     - `SPOTIFY_CLIENT_ID=...`
     - `SPOTIFY_CLIENT_SECRET=...`
6. Enable bot intents in Discord Developer Portal:
   - `MESSAGE CONTENT INTENT`
   - `SERVER MEMBERS INTENT`
7. Run:
   ```bash
   python bot.py
   ```

## Optional Environment Variables

- `MOD_LOG_CHANNEL_ID=` fallback mod-log channel id if `&setmodlog` is not used.
- `BOT_ACTIVITY_TEXT=with your crush`
- `AUTOMOD_ENABLED=false`
- `AUTOMOD_BLOCK_LINKS=true`
- `AUTOMOD_SPAM_MSG_THRESHOLD=6`
- `AUTOMOD_SPAM_INTERVAL_SECONDS=8`
- `AUTOMOD_SPAM_TIMEOUT_MINUTES=5`
- `OPENROUTER_API_KEY=`
- `OPENROUTER_MODEL=google/gemma-3-4b-it:free`
- `OPENROUTER_API_URL=https://openrouter.ai/api/v1/chat/completions`
- `OPENROUTER_MODELS_URL=https://openrouter.ai/api/v1/models`
- `OPENROUTER_APP_NAME=Discord Mod Bot`
- `OPENROUTER_HTTP_REFERER=`
- `AI_PROVIDER=openrouter`
- `GROQ_API_KEY=`
- `GROQ_MODEL=openai/gpt-oss-120b`
- `GROQ_API_URL=https://api.groq.com/openai/v1/chat/completions`
- `GROQ_MODELS_URL=https://api.groq.com/openai/v1/models`
- `AI_MAX_HISTORY=4`
- `AI_MAX_TOKENS=260`
- `AI_SUMMARY_MAX_TOKENS=320`
- `AI_CATCHUP_MAX_TOKENS=360`
- `AI_INSIGHTS_MAX_TOKENS=420`
- `AI_TIMEOUT_SECONDS=45`
- `SYNC_SLASH_COMMANDS=true`
- `VIBE_DEFAULT_MESSAGE_COUNT=200`
- `VIBE_MAX_MESSAGE_COUNT=800`
- `VIBE_MIN_REQUIRED_MESSAGES=25`
- `VIBE_MAX_PROMPT_MESSAGES=80`
- `VIBE_MAX_PROMPT_CHARS=12000`
- `AICRUSH_SCAN_PER_CHANNEL=450` (shared history-scan tuning for roast; the old aicrush command is gone)
- `AICRUSH_MAX_CHANNELS=0` (`0` means scan all visible text channels)
- `AICRUSH_FULL_HISTORY_SCAN=true`
- `AICRUSH_MAX_HISTORY_MESSAGES=12000` (per-run safety cap)
- `AICRUSH_SCAN_PAUSE_EVERY=260` (small pacing interval)
- `AICRUSH_SCAN_PAUSE_SECONDS=0.12` (sleep duration for pacing)
- `AICRUSH_CACHE_SECONDS=900` (reuse recent result to avoid repeated scans)
- `BUSINESS_ENABLED=true`
- `BUSINESS_STATE_FLUSH_SECONDS=30`
- `BUSINESS_GLOBAL_MODE=true`
- `BUSINESS_STARTER_CASH=10000`
- `BUSINESS_DAILY_CLAIM=1500`
- `BUSINESS_DAILY_CLAIM_STREAK_BONUS=250`
- `BUSINESS_HOURLY_INTEREST_RATE=0.0012`
- `BUSINESS_LOAN_GRACE_HOURS=24`
- `BUSINESS_MAX_DEBT_TO_NETWORTH=1.8`
- `BUSINESS_STOCK_COUNT=16`
- `BUSINESS_MARKET_EVENT_CHANCE=0.18`
- `BUSINESS_TRANSACTION_FEE_RATE=0.01`
- `BUSINESS_PROPERTY_MAINTENANCE_RATE=0.004`
- `BUSINESS_PROPERTY_TAX_RATE=0.006`
- `BUSINESS_AUCTION_SNIPING_WINDOW_SECONDS=30`
- `BUSINESS_AUCTION_SNIPING_EXTEND_SECONDS=60`
- `BUSINESS_MAX_OPEN_TRADES=5`
- `BUSINESS_MAX_OPEN_AUCTIONS=3`
- `BUSINESS_COMMAND_COOLDOWN_SECONDS=3`
- `BUSINESS_LEDGER_MAX_ENTRIES=50000`
- `BUSINESS_AI_PERSONALIZATION_ENABLED=true`
- `BUSINESS_AI_TUNING_ENABLED=true`
- `BUSINESS_AI_MAX_TOKENS=140`
- `BUSINESS_AI_PERSONALIZATION_CACHE_SECONDS=900`
- `BUSINESS_AI_DIRECTOR_INTERVAL_HOURS=3`
- `BUSINESS_SCHEMA_VERSION=2`
- `BUSINESS_MARKET_TICK_MINUTES=15`
- `BUSINESS_WORLD_EVENT_INTERVAL_MINUTES=120`
- `BUSINESS_WEEKLY_CYCLE_DAYS=7`
- `BUSINESS_EVENT_MAX_PER_DAY=6`
- `BUSINESS_ENABLE_COMMODITIES=true`
- `BUSINESS_ENABLE_CRYPTO=true`
- `BUSINESS_ENABLE_PRIVATE_BUSINESSES=true`
- `BUSINESS_CIRCUIT_BREAKER_DROP_PCT=25`
- `BUSINESS_MARKET_HALT_DROP_PCT=15`
- `BUSINESS_CAPITAL_GAINS_SHORT_RATE=0.15`
- `BUSINESS_CAPITAL_GAINS_LONG_RATE=0.10`
- `BUSINESS_CAPITAL_GAINS_LONG_HOLD_DAYS=7`
- `BUSINESS_INCOME_TAX_ENABLED=true`
- `CRUSH_GAME_DAILY_CAP=50` (bot-wide daily cap for `&crush`, enforced by the budget governor)
- `CRUSH_GAME_FLAVOR_DAILY_CAP=50` (daily cap for the optional one-line AI joke, Groq only)
- `VOICE_CONNECT_RETRIES=4`
- `VOICE_CONNECT_TIMEOUT=25`
- `VOICE_INTERNAL_RECONNECT=false`
- `WELCOME_DM_ENABLED=true`
- `WELCOME_MAX_CHANNEL_SUGGESTIONS=5`
- `CATCHUP_DEFAULT_HOURS=24`
- `CATCHUP_MAX_HOURS=168`
- `CATCHUP_MAX_MESSAGES=180`
- `INSIGHTS_DEFAULT_HOURS=48`
- `INSIGHTS_MAX_HOURS=168`
- `INSIGHTS_MAX_CHANNELS=10`
- `INSIGHTS_MAX_MESSAGES_PER_CHANNEL=350`
- `INSIGHTS_CHANNEL_SCAN_LIMIT=30`
- `ROAST_CONTEXT_TARGET_MESSAGES=220`
- `ROAST_CONTEXT_MIN_MESSAGES=35`
- `ROAST_CHANNEL_SCAN_LIMIT=14`
- `ROAST_HISTORY_PER_CHANNEL=280`
- `ROAST_CACHE_MAX_MESSAGES=1400`
- `OPENROUTER_FALLBACK_MODELS=google/gemma-3-4b-it:free,qwen/qwen3-4b:free,deepseek/deepseek-r1-0528:free`
- `GROQ_FALLBACK_MODELS=openai/gpt-oss-20b,qwen/qwen3.8-27b`
- `GROQ_LIMIT_RPM=30`
- `GROQ_LIMIT_RPD=1000`
- `GROQ_LIMIT_TPM=8000`
- `GROQ_LIMIT_TPD=200000`
- `GROQ_MODEL_LIMITS=`
- `GROQ_FEATURE_DAILY_CAPS=`
- `GROQ_FEATURE_DAILY_CAP_DEFAULT=0`
- `GROQ_BUDGET_MAX_WAIT_SECONDS=20`
- `GROQ_DEFAULT_RETRY_AFTER_SECONDS=60`
- `GROQ_QUEUE_MAX=100`
- `GROQ_BUDGET_STATE_FILE=` (default `data/groq_budget_state.json`)
- `DATABASE_URL=` (empty = JSON files under `data/`; see [Storage](#storage-phase-5))
- `GROQ_ALLOW_ENTERPRISE_MODELS=0`
- `AGENT_DAILY_CAP=20`
- `AGENT_MAX_TOKENS=500`
- `AGENTIC_SCHEDULED_DAILY_CAP=50`
- `AGENTIC_ESCALATION_DAILY_CAP=50`
- `AGENTIC_NUDGE_DAILY_CAP=100`
- `FFMPEG_PATH=ffmpeg`
- `MUSIC_MAX_PLAYLIST_ITEMS=50`
- `SPOTIFY_CLIENT_ID=`
- `SPOTIFY_CLIENT_SECRET=`

## Groq Budget Governor

Every Groq chat completion goes through `groq_budget.py`, which keeps the bot inside Groq's free tier
(defaults: 30 requests/min, 1,000 requests/day, 8K tokens/min, 200K tokens/day per model):

- Per-model token buckets for RPM/RPD/TPM/TPD (`GROQ_LIMIT_*`; per-model overrides via
  `GROQ_MODEL_LIMITS=model=rpm:rpd:tpm:tpd;other=...`).
- FIFO request queue: a short wait for minute budgets (up to `GROQ_BUDGET_MAX_WAIT_SECONDS`) is spent in line.
- Optional per-feature daily caps: `GROQ_FEATURE_DAILY_CAPS=ai_chat=300,crush_game=50`
  (feature names are the AI `policy_key`s; `GROQ_FEATURE_DAILY_CAP_DEFAULT=0` means unlimited).
- Automatic fallback to the next model on HTTP 429 or an exhausted budget.
- When every model is out of budget, AI commands reply "AI budget used up for today" without calling Groq.
- Usage counters are saved through the storage adapter (default: `GROQ_BUDGET_STATE_FILE`, atomic JSON
  writes after every change) and loaded on start, so a restart does not reset daily allowances. With the
  default JSON file one bot process per state file is assumed; counters are only multi-process safe when
  `DATABASE_URL` is configured (see [Storage](#storage-phase-5)).
- Default model chains use only free-tier models. Enterprise-tier models (`llama-3.3-70b-versatile`,
  `llama-3.1-8b-instant`, `moonshotai/kimi-k2-*`) are dropped from every chain, including env-provided ones,
  unless `GROQ_ALLOW_ENTERPRISE_MODELS=1`.

## Storage (phase 5)

All persistent state goes through `storage.py`. Every state area is one JSON document under a short key;
no feature reads or writes the JSON files directly. Two backends implement the same interface
(`get`/`set`/`delete`/`list_keys`/`update`/`version`, plus async `aget`/`aset`/`adelete`/`alist_keys`/`aupdate`):

- `JsonFileBackend` (default): the same files and formats as before. Writes go to a temp file and are
  moved into place with `os.replace` (falling back to a direct write where a filesystem cannot replace);
  most areas are also mirrored to `<file>.bak`, which is read when the main file is empty or corrupt.
  Missing files are seeded with the same defaults as before.
- `PostgresBackend`: used only when `DATABASE_URL` is set. Needs `asyncpg` (in `requirements.txt`, but
  imported lazily, so the bot runs without it). Nothing connects until the first storage call.

### Storage layout

| key | file (JSON backend) | format | `.bak` | table (Postgres) | contents |
| --- | --- | --- | --- | --- | --- |
| `guild_settings` | `data/mod_config.json` | indent=2 | yes | `bell_guild_settings` | Per-guild settings: moderation config, mod-log channel, feature toggles and the agentic automation config block (`agentic`). |
| `warnings` | `data/warnings.json` | indent=2 | yes | `bell_warnings` | Manual moderator warnings per guild/user. |
| `mod_log` | `data/ai_mod_state.json` | indent=2 | yes | `bell_mod_log` | AI moderation case log: cases, appeals, review actions, user risk, metrics. |
| `engagement` | `data/engagement_state.json` | indent=2 | yes | `bell_engagement` | XP, levels, streaks, daily quests per guild member. |
| `economy` | `data/business_state.json` | indent=2 | yes | `bell_economy` | Economy / business simulation state. |
| `altfinder` | `data/altfinder_state.json` | indent=2 | yes | `bell_altfinder` | Alt-account detection state. |
| `socialintel` | `data/socialintel_state.json` | indent=2 | yes | `bell_socialintel` | Social graph / interaction statistics. |
| `capabilities_overrides` | `data/capabilities_overrides.json` | indent=2 | no | `bell_capabilities_overrides` | Owner overrides for the capability catalog. |
| `capabilities_catalog` | `data/capabilities_catalog.json` | indent=2 | no | `bell_capabilities_catalog` | Generated capability catalog (rebuilt from commands; cache). |
| `crush_game` | `data/crush_game.json` | indent=2 | yes | `bell_crush_game` | Consent-first crush joke game state. |
| `agentic_state` | `data/agentic_state.json` | indent=2 | yes | `bell_agentic_state` | Agentic automation runtime state: scheduled tasks, escalation proposals, nudge history. |
| `groq_budget` | `data/groq_budget_state.json` (or `GROQ_BUDGET_STATE_FILE`) | compact, sorted keys, fsync | no | `bell_groq_budget` | Groq budget governor counters (token buckets, feature caps, circuit breaker). |

`data/bad_words.txt` is a plain text word list and stays a file. `data/aicrush_state.json` (removed
history-mining feature) is deleted at startup and is never migrated.

### Schema

`db/schema.sql` creates (idempotently):

- `bell_documents(doc_name PRIMARY KEY, version, updated_at)`: which documents exist; `version` increments on
  every write and is the cache token for the capability catalog.
- One table per area (names above), each `(doc_key TEXT PRIMARY KEY, position INTEGER, value JSONB)`: one row
  per top-level key of the document (e.g. one row per guild id in `bell_guild_settings`), with `position`
  keeping the original key order. A document is read back as `{doc_key: value, ...}`, equal to the JSON file.
  JSONB normalises the key order *inside* nested objects; values and dict equality are unchanged.

Writes replace the area's rows in one transaction. `update()` (read-modify-write) holds a per-document
`pg_advisory_xact_lock`, which is what makes the Groq budget counters safe to share between several bot
processes. With the JSON backend the counters stay single-process, exactly as before.

### Migrating to Postgres later

Nothing in this repository connects to a database by default. When you decide to move, with the bot **stopped**:

1. Back up the JSON state: `cp -r data data.backup-$(date +%Y%m%d)`
2. Install the driver: `pip install -r requirements.txt`
3. Preview what would be copied (reads files only, no database connection):
   `python db/migrate_json_to_postgres.py --dry-run`
   (add `--data-dir PATH` if your data lives elsewhere, `--json` for machine-readable output; a custom
   `GROQ_BUDGET_STATE_FILE` is picked up from the environment or `--groq-budget-file PATH`).
   Fix any area reported as `unreadable` before continuing.
4. Create an empty PostgreSQL database and a user for the bot, then put the connection string in `.env`
   (never commit it): `DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME`
5. Create the tables and copy the data (the URL is read from the environment only and never printed):
   `set -a; . ./.env; set +a; python db/migrate_json_to_postgres.py --apply-schema`
   Each area is read back and compared after writing (`migrated <key>: N rows -> <table> (verified)`).
   Areas already present in the database are skipped unless you pass `--overwrite`.
   (Equivalent for the schema step: `psql "$DATABASE_URL" -f db/schema.sql`.)
6. Start the bot with `DATABASE_URL` set. It now reads and writes Postgres; the JSON files are left untouched
   as a fallback.

To roll back, stop the bot and clear `DATABASE_URL`; it uses the JSON files again (changes made while on
Postgres are not copied back).

## Agent

`&agent <request>` runs a plan-act-check loop (`agent_core.py`) over a tool registry (`agent_tools.py`)
built from existing bot functions. It uses the normal AI completion path (Groq requests go through the
governor under the `agent` feature), replies only in the channel where it was invoked, and screens its
output with the bot's blocked-word list and AI-guard heuristics before posting.

- Read-only tools run immediately: `member_info`, `channel_info`, `warn_count`, `modlog_tail`
  (these two are moderator-only), `xp_lookup`, `economy_lookup`, `search_messages` (the bot's in-memory
  message buffers, limited to channels the requester can read).
- Consequential tools never run directly: `warn`, `timeout`, `lock_channel`, `unlock_channel`,
  `post_message`, `schedule_followup`. Each becomes a card with Confirm / Cancel buttons. Only a member
  who passes the bot's moderator check (plus the tool's Discord permission, e.g. Moderate Members for
  `timeout`) can confirm; the requester or any moderator can cancel; cards expire after 10 minutes.
  Every confirmed execution (and any failure) is written to the mod-log.
- Limits: at most 5 tool calls per request, 60 seconds overall, `AGENT_DAILY_CAP` requests per user per
  UTC day (default 20).

Run the tests with `pip install -r requirements-dev.txt && python -m pytest`.

## Agentic Automation

`agentic_automation.py` lets the bot run agent work on its own, inside hard limits. **Everything is off by
default** and enabled per server (Manage Server permission) with `&agentic`; settings live in the server's
`"agentic"` block in `data/mod_config.json`, runtime counters in `data/agentic_state.json`. With no block,
nothing runs. A one-minute `discord.ext.tasks` loop (like the other bot loops) drives the scheduler and nudges.

- **Scheduled agent tasks** (`&agentic scheduled on`, `&agentic task add <name> | <schedule> | #channel | <prompt>`,
  `&agentic task enable <name>`, `&agentic task cap <name> <n>`): each task has a name, a 5-field cron schedule
  evaluated in UTC (or `@daily` / `@weekly` / `@hourly` / `@monthly`), a target channel, a prompt and an
  enabled flag (new tasks start disabled). Runs go through the same `agent_core` loop, tool registry and
  pending-action manager as `&agent`, so consequential tools only produce Confirm cards; a scheduled run never
  executes them. Each task has its own daily model-call cap (default 10), and all scheduled runs share the
  governor feature `agent_scheduled`.
- **Escalation proposals** (`&agentic escalation on [threshold] [#mod-channel]`): when AutoMod records
  `threshold` violations (default 3) by a member within 24h, the agent reads the member's warnings and recent
  AutoMod cases (read-only), and posts ONE proposal card (timeout / ban / watch) to the mod channel (default:
  the mod-log channel). At most one proposal per member per 24h. Confirm only acknowledges it in the mod-log;
  nothing is applied automatically. Governor feature: `agent_escalation`.
- **Engagement nudges** (`&agentic nudges on [#channel] [server daily cap]`): templated streak reminders
  (streak still alive, not active yet today) and open-quest reminders, only for members who opted in with
  `&nudges on`. At most one nudge per member per day, `server daily cap` per server per day (default 10), and
  each nudge must be admitted by the governor's `engagement_nudge` daily cap (no model call).

The governor caps for these features default to the `AGENTIC_*_DAILY_CAP` values above; `GROQ_FEATURE_DAILY_CAPS`
overrides them. `&agentic status` shows what is on and today's usage.

## Required Bot Permissions

Depending on which commands you use:
- Manage Messages
- Kick Members
- Ban Members
- Moderate Members
- Manage Channels
- Read Message History

## Notes

- `&pb` checks only the latest 20 messages and removes bot/webhook messages there.
- `&pba` scans full channel history and may take time on very large channels due to API rate limits.
- `data/bad_words.txt` is auto-created at first run; add one blocked word per line.
- AI commands work after provider key is set (`OPENROUTER_API_KEY` or `GROQ_API_KEY`).
- If your selected model becomes unavailable, bot auto-falls back to another free model.
- For fastest replies, use smaller models and lower `AI_MAX_TOKENS`.
- Spotify links require Spotify API credentials; otherwise only YouTube/search playback works.
- Spotify playlists must be Public when using client credentials (`SPOTIFY_CLIENT_ID/SECRET`).
- If hosted voice keeps failing with websocket `4006`, this is usually host/node UDP/network routing. Try another node/provider.
- Vibe reports are fun-only and may be inaccurate.
- Vibe output is paragraph-style and considers both the user’s messages and replies they receive (in the same channel window).
- Vibe analysis reads recent messages on-demand in the current channel; it does not store long-term message archives.
- New members can receive an optional AI onboarding DM with channel suggestions.
- `&catchup` summarizes missed conversation from recent hours without scanning full history.
- `&serverinsights` generates channel-level engagement insights for moderators.
- Roast now uses cached + bounded guild-wide message context for faster, more specific results.
- Business economy is persisted in `data/business_state.json` and shared globally across servers where the bot is present.
- Economy uses fast buckets: market tick every 15 minutes, world event tick every 2 hours, and weekly settlement cycle every 7 days.
- Stocks + commodities + crypto now share risk controls (cost basis, gains tax, temporary asset halts, market-wide halts).
- Private businesses settle in weekly cycles with payroll/maintenance/debt pressure and controlled liquidation on prolonged stress.
- Optional LLM market director can safely nudge economy values (market bias, event chance, small tax/fee shifts) within bounded ranges.
- Optional LLM advisor adds personalized one-line strategy tips in business commands with cache to avoid lag.
- If vibe AI times out, the bot falls back to a local heuristic narrative summary.

## Crush-o-Meter game (phase 4)

`&crush` replaced the old `&aicrush`, which mined members' message history. The new game:

- Is about the person who runs it. It only uses what you deliberately give it: `&crush <answer>`
  (your answer to a fun prompt), or one of **your own** messages you reply to while running it.
- `&crush @member` is a random dice-roll pairing, and the result says so. Nothing about that
  member (messages, activity, roles) is looked at, and nobody is assigned real feelings.
  Without a member, you are paired with a fictional character.
- Never reads DMs, never scans history, and does not tally anyone's messages.
- Off by default. A moderator runs `&crushgame on #channel`; the first time, the bot posts one
  notice in that channel naming `&exclude` and `&wipe`. Re-enabling never re-posts it.
- `&exclude` (any time): you can't be named or play, your saved answer is deleted, and other
  member-targeted fun commands (`roast`, `analyze`, `vibe`, `vibecheck`, `lie_detector`, `debate`,
  `myvibe`) refuse to analyze you. `&include` undoes it. `&wipe` deletes your saved answer.
- Every result ends with a fixed "just a joke" disclaimer, and every play counts against the
  `crush_game` daily cap in the budget governor.
- On startup the legacy `data/aicrush_state.json` (and its backup) is deleted.
