"""Round-3 correctness holes in the admission-envelope path.

Each test here names a hole that the round-2 implementation left open and that
the earlier 30- and 42-test passes did not cover:

1. An invented ``_SANITY_CEILING`` normalized real branch policy -- ``0`` (a
   tracked-but-unbounded run, ``graph_compiler.ConcurrencyTracker``) and any
   large budget silently became ``None`` (no tracker at all).
2. ``True == 1`` in Python, so a boolean ``envelope_schema`` passed the version
   check; and an effective budget that disagreed with the envelope's own frozen
   definition was accepted whenever no override was recorded.
3. ``_initialize_prepared_run``'s ``BEGIN IMMEDIATE`` / thread UPDATE / commit
   raised bare ``sqlite3.Error``, escaping every admission seam's
   ``except AdmissionEnvelopeError`` and leaving a reserved QUEUED row nothing
   would dispatch. Exercised with a REAL transaction failure (a read-only
   database), not an encoding mock.
4. ``delivery_runtime._work`` and
   ``run_input_runtime._work_under_maintenance_barrier`` really execute
   reserved runs but captured no envelope, so those runs executed and then
   refused to resume.
"""

from __future__ import annotations

import json
import sqlite3

import pytest


def _branch(**kwargs):
    from tinyassets.branches import BranchDefinition, NodeDefinition

    return BranchDefinition(
        branch_def_id=kwargs.pop("branch_def_id", "b-corrections"),
        name="corrections-fixture",
        domain_id="d",
        version=1,
        state_schema={},
        node_defs=[NodeDefinition(node_id="n1", display_name="n1", prompt_template="p")],
        **kwargs,
    )


def _encode(branch, **kwargs):
    from tinyassets.run_admission_envelope import encode_admission_envelope

    options = {
        "recursion_limit": 7,
        "concurrency_budget_override": None,
        "run_name": "r",
        "branch_version_id": None,
    }
    options.update(kwargs)
    return encode_admission_envelope(branch, **options)


def _decode(raw, branch_def_id="b-corrections", **run_overrides):
    from tinyassets.branches import BranchDefinition
    from tinyassets.run_admission_envelope import _decode as decode

    run = {"run_id": "run-1", "branch_def_id": branch_def_id, "branch_version_id": None}
    run.update(run_overrides)
    return decode(
        raw, run=run, run_id="run-1", branch_from_dict=BranchDefinition.from_dict,
    )


# ── 1. No invented caps; branch policy is preserved verbatim ────────────────


@pytest.mark.parametrize("budget", [0, 1, 4096, 5_000_000])
def test_branch_concurrency_budget_survives_verbatim(budget):
    """``0`` and large budgets are real execution choices, not garbage.

    ``graph_compiler.compile_branch`` builds a ``ConcurrencyTracker`` iff the
    effective budget ``is not None``, and ``ConcurrencyTracker`` treats ``0``
    as tracked-but-unbounded (``Semaphore(budget) if budget else None``).
    Normalizing either end to ``None`` resumes the run under a different
    execution contract than the one admitted.
    """
    admitted = _decode(_encode(_branch(concurrency_budget=budget)))
    assert admitted.effective_concurrency_budget == budget
    assert admitted.branch.concurrency_budget == budget


def test_unset_branch_budget_stays_none():
    admitted = _decode(_encode(_branch()))
    assert admitted.effective_concurrency_budget is None
    assert admitted.concurrency_budget_override is None


@pytest.mark.parametrize("budget", [-1, True, "4", 2.5])
def test_malformed_branch_budget_refuses_instead_of_becoming_none(budget):
    """A budget the compiler cannot build from must fail loudly at admission.

    Degrading it to ``None`` would hand the resumed run UNBOUNDED concurrency
    while claiming that is what was admitted.
    """
    from tinyassets.run_admission_envelope import AdmissionEnvelopeError

    with pytest.raises(AdmissionEnvelopeError) as exc:
        _encode(_branch(concurrency_budget=budget))
    assert "concurrency_budget" in str(exc.value)


def test_large_recursion_limit_is_admissible():
    """No ceiling exists in the execution contract, so none is invented here."""
    assert _decode(_encode(_branch(), recursion_limit=2_000_000)).recursion_limit == 2_000_000


# ── 2. Decoder strictness ───────────────────────────────────────────────────


def test_boolean_schema_version_is_refused():
    """``True == 1``: a bare ``!=`` check let a boolean schema through."""
    from tinyassets.run_admission_envelope import AdmissionNotReconstructable

    payload = json.loads(_encode(_branch()))
    payload["envelope_schema"] = True
    with pytest.raises(AdmissionNotReconstructable):
        _decode(json.dumps(payload))


def test_effective_budget_must_match_the_frozen_definition():
    """With no override, effective IS the frozen branch's own budget."""
    from tinyassets.run_admission_envelope import AdmissionNotReconstructable

    payload = json.loads(_encode(_branch(concurrency_budget=3)))
    payload["execution"]["effective_concurrency_budget"] = 9
    with pytest.raises(AdmissionNotReconstructable) as exc:
        _decode(json.dumps(payload))
    assert "frozen definition" in str(exc.value)


def test_effective_budget_forged_to_none_is_refused():
    """The no-tracker case must not be reachable by blanking one field."""
    from tinyassets.run_admission_envelope import AdmissionNotReconstructable

    payload = json.loads(_encode(_branch(concurrency_budget=2)))
    payload["execution"]["effective_concurrency_budget"] = None
    with pytest.raises(AdmissionNotReconstructable):
        _decode(json.dumps(payload))


def test_override_still_wins_over_the_frozen_branch_budget():
    """An explicit override is the effective budget; the frozen value is inert."""
    admitted = _decode(
        _encode(_branch(concurrency_budget=3), concurrency_budget_override=8)
    )
    assert admitted.concurrency_budget_override == 8
    assert admitted.effective_concurrency_budget == 8


# ── 3. Real transaction failure settles the reserved run ────────────────────


@pytest.fixture
def reserved_run(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    from tinyassets.runs import RUN_STATUS_QUEUED, create_run, initialize_runs_db

    initialize_runs_db(tmp_path)
    run_id = create_run(
        tmp_path, branch_def_id="b-corrections", thread_id="", inputs={},
        run_name="reserved", actor="universe:u1",
    )
    assert _status(tmp_path, run_id) == RUN_STATUS_QUEUED
    return tmp_path, run_id


def _status(base, run_id):
    from tinyassets.runs import _connect

    with _connect(base) as conn:
        return conn.execute(
            "SELECT status FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()[0]


def _readonly_connect(monkeypatch, base):
    """Point the claim transaction at a genuinely read-only handle.

    A real ``sqlite3.OperationalError`` ("attempt to write a readonly
    database") then comes out of SQLite itself -- this is storage-fault
    evidence, not a stubbed exception standing in for one.
    """
    import contextlib

    from tinyassets import runs

    db = runs.runs_db_path(base)

    @contextlib.contextmanager
    def ro_connect(_base_path):
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    monkeypatch.setattr(runs, "_connect", ro_connect)


def test_readonly_storage_fault_is_wrapped_so_the_run_can_settle(
    reserved_run, monkeypatch
):
    """A storage fault in the claim transaction must not escape the wrapper.

    An escaping bare ``sqlite3.Error`` bypasses every admission seam's
    ``except AdmissionEnvelopeError`` and leaves a reserved QUEUED row whose
    graph nobody will ever run.
    """
    from tinyassets import runs
    from tinyassets.run_admission_envelope import AdmissionEnvelopeError

    base, run_id = reserved_run
    _readonly_connect(monkeypatch, base)
    with pytest.raises(AdmissionEnvelopeError) as exc:
        runs._initialize_prepared_run(
            base, run_id=run_id, branch=_branch(), actor="universe:u1",
            admission_envelope=_encode(_branch()),
        )
    assert exc.value.run_id == run_id, (
        "the failure must name the reserved run so the caller can settle it"
    )
    assert "readonly" in str(exc.value).lower()


def test_readonly_storage_fault_is_wrapped_without_an_envelope(
    reserved_run, monkeypatch
):
    """The thread_id claim fails the same way on the envelope-free seams."""
    from tinyassets import runs
    from tinyassets.run_admission_envelope import AdmissionEnvelopeError

    base, run_id = reserved_run
    _readonly_connect(monkeypatch, base)
    with pytest.raises(AdmissionEnvelopeError) as exc:
        runs._initialize_prepared_run(
            base, run_id=run_id, branch=_branch(), actor="universe:u1",
        )
    assert exc.value.run_id == run_id


def test_commit_stage_fault_is_wrapped(reserved_run, monkeypatch):
    """``commit()`` raises outside ``execute()``; it was unwrapped too.

    Driven through a real ``sqlite3.Connection`` subclass so the transaction
    really runs and really fails at the commit boundary.
    """
    import contextlib

    from tinyassets import runs
    from tinyassets.run_admission_envelope import AdmissionEnvelopeError

    class CommitFails(sqlite3.Connection):
        def commit(self):
            raise sqlite3.OperationalError("disk I/O error")

    db = runs.runs_db_path(base := reserved_run[0])
    run_id = reserved_run[1]

    @contextlib.contextmanager
    def failing_commit(_base_path):
        conn = sqlite3.connect(db, timeout=5.0, factory=CommitFails)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    monkeypatch.setattr(runs, "_connect", failing_commit)
    with pytest.raises(AdmissionEnvelopeError) as exc:
        runs._initialize_prepared_run(
            base, run_id=run_id, branch=_branch(), actor="universe:u1",
            admission_envelope=_encode(_branch()),
        )
    assert exc.value.run_id == run_id


def test_settlement_never_overwrites_a_terminal_run(reserved_run):
    """A run cancelled between reservation and capture keeps its status."""
    from tinyassets import runs
    from tinyassets.run_admission_envelope import AdmissionEnvelopeError

    base, run_id = reserved_run
    runs.update_run_status(
        base, run_id, status=runs.RUN_STATUS_CANCELLED, finished_at=runs._now(),
    )
    outcome = runs._settle_failed_admission_envelope(
        base, AdmissionEnvelopeError("capture failed", run_id=run_id),
    )
    assert outcome is not None
    assert _status(base, run_id) == runs.RUN_STATUS_CANCELLED, (
        "a failed envelope capture is not evidence about a row already settled"
    )
    assert outcome.status == runs.RUN_STATUS_CANCELLED


def test_encoding_failure_has_no_run_to_settle():
    """Encoding raises before reservation, so there is nothing to terminalize."""
    from tinyassets import runs
    from tinyassets.run_admission_envelope import AdmissionEnvelopeError

    assert runs._settle_failed_admission_envelope(
        "unused", AdmissionEnvelopeError("bad encode"),
    ) is None


# ── 4. The executing seams admit what they dispatch ─────────────────────────


def test_executing_seams_capture_an_envelope_before_dispatch():
    """Both seams that call ``_invoke_prepared_branch`` must admit first.

    Source-level assertion: these paths execute a reserved run, so a resume of
    that run has to have durable evidence. They are not non-executing intents.
    """
    import inspect

    from tinyassets import delivery_runtime, run_input_runtime

    for module, func in (
        (delivery_runtime, delivery_runtime._work),
        (run_input_runtime, run_input_runtime._work_under_maintenance_barrier),
    ):
        source = inspect.getsource(func)
        assert "_invoke_prepared_branch" in source, "fixture drift: no dispatch here"
        assert "encode_admission_envelope" in source, (
            f"{module.__name__} dispatches a reserved run with no admission "
            "envelope; that run executes and then refuses to resume."
        )
        assert "admission_envelope" in source
        assert "_reserved_run_admission_identity" in source, (
            "the envelope must carry the reserved run row's own run_name and "
            "branch_version_id, or the decoder's binding check refuses it"
        )


def test_reserved_run_admission_identity_reads_the_row(reserved_run):
    from tinyassets import runs

    base, run_id = reserved_run
    assert runs._reserved_run_admission_identity(base, run_id) == ("reserved", None)


def test_seam_envelope_round_trips_through_the_decoder(reserved_run):
    """What the seams encode must be what the resume path can decode."""
    from tinyassets import runs
    from tinyassets.run_admission_envelope import resolve_admitted_execution

    base, run_id = reserved_run
    run_name, version_id = runs._reserved_run_admission_identity(base, run_id)
    runs._initialize_prepared_run(
        base, run_id=run_id, branch=_branch(concurrency_budget=0),
        actor="universe:u1",
        admission_envelope=_encode(
            _branch(concurrency_budget=0),
            recursion_limit=runs.DEFAULT_RECURSION_LIMIT,
            run_name=run_name,
            branch_version_id=version_id,
        ),
    )
    admitted = resolve_admitted_execution(base, runs.get_run(base, run_id))
    assert admitted.source == "envelope"
    assert admitted.run_name == "reserved"
    assert admitted.recursion_limit == runs.DEFAULT_RECURSION_LIMIT
    assert admitted.effective_concurrency_budget == 0
