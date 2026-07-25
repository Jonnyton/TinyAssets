"""Replay-safe migration runner for the local full-platform-v0 fixture."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import time
from pathlib import Path
from typing import NamedTuple

_MIGRATION_NAME = re.compile(r"^(?P<version>\d{3})_(?P<name>[a-z0-9_]+)\.sql$")
_LOCK_KEY = 7_293_461_550_848_602_031


class MigrationError(RuntimeError):
    """The fixture migration chain is unsafe or cannot be applied."""


class Migration(NamedTuple):
    version: int
    name: str
    filename: str
    path: Path
    sha256: str


def discover_migrations(directory: Path) -> tuple[Migration, ...]:
    """Return the exact-byte migration chain after fail-closed validation."""
    migrations: list[Migration] = []
    versions: set[int] = set()
    for path in sorted(directory.glob("*.sql"), key=lambda candidate: candidate.name):
        match = _MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"invalid migration filename: {path.name}")
        version = int(match.group("version"))
        if version in versions:
            raise MigrationError(f"duplicate migration version {version:03d}")
        versions.add(version)
        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                filename=path.name,
                path=path,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )

    expected = list(range(1, len(migrations) + 1))
    actual = [migration.version for migration in migrations]
    if actual != expected:
        raise MigrationError(
            f"migration versions must be gap-free from 001: got {actual}"
        )
    return tuple(migrations)


def _acquire_lock(connection, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (_LOCK_KEY,))
            if cursor.fetchone()[0]:
                return
        if time.monotonic() >= deadline:
            raise MigrationError(
                f"fixture migration lock unavailable after {timeout_seconds:g}s"
            )
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def _bootstrap_history(connection) -> None:
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM pg_roles WHERE rolname = 'tinyassets_migration'
                  ) THEN
                    CREATE ROLE tinyassets_migration NOLOGIN;
                  END IF;
                END
                $$;
                CREATE TABLE IF NOT EXISTS public.schema_migrations (
                  version integer PRIMARY KEY CHECK (version > 0),
                  name text NOT NULL,
                  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
                  applied_at timestamptz NOT NULL DEFAULT now()
                );
                ALTER TABLE public.schema_migrations OWNER TO tinyassets_migration;
                REVOKE ALL ON public.schema_migrations FROM PUBLIC;
                GRANT SELECT, INSERT ON public.schema_migrations TO tinyassets_migration;
                """
            )


def _read_history(connection) -> tuple[tuple[int, str, str], ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT version, name, sha256 FROM public.schema_migrations "
            "ORDER BY version"
        )
        return tuple(cursor.fetchall())


def _validate_history(
    history: tuple[tuple[int, str, str], ...],
    migrations: tuple[Migration, ...],
) -> None:
    if len(history) > len(migrations):
        raise MigrationError("database history is ahead of the fixture chain")
    for index, (version, name, sha256) in enumerate(history):
        expected = migrations[index]
        if version != expected.version:
            raise MigrationError(
                f"applied history is not a gap-free prefix at {version:03d}"
            )
        if name != expected.name:
            raise MigrationError(
                f"migration {version:03d} name drift: {name!r} != {expected.name!r}"
            )
        if sha256 != expected.sha256:
            raise MigrationError(f"migration {version:03d} checksum drift")


def _has_untracked_fixture(connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.users') IS NOT NULL")
        return bool(cursor.fetchone()[0])


def _verify_existing_fixture(connection) -> None:
    checks = {
        "core tables": """
            SELECT ARRAY[
              'users','capabilities','nodes','host_pool','requests','bids',
              'ledger','settlements','flags','forwards'
            ]::text[] <@ ARRAY(
              SELECT tablename::text FROM pg_tables WHERE schemaname = 'public'
            )
        """,
        "required extensions": """
            SELECT ARRAY['pgcrypto','vector']::text[] <@
                   ARRAY(SELECT extname::text FROM pg_extension)
        """,
        "forward version": """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'forwards'
                AND column_name = 'version' AND is_nullable = 'NO'
            )
        """,
        "fixture auth helpers and role": """
            SELECT EXISTS (
                     SELECT 1 FROM pg_roles
                     WHERE rolname = 'tinyassets_fixture_app'
                       AND NOT rolcanlogin
                   )
               AND to_regprocedure(
                     'auth.is_request_bidder(uuid)'
                   ) IS NOT NULL
               AND to_regprocedure(
                     'auth.is_request_owner(uuid)'
                   ) IS NOT NULL
        """,
        "discovery surface": """
            SELECT to_regclass(
                     'public.artifact_field_visibility'
                   ) IS NOT NULL
               AND to_regprocedure(
                     'public.strip_private_fields(jsonb,uuid,text)'
                   ) IS NOT NULL
               AND to_regprocedure(
                     'public.discover_nodes(text,vector,jsonb,jsonb,text,integer,boolean)'
                   ) IS NOT NULL
               AND EXISTS (
                     SELECT 1
                     FROM pg_attribute
                     WHERE attrelid = 'public.nodes'::regclass
                       AND attname = 'embedding'
                       AND format_type(atttypid, atttypmod) = 'vector(16)'
                   )
        """,
        "token normalization": """
            SELECT (
              SELECT count(*) = 2
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = 'requests'
                AND column_name = ANY(ARRAY['tokens_in','tokens_out'])
            ) AND (
              SELECT count(*) = 3
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = 'ledger'
                AND column_name = ANY(ARRAY[
                  'tokens_in','tokens_out','unit_price_micros_per_mtok'
                ])
            )
        """,
        "post-RLS fixture grants": """
            SELECT has_table_privilege(
                     'tinyassets_fixture_app',
                     'public.artifact_field_visibility',
                     'SELECT'
                   )
               AND has_table_privilege(
                     'tinyassets_fixture_app',
                     'public.forwards',
                     'SELECT'
                   )
        """,
        "market ledger": """
            SELECT to_regclass('market.transactions') IS NOT NULL
               AND to_regclass('market.postings') IS NOT NULL
               AND to_regclass('market.balances') IS NOT NULL
               AND to_regprocedure(
                     'market.apply_tx(text,text,text,text,jsonb)'
                   ) IS NOT NULL
               AND to_regprocedure(
                     'market.apply_settlement(bytea,text)'
                   ) IS NOT NULL
               AND to_regprocedure('market.assert_drained(text)') IS NOT NULL
        """,
        "row security": """
            SELECT count(*) = 9
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename = ANY(ARRAY[
                'users','capabilities','nodes','host_pool','requests','bids',
                'ledger','settlements','flags'
              ])
              AND rowsecurity
        """,
    }
    with connection.cursor() as cursor:
        for description, sql in checks.items():
            cursor.execute(sql)
            if not cursor.fetchone()[0]:
                raise MigrationError(
                    f"existing fixture failed exact baseline check: {description}"
                )


def _record_history(connection, migration: Migration) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL ROLE tinyassets_migration")
        cursor.execute(
            "INSERT INTO public.schema_migrations (version, name, sha256) "
            "VALUES (%s, %s, %s)",
            (migration.version, migration.name, migration.sha256),
        )
        cursor.execute("RESET ROLE")


def run_migrations(
    connection,
    directory: Path,
    *,
    lock_timeout_seconds: float = 5.0,
    baseline_existing: bool = False,
) -> tuple[Migration, ...]:
    """Apply each pending migration and its history row atomically."""
    migrations = discover_migrations(directory)
    _acquire_lock(connection, lock_timeout_seconds)
    try:
        _bootstrap_history(connection)
        history = _read_history(connection)
        _validate_history(history, migrations)
        if not history and _has_untracked_fixture(connection):
            if not baseline_existing:
                raise MigrationError(
                    "untracked fixture schema exists; rerun with "
                    "--baseline-existing after exact verification"
                )
            _verify_existing_fixture(connection)
            for migration in migrations:
                with connection.transaction():
                    _record_history(connection, migration)
            return migrations

        for migration in migrations[len(history) :]:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(migration.path.read_text(encoding="utf-8"))
                _record_history(connection, migration)
        return migrations
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
        connection.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--migrations",
        type=Path,
        default=Path(__file__).with_name("migrations"),
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get(
            "TINYASSETS_V0_DSN",
            "postgresql://tinyassets:tinyassets_v0_dev@localhost:5433/tinyassets_v0",
        ),
    )
    parser.add_argument("--lock-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--baseline-existing", action="store_true")
    args = parser.parse_args()
    try:
        import psycopg
    except ImportError as exc:
        raise MigrationError("psycopg is required to apply migrations") from exc
    with psycopg.connect(args.dsn, autocommit=True) as connection:
        run_migrations(
            connection,
            args.migrations,
            lock_timeout_seconds=args.lock_timeout_seconds,
            baseline_existing=args.baseline_existing,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
