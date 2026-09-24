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
   exactly once; the run completes. The resumed segment's receipts land at
   ``external_write_results``, and the predecessor's receipt -- written by the
   interrupted segment -- survives at ``prior_external_write_results``.

2. Interrupt AFTER one frontier-node effect fired: the current resume cannot
   get past that partially fired node. This is one hazardous possible waiting
   placement, not a requirement that every wait fires an effect first. Its body is
   refused by the run-scoped ``already_fired`` ledger (keyed by node, not by
   sink), the refusal fails the node, the run returns to ``failed``, and a
   second resume is rejected by the status gate. The already-landed external
   write is not re-fired, and its receipt survives the failed resume.

3. Branch admission is by lineage version NUMBER only: whatever definition
   ``branch_lookup`` returns for that number is compiled and invoked against
   the old checkpoint, with no identity check against the graph the checkpoint
   was written by. A branch patched to add a node runs that node on resume.

4. A resume cancelled mid-segment is the same shape: what the cancelled
   segment fired lands at the canonical key, what earlier segments fired
   survives beside it.

The preservation is a persisted RECORD, not a rehydrated chain. Prior receipts
never enter the resumed run's ``EffectChain``: they are not results a later
node may read (design D1), and the at-most-once refusal keeps running off
``already_fired``, which case 2 exercises directly.

NOT established here: whether a production park/wait frontier is reachable at
all, provider-authorized public resume behavior, or concurrency between a live
worker and a resume of the same run. The provider is an injected synthetic
callable and the interrupted row is flipped by hand, so nothing here is
evidence about a real provider's authority or about an actual daemon restart.
The third case measures an injected lookup, not the production
immutable-version resolver's behavior.
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


def _prior_evidence(row) -> dict:
    """Receipts the segments BEFORE this one wrote, as the row keeps them."""
    from tinyassets.runs import PRIOR_EXTERNAL_WRITE_RESULTS_KEY

    return dict((row.get("output") or {}).get(PRIOR_EXTERNAL_WRITE_RESULTS_KEY) or {})


# ---------------------------------------------------------------------------
# Case 1 -- interrupt BEFORE the frontier node's effects
# ---------------------------------------------------------------------------


def test_resume_replays_only_the_frontier_node_and_keeps_prior_receipts(base, monkeypatch):
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
    # The canonical key is this segment's receipts...
    assert set(_evidence(final)) == {"n2", "n3"}
    # ...and the interrupted segment's receipt for a real external write is
    # still on the row, unchanged, instead of being replaced by the resume.
    assert set(_prior_evidence(final)) == {"n1"}, (
        "a completed resume must not drop the interrupted segment's receipts"
    )
    assert _prior_evidence(final)["n1"] == before["n1"], (
        "the preserved receipt is the one the first segment actually wrote"
    )
    # Preserved as a record, never rehydrated: the resumed chain's own ledger
    # is the resumed segment only, and the prior node is not in it.
    assert "n1" not in _evidence(final)


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
    # The resumed segment fired nothing, so its canonical ledger is empty...
    assert _evidence(final) == {}
    # ...and the receipt for the write that DID land survives the failed
    # resume, including the sink-level detail of the half that failed.
    preserved = _prior_evidence(final)
    assert set(preserved) == {"n1", "n2"}
    assert preserved["n2"][SINK]["ok"] is True
    assert preserved["n2"][SECOND_SINK]["error_kind"] == "effector_crashed"
    assert preserved == before, (
        "a failed resume must preserve the interrupted segment's receipts verbatim"
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


# ---------------------------------------------------------------------------
# Case 4 -- a resume cancelled mid-segment
# ---------------------------------------------------------------------------


def test_cancelled_resume_keeps_prior_receipts_beside_its_own(base, monkeypatch):
    """Cancel is the third terminal exit a resume has, and it persists the
    same way failure does: the row's output is rewritten from the resumed
    chain. The interrupted segment's receipt has to come through it too.
    """
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
    assert set(before) == {"n1"}

    # Cancel arrives while the resumed segment is serving its frontier node,
    # the way a user's cancel would land on a running resume.
    plain = provider.__call__

    def cancelling(prompt, system="", *, role="writer", fallback_response=None):
        text = plain(prompt, system, role=role, fallback_response=fallback_response)
        if prompt.split("packet:", 1)[1].strip() == "n2":
            runs.request_cancel(base, first.run_id)
        return text

    _interrupt(base, first.run_id)
    runs.resume_run(
        base, run_id=first.run_id, actor=ACTOR,
        branch_lookup=lambda branch_def_id, version: branch,
        provider_call=cancelling,
    )
    runs.wait_for(first.run_id, timeout=120)
    final = runs.get_run(base, first.run_id)

    assert final["status"] == runs.RUN_STATUS_CANCELLED
    # n3 is never reached, so whatever the cancelled segment recorded is at
    # most n2 -- and n1's receipt is preserved regardless.
    assert "n3" not in _evidence(final)
    assert _prior_evidence(final) == before, (
        "a cancelled resume must preserve the interrupted segment's receipts"
    )
    assert "n1" not in _evidence(final), "preserved as a record, not rehydrated"


# ---------------------------------------------------------------------------
# Case 5 -- the key is server-owned, not branch-authored
# ---------------------------------------------------------------------------


def test_prior_receipt_key_is_server_owned_and_cannot_be_forged(base, monkeypatch):
    """Two independent layers own the key, and a branch owns neither.

    The quarantine strips a branch-authored value before the effector runs,
    and the status write drops whatever survived that and recomputes the key
    from the row. Either layer alone would make the key trustworthy; the test
    pins both, because the carry reads its own key back off the row and would
    otherwise launder a forged value into a server-owned one on the next
    segment.
    """
    from tinyassets import runs

    # Layer 1: a branch-authored value never reaches the effector's output.
    forged_branch_output = {
        runs.PRIOR_EXTERNAL_WRITE_RESULTS_KEY: {"n_forged": {SINK: {"ok": True}}},
    }
    runs._quarantine_branch_authored_external_write_keys(forged_branch_output)
    assert runs.PRIOR_EXTERNAL_WRITE_RESULTS_KEY not in forged_branch_output
    assert forged_branch_output[
        f"_branch_authored_{runs.PRIOR_EXTERNAL_WRITE_RESULTS_KEY}"
    ] == {"n_forged": {SINK: {"ok": True}}}

    # Layer 2: the status write recomputes the key from the row, so a forged
    # value riding on the persisted output is dropped rather than merged.
    provider = _Provider(die_on={("n2", 1)})
    adapter = _Adapter(SINK)
    monkeypatch.setitem(effectors._EFFECTORS, SINK, adapter)
    branch = _linear(_node("n1"), _node("n2"))
    first = runs.execute_branch(
        base, branch=branch, inputs={}, actor=ACTOR, provider_call=provider,
    )
    assert first.status == runs.RUN_STATUS_FAILED
    real_prior = _evidence(runs.get_run(base, first.run_id))
    assert set(real_prior) == {"n1"}

    persisted = {
        "some_branch_key": "kept",
        runs.PRIOR_EXTERNAL_WRITE_RESULTS_KEY: {"n_forged": {SINK: {"ok": True}}},
    }
    runs._carry_prior_effect_receipts(base, first.run_id, persisted)

    carried = persisted[runs.PRIOR_EXTERNAL_WRITE_RESULTS_KEY]
    assert "n_forged" not in carried, "a branch-supplied value must not survive"
    assert set(carried) == {"n1"}
    assert carried["n1"] == real_prior["n1"]
    assert persisted["some_branch_key"] == "kept", "only the reserved key is owned"


# ---------------------------------------------------------------------------
# Case 6 -- the record survives TWO resumes, not just one
# ---------------------------------------------------------------------------


def test_prior_receipts_accumulate_across_two_resumes(base, monkeypatch):
    """Each resume replaces the row's canonical receipts with its own segment.

    With three segments the carry has to read its OWN key back and re-persist
    it, not just the canonical one -- so this is the case that separates a
    real accumulating record from a one-deep merge.
    """
    from tinyassets import runs

    provider = _Provider(die_on={("n2", 1), ("n3", 1)})
    adapter = _Adapter(SINK)
    monkeypatch.setitem(effectors._EFFECTORS, SINK, adapter)
    branch = _linear(_node("n1"), _node("n2"), _node("n3"), _node("n4"))
    lookup = lambda branch_def_id, version: branch  # noqa: E731

    # Segment 1: n1 fires, n2's body dies.
    first = runs.execute_branch(
        base, branch=branch, inputs={}, actor=ACTOR, provider_call=provider,
    )
    assert first.status == runs.RUN_STATUS_FAILED
    seg1 = _evidence(runs.get_run(base, first.run_id))
    assert set(seg1) == {"n1"}

    # Segment 2: n2 replays and fires, n3's body dies.
    _interrupt(base, first.run_id)
    runs.resume_run(
        base, run_id=first.run_id, actor=ACTOR,
        branch_lookup=lookup, provider_call=provider,
    )
    runs.wait_for(first.run_id, timeout=120)
    mid = runs.get_run(base, first.run_id)
    assert mid["status"] == runs.RUN_STATUS_FAILED
    seg2 = _evidence(mid)
    assert set(seg2) == {"n2"}
    assert set(_prior_evidence(mid)) == {"n1"}

    # Segment 3: n3 replays and fires, n4 fires, the run completes.
    _interrupt(base, first.run_id)
    runs.resume_run(
        base, run_id=first.run_id, actor=ACTOR,
        branch_lookup=lookup, provider_call=provider,
    )
    runs.wait_for(first.run_id, timeout=120)
    final = runs.get_run(base, first.run_id)

    assert final["status"] == runs.RUN_STATUS_COMPLETED
    assert provider.calls == {"n1": 1, "n2": 2, "n3": 2, "n4": 1}
    # The canonical key is the LAST segment only...
    assert set(_evidence(final)) == {"n3", "n4"}
    # ...and BOTH earlier segments' receipts are still on the row, verbatim.
    preserved = _prior_evidence(final)
    assert set(preserved) == {"n1", "n2"}
    assert preserved["n1"] == seg1["n1"], "segment 1 survived two resumes"
    assert preserved["n2"] == seg2["n2"], "segment 2 survived one resume"
    # Still a record, never rehydrated: each node fired exactly once.
    assert adapter.calls == ["n1", "n2", "n3", "n4"]


# ---------------------------------------------------------------------------
# Case 7 -- a resume that fails to COMPILE still replaces the row's output
# ---------------------------------------------------------------------------


def test_compile_failure_on_resume_does_not_erase_prior_receipts(base, monkeypatch):
    """The compile-failure exit passes ``output=None``, which reads as "writes
    nothing" -- but the terminal status write still rebuilds ``output_json``
    from the resumed chain, whose ledger is empty because nothing ran. That is
    a path that genuinely REPLACES the row's receipts with an empty record, so
    it needs the carry as much as the paths that executed nodes do.
    """
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
    assert set(before) == {"n1"}

    # Patched only after the first segment ran, so the failure is the resume's.
    def boom(*a, **kw):
        raise runs.CompilerError("branch no longer compiles")

    monkeypatch.setattr(runs, "compile_branch", boom)

    _interrupt(base, first.run_id)
    runs.resume_run(
        base, run_id=first.run_id, actor=ACTOR,
        branch_lookup=lambda branch_def_id, version: branch,
        provider_call=provider,
    )
    runs.wait_for(first.run_id, timeout=120)
    final = runs.get_run(base, first.run_id)

    assert final["status"] == runs.RUN_STATUS_FAILED
    assert "no longer compiles" in (final.get("error") or "")
    # Nothing ran, so the canonical key holds nothing...
    assert _evidence(final) == {}
    # ...and the receipt for the write that DID land is still on the row.
    assert _prior_evidence(final) == before, (
        "a resume that never compiled must not erase the earlier segment's "
        "external-write receipts"
    )
    assert adapter.calls == ["n1"], "the compile failure fired nothing"
