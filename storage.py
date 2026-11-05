"""Storage adapter for the bot's persistent JSON state.

Every piece of durable state the bot keeps (guild settings, XP/economy,
warnings, the moderation case log, crush game state, agentic automation
schedules, the Groq budget counters, ...) is a *document*: one JSON object
stored under a short key such as ``"warnings"``. Features never touch files
directly; they go through a :class:`StorageBackend`.

Two backends exist:

* :class:`JsonFileBackend` (default) keeps today's on-disk layout under
  ``data/`` byte for byte: same file names, same formatting, atomic
  replace-on-write, the ``.bak`` mirror and backup fallback on read.
* :class:`PostgresBackend` is selected only when ``DATABASE_URL`` is set. It
  needs ``asyncpg``, which is imported lazily so the bot runs without it.

The interface offers both a sync API (``get``/``set``/``delete``/
``list_keys``/``update``/``version``) and an async one (``aget``/``aset``/
``adelete``/``alist_keys``/``aupdate``). The bot's call sites are
synchronous today, so they use the sync API; the async API is there for new
code that wants to await storage.

This module is stdlib-only.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

DATABASE_URL_ENV = "DATABASE_URL"

# Serialisation styles used by the existing files.
STYLE_PRETTY = "pretty"  # json.dumps(payload, indent=2), written via a pid/ms temp file
STYLE_COMPACT = "compact"  # compact + sorted keys, mkstemp + fsync (Groq budget counters)


@dataclass(frozen=True)
class StateArea:
    """One persistent JSON document the bot owns."""

    key: str
    filename: str
    table: str
    description: str
    style: str = STYLE_PRETTY
    # Mirror every write to ``<file>.bak`` and fall back to it when the primary is empty/corrupt.
    backup: bool = True
    # Exact text written when the file is missing at startup (None = not seeded).
    seed: str | None = None
    # Legacy areas are only ever deleted; they are not migrated or given a table.
    legacy: bool = False


AREAS: tuple[StateArea, ...] = (
    StateArea(
        "guild_settings",
        "mod_config.json",
        "bell_guild_settings",
        "Per-guild settings: moderation config, mod-log channel, feature toggles and the "
        "agentic automation config block (`agentic`).",
        seed="{}",
    ),
    StateArea("warnings", "warnings.json", "bell_warnings", "Manual moderator warnings per guild/user.", seed="{}"),
    StateArea(
        "mod_log",
        "ai_mod_state.json",
        "bell_mod_log",
        "AI moderation case log: cases, appeals, review actions, user risk, metrics.",
        seed="{}",
    ),
    StateArea(
        "engagement",
        "engagement_state.json",
        "bell_engagement",
        "XP, levels, streaks, daily quests per guild member.",
        seed='{"guilds": {}}',
    ),
    StateArea("economy", "business_state.json", "bell_economy", "Economy / business simulation state.", seed="{}"),
    StateArea(
        "altfinder",
        "altfinder_state.json",
        "bell_altfinder",
        "Alt-account detection state.",
        seed='{"schema_version": 1, "guilds": {}}',
    ),
    StateArea(
        "socialintel",
        "socialintel_state.json",
        "bell_socialintel",
        "Social graph / interaction statistics.",
        seed='{"schema_version": 1, "guilds": {}}',
    ),
    StateArea(
        "capabilities_overrides",
        "capabilities_overrides.json",
        "bell_capabilities_overrides",
        "Owner overrides for the capability catalog.",
        backup=False,
    ),
    StateArea(
        "capabilities_catalog",
        "capabilities_catalog.json",
        "bell_capabilities_catalog",
        "Generated capability catalog (rebuilt from commands; cache).",
        backup=False,
    ),
    StateArea("crush_game", "crush_game.json", "bell_crush_game", "Consent-first crush joke game state."),
    StateArea(
        "agentic_state",
        "agentic_state.json",
        "bell_agentic_state",
        "Agentic automation runtime state: scheduled tasks, escalation proposals, nudge history.",
    ),
    StateArea(
        "groq_budget",
        "groq_budget_state.json",
        "bell_groq_budget",
        "Groq budget governor counters (token buckets, feature caps, circuit breaker).",
        style=STYLE_COMPACT,
        backup=False,
    ),
    StateArea(
        "legacy_aicrush",
        "aicrush_state.json",
        "",
        "Removed history-mining aicrush data; never read or migrated, deleted only by `&legacydata wipe confirm`.",
        legacy=True,
    ),
)

AREAS_BY_KEY: dict[str, StateArea] = {area.key: area for area in AREAS}
MIGRATABLE_AREAS: tuple[StateArea, ...] = tuple(area for area in AREAS if not area.legacy)

_KEY_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def area_for(key: str) -> StateArea:
    """The :class:`StateArea` for ``key``; unknown keys get a pretty/backup file ``<key>.json``."""
    area = AREAS_BY_KEY.get(key)
    if area is not None:
        return area
    if not _KEY_RE.match(key or ""):
        raise ValueError(f"Invalid storage key {key!r} (use lowercase letters, digits and underscores).")
    return StateArea(key, f"{key}.json", f"bell_{key}", "ad-hoc document")


def clone_json_dict(payload: Mapping[str, Any]) -> dict:
    """Deep copy through JSON, like the bot always did before writing."""
    try:
        cloned = json.loads(json.dumps(payload))
    except (TypeError, ValueError):
        cloned = dict(payload)
    return cloned if isinstance(cloned, dict) else {}


def redact_dsn(dsn: str) -> str:
    """``postgresql://user:***@host/db`` - never log a DATABASE_URL password."""
    return re.sub(r"(//[^:/@]+:)[^@]*@", r"\1***@", dsn or "")


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class StorageBackend:
    """Key -> JSON-object document store.

    Contract (checked by ``tests/test_storage_contract.py``):

    * ``get(key)`` returns a dict, or ``None`` if the key was never set or was deleted.
    * ``set(key, value)`` stores a JSON-serialisable dict and returns ``True`` on
      success, ``False`` if it could not be persisted (the error is logged).
    * Values are stored by value: mutating a dict after ``set`` or after ``get``
      never changes what is stored.
    * ``delete(key)`` removes the key and returns whether something was removed.
    * ``list_keys()`` lists the stored keys, sorted.
    * ``update(key, fn)`` runs ``fn(current_or_None) -> new_dict`` and stores the
      result as one read-modify-write. It is atomic across processes only when
      :attr:`shared` is true.
    * ``version(key)`` is an opaque change token (0.0 when absent) for caches.
    """

    #: True when several bot processes can safely share this backend.
    shared: bool = False
    name: str = "abstract"

    # -- sync API ----------------------------------------------------------

    def get(self, key: str) -> dict | None:
        raise NotImplementedError

    def set(self, key: str, value: Mapping[str, Any]) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        raise NotImplementedError

    def list_keys(self) -> list[str]:
        raise NotImplementedError

    def update(self, key: str, fn: Callable[[dict | None], Mapping[str, Any]]) -> dict:
        raise NotImplementedError

    def version(self, key: str) -> float:
        raise NotImplementedError

    def ensure_default(self, key: str, value: Mapping[str, Any] | None = None) -> bool:
        """Create ``key`` with its seed (or ``value``) if it does not exist. True if created."""
        if self.exists(key):
            return False
        if value is None:
            seed = area_for(key).seed
            if seed is None:
                return False
            value = json.loads(seed)
        return self.set(key, value)

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def close(self) -> None:
        return None

    # -- async API -----------------------------------------------------------

    async def aget(self, key: str) -> dict | None:
        return await asyncio.to_thread(self.get, key)

    async def aset(self, key: str, value: Mapping[str, Any]) -> bool:
        return await asyncio.to_thread(self.set, key, clone_json_dict(value))

    async def adelete(self, key: str) -> bool:
        return await asyncio.to_thread(self.delete, key)

    async def alist_keys(self) -> list[str]:
        return await asyncio.to_thread(self.list_keys)

    async def aupdate(self, key: str, fn: Callable[[dict | None], Mapping[str, Any]]) -> dict:
        return await asyncio.to_thread(self.update, key, fn)


# ---------------------------------------------------------------------------
# JSON files (default)
# ---------------------------------------------------------------------------


class JsonFileBackend(StorageBackend):
    """Today's ``data/*.json`` files, with the exact same on-disk behaviour.

    ``paths`` maps keys to explicit file paths (e.g. ``GROQ_BUDGET_STATE_FILE``);
    every other key lives at ``data_dir / area.filename``.
    """

    shared = False
    name = "json"
    ERROR_LOG_INTERVAL = 25.0

    def __init__(
        self,
        data_dir: str | os.PathLike[str] = "data",
        *,
        paths: Mapping[str, str | os.PathLike[str]] | None = None,
        log: Callable[[str], None] = print,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.paths = {key: Path(value) for key, value in (paths or {}).items()}
        self._log = log
        self._error_last_ts: dict[str, float] = {}
        self._lock = threading.RLock()

    # -- paths -------------------------------------------------------------

    def path_for(self, key: str) -> Path:
        explicit = self.paths.get(key)
        if explicit is not None:
            return explicit
        return self.data_dir / area_for(key).filename

    @staticmethod
    def backup_path(path: Path) -> Path:
        return path.with_suffix(f"{path.suffix}.bak")

    # -- low level ---------------------------------------------------------

    @staticmethod
    def _read_file(path: Path) -> dict | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None

    def _log_persistence_error(self, path: Path, action: str, error: OSError) -> None:
        now = time.monotonic()
        key = f"{action}:{path}:{getattr(error, 'errno', 'unknown')}"
        if now - self._error_last_ts.get(key, 0.0) < self.ERROR_LOG_INTERVAL:
            return
        self._error_last_ts[key] = now
        self._log(
            f"[PERSISTENCE ERROR] action={action} path=`{path}` "
            f"errno=`{getattr(error, 'errno', 'unknown')}` detail=`{error}`"
        )

    def _write_text_atomic(self, path: Path, text: str) -> tuple[bool, OSError | None]:
        """Temp file + ``os.replace``; falls back to a direct write where replace fails."""
        temp_path = path.with_name(f"{path.name}.tmp-{os.getpid()}-{int(time.time() * 1000)}")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(text, encoding="utf-8")
            os.replace(temp_path, path)
            return True, None
        except OSError as error:
            self._log_persistence_error(path, "atomic_replace", error)
            try:
                path.write_text(text, encoding="utf-8")
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                except OSError:
                    pass
                return True, None
            except OSError as fallback_error:
                self._log_persistence_error(path, "direct_write", fallback_error)
                error = fallback_error
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError as cleanup_error:
                self._log_persistence_error(path, "temp_cleanup", cleanup_error)
            return False, error

    # -- interface -----------------------------------------------------------

    def get(self, key: str) -> dict | None:
        area = area_for(key)
        path = self.path_for(key)
        primary = self._read_file(path)
        if primary or not area.backup:
            return primary
        backup = self._read_file(self.backup_path(path))
        if backup:
            return backup
        return primary if primary is not None else backup

    def exists(self, key: str) -> bool:
        path = self.path_for(key)
        if path.exists():
            return True
        return area_for(key).backup and self.backup_path(path).exists()

    def set(self, key: str, value: Mapping[str, Any]) -> bool:
        area = area_for(key)
        path = self.path_for(key)
        if area.style == STYLE_COMPACT:
            try:
                atomic_write_json(path, value)
            except (OSError, TypeError, ValueError) as error:
                self._log(f"[STORAGE] Could not save `{path}`: {error}")
                return False
            return True

        cloned = clone_json_dict(value)
        try:
            serialized = json.dumps(cloned, indent=2)
        except (TypeError, ValueError):
            self._log(f"[JSON SERIALIZE ERROR] Could not serialize payload for `{path}`.")
            return False
        ok, primary_error = self._write_text_atomic(path, serialized)
        if not ok:
            if primary_error is not None:
                self._log(
                    f"[JSON WRITE ERROR] Could not write `{path}` "
                    f"(errno={getattr(primary_error, 'errno', 'unknown')}: {primary_error})."
                )
            else:
                self._log(f"[JSON WRITE ERROR] Could not write `{path}`.")
            return False
        if area.backup:
            backup_path = self.backup_path(path)
            backup_ok, backup_error = self._write_text_atomic(backup_path, serialized)
            if not backup_ok:
                if backup_error is not None:
                    self._log(
                        f"[JSON BACKUP WRITE ERROR] Could not write `{backup_path}` "
                        f"(errno={getattr(backup_error, 'errno', 'unknown')}: {backup_error})."
                    )
                else:
                    self._log(f"[JSON BACKUP WRITE ERROR] Could not write `{backup_path}`.")
        return True

    def delete(self, key: str) -> bool:
        return bool(self.delete_files(key))

    def delete_files(self, key: str) -> list[str]:
        """Delete the file (and its ``.bak``); returns the removed paths."""
        path = self.path_for(key)
        removed: list[str] = []
        for candidate in (path, self.backup_path(path)):
            try:
                if candidate.exists():
                    candidate.unlink()
                    removed.append(str(candidate))
            except OSError:
                continue
        return removed

    def list_keys(self) -> list[str]:
        keys = set()
        for area in AREAS:
            if self.path_for(area.key).exists():
                keys.add(area.key)
        if self.data_dir.is_dir():
            known = {self.path_for(area.key).name for area in AREAS}
            for child in self.data_dir.glob("*.json"):
                stem = child.stem
                if child.name not in known and _KEY_RE.match(stem):
                    keys.add(stem)
        return sorted(keys)

    def update(self, key: str, fn: Callable[[dict | None], Mapping[str, Any]]) -> dict:
        # Serialised within this process only; JSON files are single-process storage.
        with self._lock:
            new_value = clone_json_dict(fn(self.get(key)))
            self.set(key, new_value)
            return new_value

    def version(self, key: str) -> float:
        try:
            return float(self.path_for(key).stat().st_mtime)
        except OSError:
            return 0.0

    def ensure_default(self, key: str, value: Mapping[str, Any] | None = None) -> bool:
        """Seed a missing file with exactly the text the bot has always written."""
        path = self.path_for(key)
        if path.exists():
            return False
        if value is None:
            text = area_for(key).seed
            if text is None:
                return False
        else:
            text = json.dumps(value, indent=2)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return True


def atomic_write_json(path: str | os.PathLike[str], payload: Any) -> None:
    """Write compact JSON so readers only ever see the old or the new complete file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# PostgreSQL (inactive unless DATABASE_URL is set)
# ---------------------------------------------------------------------------


class PostgresUnavailableError(RuntimeError):
    pass


class PostgresBackend(StorageBackend):
    """Documents in PostgreSQL (see ``db/schema.sql``).

    Each area has its own table with one row per top-level key of the document
    (``doc_key``, ``position``, ``value jsonb``), so e.g. guild settings are one
    row per guild. ``bell_documents`` records which documents exist and a
    version counter used as the cache token. ``update`` takes a transaction
    advisory lock per key, which makes the read-modify-write safe across
    processes (this is what the Groq budget governor relies on).

    Nothing connects until the first storage call. ``asyncpg`` is imported
    lazily. All queries run on a private event loop thread so the bot's
    synchronous call sites can use the backend from inside its own loop.
    """

    shared = True
    name = "postgres"

    def __init__(self, dsn: str, *, timeout: float = 15.0, connector: Callable[..., Any] | None = None) -> None:
        if not dsn:
            raise ValueError("PostgresBackend needs a DATABASE_URL.")
        self._dsn = dsn
        self._timeout = timeout
        self._connector = connector
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._pool: Any = None
        self._start_lock = threading.Lock()

    def __repr__(self) -> str:
        return f"PostgresBackend({redact_dsn(self._dsn)!r})"

    @staticmethod
    def table_for(key: str) -> str:
        area = area_for(key)
        if area.legacy:
            raise ValueError(f"{key!r} is a legacy area with no table.")
        return area.table

    # -- loop / pool -------------------------------------------------------

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._start_lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                thread = threading.Thread(target=loop.run_forever, name="bell-postgres", daemon=True)
                thread.start()
                self._loop, self._thread = loop, thread
            return self._loop

    async def _get_pool(self) -> Any:
        if self._pool is None:
            connector = self._connector
            if connector is None:
                try:
                    import asyncpg  # noqa: PLC0415 - optional dependency, imported lazily
                except ImportError as error:  # pragma: no cover - depends on environment
                    raise PostgresUnavailableError(
                        "DATABASE_URL is set but asyncpg is not installed (pip install -r requirements.txt)."
                    ) from error
                connector = asyncpg.create_pool
            self._pool = await connector(self._dsn, min_size=1, max_size=4, command_timeout=self._timeout)
        return self._pool

    def _run(self, coro: Any) -> Any:
        loop = self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop).result(self._timeout * 2)

    async def _dispatch(self, coro: Any) -> Any:
        loop = self._ensure_loop()
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro, loop))

    # -- queries -------------------------------------------------------------

    async def _read(self, conn: Any, key: str) -> dict | None:
        exists = await conn.fetchval("SELECT 1 FROM bell_documents WHERE doc_name = $1", key)
        if not exists:
            return None
        rows = await conn.fetch(
            f"SELECT doc_key, value FROM {self.table_for(key)} ORDER BY position, doc_key"
        )
        return {row["doc_key"]: json.loads(row["value"]) for row in rows}

    async def _write(self, conn: Any, key: str, value: Mapping[str, Any]) -> None:
        table = self.table_for(key)
        payload = clone_json_dict(value)
        await conn.execute(
            "INSERT INTO bell_documents (doc_name, version, updated_at) VALUES ($1, 1, now()) "
            "ON CONFLICT (doc_name) DO UPDATE SET version = bell_documents.version + 1, updated_at = now()",
            key,
        )
        await conn.execute(f"DELETE FROM {table}")
        if payload:
            await conn.executemany(
                f"INSERT INTO {table} (doc_key, position, value) VALUES ($1, $2, $3::jsonb)",
                [(str(k), i, json.dumps(v)) for i, (k, v) in enumerate(payload.items())],
            )

    async def _lock(self, conn: Any, key: str) -> None:
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"bell:{key}")

    async def _aget(self, key: str) -> dict | None:
        self.table_for(key)  # validate before touching the database
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await self._read(conn, key)

    async def _aset(self, key: str, value: Mapping[str, Any]) -> bool:
        self.table_for(key)  # validate before touching the database
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._lock(conn, key)
                await self._write(conn, key, value)
        return True

    async def _adelete(self, key: str) -> bool:
        self.table_for(key)  # validate before touching the database
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._lock(conn, key)
                status = await conn.execute("DELETE FROM bell_documents WHERE doc_name = $1", key)
                await conn.execute(f"DELETE FROM {self.table_for(key)}")
        return str(status).endswith(" 1")

    async def _alist_keys(self) -> list[str]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT doc_name FROM bell_documents ORDER BY doc_name")
        return [row["doc_name"] for row in rows]

    async def _aupdate(self, key: str, fn: Callable[[dict | None], Mapping[str, Any]]) -> dict:
        self.table_for(key)  # validate before touching the database
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._lock(conn, key)
                new_value = clone_json_dict(fn(await self._read(conn, key)))
                await self._write(conn, key, new_value)
        return new_value

    async def _aversion(self, key: str) -> float:
        self.table_for(key)  # validate before touching the database
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            value = await conn.fetchval("SELECT version FROM bell_documents WHERE doc_name = $1", key)
        return float(value or 0)

    # -- sync API ----------------------------------------------------------

    def get(self, key: str) -> dict | None:
        return self._run(self._aget(key))

    def set(self, key: str, value: Mapping[str, Any]) -> bool:
        try:
            return self._run(self._aset(key, value))
        except PostgresUnavailableError:
            raise
        except Exception as error:  # noqa: BLE001 - mirror JsonFileBackend: log and report failure
            print(f"[STORAGE] Postgres write failed for `{key}`: {type(error).__name__}")
            return False

    def delete(self, key: str) -> bool:
        return self._run(self._adelete(key))

    def list_keys(self) -> list[str]:
        return self._run(self._alist_keys())

    def update(self, key: str, fn: Callable[[dict | None], Mapping[str, Any]]) -> dict:
        return self._run(self._aupdate(key, fn))

    def version(self, key: str) -> float:
        return self._run(self._aversion(key))

    # -- async API -----------------------------------------------------------

    async def aget(self, key: str) -> dict | None:
        return await self._dispatch(self._aget(key))

    async def aset(self, key: str, value: Mapping[str, Any]) -> bool:
        return await self._dispatch(self._aset(key, clone_json_dict(value)))

    async def adelete(self, key: str) -> bool:
        return await self._dispatch(self._adelete(key))

    async def alist_keys(self) -> list[str]:
        return await self._dispatch(self._alist_keys())

    async def aupdate(self, key: str, fn: Callable[[dict | None], Mapping[str, Any]]) -> dict:
        return await self._dispatch(self._aupdate(key, fn))

    def close(self) -> None:
        if self._loop is None:
            return
        if self._pool is not None:
            try:
                self._run(self._pool.close())
            except Exception:  # noqa: BLE001
                pass
            self._pool = None
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._loop = None
        self._thread = None


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def backend_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    data_dir: str | os.PathLike[str] = "data",
    paths: Mapping[str, str | os.PathLike[str]] | None = None,
) -> StorageBackend:
    """PostgresBackend when ``DATABASE_URL`` is set, otherwise the JSON files."""
    env = os.environ if environ is None else environ
    dsn = str(env.get(DATABASE_URL_ENV, "") or "").strip()
    if dsn:
        return PostgresBackend(dsn)
    return JsonFileBackend(data_dir, paths=paths)


def iter_areas(keys: Iterable[str] | None = None) -> list[StateArea]:
    if keys is None:
        return list(MIGRATABLE_AREAS)
    return [area_for(key) for key in keys]
