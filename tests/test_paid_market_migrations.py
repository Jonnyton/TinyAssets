from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import threading
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "prototype" / "full-platform-v0"
RUNNER_PATH = PROTOTYPE / "migrate.py"
MIGRATIONS = PROTOTYPE / "migrations"


def _load_runner():
    assert RUNNER_PATH.exists(), "fixture migration runner is missing"
    spec = importlib.util.spec_from_file_location("tinyassets_v0_migrate", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_migration_ids_match_the_migration_directory():
    runner = _load_runner()
    migrations = runner.discover_migrations(MIGRATIONS)
    expected_filenames = sorted(path.name for path in MIGRATIONS.glob("*.sql"))
    assert [migration.filename for migration in migrations] == expected_filenames
    assert [migration.version for migration in migrations] == [
        int(filename.partition("_")[0]) for filename in expected_filenames
    ]


def test_fixture_checksum_uses_exact_file_bytes(tmp_path):
    runner = _load_runner()
    path = tmp_path / "001_first.sql"
    path.write_bytes(b"SELECT 1;\r\n")
    first = runner.discover_migrations(tmp_path)[0]
    assert first.sha256 == hashlib.sha256(b"SELECT 1;\r\n").hexdigest()
    assert first.sql == "SELECT 1;\r\n"

    path.write_bytes(b"SELECT 1;\n")
    second = runner.discover_migrations(tmp_path)[0]
    assert second.sha256 == hashlib.sha256(b"SELECT 1;\n").hexdigest()
    assert second.sha256 != first.sha256


def test_fixture_discovery_accepts_reserved_version_when_present(tmp_path):
    runner = _load_runner()
    for version in range(1, 12):
        (tmp_path / f"{version:03d}_migration.sql").write_text(
            "SELECT 1;\n",
            encoding="utf-8",
        )

    migrations = runner.discover_migrations(tmp_path)

    assert [migration.version for migration in migrations] == list(range(1, 12))


@pytest.mark.parametrize(
    "filenames, message",
    [
        (["001_first.sql", "001_duplicate.sql"], "duplicate migration version 001"),
        (["001_first.sql", "003_gap.sql"], "migration versions must be gap-free"),
        (["001_first.sql", "readme.sql"], "invalid migration filename"),
    ],
)
def test_fixture_discovery_fails_closed_on_ambiguous_history(
    tmp_path, filenames, message
):
    runner = _load_runner()
    for filename in filenames:
        (tmp_path / filename).write_text("SELECT 1;\n", encoding="utf-8")
    with pytest.raises(runner.MigrationError, match=message):
        runner.discover_migrations(tmp_path)


@pytest.fixture
def migrated_database():
    dsn = os.environ.get("TINYASSETS_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TINYASSETS_TEST_POSTGRES_DSN is required for PostgreSQL proof")
    psycopg = pytest.importorskip("psycopg")
    database = f"wave2_migrate_{uuid.uuid4().hex}"
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(psycopg.sql.SQL("CREATE DATABASE {}").format(
            psycopg.sql.Identifier(database)
        ))
    database_dsn = psycopg.conninfo.make_conninfo(dsn, dbname=database)
    try:
        yield psycopg, database_dsn
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s",
                (database,),
            )
            admin.execute(psycopg.sql.SQL("DROP DATABASE {}").format(
                psycopg.sql.Identifier(database)
            ))


def test_fresh_apply_replay_history_privileges_and_populated_baseline(
    migrated_database,
):
    psycopg, dsn = migrated_database
    runner = _load_runner()
    with psycopg.connect(dsn, autocommit=True) as connection:
        runner.run_migrations(connection, MIGRATIONS)
        runner.run_migrations(connection, MIGRATIONS)
        rows = connection.execute(
            "SELECT version, name, length(sha256) "
            "FROM public.schema_migrations ORDER BY version"
        ).fetchall()
        assert rows == [
            (version, name, 64)
            for version, name in zip(
                list(range(1, 14)),
                [
                    "core_tables",
                    "flags",
                    "rls",
                    "indexes",
                    "seed",
                    "discover_nodes",
                    "token_normalization",
                    "forwards",
                    "market_ledger",
                    "outbound_boundary",
                    "goal_canonicals",
                    "authoring_sessions",
                    "paid_market_workflow",
                ],
                strict=True,
            )
        ]
        connection.execute("SET ROLE tinyassets_fixture_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "UPDATE public.schema_migrations "
                "SET sha256 = %s WHERE version = 9",
                ("f" * 64,),
            )
        connection.rollback()
        connection.execute("RESET ROLE")
        assert connection.execute(
            "SELECT "
            "has_function_privilege("
            "'public', 'auth.is_request_bidder(uuid)', 'EXECUTE'), "
            "has_function_privilege("
            "'tinyassets_fixture_app', "
            "'auth.is_request_bidder(uuid)', 'EXECUTE')"
        ).fetchone() == (False, True)
        assert connection.execute(
            "SELECT is_nullable = 'NO' FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'forwards' "
            "AND column_name = 'version'"
        ).fetchone() == (True,)

        user_id = uuid.uuid4()
        connection.execute(
            "INSERT INTO public.users (user_id, display_name) VALUES (%s, 'kept')",
            (user_id,),
        )
        connection.execute("DROP TABLE public.schema_migrations")
        runner.run_migrations(connection, MIGRATIONS, baseline_existing=True)
        assert connection.execute(
            "SELECT display_name FROM public.users WHERE user_id = %s", (user_id,)
        ).fetchone() == ("kept",)

        connection.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles "
            "WHERE rolname = 'tinyassets_fixture_app') THEN "
            "CREATE ROLE tinyassets_fixture_app NOLOGIN; END IF; END $$"
        )
        connection.execute("SET ROLE tinyassets_fixture_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "INSERT INTO public.schema_migrations "
                "(version, name, sha256) VALUES (99, 'forged', %s)",
                ("0" * 64,),
            )
        connection.rollback()
        connection.execute("RESET ROLE")


def test_populated_baseline_is_independent_of_runner_role_name(
    migrated_database,
):
    psycopg, dsn = migrated_database
    runner = _load_runner()
    role = f"wave2_alt_runner_{uuid.uuid4().hex}"
    password = uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        session_user = admin.execute("SELECT session_user").fetchone()[0]
        admin.execute(
            psycopg.sql.SQL("CREATE ROLE {} SUPERUSER").format(
                psycopg.sql.Identifier(role)
            ) + psycopg.sql.SQL(" LOGIN PASSWORD {}").format(
                psycopg.sql.Literal(password)
            )
        )
    runner_dsn = psycopg.conninfo.make_conninfo(
        dsn,
        user=role,
        password=password,
    )
    try:
        with psycopg.connect(runner_dsn, autocommit=True) as connection:
            runner.run_migrations(connection, MIGRATIONS)
            connection.execute("DROP TABLE public.schema_migrations")
            runner.run_migrations(
                connection,
                MIGRATIONS,
                baseline_existing=True,
            )
            assert connection.execute(
                "SELECT count(*) FROM public.schema_migrations"
            ).fetchone() == (13,)
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(
                psycopg.sql.SQL("REASSIGN OWNED BY {} TO {}").format(
                    psycopg.sql.Identifier(role),
                    psycopg.sql.Identifier(session_user),
                )
            )
            admin.execute(
                psycopg.sql.SQL("DROP OWNED BY {}").format(
                    psycopg.sql.Identifier(role)
                )
            )
            admin.execute(
                psycopg.sql.SQL("DROP ROLE {}").format(
                    psycopg.sql.Identifier(role)
                )
            )


def test_failed_migration_rolls_back_and_resume_applies_once(
    migrated_database, tmp_path
):
    psycopg, dsn = migrated_database
    runner = _load_runner()
    for migration in MIGRATIONS.glob("*.sql"):
        shutil.copy2(migration, tmp_path / migration.name)
    failing = tmp_path / "014_failure_probe.sql"
    failing.write_text(
        "CREATE TABLE public.failure_probe (id integer);\nSELECT 1 / 0;\n",
        encoding="utf-8",
    )
    with psycopg.connect(dsn, autocommit=True) as connection:
        with pytest.raises(psycopg.errors.DivisionByZero):
            runner.run_migrations(connection, tmp_path)
        assert connection.execute(
            "SELECT to_regclass('public.failure_probe')"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT count(*) FROM public.schema_migrations WHERE version = 14"
        ).fetchone() == (0,)

        failing.write_text(
            "CREATE TABLE public.failure_probe (id integer PRIMARY KEY);\n",
            encoding="utf-8",
        )
        runner.run_migrations(connection, tmp_path)
        runner.run_migrations(connection, tmp_path)
        assert connection.execute(
            "SELECT count(*) FROM public.schema_migrations WHERE version = 14"
        ).fetchone() == (1,)


def test_populated_baseline_rejects_missing_late_migration_objects(
    migrated_database,
):
    psycopg, dsn = migrated_database
    runner = _load_runner()
    with psycopg.connect(dsn, autocommit=True) as connection:
        runner.run_migrations(connection, MIGRATIONS)
        connection.execute("DROP TABLE public.schema_migrations")
        connection.execute(
            "DROP TABLE public.artifact_field_visibility CASCADE"
        )
        with pytest.raises(
            runner.MigrationError,
            match="exact baseline check: discovery surface",
        ):
            runner.run_migrations(
                connection,
                MIGRATIONS,
                baseline_existing=True,
            )
        assert connection.execute(
            "SELECT count(*) FROM public.schema_migrations"
        ).fetchone() == (0,)


def test_populated_baseline_history_is_recorded_atomically(
    migrated_database,
    monkeypatch,
):
    psycopg, dsn = migrated_database
    runner = _load_runner()
    original_record_history = runner._record_history

    def fail_mid_baseline(connection, migration):
        if migration.version == 5:
            raise runner.MigrationError("injected baseline history failure")
        original_record_history(connection, migration)

    with psycopg.connect(dsn, autocommit=True) as connection:
        runner.run_migrations(connection, MIGRATIONS)
        connection.execute("DROP TABLE public.schema_migrations")
        monkeypatch.setattr(runner, "_record_history", fail_mid_baseline)
        with pytest.raises(
            runner.MigrationError,
            match="injected baseline history failure",
        ):
            runner.run_migrations(
                connection,
                MIGRATIONS,
                baseline_existing=True,
            )
        assert connection.execute(
            "SELECT count(*) FROM public.schema_migrations"
        ).fetchone() == (0,)

        monkeypatch.setattr(runner, "_record_history", original_record_history)
        runner.run_migrations(
            connection,
            MIGRATIONS,
            baseline_existing=True,
        )
        assert connection.execute(
            "SELECT count(*) FROM public.schema_migrations"
        ).fetchone() == (13,)


def test_populated_baseline_rejects_lookalike_function_body(
    migrated_database,
):
    psycopg, dsn = migrated_database
    runner = _load_runner()
    with psycopg.connect(dsn, autocommit=True) as connection:
        runner.run_migrations(connection, MIGRATIONS)
        connection.execute("DROP TABLE public.schema_migrations")
        connection.execute(
            "CREATE OR REPLACE FUNCTION auth.is_request_bidder(p_request_id uuid) "
            "RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER "
            "SET search_path = pg_catalog, public AS 'SELECT true'"
        )
        with pytest.raises(
            runner.MigrationError,
            match="exact baseline check: catalog fingerprint",
        ):
            runner.run_migrations(
                connection,
                MIGRATIONS,
                baseline_existing=True,
            )
        assert connection.execute(
            "SELECT count(*) FROM public.schema_migrations"
        ).fetchone() == (0,)


def test_checksum_drift_lock_timeout_and_concurrent_runners(
    migrated_database, tmp_path
):
    psycopg, dsn = migrated_database
    runner = _load_runner()
    for migration in MIGRATIONS.glob("*.sql"):
        shutil.copy2(migration, tmp_path / migration.name)

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def apply_concurrently():
        try:
            with psycopg.connect(dsn, autocommit=True) as connection:
                barrier.wait(timeout=5)
                runner.run_migrations(connection, tmp_path)
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [threading.Thread(target=apply_concurrently) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors

    with psycopg.connect(dsn, autocommit=True) as connection:
        assert connection.execute(
            "SELECT array_agg(version ORDER BY version) "
            "FROM public.schema_migrations"
        ).fetchone() == (list(range(1, 14)),)
        first = tmp_path / "001_core_tables.sql"
        first.write_bytes(first.read_bytes() + b"\n")
        with pytest.raises(runner.MigrationError, match="checksum drift"):
            runner.run_migrations(connection, tmp_path)
        first.write_bytes(first.read_bytes()[:-1])

    with (
        psycopg.connect(dsn, autocommit=True) as lock_holder,
        psycopg.connect(dsn, autocommit=True) as contender,
    ):
        lock_holder.execute("SELECT pg_advisory_lock(%s)", (runner._LOCK_KEY,))
        with pytest.raises(runner.MigrationError, match="lock unavailable"):
            runner.run_migrations(
                contender, tmp_path, lock_timeout_seconds=0.05
            )
        lock_holder.execute("SELECT pg_advisory_unlock(%s)", (runner._LOCK_KEY,))
