from __future__ import annotations

from pathlib import Path

from scripts.check_background_authority_inventory import (
    CANONICAL_READ_INTERFACES,
    EXPECTED_SENSITIVE_CALL_SITES,
    REQUIRED_BACKGROUND_ROOTS,
    SENSITIVE_EXECUTION_CALLS,
    CallSite,
    scan_python_calls,
    validate_inventory,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_current_repository_matches_reviewed_background_authority_inventory() -> None:
    assert validate_inventory(REPO_ROOT) == []


def test_scanner_detects_a_new_sensitive_execution_call(tmp_path: Path) -> None:
    source = tmp_path / "new_root.py"
    source.write_text(
        "def newly_added_background_root():\n"
        "    return execute_branch_async('branch-id')\n",
        encoding="utf-8",
    )

    assert scan_python_calls(source, SENSITIVE_EXECUTION_CALLS, relative_to=tmp_path) == {
        CallSite(
            path="new_root.py",
            function="newly_added_background_root",
            callee="execute_branch_async",
        )
    }


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


def test_sensitive_call_manifest_is_nonempty_and_duplicate_free() -> None:
    assert EXPECTED_SENSITIVE_CALL_SITES
    assert len(EXPECTED_SENSITIVE_CALL_SITES) == len(
        set(EXPECTED_SENSITIVE_CALL_SITES)
    )
