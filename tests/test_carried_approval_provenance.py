"""PR #1349 — carried-snapshot approval-forge bypass + fail-closed runtime gate.

Codex's final residual on PR #1349:

    A legacy/trusted snapshot with ``source_code`` + ``approved=True`` +
    ``approved_source_hash=""`` can be persisted and run, because the runtime
    only checked NON-empty hashes. Carrying paths: ``build_branch`` ``fork_from``
    copies ``parent_copy.node_defs`` wholesale, and ``rollback_node`` restores
    raw audit bodies.

This module proves the systematic fix:

1. **Fail-closed runtime gate** — ``graph_compiler._validate_source_code`` now
   refuses any approved source_code node with a missing/empty OR mismatched
   ``approved_source_hash`` (no empty-hash carve-out).
2. **Carried snapshots are reconciled** — ``build_branch`` fork-copy and
   ``rollback_node`` re-validate each carried node's approval against its
   source hash and clear approval metadata on mismatch.
3. **The bid executor** (a second code-exec path) enforces the same invariant.

The security invariant under test (no exceptions): a source_code node may
execute only if ``approved=True`` AND ``approved_source_hash`` is present AND
equals ``sha256(effective source_code)``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest


def _hash(src: str) -> str:
    return hashlib.sha256(src.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Fail-closed runtime gate (graph_compiler._validate_source_code)
# ─────────────────────────────────────────────────────────────────────────────


class TestFailClosedRuntimeGate:
    """The empty-hash carve-out is gone: an approved source_code node with no
    provenance hash must be refused, not run.
    """

    def _one_node_branch(self, *, source_code, approved, approved_source_hash):
        from tinyassets.branches import (
            BranchDefinition,
            EdgeDefinition,
            GraphNodeRef,
            NodeDefinition,
        )

        b = BranchDefinition(name="gate", entry_point="only")
        b.node_defs = [NodeDefinition(
            node_id="only", display_name="Only",
            source_code=source_code,
            approved=approved,
            approved_source_hash=approved_source_hash,
        )]
        b.graph_nodes = [GraphNodeRef(id="only", node_def_id="only")]
        b.edges = [
            EdgeDefinition(from_node="START", to_node="only"),
            EdgeDefinition(from_node="only", to_node="END"),
        ]
        return b

    def test_empty_hash_approved_node_fails_closed(self):
        """approved=True + empty hash → UnapprovedNodeError (the residual).

        NOTE (Codex S3 r11 #1): a source_code node now ALSO fails closed at the
        graph sandbox choke-point (SandboxUnavailableError) BEFORE the approval
        gate runs — source_code never executes in-process in Phase 1. This test
        exercises the SECONDARY approval-provenance defense directly so its
        coverage survives (it matters again when the Phase-2 runner lands).
        """
        from tinyassets.graph_compiler import (
            UnapprovedNodeError,
            _validate_source_code,
        )

        src = "def run(state): return {'out': 1}\n"
        b = self._one_node_branch(
            source_code=src, approved=True, approved_source_hash="",
        )
        with pytest.raises(UnapprovedNodeError, match="no.*provenance|fail-closed"):
            _validate_source_code(b.node_defs[0])

    def test_matching_hash_approved_node_passes(self):
        """pass-with: approved=True + matching hash → compiles."""
        from tinyassets.graph_compiler import compile_branch

        src = "def run(state): return {'out': 1}\n"
        b = self._one_node_branch(
            source_code=src, approved=True, approved_source_hash=_hash(src),
        )
        # Must not raise.
        compile_branch(b)

    def test_mismatched_hash_approved_node_fails_closed(self):
        """approved=True + stale/forged hash → UnapprovedNodeError.

        Secondary approval-provenance gate exercised directly (see the note on
        ``test_empty_hash_approved_node_fails_closed``): the source_code node also
        fails closed at the sandbox choke-point in Phase 1.
        """
        from tinyassets.graph_compiler import (
            UnapprovedNodeError,
            _validate_source_code,
        )

        approved_src = "def run(state): return {}\n"
        running_src = "def run(state): return {'x': 1}\n"
        b = self._one_node_branch(
            source_code=running_src, approved=True,
            approved_source_hash=_hash(approved_src),
        )
        with pytest.raises(UnapprovedNodeError, match="does not match"):
            _validate_source_code(b.node_defs[0])

    def test_mark_approved_helper_passes_gate(self):
        """The sanctioned in-process approval helper records a matching hash,
        so a node it approves runs cleanly through the fail-closed gate.
        """
        from tinyassets.branches import (
            BranchDefinition,
            EdgeDefinition,
            GraphNodeRef,
            NodeDefinition,
        )
        from tinyassets.graph_compiler import compile_branch

        b = BranchDefinition(name="helper", entry_point="only")
        b.node_defs = [NodeDefinition(
            node_id="only", display_name="Only",
            source_code="def run(state): return {'out': 2}\n",
        ).mark_approved(approved_by="host")]
        b.graph_nodes = [GraphNodeRef(id="only", node_def_id="only")]
        b.edges = [
            EdgeDefinition(from_node="START", to_node="only"),
            EdgeDefinition(from_node="only", to_node="END"),
        ]
        node = b.node_defs[0]
        assert node.approved is True
        assert node.approved_source_hash == _hash(node.source_code)
        compile_branch(b)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# 2a. Carried snapshot via build_branch fork-copy
# ─────────────────────────────────────────────────────────────────────────────


def _save_poisoned_parent(base: Path, *, branch_id: str, source_code: str) -> str:
    """Persist a branch whose node carries source_code + approved=True + EMPTY
    approved_source_hash directly (bypassing MCP authoring guards) to simulate
    a legacy / trusted snapshot, then publish a version and return its bvid.
    """
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )
    from tinyassets.daemon_server import (
        get_branch_definition,
        initialize_author_server,
        save_branch_definition,
    )

    initialize_author_server(base)
    nd = NodeDefinition(
        node_id="carried", display_name="Carried",
        source_code=source_code,
        output_keys=["out"],
    )
    # Forge the legacy state: approved flag set, but NO provenance hash.
    nd.approved = True
    nd.approved_by = "legacy-host"
    nd.approved_source_hash = ""
    branch = BranchDefinition(
        branch_def_id=branch_id,
        name="poisoned-parent",
        entry_point="carried",
        node_defs=[nd],
        graph_nodes=[GraphNodeRef(id="carried", node_def_id="carried")],
        edges=[
            EdgeDefinition(from_node="START", to_node="carried"),
            EdgeDefinition(from_node="carried", to_node="END"),
        ],
        state_schema=[{"name": "out", "type": "str"}],
    )
    save_branch_definition(base, branch_def=branch.to_dict())
    bd = get_branch_definition(base, branch_def_id=branch_id)
    v = publish_branch_version(base, bd, publisher="legacy-host")
    return v.branch_version_id


class TestForkCopyReconcilesCarriedApproval:
    """A fork that inherits the parent's node_defs wholesale must not carry an
    empty-hash (or stale-hash) approval forward.
    """

    def test_fork_copy_clears_empty_hash_approval(self, tmp_path, monkeypatch):
        from tinyassets.api.branches import _ext_branch_build

        base = tmp_path / "output"
        base.mkdir()
        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))

        src = "def run(state): return {'out': 'carried'}\n"
        bvid = _save_poisoned_parent(base, branch_id="parent1", source_code=src)

        # Fork WITHOUT supplying node_defs → inherit the parent's node wholesale.
        spec = json.dumps({
            "name": "Forked",
            "fork_from": bvid,
        })
        result = json.loads(_ext_branch_build({"spec_json": spec}))
        assert result["status"] == "built", result

        from tinyassets.daemon_server import get_branch_definition
        forked = get_branch_definition(base, branch_def_id=result["branch_def_id"])
        nd = next(n for n in forked["node_defs"] if n["node_id"] == "carried")

        # The carried, empty-hash approval must NOT survive the fork.
        assert nd["approved"] is False, nd
        assert not nd.get("approved_source_hash"), nd

    def test_forked_carried_node_fails_runtime_gate(self, tmp_path, monkeypatch):
        """End-to-end: the forked branch with the demoted carried node is
        refused. In Phase 1 the source_code node fails closed at the sandbox
        choke-point (SandboxUnavailableError); the demoted-approval provenance
        gate (UnapprovedNodeError) is the secondary defense. Either terminal
        refusal proves NO in-process execution — assert both are reachable.
        """
        from tinyassets.api.branches import _ext_branch_build
        from tinyassets.branches import BranchDefinition
        from tinyassets.daemon_server import get_branch_definition
        from tinyassets.graph_compiler import (
            UnapprovedNodeError,
            _validate_source_code,
        )
        from tinyassets.providers.base import SandboxUnavailableError
        from tinyassets.sandbox_policy import node_requires_sandbox_runner

        base = tmp_path / "output"
        base.mkdir()
        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))

        src = "def run(state): return {'out': 'carried'}\n"
        bvid = _save_poisoned_parent(base, branch_id="parent2", source_code=src)
        result = json.loads(_ext_branch_build(
            {"spec_json": json.dumps({"name": "Forked2", "fork_from": bvid})}
        ))
        assert result["status"] == "built", result

        forked = get_branch_definition(base, branch_def_id=result["branch_def_id"])
        carried = next(
            n for n in BranchDefinition.from_dict(forked).node_defs
            if n.node_id == "carried"
        )
        # Primary Phase-1 defense: a source_code node is repo/host-code touching.
        assert node_requires_sandbox_runner(carried) is True
        # The compiled node fails closed at run (no per-job runner).
        from tinyassets.graph_compiler import _build_node
        fn = _build_node(carried, provider_call=None, event_sink=None)
        with pytest.raises(SandboxUnavailableError):
            fn({})
        # Secondary defense: the demoted carried approval is refused directly.
        with pytest.raises(UnapprovedNodeError):
            _validate_source_code(carried)


# ─────────────────────────────────────────────────────────────────────────────
# 2b. Carried snapshot via rollback_node (raw audit body restore)
# ─────────────────────────────────────────────────────────────────────────────


class TestRollbackReconcilesCarriedApproval:
    """rollback_node restores a raw audit body. A v1 snapshot that carried an
    empty-hash approval must be demoted to unapproved on restore.
    """

    def test_rollback_clears_stale_empty_hash_approval(self, tmp_path, monkeypatch):
        base = tmp_path / "output"
        base.mkdir()
        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
        monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")

        from tinyassets.branches import (
            BranchDefinition,
            EdgeDefinition,
            GraphNodeRef,
            NodeDefinition,
        )
        from tinyassets.daemon_server import (
            get_branch_definition,
            initialize_author_server,
            save_branch_definition,
        )
        from tinyassets.runs import record_node_edit_audit

        initialize_author_server(base)

        # v1 body (poisoned legacy snapshot): approved=True, EMPTY hash.
        v1_src = "def run(state): return {'out': 'v1-legacy'}\n"
        v1_body = NodeDefinition(
            node_id="n", display_name="N", source_code=v1_src,
            output_keys=["out"],
        ).to_dict()
        v1_body["approved"] = True
        v1_body["approved_by"] = "legacy-host"
        v1_body["approved_source_hash"] = ""

        # Current (v2) body: a genuinely-approved, hash-matched node.
        v2_node = NodeDefinition(
            node_id="n", display_name="N",
            source_code="def run(state): return {'out': 'v2'}\n",
            output_keys=["out"],
        ).mark_approved(approved_by="tester")
        branch = BranchDefinition(
            branch_def_id="rb1",
            name="rollback-target",
            version=2,
            entry_point="n",
            node_defs=[v2_node],
            graph_nodes=[GraphNodeRef(id="n", node_def_id="n")],
            edges=[
                EdgeDefinition(from_node="START", to_node="n"),
                EdgeDefinition(from_node="n", to_node="END"),
            ],
            state_schema=[{"name": "out", "type": "str"}],
        )
        save_branch_definition(base, branch_def=branch.to_dict())

        # Audit row: version_before=1 carries the poisoned v1 body; the current
        # version (version_after) matches the persisted branch version.
        current = get_branch_definition(base, branch_def_id="rb1")
        current_version = int(current.get("version", 1))
        record_node_edit_audit(
            base,
            branch_def_id="rb1",
            version_before=1,
            version_after=current_version,
            nodes_changed=["n"],
            node_before=v1_body,
            node_after=v2_node.to_dict(),
            edit_kind="update",
        )

        # Reload universe_server against this data dir so the MCP action runs.
        from tinyassets import universe_server as us
        importlib.reload(us)
        try:
            result = json.loads(us.extensions(
                action="rollback_node",
                branch_def_id="rb1",
                node_id="n",
            ))
            assert result["status"] == "rolled_back", result

            rolled = get_branch_definition(base, branch_def_id="rb1")
            nd = next(n for n in rolled["node_defs"] if n["node_id"] == "n")
            # Restored the v1 source...
            assert nd["source_code"] == v1_src, nd
            # ...but the empty-hash approval must NOT survive the restore.
            assert nd["approved"] is False, nd
            assert not nd.get("approved_source_hash"), nd
        finally:
            importlib.reload(us)


# ─────────────────────────────────────────────────────────────────────────────
# 3. The bid executor is a second code-exec path — same fail-closed invariant
# ─────────────────────────────────────────────────────────────────────────────


class TestBidExecutorFailsClosed:
    """``execute_node_bid`` ``exec()``s source directly. It must enforce the
    same hash-provenance invariant as the compiler.
    """

    def _node(self, *, source_code, approved, approved_source_hash):
        from tinyassets.branches import NodeDefinition

        nd = NodeDefinition(
            node_id="bidn", display_name="BidN", source_code=source_code,
        )
        nd.approved = approved
        nd.approved_source_hash = approved_source_hash
        return nd

    def test_bid_executor_rejects_empty_hash(self, tmp_path):
        from tinyassets.bid.node_bid import NodeBid
        from tinyassets.executors.node_bid import execute_node_bid

        src = "def run(state):\n    return {'ok': 1}\n"
        node = self._node(source_code=src, approved=True, approved_source_hash="")
        bid = NodeBid(node_bid_id="nb_x", node_def_id="bidn", status="open")
        result = execute_node_bid(
            bid, node_lookup_fn=lambda _nid: node, output_dir=tmp_path,
        )
        assert result.status == "failed"
        assert "approval_provenance_invalid" in result.error

    def test_bid_executor_rejects_mismatched_hash(self, tmp_path):
        from tinyassets.bid.node_bid import NodeBid
        from tinyassets.executors.node_bid import execute_node_bid

        approved_src = "def run(state):\n    return {'ok': 1}\n"
        running_src = "def run(state):\n    return {'ok': 2}\n"
        node = self._node(
            source_code=running_src, approved=True,
            approved_source_hash=_hash(approved_src),
        )
        bid = NodeBid(node_bid_id="nb_y", node_def_id="bidn", status="open")
        result = execute_node_bid(
            bid, node_lookup_fn=lambda _nid: node, output_dir=tmp_path,
        )
        assert result.status == "failed"
        assert "approval_provenance_invalid" in result.error

    def test_bid_executor_runs_with_matching_hash(self, tmp_path):
        from tinyassets.bid.node_bid import NodeBid
        from tinyassets.executors.node_bid import execute_node_bid

        src = "def run(state):\n    return {'ok': state.get('x', 0) + 1}\n"
        node = self._node(
            source_code=src, approved=True, approved_source_hash=_hash(src),
        )
        bid = NodeBid(
            node_bid_id="nb_z", node_def_id="bidn",
            inputs={"x": 41}, status="open",
        )
        result = execute_node_bid(
            bid, node_lookup_fn=lambda _nid: node, output_dir=tmp_path,
        )
        assert result.status == "succeeded", result.error
        assert result.output == {"ok": 42}


# ─────────────────────────────────────────────────────────────────────────────
# Runnability surfaces reflect the fail-closed gate (describe/validate/get)
# ─────────────────────────────────────────────────────────────────────────────


class TestRunnabilitySurfacesProvenanceChecked:
    def test_empty_hash_node_is_unrunnable(self):
        from tinyassets.api.branches import _node_source_code_unrunnable

        # source_code + approved but no hash → not runnable (gate would refuse).
        assert _node_source_code_unrunnable({
            "node_id": "n", "source_code": "def run(s): return {}",
            "approved": True, "approved_source_hash": "",
        }) is True

    def test_matching_hash_node_is_runnable(self):
        from tinyassets.api.branches import _node_source_code_unrunnable

        src = "def run(s): return {}"
        assert _node_source_code_unrunnable({
            "node_id": "n", "source_code": src,
            "approved": True, "approved_source_hash": _hash(src),
        }) is False

    def test_prompt_template_node_is_runnable(self):
        from tinyassets.api.branches import _node_source_code_unrunnable

        # No executable source surface → not gated → runnable.
        assert _node_source_code_unrunnable({
            "node_id": "n", "source_code": "",
            "prompt_template": "hi {x}", "approved": False,
        }) is False
