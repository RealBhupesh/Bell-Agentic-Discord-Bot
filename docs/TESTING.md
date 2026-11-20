# Testing

## Offline suite (default)

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

Needs no Discord token, Groq key, network or database. The PostgreSQL integration tests in
`tests/test_storage_postgres_integration.py` are **skipped** in this mode (`-rs` shows why).

## PostgreSQL integration tests

These run `storage.PostgresBackend`, `db/schema.sql` and `db/migrate_json_to_postgres.py` against a
real PostgreSQL server. They only run when `BELL_TEST_DATABASE_URL` is set and reachable.

They use `BELL_TEST_DATABASE_URL`, never `DATABASE_URL`, so they cannot pick up a bot database by
accident. Each run creates its own `bell_it_<random>` schema, works only inside it, and drops it at
the end. Still, point it at a throwaway database only.

### Locally with Docker

`docker-compose.test.yml` starts a throwaway PostgreSQL 16 on `127.0.0.1:54329` (data in tmpfs, the
password is a local test value, not a secret):

```bash
docker compose -f docker-compose.test.yml up -d --wait
```

```bash
BELL_TEST_DATABASE_URL=postgresql://bell:bell-local-test-only@127.0.0.1:54329/bell_test BELL_REQUIRE_POSTGRES=1 python -m pytest -q -m postgres
```

```bash
docker compose -f docker-compose.test.yml down
```

Any other local PostgreSQL (12 or newer) works too; just set `BELL_TEST_DATABASE_URL`.

`BELL_REQUIRE_POSTGRES=1` turns "database unreachable" into a test failure instead of a skip. CI sets
it so the integration job can never pass by skipping.

## CI

`.github/workflows/tests.yml` runs on every push and pull request:

- **unit**: Python 3.10, 3.11, 3.12 and 3.13, no database (integration tests skip).
- **postgres**: Python 3.10 and 3.13 with a `postgres:16` service container; runs the integration
  tests with `BELL_REQUIRE_POSTGRES=1`, then the full suite.

It uses only GitHub-hosted runners and a public Docker image; no secrets, no deploy step, and
nothing connects to Discord or Groq.

## Known differences between the JSON and PostgreSQL backends

Found by the integration tests; both fail closed (the write returns `False`, the previously stored
document is left unchanged, and the error is logged):

- PostgreSQL JSONB cannot store the NUL character (`\u0000`) in strings. A document containing one
  can be written to the JSON files but not to PostgreSQL.
- Keys that are not listed in `storage.AREAS` ("ad-hoc" keys) have no table in `db/schema.sql`, so
  they only work with the JSON backend.
- Nested object key order is normalised by JSONB (top-level order is preserved); dict equality is
  unaffected.
