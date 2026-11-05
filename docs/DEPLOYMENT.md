# Self-hosting Bell

This guide covers running Bell on your own machine or server: storage (JSON files by default,
Postgres optional), the decisions only the owner should make, and what to watch in the logs.

> **Honesty note.** Bell has not been run as a production service. The test suite covers the logic
> with fakes. In particular, **the Postgres backend has only been exercised against fakes and local
> tests and has never been run against a live hosted Postgres database**, and the Groq free-tier
> limits used as defaults come from Groq's public docs and have not been tested against the owner's
> key. Start with the default JSON storage, and try anything else on a test server first.

## 1. Basic install

Follow the README [Quickstart](../README.md#quickstart): Python 3.10+, `pip install -r
requirements.txt`, `cp .env.example .env`, set `DISCORD_BOT_TOKEN`, then `python bot.py`.

Run the bot from the repository root: state lives in `data/` **relative to the working directory**.

Keep exactly **one** bot process per `data/` directory (and per token). The JSON backend and the
budget counters assume a single process; see [Budget counters](#budget-counters-and-multiple-processes).

### Running it as a service (example)

A minimal systemd unit, assuming the repository is in `/opt/bell` with a virtualenv in
`/opt/bell/.venv` and a dedicated `bell` user:

```ini
[Unit]
Description=Bell Discord bot
After=network-online.target
Wants=network-online.target

[Service]
User=bell
WorkingDirectory=/opt/bell
EnvironmentFile=/opt/bell/.env
ExecStart=/opt/bell/.venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

`bot.py` also loads the `.env` file in the repository folder itself (via python-dotenv), so
`EnvironmentFile` is optional.
Make `.env` readable only by the bot user (`chmod 600 .env`).

## 2. Storage

All persistent state goes through `storage.py`. Each state area is one JSON document under a short
key; no feature reads or writes the files directly. Two backends implement the same interface.

### Default: JSON files under `data/`

Nothing to configure: leave `DATABASE_URL` unset.

- Writes go to a temporary file that is moved into place with `os.replace`. A state file is never
  written in place: if the temp write or the replace fails (for example, disk full), the last good
  file is kept, the temp file is removed and the write reports failure.
- Most areas are mirrored to `<file>.bak` the same way. The `.bak` copy is read when the main file
  is empty or corrupt.
- Missing files are created with defaults on first use.

| key | file | `.bak` | Postgres table | contents |
| --- | --- | --- | --- | --- |
| `guild_settings` | `data/mod_config.json` | yes | `bell_guild_settings` | Per-server settings: moderation config, mod-log channel, feature toggles, the `agentic` automation block. |
| `warnings` | `data/warnings.json` | yes | `bell_warnings` | Manual moderator warnings. |
| `mod_log` | `data/ai_mod_state.json` | yes | `bell_mod_log` | AI moderation case log, appeals, review actions, risk, metrics. |
| `engagement` | `data/engagement_state.json` | yes | `bell_engagement` | XP, levels, streaks, quests. |
| `economy` | `data/business_state.json` | yes | `bell_economy` | Economy / business simulation. |
| `altfinder` | `data/altfinder_state.json` | yes | `bell_altfinder` | Alt-account detection state. |
| `socialintel` | `data/socialintel_state.json` | yes | `bell_socialintel` | Interaction statistics. |
| `capabilities_overrides` | `data/capabilities_overrides.json` | no | `bell_capabilities_overrides` | Owner overrides for the capability catalog. |
| `capabilities_catalog` | `data/capabilities_catalog.json` | no | `bell_capabilities_catalog` | Generated capability catalog (a cache). |
| `crush_game` | `data/crush_game.json` | yes | `bell_crush_game` | Crush-o-Meter: enabled flags, players' own saved answers, the exclusion list. |
| `agentic_state` | `data/agentic_state.json` | yes | `bell_agentic_state` | Automation runtime state: task usage, proposals, nudge history and opt-ins. |
| `groq_budget` | `data/groq_budget_state.json` (or `GROQ_BUDGET_STATE_FILE`) | no | `bell_groq_budget` | Budget governor counters. Compact JSON, fsynced. |

`data/bad_words.txt` is a plain word list and always stays a file.
`data/aicrush_state.json` belongs to a removed feature: it is never read or migrated, and only the
owner can delete it (see [Owner-only decisions](#4-owner-only-decisions)).

**Backups:** stop the bot (or accept a slightly inconsistent snapshot) and copy the folder:

```bash
cp -r data "data.backup-$(date +%Y%m%d)"
```

### Optional: PostgreSQL via `DATABASE_URL`

> Experimental. Exercised only against an in-process fake and local tests, never against a live
> hosted Postgres. Keep your JSON files and a backup.

When `DATABASE_URL` is set, `PostgresBackend` is used instead of the JSON files. It needs `asyncpg`
(already in `requirements.txt`, imported only when needed). Nothing connects until the first storage
call.

**Schema** (`db/schema.sql`, idempotent):

- `bell_documents(doc_name PRIMARY KEY, version, updated_at)`: which documents exist. `version`
  increases on every write.
- One table per area (see the table above), each `(doc_key TEXT PRIMARY KEY, position INTEGER,
  value JSONB)`: one row per top-level key of the document (for example, one row per guild id), with
  `position` keeping the original order. JSONB normalises key order *inside* nested objects; values
  are unchanged.
- Writes replace an area's rows in one transaction. Read-modify-write updates hold a per-document
  `pg_advisory_xact_lock`.

**Migrating** (with the bot **stopped**):

1. Back up the JSON state:

   ```bash
   cp -r data "data.backup-$(date +%Y%m%d)"
   ```

2. Install the driver:

   ```bash
   pip install -r requirements.txt
   ```

3. **Dry run first.** This reads the files only, never imports `asyncpg` and never opens a database
   connection:

   ```bash
   python db/migrate_json_to_postgres.py --dry-run
   ```

   Options: `--data-dir PATH` if your data is elsewhere, `--groq-budget-file PATH` for a custom
   counter file (it also reads `GROQ_BUDGET_STATE_FILE`), `--json` for machine-readable output. Fix
   any area reported as `unreadable` before going on.

4. Create an empty PostgreSQL database and a user for the bot. Put the connection string in `.env`
   (never commit it):

   ```
   DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME
   ```

5. **Real run**: create the tables and copy the data. The URL is read from the environment only (not
   the command line, so it stays out of shell history) and is never printed:

   ```bash
   set -a; . ./.env; set +a; python db/migrate_json_to_postgres.py --apply-schema
   ```

   Each area is read back and compared after writing (`migrated <key>: N rows -> <table>
   (verified)`). Areas that already exist in the database are skipped unless you pass
   `--overwrite`. Applying the schema by hand is equivalent:
   `psql "$DATABASE_URL" -f db/schema.sql`.

6. Start the bot with `DATABASE_URL` set. It now reads and writes Postgres. The JSON files are left
   untouched.

**Rolling back:** stop the bot and remove `DATABASE_URL` from `.env`. It goes back to the JSON files.
Changes made while on Postgres are **not** copied back.

### Budget counters and multiple processes

The Groq budget counters (`groq_budget`) are what keep the bot inside its AI budget.

- With JSON storage, one bot process owns the counter file. Two processes sharing it can lose each
  other's increments.
- With Postgres, the counters are updated under an advisory lock and re-read before each request, so
  several processes can share them. (Again: only tested against fakes.)
- In either case the governor **fails closed**: if the counters can't be saved, or exist but can't
  be read, AI requests and capped features are refused (`QuotaPersistenceError`) until it is fixed.
  See [Logs and what to watch](#5-logs-and-what-to-watch).

## 3. Configuration review before going live

- Go through `.env.example`. It ships with every automation and proactive feature off
  (`AUTO_LOOPS_ENABLED`, `THREADREVIVE_PROACTIVE_ENABLED`, `WELCOME_CONCIERGE_ENABLED`,
  `BUSINESS_AI_TUNING_ENABLED`, `AUTOMOD_ENABLED`, `AI_MOD_ENABLED`). Note that if a variable is
  missing from `.env` entirely, the code default applies, and for `WELCOME_CONCIERGE_ENABLED` and
  `BUSINESS_AI_TUNING_ENABLED` that default is `true`. Copy the template rather than starting from an
  empty file.
- Check your real Groq limits in the Groq console and set `GROQ_LIMIT_*` at or below them.
- Keep `GROQ_ALLOW_ENTERPRISE_MODELS=0` unless you intend to pay for paid-tier models.
- Decide on per-feature caps (`GROQ_FEATURE_DAILY_CAPS`, `AGENT_DAILY_CAP`, `CRUSH_GAME_*`,
  `AGENTIC_*_DAILY_CAP`).

## 4. Owner-only decisions

Some things are deliberately left to a person rather than done automatically.

### `&legacydata` (bot owner only)

The removed history-mining crush command left `data/aicrush_state.json` (and possibly a `.bak`).
Bell never reads, migrates or deletes it by itself.

- `&legacydata status` reports whether the file(s) are still on disk.
- `&legacydata wipe` explains what will happen and asks for confirmation.
- `&legacydata wipe confirm` **permanently deletes** them. This cannot be undone. Take a backup first
  if you might need it.

Only the Discord application owner (as discord.py's `is_owner` check sees it) can run this command.

### Automation opt-ins (per server, Manage Server)

Agentic automation has no global switch. Each server must opt in, using an account with the
**Manage Server** permission:

- `&agentic scheduled on` plus `&agentic task add ...` / `&agentic task enable <name>` for
  scheduled agent tasks. New tasks start disabled.
- `&agentic escalation on [threshold] [#mod-channel]` for escalation proposals. Confirming a
  proposal only records the decision; nothing is applied automatically.
- `&agentic nudges on [#channel] [server daily cap]` for engagement nudges. Each member must also
  opt in with `&nudges on`.
- `&crushgame on #channel` for the Crush-o-Meter game.

As the bot operator, decide which servers you are comfortable enabling these on, and set the global
daily caps in `.env` to limit what any server can spend.

## 5. Logs and what to watch

Bell prints its logs to **standard output / standard error**; there is no log file. Under systemd
they go to the journal (`journalctl -u bell -f`); under Docker, to `docker logs`. Redirect them
yourself if you run it by hand (`python bot.py >> bell.log 2>&1`).

Log lines start with a bracketed tag. The important ones:

| Tag | Meaning | What to do |
| --- | --- | --- |
| `[GROQ BUDGET] Usage counters unreadable; AI requests are blocked until fixed` | The stored counter file/rows exist but can't be read. AI is paused (fail closed). | Restore the counter file from a backup, or delete it to accept fresh counters, then restart. |
| `[GROQ BUDGET] Saving usage counters failed` / `Could not save counters` | Counters couldn't be written (disk full, permissions, database down). AI is paused until a save succeeds. | Fix disk space / permissions / database. Requests resume automatically after a successful save. |
| `[STORAGE] Could not save ...` | A JSON state file write failed; the last good file was kept. | Check disk space and permissions on `data/`. |
| `[STORAGE] Postgres write failed for ...` | A Postgres write failed. | Check the database. |
| `[AGENTIC TICK ERROR]`, `[AGENTIC ESCALATION ERROR]` | An automation run failed. | Review `&agentic status`; disable the task if it keeps failing. |
| `[AGENT MODLOG ERROR]` | A confirmed agent action could not be written to the mod log. | Check the mod-log channel still exists and the bot can post there. |
| `[AI ERROR]` and other `... AI ERROR` tags | A model call failed. | Usually transient; repeated errors may mean a bad key or a model change. |
| `[SLASH SYNC ERROR]` | Slash commands failed to sync. | Prefix commands still work. Check the `applications.commands` scope. |

Users see these refusals in Discord, which are expected behaviour rather than errors:

- "AI budget used up for today. Please try again later." (every model's daily budget is used)
- "Daily AI limit for this feature has been reached." (a per-feature cap)
- "AI is paused: the bot could not safely record its usage limits. Please tell the bot owner."
  (fail closed; look for a `[GROQ BUDGET]` log line)

## 6. Updating

```bash
git pull
```

```bash
pip install -r requirements.txt
```

```bash
python -m pytest -q
```

Then restart the bot. Back up `data/` (or your database) before updating.
