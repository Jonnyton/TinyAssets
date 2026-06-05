"""Runtime-coordination subsystem — extracted from workflow/universe_server.py
(Task #13 — decomp Step 6).

Houses 4 small-to-medium action groups that share a common runtime-coordination
purpose: project-scoped memory, zero-side-effect dry inspection, teammate
messaging, and scheduler hooks. The MCP tool decoration stays in
``workflow/universe_server.py`` (Pattern A2 from the decomp plan); this
module is plain functions consumed via the ``extensions()`` MCP tool.

Public surface (back-compat re-exported via ``workflow.universe_server``):
    Dispatch tables:
        _PROJECT_MEMORY_ACTIONS / _PROJECT_MEMORY_WRITE_ACTIONS
        _INSPECT_DRY_ACTIONS
        _MESSAGING_ACTIONS
        _SCHEDULER_ACTIONS

    Project memory handlers:
        _action_project_memory_get / _action_project_memory_set /
        _action_project_memory_list

    Dry inspect handlers + helpers:
        _action_dry_inspect_node / _action_dry_inspect_patch
        _load_branch_for_inspect / _apply_patch_ops

    Messaging handlers:
        _action_messaging_send / _action_messaging_receive /
        _action_messaging_ack

    Scheduler handlers:
        _action_schedule_branch / _action_unschedule_branch /
        _action_list_schedules / _action_subscribe_branch /
        _action_unsubscribe_branch / _action_pause_schedule /
        _action_unpause_schedule / _action_list_scheduler_subscriptions

Cross-module note: ``_current_actor`` lives in ``workflow.universe_server``
(universe-engine territory) and is lazy-imported inside the functions that
use it. This avoids the load-time cycle (universe_server back-compat-imports
symbols from this module). Same pattern as Tasks #11/#12.

There is NO dispatch-glue function here (unlike runs.py's
_dispatch_run_action and evaluation.py's _dispatch_judgment_action). The
``extensions()`` body inlines the dispatch loop directly for these 4 tables;
the ledger-write path consults ``_PROJECT_MEMORY_WRITE_ACTIONS`` only
(messaging/dry-inspect/scheduler have no separate write-set in current code).

Source ranges extracted (current line numbers, post-#12 land):
- L7078–7148 — Project memory (3 handlers + dispatch dict + write set)
- L7152–7290 — Dry-inspect (helpers + 2 handlers + dispatch dict)
- L7406–7498 — Teammate messaging (3 handlers + dispatch dict)
- L7500–7690 — Scheduler (8 handlers + dispatch dict)

`_apply_patch_ops` placement: per Step 6 prep §3.3 Option B (lead-confirmed),
moves with its only consumer (``_action_dry_inspect_patch``) instead of
remaining in universe_server for hypothetical branches.py future use.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from workflow.api.helpers import _base_path

logger = logging.getLogger("universe_server.runtime_ops")


# ───────────────────────────────────────────────────────────────────────────

def _action_project_memory_get(kwargs: dict[str, Any]) -> str:
    from workflow.memory.project import project_memory_get

    project_id = kwargs.get("project_id", "").strip()
    key = kwargs.get("key", "").strip()
    if not project_id or not key:
        return json.dumps({"error": "project_id and key are required."})
    row = project_memory_get(_base_path(), project_id=project_id, key=key)
    if row is None:
        return json.dumps({"found": False, "project_id": project_id, "key": key})
    return json.dumps({"found": True, **row})


def _action_project_memory_set(kwargs: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.memory.project import project_memory_set

    project_id = kwargs.get("project_id", "").strip()
    key = kwargs.get("key", "").strip()
    raw_value = kwargs.get("value", "")
    if not project_id or not key:
        return json.dumps({"error": "project_id and key are required."})
    try:
        value = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
    except (json.JSONDecodeError, TypeError):
        value = raw_value
    expected_version_raw = kwargs.get("expected_version")
    expected_version: int | None = None
    if expected_version_raw is not None:
        try:
            expected_version = int(expected_version_raw)
        except (TypeError, ValueError):
            return json.dumps({"error": "expected_version must be an integer."})
    actor = _current_actor()
    result = project_memory_set(
        _base_path(),
        project_id=project_id,
        key=key,
        value=value,
        actor=actor,
        expected_version=expected_version,
    )
    return json.dumps(result)


def _action_project_memory_list(kwargs: dict[str, Any]) -> str:
    from workflow.memory.project import project_memory_list

    project_id = kwargs.get("project_id", "").strip()
    if not project_id:
        return json.dumps({"error": "project_id is required."})
    key_prefix = kwargs.get("key_prefix", "") or ""
    try:
        limit = int(kwargs.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    rows = project_memory_list(
        _base_path(), project_id=project_id, key_prefix=key_prefix, limit=limit
    )
    return json.dumps({"project_id": project_id, "entries": rows, "count": len(rows)})


_PROJECT_MEMORY_ACTIONS: dict[str, Any] = {
    "project_memory_get": _action_project_memory_get,
    "project_memory_set": _action_project_memory_set,
    "project_memory_list": _action_project_memory_list,
}

_PROJECT_MEMORY_WRITE_ACTIONS: frozenset[str] = frozenset({"project_memory_set"})


# ───────────────────────────────────────────────────────────────────────────
# dry_inspect_node / dry_inspect_patch — zero-side-effect structural preview
# ───────────────────────────────────────────────────────────────────────────


def _load_branch_for_inspect(
    branch_def_id: str,
    branch_spec_json: str,
) -> tuple[Any, str | None]:
    """Return (BranchDefinition, error_str). Exactly one of the two inputs."""
    from workflow.branches import BranchDefinition as _BD

    if branch_spec_json:
        try:
            spec = json.loads(branch_spec_json)
        except json.JSONDecodeError as exc:
            return None, f"branch_spec_json is not valid JSON: {exc}"
        try:
            return _BD.from_dict(spec), None
        except Exception as exc:  # noqa: BLE001
            return None, f"branch_spec_json could not be parsed: {exc}"

    if not branch_def_id:
        return None, "branch_def_id or branch_spec_json is required."

    try:
        from workflow.daemon_server import get_branch_definition
        source = get_branch_definition(_base_path(), branch_def_id=branch_def_id)
        return _BD.from_dict(source), None
    except KeyError:
        return None, f"Branch '{branch_def_id}' not found."


def _action_dry_inspect_node(kwargs: dict[str, Any]) -> str:
    from workflow.graph_compiler import inspect_node_dry

    bid = (kwargs.get("branch_def_id") or "").strip()
    nid = (kwargs.get("node_id") or "").strip()
    spec_json = (kwargs.get("branch_spec_json") or kwargs.get("spec_json") or "").strip()

    branch, err = _load_branch_for_inspect(bid, spec_json)
    if err:
        return json.dumps({"error": err})

    result = inspect_node_dry(branch, node_id=nid)
    return json.dumps(result, default=str)


def _apply_patch_ops(
    branch: Any,
    changes_json: str,
) -> tuple[Any, str | None]:
    """Apply patch_branch-style ops to a branch copy without persisting.

    Returns (patched_branch, error_str).  Uses the same op executor as
    the real patch_branch action but skips the DB write.
    """
    try:
        ops = json.loads(changes_json) if isinstance(changes_json, str) else changes_json
    except json.JSONDecodeError as exc:
        return None, f"changes_json is not valid JSON: {exc}"

    if not isinstance(ops, list):
        return None, "changes_json must be a JSON array of ops."

    from workflow.api.branches import _apply_patch_op
    from workflow.branches import BranchDefinition as _BD

    staged = _BD.from_dict(branch.to_dict())
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            return None, f"Op #{i} is not an object."
        err = _apply_patch_op(staged, op)
        if err:
            op_name = str(op.get("op") or "?")
            return None, f"Op #{i} {op_name} failed: {err}"

    try:
        return _BD.from_dict(staged.to_dict()), None
    except Exception as exc:  # noqa: BLE001
        return None, f"Patched branch could not be reconstructed: {exc}"


def _action_dry_inspect_patch(kwargs: dict[str, Any]) -> str:
    from workflow.graph_compiler import inspect_node_dry

    bid = (kwargs.get("branch_def_id") or "").strip()
    nid = (kwargs.get("node_id") or "").strip()
    changes_json = (kwargs.get("changes_json") or "").strip()
    spec_json = (kwargs.get("branch_spec_json") or kwargs.get("spec_json") or "").strip()

    if not changes_json:
        return json.dumps({"error": "changes_json is required for dry_inspect_patch."})

    branch, err = _load_branch_for_inspect(bid, spec_json)
    if err:
        return json.dumps({"error": err})

    patched, err2 = _apply_patch_ops(branch, changes_json)
    if err2:
        return json.dumps({"error": err2})

    result = inspect_node_dry(patched, node_id=nid)
    return json.dumps(result, default=str)


_INSPECT_DRY_ACTIONS: dict[str, Any] = {
    "dry_inspect_node": _action_dry_inspect_node,
    "dry_inspect_patch": _action_dry_inspect_patch,
}


# ───────────────────────────────────────────────────────────────────────────
# Teammate messaging
# ───────────────────────────────────────────────────────────────────────────


def _action_messaging_send(kwargs: dict[str, Any]) -> str:
    from workflow.runs import post_teammate_message

    from_run_id = kwargs.get("from_run_id", "").strip()
    to_node_id = kwargs.get("to_node_id", "").strip()
    message_type = kwargs.get("message_type", "").strip()
    body_raw = kwargs.get("body_json", "") or kwargs.get("body", "") or "{}"
    reply_to_id = kwargs.get("reply_to_message_id") or None

    if isinstance(body_raw, dict):
        body = body_raw
    else:
        try:
            body = json.loads(body_raw)
        except (json.JSONDecodeError, TypeError):
            return json.dumps({"error": "body_json is not valid JSON."})

    base_path = _base_path()
    try:
        record = post_teammate_message(
            base_path,
            from_run_id=from_run_id,
            to_node_id=to_node_id,
            message_type=message_type,
            body=body,
            reply_to_id=reply_to_id,
        )
    except (KeyError, ValueError, PermissionError) as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"message_id": record["message_id"], "delivered_at": record["sent_at"]})


def _action_messaging_receive(kwargs: dict[str, Any]) -> str:
    from workflow.runs import read_teammate_messages

    node_id = kwargs.get("node_id", "").strip()
    since = kwargs.get("since") or None
    raw_types = kwargs.get("message_types", "") or ""
    limit = int(kwargs.get("limit", 50) or 50)

    if isinstance(raw_types, list):
        message_types = [t.strip() for t in raw_types if t.strip()]
    elif isinstance(raw_types, str) and raw_types.strip():
        message_types = [t.strip() for t in raw_types.split(",") if t.strip()]
    else:
        message_types = None

    base_path = _base_path()
    try:
        messages = read_teammate_messages(
            base_path,
            node_id=node_id,
            since=since,
            message_types=message_types,
            limit=limit,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"messages": messages, "count": len(messages)})


def _action_messaging_ack(kwargs: dict[str, Any]) -> str:
    from workflow.runs import ack_teammate_message

    message_id = kwargs.get("message_id", "").strip()
    node_id = kwargs.get("node_id", "").strip()

    if not message_id:
        return json.dumps({"error": "message_id is required."})
    if not node_id:
        return json.dumps({"error": "node_id is required."})

    base_path = _base_path()
    try:
        result = ack_teammate_message(base_path, message_id=message_id, node_id=node_id)
    except KeyError as exc:
        return json.dumps({"error": str(exc)})
    except PermissionError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps(result)


_MESSAGING_ACTIONS: dict[str, Any] = {
    "messaging_send": _action_messaging_send,
    "messaging_receive": _action_messaging_receive,
    "messaging_ack": _action_messaging_ack,
}


# ── Scheduler MCP actions ─────────────────────────────────────────────────


def _action_schedule_branch(kwargs: dict[str, Any]) -> str:
    from workflow.runs import initialize_runs_db
    from workflow.scheduler import CronParseError, register_schedule

    branch_def_id = (kwargs.get("branch_def_id") or "").strip()
    if not branch_def_id:
        return json.dumps({"error": "branch_def_id is required."})
    cron_expr = (kwargs.get("cron_expr") or "").strip()
    interval_seconds = kwargs.get("interval_seconds") or 0.0
    try:
        interval_seconds = float(interval_seconds)
    except (TypeError, ValueError):
        interval_seconds = 0.0
    if not cron_expr and interval_seconds <= 0:
        return json.dumps({"error": "one of cron_expr or interval_seconds must be provided."})
    owner_actor = (kwargs.get("owner_actor") or "").strip() or "anonymous"
    raw_inputs = kwargs.get("inputs_template_json") or "{}"
    try:
        inputs_template = json.loads(raw_inputs) if isinstance(raw_inputs, str) else raw_inputs
    except (json.JSONDecodeError, TypeError):
        inputs_template = {}
    skip_if_running = bool(kwargs.get("skip_if_running", False))
    base = _base_path()
    initialize_runs_db(base)
    try:
        schedule_id = register_schedule(
            base,
            branch_def_id=branch_def_id,
            owner_actor=owner_actor,
            cron_expr=cron_expr,
            interval_seconds=interval_seconds,
            inputs_template=inputs_template,
            skip_if_running=skip_if_running,
        )
    except CronParseError as exc:
        return json.dumps({"error": f"Invalid cron_expr: {exc}"})
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({
        "status": "scheduled",
        "schedule_id": schedule_id,
        "branch_def_id": branch_def_id,
        "cron_expr": cron_expr,
        "interval_seconds": interval_seconds,
    })


def _action_unschedule_branch(kwargs: dict[str, Any]) -> str:
    from workflow.scheduler import unregister_schedule

    schedule_id = (kwargs.get("schedule_id") or "").strip()
    if not schedule_id:
        return json.dumps({"error": "schedule_id is required."})
    owner_actor = (kwargs.get("owner_actor") or "").strip() or "anonymous"
    base = _base_path()
    try:
        removed = unregister_schedule(base, schedule_id, requesting_actor=owner_actor)
    except PermissionError as exc:
        return json.dumps({"error": str(exc)})
    if not removed:
        return json.dumps({"error": f"schedule_id '{schedule_id}' not found."})
    return json.dumps({"status": "unscheduled", "schedule_id": schedule_id})


def _action_list_schedules(kwargs: dict[str, Any]) -> str:
    from workflow.runs import initialize_runs_db
    from workflow.scheduler import list_schedules

    owner_actor = (kwargs.get("owner_actor") or "").strip()
    active_only = bool(kwargs.get("active_only", True))
    base = _base_path()
    initialize_runs_db(base)
    rows = list_schedules(base, owner_actor=owner_actor, active_only=active_only)
    return json.dumps({"schedules": rows, "count": len(rows)})


def _action_subscribe_branch(kwargs: dict[str, Any]) -> str:
    from workflow.runs import initialize_runs_db
    from workflow.scheduler import VALID_EVENT_TYPES, register_subscription

    branch_def_id = (kwargs.get("branch_def_id") or "").strip()
    if not branch_def_id:
        return json.dumps({"error": "branch_def_id is required."})
    event_type = (kwargs.get("event_type") or "").strip()
    if not event_type:
        return json.dumps({"error": "event_type is required."})
    if event_type not in VALID_EVENT_TYPES:
        return json.dumps({
            "error": f"Unknown event_type '{event_type}'.",
            "valid": sorted(VALID_EVENT_TYPES),
        })
    owner_actor = (kwargs.get("owner_actor") or "").strip() or "anonymous"
    base = _base_path()
    initialize_runs_db(base)
    try:
        sub_id = register_subscription(
            base,
            branch_def_id=branch_def_id,
            owner_actor=owner_actor,
            event_type=event_type,
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({
        "status": "subscribed",
        "subscription_id": sub_id,
        "branch_def_id": branch_def_id,
        "event_type": event_type,
    })


def _action_unsubscribe_branch(kwargs: dict[str, Any]) -> str:
    from workflow.scheduler import unregister_subscription

    subscription_id = (kwargs.get("subscription_id") or "").strip()
    if not subscription_id:
        return json.dumps({"error": "subscription_id is required."})
    owner_actor = (kwargs.get("owner_actor") or "").strip() or "anonymous"
    base = _base_path()
    try:
        removed = unregister_subscription(base, subscription_id, requesting_actor=owner_actor)
    except PermissionError as exc:
        return json.dumps({"error": str(exc)})
    if not removed:
        return json.dumps({"error": f"subscription_id '{subscription_id}' not found."})
    return json.dumps({"status": "unsubscribed", "subscription_id": subscription_id})


def _action_pause_schedule(kwargs: dict[str, Any]) -> str:
    from workflow.scheduler import pause_schedule

    schedule_id = (kwargs.get("schedule_id") or "").strip()
    if not schedule_id:
        return json.dumps({"error": "schedule_id is required."})
    owner_actor = (kwargs.get("owner_actor") or "").strip() or "anonymous"
    base = _base_path()
    try:
        found = pause_schedule(base, schedule_id, requesting_actor=owner_actor)
    except PermissionError as exc:
        return json.dumps({"error": str(exc)})
    if not found:
        return json.dumps({"error": f"schedule_id '{schedule_id}' not found."})
    return json.dumps({"status": "paused", "schedule_id": schedule_id})


def _action_unpause_schedule(kwargs: dict[str, Any]) -> str:
    from workflow.scheduler import unpause_schedule

    schedule_id = (kwargs.get("schedule_id") or "").strip()
    if not schedule_id:
        return json.dumps({"error": "schedule_id is required."})
    owner_actor = (kwargs.get("owner_actor") or "").strip() or "anonymous"
    base = _base_path()
    try:
        found = unpause_schedule(base, schedule_id, requesting_actor=owner_actor)
    except PermissionError as exc:
        return json.dumps({"error": str(exc)})
    if not found:
        return json.dumps({"error": f"schedule_id '{schedule_id}' not found."})
    return json.dumps({"status": "unpaused", "schedule_id": schedule_id})


def _action_list_scheduler_subscriptions(kwargs: dict[str, Any]) -> str:
    from workflow.runs import initialize_runs_db
    from workflow.scheduler import list_scheduler_subscriptions

    owner_actor = (kwargs.get("owner_actor") or "").strip()
    event_type = (kwargs.get("event_type") or "").strip()
    active_only = bool(kwargs.get("active_only", True))
    base = _base_path()
    initialize_runs_db(base)
    rows = list_scheduler_subscriptions(
        base, owner_actor=owner_actor, event_type=event_type, active_only=active_only
    )
    return json.dumps({"subscriptions": rows, "count": len(rows)})


_SCHEDULER_ACTIONS: dict[str, Any] = {
    "schedule_branch": _action_schedule_branch,
    "unschedule_branch": _action_unschedule_branch,
    "list_schedules": _action_list_schedules,
    "subscribe_branch": _action_subscribe_branch,
    "unsubscribe_branch": _action_unsubscribe_branch,
    "pause_schedule": _action_pause_schedule,
    "unpause_schedule": _action_unpause_schedule,
    "list_scheduler_subscriptions": _action_list_scheduler_subscriptions,
}

