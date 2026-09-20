"""Static initial/recovery dispatch converges on one guarded origin adapter."""

import contextvars

import pytest

from tests.test_run_input_runtime import admitted  # noqa: F401
from tinyassets import daemon_server, run_input_runtime, runs
from tinyassets import run_input_origins as origins
from tinyassets.auth.middleware import current_identity_or_none
from tinyassets.run_input_direct import _root_only, prepare_admitted_direct
from tinyassets.run_input_origin import OriginHeld
from tinyassets.storage import _connect as author_connect
from tinyassets.storage import run_input_admissions as admissions


@pytest.fixture
def direct(admitted):  # noqa: F811
    base, run_id = admitted
    daemon_server.initialize_author_server(base)
    with author_connect(base) as conn:
        conn.execute("INSERT INTO founder_home(founder_sub,universe_id,created_at) "
                     "VALUES('owner','u',1)")
        conn.execute("INSERT INTO universe_acl(universe_id,actor_id,permission,granted_at,"
                     "granted_by) VALUES('u','owner','admin',1,'owner')")
    with runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        old = admissions.load_in_transaction(conn, run_id=run_id, owner_id="owner", universe_id="u")
        snapshot = old["snapshot"]
        snapshot["author"] = "owner"
        conn.execute("DELETE FROM run_input_admissions WHERE run_id=?", (run_id,))
        admissions.accept_in_transaction(
            conn, run_id=run_id, owner_id="owner", universe_id="u", snapshot=snapshot,
            origin_kind="direct", origin_version=1,
            origin_options={"recursion_limit": 7, "concurrency_budget_override": 3},
        )
    daemon_server.save_branch_definition(base, branch_def=snapshot)
    return base, run_id


def test_direct_preparer_uses_explicit_identity_and_original_options(direct, monkeypatch):
    base, run_id = direct
    monkeypatch.setattr(runs, "DEFAULT_RECURSION_LIMIT", 999)
    def prepare():
        assert current_identity_or_none() is None
        with author_connect(base) as author, runs._connect(base) as conn:
            author.execute("BEGIN IMMEDIATE")
            conn.execute("BEGIN IMMEDIATE")
            envelope = admissions.load_in_transaction(conn, run_id=run_id,
                                                      owner_id="owner", universe_id="u")
            return prepare_admitted_direct(base, envelope, author_conn=author, runs_conn=conn)
    prepared = contextvars.Context().run(prepare)
    assert prepared.identity.user_id == "owner" and prepared.actor == "universe:u"
    assert prepared.recursion_limit == 7 and prepared.concurrency_budget_override == 3


@pytest.mark.parametrize("root,epoch,closing,allowed", [
    (None, None, None, True), ("run", 1, "", True), ("parent", 1, "", False),
    (None, 1, "", False), ("run", 0, "", False), ("run", True, "", False),
    ("run", 1, "cancelled", False),
])
def test_root_family_is_not_child_pool_provenance(root, epoch, closing, allowed):
    row = {"run_id": "run", "workspace_budget_root_run_id": root,
           "workspace_budget_epoch": epoch, "workspace_budget_closing_reason": closing}
    if allowed:
        _root_only(row)
    else:
        with pytest.raises((OriginHeld, PermissionError)):
            _root_only(row)


def test_recovery_scan_nominates_no_file_run_without_effect_replay(direct, monkeypatch):
    base, run_id = direct
    nominated = []
    monkeypatch.setattr(origins, "dispatch_initial_run",
                        lambda base, *, run_id: nominated.append(run_id))
    assert origins.reconcile_admitted_runs(base) == ""
    assert nominated == [run_id]
    with runs._connect(base) as conn:
        conn.execute("UPDATE run_input_admissions SET execution_started_at=1,claim_token='started'")
    origins.reconcile_admitted_runs(base)
    assert nominated == [run_id]


def test_unknown_origin_refuses_before_executor(admitted, monkeypatch):  # noqa: F811
    base, run_id = admitted
    monkeypatch.setattr(runs, "_get_executor", lambda **kwargs: pytest.fail("must stay held"))
    with pytest.raises(OriginHeld, match="unknown"):
        origins.dispatch_initial_run(base, run_id=run_id)
    assert runs.get_run(base, run_id)["status"] == "queued"


def test_under_guard_origin_conflict_stays_held_without_marker(direct):
    base, run_id = direct
    with runs._connect(base) as conn:
        conn.execute("CREATE TABLE conversation_run_admissions(run_id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO conversation_run_admissions VALUES(?)", (run_id,))
    origins.dispatch_initial_run(base, run_id=run_id)
    runs.wait_for(run_id, timeout=15)
    row = runs.get_run(base, run_id)
    assert row["status"] == "queued"
    with runs._connect(base) as conn:
        marker = conn.execute("SELECT execution_started_at FROM run_input_admissions").fetchone()[0]
        assert marker is None


@pytest.mark.parametrize("marker,token", [(1, None), (None, "orphan")])
def test_corrupt_prior_start_evidence_is_not_terminalized(direct, marker, token):
    base, run_id = direct
    with runs._connect(base) as conn:
        conn.execute("UPDATE run_input_admissions SET execution_started_at=?,claim_token=?",
                     (marker, token))
    origins.dispatch_initial_run(base, run_id=run_id)
    runs.wait_for(run_id, timeout=15)
    assert runs.get_run(base, run_id)["status"] == "queued"
    with runs._connect(base) as conn:
        assert tuple(conn.execute("SELECT execution_started_at,claim_token "
                                  "FROM run_input_admissions").fetchone()) == (marker, token)


def test_initial_and_recovery_use_same_static_adapter(direct, monkeypatch):
    base, run_id = direct
    calls = []
    monkeypatch.setattr(run_input_runtime, "dispatch_admitted_run",
                        lambda base, **kwargs: calls.append(kwargs))
    origins.dispatch_initial_run(base, run_id=run_id)
    origins.reconcile_admitted_runs(base)
    assert len(calls) == 2
    assert calls[0]["prepare"] is calls[1]["prepare"] is origins._prepare
    assert calls[0]["on_settled"] is calls[1]["on_settled"] is origins._settled


def test_actual_direct_initial_dispatch_then_recovery_does_not_repeat(direct):
    base, run_id = direct
    origins.dispatch_initial_run(base, run_id=run_id)
    runs.wait_for(run_id, timeout=15)
    row = runs.get_run(base, run_id)
    assert row["status"] == "completed", row["error"]
    with runs._connect(base) as conn:
        marker = tuple(conn.execute("SELECT execution_started_at,claim_token "
                                    "FROM run_input_admissions").fetchone())
    assert marker[0] is not None and marker[1]
    origins.reconcile_admitted_runs(base)
    with runs._connect(base) as conn:
        assert tuple(conn.execute("SELECT execution_started_at,claim_token "
                                  "FROM run_input_admissions").fetchone()) == marker


def test_consumer_missing_correlation_refuses_symmetrically(direct):
    base, run_id = direct
    with runs._connect(base) as conn:
        envelope = {"run_id": run_id, "origin_kind": "canonical_consumer"}
        with pytest.raises(OriginHeld, match="correlation_missing"):
            origins._correlation(conn, envelope)
