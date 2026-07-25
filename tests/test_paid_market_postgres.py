from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import random
import threading
import uuid
from pathlib import Path

import pytest

from tinyassets.paid_market.ledger import Ledger, LedgerError

ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "prototype" / "full-platform-v0"
MIGRATIONS = PROTOTYPE / "migrations"
RUNNER_PATH = PROTOTYPE / "migrate.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("tinyassets_v0_migrate", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def market_database():
    dsn = os.environ.get("TINYASSETS_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TINYASSETS_TEST_POSTGRES_DSN is required for PostgreSQL proof")
    psycopg = pytest.importorskip("psycopg")
    database = f"wave2_market_{uuid.uuid4().hex}"
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(
            psycopg.sql.SQL("CREATE DATABASE {}").format(
                psycopg.sql.Identifier(database)
            )
        )
    database_dsn = psycopg.conninfo.make_conninfo(dsn, dbname=database)
    with psycopg.connect(database_dsn, autocommit=True) as connection:
        _load_runner().run_migrations(connection, MIGRATIONS)
    try:
        yield psycopg, database_dsn
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s",
                (database,),
            )
            admin.execute(
                psycopg.sql.SQL("DROP DATABASE {}").format(
                    psycopg.sql.Identifier(database)
                )
            )


def _body(
    key: str,
    postings: list[tuple[str, int]],
    *,
    tenant: str = "tenant-a",
    memo: str = "accepted",
) -> bytes:
    value = {
        "authority": {"tenant_id": tenant},
        "idempotency_key": key,
        "memo": memo,
        "postings": [
            {"account": account, "delta_micros": delta}
            for account, delta in postings
        ],
        "schema_version": 1,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _apply(connection, body: bytes, supplied_hash: str | None = None):
    supplied_hash = supplied_hash or hashlib.sha256(body).hexdigest()
    return connection.execute(
        "SELECT status, tx_id "
        "FROM market.apply_settlement(%s::bytea, %s)",
        (body, supplied_hash),
    ).fetchone()


def test_ledger_boundary_is_non_login_fixed_path_and_least_privilege(
    market_database,
):
    psycopg, dsn = market_database
    with psycopg.connect(dsn, autocommit=True) as connection:
        owner = connection.execute(
            "SELECT r.rolcanlogin, p.prosecdef, p.proconfig "
            "FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner "
            "WHERE p.oid = 'market.apply_settlement(bytea,text)'::regprocedure"
        ).fetchone()
        assert owner == (
            False,
            True,
            ["search_path=pg_catalog, market, pg_temp"],
        )
        assert connection.execute(
            "SELECT rolcanlogin FROM pg_roles "
            "WHERE rolname = 'tinyassets_fixture_settlement'"
        ).fetchone() == (False,)

        connection.execute("SET ROLE tinyassets_fixture_app")
        for statement in (
            "INSERT INTO market.transactions "
            "(tenant_id, idempotency_key, request_sha256, memo) "
            "VALUES ('tenant-a', 'forged', repeat('0', 64), '')",
            "SELECT * FROM market.apply_settlement("
            "'{}'::text::bytea, repeat('0', 64))",
            "SELECT market.assert_drained('escrow:x')",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(statement)
            connection.rollback()
            connection.execute("SET ROLE tinyassets_fixture_app")
        connection.execute("RESET ROLE")

        connection.execute("SET ROLE tinyassets_fixture_settlement")
        for statement in (
            "INSERT INTO market.balances(account, balance_micros) "
            "VALUES ('user:forged', 1)",
            "SELECT * FROM market.apply_tx("
            "'tenant-a', 'forged', repeat('0', 64), '', '[]'::jsonb)",
            "SELECT market.assert_drained('escrow:x')",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(statement)
            connection.rollback()
            connection.execute("SET ROLE tinyassets_fixture_settlement")

        connection.execute(
            "CREATE FUNCTION pg_temp.sha256(bytea) RETURNS bytea "
            "LANGUAGE sql IMMUTABLE AS 'SELECT decode(repeat(''0'', 64), ''hex'')'"
        )
        body = _body(
            "hostile-path",
            [("escrow:path", -100), ("user:seller", 99), ("treasury", 1)],
        )
        connection.execute("RESET ROLE")
        connection.execute(
            "INSERT INTO market.balances(account, balance_micros) "
            "VALUES ('escrow:path', 100)"
        )
        connection.execute("SET ROLE tinyassets_fixture_settlement")
        assert _apply(connection, body)[0] == "applied"


def test_canonical_hash_replay_conflict_and_bounds(market_database):
    psycopg, dsn = market_database
    body = _body(
        "settle:1",
        [("escrow:1", -10_000), ("user:seller", 9_900), ("treasury", 100)],
    )
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO market.balances(account, balance_micros) "
            "VALUES ('escrow:1', 10000)"
        )
        connection.execute("SET ROLE tinyassets_fixture_settlement")
        first = _apply(connection, body)
        replay = _apply(connection, body)
        assert first == ("applied", replay[1])
        assert replay[0] == "replayed"
        with pytest.raises(psycopg.errors.RaiseException, match="idempotency conflict"):
            _apply(connection, _body("settle:1", [
                ("escrow:1", -10_000),
                ("user:seller", 9_899),
                ("treasury", 101),
            ]))
        with pytest.raises(psycopg.errors.RaiseException, match="hash mismatch"):
            _apply(connection, _body("settle:2", [
                ("escrow:1", -1),
                ("treasury", 1),
            ]), "0" * 64)

        invalid = (
            _body("x" * 129, [("escrow:1", -1), ("treasury", 1)]),
            _body(
                "memo",
                [("escrow:1", -1), ("treasury", 1)],
                memo="m" * 513,
            ),
            _body(
                "account",
                [("escrow:" + "x" * 250, -1), ("treasury", 1)],
            ),
            _body(
                "postings",
                [("escrow:1", -16)]
                + [(f"user:{index}", 1) for index in range(16)]
                + [("treasury", 0)],
            ),
            _body("external", [("external:mint", -1), ("treasury", 1)]),
            _body("pool", [("pool:forged", -1), ("treasury", 1)]),
            _body("treasury", [("escrow:1", -1), ("treasury:forged", 1)]),
            _body("no-fee", [("escrow:1", -1), ("user:seller", 1)]),
            b"{" + b" " * 16384 + b"}",
        )
        for rejected in invalid:
            with pytest.raises(psycopg.errors.RaiseException):
                _apply(connection, rejected)


def test_identical_replay_100_callers_applies_once(market_database):
    psycopg, dsn = market_database
    body = _body(
        "settle:100",
        [("escrow:100", -10_000), ("user:seller", 9_900), ("treasury", 100)],
    )
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO market.balances(account, balance_micros) "
            "VALUES ('escrow:100', 10000)"
        )

    barrier = threading.Barrier(100)
    results: list[tuple[str, int]] = []
    errors: list[Exception] = []

    def apply_once():
        try:
            with psycopg.connect(dsn, autocommit=True) as connection:
                connection.execute("SET ROLE tinyassets_fixture_settlement")
                barrier.wait(timeout=10)
                results.append(_apply(connection, body))
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    threads = [threading.Thread(target=apply_once) for _ in range(100)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not errors
    assert len(results) == 100
    assert len({tx_id for _, tx_id in results}) == 1
    assert [status for status, _ in results].count("applied") == 1

    with psycopg.connect(dsn, autocommit=True) as connection:
        assert connection.execute(
            "SELECT count(*) FROM market.postings"
        ).fetchone() == (3,)


def test_duplicate_accounts_match_pure_ledger_and_failures_roll_back(
    market_database,
):
    psycopg, dsn = market_database
    rng = random.Random(20260724)
    pure = Ledger({"escrow:diff": 1_000_000})
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO market.balances(account, balance_micros) "
            "VALUES ('escrow:diff', 1000000)"
        )
        connection.execute("SET ROLE tinyassets_fixture_settlement")
        for index in range(50):
            gross = rng.randint(100, 10_000)
            fee = gross // 100
            entries = [
                ("escrow:diff", -gross),
                ("user:seller", gross - fee),
                ("treasury", fee // 2),
                ("treasury", fee - fee // 2),
            ]
            pure.apply(entries)
            assert _apply(connection, _body(f"diff:{index}", entries))[0] == "applied"

        connection.execute("RESET ROLE")
        actual = dict(
            connection.execute(
                "SELECT account, balance_micros FROM market.balances"
            ).fetchall()
        )
        assert actual == pure.balances
        connection.execute("SET ROLE tinyassets_fixture_settlement")

        overdraft = _body(
            "overdraft",
            [
                ("escrow:diff", -2_000_000),
                ("user:seller", 1_980_000),
                ("treasury", 20_000),
            ],
        )
        with pytest.raises(LedgerError):
            pure.apply([
                ("escrow:diff", -2_000_000),
                ("user:seller", 1_980_000),
                ("treasury", 20_000),
            ])
        with pytest.raises(psycopg.errors.RaiseException, match="overdraft"):
            _apply(connection, overdraft)
        connection.execute("RESET ROLE")
        assert connection.execute(
            "SELECT count(*) FROM market.transactions "
            "WHERE idempotency_key = 'overdraft'"
        ).fetchone() == (0,)
