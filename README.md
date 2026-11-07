# Bell

Bell is a consent-first Discord community bot with agentic AI. It moderates, runs engagement and an
in-server economy, hosts a few opt-out-able fun games, and includes a tool-using AI agent. Anything
that acts on its own is **off by default** and has to be switched on per server by a moderator.

"Consent-first" means:

- Members can opt out of every member-targeted fun feature with `&exclude`, and delete their stored
  fun-feature data with `&wipe`.
- The Crush-o-Meter game only uses what the player deliberately types into it. It never reads
  message history, DMs, or anyone else's messages.
- The agent can *read* a few things, but any action with consequences (warn, timeout, lock a
  channel, post a message) becomes a Confirm / Cancel card that a moderator has to click.
- Automation (scheduled agent tasks, escalation proposals, engagement nudges) is off until a server
  turns it on, and member nudges also need each member's own `&nudges on`.

> **Status: hobby / pre-production.** None of this has been proven in production. The test suite
> covers the logic with fakes; see [What has and hasn't been tested](#what-has-and-hasnt-been-tested).

Further docs:

- [docs/DEMO.md](docs/DEMO.md): a scripted walkthrough for a private test server, using only
  synthetic data.
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): self-hosting, storage options (JSON or Postgres),
  owner-only decisions, logs.
- [docs/TESTING.md](docs/TESTING.md): the offline suite, the PostgreSQL integration tests and CI.
- [.env.example](.env.example): every supported environment variable, with a comment and a safe
  default.

## Feature tour

The default prefix is `&` (`BOT_PREFIX`). `&help` lists the commands. Many fun and AI commands are
hybrid commands, so they also work as `/slash` commands once slash commands have synced.

### Moderation

- Manual tools: `&kick`, `&ban`, `&unban`, `&mute` / `&unmute` (Discord timeouts), `&warn`,
  `&warnings`, `&clearwarns`, `&lock` / `&unlock`, `&slowmode`, `&clear <n>`,
  `&bulkdelete <#channel> <n>`, `&pb` / `&pba` (remove bot and webhook messages).
- AutoMod (`&automod on|off|status`): a blocked-word list (`data/bad_words.txt`, reload with
  `&reloadbadwords`), link blocking, and spam detection with an automatic timeout. Off unless
  `AUTOMOD_ENABLED=true` or a moderator turns it on.
- AI moderation guard (`&aiguard`, `&aimodmode`): optional AI-assisted case review with a shadow
  period. Off by default (`AI_MOD_ENABLED=false`).
- Mod log: `&setmodlog [#channel]` / `&clearmodlog`. Manual actions, AutoMod actions and every
  confirmed agent action are logged there.

### Engagement

- XP, levels, daily streaks and quests (`ENGAGEMENT_ENABLED`, `XP_*`, `STREAK_*`, `QUEST_*`).
- Optional welcome concierge DM for new members, with channel suggestions.
- AI conversation helpers: `&ai` / `&ask`, `&aisummary`, `&catchup`, `&serverinsights`, plus fun
  commands such as `&roast`, `&vibe`, `&futureme`, `&rizzcoach`, `&argument` and `&debate`.
  Member-targeted ones refuse to analyse anyone who used `&exclude`.
- Music: `&join`, `&play <link or search>`, `&queue`, `&skip`, and so on. Needs `ffmpeg`. Spotify
  links need `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET`.

### Economy

A simulated "Business Empire": cash and daily claims, stocks, commodities, crypto, property,
loans, private businesses, taxes, trades and auctions (`&balance`, `&dailyclaim`, `&stocks`,
`&buy`, `&startbiz`, `&trade`, `&auction_start`, `&bizleaderboard`, ...). By default it is shared
across every server the bot is in (`BUSINESS_GLOBAL_MODE=true`). An optional AI "market director"
and an AI advisor can nudge it within bounded ranges (`BUSINESS_AI_*`).

### The Crush-o-Meter consent game

`&crush` is a party game about the person who runs it. It replaced an older command that mined
members' message history; that command and its data path are gone.

- It only uses what the player deliberately gives it: `&crush <answer>` (an answer to a fun prompt),
  or one of the player's **own** messages that they reply to while running the command. A message
  written by anyone else is ignored.
- `&crush @member` is a seeded daily dice roll, and the result says so. Nothing about that member
  (messages, activity, roles) is looked at. Without a member, the player is paired with a fictional
  character (a houseplant, a raccoon, a haunted rubber duck, ...).
- It never reads DMs, never scans history and never tallies anyone's messages.
- Off by default. A moderator runs `&crushgame on #channel`; the first time, the bot posts one notice
  in that channel naming `&exclude` and `&wipe`. Turning it on again never re-posts the notice.
- `&exclude` (any time) stops you being named or playing, deletes your saved answer, and makes the
  other member-targeted fun commands refuse to analyse you. `&include` undoes it. `&wipe` deletes
  your saved answer.
- Every result ends with a fixed "just a joke" disclaimer, and every play counts against the
  `crush_game` daily cap (`CRUSH_GAME_DAILY_CAP`, default 50).
- Optional AI joke line: only when the provider is Groq. The prompt contains the player's display
  name, the partner's display name (or the fictional character), the player's own answer and the
  random score. It has its own daily cap (`CRUSH_GAME_FLAVOR_DAILY_CAP`). Without Groq the game is
  template-only and makes no model call.
- Old data from the removed command (`data/aicrush_state.json`) is never read, written, migrated or
  deleted automatically. Only the bot owner can delete it, with `&legacydata wipe confirm`.

### Agent tools (`&agent`)

`&agent <request>` runs a plan-act-check loop (`agent_core.py`) over a tool registry
(`agent_tools.py`) built from existing bot functions. It replies only in the channel where it was
invoked, and its output is screened with the blocked-word list and the AI-guard heuristics before
posting.

- Read-only tools run straight away: `member_info`, `channel_info`, `warn_count` and `modlog_tail`
  (these two are moderator-only), `xp_lookup`, `economy_lookup`, and `search_messages` (the bot's
  in-memory message buffers, limited to channels the requester can read).
- Consequential tools never run directly: `warn`, `timeout`, `lock_channel`, `unlock_channel`,
  `post_message` and `schedule_followup` each become a Confirm / Cancel card. Only a member who passes
  the bot's moderator check (plus the tool's own Discord permission, for example Moderate Members for
  `timeout`) can confirm. The requester or any moderator can cancel. Cards expire after 10 minutes.
  Every confirmed execution, and every failure, is written to the mod log.
- Limits: at most 5 tool calls per request, 60 seconds overall, and `AGENT_DAILY_CAP` requests per
  user per UTC day (default 20).

### Agentic automation (all default-OFF)

`agentic_automation.py` lets the bot run agent work on its own, inside hard limits. **Nothing runs
until a server enables it** with `&agentic` (Manage Server permission). Settings live in the
server's `agentic` block of the guild settings; with no block, nothing runs. `&agentic status` shows
what is on and today's usage.

- **Scheduled agent tasks** (`&agentic scheduled on`, then
  `&agentic task add <name> | <schedule> | #channel | <prompt>` and `&agentic task enable <name>`):
  5-field cron in UTC, or `@hourly` / `@daily` / `@weekly` / `@monthly`. New tasks start
  **disabled**. Runs use the same agent loop and tool registry as `&agent`, so consequential tools
  only ever produce Confirm cards; a scheduled run never executes them. Each task has its own daily
  model-call cap (default 10, `&agentic task cap <name> <n>`). Governor feature: `agent_scheduled`.
- **Escalation proposals** (`&agentic escalation on [threshold] [#mod-channel]`): when AutoMod
  records `threshold` violations (default 3) by one member within 24 hours, the agent reads that
  member's warnings and recent AutoMod cases (read-only) and posts **one** proposal card (timeout,
  ban or watch) to the mod channel. At most one proposal per member per 24 hours. Confirm only
  records the decision in the mod log; **nothing is applied automatically**. Governor feature:
  `agent_escalation`.
- **Engagement nudges** (`&agentic nudges on [#channel] [server daily cap]`): templated streak and
  open-quest reminders (no model call), only for members who opted in with `&nudges on`. At most one
  nudge per member per day and `server daily cap` per server per day (default 10). Each nudge must
  also be admitted by the governor's `engagement_nudge` daily cap.

Separate from `&agentic`, two older proactive features also exist and are off unless enabled:
auto engagement loops (`AUTO_LOOPS_ENABLED`, code default `false`) and proactive thread revival
(`THREADREVIVE_PROACTIVE_ENABLED`, code default `false`).

## Architecture

```
                 Discord gateway
                        │
                        ▼
 ┌───────────────────────────────────────────────────────────────┐
 │ bot.py  (discord.py commands, events, background task loops)  │
 │  moderation · engagement · economy · music · fun · AI helpers │
 └──┬──────────────┬──────────────────┬───────────────┬──────────┘
    │              │                  │               │
    ▼              ▼                  ▼               ▼
 agent_core.py  agentic_automation.py  crush_game.py   request_groq_completion
 (plan-act-     (scheduler, escalation, (consent game)          │
  check loop)    nudges)                                        ▼
    │              │                                    groq_budget.py
    ▼              │                                    (budget governor:
 agent_tools.py ◄──┘                                     RPM/RPD/TPM/TPD,
 (tool registry,                                         feature caps,
  pending actions)                                       model fallback,
                                                         fail closed)
                        all persistent state                    │
                                 │                              │
                                 ▼                              ▼
                     storage.py (storage adapter) ◄─────────────┘
                     ├─ JsonFileBackend  (default: data/*.json)
                     └─ PostgresBackend  (only if DATABASE_URL is set)
```

- **`bot.py`**: the Discord bot itself. Reads configuration from the environment (via
  `python-dotenv`), registers commands and events, and wires the modules below together. It is a
  large single file.
- **`agent_core.py`**: the `&agent` loop. Asks the model for one JSON decision at a time (call a
  tool or give the final reply) and enforces the tool-call, time and daily limits.
- **`agent_tools.py`**: the tool registry. Read-only tools run immediately; consequential tools
  return a pending action that bot.py turns into a Confirm / Cancel card.
- **`agentic_automation.py`**: scheduled tasks, escalation proposals and nudges. Does not import
  discord; bot.py injects the Discord callbacks.
- **`crush_game.py`**: the Crush-o-Meter game. Also discord-free.
- **`groq_budget.py`**: the Groq budget governor. Every Groq chat completion goes through it.
- **`storage.py`**: the storage adapter. Every piece of durable state is one JSON document under a
  short key (`guild_settings`, `warnings`, `economy`, `crush_game`, `groq_budget`, ...). The default
  `JsonFileBackend` keeps one file per key under `data/` with atomic writes and a `.bak` mirror. The
  optional `PostgresBackend` is used only when `DATABASE_URL` is set. See
  [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full layout and migration steps.
- **`db/`**: `schema.sql` for the Postgres backend and `migrate_json_to_postgres.py` for copying
  existing JSON state into it.

## Quickstart

### 1. Requirements

- Python **3.10 or newer** (command signatures use `X | None` syntax, which discord.py evaluates
  at runtime). The test suite was last run on Python 3.13; older versions have not been checked.
- `ffmpeg` on the host, only if you want music.
- A Discord application and bot token.
- Optional: a Groq API key (recommended AI provider, protected by the budget governor) or an
  OpenRouter key.

### 2. Install

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

`asyncpg` is in `requirements.txt` but is only imported when `DATABASE_URL` is set.

### 3. Create the bot in the Discord Developer Portal

1. Go to <https://discord.com/developers/applications> and click **New Application**.
2. Open **Bot**, then **Reset Token**, and copy the token. It goes in `.env` as
   `DISCORD_BOT_TOKEN`. Never commit it.
3. On the same page, under **Privileged Gateway Intents**, enable **Message Content Intent** and
   **Server Members Intent**. (Presence Intent is only needed if you set
   `DISCORD_ENABLE_PRESENCE_INTENT=true`.)
4. Open **OAuth2 → URL Generator**. Select the scopes `bot` and `applications.commands`. Under bot
   permissions, pick what you will use: View Channels, Send Messages, Embed Links, Read Message
   History, Manage Messages, Moderate Members, Kick Members, Ban Members, Manage Channels, and Connect
   and Speak for music.
5. Open the generated URL and invite the bot to a **private test server** first.

### 4. Configure `.env`

```bash
cp .env.example .env
```

Set at least `DISCORD_BOT_TOKEN`. For AI features set `AI_PROVIDER=groq` and `GROQ_API_KEY`.
Everything else has a safe default; [.env.example](.env.example) explains each variable.

### 5. Run

```bash
python bot.py
```

In your test server, type `&help`. Logs go to standard output (see
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#5-logs-and-what-to-watch)).

## Running the tests

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest -q
```

The suite needs no Discord token, network access or database. The Postgres backend is exercised
against an in-process fake (`tests/fakes.py`), and state fixtures under `tests/fixtures/` are
synthetic. Integration tests against a real PostgreSQL server
(`tests/test_storage_postgres_integration.py`) are skipped unless `BELL_TEST_DATABASE_URL` is set;
see [docs/TESTING.md](docs/TESTING.md) for running them locally with Docker and for CI.

You can also preview a Postgres migration against the synthetic fixtures without a database:

```bash
python db/migrate_json_to_postgres.py --dry-run --data-dir tests/fixtures/json_state
```

## Budget safety

Bell is set up so that, by default, it cannot spend money or exceed a free AI tier on its own.

### The governor

Every Groq chat completion goes through `GroqBudgetGovernor` in `groq_budget.py`:

- **Per-model token buckets** for requests/minute, requests/day, tokens/minute and tokens/day
  (`GROQ_LIMIT_RPM`, `GROQ_LIMIT_RPD`, `GROQ_LIMIT_TPM`, `GROQ_LIMIT_TPD`; per-model overrides with
  `GROQ_MODEL_LIMITS=model=rpm:rpd:tpm:tpd;...`).
- **FIFO queue**: a short wait for a minute budget (up to `GROQ_BUDGET_MAX_WAIT_SECONDS`) is spent in
  line, and the queue is bounded (`GROQ_QUEUE_MAX`).
- **Model fallback**: on HTTP 429 or an exhausted budget, the next model in the chain is tried.
- **Circuit breaker**: once every model is out of budget, AI commands reply "AI budget used up for
  today" without calling Groq.

The governor applies to **Groq only**. If you choose OpenRouter (`AI_PROVIDER=openrouter`), requests
are limited by the bot's in-flight limit and circuit breaker, but not by the governor's per-day
budgets or feature caps. The per-feature caps that do not involve a model call (the crush game,
engagement nudges) are enforced by the governor regardless of provider.

### Free-tier model defaults

The default chain is `openai/gpt-oss-120b`, then `openai/gpt-oss-20b`, then `qwen/qwen3.8-27b`. The
default limits are 30 requests/min, 1,000 requests/day, 8,000 tokens/min and 200,000 tokens/day per
model.

These numbers come from **Groq's public rate-limit documentation** for the free tier. They have
**not** been verified against the owner's own Groq key or account, and Groq can change them. Check
your limits in the Groq console and lower the `GROQ_LIMIT_*` values if yours are stricter.

Models that Groq serves only on paid tiers (`llama-3.3-70b-versatile`, `llama-3.1-8b-instant`,
`moonshotai/kimi-k2-*`) are dropped from every model chain, including ones you set in the
environment, unless you set `GROQ_ALLOW_ENTERPRISE_MODELS=1`.

### Fail-closed persistence (`QuotaPersistenceError`)

Usage counters are saved through the storage adapter after every change and loaded at start, so a
restart does not reset daily allowances. If the counters cannot be trusted, the governor refuses
work instead of guessing:

- If saving the counters fails, or a stored counter file exists but is unreadable or corrupt, new AI
  requests (and capped non-AI features) are refused with
  "AI is paused: the bot could not safely record its usage limits. Please tell the bot owner."
  Internally this is `QuotaPersistenceError`.
- A *missing* counter file (fresh install) is normal and starts with full budgets.
- Requests resume once a save succeeds again, or once the owner restores a good counter file or
  deletes the broken one (deleting it means accepting fresh counters).
- The governor never overwrites unreadable stored counters with fresh, lower ones.

With the default JSON backend, one bot process per counter file is assumed. Counters are only safe to
share between several processes with the Postgres backend, which updates them under an advisory lock.

### Per-feature caps

Each AI-using feature has a `policy_key` that the governor can cap per UTC day:

| Feature | Cap variable | Default |
| --- | --- | --- |
| `&agent` (per user, enforced in `agent_core.py`) | `AGENT_DAILY_CAP` | 20 per user |
| Crush-o-Meter plays | `CRUSH_GAME_DAILY_CAP` | 50 |
| Crush-o-Meter AI joke line | `CRUSH_GAME_FLAVOR_DAILY_CAP` | 50 |
| Scheduled agent tasks (all) | `AGENTIC_SCHEDULED_DAILY_CAP` | 50 |
| Escalation proposals | `AGENTIC_ESCALATION_DAILY_CAP` | 50 |
| Engagement nudges | `AGENTIC_NUDGE_DAILY_CAP` | 100 |
| Anything else | `GROQ_FEATURE_DAILY_CAPS=name=n,...` | unlimited (`GROQ_FEATURE_DAILY_CAP_DEFAULT=0`) |

`GROQ_FEATURE_DAILY_CAPS` overrides the per-feature defaults above. Each scheduled task also has its
own per-task cap (default 10), and nudges have a per-server daily cap (default 10).

## What has and hasn't been tested

- The unit tests (`python -m pytest`) cover the governor, storage adapter, migration dry run, agent
  loop and tools, agentic automation and the crush game, all with fakes and synthetic fixtures.
- The Postgres backend is tested against fakes and, in CI, against a throwaway PostgreSQL 16
  container (`tests/test_storage_postgres_integration.py`: adapter contract, concurrent locked
  updates from two connection pools, the Groq governor and the migration script). **It has never
  been run against a live hosted Postgres database or with the bot connected to Discord.** Treat it
  as experimental. Known JSON/Postgres differences are listed in
  [docs/TESTING.md](docs/TESTING.md#known-differences-between-the-json-and-postgresql-backends).
- The Groq free-tier limits used as defaults come from Groq's public docs and have not been tested
  against the owner's key.
- Nothing in this repository should be described as production-proven.
