"""Integration: what a REAL ``resume_run`` does to a real interrupted run.

The prior characterization module measured LangGraph's checkpoint semantics on
synthetic graphs, and the TinyAssets effect ledger in isolation. It explicitly
did not establish whether the full ``resume_run`` lifecycle -- status gates,
lineage-keyed branch admission, background worker, effect-chain seeding --
preserves those semantics end to end. This module does, because durable
workspace waiting would be built on exactly that lifecycle.

Nothing here stubs ``resume_run``, ``_invoke_graph_resume`` or the worker. Each
test drives a real ``execute_branch`` to a real interrupt, leaves a real
SqliteSaver checkpoint under the run's data dir, flips the row to
``interrupted`` the way ``recover_in_flight_runs`` does, and calls the real
``resume_run``. The only synthetic parts are the provider callable and the
effect adapters -- no network, no provider process, no external write.

MEASURED (2026-09-24 UTC, Windows, ``pytest tests/test_resume_lifecycle_integration.py``):

1. Interrupt BEFORE the frontier node's effects: the completed predecessor is
   neither re-served nor re-fired; the frontier node's body is re-served
   exactly once; the run completes. But the completed run's
   ``external_write_results`` then contains ONLY the resumed segment -- the
   predecessor's receipt, written by the interrupted segment, is gone.

2. Interrupt AFTER one frontier-node effect fired: the current resume cannot
   get past that partially fired node. This is one hazardous possible waiting
   placement, not a requirement that every wait fires an effect first. Its body is
   refused by the run-scoped ``already_fired`` ledger (keyed by node, not by
   sink), the refusal fails the node, the run returns to ``failed``, and a
   second resume is rejected by the status gate. The already-landed external
   write is not re-fired -- and its receipt is erased by the failed resume.

3. Branch admission is by lineage version NUMBER only: whatever definition
   ``branch_lookup`` returns for that number is compiled and invoked against
   the old checkpoint, with no identity check against the graph the checkpoint
   was written by. A branch patched to add a node runs that node on resume.

NOT established here: whether a production park/wait frontier is reachable at
all, provider-authorized public resume behavior, or concurrency between a live
worker and a resume of the same run. The third case measures an injected lookup,
not the production immutable-version resolver's behavior.
"""

from __future__ import annotations

import json

import pytest

from tinyassets import effectors
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)

SINK = "authenticated_external_call"
SECOND_SINK = "wiki_write_back"

#: Runs execute as this actor and the branches are authored by it, so the
#: compiled execution context is "own" provenance rather than public-foreign.
ACTOR = "universe:u-resume"


def _packet(node_id: str) -> str:
    return json.dumps({
        "sink": SINK, "connection_id": "c1", "grant_id": "g1", "verb": "GET",
        "request": {"method": "GET", "url": f"https://api.example.test/{node_id}"},
    })


def _node(node_id: str, effects=(SINK,)) -> NodeDefinition:
    return NodeDefinition(
        node_id=node_id, display_name=node_id,
        prompt_template=f"packet:{node_id}",
        output_keys=[f"{node_id}_packet"],
        effects=list(effects),
    )


def _linear(*nodes: NodeDefinition) -> BranchDefinition:
    branch = BranchDefinition(
        name="resume-chain", entry_point=nodes[0].node_id, author=ACTOR,
    )
    branch.node_defs = list(nodes)
    branch.graph_nodes = [GraphNodeRef(id=n.node_id, node_def_id=n.node_id) for n in nodes]
    edges = [EdgeDefinition(from_node="START", to_node=nodes[0].node_id)]
    for a, b in zip(nodes, nodes[1:]):
        edges.append(EdgeDefinition(from_node=a.node_id, to_node=b.node_id))
    edges.append(EdgeDefinition(from_node=nodes[-1].node_id, to_node="END"))
    branch.edges = edges
    branch.state_schema = [{"name": f"{n.node_id}_packet", "type": "str"} for n in nodes]
    return branch


class _Provider:
    """Synthetic writer. Counts calls per node and can die once, on cue.

    Counting per node IS the measurement: a node body that replays after a
    resume calls the provider a second time.
    """

    def __init__(self, die_on: set[tuple[str, int]] | None = None):
        self.calls: dict[str, int] = {}
        self.die_on = set(die_on or ())

    def __call__(self, prompt, system="", *, role="writer", fallback_response=None):
        node_id = prompt.split("packet:", 1)[1].strip()
        self.calls[node_id] = self.calls.get(node_id, 0) + 1
        if (node_id, self.calls[node_id]) in self.die_on:
            raise RuntimeError(f"host died serving {node_id}")
        return _packet(node_id)


class _Adapter:
    """Stand-in effector. Records which nodes reached the sink."""

    def __init__(self, name: str, crash_first_for: set[str] | None = None):
        self.name = name
        self.calls: list[str] = []
        self.crash_first_for = set(crash_first_for or ())

    def __call__(self, *, node_id, output_keys, run_state, base_path, run_id, dry_run,
                 allowed_state_keys=None, prior_effects=None):
        self.calls.append(node_id)
        if node_id in self.crash_first_for and self.calls.count(node_id) == 1:
            raise RuntimeError(f"{self.name} unavailable for {node_id}")
        return {"status": 200, "ok": True, "node": node_id, "sink": self.name}


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    from tinyassets.runs import initialize_runs_db

    initialize_runs_db(tmp_path)
    return tmp_path


def _interrupt(base_path, run_id) -> None:
    """Park the row where ``resume_run``'s status gate expects it.

    ``recover_in_flight_runs`` writes exactly this status for a run whose host
    died; writing it directly keeps the test off server startup.
    """
    from tinyassets.runs import RUN_STATUS_INTERRUPTED, update_run_status

    update_run_status(base_path, run_id, status=RUN_STATUS_INTERRUPTED)


def _evidence(row) -> dict:
    return dict((row.get("output") or {}).get("external_write_results") or {})


# ---------------------------------------------------------------------------
# Case 1 -- interrupt BEFORE the frontier node's effects
# ---------------------------------------------------------------------------


def test_resume_replays_only_the_frontier_node_but_drops_prior_receipts(base, monkeypatch):
    from tinyassets import runs

    provider = _Provider(die_on={("n2", 1)})
    adapter = _Adapter(SINK)
    monkeypatch.setitem(effectors._EFFECTORS, SINK, adapter)
    branch = _linear(_node("n1"), _node("n2"), _node("n3"))

    first = runs.execute_branch(
        base, branch=branch, inputs={}, actor=ACTOR, provider_call=provider,
    )
    assert first.status == runs.RUN_STATUS_FAILED
    before = _evidence(runs.get_run(base, first.run_id))
    assert set(before) == {"n1"}, "only the predecessor's write landed pre-interrupt"
    assert runs._has_checkpoint(base, first.run_id), "the interrupt left a real checkpoint"

    _interrupt(base, first.run_id)
    dispatched = runs.resume_run(
        base, run_id=first.run_id, actor=ACTOR,
        branch_lookup=lambda branch_def_id, version: branch,
        provider_call=provider,
    )
    assert dispatched.status == runs.RUN_STATUS_RESUMED
    runs.wait_for(first.run_id, timeout=120)
    final = runs.get_run(base, first.run_id)

    assert final["status"] == runs.RUN_STATUS_COMPLETED
    # The measurement: the completed predecessor is not re-served and not
    # re-fired; the frontier node's body replays exactly once.
    assert provider.calls == {"n1": 1, "n2": 2, "n3": 1}
    assert adapter.calls == ["n1", "n2", "n3"]
    # ...and the defect: the resumed segment's evidence REPLACES the row's, so
    # the interrupted segment's receipt for a real external write is lost.
    assert set(_evidence(final)) == {"n2", "n3"}, (
        "current behaviour: a completed resume drops the interrupted segment's "
        "external_write_results instead of merging them"
    )


# ---------------------------------------------------------------------------
# Case 2 -- interrupt AFTER the frontier node's effects fired
# ---------------------------------------------------------------------------


def test_node_that_already_fired_can_never_be_resumed_past(base, monkeypatch):
    """One placement a safe durable wait cannot blindly resume through.

    ``n2`` lands its external write through the first sink and then fails on
    the second -- the same frontier a node would leave if it dispatched work
    and then had to wait for the answer. Resume replays the body, the
    run-scoped ledger (keyed by NODE, so the landed sink and the failed one
    share one key) refuses the whole node, and the run is terminal again.
    """
    from tinyassets import runs
    from tinyassets.runs import ResumeError

    provider = _Provider()
    landed = _Adapter(SINK)
    flaky = _Adapter(SECOND_SINK, crash_first_for={"n2"})
    monkeypatch.setitem(effectors._EFFECTORS, SINK, landed)
    monkeypatch.setitem(effectors._EFFECTORS, SECOND_SINK, flaky)
    branch = _linear(_node("n1"), _node("n2", (SINK, SECOND_SINK)), _node("n3"))

    first = runs.execute_branch(
        base, branch=branch, inputs={}, actor=ACTOR, provider_call=provider,
    )
    assert first.status == runs.RUN_STATUS_FAILED
    before = _evidence(runs.get_run(base, first.run_id))
    assert landed.calls == ["n1", "n2"], "n2's external write really landed"
    assert before["n2"][SINK]["ok"] is True
    assert before["n2"][SECOND_SINK]["error_kind"] == "effector_crashed"

    _interrupt(base, first.run_id)
    runs.resume_run(
        base, run_id=first.run_id, actor=ACTOR,
        branch_lookup=lambda branch_def_id, version: branch,
        provider_call=provider,
    )
    runs.wait_for(first.run_id, timeout=120)
    final = runs.get_run(base, first.run_id)

    assert final["status"] == runs.RUN_STATUS_FAILED
    assert "already fired" in (final.get("error") or ""), (
        "the replayed body is refused by the already_fired ledger, not re-run"
    )
    # No double fire -- the ledger does hold. n2's body WAS re-served, so the
    # refusal is what stopped the second dispatch, not the node being skipped.
    assert provider.calls["n2"] == 2
    assert landed.calls == ["n1", "n2"]
    assert flaky.calls == ["n2"]
    # n3 never runs: resuming cannot get the run past n2, at all.
    assert "n3" not in provider.calls
    # And the failed resume erases the receipt for the write that DID land.
    assert _evidence(final) == {}, (
        "current behaviour: a failed resume replaces the row's "
        "external_write_results with the resumed segment's empty ledger"
    )
    # Terminal: the status gate rejects a second attempt, so no retry loop
    # recovers this run.
    with pytest.raises(ResumeError) as excinfo:
        runs.resume_run(
            base, run_id=first.run_id, actor=ACTOR,
            branch_lookup=lambda branch_def_id, version: branch,
            provider_call=provider,
        )
    assert excinfo.value.reason == "not_interrupted"


# ---------------------------------------------------------------------------
# Case 3 -- which definition resume admits
# ---------------------------------------------------------------------------


def test_resume_admits_the_lineage_version_number_without_a_graph_identity_check(
    base, monkeypatch,
):
    from tinyassets import runs

    provider = _Provider(die_on={("n2", 1)})
    adapter = _Adapter(SINK)
    monkeypatch.setitem(effectors._EFFECTORS, SINK, adapter)
    original = _linear(_node("n1"), _node("n2"), _node("n3"))

    first = runs.execute_branch(
        base, branch=original, inputs={}, actor=ACTOR, provider_call=provider,
    )
    assert first.status == runs.RUN_STATUS_FAILED
    lineage = runs.get_lineage(base, first.run_id)
    assert lineage is not None and lineage["branch_version"] == 1

    # A definition patched AFTER the interrupt, published under the same
    # branch_def_id and the same version number the lineage records.
    patched = _linear(_node("n1"), _node("n2"), _node("n3"), _node("n4"))
    patched.branch_def_id = original.branch_def_id
    seen: list[tuple[str, int]] = []

    def lookup(branch_def_id: str, version: int):
        seen.append((branch_def_id, version))
        return patched

    _interrupt(base, first.run_id)
    runs.resume_run(
        base, run_id=first.run_id, actor=ACTOR,
        branch_lookup=lookup, provider_call=provider,
    )
    runs.wait_for(first.run_id, timeout=120)
    final = runs.get_run(base, first.run_id)

    # Admission is the lineage's (branch_def_id, version) pair, asked once.
    assert seen == [(runs.get_run(base, first.run_id)["branch_def_id"], 1)]
    # ...and whatever that pair resolves to is what runs, over a checkpoint
    # written by a different graph. The added node executes and fires.
    assert final["status"] == runs.RUN_STATUS_COMPLETED
    assert provider.calls["n4"] == 1
    assert adapter.calls[-1] == "n4"
