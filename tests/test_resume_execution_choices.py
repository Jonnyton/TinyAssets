"""C.1: a resumed run executes with the execution choices it was ADMITTED with.

Design source:
``openspec/changes/consolidate-platform-resource-policy/design-amendment-resume-exact-definition.md``
§"Round-2 corrections", C.1.

**What makes this evidence rather than decoration.** The earlier round persisted
``recursion_limit`` / ``concurrency_budget_override`` into the admission
envelope and then dropped them: ``resume_run`` never passed them on, and
``_invoke_graph_resume`` called ``compile_branch`` with no
``concurrency_budget_override`` and ``app.invoke`` with no ``recursion_limit``.
Every assertion below therefore reads the value at the **real seam that
consumes it** -- the actual ``compile_branch`` call and the actual
``app.invoke`` config -- not at a mocked worker boundary. The proxies delegate
to the real implementations; nothing here substitutes the resume body.

Run admission goes through the SYNCHRONOUS ``execute_branch``, which C.3 brought
under envelope capture, so this file is also the executing proof for that seam:
without C.3 there is no envelope and the resume refuses outright.

NOT established here: real provider authority (the writer is synthetic), daemon
restart behaviour (the INTERRUPTED row is written by hand), or that LangGraph
enforces the recursion cap -- only that the admitted number reaches the config
key ``_invoke_graph`` uses for the same purpose.
"""

from __future__ import annotations

import json
from concurrent.futures import Future

import pytest

from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)

ACTOR = "universe:u-exec-choices"

#: Deliberately not the platform default (100) and not the branch-wide budget,
#: so a fallback to either is visible as a failure rather than a coincidence.
ADMITTED_RECURSION_LIMIT = 77
ADMITTED_CONCURRENCY_OVERRIDE = 3
BRANCH_WIDE_CONCURRENCY = 9


def _node(node_id: str) -> NodeDefinition:
    return NodeDefinition(
        node_id=node_id, display_name=node_id,
        prompt_template=f"packet:{node_id}",
        output_keys=[f"{node_id}_out"],
    )


def _linear(*nodes: NodeDefinition) -> BranchDefinition:
    branch = BranchDefinition(
        name="exec-choices-chain", entry_point=nodes[0].node_id, author=ACTOR,
    )
    branch.node_defs = list(nodes)
    branch.graph_nodes = [GraphNodeRef(id=n.node_id, node_def_id=n.node_id) for n in nodes]
    edges = [EdgeDefinition(from_node="START", to_node=nodes[0].node_id)]
    for a, b in zip(nodes, nodes[1:]):
        edges.append(EdgeDefinition(from_node=a.node_id, to_node=b.node_id))
    edges.append(EdgeDefinition(from_node=nodes[-1].node_id, to_node="END"))
    branch.edges = edges
    branch.state_schema = [{"name": f"{n.node_id}_out", "type": "str"} for n in nodes]
    branch.concurrency_budget = BRANCH_WIDE_CONCURRENCY
    return branch


class _Provider:
    def __init__(self, die_on: set[tuple[str, int]] | None = None):
        self.calls: dict[str, int] = {}
        self.die_on = set(die_on or ())

    def __call__(self, prompt, system="", *, role="writer", fallback_response=None):
        node_id = prompt.split("packet:", 1)[1].strip()
        self.calls[node_id] = self.calls.get(node_id, 0) + 1
        if (node_id, self.calls[node_id]) in self.die_on:
            raise RuntimeError(f"host died serving {node_id}")
        return json.dumps({"node": node_id})


class _AppProxy:
    """Wraps the compiled LangGraph app; records the config invoke receives."""

    def __init__(self, inner, sink: dict):
        self._inner = inner
        self._sink = sink

    def invoke(self, state, config=None, **kwargs):
        self._sink["invoke_config"] = config
        return self._inner.invoke(state, config=config, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _GraphProxy:
    def __init__(self, inner, sink: dict):
        self._inner = inner
        self._sink = sink

    def compile(self, **kwargs):
        return _AppProxy(self._inner.compile(**kwargs), self._sink)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _CompiledProxy:
    def __init__(self, inner, sink: dict):
        self._inner = inner
        self._sink = sink

    @property
    def graph(self):
        return _GraphProxy(self._inner.graph, self._sink)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _InlineExecutor:
    """Runs the resume worker on the calling thread so an exception surfaces."""

    def submit(self, fn, *args, **kwargs):
        future: Future = Future()
        future.set_result(fn(*args, **kwargs))
        return future


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    from tinyassets.runs import initialize_runs_db

    initialize_runs_db(tmp_path)
    return tmp_path


def _admit_and_interrupt(base):
    """A real sync-admitted run, parked INTERRUPTED with a live checkpoint."""
    from tinyassets import runs

    provider = _Provider(die_on={("n2", 1)})
    branch = _linear(_node("n1"), _node("n2"), _node("n3"))
    first = runs.execute_branch(
        base, branch=branch, inputs={}, actor=ACTOR, provider_call=provider,
        recursion_limit_override=ADMITTED_RECURSION_LIMIT,
        concurrency_budget_override=ADMITTED_CONCURRENCY_OVERRIDE,
    )
    assert first.status == runs.RUN_STATUS_FAILED, first.error
    assert runs._has_checkpoint(base, first.run_id), "no checkpoint to resume from"
    runs.update_run_status(base, first.run_id, status=runs.RUN_STATUS_INTERRUPTED)
    return first.run_id, branch, provider


def test_resume_compiles_and_invokes_with_the_admitted_execution_choices(
    base, monkeypatch,
):
    """The admitted 77 / 3 reach app.invoke's config and compile_branch."""
    from tinyassets import runs

    run_id, branch, provider = _admit_and_interrupt(base)

    sink: dict = {}
    real_compile = runs.compile_branch

    def _spy_compile(branch_arg, **kwargs):
        sink.setdefault("compile_calls", []).append(
            kwargs.get("concurrency_budget_override", "<<absent>>")
        )
        return _CompiledProxy(real_compile(branch_arg, **kwargs), sink)

    monkeypatch.setattr(runs, "compile_branch", _spy_compile)
    monkeypatch.setattr(runs, "_get_executor", lambda *a, **k: _InlineExecutor())

    runs.resume_run(
        base, run_id=run_id, actor=ACTOR,
        # Deliberately poisoned: if the removed branch_lookup path ever comes
        # back, this graph is not the admitted one and the run would diverge.
        branch_lookup=lambda _bid, _v: _linear(_node("injected")),
        provider_call=provider,
    )

    assert sink.get("compile_calls"), "the real compile_branch seam was never reached"
    assert sink["compile_calls"][0] == ADMITTED_CONCURRENCY_OVERRIDE, (
        "resume compiled with the wrong concurrency budget: "
        f"{sink['compile_calls'][0]!r} (branch-wide is {BRANCH_WIDE_CONCURRENCY}, "
        "absent means the pre-fix drop)"
    )
    config = sink.get("invoke_config")
    assert config is not None, "the real app.invoke seam was never reached"
    assert config.get("recursion_limit") == ADMITTED_RECURSION_LIMIT, (
        f"resume invoked with recursion_limit={config.get('recursion_limit')!r}; "
        f"admitted {ADMITTED_RECURSION_LIMIT}"
    )
    assert config["configurable"]["thread_id"] == run_id


def test_admitted_choices_survive_a_draft_edit_between_admit_and_resume(
    base, monkeypatch,
):
    """Editing the draft's budget does not move an already-admitted run's.

    The envelope is the authority, so a later edit to the branch-wide
    ``concurrency_budget`` cannot retroactively change what a parked run
    resumes with.
    """
    from tinyassets import runs
    from tinyassets.run_admission_envelope import resolve_admitted_execution

    run_id, branch, _provider = _admit_and_interrupt(base)

    branch.concurrency_budget = BRANCH_WIDE_CONCURRENCY + 100  # author edits the draft

    admitted = resolve_admitted_execution(base, runs.get_run(base, run_id))
    assert admitted.source == "envelope"
    assert admitted.recursion_limit == ADMITTED_RECURSION_LIMIT
    assert admitted.concurrency_budget_override == ADMITTED_CONCURRENCY_OVERRIDE
    assert admitted.effective_concurrency_budget == ADMITTED_CONCURRENCY_OVERRIDE
    assert tuple(n.node_id for n in admitted.branch.node_defs) == ("n1", "n2", "n3")


def test_version_based_sync_admission_captures_its_envelope(base, monkeypatch):
    """C.3: ``execute_branch_version`` admits under an envelope too.

    The branch handed to ``_invoke_graph`` is the immutable snapshot, and the
    envelope records THAT object plus the per-run choices the snapshot cannot
    carry.
    """
    from tinyassets import runs
    from tinyassets.run_admission_envelope import resolve_admitted_execution

    branch = _linear(_node("v1"), _node("v2"))
    provider = _Provider()

    loaded: list[BranchDefinition] = []

    def _fake_load(_base, version_id):
        assert version_id == "bv-exec-choices"
        snapshot = BranchDefinition.from_dict(branch.to_dict())
        loaded.append(snapshot)
        return snapshot

    monkeypatch.setattr(runs, "_load_branch_version", _fake_load)

    outcome = runs.execute_branch_version(
        base, branch_version_id="bv-exec-choices", inputs={}, actor=ACTOR,
        provider_call=provider,
        recursion_limit_override=ADMITTED_RECURSION_LIMIT,
        concurrency_budget_override=ADMITTED_CONCURRENCY_OVERRIDE,
    )
    assert outcome.status == runs.RUN_STATUS_COMPLETED, outcome.error

    row = runs.get_run(base, outcome.run_id)
    admitted = resolve_admitted_execution(base, row)
    assert admitted.source == "envelope"
    assert admitted.recursion_limit == ADMITTED_RECURSION_LIMIT
    assert admitted.concurrency_budget_override == ADMITTED_CONCURRENCY_OVERRIDE
    assert admitted.branch_version_id == "bv-exec-choices"
    assert tuple(n.node_id for n in admitted.branch.node_defs) == ("v1", "v2")
    # branch_version_id's attribution meaning is untouched by the envelope.
    assert row.get("branch_version_id") == "bv-exec-choices"


def test_admission_envelope_is_absent_from_the_public_run_projection(base):
    """The envelope is private: no public read surface may carry it."""
    from tinyassets import runs
    from tinyassets.run_admission_envelope import ENVELOPE_COLUMN

    run_id, _branch, _provider = _admit_and_interrupt(base)
    row = runs.get_run(base, run_id)
    assert ENVELOPE_COLUMN not in row
    assert not any("envelope" in str(k).lower() for k in row)
