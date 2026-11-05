-- Bell bot storage schema for PostgresBackend (storage.py).
--
-- Inactive by default: the bot only uses PostgreSQL when DATABASE_URL is set.
-- Apply with:  psql "$DATABASE_URL" -f db/schema.sql
-- (db/migrate_json_to_postgres.py --apply-schema does the same.)
--
-- Every state area is one JSON document. Each area table holds one row per
-- top-level key of that document (e.g. one row per guild id for guild
-- settings); `position` keeps the original top-level key order. Values are
-- JSONB, so nested object key order is normalised by PostgreSQL (dict
-- equality is unchanged). Idempotent: safe to run more than once.

BEGIN;

-- Which documents exist, plus a version counter used as the cache token.
CREATE TABLE IF NOT EXISTS bell_documents (
    doc_name   TEXT PRIMARY KEY,
    version    BIGINT      NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- guild_settings: Per-guild settings: moderation config, mod-log channel, feature toggles and the agentic automation config block (`agentic`). (was data/mod_config.json)
CREATE TABLE IF NOT EXISTS bell_guild_settings (
    doc_key  TEXT    PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    value    JSONB   NOT NULL
);

-- warnings: Manual moderator warnings per guild/user. (was data/warnings.json)
CREATE TABLE IF NOT EXISTS bell_warnings (
    doc_key  TEXT    PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    value    JSONB   NOT NULL
);

-- mod_log: AI moderation case log: cases, appeals, review actions, user risk, metrics. (was data/ai_mod_state.json)
CREATE TABLE IF NOT EXISTS bell_mod_log (
    doc_key  TEXT    PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    value    JSONB   NOT NULL
);

-- engagement: XP, levels, streaks, daily quests per guild member. (was data/engagement_state.json)
CREATE TABLE IF NOT EXISTS bell_engagement (
    doc_key  TEXT    PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    value    JSONB   NOT NULL
);

-- economy: Economy / business simulation state. (was data/business_state.json)
CREATE TABLE IF NOT EXISTS bell_economy (
    doc_key  TEXT    PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    value    JSONB   NOT NULL
);

-- altfinder: Alt-account detection state. (was data/altfinder_state.json)
CREATE TABLE IF NOT EXISTS bell_altfinder (
    doc_key  TEXT    PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    value    JSONB   NOT NULL
);

-- socialintel: Social graph / interaction statistics. (was data/socialintel_state.json)
CREATE TABLE IF NOT EXISTS bell_socialintel (
    doc_key  TEXT    PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    value    JSONB   NOT NULL
);

-- capabilities_overrides: Owner overrides for the capability catalog. (was data/capabilities_overrides.json)
CREATE TABLE IF NOT EXISTS bell_capabilities_overrides (
    doc_key  TEXT    PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    value    JSONB   NOT NULL
);

-- capabilities_catalog: Generated capability catalog (rebuilt from commands; cache). (was data/capabilities_catalog.json)
CREATE TABLE IF NOT EXISTS bell_capabilities_catalog (
    doc_key  TEXT    PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    value    JSONB   NOT NULL
);

-- crush_game: Consent-first crush joke game state. (was data/crush_game.json)
CREATE TABLE IF NOT EXISTS bell_crush_game (
    doc_key  TEXT    PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    value    JSONB   NOT NULL
);

-- agentic_state: Agentic automation runtime state: scheduled tasks, escalation proposals, nudge history. (was data/agentic_state.json)
CREATE TABLE IF NOT EXISTS bell_agentic_state (
    doc_key  TEXT    PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    value    JSONB   NOT NULL
);

-- groq_budget: Groq budget governor counters (token buckets, feature caps, circuit breaker). (was data/groq_budget_state.json)
CREATE TABLE IF NOT EXISTS bell_groq_budget (
    doc_key  TEXT    PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    value    JSONB   NOT NULL
);

COMMIT;
