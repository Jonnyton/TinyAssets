"""Tests for run_branch_version — Phase A item 6 (Task #65b).

Coverage:
- execute_branch_version_async happy path: row populated with branch_version_id.
- execute_branch_version_async unknown version → KeyError.
- execute_branch_version_async snapshot drift → SnapshotSchemaDrift with class-level constants.
- execute_branch_version_async immutable against live def edit.
- _action_run_branch_version validates required args (bvid, inputs_json, recursion_limit).
- _action_run_branch_version happy path returns run_id + branch_version_id.
- _action_run_branch_version handles SnapshotSchemaDrift via failure_class + suggested_action.
- def-based runs leave runs.branch_version_id NULL (regression check).
- Cancellation works for version-based runs (basic; parent propagation deferred to #53).
"""
from __future__ import annotations

import json

import pytest

from tinyassets.branch_versions import (
    BranchVersionContentMismatch,
    compute_content_hash,
    publish_branch_version,
)
from tinyassets.runs import (
    SnapshotSchemaDrift,
    _connect,
    execute_branch_async,
    execute_branch_version_async,
    get_run,
    initialize_runs_db,
    request_cancel,
    wait_for,
)


def _seed_branch(base_path, branch_id: str = "b1"):
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )
    from tinyassets.daemon_server import (
        initialize_author_server,
        save_branch_definition,
    )

    initialize_author_server(base_path)
    nd = NodeDefinition(node_id="n1", display_name="N1", prompt_template="do X")
    branch = BranchDefinition(
        branch_def_id=branch_id,
        name=f"Branch {branch_id}",
        graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
        edges=[EdgeDefinition(from_node="n1", to_node="END")],
        entry_point="n1",
        node_defs=[nd],
        state_schema=[],
    )
    save_branch_definition(base_path, branch_def=branch.to_dict())
    return branch


def _publish(base_path, branch) -> str:
    return publish_branch_version(
        base_path, branch.to_dict(), publisher="alice"
    ).branch_version_id


# ── SnapshotSchemaDrift class shape ───────────────────────────────────────────


class TestSnapshotSchemaDriftClass:
    def test_failure_class_constant(self):
        assert SnapshotSchemaDrift.failure_class == "snapshot_schema_drift"

    def test_suggested_action_constant(self):
        assert SnapshotSchemaDrift.suggested_action == (
            "republish at current schema version"
        )

    def test_class_attributes_readable_without_instance(self):
        # Per lead's brief — handler reads off the class without instantiating.
        assert hasattr(SnapshotSchemaDrift, "failure_class")
        assert hasattr(SnapshotSchemaDrift, "suggested_action")


# ── execute_branch_version_async ──────────────────────────────────────────────


class TestExecuteBranchVersionAsync:
    def test_rejects_snapshot_changed_by_raw_dml(self, tmp_path):
        """The stored hash is evidence; the mutable snapshot row is not authority."""
        from tinyassets.branch_versions import _connect as bv_connect

        branch = _seed_branch(tmp_path)
        bvid = _publish(tmp_path, branch)

        with bv_connect(tmp_path) as conn:
            row = conn.execute(
                "SELECT snapshot_json FROM branch_versions WHERE branch_version_id = ?",
                (bvid,),
            ).fetchone()
            snapshot = json.loads(row["snapshot_json"])
            snapshot["node_defs"][0]["prompt_template"] = "attacker-controlled prompt"
            attacker_hash = compute_content_hash(snapshot)
            conn.execute(
                "UPDATE branch_versions SET snapshot_json = ?, content_hash = ? "
                "WHERE branch_version_id = ?",
                (json.dumps(snapshot), attacker_hash, bvid),
            )

        with pytest.raises(BranchVersionContentMismatch, match="content hash"):
            execute_branch_version_async(
                tmp_path,
                branch_version_id=bvid,
                inputs={},
            )

    def test_happy_path_populates_branch_version_id(self, tmp_path):
        branch = _seed_branch(tmp_path)
        bvid = _publish(tmp_path, branch)

        outcome = execute_branch_version_async(
            tmp_path,
            branch_version_id=bvid,
            inputs={},
            actor="alice",
        )
        assert outcome.run_id

        # Wait for the background worker so the row is fully written.
        wait_for(outcome.run_id, timeout=10.0)

        with _connect(tmp_path) as conn:
            row = conn.execute(
                "SELECT branch_version_id FROM runs WHERE run_id = ?",
                (outcome.run_id,),
            ).fetchone()
        assert row["branch_version_id"] == bvid

    def test_unknown_version_raises_keyerror(self, tmp_path):
        initialize_runs_db(tmp_path)
        with pytest.raises(KeyError, match="not found"):
            execute_branch_version_async(
                tmp_path,
                branch_version_id="nonexistent-bvid@deadbeef",
                inputs={},
            )

    def test_snapshot_drift_raises_typed_error(self, tmp_path):
        """Snapshot with malformed inner structure — BranchDefinition.from_dict
        fails and the helper wraps as SnapshotSchemaDrift.

        BranchDefinition.from_dict is defensive about missing top-level
        keys (defaults to empty lists), so we plant a structurally
        broken graph_nodes list to trigger reconstruction failure.
        """
        from tinyassets.branch_versions import _connect as bv_connect
        from tinyassets.branch_versions import initialize_branch_versions_db

        initialize_branch_versions_db(tmp_path)
        bvid = "fake_branch@drift123"
        # Drift snapshot: graph_nodes contains a non-dict that
        # GraphNodeRef.from_dict cannot consume.
        snapshot = {
            "branch_def_id": "fake_branch",
            "entry_point": "n1",
            "graph_nodes": ["this should be a dict, not a string"],
            "edges": [],
            "node_defs": [],
            "state_schema": [],
        }
        content_hash = compute_content_hash(snapshot)
        bvid = f"fake_branch@{content_hash}"
        with bv_connect(tmp_path) as conn:
            conn.execute(
                """
                INSERT INTO branch_versions
                    (branch_version_id, branch_def_id, content_hash,
                     snapshot_json, notes, publisher, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bvid, "fake_branch", content_hash,
                    json.dumps(snapshot), "", "alice",
                    "2026-04-25T00:00:00+00:00",
                ),
            )

        with pytest.raises(SnapshotSchemaDrift) as exc_info:
            execute_branch_version_async(
                tmp_path, branch_version_id=bvid, inputs={},
            )
        # Confirm class-level constants surface on the raised exception type.
        assert type(exc_info.value).failure_class == "snapshot_schema_drift"
        assert "republish" in type(exc_info.value).suggested_action

    def test_immutable_against_def_edit(self, tmp_path):
        """Publish v1, edit live def, run v1 — run uses the snapshot, not
        the edited def. Critical immutability invariant."""
        from tinyassets.daemon_server import (
            get_branch_definition,
            update_branch_definition,
        )

        branch = _seed_branch(tmp_path)
        bvid = _publish(tmp_path, branch)

        # Mutate the LIVE def — change name on the canonical row.
        update_branch_definition(
            tmp_path, branch_def_id=branch.branch_def_id,
            updates={"name": "EDITED"},
        )

        # Re-fetch live def to confirm edit happened.
        live = get_branch_definition(tmp_path, branch_def_id=branch.branch_def_id)
        assert live["name"] == "EDITED"

        # Run the OLD version. The snapshot's name should still be the
        # original, even though the live def has been edited.
        outcome = execute_branch_version_async(
            tmp_path, branch_version_id=bvid, inputs={},
        )
        assert outcome.run_id
        # Note: snapshot's NAME is not retained in branch_versions.snapshot
        # (only topology fields per _canonical_snapshot). But the bvid the
        # run was tagged with is stable, so the immutability invariant we
        # actually test is that the run record carries the published bvid
        # — not whatever bvid a fresh publish_version on the edited def
        # would mint.
        wait_for(outcome.run_id, timeout=10.0)
        record = get_run(tmp_path, outcome.run_id)
        assert record is not None
        # Confirm the run row carries the ORIGINAL bvid.
        with _connect(tmp_path) as conn:
            row = conn.execute(
                "SELECT branch_version_id FROM runs WHERE run_id = ?",
                (outcome.run_id,),
            ).fetchone()
        assert row["branch_version_id"] == bvid


# ── def-based runs invariant ─────────────────────────────────────────────────


class TestDefBasedRunsLeaveBranchVersionIdNull:
    def test_execute_branch_async_does_not_populate_new_column(self, tmp_path):
        branch = _seed_branch(tmp_path)
        outcome = execute_branch_async(
            tmp_path, branch=branch, inputs={}, actor="alice",
        )
        assert outcome.run_id
        wait_for(outcome.run_id, timeout=10.0)

        with _connect(tmp_path) as conn:
            row = conn.execute(
                "SELECT branch_version_id FROM runs WHERE run_id = ?",
                (outcome.run_id,),
            ).fetchone()
        assert row["branch_version_id"] is None


# ── Cancellation (basic; parent propagation deferred per #53) ────────────────


class TestCancellationVersionRuns:
    def test_cancel_run_works_for_version_runs(self, tmp_path):
        branch = _seed_branch(tmp_path)
        bvid = _publish(tmp_path, branch)
        outcome = execute_branch_version_async(
            tmp_path, branch_version_id=bvid, inputs={},
        )
        # Cancel before worker finishes.
        request_cancel(tmp_path, outcome.run_id)
        # Wait briefly for worker to observe cancellation.
        wait_for(outcome.run_id, timeout=10.0)
        record = get_run(tmp_path, outcome.run_id)
        # Run reaches a terminal state — completed (if worker beat cancel)
        # or cancelled. Either is valid per cancellation semantics; what we
        # care about is that the run_id is respected by the cancel verb
        # without errors.
        assert record is not None
        assert record["status"] in {"completed", "cancelled", "failed"}


# ── _action_run_branch_version MCP wiring ─────────────────────────────────────


class TestActionRunBranchVersionWiring:
    def test_action_in_run_actions_registry(self):
        from tinyassets.api.runs import _RUN_ACTIONS
        assert "run_branch_version" in _RUN_ACTIONS

    def test_action_in_run_write_actions(self):
        from tinyassets.api.runs import _RUN_WRITE_ACTIONS
        assert "run_branch_version" in _RUN_WRITE_ACTIONS

    def test_missing_branch_version_id_returns_error(self):
        from tinyassets.api.runs import _action_run_branch_version
        result = json.loads(_action_run_branch_version({}))
        assert "error" in result
        assert "branch_version_id" in result["error"]

    def test_invalid_inputs_json_returns_error(self):
        from tinyassets.api.runs import _action_run_branch_version
        result = json.loads(_action_run_branch_version({
            "branch_version_id": "x@y",
            "inputs_json": "not valid json {",
        }))
        assert "error" in result
        assert "inputs_json" in result["error"]

    def test_inputs_json_must_be_object(self):
        from tinyassets.api.runs import _action_run_branch_version
        result = json.loads(_action_run_branch_version({
            "branch_version_id": "x@y",
            "inputs_json": "[1, 2, 3]",  # array, not object
        }))
        assert "error" in result
        assert "JSON object" in result["error"]

    def test_recursion_limit_must_be_integer(self):
        from tinyassets.api.runs import _action_run_branch_version
        result = json.loads(_action_run_branch_version({
            "branch_version_id": "x@y",
            "recursion_limit_override": "not-a-number",
        }))
        assert "error" in result
        assert "integer" in result["error"]

    def test_recursion_limit_out_of_range(self):
        from tinyassets.api.runs import _action_run_branch_version
        result = json.loads(_action_run_branch_version({
            "branch_version_id": "x@y",
            "recursion_limit_override": "1",  # below 10
        }))
        assert "error" in result
        assert "out of range" in result["error"]

    def test_unknown_branch_version_id_returns_error(self, tmp_path, monkeypatch):
        """Live invocation against an unknown bvid surfaces KeyError as JSON error."""
        from tinyassets.api import engine_helpers as eh
        from tinyassets.api import runs as runs_mod
        monkeypatch.setattr(runs_mod, "_base_path", lambda: tmp_path)
        monkeypatch.setattr(eh, "_current_actor", lambda: "alice")
        # Initialize the runs DB so _ensure_runs_recovery doesn't blow up.
        initialize_runs_db(tmp_path)

        result = json.loads(runs_mod._action_run_branch_version({
            "branch_version_id": "totally-fake@deadbeef",
        }))
        assert "error" in result
        assert "not found" in result["error"]


# ── Schema-drift handler-level test ──────────────────────────────────────────


class TestActionHandlesSnapshotDrift:
    def test_handler_returns_failure_class_and_suggested_action(
        self, tmp_path, monkeypatch
    ):
        """Plant a drifted snapshot, invoke the handler, confirm the JSON
        response carries failure_class + suggested_action from the class."""
        from tinyassets.api import engine_helpers as eh
        from tinyassets.api import runs as runs_mod
        from tinyassets.branch_versions import _connect as bv_connect
        from tinyassets.branch_versions import initialize_branch_versions_db

        monkeypatch.setattr(eh, "_current_actor", lambda: "alice")
        monkeypatch.setattr(runs_mod, "_base_path", lambda: tmp_path)
        initialize_runs_db(tmp_path)

        initialize_branch_versions_db(tmp_path)
        # Same malformed-graph_nodes pattern as the helper-level drift test.
        snapshot = {
            "branch_def_id": "drifted",
            "entry_point": "n1",
            "graph_nodes": ["should be dict"],
            "edges": [],
            "node_defs": [],
            "state_schema": [],
        }
        content_hash = compute_content_hash(snapshot)
        bvid = f"drifted@{content_hash}"
        with bv_connect(tmp_path) as conn:
            conn.execute(
                """
                INSERT INTO branch_versions
                    (branch_version_id, branch_def_id, content_hash,
                     snapshot_json, notes, publisher, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bvid, "drifted", content_hash,
                    json.dumps(snapshot), "", "alice",
                    "2026-04-25T00:00:00+00:00",
                ),
            )

        result = json.loads(runs_mod._action_run_branch_version({
            "branch_version_id": bvid,
        }))
        assert result.get("failure_class") == "snapshot_schema_drift"
        assert "republish" in result.get("suggested_action", "")


class TestActionHandlesContentMismatch:
    def test_handler_returns_structured_failure(self, tmp_path, monkeypatch):
        from tinyassets.api import engine_helpers as eh
        from tinyassets.api import runs as runs_mod
        from tinyassets.branch_versions import _connect as bv_connect

        monkeypatch.setattr(eh, "_current_actor", lambda: "alice")
        monkeypatch.setattr(runs_mod, "_base_path", lambda: tmp_path)
        initialize_runs_db(tmp_path)
        bvid = _publish(tmp_path, _seed_branch(tmp_path))

        with bv_connect(tmp_path) as conn:
            row = conn.execute(
                "SELECT snapshot_json FROM branch_versions WHERE branch_version_id = ?",
                (bvid,),
            ).fetchone()
            snapshot = json.loads(row["snapshot_json"])
            snapshot["entry_point"] = "attacker-node"
            conn.execute(
                "UPDATE branch_versions SET snapshot_json = ?, content_hash = ? "
                "WHERE branch_version_id = ?",
                (json.dumps(snapshot), compute_content_hash(snapshot), bvid),
            )

        result = json.loads(runs_mod._action_run_branch_version({
            "branch_version_id": bvid,
        }))

        assert result["failure_class"] == "branch_version_content_mismatch"
        assert "republish" in result["suggested_action"]
