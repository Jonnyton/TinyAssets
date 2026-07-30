from __future__ import annotations

from pathlib import Path

from scripts.check_background_authority_inventory import (
    CANONICAL_READ_INTERFACES,
    EXPECTED_SENSITIVE_CALL_SITES,
    REQUIRED_BACKGROUND_ROOTS,
    SENSITIVE_EXECUTION_CALLS,
    CallSite,
    collect_sensitive_call_sites,
    compare_call_sites,
    scan_python_calls,
    validate_inventory,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_current_repository_matches_reviewed_background_authority_inventory() -> None:
    assert validate_inventory(REPO_ROOT) == []


def test_scanner_detects_a_new_sensitive_execution_call(tmp_path: Path) -> None:
    source = tmp_path / "new_root.py"
    source.write_text(
        "def newly_added_background_root():\n    return execute_branch_async('branch-id')\n",
        encoding="utf-8",
    )

    assert scan_python_calls(source, SENSITIVE_EXECUTION_CALLS, relative_to=tmp_path) == {
        CallSite(
            path="new_root.py",
            function="newly_added_background_root",
            callee="execute_branch_async",
        )
    }


def test_scanner_counts_duplicate_calls_in_one_function(tmp_path: Path) -> None:
    source = tmp_path / "duplicate_root.py"
    source.write_text(
        "def duplicated_background_root():\n"
        "    execute_branch('first')\n"
        "    return execute_branch('second')\n",
        encoding="utf-8",
    )

    assert scan_python_calls(source, SENSITIVE_EXECUTION_CALLS, relative_to=tmp_path) == {
        CallSite(
            path="duplicate_root.py",
            function="duplicated_background_root",
            callee="execute_branch",
            count=2,
        )
    }


def test_scanner_resolves_imported_sensitive_alias(tmp_path: Path) -> None:
    source = tmp_path / "aliased_root.py"
    source.write_text(
        "from tinyassets.runs import execute_branch as run_now\n\n"
        "def aliased_background_root():\n"
        "    return run_now('branch-id')\n",
        encoding="utf-8",
    )

    assert scan_python_calls(source, SENSITIVE_EXECUTION_CALLS, relative_to=tmp_path) == {
        CallSite(
            path="aliased_root.py",
            function="aliased_background_root",
            callee="execute_branch",
        )
    }


def test_scanner_resolves_assigned_sensitive_alias(tmp_path: Path) -> None:
    source = tmp_path / "assigned_alias_root.py"
    source.write_text(
        "import tinyassets.runs\n\n"
        "run_now = tinyassets.runs.execute_branch\n\n"
        "def aliased_background_root():\n"
        "    return run_now('branch-id')\n",
        encoding="utf-8",
    )

    assert scan_python_calls(source, SENSITIVE_EXECUTION_CALLS, relative_to=tmp_path) == {
        CallSite(
            path="assigned_alias_root.py",
            function="aliased_background_root",
            callee="execute_branch",
        )
    }


def test_repository_scan_detects_an_unreviewed_root(tmp_path: Path) -> None:
    package = tmp_path / "tinyassets"
    package.mkdir()
    source = package / "new_root.py"
    source.write_text(
        "def newly_added_background_root():\n    return execute_branch_async('branch-id')\n",
        encoding="utf-8",
    )

    observed = collect_sensitive_call_sites(tmp_path, scan_roots=("tinyassets",))
    assert observed == {
        CallSite(
            path="tinyassets/new_root.py",
            function="newly_added_background_root",
            callee="execute_branch_async",
        )
    }
    assert compare_call_sites(observed, ()) == [
        "unreviewed sensitive callsite: "
        "CallSite(path='tinyassets/new_root.py', "
        "function='newly_added_background_root', "
        "callee='execute_branch_async', count=1)"
    ]


def test_inventory_covers_every_required_source_family() -> None:
    assert set(REQUIRED_BACKGROUND_ROOTS) == {
        "schedule_and_event",
        "goal_subscription",
        "soul_and_compiled_cycle",
        "request_admission",
        "goal_pool_and_paid_market",
        "branch_task_and_graph_enqueue",
        "direct_live_and_versioned_run",
        "resume_and_recovery",
        "request_actor_boundary",
        "daemon_cloud_and_distributed_worker",
        "selector_leaderboard_and_market_delegate",
        "retired_wiki_forwarding",
    }
    assert all(REQUIRED_BACKGROUND_ROOTS.values())


def test_inventory_records_canonical_read_interfaces_without_new_truth() -> None:
    assert set(CANONICAL_READ_INTERFACES) == {
        "identity",
        "acl",
        "branch",
        "branch_write_author",
        "daemon",
        "run",
        "request_admission",
        "filing_only_wiki_negative",
        "goal_subscription",
        "paid_market_acceptance",
        "queue",
        "b2",
        "provider_work",
        "provider_attempt",
    }
    assert all(CANONICAL_READ_INTERFACES.values())

    assert {ref.marker for ref in CANONICAL_READ_INTERFACES["branch"]} == {
        "def _resolve_readable_branch(",
        "def _resolve_readable_version(",
    }
    assert {ref.marker for ref in CANONICAL_READ_INTERFACES["daemon"]} == {
        "def get_daemon(",
        "def list_runtime_instances(",
    }
    assert any(
        ref.marker == "class RecordVerifier:" and ref.state == "contract-only"
        for ref in CANONICAL_READ_INTERFACES["b2"]
    )


def test_inventory_closes_indirect_and_packaged_execution_boundaries() -> None:
    observed = set(EXPECTED_SENSITIVE_CALL_SITES)
    assert (
        CallSite(
            "fantasy_daemon/__main__.py",
            "DaemonController._run_graph",
            "stream",
        )
        in observed
    )
    assert (
        CallSite(
            "tinyassets/scheduler.py",
            "Scheduler._maybe_fire_schedule",
            "_run_fn",
        )
        in observed
    )
    assert (
        CallSite(
            "packaging/claude-plugin/plugins/tinyassets-universe-server/"
            "runtime/tinyassets/graph_compiler.py",
            "_build_invoke_branch_node._node_fn",
            "execute_branch",
        )
        in observed
    )


def test_sensitive_call_manifest_is_nonempty_and_duplicate_free() -> None:
    assert EXPECTED_SENSITIVE_CALL_SITES
    assert len(EXPECTED_SENSITIVE_CALL_SITES) == len(set(EXPECTED_SENSITIVE_CALL_SITES))
