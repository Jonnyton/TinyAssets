"""Authenticated persisted insertion/invocation, never packet-selected budget."""

# ruff: noqa: F811 -- imported pytest fixtures
import pytest

from tests.test_delivery_node_rpc import node_env  # noqa: F401
from tests.test_delivery_public import linked  # noqa: F401
from tests.test_receiver_links import env  # noqa: F401
from tests.workspace_family_test_support import (
    managed_runtime,  # noqa: F401
    simulated_managed_runtime,
)
from tinyassets import runs
from tinyassets import workspace_family as family


def _create(base, **kwargs):
    params = dict(
        branch_def_id="branch",
        thread_id="",
        inputs={},
        actor="actor",
        owner_user_id="owner",
        queue_universe_id="universe",
    )
    params.update(kwargs)
    with simulated_managed_runtime(base):
        return runs.create_run(base, **params)


def test_authenticated_root_insert_assigns_itself_and_ignores_packet(tmp_path):
    run = _create(tmp_path, inputs={"workspace_budget_root_run_id": "someone-else"})
    with runs._connect(tmp_path) as conn:
        row = conn.execute(
            "SELECT workspace_budget_root_run_id,workspace_budget_epoch,"
            "workspace_budget_closing_reason FROM runs WHERE run_id=?",
            (run,),
        ).fetchone()
    assert tuple(row) == (run, 1, "")


def test_legacy_daemon_owner_fallback_is_not_family_authority(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "_resolve_owner_user_id", lambda *a: "owner")
    run = _create(tmp_path, owner_user_id=None)
    with runs._connect(tmp_path) as conn:
        row = conn.execute(
            "SELECT workspace_budget_root_run_id FROM runs WHERE run_id=?", (run,)
        ).fetchone()
    assert row[0] is None


def test_child_inherits_from_live_immediate_parent_after_original_root_completed(tmp_path):
    root = _create(tmp_path)
    runs.update_run_status(tmp_path, root, status="running")
    parent = family.execution_member(tmp_path, root)
    child = _create(tmp_path, _workspace_parent=parent)
    runs.update_run_status(tmp_path, child, status="running")
    runs.update_run_status(tmp_path, root, status="completed")
    child_context = family.execution_member(tmp_path, child)
    grandchild = _create(tmp_path, _workspace_parent=child_context)
    with runs._connect(tmp_path) as conn:
        row = conn.execute(
            "SELECT workspace_budget_root_run_id,workspace_budget_epoch FROM runs WHERE run_id=?",
            (grandchild,),
        ).fetchone()
    assert tuple(row) == (root, 1)
    with pytest.raises(family.FamilyRefused, match="running"):
        _create(tmp_path, _workspace_parent=parent)


def test_child_copy_is_atomic_with_owner_refusal(tmp_path):
    root = _create(tmp_path)
    runs.update_run_status(tmp_path, root, status="running")
    parent = family.execution_member(tmp_path, root)
    with pytest.raises(family.FamilyRefused, match="identity"):
        _create(tmp_path, owner_user_id="other", _workspace_parent=parent)
    with runs._connect(tmp_path) as conn:
        assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 1


def test_broken_family_row_never_uses_legacy_resume_fallback(tmp_path):
    root = _create(tmp_path)
    runs.update_run_status(tmp_path, root, status="running")
    with runs._connect(tmp_path) as conn:
        conn.execute("UPDATE runs SET workspace_budget_epoch=NULL WHERE run_id=?", (root,))
    with pytest.raises(family.FamilyRefused, match="unknown"):
        family.execution_member(tmp_path, root)


def test_compile_snapshot_does_not_authorize_queued_parent(tmp_path):
    root = _create(tmp_path)
    parent = family.execution_member(tmp_path, root, for_compile=True)
    with pytest.raises(family.FamilyRefused, match="running"):
        _create(tmp_path, _workspace_parent=parent)
    runs.update_run_status(tmp_path, root, status="running")
    child = _create(tmp_path, _workspace_parent=parent)
    assert child != root


def test_parallel_child_insertion_waits_for_short_family_transaction(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    root = _create(tmp_path)
    runs.update_run_status(tmp_path, root, status="running")
    parent = family.execution_member(tmp_path, root)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with family.try_family_fence(tmp_path, root) as fence:
            assert fence is not None
            # Release the fence before collecting the result, never wait while
            # holding it. The child must serialize rather than fail spuriously.
            future = pool.submit(_create, tmp_path, _workspace_parent=parent)
            import time

            time.sleep(0.1)
            assert not future.done()
        assert future.result(timeout=5) != root


@pytest.mark.parametrize("owner", [None, "owner"])
def test_legacy_child_never_mints_a_fresh_quota(tmp_path, owner, monkeypatch):
    monkeypatch.setattr(runs, "_resolve_owner_user_id", lambda *a: "owner")
    child = _create(tmp_path, owner_user_id=owner, _workspace_parent=family.UNMANAGED_PARENT)
    assert family.execution_member(tmp_path, child, for_compile=True) is None


def test_compile_context_broken_association_escapes_actor_fallback(tmp_path):
    from tinyassets.branches import BranchDefinition

    root = _create(tmp_path)
    with runs._connect(tmp_path) as conn:
        conn.execute("UPDATE runs SET workspace_budget_epoch=NULL WHERE run_id=?", (root,))
    with pytest.raises(family.FamilyRefused, match="unknown"):
        runs._execution_context_for_run(tmp_path, root, BranchDefinition(), fallback_actor="owner")


def test_actual_nested_graph_uses_same_family(node_env):
    from tests.test_delivery_node_rpc import (
        _rows,
        test_nested_invoke_uses_child_branch_run_and_inherited_owner,
    )

    # Existing full compiler -> child launch -> real RPC proof, augmented with
    # persisted budget assertions, not a mock accepting a forwarded keyword.
    with simulated_managed_runtime(node_env[0]):
        test_nested_invoke_uses_child_branch_run_and_inherited_owner(node_env)
    base = node_env[0]
    child_id = _rows(base)[0]["source_run_id"]
    with runs._connect(base) as conn:
        child = conn.execute("SELECT * FROM runs WHERE run_id=?", (child_id,)).fetchone()
        root = conn.execute(
            "SELECT * FROM runs WHERE run_id=?", (child["workspace_budget_root_run_id"],)
        ).fetchone()
    assert child["run_id"] != root["run_id"]
    assert child["workspace_budget_epoch"] == root["workspace_budget_epoch"] == 1
    assert root["branch_def_id"] == "b-parent"
