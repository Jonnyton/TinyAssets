"""R2 + storage contract: a run must durably record what it was admitted with.

Design source:
``openspec/changes/consolidate-platform-resource-policy/design-amendment-resume-exact-definition.md``
(root-approved shape, 2026-09-23).

**Original red evidence (preserved).** Before this change,
``tinyassets/runs.py:_execute_branch_core`` froze the admitted
``BranchDefinition`` in process memory (``BranchDefinition.from_dict(
branch.to_dict())``) and closed the background worker over it, while handing
``branch_version_id=None`` to ``_prepare_run`` ("Def-based runs leave it as
None"). The only copy of what was admitted lived in a worker closure: a daemon
restart between run creation and worker completion lost it, and resume then
resolved the CURRENT mutable definition
(``tinyassets/api/runs.py:_branch_lookup``).

**Adapted per root review.** R2 originally demanded a non-NULL
``runs.branch_version_id`` for def runs. That is rejected: ``branch_version_id``
means "the user selected this published version" and feeds contribution
attribution, branch-delete dependency counting and market canonicality, and the
canonical snapshot cannot carry per-run execution choices at all. The durable
requirement is now a private admission **envelope**; explicit version
attribution must stay exactly as it was (asserted below).
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

import pytest

ADMITTED_NODES = ("n1", "n2")


def _become(user_id: str) -> None:
    from tinyassets.auth import middleware as _mw
    from tinyassets.auth.provider import Identity

    _mw._current_identity.set(
        Identity(
            user_id=user_id,
            username=user_id,
            display_name=user_id,
            capabilities=[
                "tinyassets.universe.read",
                "tinyassets.universe.write",
                "tinyassets.universe.admin",
                "tinyassets.extensions.read",
                "tinyassets.extensions.write",
            ],
        )
    )


def _branch(node_ids: tuple[str, ...], *, branch_def_id: str, version: int = 1):
    from tinyassets.branches import BranchDefinition, NodeDefinition

    return BranchDefinition(
        branch_def_id=branch_def_id,
        name="admission-pin-fixture",
        domain_id="d",
        version=version,
        state_schema={},
        node_defs=[
            NodeDefinition(node_id=n, display_name=n, prompt_template=f"step {n}")
            for n in node_ids
        ],
    )


def _noop_worker(*_args, **kwargs):
    from tinyassets.runs import RUN_STATUS_QUEUED, RunOutcome

    return RunOutcome(
        run_id=kwargs.get("run_id", ""), status=RUN_STATUS_QUEUED, output={}, error="",
    )


def _seed(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _become("tester")
    from tinyassets.daemon_server import (
        create_branch_definition_once,
        initialize_author_server,
    )
    from tinyassets.runs import initialize_runs_db

    initialize_author_server(tmp_path)
    admitted = _branch(ADMITTED_NODES, branch_def_id="branch-admission-pin")
    stored, _created = create_branch_definition_once(
        tmp_path, branch_def=admitted.to_dict()
    )
    initialize_runs_db(tmp_path)
    return stored


@pytest.fixture
def prepared_def_run(tmp_path, monkeypatch):
    """A def-based run created through the real ``execute_branch_async`` path."""
    stored = _seed(tmp_path, monkeypatch)
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.branches import BranchDefinition
    from tinyassets.runs import execute_branch_async

    with patch("tinyassets.runs._invoke_prepared_branch", side_effect=_noop_worker):
        outcome = execute_branch_async(
            tmp_path,
            branch=BranchDefinition.from_dict(stored),
            inputs={},
            run_name="admission-pin-run",
            actor=_current_actor(),
            recursion_limit_override=7,
            concurrency_budget_override=3,
        )
    return tmp_path, outcome.run_id, stored["branch_def_id"]


def test_def_based_run_durably_binds_its_admitted_definition(prepared_def_run):
    """The run must durably identify the definition it was admitted with."""
    base, run_id, bdid = prepared_def_run

    from tinyassets.run_admission_envelope import resolve_admitted_execution
    from tinyassets.runs import get_run

    run = get_run(base, run_id)
    assert run is not None, "the run row was not created at all"
    assert run["branch_def_id"] == bdid

    admitted = resolve_admitted_execution(base, run)
    assert admitted.source == "envelope", (
        "def-based run recorded no admitted-definition envelope. The admitted "
        "graph would exist only in the worker closure "
        "(tinyassets/runs.py _execute_branch_core), so a resume after a daemon "
        "restart has nothing durable to resolve and falls back to the CURRENT "
        "mutable definition (tinyassets/api/runs.py _branch_lookup)."
    )
    assert tuple(n.node_id for n in admitted.branch.node_defs) == ADMITTED_NODES


def test_envelope_preserves_name_domain_and_caller_metadata(prepared_def_run):
    """Name/domain and the caller's run name survive — the snapshot drops them."""
    base, run_id, _bdid = prepared_def_run
    from tinyassets.run_admission_envelope import resolve_admitted_execution
    from tinyassets.runs import get_run

    admitted = resolve_admitted_execution(base, get_run(base, run_id))
    assert admitted.branch.name == "admission-pin-fixture"
    assert admitted.branch.domain_id == "d"
    assert admitted.run_name == "admission-pin-run"


def test_caller_execution_overrides_roundtrip(prepared_def_run):
    """Effective recursion/concurrency choices are the admitted ones, not defaults."""
    base, run_id, _bdid = prepared_def_run
    from tinyassets.run_admission_envelope import resolve_admitted_execution
    from tinyassets.runs import DEFAULT_RECURSION_LIMIT, get_run

    admitted = resolve_admitted_execution(base, get_run(base, run_id))
    assert admitted.recursion_limit == 7 != DEFAULT_RECURSION_LIMIT
    assert admitted.concurrency_budget_override == 3
    assert admitted.effective_concurrency_budget == 3


def test_def_run_attribution_columns_unchanged(prepared_def_run):
    """``branch_version_id`` still means "user selected a published version"."""
    base, run_id, bdid = prepared_def_run
    from tinyassets.runs import get_run

    run = get_run(base, run_id)
    assert run["branch_version_id"] is None, (
        "a platform-minted pin in branch_version_id would reclassify every def "
        "run's contribution attribution (artifact_kind) and count toward the "
        "branch-delete dependency gate"
    )
    # The contribution-event classifier reads the column directly; prove the
    # derivation it performs still lands on branch_def for a def run.
    artifact_kind = "branch_version" if run["branch_version_id"] else "branch_def"
    assert artifact_kind == "branch_def"
    assert (run["branch_version_id"] or run["branch_def_id"]) == bdid


def test_branch_versions_store_untouched_by_def_admission(prepared_def_run):
    """No snapshot is published, so branch deletion/dependency gates are unaffected."""
    base, _run_id, bdid = prepared_def_run
    from tinyassets.branch_versions import list_branch_versions

    assert list_branch_versions(base, bdid) == []


def test_envelope_is_not_in_the_run_projection(prepared_def_run):
    """The envelope is private: no public run read exposes it."""
    base, run_id, _bdid = prepared_def_run
    from tinyassets.runs import get_run, list_runs

    run = get_run(base, run_id)
    assert "admission_envelope_json" not in run
    assert not any("envelope" in k for k in run)
    blob = json.dumps(run, default=str)
    assert "envelope_schema" not in blob
    for listed in list_runs(base):
        assert "admission_envelope_json" not in listed


def test_duplicate_preparation_cannot_replace_the_original_envelope(prepared_def_run):
    """A second preparation may re-supply the same envelope, never a different one."""
    base, run_id, _bdid = prepared_def_run
    from tinyassets.branches import BranchDefinition
    from tinyassets.run_admission_envelope import (
        AdmissionEnvelopeConflict,
        encode_admission_envelope,
        read_raw_envelope,
    )
    from tinyassets.runs import _initialize_prepared_run, get_run

    original = read_raw_envelope(base, run_id)
    assert original

    run = get_run(base, run_id)
    hostile = _branch(("n1", "n2", "n3_injected"), branch_def_id=run["branch_def_id"])
    replacement = encode_admission_envelope(
        BranchDefinition.from_dict(hostile.to_dict()),
        recursion_limit=1,
        concurrency_budget_override=None,
        run_name="replaced",
        branch_version_id=None,
    )
    with pytest.raises(AdmissionEnvelopeConflict):
        _initialize_prepared_run(
            base, run_id=run_id, branch=hostile, actor=run["actor"],
            admission_envelope=replacement,
        )
    assert read_raw_envelope(base, run_id) == original

    # Re-supplying the identical envelope is idempotent, not a conflict.
    _initialize_prepared_run(
        base, run_id=run_id, branch=hostile, actor=run["actor"],
        admission_envelope=original,
    )
    assert read_raw_envelope(base, run_id) == original


def test_envelope_capture_failure_prevents_dispatch(tmp_path, monkeypatch):
    """A run whose envelope will not persist must fail, not run unresumably."""
    stored = _seed(tmp_path, monkeypatch)
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.branches import BranchDefinition
    from tinyassets.run_admission_envelope import AdmissionEnvelopeError
    from tinyassets.runs import RUN_STATUS_FAILED, execute_branch_async, get_run

    def _boom(_conn, *, run_id, envelope):
        raise AdmissionEnvelopeError("simulated storage failure", run_id=run_id)

    dispatched: list[str] = []

    with (
        patch(
            "tinyassets.run_admission_envelope.capture_admission_envelope",
            side_effect=_boom,
        ),
        patch(
            "tinyassets.runs._invoke_prepared_branch",
            side_effect=lambda *a, **k: dispatched.append(k.get("run_id")),
        ),
    ):
        outcome = execute_branch_async(
            tmp_path,
            branch=BranchDefinition.from_dict(stored),
            inputs={},
            run_name="envelope-failure",
            actor=_current_actor(),
        )

    assert outcome.status == RUN_STATUS_FAILED
    assert "Admission envelope capture failed" in outcome.error
    assert dispatched == [], "the graph was dispatched without a durable envelope"
    assert get_run(tmp_path, outcome.run_id)["status"] == RUN_STATUS_FAILED


def test_real_sqlite_write_failure_leaves_no_forever_queued_run(tmp_path, monkeypatch):
    """C.5: a genuine storage fault, not a synthetic AdmissionEnvelopeError.

    The previous round only proved the handler when the helper *itself* raised
    the typed error -- which assumes the thing under test. Here a real SQLite
    write fails at the capture seam (an AFTER trigger that raises), so the
    wrapping in ``capture_admission_envelope`` is exercised rather than
    stipulated. The reserved run must end terminal-FAILED, never be submitted,
    and keep its attribution.
    """
    stored = _seed(tmp_path, monkeypatch)
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.branches import BranchDefinition
    from tinyassets.runs import (
        RUN_STATUS_FAILED,
        _connect,
        execute_branch_async,
        get_run,
    )

    actor = _current_actor()
    # A real constraint at the real write. Any UPDATE that sets the envelope
    # column now fails inside SQLite itself.
    with _connect(tmp_path) as conn:
        conn.execute(
            "CREATE TRIGGER envelope_write_fails "
            "AFTER UPDATE OF admission_envelope_json ON runs "
            "BEGIN SELECT RAISE(ABORT, 'disk I/O error'); END"
        )

    dispatched: list[str] = []
    with patch(
        "tinyassets.runs._invoke_prepared_branch",
        side_effect=lambda *a, **k: dispatched.append(k.get("run_id")),
    ):
        outcome = execute_branch_async(
            tmp_path,
            branch=BranchDefinition.from_dict(stored),
            inputs={},
            run_name="real-storage-fault",
            actor=actor,
        )

    assert outcome.status == RUN_STATUS_FAILED, outcome.error
    assert "Admission envelope capture failed" in outcome.error
    assert dispatched == [], "a run with no durable envelope was submitted"

    with _connect(tmp_path) as conn:
        conn.execute("DROP TRIGGER envelope_write_fails")

    row = get_run(tmp_path, outcome.run_id)
    assert row["status"] == RUN_STATUS_FAILED, "reserved run left non-terminal"
    assert row["finished_at"], "a terminal run must carry finished_at"
    # Attribution survives the failure path; nothing is reassigned or dropped.
    assert row["actor"] == actor
    assert row.get("run_name") == "real-storage-fault"
    # And the envelope column really is still empty -- the run is honestly
    # non-resumable rather than carrying a half-written payload.
    with _connect(tmp_path) as conn:
        raw = conn.execute(
            "SELECT admission_envelope_json AS env FROM runs WHERE run_id = ?",
            (outcome.run_id,),
        ).fetchone()["env"]
    assert not raw


def test_encoding_failure_before_reservation_reserves_no_run(tmp_path, monkeypatch):
    """C.5's other half: an encode fault propagates with no run row at all.

    Encoding happens BEFORE the run is reserved, so there is nothing to
    terminalize; inventing a run id to settle would be the fiction. The
    contract is that no queued row is left behind.
    """
    stored = _seed(tmp_path, monkeypatch)
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.branches import BranchDefinition
    from tinyassets.run_admission_envelope import AdmissionEnvelopeError
    from tinyassets.runs import _connect, execute_branch_async

    with _connect(tmp_path) as conn:
        before = conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]

    with (
        patch(
            "tinyassets.run_admission_envelope.encode_admission_envelope",
            side_effect=AdmissionEnvelopeError("unserializable definition"),
        ),
        pytest.raises(AdmissionEnvelopeError),
    ):
        execute_branch_async(
            tmp_path,
            branch=BranchDefinition.from_dict(stored),
            inputs={},
            run_name="encode-failure",
            actor=_current_actor(),
        )

    with _connect(tmp_path) as conn:
        after = conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"]
    assert after == before, "an encode failure must not reserve a run"


def test_migration_is_additive_and_idempotent(tmp_path, monkeypatch):
    """The column is added to a pre-existing table; old rows stay unknown."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _become("tester")
    from tinyassets.run_admission_envelope import ENVELOPE_COLUMN
    from tinyassets.runs import _connect, create_run, initialize_runs_db, runs_db_path

    initialize_runs_db(tmp_path)

    # Simulate a pre-migration install by dropping the column back off.
    with _connect(tmp_path) as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(runs)")}
        assert ENVELOPE_COLUMN in cols
        conn.execute(f"ALTER TABLE runs DROP COLUMN {ENVELOPE_COLUMN}")
        conn.commit()

    legacy_run = create_run(
        tmp_path, branch_def_id="legacy-branch", thread_id="", inputs={},
        actor="tester", run_name="legacy",
    )

    # Re-running the migration is idempotent and leaves the old row unknown.
    for _ in range(2):
        with sqlite3.connect(runs_db_path(tmp_path)) as raw:
            raw.row_factory = sqlite3.Row
            from tinyassets.runs import _migrate_runs_table_columns

            _migrate_runs_table_columns(raw)
    with _connect(tmp_path) as conn:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(runs)")]
        assert cols.count(ENVELOPE_COLUMN) == 1
        row = conn.execute(
            f"SELECT {ENVELOPE_COLUMN} AS env FROM runs WHERE run_id = ?",
            (legacy_run,),
        ).fetchone()
    assert row["env"] is None, "an existing row must be left unknown, never guessed"
