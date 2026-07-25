from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import random
import uuid
from pathlib import Path

import pytest

from tinyassets.paid_market.ledger import spot_settlement_entries

ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "prototype" / "full-platform-v0"
MIGRATIONS = PROTOTYPE / "migrations"
WORKFLOW_MIGRATION = MIGRATIONS / "010_paid_market_workflow.sql"
RUNNER_PATH = PROTOTYPE / "migrate.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("tinyassets_v0_migrate", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_workflow_migration_is_dark_and_omits_unowned_delivery_authority():
    sql = WORKFLOW_MIGRATION.read_text(encoding="utf-8")
    assert "CREATE SCHEMA market_workflow" in sql
    for table in (
        "requests",
        "bids",
        "matches",
        "match_bids",
        "fanout_slots",
        "claims",
        "transition_events",
        "outbox",
        "authority_grants",
    ):
        assert f"CREATE TABLE market_workflow.{table}" in sql
    for function in (
        "submit_request",
        "transition_request",
        "apply_accounting_settlement",
        "workflow_status",
    ):
        assert f"CREATE FUNCTION market_workflow.{function}" in sql
    assert "lease_fence" not in sql
    assert "accepted_result_sha256" not in sql
    assert "delivery_receipt" not in sql
    assert "CREATE TABLE market_workflow.disput" not in sql
    assert "CREATE TABLE market_workflow.accept" not in sql


@pytest.fixture
def workflow_database():
    dsn = os.environ.get("TINYASSETS_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TINYASSETS_TEST_POSTGRES_DSN is required for PostgreSQL proof")
    psycopg = pytest.importorskip("psycopg")
    database = f"wave2_workflow_{uuid.uuid4().hex}"
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


def _seed_identity(connection):
    buyer = uuid.uuid4()
    seller = uuid.uuid4()
    capability = f"cap-{uuid.uuid4().hex}"
    connection.execute(
        "INSERT INTO public.users(user_id, display_name) VALUES "
        "(%s, 'buyer'), (%s, 'seller')",
        (buyer, seller),
    )
    connection.execute(
        "INSERT INTO public.capabilities(capability_id, node_type, llm_model) "
        "VALUES (%s, 'workflow', 'fixture')",
        (capability,),
    )
    return buyer, seller, capability


def _set_actor(connection, *, role, actor, tenant):
    connection.execute(f"SET ROLE {role}")
    connection.execute("SELECT set_config('app.current_user_id', %s, false)", (str(actor),))
    connection.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant,))


def _request_body(*, key, requester, capability, tenant="tenant-a", payload="a" * 64):
    value = {
        "schema_version": 1,
        "idempotency_key": key,
        "requester_user_id": str(requester),
        "capability_digest": capability,
        "payload_sha256": payload,
        "budget_micros": 10_000,
        "spend_cap_micros": 10_000,
        "bid_window_ends_at": 2_000_000_000,
        "deadline": 2_000_003_600,
        "acceptance_policy": "machine_gate_only:v1",
        "settlement_policy_version": "spot:v1",
        "visibility": "paid",
        "fanout_limit": 1,
        "tenant_advisory": tenant,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _transition_body(*, key, request_id, expected_version, action):
    value = {
        "schema_version": 1,
        "idempotency_key": key,
        "request_id": str(request_id),
        "expected_version": expected_version,
        "action": action,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _call_body(connection, function, body):
    return connection.execute(
        f"SELECT * FROM market_workflow.{function}(%s::bytea, %s)",
        (body, hashlib.sha256(body).hexdigest()),
    ).fetchone()


def test_workflow_roles_deny_direct_dml_and_commands_use_fixed_non_login_owner(
    workflow_database,
):
    psycopg, dsn = workflow_database
    with psycopg.connect(dsn, autocommit=True) as connection:
        assert connection.execute(
            "SELECT rolcanlogin FROM pg_roles "
            "WHERE rolname = 'tinyassets_fixture_workflow_owner'"
        ).fetchone() == (False,)
        assert connection.execute(
            "SELECT "
            "has_table_privilege('public', 'market_workflow.requests', 'INSERT'), "
            "has_table_privilege('tinyassets_fixture_app', "
            "'market_workflow.requests', 'INSERT'), "
            "has_table_privilege('tinyassets_fixture_workflow_command', "
            "'market_workflow.requests', 'INSERT')"
        ).fetchone() == (False, False, False)
        owner, security_definer, settings = connection.execute(
            "SELECT pg_get_userbyid(proowner), prosecdef, proconfig "
            "FROM pg_proc WHERE oid = "
            "'market_workflow.submit_request(bytea,text)'::regprocedure"
        ).fetchone()
        assert owner == "tinyassets_fixture_workflow_owner"
        assert security_definer is True
        assert settings == [
            "search_path=pg_catalog, market_workflow, auth, pg_temp"
        ]

        _set_actor(
            connection,
            role="tinyassets_fixture_workflow_command",
            actor=uuid.uuid4(),
            tenant="tenant-a",
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                "INSERT INTO market_workflow.requests DEFAULT VALUES"
            )


def test_submission_transition_idempotency_authority_outbox_and_hostile_search_path(
    workflow_database,
):
    psycopg, dsn = workflow_database
    with psycopg.connect(dsn, autocommit=True) as connection:
        buyer, _, capability = _seed_identity(connection)
        connection.execute("CREATE SCHEMA hostile")
        connection.execute(
            "CREATE TABLE hostile.requests(request_id uuid PRIMARY KEY)"
        )
        _set_actor(
            connection,
            role="tinyassets_fixture_workflow_command",
            actor=buyer,
            tenant="tenant-a",
        )
        connection.execute("SET search_path = hostile, public")
        body = _request_body(key="submit", requester=buyer, capability=capability)
        applied = _call_body(connection, "submit_request", body)
        replayed = _call_body(connection, "submit_request", body)
        assert applied[0] == "applied"
        assert replayed == ("replayed", applied[1], 1)

        changed = _request_body(
            key="submit",
            requester=buyer,
            capability=capability,
            payload="b" * 64,
        )
        with pytest.raises(psycopg.errors.RaiseException, match="idempotency conflict"):
            _call_body(connection, "submit_request", changed)

        transition = _transition_body(
            key="open",
            request_id=applied[1],
            expected_version=1,
            action="open_bidding",
        )
        opened = _call_body(connection, "transition_request", transition)
        assert opened == ("applied", applied[1], "bidding", 2)
        cancel = _transition_body(
            key="cancel",
            request_id=applied[1],
            expected_version=2,
            action="cancel_request",
        )
        cancelled = _call_body(connection, "transition_request", cancel)
        assert cancelled == ("applied", applied[1], "cancelled", 3)
        assert _call_body(connection, "transition_request", transition) == (
            "replayed",
            applied[1],
            "bidding",
            2,
        )
        connection.execute("RESET ROLE")
        assert connection.execute(
            "SELECT count(*) FROM market_workflow.transition_events "
            "WHERE request_id = %s",
            (applied[1],),
        ).fetchone() == (3,)
        assert connection.execute(
            "SELECT request_version, capability_digest "
            "FROM market_workflow.outbox ORDER BY request_version"
        ).fetchall() == [(2, capability), (3, capability)]

        _set_actor(
            connection,
            role="tinyassets_fixture_workflow_command",
            actor=uuid.uuid4(),
            tenant="tenant-a",
        )
        denied_cancel = _transition_body(
            key="denied-cancel",
            request_id=applied[1],
            expected_version=3,
            action="cancel_request",
        )
        with pytest.raises(psycopg.errors.RaiseException, match="requester authority"):
            _call_body(connection, "transition_request", denied_cancel)


def test_rls_hides_full_workflow_rows_from_unrelated_tenant_member(
    workflow_database,
):
    psycopg, dsn = workflow_database
    with psycopg.connect(dsn, autocommit=True) as connection:
        buyer, _, capability = _seed_identity(connection)
        intruder = uuid.uuid4()
        connection.execute(
            "INSERT INTO public.users(user_id, display_name) "
            "VALUES (%s, 'intruder')",
            (intruder,),
        )
        _set_actor(
            connection,
            role="tinyassets_fixture_workflow_command",
            actor=buyer,
            tenant="tenant-a",
        )
        body = _request_body(key="private", requester=buyer, capability=capability)
        request_id = _call_body(connection, "submit_request", body)[1]
        opened = _transition_body(
            key="private-open",
            request_id=request_id,
            expected_version=1,
            action="open_bidding",
        )
        _call_body(connection, "transition_request", opened)
        connection.execute("RESET ROLE")

        _set_actor(
            connection,
            role="tinyassets_fixture_workflow_reader",
            actor=intruder,
            tenant="tenant-a",
        )
        for table in ("requests", "matches", "claims", "transition_events", "outbox"):
            assert connection.execute(
                f"SELECT count(*) FROM market_workflow.{table}"
            ).fetchone() == (0,)


def _settlement_body(
    *,
    key,
    request_id,
    buyer,
    seller,
    tenant="tenant-a",
    gross=10_000,
    subject=None,
    grant_id=None,
    grant_signature=None,
    grant_generation=None,
    supply_route=None,
):
    escrow = f"escrow:{request_id}"
    postings = tuple(
        spot_settlement_entries(
            escrow_account=escrow,
            seller_account=f"user:{seller}",
            gross_micros=gross,
        )
    )
    value = {
        "action": "settle",
        "amount_micros": gross,
        "authority": {
            "grant": (
                {
                    "grant_id": str(grant_id),
                    "revocation_generation": grant_generation,
                    "verified_signature_sha256": grant_signature,
                }
                if grant_id
                else None
            ),
            "host_owner_user_id": str(seller),
            "requester_user_id": str(buyer),
            "subject_id": str(subject or buyer),
            "tenant_id": tenant,
        },
        "business_reference": str(request_id),
        "escrow_account": escrow,
        "expected_state_version": 7,
        "idempotency_key": key,
        "memo": "dark accepted settlement",
        "postings": [
            {"account": account, "delta_micros": delta}
            for account, delta in postings
        ],
        "schema_version": 1,
    }
    if supply_route is not None:
        value["supply_route"] = supply_route
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _seed_accepted_request(
    connection,
    *,
    buyer,
    seller,
    capability,
    residual=0,
    gross=10_000,
    spend_cap=None,
):
    request_id = uuid.uuid4()
    bid_id = uuid.uuid4()
    match_id = uuid.uuid4()
    authorized_cap = gross if spend_cap is None else spend_cap
    connection.execute(
        "INSERT INTO market_workflow.requests("
        "request_id, tenant_id, requester_user_id, capability_digest, "
        "payload_sha256, budget_micros, spend_cap_micros, bid_window_ends_at, "
        "deadline, acceptance_policy, settlement_policy_version, visibility, "
        "fanout_limit, state, version, idempotency_key, command_sha256"
        ") VALUES (%s, 'tenant-a', %s, %s, %s, %s, %s, "
        "to_timestamp(2000000000), to_timestamp(2000003600), "
        "'machine_gate_only:v1', 'spot:v1', 'paid', 1, 'accepted', 7, %s, %s)",
        (
            request_id,
            buyer,
            capability,
            "a" * 64,
            authorized_cap,
            authorized_cap,
            f"seed:{request_id}",
            "b" * 64,
        ),
    )
    connection.execute(
        "INSERT INTO market_workflow.bids("
        "bid_id, bid_version, request_id, tenant_id, host_id, "
        "host_owner_user_id, capability_digest, size_mtok, "
        "price_micros_per_mtok, expires_at, capacity_grant_id, "
        "capacity_fence, state, command_sha256"
        ") VALUES (%s, 1, %s, 'tenant-a', %s, %s, %s, 10, 5, "
        "to_timestamp(2000000000), %s, 1, 'claimed', %s)",
        (
            bid_id,
            request_id,
            uuid.uuid4(),
            seller,
            capability,
            uuid.uuid4(),
            "c" * 64,
        ),
    )
    connection.execute(
        "INSERT INTO market_workflow.matches("
        "match_id, tenant_id, request_id, request_version, matcher_version, "
        "need_mtok, total_cost_micros, decision_sha256"
        ") VALUES (%s, 'tenant-a', %s, 2, 'best_execution:v1', 10, %s, %s)",
        (match_id, request_id, gross, "d" * 64),
    )
    connection.execute(
        "INSERT INTO market_workflow.match_bids("
        "tenant_id, match_id, bid_id, bid_version, slot_index"
        ") VALUES ('tenant-a', %s, %s, 1, 0)",
        (match_id, bid_id),
    )
    connection.execute(
        "UPDATE market_workflow.requests "
        "SET winning_bid_id = %s, winning_bid_version = 1, "
        "winning_match_id = %s "
        "WHERE request_id = %s",
        (bid_id, match_id, request_id),
    )
    connection.execute(
        "INSERT INTO market.balances(account, balance_micros) VALUES (%s, %s)",
        (f"escrow:{request_id}", gross + residual),
    )
    return request_id


def test_accounting_wrapper_cas_fee_drain_replay_and_failure_rollback(
    workflow_database,
):
    psycopg, dsn = workflow_database
    with psycopg.connect(dsn, autocommit=True) as connection:
        buyer, seller, capability = _seed_identity(connection)
        request_id = _seed_accepted_request(
            connection,
            buyer=buyer,
            seller=seller,
            capability=capability,
        )
        failed_id = _seed_accepted_request(
            connection,
            buyer=buyer,
            seller=seller,
            capability=capability,
            residual=1,
        )
        mismatched_amount_id = _seed_accepted_request(
            connection,
            buyer=buyer,
            seller=seller,
            capability=capability,
        )
        exact_match_id = _seed_accepted_request(
            connection,
            buyer=buyer,
            seller=seller,
            capability=capability,
            gross=10_000,
            spend_cap=20_000,
        )
        _set_actor(
            connection,
            role="tinyassets_fixture_settlement",
            actor=buyer,
            tenant="tenant-a",
        )
        body = _settlement_body(
            key="settle",
            request_id=request_id,
            buyer=buyer,
            seller=seller,
        )
        supplied_hash = hashlib.sha256(body).hexdigest()
        applied = connection.execute(
            "SELECT * FROM market_workflow.apply_accounting_settlement("
            "%s, 7, %s::bytea, %s)",
            (request_id, body, supplied_hash),
        ).fetchone()
        replayed = connection.execute(
            "SELECT * FROM market_workflow.apply_accounting_settlement("
            "%s, 7, %s::bytea, %s)",
            (request_id, body, supplied_hash),
        ).fetchone()
        assert applied[0] == "applied"
        assert replayed == ("replayed", applied[1], 8)
        connection.execute("RESET ROLE")
        assert connection.execute(
            "SELECT state, version, settlement_tx_id "
            "FROM market_workflow.requests WHERE request_id = %s",
            (request_id,),
        ).fetchone() == ("settled", 8, applied[1])
        assert connection.execute(
            "SELECT sum(delta_micros) FROM market.postings WHERE tx_id = %s",
            (applied[1],),
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT sum(delta_micros) > 0 FROM market.postings "
            "WHERE tx_id = %s AND account = 'treasury'",
            (applied[1],),
        ).fetchone() == (True,)
        assert connection.execute(
            "SELECT balance_micros FROM market.balances WHERE account = %s",
            (f"escrow:{request_id}",),
        ).fetchone() == (0,)

        _set_actor(
            connection,
            role="tinyassets_fixture_settlement",
            actor=buyer,
            tenant="tenant-a",
        )
        exact_match_body = _settlement_body(
            key="exact-match-total",
            request_id=exact_match_id,
            buyer=buyer,
            seller=seller,
            gross=10_000,
        )
        assert connection.execute(
            "SELECT status FROM market_workflow.apply_accounting_settlement("
            "%s, 7, %s::bytea, %s)",
            (
                exact_match_id,
                exact_match_body,
                hashlib.sha256(exact_match_body).hexdigest(),
            ),
        ).fetchone() == ("applied",)

        connection.execute("RESET ROLE")
        _set_actor(
            connection,
            role="tinyassets_fixture_settlement",
            actor=buyer,
            tenant="tenant-a",
        )
        failing_body = _settlement_body(
            key="residual",
            request_id=failed_id,
            buyer=buyer,
            seller=seller,
        )
        with pytest.raises(psycopg.errors.RaiseException, match="not drained"):
            connection.execute(
                "SELECT * FROM market_workflow.apply_accounting_settlement("
                "%s, 7, %s::bytea, %s)",
                (
                    failed_id,
                    failing_body,
                    hashlib.sha256(failing_body).hexdigest(),
                ),
            )
        connection.execute("RESET ROLE")
        assert connection.execute(
            "SELECT state, version, settlement_tx_id "
            "FROM market_workflow.requests WHERE request_id = %s",
            (failed_id,),
        ).fetchone() == ("accepted", 7, None)
        assert connection.execute(
            "SELECT count(*) FROM market.transactions "
            "WHERE idempotency_key = 'residual'"
        ).fetchone() == (0,)

        _set_actor(
            connection,
            role="tinyassets_fixture_settlement",
            actor=buyer,
            tenant="tenant-a",
        )
        mismatched_amount = _settlement_body(
            key="amount-mismatch",
            request_id=mismatched_amount_id,
            buyer=buyer,
            seller=seller,
            gross=9_000,
        )
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="settlement amount mismatch",
        ):
            connection.execute(
                "SELECT * FROM market_workflow.apply_accounting_settlement("
                "%s, 7, %s::bytea, %s)",
                (
                    mismatched_amount_id,
                    mismatched_amount,
                    hashlib.sha256(mismatched_amount).hexdigest(),
                ),
            )
        connection.execute("RESET ROLE")
        assert connection.execute(
            "SELECT state, settlement_tx_id FROM market_workflow.requests "
            "WHERE request_id = %s",
            (mismatched_amount_id,),
        ).fetchone() == ("accepted", None)


def test_accounting_wrapper_rechecks_signed_account_bound_grant_and_revocation(
    workflow_database,
):
    psycopg, dsn = workflow_database
    with psycopg.connect(dsn, autocommit=True) as connection:
        buyer, seller, capability = _seed_identity(connection)
        host = uuid.uuid4()
        connection.execute(
            "INSERT INTO public.users(user_id, display_name) VALUES (%s, 'host')",
            (host,),
        )
        request_id = _seed_accepted_request(
            connection,
            buyer=buyer,
            seller=seller,
            capability=capability,
        )
        grant_id = uuid.uuid4()
        signature = "d" * 64
        connection.execute(
            "INSERT INTO market_workflow.authority_grants("
            "grant_id, tenant_id, host_actor_id, target_actor_id, account, "
            "allowed_actions, max_amount_micros, issued_at, expires_at, "
            "revocation_generation, signature_sha256"
            ") VALUES (%s, 'tenant-a', %s, %s, %s, ARRAY['settle'], 10000, "
            "now() - interval '1 minute', now() + interval '5 minutes', 4, %s)",
            (
                grant_id,
                host,
                buyer,
                f"escrow:{request_id}",
                signature,
            ),
        )
        _set_actor(
            connection,
            role="tinyassets_fixture_settlement",
            actor=host,
            tenant="tenant-a",
        )
        forged = _settlement_body(
            key="grant-forged",
            request_id=request_id,
            buyer=buyer,
            seller=seller,
            subject=host,
            grant_id=grant_id,
            grant_signature="e" * 64,
            grant_generation=4,
        )
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="bounded on-behalf grant",
        ):
            connection.execute(
                "SELECT * FROM market_workflow.apply_accounting_settlement("
                "%s, 7, %s::bytea, %s)",
                (request_id, forged, hashlib.sha256(forged).hexdigest()),
            )
        connection.execute("RESET ROLE")
        assert connection.execute(
            "SELECT state, settlement_tx_id FROM market_workflow.requests "
            "WHERE request_id = %s",
            (request_id,),
        ).fetchone() == ("accepted", None)

        _set_actor(
            connection,
            role="tinyassets_fixture_settlement",
            actor=host,
            tenant="tenant-a",
        )
        valid = _settlement_body(
            key="grant-valid",
            request_id=request_id,
            buyer=buyer,
            seller=seller,
            subject=host,
            grant_id=grant_id,
            grant_signature=signature,
            grant_generation=4,
        )
        assert connection.execute(
            "SELECT status FROM market_workflow.apply_accounting_settlement("
            "%s, 7, %s::bytea, %s)",
            (request_id, valid, hashlib.sha256(valid).hexdigest()),
        ).fetchone() == ("applied",)

        connection.execute("RESET ROLE")
        revoked_id = _seed_accepted_request(
            connection,
            buyer=buyer,
            seller=seller,
            capability=capability,
        )
        connection.execute(
            "UPDATE market_workflow.authority_grants "
            "SET revoked = true, account = %s WHERE grant_id = %s",
            (f"escrow:{revoked_id}", grant_id),
        )
        _set_actor(
            connection,
            role="tinyassets_fixture_settlement",
            actor=host,
            tenant="tenant-a",
        )
        revoked = _settlement_body(
            key="grant-revoked",
            request_id=revoked_id,
            buyer=buyer,
            seller=seller,
            subject=host,
            grant_id=grant_id,
            grant_signature=signature,
            grant_generation=4,
        )
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="bounded on-behalf grant",
        ):
            connection.execute(
                "SELECT * FROM market_workflow.apply_accounting_settlement("
                "%s, 7, %s::bytea, %s)",
                (revoked_id, revoked, hashlib.sha256(revoked).hexdigest()),
            )


def test_randomized_persistent_settlements_match_pure_ledger_and_always_charge_fee(
    workflow_database,
):
    from tinyassets.paid_market.ledger import Ledger

    psycopg, dsn = workflow_database
    rng = random.Random(20260725)
    with psycopg.connect(dsn, autocommit=True) as connection:
        buyer, seller, capability = _seed_identity(connection)
        cases = []
        initial = {}
        for index in range(24):
            gross = rng.randint(100, 10_000)
            effective_seller = buyer if index % 3 == 0 else seller
            request_id = _seed_accepted_request(
                connection,
                buyer=buyer,
                seller=effective_seller,
                capability=capability,
                gross=gross,
            )
            escrow = f"escrow:{request_id}"
            initial[escrow] = gross
            cases.append((index, request_id, gross, effective_seller))
        pure = Ledger(initial)

        _set_actor(
            connection,
            role="tinyassets_fixture_settlement",
            actor=buyer,
            tenant="tenant-a",
        )
        for index, request_id, gross, effective_seller in cases:
            entries = tuple(
                spot_settlement_entries(
                    escrow_account=f"escrow:{request_id}",
                    seller_account=f"user:{effective_seller}",
                    gross_micros=gross,
                )
            )
            pure.apply(entries)
            body = _settlement_body(
                key=f"random:{index}",
                request_id=request_id,
                buyer=buyer,
                seller=effective_seller,
                gross=gross,
                supply_route="external" if index % 2 else "native",
            )
            assert connection.execute(
                "SELECT status FROM market_workflow.apply_accounting_settlement("
                "%s, 7, %s::bytea, %s)",
                (request_id, body, hashlib.sha256(body).hexdigest()),
            ).fetchone() == ("applied",)

        connection.execute("RESET ROLE")
        actual = dict(
            connection.execute(
                "SELECT account, balance_micros FROM market.balances"
            ).fetchall()
        )
        assert actual == pure.balances
        assert connection.execute(
            "SELECT count(DISTINCT tx_id) FROM market.postings "
            "WHERE account = 'treasury' AND delta_micros > 0"
        ).fetchone() == (len(cases),)


def test_zero_host_status_is_durable_pending_and_settlement_unavailable(
    workflow_database,
):
    psycopg, dsn = workflow_database
    with psycopg.connect(dsn, autocommit=True) as connection:
        buyer, _, capability = _seed_identity(connection)
        _set_actor(
            connection,
            role="tinyassets_fixture_workflow_command",
            actor=buyer,
            tenant="tenant-a",
        )
        body = _request_body(key="zero-host", requester=buyer, capability=capability)
        _call_body(connection, "submit_request", body)
        connection.execute("RESET ROLE")
        _set_actor(
            connection,
            role="tinyassets_fixture_workflow_reader",
            actor=buyer,
            tenant="tenant-a",
        )
        assert connection.execute(
            "SELECT * FROM market_workflow.workflow_status()"
        ).fetchone() == ("dark_pending", 1, False)
