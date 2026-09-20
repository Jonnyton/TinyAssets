"""Consumer-only registry assembly never needs the optional file/direct backend."""

import builtins
import contextvars
import uuid

import pytest

from tests.test_consumer_run_envelope import reserve, setup
from tests.test_consumer_selection import store as store
from tinyassets import run_input_origins as origins
from tinyassets import run_input_runtime, runs
from tinyassets.run_input_origin import OriginHeld


def record(base):
    return reserve(base, str(uuid.uuid4()), setup(base))


def test_consumer_intake_stamps_exact_origin_and_all_dispatches_share_adapter(store, monkeypatch):
    from tinyassets.consumer_runtime import _dispatch

    row = record(store)
    with runs._connect(store) as conn:
        stored = conn.execute("SELECT origin_kind,origin_version,origin_options_json "
                              "FROM run_input_admissions").fetchone()
        assert tuple(stored) == ("canonical_consumer", 1, "{}")
    calls = []
    monkeypatch.setattr(run_input_runtime, "dispatch_admitted_run",
                        lambda base, **kwargs: calls.append(kwargs))
    for _ in range(2):
        _dispatch(store, row, owner=row["owner_user_id"], universe=row["universe_id"])
    contextvars.Context().run(origins.reconcile_admitted_runs, store)
    assert len(calls) == 3
    assert all(call["run_id"] == row["run_id"] and call["prepare"] is origins._prepare
               and call["on_settled"] is origins._settled for call in calls)


@pytest.mark.parametrize("marker,token", [(1, None), (None, "orphan"), (1, "started")])
def test_ambiguous_or_started_admission_is_not_nominated_or_replayed(
    store, monkeypatch, marker, token,
):
    row = record(store)
    with runs._connect(store) as conn:
        conn.execute("UPDATE run_input_admissions SET execution_started_at=?,claim_token=?",
                     (marker, token))
    monkeypatch.setattr(run_input_runtime, "dispatch_admitted_run",
                        lambda *a, **k: pytest.fail("must not nominate started work"))
    origins.reconcile_admitted_runs(store)
    assert runs.get_run(store, row["run_id"])["status"] == "queued"


@pytest.mark.parametrize("kind,version,options", [("", 0, "{}"), ("future", 1, "{}"),
                                                  ("canonical_consumer", 1, '{"extra":1}')])
def test_legacy_unknown_and_invalid_origin_hold_before_executor(
    store, monkeypatch, kind, version, options,
):
    row = record(store)
    with runs._connect(store) as conn:
        conn.execute("UPDATE run_input_admissions SET origin_kind=?,origin_version=?,"
                     "origin_options_json=?",
                     (kind, version, options))
    monkeypatch.setattr(runs, "_get_executor", lambda **k: pytest.fail("must stay held"))
    with pytest.raises(OriginHeld):
        origins.dispatch_initial_run(store, run_id=row["run_id"])
    assert runs.get_run(store, row["run_id"])["status"] == "queued"


@pytest.mark.parametrize("module", ["tinyassets.consumer_runtime", "tinyassets.run_input_direct"])
def test_missing_installed_adapter_is_typed_hold_before_submission(store, monkeypatch, module):
    row = record(store)
    if module.endswith("run_input_direct"):
        with runs._connect(store) as conn:
            conn.execute("UPDATE run_input_admissions SET origin_kind='direct',"
                         "origin_options_json=?",
                         ('{"concurrency_budget_override":null,"recursion_limit":100}',))
    original = builtins.__import__

    def absent(name, *args, **kwargs):
        if name == module:
            raise ModuleNotFoundError(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", absent)
    monkeypatch.setattr(runs, "_get_executor", lambda **k: pytest.fail("must stay held"))
    with pytest.raises(OriginHeld, match="unavailable"):
        origins.dispatch_initial_run(store, run_id=row["run_id"])


def test_missing_canonical_correlation_holds_under_guard_before_marker(store):
    row = record(store)
    with runs._connect(store) as conn:
        conn.execute("DELETE FROM conversation_run_admissions")
    origins.dispatch_initial_run(store, run_id=row["run_id"])
    runs.wait_for(row["run_id"], timeout=10)
    with runs._connect(store) as conn:
        assert tuple(conn.execute("SELECT execution_started_at,claim_token "
                                  "FROM run_input_admissions").fetchone()) == (None, None)
    assert runs.get_run(store, row["run_id"])["status"] == "queued"


@pytest.mark.parametrize("mutation,phase", [
    ("claim_token='started'", "recovery_required"),
    ("execution_started_at=1", "recovery_required"),
    ("origin_kind='unknown'", "origin_unavailable"),
])
def test_owner_status_projects_shared_uncertainty_without_replay(
    store, monkeypatch, mutation, phase,
):
    from tests.test_consumer_selection import HOME, OWNER
    from tinyassets.consumer_runtime import read_turn

    key = str(uuid.uuid4())
    row = reserve(store, key, setup(store))
    with runs._connect(store) as conn:
        conn.execute("UPDATE run_input_admissions SET " + mutation)
    monkeypatch.setattr(origins, "dispatch_initial_run",
                        lambda *a, **k: pytest.fail("observation cannot dispatch"))
    observed = read_turn(store, owner=OWNER, universe=HOME, request_key=key)
    assert observed["consumer_turn"]["state"] == "held"
    assert observed["consumer_turn"]["phase"] == phase
    assert observed["consumer_turn"]["automatic_replay"] is False
    assert runs.get_run(store, row["run_id"])["status"] == "queued"
    assert read_turn(store, owner="other", universe=HOME, request_key=key) == {"error": "not_found"}
