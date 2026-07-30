"""Fail CI when a background Branch execution root escapes the reviewed inventory.

This checker is intentionally dark: it does not authorize execution or choose a
storage backend.  It makes two review obligations executable:

* every call to a Branch execution/queue boundary is an exact reviewed callsite;
* every source family and canonical read owner named by the OpenSpec target is
  still present at its recorded source marker.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True, order=True)
class CallSite:
    path: str
    function: str
    callee: str
    count: int = 1


@dataclass(frozen=True)
class SourceReference:
    path: str
    marker: str
    state: str = "implemented"


SENSITIVE_EXECUTION_CALLS = frozenset(
    {
        "_action_run_branch_version",
        "_execute_branch_core",
        "_run_fn",
        "append_task",
        "append_task_capped",
        "claim_task",
        "dispatch_selector",
        "execute_branch",
        "execute_branch_async",
        "execute_branch_version_async",
        "recover_expired",
        "recover_in_flight_runs",
        "resume_run",
        "stream",
    }
)

# Populated from the reviewed current-main scan.  Any addition/removal is a
# review event: update the audit and this exact set together.
EXPECTED_SENSITIVE_CALL_SITES: tuple[CallSite, ...] = (
    CallSite(
        "fantasy_daemon/__main__.py",
        "DaemonController._try_execute_soul_loop",
        "execute_branch",
    ),
    CallSite("fantasy_daemon/__main__.py", "_try_dispatcher_pick", "claim_task"),
    CallSite(
        "fantasy_daemon/__main__.py",
        "_try_execute_claimed_branch_task",
        "execute_branch",
    ),
    CallSite(
        "fantasy_daemon/__main__.py",
        "DaemonController._run_graph",
        "stream",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/"
        "runtime/tinyassets/api/market.py",
        "_action_goal_run_canonical",
        "_action_run_branch_version",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/"
        "runtime/tinyassets/api/quality_leaderboard.py",
        "build_quality_leaderboard",
        "dispatch_selector",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/runs.py",
        "_action_resume_run",
        "resume_run",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/runs.py",
        "_action_run_branch",
        "execute_branch_async",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/runs.py",
        "_action_run_branch_version",
        "execute_branch_version_async",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/runs.py",
        "_ensure_runs_recovery",
        "recover_in_flight_runs",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/"
        "runtime/tinyassets/api/selector_dispatch.py",
        "dispatch_selector",
        "_execute_branch_core",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/"
        "runtime/tinyassets/api/universe.py",
        "_action_submit_request",
        "append_task",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/"
        "runtime/tinyassets/bug_investigation.py",
        "enqueue_investigation_request",
        "append_task",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/"
        "runtime/tinyassets/dispatcher.py",
        "run_branch_task_producers_into_queue",
        "append_task",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/"
        "runtime/tinyassets/graph_compiler.py",
        "_build_invoke_branch_node._node_fn",
        "execute_branch",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/"
        "runtime/tinyassets/graph_compiler.py",
        "_build_invoke_branch_node._node_fn",
        "execute_branch_async",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/"
        "runtime/tinyassets/graph_compiler.py",
        "_build_invoke_branch_version_node._node_fn",
        "execute_branch_version_async",
        count=2,
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/"
        "runtime/tinyassets/graph_compiler.py",
        "_node_enqueue_branch_run",
        "append_task_capped",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/runs.py",
        "execute_branch_async",
        "_execute_branch_core",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/runs.py",
        "execute_branch_version_async",
        "_execute_branch_core",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/"
        "runtime/tinyassets/scheduler.py",
        "Scheduler._dispatch_event",
        "_run_fn",
    ),
    CallSite(
        "packaging/claude-plugin/plugins/tinyassets-universe-server/"
        "runtime/tinyassets/scheduler.py",
        "Scheduler._maybe_fire_schedule",
        "_run_fn",
    ),
    CallSite(
        "tinyassets/api/market.py",
        "_action_goal_run_canonical",
        "_action_run_branch_version",
    ),
    CallSite(
        "tinyassets/api/quality_leaderboard.py",
        "build_quality_leaderboard",
        "dispatch_selector",
    ),
    CallSite("tinyassets/api/runs.py", "_action_resume_run", "resume_run"),
    CallSite("tinyassets/api/runs.py", "_action_run_branch", "execute_branch_async"),
    CallSite(
        "tinyassets/api/runs.py",
        "_action_run_branch_version",
        "execute_branch_version_async",
    ),
    CallSite(
        "tinyassets/api/runs.py",
        "_ensure_runs_recovery",
        "recover_in_flight_runs",
    ),
    CallSite(
        "tinyassets/api/selector_dispatch.py",
        "dispatch_selector",
        "_execute_branch_core",
    ),
    CallSite("tinyassets/api/universe.py", "_action_submit_request", "append_task"),
    CallSite(
        "tinyassets/bug_investigation.py",
        "enqueue_investigation_request",
        "append_task",
    ),
    CallSite(
        "tinyassets/dispatcher.py",
        "run_branch_task_producers_into_queue",
        "append_task",
    ),
    CallSite(
        "tinyassets/graph_compiler.py",
        "_build_invoke_branch_node._node_fn",
        "execute_branch",
    ),
    CallSite(
        "tinyassets/graph_compiler.py",
        "_build_invoke_branch_node._node_fn",
        "execute_branch_async",
    ),
    CallSite(
        "tinyassets/graph_compiler.py",
        "_build_invoke_branch_version_node._node_fn",
        "execute_branch_version_async",
        count=2,
    ),
    CallSite(
        "tinyassets/graph_compiler.py",
        "_node_enqueue_branch_run",
        "append_task_capped",
    ),
    CallSite("tinyassets/runs.py", "execute_branch_async", "_execute_branch_core"),
    CallSite(
        "tinyassets/runs.py",
        "execute_branch_version_async",
        "_execute_branch_core",
    ),
    CallSite(
        "tinyassets/scheduler.py",
        "Scheduler._dispatch_event",
        "_run_fn",
    ),
    CallSite(
        "tinyassets/scheduler.py",
        "Scheduler._maybe_fire_schedule",
        "_run_fn",
    ),
)


REQUIRED_BACKGROUND_ROOTS: Mapping[str, tuple[SourceReference, ...]] = {
    "schedule_and_event": (
        SourceReference(
            "tinyassets/scheduler.py",
            'self._run_fn(row["branch_def_id"], actor, inputs, run_name)',
        ),
        SourceReference(
            "tinyassets/scheduler.py",
            'self._run_fn(sub["branch_def_id"], actor, inputs, run_name)',
        ),
    ),
    "goal_subscription": (
        SourceReference("tinyassets/subscriptions.py", "def subscribe("),
        SourceReference("tinyassets/scheduler.py", "def register_subscription("),
    ),
    "soul_and_compiled_cycle": (
        SourceReference(
            "fantasy_daemon/__main__.py",
            "read_legacy_premise(output_dir).strip()",
        ),
        SourceReference(
            "fantasy_daemon/__main__.py",
            "compiled.stream(initial_state, config=config)",
        ),
        SourceReference("fantasy_daemon/branches/universe_cycle.yaml", "graph_nodes:"),
    ),
    "request_admission": (
        SourceReference("tinyassets/storage/request_admissions.py", "class RequestAdmissionStore:"),
        SourceReference("tinyassets/api/universe.py", "def _action_submit_request("),
    ),
    "goal_pool_and_paid_market": (
        SourceReference("tinyassets/producers/goal_pool.py", "class GoalPoolProducer:"),
        SourceReference("tinyassets/producers/node_bid.py", "class NodeBidProducer:"),
    ),
    "branch_task_and_graph_enqueue": (
        SourceReference("tinyassets/branch_tasks.py", "def append_task("),
        SourceReference("tinyassets/graph_compiler.py", "def _node_enqueue_branch_run("),
    ),
    "direct_live_and_versioned_run": (
        SourceReference("tinyassets/runs.py", "def execute_branch_async("),
        SourceReference("tinyassets/runs.py", "def execute_branch_version_async("),
        SourceReference("tinyassets/runs.py", "def _execute_branch_core("),
    ),
    "resume_and_recovery": (
        SourceReference("tinyassets/runs.py", "def resume_run("),
        SourceReference("tinyassets/runs.py", "def recover_in_flight_runs("),
        SourceReference("tinyassets/branch_tasks.py", "def recover_claimed_tasks("),
        SourceReference("tinyassets/branch_tasks_v2.py", "    def recover_expired("),
    ),
    "request_actor_boundary": (
        SourceReference("tinyassets/api/permissions.py", "def current_request_actor_id("),
        SourceReference("tinyassets/api/engine_helpers.py", "def _current_actor("),
    ),
    "daemon_cloud_and_distributed_worker": (
        SourceReference("fantasy_daemon/__main__.py", "def _try_execute_claimed_branch_task("),
        SourceReference("tinyassets/cloud_worker.py", "def run_supervisor("),
        SourceReference("tinyassets/execution_authority/records.py", "class ExecutionGrantV1:"),
    ),
    "selector_leaderboard_and_market_delegate": (
        SourceReference("tinyassets/api/selector_dispatch.py", "def dispatch_selector("),
        SourceReference(
            "tinyassets/api/quality_leaderboard.py",
            "def recommend_parent_for_fork(",
        ),
        SourceReference("tinyassets/api/market.py", "def _action_goal_run_canonical("),
    ),
    "retired_wiki_forwarding": (
        SourceReference(
            "tinyassets/bug_investigation.py",
            "def enqueue_investigation_request(",
            state="retirement-only",
        ),
        SourceReference(
            "tinyassets/api/wiki.py",
            "def _wiki_file_bug(",
            state="filing-only-negative",
        ),
        SourceReference(
            "packaging/claude-plugin/plugins/tinyassets-universe-server/"
            "runtime/tinyassets/api/wiki.py",
            "def _wiki_file_bug(",
            state="filing-only-negative",
        ),
    ),
}


CANONICAL_READ_INTERFACES: Mapping[str, tuple[SourceReference, ...]] = {
    "identity": (
        SourceReference("tinyassets/api/permissions.py", "def current_request_actor_id("),
    ),
    "acl": (SourceReference("tinyassets/api/permissions.py", "def universe_access_allows("),),
    "branch": (
        SourceReference("tinyassets/api/branches.py", "def _resolve_readable_branch("),
        SourceReference("tinyassets/api/branches.py", "def _resolve_readable_version("),
    ),
    "branch_write_author": (
        SourceReference("tinyassets/api/branches.py", "def _branch_authorized("),
    ),
    "daemon": (
        SourceReference("tinyassets/daemon_registry.py", "def get_daemon("),
        SourceReference("tinyassets/daemon_registry.py", "def list_runtime_instances("),
    ),
    "run": (
        SourceReference("tinyassets/api/runs.py", "def _run_read_allowed("),
        SourceReference("tinyassets/api/runs.py", "def _run_write_allowed("),
    ),
    "request_admission": (
        SourceReference("tinyassets/storage/request_admissions.py", "class RequestAdmissionStore:"),
    ),
    "filing_only_wiki_negative": (
        SourceReference("tinyassets/api/wiki.py", "def _wiki_file_bug("),
        SourceReference(
            "openspec/changes/retire-cheat-loop/specs/wiki-commons/spec.md",
            "no trigger receipt, branch task, run, or investigation section",
        ),
    ),
    "goal_subscription": (
        SourceReference("tinyassets/subscriptions.py", "def list_subscriptions("),
        SourceReference("tinyassets/scheduler.py", "def list_scheduler_subscriptions("),
    ),
    "paid_market_acceptance": (
        SourceReference(
            "openspec/changes/paid-market-track-e-wave-2-transport/specs/"
            "paid-market-economy/spec.md",
            "Acceptance SHALL revalidate",
            state="contract-only",
        ),
    ),
    "queue": (
        SourceReference("tinyassets/branch_tasks.py", "def read_queue("),
        SourceReference("tinyassets/branch_tasks_v2.py", "class Epoch2OperationalRead:"),
    ),
    "b2": (
        SourceReference("tinyassets/execution_authority/records.py", "class ExecutionGrantV1:"),
        SourceReference(
            "tinyassets/execution_authority/records.py",
            "class RecordVerifier:",
            state="contract-only",
        ),
    ),
    "provider_work": (
        SourceReference(
            "openspec/changes/constrain-set-engine-provider-authority/specs/"
            "provider-routing/spec.md",
            "provider work holds",
            state="contract-only",
        ),
    ),
    "provider_attempt": (
        SourceReference(
            "openspec/changes/provider-attempt-receipts/specs/provider-routing/spec.md",
            "provider-attempt receipt",
            state="contract-only",
        ),
    ),
}


_SCAN_ROOTS = (
    "tinyassets",
    "fantasy_daemon",
    "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets",
)
_WIKI_NEGATIVE_PATHS = (
    "tinyassets/api/wiki.py",
    "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/wiki.py",
)
_WIKI_FORBIDDEN_CALLS = frozenset(
    {
        "_maybe_enqueue_investigation",
        "append_task",
        "append_task_capped",
        "enqueue_investigation_request",
        "execute_branch_async",
        "execute_branch_version_async",
    }
)


def _callee_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


class _CallVisitor(ast.NodeVisitor):
    def __init__(self, names: frozenset[str]) -> None:
        self._names = names
        self._scope: list[str] = []
        self._aliases: dict[str, str] = {}
        self.calls: Counter[tuple[str, str]] = Counter()

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for imported in node.names:
            if imported.name in self._names:
                self._aliases[imported.asname or imported.name] = imported.name

    def _record_assigned_alias(self, target: ast.expr, value: ast.expr) -> None:
        if not isinstance(target, ast.Name):
            return
        canonical = None
        if isinstance(value, ast.Name):
            canonical = self._aliases.get(value.id, value.id)
        elif isinstance(value, ast.Attribute):
            canonical = value.attr
        if canonical in self._names:
            self._aliases[target.id] = canonical

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._record_assigned_alias(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._record_assigned_alias(node.target, node.value)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        callee = _callee_name(node)
        if isinstance(node.func, ast.Name):
            callee = self._aliases.get(node.func.id, callee)
        if callee in self._names:
            self.calls[(".".join(self._scope) or "<module>", callee)] += 1
        self.generic_visit(node)


def scan_python_calls(
    path: Path,
    names: frozenset[str],
    *,
    relative_to: Path,
) -> set[CallSite]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    visitor = _CallVisitor(names)
    visitor.visit(tree)
    relative = path.relative_to(relative_to).as_posix()
    return {
        CallSite(path=relative, function=function, callee=callee, count=count)
        for (function, callee), count in visitor.calls.items()
    }


def collect_sensitive_call_sites(
    repo_root: Path,
    *,
    scan_roots: Sequence[str] = _SCAN_ROOTS,
) -> set[CallSite]:
    observed: set[CallSite] = set()
    for root_name in scan_roots:
        root = repo_root / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            observed.update(
                scan_python_calls(
                    path,
                    SENSITIVE_EXECUTION_CALLS,
                    relative_to=repo_root,
                )
            )
    return observed


def _all_references() -> Iterable[tuple[str, SourceReference]]:
    for group, refs in REQUIRED_BACKGROUND_ROOTS.items():
        for ref in refs:
            yield f"root:{group}", ref
    for group, refs in CANONICAL_READ_INTERFACES.items():
        for ref in refs:
            yield f"read:{group}", ref


def compare_call_sites(
    observed: Iterable[CallSite],
    expected: Iterable[CallSite],
) -> list[str]:
    observed_set = set(observed)
    expected_set = set(expected)
    errors = [
        f"unreviewed sensitive callsite: {callsite}"
        for callsite in sorted(observed_set - expected_set)
    ]
    errors.extend(
        f"stale sensitive callsite: {callsite}" for callsite in sorted(expected_set - observed_set)
    )
    return errors


def validate_inventory(repo_root: Path) -> list[str]:
    observed = collect_sensitive_call_sites(repo_root)
    errors = compare_call_sites(observed, EXPECTED_SENSITIVE_CALL_SITES)

    for owner, ref in _all_references():
        path = repo_root / ref.path
        if not path.is_file():
            errors.append(f"{owner} missing source: {ref.path}")
            continue
        text = path.read_text(encoding="utf-8")
        if ref.marker not in text:
            errors.append(f"{owner} missing marker in {ref.path}: {ref.marker!r}")

    for relative in _WIKI_NEGATIVE_PATHS:
        path = repo_root / relative
        for callsite in sorted(
            scan_python_calls(path, _WIKI_FORBIDDEN_CALLS, relative_to=repo_root)
        ):
            errors.append(f"filing-only wiki gained execution call: {callsite}")
    return errors


def _format_calls(calls: Sequence[CallSite]) -> str:
    return "\n".join(
        f"{call.path}::{call.function} -> {call.callee} [count={call.count}]"
        for call in sorted(calls)
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--print-observed", action="store_true")
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    if args.print_observed:
        print(_format_calls(tuple(collect_sensitive_call_sites(root))))
        return 0
    errors = validate_inventory(root)
    if errors:
        print("\n".join(errors))
        return 1
    print("background authority inventory closure: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
