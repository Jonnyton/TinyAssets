"""Run-execution subsystem — extracted from workflow/universe_server.py
(Task #11 — decomp Step 4).

Contains the run dispatcher (_RUN_ACTIONS), 16 action handlers, and the
failure-classification taxonomy. The MCP tool registration stays in
``workflow/universe_server.py`` (Pattern A2 from the decomp plan); this
module is plain functions consumed via the ``extensions()`` MCP tool.

Public surface (back-compat re-exported via ``workflow.universe_server``):
    _RUN_ACTIONS               : action dispatch table (16 entries)
    _RUN_WRITE_ACTIONS         : frozenset of write actions for ledger gating
    _dispatch_run_action       : ledger-aware action dispatcher
    _action_*                  : 16 individual handlers
    _classify_run_error        : failure-class router (also test-imported)
    _classify_run_outcome_error: outcome-error parser (also test-imported)
    _ensure_runs_recovery      : startup-recovery idempotent gate
    _build_failure_taxonomy    : taxonomy lazy-init
    _FAILURE_TAXONOMY          : module-level taxonomy state
    _run_mermaid_from_events   : mermaid renderer for run streams
    _branch_name_for_run       : human-name lookup for run records
    _compose_run_snapshot      : run-record → response-shape adapter

Cross-module note: ``_append_global_ledger``, ``_truncate``, ``_current_actor``,
``_mermaid_label``, ``_mermaid_node_id``, ``_resolve_branch_id``, ``logger`` all
live in ``workflow.universe_server`` (universe-engine territory) and are
lazy-imported inside the functions that use them. This avoids the load-time
cycle (universe_server back-compat-imports symbols from this module).

Source ranges extracted (current line numbers, post-#10 land):
- L7016–7982 — Phase 3 banner + helpers + 9 primary handlers
- L8053–8221 — query_runs + routing_evidence + memory_scope_status
- L8473–8757 — branch_version + rollback handlers + dispatch table + dispatcher
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from workflow.api.helpers import (
    _base_path,
    _default_universe,
    _read_text,
    _universe_dir,
)

logger = logging.getLogger("universe_server.runs")

ENV_CAPABILITIES_VAR = "UNIVERSE_SERVER_CAPABILITIES"


def _current_actor_grants() -> tuple[str, ...]:
    raw = os.environ.get(ENV_CAPABILITIES_VAR, "")
    return tuple(part for part in raw.replace(",", " ").split() if part)


def _current_actor_has_capability(action: str) -> bool:
    from workflow.api.engine_helpers import _current_actor
    from workflow.auth.provider import resolve_permission

    return resolve_permission(
        actor_id=_current_actor(),
        action=action,
        grants=_current_actor_grants(),
    ).allowed


_EMPTY_LLM_RESPONSE_ACTION = (
    "Ask the host to check get_status provider availability/cooldowns and fix "
    "provider credentials or CLI, then rerun; only switch llm_type if get_status "
    "shows another provider available."
)


# Phase 3: Graph Runner — execute a BranchDefinition
# ───────────────────────────────────────────────────────────────────────────
# The runner compiles a validated branch into a LangGraph StateGraph via
# `workflow.graph_compiler.compile_branch`, runs it synchronously against
# user-supplied inputs, and persists run metadata + per-node events in
# `<base>/.runs.db`. Status-aware mermaid diagrams are returned so
# Claude.ai can auto-visualize the live/completed graph. True async
# execution is task #39 (Phase 3.5).


def _run_mermaid_from_events(
    branch_def_id: str,
    node_statuses: list[dict[str, Any]],
) -> str:
    """Render a status-colored mermaid flowchart for a run snapshot.

    Colors: ran=green, running=amber, failed=red, pending=grey. The caller
    embeds this in the `summary` markdown and as a top-level field so
    Claude.ai auto-renders.
    """
    from workflow.api.branches import (
        _mermaid_label,
        _mermaid_node_id,
    )
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition

    try:
        source_dict = get_branch_definition(
            _base_path(), branch_def_id=branch_def_id,
        )
    except KeyError:
        return "```mermaid\nflowchart LR\n    missing_branch[\"(branch not found)\"]\n```"

    branch = BranchDefinition.from_dict(source_dict)
    status_by_id = {s["node_id"]: s["status"] for s in node_statuses}

    lines: list[str] = ["```mermaid", "flowchart LR"]
    lines.append('    START(["START"])')
    lines.append('    END(["END"])')

    for node in branch.node_defs:
        nid = _mermaid_node_id(node.node_id)
        label = _mermaid_label(node.display_name or node.node_id)
        lines.append(f'    {nid}["{label}"]')

    for edge in branch.edges:
        src = _mermaid_node_id(edge.from_node)
        dst = _mermaid_node_id(edge.to_node)
        lines.append(f"    {src} --> {dst}")

    # Apply status classes per node.
    status_classes = {
        "ran": "ran",
        "running": "running",
        "failed": "failed",
        "pending": "pending",
    }
    for node in branch.node_defs:
        nid = _mermaid_node_id(node.node_id)
        st = status_by_id.get(node.node_id, "pending")
        cls = status_classes.get(st, "pending")
        lines.append(f"    class {nid} {cls}")

    lines.extend([
        "    classDef ran fill:#d4edda,stroke:#28a745,stroke-width:2px",
        "    classDef running fill:#fff3cd,stroke:#ffc107,stroke-width:2px",
        "    classDef failed fill:#f8d7da,stroke:#dc3545,stroke-width:2px",
        "    classDef pending fill:#e9ecef,stroke:#6c757d,stroke-width:1px",
    ])

    lines.append("```")
    return "\n".join(lines)


_RUNS_RECOVERY_DONE = False


def _ensure_runs_recovery() -> None:
    """Once per process, mark any queued/running rows in the runs DB as
    ``interrupted``. Called from Phase 3 run handlers so the recovery
    happens on first use without needing a server start hook."""
    global _RUNS_RECOVERY_DONE
    if _RUNS_RECOVERY_DONE:
        return
    try:
        from workflow.runs import recover_in_flight_runs

        recover_in_flight_runs(_base_path())
    except Exception:
        logger.exception("in-flight run recovery failed")
    _RUNS_RECOVERY_DONE = True


_FAILURE_TAXONOMY: list[tuple[type, str, str]] = []


def _build_failure_taxonomy() -> list[tuple[type, str, str]]:
    """Build the (exc_type, failure_class, suggested_action) table lazily."""
    rows: list[tuple[type, str, str]] = []
    try:
        from workflow.graph_compiler import EmptyResponseError
        rows.append((
            EmptyResponseError,
            "empty_llm_response",
            _EMPTY_LLM_RESPONSE_ACTION,
        ))
    except ImportError:
        pass
    rows.append((
        RecursionError,
        "recursion_limit",
        "Branch loop may be too deep; raise recursion_limit_override param or simplify loop.",
    ))
    rows.append((
        TimeoutError,
        "timeout",
        "Branch run timed out; try a shorter branch or increase timeout param.",
    ))
    return rows


def _actionable_by(failure_class: str) -> str:
    """Look up `actionable_by` for a failure_class via the canonical table.

    BUG-029 surface: chatbot reads this field to know whether to retry
    via another tool call ("chatbot"), surface a host-action to the user
    ("host"), escalate the raw error to the user for human judgment
    ("user"), or accept the run as terminal-by-design with no recovery
    path ("none" — e.g. cancelled).

    Defaults to "user" — never silently drops the field; conservative
    "ask the human" beats silent absence. Use "none" only when the
    failure is genuinely unrecoverable.
    """
    from workflow.runs import ACTIONABLE_BY
    return ACTIONABLE_BY.get(failure_class, "user")


def _failure_payload(
    exc: Exception, failure_class: str, suggested_action: str,
) -> dict[str, Any]:
    """Construct the standard failure response with all 3 BUG-029 fields."""
    return {
        "status": "error",
        "error": f"Run failed: {exc}",
        "failure_class": failure_class,
        "suggested_action": suggested_action,
        "actionable_by": _actionable_by(failure_class),
    }


def _classify_run_error(exc: Exception, bid: str) -> dict[str, Any]:
    for exc_type, failure_class, suggested_action in _build_failure_taxonomy():
        if isinstance(exc, exc_type):
            return _failure_payload(exc, failure_class, suggested_action)
    msg = str(exc).lower()
    if "quota" in msg or "rate limit" in msg or "rate_limit" in msg or "ratelimit" in msg:
        return _failure_payload(
            exc, "quota_exhausted",
            "Provider quota or rate limit hit; wait before retrying OR"
            " switch providers via the llm_type param.",
        )
    if "all providers exhausted" in msg or "providers exhausted" in msg:
        return _failure_payload(
            exc, "provider_exhausted",
            "Provider chain exhausted; check provider credentials/config or"
            " rerun after cooldown.",
        )
    if "auth expir" in msg or "token expir" in msg or "credential" in msg:
        return _failure_payload(
            exc, "permission_denied:auth_expired",
            "Provider credentials have expired; re-authenticate or rotate the API key.",
        )
    if "permission denied" in msg:
        return _failure_payload(
            exc, "permission_denied:approval_required",
            "Ask host to approve the source_code node via extensions"
            " action=approve_source_code before running.",
        )
    if "approv" in msg or "source_code" in msg:
        return _failure_payload(
            exc, "node_not_approved",
            "Ask host to approve the source_code node via extensions"
            " action=approve_source_code before running.",
        )
    if "concurrent" in msg or "conflict" in msg or "modified" in msg or "stale" in msg:
        return _failure_payload(
            exc, "state_mutation_conflict",
            "Concurrent modification detected; re-fetch the branch state"
            " with get_branch then reapply your edit.",
        )
    if "compile failed" in msg or "already being used as a state key" in msg:
        return _failure_payload(
            exc, "compile_error",
            "Inspect the branch definition, node ids, state_schema, and graph"
            " edges; patch the branch and rerun.",
        )
    if "provider" in msg or "api key" in msg or "api_key" in msg or "auth" in msg:
        return _failure_payload(
            exc, "provider_unavailable",
            "No LLM provider is reachable; check ANTHROPIC/GROQ/GEMINI keys.",
        )
    return _failure_payload(
        exc, "unknown",
        f"Inspect the run transcript with get_run for branch '{bid}' details.",
    )


def _classify_run_outcome_error(error_str: str) -> tuple[str, str] | None:
    """Map a stored run-failure error string to (failure_class, suggested_action).

    Called on RunOutcome objects whose error was recorded by the async runner,
    so exception type is gone — only the serialised string remains.  Returns
    None when the error does not match any known pattern (caller keeps raw
    error string and omits failure_class / suggested_action).
    """
    msg = error_str.lower()
    if "empty" in msg and ("llm" in msg or "response" in msg or "provider" in msg):
        return (
            "empty_llm_response",
            _EMPTY_LLM_RESPONSE_ACTION,
        )
    if "timed out" in msg or "timeout" in msg:
        return (
            "timeout",
            "Branch run timed out; try a shorter branch or increase timeout param.",
        )
    if "quota" in msg or "rate limit" in msg or "rate_limit" in msg or "ratelimit" in msg:
        return (
            "quota_exhausted",
            "Provider quota or rate limit hit; wait before retrying OR"
            " switch providers via the llm_type param.",
        )
    if "all providers exhausted" in msg or "providers exhausted" in msg:
        return (
            "provider_exhausted",
            "Provider chain exhausted; check provider credentials/config or"
            " rerun after cooldown.",
        )
    if "overload" in msg or "503" in msg or "service unavailable" in msg or "server error" in msg:
        return (
            "provider_overloaded",
            "Provider is temporarily overloaded; wait 30-60s then retry"
            " or switch llm_type.",
        )
    if (
        "maximum context length" in msg
        or "context_length_exceeded" in msg
        or "tokens exceeded" in msg
        or "too many tokens" in msg
    ):
        return (
            "context_length_exceeded",
            "Input or accumulated state is too long for this provider;"
            " try a branch with fewer nodes or a higher-context model.",
        )
    if "auth expir" in msg or "token expir" in msg or "credential" in msg:
        return (
            "permission_denied:auth_expired",
            "Provider credentials have expired; re-authenticate or rotate the API key.",
        )
    if "approv" in msg or "source_code" in msg:
        return (
            "node_not_approved",
            "Ask host to approve the source_code node via extensions"
            " action=approve_source_code before running.",
        )
    if "permission denied" in msg:
        return (
            "permission_denied:approval_required",
            "Ask host to approve the source_code node via extensions"
            " action=approve_source_code before running.",
        )
    if "exit code" in msg or "subprocess failure" in msg or "api likely unavailable" in msg:
        return (
            "provider_subprocess_failed",
            "Provider CLI process failed; check that claude/codex binary is"
            " installed and reachable.",
        )
    if "concurrent" in msg or "conflict" in msg or "modified" in msg or "stale" in msg:
        return (
            "state_mutation_conflict",
            "Concurrent modification detected; re-fetch the branch state"
            " with get_branch then reapply your edit.",
        )
    if "compile failed" in msg or "already being used as a state key" in msg:
        return (
            "compile_error",
            "Inspect the branch definition, node ids, state_schema, and graph"
            " edges; patch the branch and rerun.",
        )
    if "provider" in msg or "api key" in msg or "api_key" in msg:
        return (
            "provider_unavailable",
            "No LLM provider is reachable; check ANTHROPIC/GROQ/GEMINI keys.",
        )
    if "call failed" in msg or "groq" in msg or "gemini" in msg or "grok" in msg:
        return (
            "provider_error",
            "Provider returned an unexpected error; check provider logs"
            " or try a different llm_type.",
        )
    return None


def _action_run_branch(kwargs: dict[str, Any]) -> str:
    """Execute a branch once.

    Durability guarantee (v1): runs are *terminal-on-restart*. If the
    daemon exits while a run is in flight, the row is marked
    ``interrupted`` on next startup (see
    ``workflow.runs.recover_in_flight_runs``) and ``get_run`` returns
    ``resumable=false`` with ``resumable_reason="v1 terminal-on-restart"``.
    To continue, re-invoke ``run_branch`` with the same ``branch_def_id``
    and ``inputs_json`` — a new ``run_id`` is returned. Mid-run resume
    from a SqliteSaver checkpoint is a future extension and is not
    available today; do not poll an ``interrupted`` run expecting it to
    flip back to ``running``.
    """
    from workflow.api.branches import _resolve_branch_id
    from workflow.api.engine_helpers import _current_actor
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition
    from workflow.runs import (
        RUN_STATUS_CANCELLED,
        RUN_STATUS_COMPLETED,
        RUN_STATUS_FAILED,
        RUN_STATUS_INTERRUPTED,
        execute_branch_async,
        get_run,
        record_lineage,
    )

    _ensure_runs_recovery()
    actor = _current_actor()

    bid = _resolve_branch_id(kwargs.get("branch_def_id", "").strip(), _base_path())
    if not bid:
        return json.dumps({"error": "branch_def_id is required."})

    try:
        source_dict = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({"error": f"Branch '{bid}' not found."})

    branch = BranchDefinition.from_dict(source_dict)
    errors = branch.validate()
    if errors:
        return json.dumps({
            "error": "Branch is not valid. Fix these before running:",
            "validation_errors": errors,
        })

    inputs_raw = kwargs.get("inputs_json", "").strip()
    inputs: dict[str, Any] = {}
    if inputs_raw:
        try:
            parsed = json.loads(inputs_raw)
            if not isinstance(parsed, dict):
                return json.dumps({
                    "error": "inputs_json must decode to a JSON object.",
                })
            inputs = parsed
        except json.JSONDecodeError as exc:
            return json.dumps({
                "error": f"inputs_json is not valid JSON: {exc}",
            })

    resume_from = (kwargs.get("resume_from") or "").strip()
    source_run: dict[str, Any] | None = None
    if resume_from:
        if any(ch.isspace() for ch in resume_from):
            return json.dumps({
                "error": "resume_from must be a single run_id with no whitespace.",
                "failure_class": "resume_from_invalid",
                "actionable_by": "chatbot",
            })
        source_run = get_run(_base_path(), resume_from)
        if source_run is None:
            return json.dumps({
                "error": "resume_from source run was not found.",
                "failure_class": "resume_from_not_found",
                "actionable_by": "chatbot",
            })
        if source_run.get("actor") != actor:
            return json.dumps({
                "error": "resume_from source run is not visible to the current actor.",
                "failure_class": "resume_from_forbidden",
                "actionable_by": "user",
            })
        if source_run.get("branch_def_id") != bid:
            return json.dumps({
                "error": (
                    "resume_from source run belongs to a different workflow "
                    "than the requested target branch."
                ),
                "failure_class": "resume_from_branch_mismatch",
                "actionable_by": "chatbot",
            })
        terminal_statuses = {
            RUN_STATUS_COMPLETED,
            RUN_STATUS_FAILED,
            RUN_STATUS_CANCELLED,
            RUN_STATUS_INTERRUPTED,
        }
        if source_run.get("status") not in terminal_statuses:
            return json.dumps({
                "error": (
                    "resume_from source run must be terminal before it can "
                    "seed a new run."
                ),
                "failure_class": "resume_from_invalid_state",
                "source_status": source_run.get("status"),
                "actionable_by": "chatbot",
            })
        source_inputs = source_run.get("inputs")
        if isinstance(source_inputs, dict):
            inputs = {**source_inputs, **inputs}

    # Real provider — lazy import so test envs without providers work.
    provider_call: Any = None
    try:
        from domains.fantasy_daemon.phases._provider_stub import (
            call_provider as provider_call,
        )
    except ImportError:
        provider_call = None

    # Parse + validate recursion_limit_override (10-1000).
    _rl_raw = kwargs.get("recursion_limit_override", "")
    recursion_limit_override: int | None = None
    if _rl_raw:
        try:
            _rl_val = int(_rl_raw)
        except (TypeError, ValueError):
            return json.dumps({"error": "recursion_limit_override must be an integer."})
        if not 10 <= _rl_val <= 1000:
            return json.dumps({
                "error": (
                    f"recursion_limit_override {_rl_val} out of range. "
                    "Valid range: 10-1000."
                ),
            })
        recursion_limit_override = _rl_val

    try:
        outcome = execute_branch_async(
            _base_path(),
            branch=branch,
            inputs=inputs,
            run_name=kwargs.get("run_name", ""),
            actor=actor,
            provider_call=provider_call,
            recursion_limit_override=recursion_limit_override,
        )
    except Exception as exc:
        logger.exception("run_branch failed for %s", bid)
        return json.dumps(_classify_run_error(exc, bid))

    # Write-ack per tool_return_shapes.md §Write actions. Phase 3.5 async:
    # the graph is running in a background worker, so the MCP call returns
    # status=queued almost immediately. The text channel is phone-legible
    # (no raw IDs); the run_id lives in structuredContent for the next
    # tool call.
    error_annotation = _classify_run_outcome_error(outcome.error) if outcome.error else None
    error_lines: list[str] = []
    if outcome.error:
        error_lines.append(f"Error: {outcome.error}")
    if error_annotation:
        error_lines.append(f"Suggested action: {error_annotation[1]}")
    text = "\n".join([
        f"**Run {outcome.status}.** Workflow handed to the "
        "background executor.",
        "",
        *error_lines,
        "Use `wait_for_run` to wait for progress without burning repeated "
        "tool calls, `get_run` for a snapshot, or `cancel_run` to stop. "
        "Each takes a `run_id` "
        "from the structured content of this response.",
    ]).strip()

    result: dict[str, Any] = {
        "text": text,
        "run_id": outcome.run_id,
        "status": outcome.status,
        "output": outcome.output,
        "error": outcome.error,
    }
    if source_run is not None:
        branch_version = int(getattr(branch, "version", 1) or 1)
        record_lineage(
            _base_path(),
            run_id=outcome.run_id,
            parent_run_id=resume_from,
            branch_def_id=bid,
            branch_version=branch_version,
            edits_since_parent=[],
        )
        result["resume_from"] = resume_from
        result["source_run_id"] = resume_from
    if error_annotation:
        result["failure_class"] = error_annotation[0]
        result["suggested_action"] = error_annotation[1]
        result["actionable_by"] = _actionable_by(error_annotation[0])
    return json.dumps(result)


def _branch_name_for_run(run_record: dict[str, Any]) -> str:
    """Fetch the human-legible branch name for a run record.

    Text channels should surface names, never raw branch_def_id strings.
    Falls back to ``(unknown workflow)`` when the branch is missing.
    """
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition

    try:
        source_dict = get_branch_definition(
            _base_path(),
            branch_def_id=run_record.get("branch_def_id", ""),
        )
        branch = BranchDefinition.from_dict(source_dict)
        return branch.name or "(unnamed workflow)"
    except Exception:
        return "(unknown workflow)"


def _compose_run_snapshot(
    run_record: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pack run metadata + node statuses + mermaid into a phone-legible dict."""
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition
    from workflow.runs import build_node_status_map

    declared_order: list[str] = []
    branch_name = ""
    try:
        source_dict = get_branch_definition(
            _base_path(), branch_def_id=run_record["branch_def_id"],
        )
        branch = BranchDefinition.from_dict(source_dict)
        declared_order = [gn.id for gn in branch.graph_nodes]
        branch_name = branch.name or ""
    except KeyError:
        pass

    node_statuses = build_node_status_map(events, declared_order)
    if run_record.get("status") == "failed" and run_record.get("last_node_id"):
        failed_node_id = run_record["last_node_id"]
        for node_status in node_statuses:
            if (
                node_status.get("node_id") == failed_node_id
                and node_status.get("status") == "running"
            ):
                node_status["status"] = "failed"
                break
    mermaid = _run_mermaid_from_events(
        run_record["branch_def_id"], node_statuses,
    )

    node_lines = (
        [f"  - {s['node_id']}: {s['status']}" for s in node_statuses]
        or ["  (no nodes reported)"]
    )
    # Phone-legible header — name first, IDs only in structuredContent.
    header_branch = branch_name or "(branch)"
    summary = "\n".join([
        f"**Run on workflow `{header_branch}`** — status "
        f"`{run_record['status']}`",
        f"Actor: {run_record['actor']}",
        "",
        "Nodes:",
        *node_lines,
        "",
        "Graph:",
        mermaid,
    ])

    # Surface the applied recursion limit from the __system__ event if present.
    recursion_limit: int | None = None
    for ev in events:
        if ev.get("node_id") == "__system__" and ev.get("status") == "recursion_limit_applied":
            try:
                recursion_limit = int(ev.get("detail", {}).get("recursion_limit", 0)) or None
            except (TypeError, ValueError):
                pass
            break

    snapshot: dict[str, Any] = {
        "text": summary,
        "run_id": run_record["run_id"],
        "branch_def_id": run_record["branch_def_id"],
        "status": run_record["status"],
        "actor": run_record["actor"],
        "last_node_id": run_record.get("last_node_id", ""),
        "started_at": run_record.get("started_at"),
        "finished_at": run_record.get("finished_at"),
        "error": run_record.get("error", ""),
        "node_statuses": node_statuses,
        "mermaid": mermaid,
        "summary": summary,
        "recursion_limit": recursion_limit,
    }
    # INTERRUPTED runs are terminal in v1 (durability guarantee — see
    # ``_action_run_branch`` docstring + ``runs.recover_in_flight_runs``).
    # The client must rerun with the same ``inputs_json``; it cannot be
    # polled to recovery. Surface this explicitly so chatbots don't
    # busy-wait forever.
    if run_record["status"] == "interrupted":
        snapshot["resumable"] = False
        snapshot["resumable_reason"] = "v1 terminal-on-restart"
    # BUG-029: enrich failed snapshots so chatbots have a user-actionable hint.
    # `actionable_by` tells the chatbot WHO can fix it — chatbot/host/user —
    # so it doesn't have to guess (Mara's failure mode 2026-04-24).
    if run_record["status"] == "failed":
        error_annotation = _classify_run_outcome_error(run_record.get("error", ""))
        if error_annotation:
            snapshot["failure_class"] = error_annotation[0]
            snapshot["suggested_action"] = error_annotation[1]
            snapshot["actionable_by"] = _actionable_by(error_annotation[0])
    return snapshot


def _action_get_run(kwargs: dict[str, Any]) -> str:
    from workflow.runs import get_run as _get_run
    from workflow.runs import list_events

    rid = kwargs.get("run_id", "").strip()
    if not rid:
        return json.dumps({"error": "run_id is required."})

    record = _get_run(_base_path(), rid)
    if record is None:
        return json.dumps({"error": f"Run '{rid}' not found."})

    events = list_events(_base_path(), rid)
    return json.dumps(_compose_run_snapshot(record, events), default=str)


def _action_list_runs(kwargs: dict[str, Any]) -> str:
    from workflow.runs import list_runs as _list_runs

    rows = _list_runs(
        _base_path(),
        branch_def_id=kwargs.get("branch_def_id", ""),
        status=kwargs.get("status", ""),
        limit=int(kwargs.get("limit", 50) or 50),
    )
    summaries = [
        {
            "run_id": r["run_id"],
            "branch_def_id": r["branch_def_id"],
            "run_name": r["run_name"],
            "status": r["status"],
            "actor": r["actor"],
            "started_at": r.get("started_at"),
            "finished_at": r.get("finished_at"),
            "last_node_id": r.get("last_node_id", ""),
        }
        for r in rows
    ]
    # Catalog shape per tool_return_shapes.md — compact markdown list
    # for phone clients; full fidelity is in the `runs` array.
    if summaries:
        lines = [f"**{len(summaries)} run(s):**", ""]
        for s in summaries[:12]:
            name = s["run_name"] or s["run_id"]
            lines.append(
                f"- `{s['run_id']}` · {s['status']} · "
                f"branch={s['branch_def_id']}"
                + (f" · name={name}" if s['run_name'] else "")
            )
        if len(summaries) > 12:
            lines.append(
                f"- … and {len(summaries) - 12} more. Narrow with "
                "`branch_def_id=...` or `status=...`."
            )
        text = "\n".join(lines)
    else:
        text = "No runs match the filter."
    return json.dumps({
        "text": text,
        "runs": summaries,
        "count": len(summaries),
    }, default=str)


def _action_stream_run(kwargs: dict[str, Any]) -> str:
    from workflow.runs import get_run as _get_run
    from workflow.runs import list_events

    rid = kwargs.get("run_id", "").strip()
    if not rid:
        return json.dumps({"error": "run_id is required."})

    record = _get_run(_base_path(), rid)
    if record is None:
        return json.dumps({"error": f"Run '{rid}' not found."})

    since = int(kwargs.get("since_step", -1))
    events = list_events(_base_path(), rid, since_step=since)
    next_cursor = max(
        (e.get("step_index", since) for e in events), default=since,
    )

    # State-over-time shape per tool_return_shapes.md — ordered event
    # ticks, tight one-line per event for phone polling.
    if events:
        lines = [
            f"**Run {record['status']}** · {len(events)} new event(s)",
            "",
        ]
        for e in events[-12:]:
            lines.append(
                f"- step {e.get('step_index')} · "
                f"`{e.get('node_id', '?')}` · {e.get('status', '?')}"
            )
        if len(events) > 12:
            lines.insert(
                2, f"_(showing last 12 of {len(events)})_\n",
            )
        lines.append("")
        lines.append(f"Next poll: `since_step={next_cursor}`.")
        text = "\n".join(lines)
    else:
        text = (
            f"No new events since step {since}. "
            f"Run status: `{record['status']}`."
        )

    return json.dumps({
        "text": text,
        "run_id": rid,
        "status": record["status"],
        "events": events,
        "next_cursor": next_cursor,
    }, default=str)


def _action_wait_for_run(kwargs: dict[str, Any]) -> str:
    """Long-poll for new events on a run (#65).

    Holds the response for up to ``max_wait_s`` OR until new events
    land, then returns everything since ``since_step``. One tool call
    covers ~60s of run wall time — dramatically cheaper than repeated
    stream_run polls on the Claude.ai per-turn budget.
    """
    from workflow.runs import await_run_events
    from workflow.runs import get_run as _get_run

    rid = kwargs.get("run_id", "").strip()
    if not rid:
        return json.dumps({
            "error": "run_id is required for wait_for_run.",
        })
    record = _get_run(_base_path(), rid)
    if record is None:
        return json.dumps({"error": f"Run '{rid}' not found."})

    # Bound max_wait_s to 120s so a broken client can't tie up the
    # server thread forever. Default 60s per spec.
    raw_wait = kwargs.get("max_wait_s", 60)
    try:
        max_wait_s = max(0.5, min(120.0, float(raw_wait)))
    except (TypeError, ValueError):
        max_wait_s = 60.0
    since = int(kwargs.get("since_step", -1) or -1)

    result = await_run_events(
        _base_path(), rid,
        since_step=since,
        max_wait_s=max_wait_s,
    )
    events = result["events"]
    status = result["status"]
    next_cursor = result["next_cursor"]
    reason = result["reason"]
    waited = result["waited_s"]

    if events:
        header = (
            f"**Run status: `{status}`** · {len(events)} new event(s) "
            f"after waiting {waited}s."
        )
    elif reason == "terminal":
        header = (
            f"**Run finished** with status `{status}` "
            f"({waited}s wait)."
        )
    else:
        header = (
            f"**Still running** — no new events in {waited}s. "
            f"Status: `{status}`."
        )

    lines = [header, ""]
    for e in events[-12:]:
        lines.append(
            f"- step {e.get('step_index')} · "
            f"`{e.get('node_id', '?')}` · {e.get('status', '?')}"
        )
    if len(events) > 12:
        lines.insert(
            2, f"_(showing last 12 of {len(events)})_\n",
        )
    if events:
        lines.append("")
        lines.append(f"Next poll: `since_step={next_cursor}`.")
    text = "\n".join(lines)

    return json.dumps({
        "text": text,
        "run_id": rid,
        "status": status,
        "events": events,
        "next_cursor": next_cursor,
        "waited_s": waited,
        "reason": reason,
    }, default=str)


def _action_cancel_run(kwargs: dict[str, Any]) -> str:
    from workflow.runs import (
        get_run as _get_run,
    )
    from workflow.runs import (
        request_cancel,
    )

    rid = kwargs.get("run_id", "").strip()
    if not rid:
        return json.dumps({"error": "run_id is required."})
    if _get_run(_base_path(), rid) is None:
        return json.dumps({"error": f"Run '{rid}' not found."})

    request_cancel(_base_path(), rid)
    note = (
        "Cancel noted. Sync v1 runs typically finish before the flag "
        "is checked; full cooperative cancel ships with Phase 3.5 "
        "(task #39)."
    )
    text = (
        "**Cancel requested.** The background executor will stop at the "
        f"next checkpoint.\n\n{note}"
    )
    return json.dumps({
        "text": text,
        "run_id": rid,
        "status": "cancel_requested",
        "note": note,
    })


def _action_get_run_output(kwargs: dict[str, Any]) -> str:
    from workflow.runs import get_run as _get_run

    rid = kwargs.get("run_id", "").strip()
    if not rid:
        return json.dumps({"error": "run_id is required."})

    record = _get_run(_base_path(), rid)
    if record is None:
        return json.dumps({"error": f"Run '{rid}' not found."})

    field = kwargs.get("field_name", "").strip()
    output = record.get("output") or {}
    if field:
        if field not in output:
            return json.dumps({
                "error": f"Output field '{field}' not present on run.",
                "available_fields": sorted(output.keys()),
            })
        value = output[field]
        # Scalar/single-artifact shape per tool_return_shapes.md —
        # tight one-liner + full value for scripts.
        preview = str(value)
        if len(preview) > 240:
            preview = preview[:240].rstrip() + "…"
        branch_label = _branch_name_for_run(record)
        text = (
            f"**{field}** (workflow '{branch_label}'):\n\n{preview}"
        )
        return json.dumps({
            "text": text,
            "run_id": rid,
            "field_name": field,
            "value": value,
        }, default=str)
    # Whole-output read — catalog of fields.
    branch_label = _branch_name_for_run(record)
    lines = [
        f"**Output from workflow '{branch_label}'** "
        f"(status: {record.get('status')})"
    ]
    if output:
        lines.append("")
        for key in sorted(output.keys()):
            val_preview = str(output[key])
            if len(val_preview) > 120:
                val_preview = val_preview[:120].rstrip() + "…"
            lines.append(f"- `{key}`: {val_preview}")
    else:
        lines.append("\n_(no output produced)_")
    return json.dumps({
        "text": "\n".join(lines),
        "run_id": rid,
        "status": record.get("status"),
        "output": output,
    }, default=str)


def _action_attach_existing_child_run(kwargs: dict[str, Any]) -> str:
    """Attach a completed child run receipt to a waiting parent run."""
    from workflow.api.engine_helpers import _current_actor
    from workflow.runs import ChildRunAttachmentError, attach_existing_child_run

    parent_run_id = kwargs.get("run_id", "").strip()
    child_run_id = kwargs.get("child_run_id", "").strip()
    child_branch_def_id = kwargs.get("child_branch_def_id", "").strip()
    output_digest = kwargs.get("output_digest", "").strip()

    try:
        result = attach_existing_child_run(
            _base_path(),
            parent_run_id=parent_run_id,
            child_run_id=child_run_id,
            child_branch_def_id=child_branch_def_id,
            output_digest=output_digest,
            actor=_current_actor(),
        )
    except ChildRunAttachmentError as exc:
        payload: dict[str, Any] = {
            "error": str(exc),
            "error_code": exc.code,
        }
        payload.update(exc.details)
        return json.dumps(payload, default=str)

    text = (
        "**Child receipt attached.** "
        f"Parent run `{result['parent_run_id']}` now references child run "
        f"`{result['child_run_id']}` via `{result['stable_evidence_handle']}`. "
        "This is a receipt validation path only."
    )
    return json.dumps({
        "text": text,
        "run_id": result["parent_run_id"],
        **result,
    }, default=str)


def _action_resume_run(kwargs: dict[str, Any]) -> str:
    """Resume an INTERRUPTED run from its SqliteSaver checkpoint.

    Auth re-check is performed at resume time — the caller must still own
    the run. If the run is already in RESUMED status, the call is
    idempotent and returns the existing run_id.
    """
    from workflow.api.engine_helpers import _current_actor
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition
    from workflow.runs import ResumeError, resume_run

    _ensure_runs_recovery()

    run_id = kwargs.get("run_id", "").strip()
    if not run_id:
        return json.dumps({"error": "run_id is required."})

    actor = _current_actor()

    def _branch_lookup(branch_def_id: str, _version: int) -> BranchDefinition | None:
        try:
            source_dict = get_branch_definition(_base_path(), branch_def_id=branch_def_id)
            return BranchDefinition.from_dict(source_dict)
        except Exception:
            return None

    provider_call: Any = None
    try:
        from domains.fantasy_daemon.phases._provider_stub import (
            call_provider as provider_call,
        )
    except ImportError:
        provider_call = None

    try:
        outcome = resume_run(
            _base_path(),
            run_id=run_id,
            actor=actor,
            branch_lookup=_branch_lookup,
            provider_call=provider_call,
        )
    except ResumeError as exc:
        return json.dumps({
            "error": str(exc), "reason": exc.reason, "current_status": exc.current_status,
        })
    except Exception as exc:
        logger.exception("resume_run failed for %s", run_id)
        return json.dumps({"error": f"Resume failed: {exc}"})

    text = "\n".join([
        f"**Run {outcome.status}.** Resume handed to the background executor.",
        "",
        f"Error: {outcome.error}" if outcome.error else "",
        "Use `get_run` to check progress or `cancel_run` to stop.",
    ]).strip()

    return json.dumps({
        "text": text,
        "run_id": outcome.run_id,
        "status": outcome.status,
        "output": outcome.output,
        "error": outcome.error,
    })


def _action_estimate_run_cost(kwargs: dict[str, Any]) -> str:
    """Estimate cost and time for running a branch before dispatch.

    Returns a structured estimate so the chatbot can narrate cost/time
    framing before the user commits to a paid-market bid or free-queue
    wait. Read-only — no provider calls, no writes.

    Confidence levels:
    - "low": branch has never been run (estimate from node declarations).
    - "medium": 1-4 prior completed runs exist (use average).
    - "high": 5+ prior completed runs exist (use median of sample).
    """
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition
    from workflow.runs import RUN_STATUS_COMPLETED, list_runs

    bid = kwargs.get("branch_def_id", "").strip()
    if not bid:
        return json.dumps({"error": "branch_def_id is required."})

    try:
        source_dict = get_branch_definition(_base_path(), branch_def_id=bid)
    except Exception:
        return json.dumps({"error": f"Branch '{bid}' not found."})

    branch = BranchDefinition.from_dict(source_dict)
    node_count = len(branch.node_defs)

    # Per-node cost heuristic: roughly 0.01 credits per node for a
    # prompt-template node (LLM call), 0.001 for a code node (exec only).
    # These are illustrative baseline defaults — real pricing depends on
    # the provider bid the user sets at dispatch time (paid_market model).
    credits_per_node: dict[str, float] = {}
    for n in branch.node_defs:
        if n.prompt_template:
            credits_per_node[n.node_id] = 0.01
        else:
            credits_per_node[n.node_id] = 0.001

    estimated_paid_market_credits = round(sum(credits_per_node.values()), 4)

    # Confidence: check prior completed run history.
    try:
        prior_runs = list_runs(
            _base_path(), branch_def_id=bid, status=RUN_STATUS_COMPLETED,
        )
    except Exception:
        prior_runs = []

    run_count = len(prior_runs)
    if run_count == 0:
        confidence = "low"
    elif run_count < 5:
        confidence = "medium"
    else:
        confidence = "high"

    # Free-queue ETA: best-effort from dispatcher queue depth.
    free_queue_eta_hours: float | None = None
    free_queue_caveat: str | None = None
    try:
        from workflow.dispatcher import get_queue_depth
        queue_depth = get_queue_depth()
        # Rough heuristic: ~10 min per queued run ahead of this one.
        free_queue_eta_hours = round((queue_depth * 10) / 60, 2)
    except Exception:
        free_queue_caveat = (
            "Dispatcher queue depth unavailable — free_queue_eta_hours is null. "
            "Dispatcher may be disabled or not yet initialised."
        )

    # Build a chatbot-quotable basis string.
    llm_nodes = sum(1 for n in branch.node_defs if n.prompt_template)
    code_nodes = node_count - llm_nodes
    basis_parts = [
        f"{node_count} node(s) total: {llm_nodes} LLM node(s) at ~0.01 credits each, "
        f"{code_nodes} code/other node(s) at ~0.001 credits each.",
        f"Confidence: {confidence} ({run_count} prior completed run(s)).",
    ]
    if free_queue_caveat:
        basis_parts.append(free_queue_caveat)
    else:
        basis_parts.append(
            f"Free-queue ETA based on ~{free_queue_eta_hours}h "
            "(estimated from current queue depth)."
        )
    basis = " ".join(basis_parts)

    return json.dumps({
        "branch_def_id": bid,
        "node_count": node_count,
        "estimated_paid_market_credits": estimated_paid_market_credits,
        "free_queue_eta_hours": free_queue_eta_hours,
        "confidence": confidence,
        "basis": basis,
        "prior_run_count": run_count,
    })



def _action_query_runs(kwargs: dict[str, Any]) -> str:
    from workflow.runs import _VALID_AGGREGATES, query_runs

    bid = kwargs.get("branch_def_id", "").strip()
    raw_filters = kwargs.get("filters_json", "") or kwargs.get("filters", "") or ""
    raw_select = kwargs.get("select", "") or ""
    raw_aggregate = kwargs.get("aggregate_json", "") or kwargs.get("aggregate", "") or ""
    raw_limit = kwargs.get("limit", _DEFAULT_QUERY_LIMIT) or _DEFAULT_QUERY_LIMIT

    filters: dict[str, Any] = {}
    if raw_filters:
        try:
            filters = json.loads(raw_filters) if isinstance(raw_filters, str) else raw_filters
        except (json.JSONDecodeError, TypeError):
            return json.dumps({"error": "filters_json is not valid JSON."})

    select: list[str] = []
    if raw_select:
        if isinstance(raw_select, str):
            select = [s.strip() for s in raw_select.split(",") if s.strip()]
        elif isinstance(raw_select, list):
            select = raw_select

    aggregate: dict[str, Any] | None = None
    if raw_aggregate:
        try:
            agg_parsed = (
                json.loads(raw_aggregate) if isinstance(raw_aggregate, str)
                else raw_aggregate
            )
            if isinstance(agg_parsed, dict):
                agg_fn = agg_parsed.get("fn", agg_parsed.get("op", "count"))
                if agg_fn not in _VALID_AGGREGATES:
                    return json.dumps({
                        "error": f"aggregate.fn must be one of: {sorted(_VALID_AGGREGATES)}",
                    })
                aggregate = agg_parsed
        except (json.JSONDecodeError, TypeError):
            return json.dumps({"error": "aggregate_json is not valid JSON."})

    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = _DEFAULT_QUERY_LIMIT

    result = query_runs(
        _base_path(),
        branch_def_id=bid,
        filters=filters,
        select=select,
        aggregate=aggregate,
        limit=limit,
    )
    return json.dumps(result, default=str)


_DEFAULT_QUERY_LIMIT = 100


def _action_run_routing_evidence(kwargs: dict[str, Any]) -> str:
    """Return recent run records shaped for provider/routing self-audit.

    Answers "which LLM answered the last call?" and "why did the run fail?"
    Each record includes derived latency_ms, failure_class, suggested_action,
    and a caveat noting that provider_used / token_count fields are not yet
    in the runs schema (pending schema migration).
    """
    from workflow.runs import list_recent_runs

    bid = (kwargs.get("branch_def_id") or "").strip()
    raw_limit = kwargs.get("limit", 10)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = 10

    records = list_recent_runs(_base_path(), branch_def_id=bid, limit=limit)
    return json.dumps({
        "runs": records,
        "count": len(records),
        "caveat": records[0]["caveat"] if records else (
            "No runs found. Execute a branch first, then call get_routing_evidence."
        ),
    }, default=str)


# ───────────────────────────────────────────────────────────────────────────
# get_memory_scope_status — self-auditing primitive §4.1
# ───────────────────────────────────────────────────────────────────────────


def _action_get_memory_scope_status(kwargs: dict[str, Any]) -> str:
    """Snapshot of memory-scope enforcement state for chatbot self-audit.

    Self-auditing-tools pattern (§4.1). Answers: "Is tiered scope active?
    Which tiers are being enforced? Have any scope mismatches been logged?"
    Returns concrete evidence the chatbot can narrate; does not infer.

    Shape (schema_version=1):
        {
          "schema_version": int,
          "tiered_scope_enabled": bool,
          "flag_state": str,
          "active_enforcement_tiers": [str, ...],
          "all_scope_tiers": [str, ...],
          "retrieval_stats_by_tier": {},
          "recent_scope_mismatch_warnings": [str, ...],
          "caveats": [str, ...],
          "actionable_next_steps": [str, ...],
        }
    """
    import os as _os

    from workflow.retrieval.router import tiered_scope_enabled

    flag_on = tiered_scope_enabled()
    flag_raw = _os.environ.get("WORKFLOW_TIERED_SCOPE", "off")
    all_tiers = ["universe_id", "goal_id", "branch_id", "user_id"]
    active_tiers = all_tiers if flag_on else ["universe_id"]

    universe_id = (kwargs.get("universe_id") or "").strip() or _default_universe()
    udir = _universe_dir(universe_id)
    log_content = _read_text(udir / "activity.log")
    mismatch_lines: list[str] = []
    if log_content:
        for line in log_content.strip().splitlines():
            if "retrieval.scope_mismatch" in line:
                mismatch_lines.append(line.strip())
    recent_mismatches = mismatch_lines[-10:]

    caveats: list[str] = [
        "retrieval_stats_by_tier is not yet instrumented (Stage 2b.3);"
        " per-tier drop counts will appear in Stage 2c.",
    ]
    if not flag_on:
        caveats.append(
            "WORKFLOW_TIERED_SCOPE=off: only universe_id is enforced."
            " goal_id / branch_id / user_id isolation is NOT active."
        )
    if recent_mismatches:
        caveats.append(
            f"{len(recent_mismatches)} recent scope-mismatch warning(s) in"
            " activity.log — inspect recent_scope_mismatch_warnings."
        )

    next_steps: list[str] = []
    if not flag_on:
        next_steps.append(
            "Set WORKFLOW_TIERED_SCOPE=on to enable full four-tier"
            " isolation (universe/goal/branch/user)."
        )
    next_steps.append(
        "Check activity.log for 'retrieval.scope_mismatch' to diagnose"
        " any cross-universe content bleed."
    )

    return json.dumps({
        "schema_version": 1,
        "tiered_scope_enabled": flag_on,
        "flag_state": flag_raw,
        "active_enforcement_tiers": active_tiers,
        "all_scope_tiers": all_tiers,
        "retrieval_stats_by_tier": {},
        "recent_scope_mismatch_warnings": recent_mismatches,
        "caveats": caveats,
        "actionable_next_steps": next_steps,
        "universe_id": universe_id,
    })


def _action_run_branch_version(kwargs: dict[str, Any]) -> str:
    """Execute a published branch_version snapshot.

    Phase A item 6 (Task #65b). Sibling to ``run_branch``; resolves a
    ``branch_version_id`` via ``branch_versions``, reconstructs a
    ``BranchDefinition`` from the immutable snapshot, and hands off to
    the same async executor pool. Records the ``branch_version_id`` on
    the new ``runs.branch_version_id`` column for attribution.
    """
    from workflow.api.engine_helpers import _current_actor
    from workflow.runs import (
        SnapshotSchemaDrift,
        execute_branch_version_async,
    )

    _ensure_runs_recovery()

    bvid = (kwargs.get("branch_version_id") or "").strip()
    if not bvid:
        return json.dumps({"error": "branch_version_id is required."})

    inputs_raw = kwargs.get("inputs_json", "").strip()
    inputs: dict[str, Any] = {}
    if inputs_raw:
        try:
            parsed = json.loads(inputs_raw)
            if not isinstance(parsed, dict):
                return json.dumps({
                    "error": "inputs_json must decode to a JSON object.",
                })
            inputs = parsed
        except json.JSONDecodeError as exc:
            return json.dumps({
                "error": f"inputs_json is not valid JSON: {exc}",
            })

    # Real provider — lazy import so test envs without providers work.
    provider_call: Any = None
    try:
        from domains.fantasy_daemon.phases._provider_stub import (
            call_provider as provider_call,
        )
    except ImportError:
        provider_call = None

    # Parse + validate recursion_limit_override (10-1000) — same shape as run_branch.
    _rl_raw = kwargs.get("recursion_limit_override", "")
    recursion_limit_override: int | None = None
    if _rl_raw:
        try:
            _rl_val = int(_rl_raw)
        except (TypeError, ValueError):
            return json.dumps({"error": "recursion_limit_override must be an integer."})
        if not 10 <= _rl_val <= 1000:
            return json.dumps({
                "error": (
                    f"recursion_limit_override {_rl_val} out of range. "
                    "Valid range: 10-1000."
                ),
            })
        recursion_limit_override = _rl_val

    try:
        outcome = execute_branch_version_async(
            _base_path(),
            branch_version_id=bvid,
            inputs=inputs,
            run_name=kwargs.get("run_name", ""),
            actor=_current_actor(),
            provider_call=provider_call,
            recursion_limit_override=recursion_limit_override,
        )
    except KeyError as exc:
        return json.dumps({"error": str(exc).strip("'\"")})
    except SnapshotSchemaDrift as exc:
        return json.dumps({
            "error": str(exc),
            "failure_class": SnapshotSchemaDrift.failure_class,
            "suggested_action": SnapshotSchemaDrift.suggested_action,
            "actionable_by": SnapshotSchemaDrift.actionable_by,
        })
    except Exception as exc:
        logger.exception("run_branch_version failed for %s", bvid)
        return json.dumps(_classify_run_error(exc, bvid))

    # Write-ack mirroring _action_run_branch's response shape.
    error_annotation = _classify_run_outcome_error(outcome.error) if outcome.error else None
    error_lines: list[str] = []
    if outcome.error:
        error_lines.append(f"Error: {outcome.error}")
    if error_annotation:
        error_lines.append(f"Suggested action: {error_annotation[1]}")
    text = "\n".join([
        f"**Run {outcome.status}.** Version-based workflow handed to the "
        "background executor.",
        "",
        *error_lines,
        "Use `wait_for_run` to wait for progress without burning repeated "
        "tool calls, `get_run` for a snapshot, or `cancel_run` to stop. "
        "Each takes a `run_id` "
        "from the structured content of this response.",
    ]).strip()

    result: dict[str, Any] = {
        "text": text,
        "run_id": outcome.run_id,
        "status": outcome.status,
        "output": outcome.output,
        "error": outcome.error,
        "branch_version_id": bvid,
    }
    if error_annotation:
        result["failure_class"] = error_annotation[0]
        result["suggested_action"] = error_annotation[1]
        result["actionable_by"] = _actionable_by(error_annotation[0])
    return json.dumps(result)


def _action_rollback_merge(kwargs: dict[str, Any]) -> str:
    """Surgical-rollback (Task #22 Phase B). Explicit rollback capability.

    Required kwargs: ``branch_version_id`` (seed), ``reason``.
    Optional kwargs: ``severity`` (P0/P1/P2; default P1).

    Computes the dependency closure from the seed, atomically flips each
    closure version to ``status='rolled_back'`` + emits one
    ``caused_regression`` event per version (single runs-DB transaction),
    then re-points any goal canonical pointing into the closure to the
    nearest non-rolled-back ancestor (separate author_server-DB step
    per cross-DB refinement; see ``workflow/rollback.py`` module
    docstring).
    """
    from workflow.api.engine_helpers import _current_actor
    from workflow.daemon_server import CAP_ROLLBACK_BRANCH
    from workflow.rollback import rollback_merge_orchestrator

    bvid = (kwargs.get("branch_version_id") or "").strip()
    reason = (kwargs.get("reason") or "").strip()
    severity = (kwargs.get("severity") or "P1").strip().upper()
    if not bvid:
        return json.dumps({"error": "branch_version_id is required."})
    if not reason:
        return json.dumps({"error": "reason is required."})

    actor = _current_actor()
    if not _current_actor_has_capability(CAP_ROLLBACK_BRANCH):
        return json.dumps({
            "error": (
                f"Missing capability: {CAP_ROLLBACK_BRANCH} "
                f"(request actor was {actor!r})."
            ),
        })

    result = rollback_merge_orchestrator(
        _base_path(),
        bvid,
        reason=reason,
        set_by=actor,
        severity=severity,
    )
    if result.get("status") == "rejected":
        return json.dumps(result, default=str)

    closure = result.get("closure", [])
    repoint = result.get("repoint", {})
    text_lines = [
        f"**Rolled back** {len(closure)} branch_version(s) seeded from "
        f"`{bvid}` (severity {severity}).",
        f"Reason: {reason}",
    ]
    repointed_count = repoint.get("repointed_count", 0)
    if repointed_count:
        text_lines.append(
            f"Re-pointed canonical bindings on {repointed_count} Goal(s) "
            "to nearest non-rolled-back ancestor."
        )
    # DESIGN-008 round 4 — selector bindings are cleared (not walked up)
    # so the leaderboard read path falls back to the platform default.
    selector_repoint = result.get("selector_repoint", {})
    selector_repointed_count = selector_repoint.get("repointed_count", 0)
    if selector_repointed_count:
        text_lines.append(
            f"Cleared selector bindings on {selector_repointed_count} "
            "Goal(s); leaderboard falls back to platform default until "
            "operator re-binds via `goals action=set_selector`."
        )
    return json.dumps({
        "text": "\n".join(text_lines),
        **result,
    }, default=str)


def _action_get_rollback_history(kwargs: dict[str, Any]) -> str:
    """Read-only rollback history surface. No authority restriction.

    Optional kwargs: ``since_days`` (default 7).
    """
    from workflow.rollback import get_rollback_history

    try:
        since_days = int(kwargs.get("since_days", 7) or 7)
    except (TypeError, ValueError):
        since_days = 7
    since_days = max(1, min(since_days, 365))

    rollbacks = get_rollback_history(_base_path(), since_days=since_days)
    if rollbacks:
        text_lines = [
            f"**{len(rollbacks)} rollback(s)** in the past {since_days} day(s):",
            "",
        ]
        for r in rollbacks[:20]:
            text_lines.append(
                f"- `{r['branch_version_id']}` · "
                f"{r['rolled_back_at']} · by `{r['rolled_back_by']}` · "
                f"{r['rolled_back_reason']}"
            )
        if len(rollbacks) > 20:
            text_lines.append(f"_… and {len(rollbacks) - 20} more._")
        text = "\n".join(text_lines)
    else:
        text = f"_No rollbacks in the past {since_days} day(s)._"
    return json.dumps({
        "text": text,
        "rollbacks": rollbacks,
        "count": len(rollbacks),
        "since_days": since_days,
    }, default=str)


_RUN_ACTIONS: dict[str, Any] = {
    "run_branch": _action_run_branch,
    "run_branch_version": _action_run_branch_version,
    "get_run": _action_get_run,
    "list_runs": _action_list_runs,
    "stream_run": _action_stream_run,
    "wait_for_run": _action_wait_for_run,
    "cancel_run": _action_cancel_run,
    "get_run_output": _action_get_run_output,
    "attach_existing_child_run": _action_attach_existing_child_run,
    "resume_run": _action_resume_run,
    "estimate_run_cost": _action_estimate_run_cost,
    "query_runs": _action_query_runs,
    "get_routing_evidence": _action_run_routing_evidence,
    "get_memory_scope_status": _action_get_memory_scope_status,
    "rollback_merge": _action_rollback_merge,
    "get_rollback_history": _action_get_rollback_history,
}

_RUN_WRITE_ACTIONS: frozenset[str] = frozenset(
    {"run_branch", "run_branch_version", "cancel_run", "resume_run",
     "rollback_merge", "attach_existing_child_run"}
)


def _dispatch_run_action(
    action: str,
    handler: Any,
    kwargs: dict[str, Any],
) -> str:
    """Dispatch a Phase 3 run action, ledger the write actions.

    run_branch and cancel_run both mutate durable state so they land in
    the global ledger with the run_id as the target.
    """
    from workflow.api.branches import _append_global_ledger
    from workflow.api.engine_helpers import _truncate

    result_str = handler(kwargs)
    if action not in _RUN_WRITE_ACTIONS:
        return result_str

    try:
        result = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return result_str
    if not isinstance(result, dict):
        return result_str
    # Only skip ledger on actual error responses (non-empty 'error' value).
    # _action_run_branch always includes an empty 'error' field on success.
    if result.get("error"):
        return result_str

    try:
        target = result.get("run_id", "") or kwargs.get("run_id", "")
        summary_bits = [action]
        if kwargs.get("branch_def_id"):
            summary_bits.append(f"branch={kwargs['branch_def_id']}")
        if result.get("status"):
            summary_bits.append(f"status={result['status']}")
        _append_global_ledger(
            action,
            target=str(target),
            summary=_truncate(" ".join(summary_bits)),
            payload=None,
        )
    except Exception as exc:
        logger.warning("Ledger write failed for run action %s: %s", action, exc)
    return result_str
