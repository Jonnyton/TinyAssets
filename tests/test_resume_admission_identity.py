"""R1: resume must never run a definition other than the admitted one.

Design source:
``openspec/changes/consolidate-platform-resource-policy/design-amendment-resume-exact-definition.md``
(root-approved shape, 2026-09-23).

**Preserved red evidence.** On the pre-change tree ``resume_run`` took its graph
from the injected ``branch_lookup``, whose only implementation
(``tinyassets/api/runs.py:_action_resume_run._branch_lookup``) calls
``get_branch_definition`` — the CURRENT editable definition. An author edit
between interruption and resume therefore *substituted* a different graph under
an existing checkpoint: admitted ``(n1, n2)``, resumed ``(n1, n2, n3_injected)``.
That is substitution, not suspicion.

The fix is a success, not a refusal: a run admitted after this change resumes on
its own admitted snapshot even though the draft was edited. Only a run with no
honest durable record refuses, and it refuses with a typed reason.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future
from unittest.mock import patch

import pytest

ADMITTED_NODES = ("n1", "n2")
EDITED_NODES = ("n1", "n2", "n3_injected")

#: A refusal for any other reason makes these tests vacuous — a resume blocked
#: by provider authority or a missing checkpoint proves nothing about identity.
IDENTITY_REFUSAL_REASONS = {"admission_not_reconstructable"}


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


def _branch(node_ids, *, branch_def_id: str, name: str = "resume-identity-fixture"):
    from tinyassets.branches import BranchDefinition, NodeDefinition

    return BranchDefinition(
        branch_def_id=branch_def_id,
        name=name,
        domain_id="d",
        version=1,
        state_schema={},
        node_defs=[
            NodeDefinition(node_id=n, display_name=n, prompt_template=f"step {n}")
            for n in node_ids
        ],
    )


class _ResumeRecorder:
    """Stands in for ``_invoke_graph_resume`` and records the graph it is given."""

    def __init__(self) -> None:
        self.node_ids: tuple[str, ...] | None = None
        self.branch_name = ""
        self.recursion_limit = None
        self.concurrency_budget_override = "<<never called>>"
        self.done = threading.Event()

    def __call__(
        self, _base, *, run_id, branch, thread_id, provider_call,
        recursion_limit, concurrency_budget_override,
    ):
        from tinyassets.runs import RUN_STATUS_COMPLETED, RunOutcome

        self.node_ids = tuple(n.node_id for n in branch.node_defs)
        self.branch_name = branch.name
        # C.1: these are REQUIRED keyword arguments now. A resume path that
        # dropped them would not even satisfy this signature.
        self.recursion_limit = recursion_limit
        self.concurrency_budget_override = concurrency_budget_override
        self.done.set()
        return RunOutcome(
            run_id=run_id, status=RUN_STATUS_COMPLETED, output={}, error="",
        )

    def wait(self) -> tuple[str, ...]:
        assert self.done.wait(10), "resume worker never ran"
        assert self.node_ids is not None
        return self.node_ids


class _InlineExecutor:
    """Runs the submitted worker on the calling thread so failures surface.

    A pooled worker's exception lands in a Future nobody reads, which would let
    a resume that never actually ran read as a pass. The admission fixture
    below uses the same executor for the opposite reason: a pooled worker that
    outlives the ``patch`` block that stubbed it runs the REAL worker body and
    terminalizes the run out from under the test.
    """

    def submit(self, fn, *args, **kwargs):
        future: Future = Future()
        future.set_result(fn(*args, **kwargs))
        return future


def _poisoned_lookup(node_ids, branch_def_id):
    """A ``branch_lookup`` that hands back an EDITED graph. Must be ignored."""
    calls: list[tuple[str, int]] = []

    def _lookup(bdid: str, version: int):
        calls.append((bdid, version))
        return _branch(node_ids, branch_def_id=branch_def_id)

    return _lookup, calls


@pytest.fixture
def admitted_run(tmp_path, monkeypatch):
    """A real def-based run, admitted with ADMITTED_NODES, left INTERRUPTED.

    Dispatch is forced onto the calling thread. ``execute_branch_async``
    submits its worker to a real pool and returns ``queued`` within
    milliseconds, so ``patch(..._invoke_prepared_branch)`` around that call
    covers the *dispatch*, never the pool thread's execution of it. Whichever
    body the pool thread reaches is then pure scheduling luck, and the real
    body cannot succeed here (the fixture branch declares no entry point):
    it writes ``failed`` and clobbers the ``interrupted`` set just below.
    That is the Linux-only failure of cloud oracle 35959680983 — the resume
    guards under test were never reached. Running the stub inline closes the
    window instead of widening it with a sleep.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _become("tester")

    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import (
        create_branch_definition_once,
        initialize_author_server,
    )
    from tinyassets.runs import (
        RUN_STATUS_INTERRUPTED,
        RUN_STATUS_QUEUED,
        RunOutcome,
        execute_branch_async,
        get_future,
        get_run,
        initialize_runs_db,
        update_run_status,
    )

    initialize_author_server(tmp_path)
    stored, _created = create_branch_definition_once(
        tmp_path,
        branch_def=_branch(ADMITTED_NODES, branch_def_id="branch-resume-identity").to_dict(),
    )
    initialize_runs_db(tmp_path)

    def _noop(*_a, **kw):
        return RunOutcome(
            run_id=kw.get("run_id", ""), status=RUN_STATUS_QUEUED, output={}, error="",
        )

    actor = _current_actor()
    with (
        patch("tinyassets.runs._invoke_prepared_branch", side_effect=_noop),
        patch("tinyassets.runs._get_executor", return_value=_InlineExecutor()),
    ):
        outcome = execute_branch_async(
            tmp_path,
            branch=BranchDefinition.from_dict(stored),
            inputs={},
            run_name="resume-identity-run",
            actor=actor,
        )
    # Initial-state diagnostics. A run that is already terminal here was
    # settled by something other than this fixture, and every assertion below
    # would then be testing the status gate rather than the identity guard.
    admitted_status = get_run(tmp_path, outcome.run_id).get("status")
    assert admitted_status == RUN_STATUS_QUEUED, (
        f"admitted run settled to {admitted_status!r} before it was interrupted; "
        "the stubbed worker did not own this dispatch"
    )
    future = get_future(outcome.run_id)
    assert future is None or future.done(), (
        "a background worker outlived the stub and can still terminalize this run"
    )
    update_run_status(tmp_path, outcome.run_id, status=RUN_STATUS_INTERRUPTED)
    assert get_run(tmp_path, outcome.run_id).get("status") == RUN_STATUS_INTERRUPTED
    return tmp_path, outcome.run_id, stored["branch_def_id"], actor


def test_resume_never_runs_an_edited_definition(admitted_run):
    """The edited draft must not reach the resumed graph — R1, the core defect."""
    base, run_id, bdid, actor = admitted_run
    # The author edits the draft after the run was admitted: three nodes now.
    from tinyassets.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )
    from tinyassets.runs import resume_run

    current = get_branch_definition(base, branch_def_id=bdid)
    edited = dict(current)
    edited["node_defs"] = _branch(EDITED_NODES, branch_def_id=bdid).to_dict()["node_defs"]
    save_branch_definition(base, branch_def=edited)

    lookup, lookup_calls = _poisoned_lookup(EDITED_NODES, bdid)
    recorder = _ResumeRecorder()
    with (
        patch("tinyassets.runs._has_checkpoint", return_value=True),
        patch("tinyassets.runs._invoke_graph_resume", side_effect=recorder),
        patch("tinyassets.runs._get_executor", return_value=_InlineExecutor()),
    ):
        resume_run(base, run_id=run_id, actor=actor, branch_lookup=lookup)

    assert recorder.wait() == ADMITTED_NODES, (
        "resume ran a definition the run was never admitted with"
    )
    # Success, not refusal: the run genuinely resumed on its admitted snapshot.
    assert recorder.branch_name == "resume-identity-fixture"
    assert lookup_calls == [], "the mutable lookup is no longer a definition authority"


def test_legacy_def_run_without_envelope_refuses_before_provider(tmp_path, monkeypatch):
    """No durable record → typed refusal, before any provider or effect."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _become("tester")
    from tinyassets.runs import (
        RUN_STATUS_INTERRUPTED,
        ResumeError,
        create_run,
        initialize_runs_db,
        resume_run,
        update_run_status,
    )

    initialize_runs_db(tmp_path)
    run_id = create_run(
        tmp_path, branch_def_id="legacy-branch", thread_id="", inputs={},
        actor="tester", run_name="legacy",
    )
    update_run_status(tmp_path, run_id, status=RUN_STATUS_INTERRUPTED)

    lookup, lookup_calls = _poisoned_lookup(EDITED_NODES, "legacy-branch")
    provider_calls: list[str] = []
    recorder = _ResumeRecorder()

    def _provider_spy(*_a, **kw):
        provider_calls.append(kw.get("run_id", ""))
        raise AssertionError("provider admission must not be reached")

    with (
        patch("tinyassets.runs._has_checkpoint", return_value=True),
        patch("tinyassets.runs._invoke_graph_resume", side_effect=recorder),
        patch(
            "tinyassets.foreground_run_provider.prepare_foreground_run_provider",
            side_effect=_provider_spy,
        ),
        pytest.raises(ResumeError) as caught,
    ):
        resume_run(tmp_path, run_id=run_id, actor="tester", branch_lookup=lookup)

    assert caught.value.reason == "admission_not_reconstructable"
    assert caught.value.reason in IDENTITY_REFUSAL_REASONS
    assert provider_calls == [], "refused after provider admission, not before"
    assert not recorder.done.is_set(), "a graph was dispatched anyway"
    assert lookup_calls == []


def test_corrupt_envelope_refuses_and_never_falls_back(admitted_run):
    """A corrupt envelope refuses; it never degrades to the current definition."""
    base, run_id, bdid, actor = admitted_run
    from tinyassets.run_admission_envelope import ENVELOPE_COLUMN
    from tinyassets.runs import ResumeError, _connect, resume_run

    with _connect(base) as conn:
        conn.execute(
            f"UPDATE runs SET {ENVELOPE_COLUMN} = ? WHERE run_id = ?",
            ("{not json", run_id),
        )
        conn.commit()

    lookup, lookup_calls = _poisoned_lookup(EDITED_NODES, bdid)
    recorder = _ResumeRecorder()
    with (
        patch("tinyassets.runs._has_checkpoint", return_value=True),
        patch("tinyassets.runs._invoke_graph_resume", side_effect=recorder),
        pytest.raises(ResumeError) as caught,
    ):
        resume_run(base, run_id=run_id, actor=actor, branch_lookup=lookup)

    assert caught.value.reason in IDENTITY_REFUSAL_REASONS
    assert not recorder.done.is_set()
    assert lookup_calls == []


def test_legacy_version_run_refuses_despite_its_immutable_pin(tmp_path, monkeypatch):
    """C.2: an explicit ``branch_version_id`` does NOT make a legacy run resumable.

    The previous round reconstructed such a run from its published snapshot,
    arguing that the old resume path applied no per-run overrides so nothing
    could be lost. That argument was invalid: the missing parameters were the
    BUG, and C.1 has now given the resume path exactly those parameters. A
    legacy run records the user's version SELECTION and nothing about the
    recursion limit or concurrency budget it was admitted with, so its
    execution is not reconstructable and it refuses.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _become("tester")
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.runs import (
        RUN_STATUS_INTERRUPTED,
        ResumeError,
        create_run,
        initialize_runs_db,
        resume_run,
        update_run_status,
    )

    initialize_runs_db(tmp_path)
    published = publish_branch_version(
        tmp_path,
        _branch(ADMITTED_NODES, branch_def_id="branch-legacy-version").to_dict(),
        publisher="tester",
    )
    run_id = create_run(
        tmp_path, branch_def_id="branch-legacy-version", thread_id="", inputs={},
        actor="tester", run_name="legacy-version",
        branch_version_id=published.branch_version_id,
    )
    update_run_status(tmp_path, run_id, status=RUN_STATUS_INTERRUPTED)

    lookup, lookup_calls = _poisoned_lookup(EDITED_NODES, "branch-legacy-version")
    recorder = _ResumeRecorder()
    with (
        patch("tinyassets.runs._has_checkpoint", return_value=True),
        patch("tinyassets.runs._invoke_graph_resume", side_effect=recorder),
        patch("tinyassets.runs._get_executor", return_value=_InlineExecutor()),
        pytest.raises(ResumeError) as caught,
    ):
        resume_run(tmp_path, run_id=run_id, actor="tester", branch_lookup=lookup)

    assert caught.value.reason == "admission_not_reconstructable"
    assert not recorder.done.is_set(), "a legacy run must never reach the worker"
    assert lookup_calls == [], "branch_lookup must not be consulted at all"
    # The published version itself is untouched -- the refusal is about the
    # RUN's missing evidence, not about the version's validity.
    assert published.branch_version_id


def test_no_admission_truth_is_inferred_from_a_function_signature():
    """C.2: the signature-reflection gate is gone, not merely unused.

    ``resume_applies_per_run_execution_overrides()`` asked whether
    ``_invoke_graph_resume`` accepted per-run overrides and, if not, treated a
    legacy run as reconstructable. That inverted the evidence: the absence
    proved the old path DROPPED the admitted choices. It is also now
    self-defeating -- C.1 added those parameters -- so the helper must be
    absent, not just unreferenced.
    """
    import inspect

    from tinyassets import run_admission_envelope
    from tinyassets.runs import _invoke_graph_resume

    assert not hasattr(run_admission_envelope, "resume_applies_per_run_execution_overrides")
    assert not hasattr(run_admission_envelope, "_reconstruct_legacy")
    # C.1 in the same breath: the parameters the retired gate looked for exist.
    params = set(inspect.signature(_invoke_graph_resume).parameters)
    assert {"recursion_limit", "concurrency_budget_override"} <= params


def test_resume_hands_the_worker_the_admitted_execution_choices(admitted_run):
    """C.1 at the dispatch seam; the real compile/invoke seams are covered in
    ``tests/test_resume_execution_choices.py``."""
    from tinyassets.runs import resume_run

    tmp_path, run_id, branch_def_id, actor = admitted_run
    lookup, lookup_calls = _poisoned_lookup(EDITED_NODES, branch_def_id)
    recorder = _ResumeRecorder()
    with (
        patch("tinyassets.runs._has_checkpoint", return_value=True),
        patch("tinyassets.runs._invoke_graph_resume", side_effect=recorder),
        patch("tinyassets.runs._get_executor", return_value=_InlineExecutor()),
    ):
        resume_run(tmp_path, run_id=run_id, actor=actor, branch_lookup=lookup)

    assert recorder.wait() == ADMITTED_NODES
    from tinyassets.runs import DEFAULT_RECURSION_LIMIT

    assert recorder.recursion_limit == DEFAULT_RECURSION_LIMIT
    assert recorder.concurrency_budget_override is None
    assert lookup_calls == []
