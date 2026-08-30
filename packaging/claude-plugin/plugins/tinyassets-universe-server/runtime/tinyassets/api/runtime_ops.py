"""Runtime-coordination subsystem — extracted from tinyassets/universe_server.py
(Task #13 — decomp Step 6).

Houses 4 small-to-medium action groups that share a common runtime-coordination
purpose: project-scoped memory, zero-side-effect dry inspection, teammate
messaging, and scheduler hooks. The MCP tool decoration stays in
``tinyassets/universe_server.py`` (Pattern A2 from the decomp plan); this
module is plain functions consumed via the ``extensions()`` MCP tool.

Public surface (back-compat re-exported via ``tinyassets.universe_server``):
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

Cross-module note: ``_current_actor`` lives in ``tinyassets.universe_server``
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

from tinyassets.api.helpers import _base_path

logger = logging.getLogger("universe_server.runtime_ops")


# ───────────────────────────────────────────────────────────────────────────

def _action_project_memory_get(kwargs: dict[str, Any]) -> str:
    from tinyassets.memory.project import project_memory_get

    project_id = kwargs.get("project_id", "").strip()
    key = kwargs.get("key", "").strip()
    if not project_id or not key:
        return json.dumps({"error": "project_id and key are required."})
    row = project_memory_get(_base_path(), project_id=project_id, key=key)
    if row is None:
        return json.dumps({"found": False, "project_id": project_id, "key": key})
    return json.dumps({"found": True, **row})


def _action_project_memory_set(kwargs: dict[str, Any]) -> str:
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.memory.project import project_memory_set

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
    from tinyassets.memory.project import project_memory_list

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
    from tinyassets.branches import BranchDefinition as _BD

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
        from tinyassets.daemon_server import get_branch_definition
        source = get_branch_definition(_base_path(), branch_def_id=branch_def_id)
        return _BD.from_dict(source), None
    except KeyError:
        return None, f"Branch '{branch_def_id}' not found."


def _action_dry_inspect_node(kwargs: dict[str, Any]) -> str:
    from tinyassets.graph_compiler import inspect_node_dry

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

    from tinyassets.api.branches import _apply_patch_op
    from tinyassets.branches import BranchDefinition as _BD

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
    from tinyassets.graph_compiler import inspect_node_dry

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
    from tinyassets.runs import post_teammate_message

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
    from tinyassets.runs import read_teammate_messages

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
    from tinyassets.runs import ack_teammate_message

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
#
# Ownership of a schedule is DERIVED from the authenticated request, never read
# from a caller field. ``owner_actor`` used to arrive in kwargs and default to
# "anonymous", which made registration an unauthenticated self-issued authority
# claim: anyone could schedule a branch and name whoever they liked as its owner.
# The five schedule actions below ignore that kwarg entirely (it survives on the
# ``extensions()`` signature only for the event-SUBSCRIPTION actions, a separate
# lane). Event subscriptions are not in scope for user-owned-automations 2.1.


def _schedule_request_universe(kwargs: dict[str, Any]) -> str:
    """The universe a schedule request is scoped to — the shared MCP resolver.

    An explicit ``universe_id`` wins, exactly as it does for every sibling action;
    an omitted one resolves to the authenticated founder's own home. Either way it
    is only a SCOPE: the admin-ACL and founder-home gates decide whether the
    request may act on it, so a caller naming someone else's universe is refused
    rather than obeyed.
    """
    from tinyassets.api.helpers import _request_universe

    return _request_universe(str(kwargs.get("universe_id") or ""))


def _schedule_request_owner(kwargs: dict[str, Any]) -> tuple[str, str, str | None]:
    """Return ``(actor, universe_id, error_json)`` for a schedule request.

    ``error_json`` is non-None when the request may not act on schedules at all:
    unauthenticated, without a current admin ACL on the universe it is scoped to,
    or scoped to a universe that is not the caller's own home.

    All three gates apply to CREATE and to LIST alike. They were not: list checked
    admin but not home, so an admin could name another universe and read its
    schedules — which branch runs, how often, when they last fired. Registration
    and reading a universe's automations are the same authority.
    """
    from tinyassets.api import permissions
    from tinyassets.daemon_server import get_founder_home, universe_access_permission

    if not permissions.is_authenticated_request():
        return "", "", json.dumps({
            "error": "authentication_required",
            "note": "A schedule belongs to a person. Sign in to register or change one.",
        })
    actor = permissions.current_actor_id()
    universe_id = _schedule_request_universe(kwargs)
    if not universe_id:
        return actor, "", json.dumps({"error": "universe_required"})
    base = _base_path()
    if universe_access_permission(
        base, universe_id=universe_id, actor_id=actor
    ) != "admin":
        return actor, universe_id, json.dumps({
            "error": "owner_not_admin",
            "universe_id": universe_id,
        })
    # An admin ACL says they may act on it; the home binding says the runs are
    # billed to their own subscription, which is the only place a background run
    # may draw from.
    if get_founder_home(base, actor) != universe_id:
        return actor, universe_id, json.dumps({
            "error": "not_owner_home",
            "universe_id": universe_id,
            "note": "Schedules run on your own universe's subscription.",
        })
    return actor, universe_id, None


def _action_schedule_branch(kwargs: dict[str, Any]) -> str:
    """Register a schedule for the authenticated owner's own universe.

    ``cron_expr`` is evaluated in **UTC**, not host-local time. That is both a
    user-facing fact and a correctness one: the cadence floor below is computed
    from wall-clock minute/hour algebra, which only equals elapsed time in a zone
    with no DST transitions.
    """
    from tinyassets.runs import initialize_runs_db
    from tinyassets.scheduler import (
        MIN_SCHEDULE_INTERVAL_S,
        CronParseError,
        is_running,
        min_cron_interval_seconds,
        register_schedule,
    )

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
    # Cadence floor: a scheduled run spends the OWNER's subscription, so a
    # sub-floor cadence is a way to drain them. Refuse rather than store it.
    # BOTH trigger kinds: the floor used to apply only to interval_seconds, so
    # `* * * * *` walked past it and fired every minute.
    if not cron_expr and interval_seconds < MIN_SCHEDULE_INTERVAL_S:
        return json.dumps({
            "error": "trigger_invalid",
            "reason": "interval_below_floor",
            "interval_seconds": interval_seconds,
            "minimum_interval_seconds": MIN_SCHEDULE_INTERVAL_S,
        })
    if cron_expr:
        try:
            cron_gap = min_cron_interval_seconds(cron_expr)
        except CronParseError as exc:
            return json.dumps({"error": f"Invalid cron_expr: {exc}"})
        if cron_gap < MIN_SCHEDULE_INTERVAL_S:
            return json.dumps({
                "error": "trigger_invalid",
                "reason": "cron_below_floor",
                "cron_expr": cron_expr,
                "minimum_interval_seconds": MIN_SCHEDULE_INTERVAL_S,
                "shortest_gap_seconds": cron_gap,
            })

    actor, universe_id, error = _schedule_request_owner(kwargs)
    if error is not None:
        return error

    base = _base_path()
    # D4 — fail loud at registration. A row stored while the tick loop is down is
    # a promise the daemon cannot keep; that silent storage is the defect this
    # change removes, so refuse instead of accepting it.
    if not is_running():
        return json.dumps({
            "error": "scheduler_unavailable",
            "reason": "scheduler_not_running",
        })

    raw_inputs = kwargs.get("inputs_template_json") or "{}"
    try:
        inputs_template = json.loads(raw_inputs) if isinstance(raw_inputs, str) else raw_inputs
    except (json.JSONDecodeError, TypeError):
        inputs_template = {}
    skip_if_running = bool(kwargs.get("skip_if_running", False))
    initialize_runs_db(base)
    try:
        schedule_id = register_schedule(
            base,
            branch_def_id=branch_def_id,
            owner_actor=f"universe:{universe_id}",
            universe_id=universe_id,
            owner_principal_id=actor,
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
        "universe_id": universe_id,
        "cron_expr": cron_expr,
        "interval_seconds": interval_seconds,
    })


def _schedule_row_universe(row: dict[str, Any], request_universe: str, actor: str) -> str:
    """The universe whose admins may control ``row``, or '' when none can.

    A derived row carries its own ``universe_id``. A MIGRATED row does not — the
    column did not exist when it was written — so its universe is recovered from
    the pre-2.1 ``owner_actor``: either ``universe:<id>`` or the bare principal
    whose home this is. Recovery is scoped to the universe the request is already
    entitled to, so it can never widen a caller's reach; it only makes rows an
    install already has controllable by the people who own them.

    A legacy row whose ``owner_actor`` matches neither is ORPHANED: no universe
    claims it, so no admin can act on it. Losing that row is the correct outcome
    of not being able to say whose it is — inventing an owner is the thing this
    change exists to stop.
    """
    from tinyassets.scheduler import legacy_owner_actors_for

    own = str(row.get("universe_id") or "").strip()
    if own:
        return own
    if not request_universe:
        return ""
    owner_actor = str(row.get("owner_actor") or "").strip()
    if owner_actor in legacy_owner_actors_for(
        request_universe, _recoverable_principals(request_universe, actor)
    ):
        return request_universe
    return ""


def _recoverable_principals(universe_id: str, actor: str) -> tuple[str, ...]:
    """Principals a legacy row's bare ``owner_actor`` may name for ``universe_id``.

    The caller, plus every founder whose home IS this universe. Without the
    second, a bare-founder legacy row was addressable only when that founder
    happened to be the caller — so a delegated admin of the universe could see
    the row but never delete it (Codex round 2, finding 6). Reading the registry
    is what makes "an admin of X can clean up X's legacy rows" true rather than
    true-for-one-person.
    """
    from tinyassets.daemon_server import founder_subs_for_universe

    principals = {actor} if actor else set()
    try:
        principals.update(founder_subs_for_universe(_base_path(), universe_id))
    except Exception:  # noqa: BLE001 - a registry read must not break the surface
        logger.warning(
            "schedule legacy recovery: founder lookup failed for %r",
            universe_id,
            exc_info=True,
        )
    return tuple(sorted(p for p in principals if p))


def _schedule_control_context(
    schedule_id: str, kwargs: dict[str, Any]
) -> tuple[dict[str, Any], str, str, str | None]:
    """Resolve ``(row, actor, row_universe, error_json)`` for pause/resume/delete.

    Authority is a CURRENT admin ACL on the row's own universe — not on whatever
    universe the request happens to name, which a caller controls. The stored
    ``owner_principal_id`` alone is not enough: a revoked owner could otherwise
    still pause and delete a row by id while being unable to list it, which is
    the inconsistency Codex found. A revoked owner learns why from the refusal
    the tick records, not from retaining control.
    """
    from tinyassets.api import permissions
    from tinyassets.daemon_server import universe_access_permission
    from tinyassets.scheduler import get_schedule

    if not permissions.is_authenticated_request():
        return {}, "", "", json.dumps({"error": "authentication_required"})
    actor = permissions.current_actor_id()
    base = _base_path()
    row = get_schedule(base, schedule_id)
    if row is None:
        return {}, actor, "", json.dumps(
            {"error": f"schedule_id '{schedule_id}' not found."}
        )
    row_universe = _schedule_row_universe(
        row, _schedule_request_universe(kwargs), actor
    )
    if not row_universe or universe_access_permission(
        base, universe_id=row_universe, actor_id=actor
    ) != "admin":
        return row, actor, row_universe, json.dumps({
            "error": "owner_not_admin",
            "schedule_id": schedule_id,
            "note": (
                "Controlling a schedule needs a current admin grant on the "
                "universe that owns it."
            ),
        })
    return row, actor, row_universe, None


def _action_unschedule_branch(kwargs: dict[str, Any]) -> str:
    from tinyassets.scheduler import unregister_schedule

    schedule_id = (kwargs.get("schedule_id") or "").strip()
    if not schedule_id:
        return json.dumps({"error": "schedule_id is required."})
    _row, actor, _uid, error = _schedule_control_context(schedule_id, kwargs)
    if error is not None:
        return error
    base = _base_path()
    try:
        # admin=True: `_schedule_control_context` has already proven a CURRENT
        # admin grant on the row's own universe, which is the authority. The
        # library's stored-owner comparison would additionally pass a revoked
        # owner, which is exactly what this surface must not do.
        removed = unregister_schedule(
            base, schedule_id, requesting_actor=actor, admin=True
        )
    except PermissionError as exc:
        return json.dumps({"error": str(exc)})
    if not removed:
        return json.dumps({"error": f"schedule_id '{schedule_id}' not found."})
    return json.dumps({"status": "unscheduled", "schedule_id": schedule_id})


#: Fields a schedule's owner sees on their own surface. The raw row also carries
#: the inputs template and the owner principal; the summary keeps what the owner
#: needs to answer "is this on, and did it run?" — including ``legacy``, which is
#: why a listed schedule can be active and still never fire.
_SCHEDULE_SUMMARY_FIELDS = (
    "schedule_id",
    "branch_def_id",
    "universe_id",
    "owner_actor",
    "cron_expr",
    "interval_seconds",
    "skip_if_running",
    "active",
    "paused",
    "pause_reason",
    "legacy",
    "created_at",
    "last_fired_at",
)


def _fresh_refusal_reasons(base: Any, universe_ids: set[str]) -> dict[str, str]:
    """Freshest ledger reason per ``schedule:<id>`` key across ``universe_ids``.

    Same read the automations surface does. A skipped attempt that does not pause
    the row (``skip_if_running``, ``run_fn_incompatible``, ``enqueue_error:*``)
    leaves no mark ON the row, so without this the owner's list said only that
    nothing had run lately and never why.
    """
    from tinyassets.runtime.assigned_queue_consumer import (
        assigned_queue_refusal_freshness_seconds,
    )
    from tinyassets.storage.assigned_queue_refusals import AssignedQueueRefusalStore

    reasons: dict[str, str] = {}
    store = AssignedQueueRefusalStore(base)
    window = assigned_queue_refusal_freshness_seconds()
    for uid in universe_ids:
        try:
            reasons.update(
                store.fresh_reasons(universe_id=uid, max_age_seconds=window)
            )
        except Exception:  # noqa: BLE001 - a projection read never fails the surface
            logger.warning(
                "schedule list: refusal read failed for %r", uid, exc_info=True
            )
    return reasons


def _action_list_schedules(kwargs: dict[str, Any]) -> str:
    from tinyassets.api import permissions
    from tinyassets.runs import initialize_runs_db
    from tinyassets.scheduler import REFUSAL_KEY_PREFIX, list_schedules

    if not permissions.is_authenticated_request():
        return json.dumps({"error": "authentication_required"})
    active_only = bool(kwargs.get("active_only", True))
    base = _base_path()
    initialize_runs_db(base)

    # Owner-scoped read: a schedule discloses which branch runs, how often, and
    # when it last fired — the owner's operational picture, so the admin gate
    # registration uses is the default path.
    actor, universe_id, error = _schedule_request_owner(kwargs)
    if error is None:
        # MIGRATED legacy rows carry universe_id='' and would be invisible to the
        # only people who may delete them, so they are recovered by owner_actor:
        # `universe:<id>`, the caller, or a founder whose home this universe is.
        rows = list_schedules(
            base,
            universe_id=universe_id,
            legacy_owner_actors=_recoverable_principals(universe_id, actor),
            active_only=active_only,
        )
        scope = "universe"
    else:
        # The person a refusal is ABOUT is often the one who can no longer pass
        # that gate: `owner_lost_admin` and `not_owner_home` are exactly the
        # states that lock an owner out of the surface telling them why their
        # schedule stopped. Fall back to a READ of their own rows — never
        # control, which stays admin-only (Codex round 2, finding 2).
        rows = list_schedules(
            base, owner_principal_id=actor, active_only=active_only
        )
        if not rows:
            # No rows of their own: this is a stranger naming someone else's
            # universe, and they get the refusal rather than an empty list.
            return error
        universe_id = ""
        scope = "owner"

    reasons = _fresh_refusal_reasons(
        base, {str(row.get("universe_id") or "") for row in rows}
    )
    summaries = []
    for row in rows:
        summary = {field: row.get(field) for field in _SCHEDULE_SUMMARY_FIELDS}
        summary["recent_reason"] = reasons.get(
            f"{REFUSAL_KEY_PREFIX}{row.get('schedule_id')}"
        )
        summaries.append(summary)
    return json.dumps({
        "universe_id": universe_id,
        "scope": scope,
        "schedules": summaries,
        "count": len(summaries),
    })


def _action_subscribe_branch(kwargs: dict[str, Any]) -> str:
    from tinyassets.runs import initialize_runs_db
    from tinyassets.scheduler import VALID_EVENT_TYPES, register_subscription

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
    from tinyassets.scheduler import unregister_subscription

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
    from tinyassets.scheduler import pause_schedule

    schedule_id = (kwargs.get("schedule_id") or "").strip()
    if not schedule_id:
        return json.dumps({"error": "schedule_id is required."})
    _row, actor, _uid, error = _schedule_control_context(schedule_id, kwargs)
    if error is not None:
        return error
    base = _base_path()
    try:
        # admin=True: the context has already proven a CURRENT admin grant on the
        # row's own universe. See _action_unschedule_branch.
        found = pause_schedule(base, schedule_id, requesting_actor=actor, admin=True)
    except PermissionError as exc:
        return json.dumps({"error": str(exc)})
    if not found:
        return json.dumps({"error": f"schedule_id '{schedule_id}' not found."})
    return json.dumps({"status": "paused", "schedule_id": schedule_id})


def _action_unpause_schedule(kwargs: dict[str, Any]) -> str:
    from tinyassets.scheduler import unpause_schedule

    schedule_id = (kwargs.get("schedule_id") or "").strip()
    if not schedule_id:
        return json.dumps({"error": "schedule_id is required."})
    _row, actor, _uid, error = _schedule_control_context(schedule_id, kwargs)
    if error is not None:
        return error
    base = _base_path()
    try:
        # admin=True: the context has already proven a CURRENT admin grant on the
        # row's own universe. See _action_unschedule_branch.
        found = unpause_schedule(base, schedule_id, requesting_actor=actor, admin=True)
    except PermissionError as exc:
        return json.dumps({"error": str(exc)})
    if not found:
        return json.dumps({"error": f"schedule_id '{schedule_id}' not found."})
    return json.dumps({"status": "unpaused", "schedule_id": schedule_id})


def _action_list_scheduler_subscriptions(kwargs: dict[str, Any]) -> str:
    from tinyassets.runs import initialize_runs_db
    from tinyassets.scheduler import list_scheduler_subscriptions

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

