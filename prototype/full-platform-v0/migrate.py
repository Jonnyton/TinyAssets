"""Replay-safe migration runner for the local full-platform-v0 fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import NamedTuple

_MIGRATION_NAME = re.compile(r"^(?P<version>\d{3})_(?P<name>[a-z0-9_]+)\.sql$")
_RESERVED_MIGRATION_VERSIONS = frozenset({10})
_LOCK_KEY = 7_293_461_550_848_602_031
_FIXTURE_SCHEMA_SHA256 = (
    "56937c99d9467b10b7862a50601ddd2c199529901283da83bd37825504f0b473"
)


class MigrationError(RuntimeError):
    """The fixture migration chain is unsafe or cannot be applied."""


class Migration(NamedTuple):
    version: int
    name: str
    filename: str
    path: Path
    sha256: str
    sql: str


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
        raw_sql = path.read_bytes()
        try:
            sql = raw_sql.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MigrationError(
                f"migration is not valid UTF-8: {path.name}"
            ) from exc
        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                filename=path.name,
                path=path,
                sha256=hashlib.sha256(raw_sql).hexdigest(),
                sql=sql,
            )
        )

    actual = [migration.version for migration in migrations]
    expected = [
        version
        for version in range(1, (actual[-1] if actual else 0) + 1)
        if version not in _RESERVED_MIGRATION_VERSIONS or version in versions
    ]
    if actual != expected:
        raise MigrationError(
            "migration versions must be gap-free from 001 except reserved "
            f"versions {sorted(_RESERVED_MIGRATION_VERSIONS)}: got {actual}"
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
        "market workflow": """
            SELECT ARRAY[
              'requests','bids','matches','match_bids','fanout_slots',
              'claims','transition_events','outbox','authority_grants',
              'command_log'
            ]::text[] <@ ARRAY(
              SELECT tablename::text
              FROM pg_tables
              WHERE schemaname = 'market_workflow'
            )
               AND to_regprocedure(
                     'market_workflow.submit_request(bytea,text)'
                   ) IS NOT NULL
               AND to_regprocedure(
                     'market_workflow.transition_request(bytea,text)'
                   ) IS NOT NULL
               AND to_regprocedure(
                     'market_workflow.apply_accounting_settlement(uuid,bigint,bytea,text)'
                   ) IS NOT NULL
               AND to_regprocedure(
                     'market_workflow.workflow_status()'
                   ) IS NOT NULL
               AND to_regprocedure(
                     'market_workflow.can_read_request(text,uuid)'
                   ) IS NOT NULL
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
    actual_fingerprint = _fixture_schema_sha256(connection)
    if actual_fingerprint != _FIXTURE_SCHEMA_SHA256:
        raise MigrationError(
            "existing fixture failed exact baseline check: catalog fingerprint "
            f"{actual_fingerprint}"
        )


def _fixture_schema_sha256(connection) -> str:
    """Hash the complete fixture-owned catalog surface deterministically."""
    query = """
        WITH runner AS (
          SELECT oid FROM pg_roles WHERE rolname = current_user
        ),
        fixture_objects AS (
          SELECT 'extension'::text AS kind,
                 e.extname::text AS identity,
                 e.extname::text AS definition
          FROM pg_extension AS e
          WHERE e.extname = ANY(ARRAY['pgcrypto','vector'])

          UNION ALL
          SELECT 'role', r.rolname,
                 concat_ws('|', r.rolcanlogin, r.rolsuper, r.rolinherit)
          FROM pg_roles AS r
          WHERE r.rolname = ANY(ARRAY[
            'tinyassets_fixture_app',
            'tinyassets_fixture_market_owner',
            'tinyassets_fixture_settlement',
            'tinyassets_fixture_workflow_command',
            'tinyassets_fixture_workflow_owner',
            'tinyassets_fixture_workflow_reader',
            'tinyassets_migration'
          ])

          UNION ALL
          SELECT 'schema', n.nspname,
                 concat_ws(
                   '|',
                   CASE pg_get_userbyid(n.nspowner)
                     WHEN current_user THEN '<runner>'
                     ELSE pg_get_userbyid(n.nspowner)
                   END,
                   coalesce((
                     SELECT string_agg(item, ',' ORDER BY item)
                     FROM (
                       SELECT concat_ws(
                                ':',
                                CASE acl.grantee
                                  WHEN 0 THEN 'PUBLIC'
                                  WHEN (SELECT oid FROM runner) THEN '<runner>'
                                  ELSE pg_get_userbyid(acl.grantee)
                                END,
                                CASE acl.grantor
                                  WHEN (SELECT oid FROM runner) THEN '<runner>'
                                  ELSE pg_get_userbyid(acl.grantor)
                                END,
                                acl.privilege_type,
                                acl.is_grantable
                              ) AS item
                       FROM aclexplode(n.nspacl) AS acl
                     ) AS normalized_acl
                   ), '')
                 )
          FROM pg_namespace AS n
          WHERE n.nspname = ANY(
            ARRAY['public','auth','market','market_workflow']
          )

          UNION ALL
          SELECT 'relation',
                 n.nspname || '.' || c.relname,
                 concat_ws(
                   '|',
                   c.relkind,
                   CASE pg_get_userbyid(c.relowner)
                     WHEN current_user THEN '<runner>'
                     ELSE pg_get_userbyid(c.relowner)
                   END,
                   c.relrowsecurity,
                   c.relforcerowsecurity,
                   coalesce((
                     SELECT string_agg(item, ',' ORDER BY item)
                     FROM (
                       SELECT concat_ws(
                                ':',
                                CASE acl.grantee
                                  WHEN 0 THEN 'PUBLIC'
                                  WHEN (SELECT oid FROM runner) THEN '<runner>'
                                  ELSE pg_get_userbyid(acl.grantee)
                                END,
                                CASE acl.grantor
                                  WHEN (SELECT oid FROM runner) THEN '<runner>'
                                  ELSE pg_get_userbyid(acl.grantor)
                                END,
                                acl.privilege_type,
                                acl.is_grantable
                              ) AS item
                       FROM aclexplode(c.relacl) AS acl
                     ) AS normalized_acl
                   ), '')
                 )
          FROM pg_class AS c
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
          WHERE n.nspname = ANY(
            ARRAY['public','auth','market','market_workflow']
          )
            AND c.relkind = ANY(ARRAY['r','p','S'])
            AND NOT (
              n.nspname = 'public' AND c.relname = 'schema_migrations'
            )

          UNION ALL
          SELECT 'column',
                 n.nspname || '.' || c.relname || '.' || a.attname,
                 concat_ws(
                   '|',
                   a.attnum,
                   format_type(a.atttypid, a.atttypmod),
                   a.attnotnull,
                   coalesce(pg_get_expr(d.adbin, d.adrelid), '')
                 )
          FROM pg_attribute AS a
          JOIN pg_class AS c ON c.oid = a.attrelid
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
          LEFT JOIN pg_attrdef AS d
            ON d.adrelid = a.attrelid AND d.adnum = a.attnum
          WHERE n.nspname = ANY(
            ARRAY['public','auth','market','market_workflow']
          )
            AND c.relkind = ANY(ARRAY['r','p'])
            AND NOT (
              n.nspname = 'public' AND c.relname = 'schema_migrations'
            )
            AND a.attnum > 0
            AND NOT a.attisdropped

          UNION ALL
          SELECT 'constraint',
                 n.nspname || '.' || c.relname || '.' || con.conname,
                 pg_get_constraintdef(con.oid, true)
          FROM pg_constraint AS con
          JOIN pg_class AS c ON c.oid = con.conrelid
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
          WHERE n.nspname = ANY(
            ARRAY['public','auth','market','market_workflow']
          )
            AND NOT (
              n.nspname = 'public' AND c.relname = 'schema_migrations'
            )

          UNION ALL
          SELECT 'index',
                 schemaname || '.' || indexname,
                 indexdef
          FROM pg_indexes
          WHERE schemaname = ANY(
            ARRAY['public','auth','market','market_workflow']
          )
            AND NOT (
              schemaname = 'public' AND tablename = 'schema_migrations'
            )

          UNION ALL
          SELECT 'policy',
                 schemaname || '.' || tablename || '.' || policyname,
                 concat_ws(
                   '|',
                   permissive,
                   roles::text,
                   cmd,
                   coalesce(qual, ''),
                   coalesce(with_check, '')
                 )
          FROM pg_policies
          WHERE schemaname = ANY(
            ARRAY['public','auth','market','market_workflow']
          )

          UNION ALL
          SELECT 'function',
                 n.nspname || '.' || p.proname || '('
                   || pg_get_function_identity_arguments(p.oid) || ')',
                 concat_ws(
                   '|',
                   CASE pg_get_userbyid(p.proowner)
                     WHEN current_user THEN '<runner>'
                     ELSE pg_get_userbyid(p.proowner)
                   END,
                   p.prosecdef,
                   p.provolatile,
                   coalesce(p.proconfig::text, ''),
                   coalesce((
                     SELECT string_agg(item, ',' ORDER BY item)
                     FROM (
                       SELECT concat_ws(
                                ':',
                                CASE acl.grantee
                                  WHEN 0 THEN 'PUBLIC'
                                  WHEN (SELECT oid FROM runner) THEN '<runner>'
                                  ELSE pg_get_userbyid(acl.grantee)
                                END,
                                CASE acl.grantor
                                  WHEN (SELECT oid FROM runner) THEN '<runner>'
                                  ELSE pg_get_userbyid(acl.grantor)
                                END,
                                acl.privilege_type,
                                acl.is_grantable
                              ) AS item
                       FROM aclexplode(p.proacl) AS acl
                     ) AS normalized_acl
                   ), ''),
                   pg_get_functiondef(p.oid)
                 )
          FROM pg_proc AS p
          JOIN pg_namespace AS n ON n.oid = p.pronamespace
          WHERE n.nspname = ANY(ARRAY['auth','market','market_workflow'])
             OR (
               n.nspname = 'public'
               AND p.proname = ANY(ARRAY[
                 'discover_nodes',
                 'strip_private_fields'
               ])
             )
        )
        SELECT kind, identity, definition
        FROM fixture_objects
        ORDER BY kind, identity, definition
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
    encoded = json.dumps(
        rows,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
            with connection.transaction():
                for migration in migrations:
                    _record_history(connection, migration)
            return migrations

        for migration in migrations[len(history) :]:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(migration.sql)
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
