"""Universe MCP tool surface — extracted from
``workflow/universe_server.py`` (Task #7 — decomp Step 9).

The largest single submodule extracted from the monolith: 27 universe-tool
``_action_*`` handlers (universe-CRUD, daemon control, canon, queue,
subscriptions, goal-pool, daemon overview, tier config), the ``WRITE_ACTIONS``
dispatch table + 14 ``_extract_*`` extractor closures, the ledger dispatcher
trio (``_ledger_target_dir`` / ``_scope_universe_response`` /
``_dispatch_with_ledger``), the daemon telemetry block (``_last_activity_at``,
``_staleness_bucket``, ``_phase_human``, ``_compute_accept_rate_from_db``,
``_compute_word_count_from_files``, ``_daemon_liveness``,
``_parse_activity_line``), and the Pattern A2 body of the ``universe()`` MCP
tool exposed as ``_universe_impl(action, **kwargs)``.

The ``@mcp.tool() def universe(...)`` decorator + 23-arg signature + chatbot-
facing docstring stays in ``workflow/universe_server.py`` (Pattern A2) so
FastMCP introspection sees the surface unchanged. The wrapper there delegates
to ``_universe_impl()`` from this module.

Public surface (back-compat re-exported via ``workflow.universe_server``):
    WRITE_ACTIONS                       : dispatch table (14 write actions)
    _extract_*                          : 14 extractor closures
    _ledger_target_dir                  : universe-dir resolver for ledger entries
    _scope_universe_response            : #15 contract — `Universe: <id>` text lead-in
    _dispatch_with_ledger               : universe-tool ledger wrapper
    _universe_impl                      : Pattern A2 body for the ``universe()`` MCP tool
    _last_activity_at, _staleness_bucket, _phase_human :
                                          daemon telemetry primitives
    _compute_accept_rate_from_db        : reads ``<udir>/story.db`` directly
    _compute_word_count_from_files      : walks ``<udir>/output/**/*.md``
    _daemon_liveness                    : composite liveness block (test-monkeypatched)
    _parse_activity_line                : activity-log line parser (single-caller helper)
    _action_*                           : 27 universe-tool handlers
    _list_output_tree, _trim_overview_for_bytes, _overview_limits,
    _tail_file_lines, _query_world_db, _normalize_escaped_text,
    _goal_pool_not_available, _paid_market_not_available :
                                          handler-scoped helpers

Cross-module note: ``_current_actor``, ``_truncate``, ``_append_ledger``,
``_upload_whitelist_prefixes`` (and ``_storage_backend``,
``_format_dirty_file_conflict``, ``_format_commit_failed`` if needed by future
edits) live in ``workflow.universe_server`` (preamble engine helpers
territory) and are lazy-imported inside the functions that use them. This
avoids the load-time cycle (universe_server back-compat-imports symbols from
this module). Step 10 (``engine_helpers.py``) will retarget these lazy imports
to ``workflow.api.engine_helpers``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from workflow.api.helpers import (
    _base_path,
    _default_universe,
    _read_json,
    _read_text,
    _universe_dir,
)
from workflow.catalog import list_unreconciled_writes
from workflow.universe_soul import (
    SOUL_FILENAME,
    ensure_universe_soul,
    has_soul,
    legacy_premise_path,
    premise_from_soul,
    read_legacy_premise,
    read_universe_soul,
    write_universe_soul,
)

logger = logging.getLogger("universe_server.universe")

ENV_CAPABILITIES_VAR = "UNIVERSE_SERVER_CAPABILITIES"
ACTION_SUBMIT_PRIORITY_REQUEST = "submit_priority_request"
ACTION_CANCEL_BRANCH_TASK = "cancel_branch_task"
ACTION_POST_PRIORITY_GOAL_POOL = "post_priority_goal_pool"


def _env_actor_grants() -> tuple[str, ...]:
    raw = os.environ.get(ENV_CAPABILITIES_VAR, "")
    return tuple(part for part in re.split(r"[\s,]+", raw.strip()) if part)


def _env_actor_can(action: str, *, universe_id: str = "") -> bool:
    from workflow.auth.provider import PermissionScope, resolve_permission

    actor = os.environ.get("UNIVERSE_SERVER_USER", "anonymous")
    grants = _env_actor_grants()
    return resolve_permission(
        actor_id=actor,
        action=action,
        grants=grants,
        scope=PermissionScope(universe_id=universe_id),
    ).allowed

# WRITE_ACTIONS is the single source of truth for which `universe` tool
# actions are writes. The dispatcher consults this table; any action
# registered here is funneled through `_dispatch_with_ledger`, which
# refuses to return a success response without first writing the ledger
# entry. To add a new write action: put its name here with extractors for
# (target, summary, payload). No handler-side ledger code is needed — and
# no handler can silently skip the ledger.
#
# Each entry maps action name -> extractor callable:
#   extractor(kwargs, result_dict) -> (target: str, summary: str, payload: dict | None)
# kwargs is the normalized handler kwargs. result_dict is the parsed JSON
# of the handler's return string (used to pick up server-generated IDs like
# request_id / note_id).


def _extract_submit_request(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    return (
        str(result.get("request_id", "")),
        _truncate(kwargs.get("text", "")),
        {
            "request_type": kwargs.get("request_type", "") or None,
            "branch_id": kwargs.get("branch_id", "") or None,
            "pickup_incentive": kwargs.get("pickup_incentive", "") or None,
            "directed_daemon_id": kwargs.get("directed_daemon_id", "") or None,
            "request_classification": result.get("request_classification"),
        },
    )


def _extract_give_direction(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    return (
        kwargs.get("target") or str(result.get("note_id", "")),
        _truncate(kwargs.get("text", "")),
        {
            "category": kwargs.get("category", "direction"),
            "note_id": result.get("note_id", ""),
            "anchor": result.get("anchor", {}),
        },
    )


def _extract_set_premise(
    kwargs: dict[str, Any], _result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    text = kwargs.get("text", "")
    return (
        SOUL_FILENAME,
        _truncate(text),
        {
            "bytes": len(text.encode("utf-8")),
            "legacy_program_mirror": "PROGRAM.md",
        },
    )


def _extract_add_canon(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    name = result.get("filename", "") or kwargs.get("filename", "")
    provenance = kwargs.get("provenance_tag", "")
    return (
        f"canon/{name}",
        _truncate(f"{name} ({provenance or 'untagged'})"),
        {
            "filename": name,
            "provenance": provenance,
            "bytes": len(kwargs.get("text", "").encode("utf-8")),
        },
    )


def _extract_add_canon_from_path(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    name = result.get("filename", "") or Path(kwargs.get("path", "")).name
    provenance = kwargs.get("provenance_tag", "") or "user_upload"
    bytes_written = result.get("bytes_written", 0)
    return (
        f"canon/sources/{name}",
        _truncate(f"{name} ({provenance}, {bytes_written} bytes)"),
        {
            "filename": name,
            "provenance": provenance,
            "source_path": kwargs.get("path", ""),
            "bytes": bytes_written,
            "synthesis_signal": result.get("synthesis_signal_emitted", False),
        },
    )


def _extract_control_daemon(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    return (
        ".pause",
        str(result.get("action", kwargs.get("text", "").strip().lower())),
        {"status": result.get("status", "")},
    )


def _extract_switch_universe(
    kwargs: dict[str, Any], _result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    uid = kwargs.get("universe_id", "")
    return (uid, f"daemon switched to {uid}", {})


def _extract_create_universe(
    kwargs: dict[str, Any], _result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    uid = kwargs.get("universe_id", "")
    text = kwargs.get("text", "")
    summary = _truncate(text) if text.strip() else f"created {uid}"
    return (uid, summary, {
        "has_premise": bool(text.strip()),
        "has_soul": True,
        "soul_path": SOUL_FILENAME,
    })


def _synthesis_first_run_checklist(has_premise: bool) -> dict[str, Any]:
    """Explain when upload synthesis signals become actionable on first run."""
    steps = [
        {
            "id": "premise",
            "label": "Save a soul purpose with create_universe text or set_premise.",
            "complete": has_premise,
        },
        {
            "id": "canon_source",
            "label": "Upload at least one canon source with add_canon or add_canon_from_path.",
            "complete": False,
        },
        {
            "id": "synthesis_signal",
            "label": "Confirm the upload response reports synthesis_signal_emitted=true.",
            "complete": False,
        },
        {
            "id": "daemon_worldbuild",
            "label": "Let the daemon process the synthesize_source signal in a worldbuild cycle.",
            "complete": False,
        },
    ]
    if has_premise:
        next_action = (
            "Upload canon with add_canon or add_canon_from_path, then wait for "
            "the daemon to process the synthesize_source signal."
        )
    else:
        next_action = (
            "Set a premise before uploading canon; synthesis needs the premise "
            "and source material to produce useful context."
        )
    return {
        "synthesis_signal_meaning": (
            "synthesis_signal_emitted only means an uploaded source was queued; "
            "it is meaningful after a premise exists, at least one canon source "
            "has been uploaded, and the daemon has processed the synthesize_source "
            "signal."
        ),
        "steps": steps,
        "next_action": next_action,
    }


# action name -> (extractor, control_daemon_gate)
# control_daemon_gate: if set, the wrapper only logs when the daemon action
# was an actual write (pause/resume), not a read (status).
def _extract_queue_cancel(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    return (
        str(kwargs.get("branch_task_id", "")),
        _truncate(f"cancel {kwargs.get('branch_task_id', '')}"),
        {"status": result.get("status", "")},
    )


def _extract_subscribe_goal(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    g = str(kwargs.get("goal_id", ""))
    return (g, _truncate(f"subscribe {g}"), {"status": result.get("status", "")})


def _extract_unsubscribe_goal(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    g = str(kwargs.get("goal_id", ""))
    return (g, _truncate(f"unsubscribe {g}"), {"status": result.get("status", "")})


def _extract_post_to_goal_pool(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    g = str(kwargs.get("goal_id", ""))
    bd = str(kwargs.get("branch_def_id", ""))
    return (
        str(result.get("path", f"goal_pool/{g}")),
        _truncate(f"post {bd} to {g}"),
        {
            "goal_id": g,
            "branch_def_id": bd,
            "status": result.get("status", ""),
        },
    )


def _extract_submit_node_bid(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    nb = str(result.get("node_bid_id", ""))
    nd = str(kwargs.get("node_def_id", ""))
    bid = kwargs.get("bid", 0.0)
    return (
        str(result.get("path", f"bids/{nb}.yaml")),
        _truncate(f"bid {bid} for node {nd}"),
        {
            "node_bid_id": nb,
            "node_def_id": nd,
            "bid": bid,
            "status": result.get("status", ""),
        },
    )


def _extract_set_tier_config(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    tier_name = str(kwargs.get("tier", ""))
    en = bool(kwargs.get("enabled", False))
    return (
        f"tier/{tier_name}",
        _truncate(f"set_tier_config {tier_name}={en}"),
        {
            "tier": tier_name,
            "enabled": en,
            "status": result.get("status", ""),
        },
    )


def _extract_daemon_create(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    daemon = result.get("daemon", {}) if isinstance(result.get("daemon"), dict) else {}
    daemon_id = str(daemon.get("daemon_id") or "")
    name = str(daemon.get("display_name") or "")
    return (
        daemon_id,
        _truncate(f"create daemon {name}"),
        {
            "soul_mode": daemon.get("soul_mode"),
            "has_soul": daemon.get("has_soul"),
            "domain_claims": daemon.get("domain_claims", []),
        },
    )


def _extract_daemon_summon(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    runtime = result.get("runtime", {}) if isinstance(result.get("runtime"), dict) else {}
    runtime_id = str(runtime.get("runtime_instance_id") or "")
    provider = str(runtime.get("provider_name") or "")
    daemon_id = str(runtime.get("daemon_id") or "")
    return (
        runtime_id,
        _truncate(f"summon {daemon_id} on {provider}"),
        {
            "daemon_id": daemon_id,
            "provider_name": provider,
            "model_name": runtime.get("model_name"),
            "status": runtime.get("status"),
        },
    )


def _extract_daemon_banish(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    runtime = result.get("runtime", {}) if isinstance(result.get("runtime"), dict) else {}
    runtime_id = str(runtime.get("runtime_instance_id") or "")
    return (
        runtime_id,
        _truncate(f"banish runtime {runtime_id}"),
        {
            "daemon_id": runtime.get("daemon_id"),
            "status": runtime.get("status"),
        },
    )


def _extract_daemon_control(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    runtime_id = str(result.get("runtime_instance_id") or "")
    action = str(result.get("action") or kwargs.get("action", "daemon_control"))
    return (
        runtime_id or str(result.get("daemon_id", "")),
        _truncate(f"{action} {runtime_id}"),
        {
            "daemon_id": result.get("daemon_id"),
            "runtime_instance_id": result.get("runtime_instance_id"),
            "authority_scope": result.get("authority_scope"),
            "effect": result.get("effect"),
            "action_id": result.get("action_id"),
        },
    )


def _extract_daemon_update_behavior(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    daemon_id = str(result.get("daemon_id") or "")
    return (
        daemon_id,
        _truncate(f"update daemon behavior {daemon_id}"),
        {
            "daemon_id": daemon_id,
            "authority_scope": result.get("authority_scope"),
            "effect": result.get("effect"),
            "action_id": result.get("action_id"),
        },
    )


def _extract_daemon_memory_capture(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    entry = result.get("entry", {}) if isinstance(result.get("entry"), dict) else {}
    entry_id = str(entry.get("entry_id") or "")
    daemon_id = str(result.get("daemon_id") or entry.get("daemon_id") or "")
    return (
        entry_id,
        _truncate(f"capture daemon memory {daemon_id}"),
        {
            "daemon_id": daemon_id,
            "entry_id": entry_id,
            "memory_kind": entry.get("memory_kind"),
            "promotion_state": entry.get("promotion_state"),
        },
    )


def _extract_daemon_memory_review(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    entry_id = str(result.get("entry_id") or "")
    daemon_id = str(result.get("daemon_id") or "")
    decision = str(result.get("decision") or "")
    return (
        entry_id,
        _truncate(f"{decision} daemon memory {entry_id}"),
        {
            "daemon_id": daemon_id,
            "entry_id": entry_id,
            "decision": decision,
        },
    )


def _extract_daemon_memory_promote(
    kwargs: dict[str, Any], result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    from workflow.api.engine_helpers import _truncate
    promotion_id = str(result.get("promotion_id") or "")
    daemon_id = str(result.get("daemon_id") or "")
    return (
        promotion_id,
        _truncate(f"promote daemon memory {daemon_id}"),
        {
            "daemon_id": daemon_id,
            "promotion_id": promotion_id,
            "entry_ids": result.get("entry_ids", []),
            "promoted_count": result.get("promoted_count", 0),
        },
    )


WRITE_ACTIONS: dict[str, Any] = {
    "submit_request": (_extract_submit_request, None),
    "give_direction": (_extract_give_direction, None),
    "set_premise": (_extract_set_premise, None),
    "add_canon": (_extract_add_canon, None),
    "add_canon_from_path": (_extract_add_canon_from_path, None),
    "control_daemon": (_extract_control_daemon, {"pause", "resume"}),
    "switch_universe": (_extract_switch_universe, None),
    "create_universe": (_extract_create_universe, None),
    "queue_cancel": (_extract_queue_cancel, None),
    "subscribe_goal": (_extract_subscribe_goal, None),
    "unsubscribe_goal": (_extract_unsubscribe_goal, None),
    "post_to_goal_pool": (_extract_post_to_goal_pool, None),
    "submit_node_bid": (_extract_submit_node_bid, None),
    "set_tier_config": (_extract_set_tier_config, None),
    "daemon_create": (_extract_daemon_create, None),
    "daemon_summon": (_extract_daemon_summon, None),
    "daemon_banish": (_extract_daemon_banish, None),
    "daemon_pause": (_extract_daemon_control, None),
    "daemon_resume": (_extract_daemon_control, None),
    "daemon_restart": (_extract_daemon_control, None),
    "daemon_update_behavior": (_extract_daemon_update_behavior, None),
    "daemon_memory_capture": (_extract_daemon_memory_capture, None),
    "daemon_memory_review": (_extract_daemon_memory_review, None),
    "daemon_memory_promote": (_extract_daemon_memory_promote, None),
}


def _ledger_target_dir(action: str, kwargs: dict[str, Any]) -> Path:
    """Resolve which universe directory owns the ledger entry for this action.

    create_universe writes to the newly-created universe's ledger. All others
    write to the universe whose state they affect (the handler's target uid).
    """
    uid = kwargs.get("universe_id", "") or _default_universe()
    if action == "create_universe":
        return _base_path() / uid
    return _universe_dir(uid)


def _scope_universe_response(result_str: str) -> str:
    """Ensure every universe-scoped response leads with a `Universe: <id>`
    header and puts `universe_id` as the first key.

    #15 contract: downstream reasoning must be able to ground a response to
    its universe without re-reading the full JSON. On phones the bot often
    summarizes; a phone-legible `text` lead-in survives summarization even
    when deep JSON fields don't.

    Responses that aren't a dict, aren't JSON, or have no `universe_id`
    field are returned unchanged — errors without universe context must
    not claim a universe, and multi-universe responses (e.g. list) stay
    as-is.
    """
    try:
        data = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return result_str
    if not isinstance(data, dict):
        return result_str
    uid = data.get("universe_id")
    if not isinstance(uid, str) or not uid:
        return result_str

    header = f"Universe: {uid}"
    scoped: dict[str, Any] = {"universe_id": uid}
    existing_text = data.get("text")
    if isinstance(existing_text, str) and existing_text.strip():
        scoped["text"] = f"{header}\n\n{existing_text}"
    else:
        scoped["text"] = header
    for k, v in data.items():
        if k in ("universe_id", "text"):
            continue
        scoped[k] = v
    return json.dumps(scoped, default=str)


def _dispatch_with_ledger(
    action: str,
    handler: Any,
    kwargs: dict[str, Any],
) -> str:
    """Enforce: every WRITE action lands in the public ledger before returning.

    If the handler returned an error or the action is a write gate that was
    actually a read (e.g. control_daemon text=status), no ledger entry is
    written. For all successful writes, we parse the result, derive the
    attribution fields via the declared extractor, and append the entry.

    Ledger append failures degrade gracefully (logged warning): the mutation
    has already landed on disk, so refusing to return success would be worse
    than missing one audit entry.

    Every return path passes through `_scope_universe_response` so any
    universe-scoped dict gets the `Universe: <id>` text lead-in and key
    reordering (#15).
    """
    from workflow.api.engine_helpers import _append_ledger
    result_str = handler(**kwargs)

    spec = WRITE_ACTIONS.get(action)
    if spec is None:
        return _scope_universe_response(result_str)

    extractor, write_gate = spec

    try:
        result = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return _scope_universe_response(result_str)

    if not isinstance(result, dict) or "error" in result:
        return _scope_universe_response(result_str)

    # control_daemon branch — only append if actually a write
    if write_gate is not None:
        daemon_action = (kwargs.get("text") or "").strip().lower()
        if daemon_action not in write_gate:
            return _scope_universe_response(result_str)

    try:
        target, summary, payload = extractor(kwargs, result)
        udir = _ledger_target_dir(action, kwargs)
        _append_ledger(
            udir, action, target=target, summary=summary, payload=payload,
        )
    except Exception as exc:
        logger.warning("Ledger extraction failed for %s: %s", action, exc)

    return _scope_universe_response(result_str)


# ---------------------------------------------------------------------------
# Daemon telemetry — liveness, staleness, human-readable phase
# ---------------------------------------------------------------------------
# The daemon writes `current_phase` and `last_updated` into status.json via
# `domains.fantasy_daemon.phases._activity.update_phase`. status.json itself
# is not a heartbeat — it only moves when a phase transitions. For liveness
# we also consult `activity.log`, which is appended to on every node entry,
# `.runtime_status.json`, which is refreshed while the graph process is alive,
# and PROGRAM.md + work_targets.json to disambiguate "no premise" vs
# "starved for work" vs "actually running".


# Staleness buckets, in seconds. Chosen to match the lead's spec: <1h fresh,
# <24h idle, >24h dormant. "fresh" is the only bucket that should be read
# as "the daemon is alive right now".
_STALE_FRESH_SECONDS = 60 * 60
_STALE_IDLE_SECONDS = 24 * 60 * 60


def _last_activity_at(udir: Path, status: dict[str, Any] | None) -> str | None:
    """Return the most recent heartbeat ISO timestamp we can find.

    Uses the newest of activity.log mtime (node progress),
    .runtime_status.json mtime (running-process heartbeat), status.json's
    `last_updated`, and status.json file mtime. Returns None only if nothing
    on disk indicates the daemon ever ran.
    """
    heartbeat_candidates: list[datetime] = []

    for path in (udir / "activity.log", udir / ".runtime_status.json"):
        if not path.exists():
            continue
        try:
            heartbeat_candidates.append(
                datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
            )
        except OSError:
            pass
    if heartbeat_candidates:
        return max(heartbeat_candidates).isoformat()

    if status and isinstance(status, dict):
        last_updated = status.get("last_updated")
        if isinstance(last_updated, str) and last_updated:
            try:
                parsed = datetime.fromisoformat(last_updated)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc).isoformat()
            except ValueError:
                pass

    status_path = udir / "status.json"
    if status_path.exists():
        try:
            return datetime.fromtimestamp(
                status_path.stat().st_mtime, tz=timezone.utc,
            ).isoformat()
        except OSError:
            pass

    return None


def _staleness_bucket(last_activity_iso: str | None) -> str:
    """Classify liveness from a last-activity timestamp.

    Returns one of: "fresh" (<1h), "idle" (<24h), "dormant" (>=24h), or
    "never" (no timestamp recorded). Callers that previously trusted
    `daemon_state: running` from status.json should consult this instead.
    """
    if not last_activity_iso:
        return "never"
    try:
        ts = datetime.fromisoformat(last_activity_iso)
    except (TypeError, ValueError):
        return "never"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    if age < _STALE_FRESH_SECONDS:
        return "fresh"
    if age < _STALE_IDLE_SECONDS:
        return "idle"
    return "dormant"


def _phase_human(
    raw_phase: str | None,
    has_premise: bool,
    has_work: bool,
    is_paused: bool,
    staleness: str,
) -> str:
    """Translate raw daemon state into a legible phase for downstream readers.

    Precedence: paused > dormant-no-premise > dormant > no-premise > starved
    > raw_phase > idle. Chat clients and humans both need a single sentence
    that explains why nothing is happening; the raw phase alone ("unknown",
    "dispatch_execution") is not enough when no premise or no work exists.
    """
    if is_paused:
        return "paused"
    if staleness == "dormant":
        if not has_premise:
            return "dormant-no-premise"
        if not has_work:
            return "dormant-starved"
        return "dormant"
    if not has_premise:
        return "idle-no-premise"
    if not has_work:
        return "starved"
    if raw_phase and raw_phase not in ("", "unknown"):
        return raw_phase
    return "idle"


def _compute_accept_rate_from_db(
    udir: Path,
) -> tuple[float | None, dict[str, Any]]:
    """Derive accept_rate directly from scene_history.

    Returns (rate, sample) where rate is None when no evaluated scenes exist,
    and sample carries the raw counts so downstream readers can tell the
    difference between "0% accepted" and "nothing evaluated yet". This is
    deliberately read-time — status.json's cached `accept_rate` is never
    updated by the daemon today, so reading it is misleading.
    """
    db_path = udir / "story.db"
    sample: dict[str, Any] = {"accepted": 0, "evaluated": 0, "source": "none"}
    if not db_path.exists():
        return None, sample

    try:
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='scene_history'",
            ).fetchone()
            if not row:
                return None, sample
            # Only scenes that have been judged count toward the rate.
            # `pending` means not yet evaluated — not a reject.
            evaluated = conn.execute(
                "SELECT COUNT(*) FROM scene_history "
                "WHERE verdict IS NOT NULL AND verdict != '' "
                "AND verdict != 'pending'",
            ).fetchone()[0]
            accepted = conn.execute(
                "SELECT COUNT(*) FROM scene_history "
                "WHERE verdict IN ('accept', 'second_draft')",
            ).fetchone()[0]
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("Failed to read scene_history from %s: %s", db_path, exc)
        return None, sample

    sample = {"accepted": accepted, "evaluated": evaluated, "source": "scene_history"}
    if evaluated == 0:
        return None, sample
    return accepted / evaluated, sample


def _compute_word_count_from_files(
    udir: Path,
) -> tuple[int, dict[str, Any]]:
    """Derive word_count by reading prose files on disk.

    Returns (total_words, sample). `status.json::word_count` is a cached
    value maintained by `DashboardMetrics` in the daemon process — it's
    only flushed during runs, never corrected when output files are
    added/removed/moved, and can drift wildly across universe switches.
    Reading the files is slower but always truthful.

    The walk covers `output/**/*.md` under the universe directory, which
    matches where commit writes prose (`output/book-{N}/chapter-{NN}/
    scene-{NN}.md`). Non-scene markdown (canon/, INDEX.md, progress.md)
    lives outside `output/` so it won't be double-counted.

    Returns `(0, {"source": "none"})` when there's no output directory
    yet — callers should treat that distinctly from "0 words written".
    """
    out_dir = udir / "output"
    sample: dict[str, Any] = {"scenes": 0, "source": "none"}
    if not out_dir.is_dir():
        return 0, sample

    total = 0
    scenes = 0
    try:
        for path in out_dir.rglob("*.md"):
            if not path.is_file():
                continue
            name = path.name
            # Skip index files; only prose counts. Scene files are
            # scene-*.md; chapter-*.md is a chapter-level wrapper we don't
            # want to double-count if both exist. Count anything under
            # output/ that looks like prose.
            if name.startswith(".") or name in {"INDEX.md", "progress.md"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            total += len(text.split())
            if name.startswith("scene-"):
                scenes += 1
    except OSError as exc:
        logger.debug("word_count walk failed at %s: %s", out_dir, exc)
        return 0, {"scenes": 0, "source": "error"}

    sample = {"scenes": scenes, "source": "output_files"}
    return total, sample


def _daemon_liveness(udir: Path, status: dict[str, Any] | None) -> dict[str, Any]:
    """Build the shared liveness block used by list, inspect, and status.

    Centralizing this shape is the point — every reader surface gets the
    same interpreted fields, so legibility fixes in one place land
    everywhere at once.
    """
    has_premise = bool(
        read_legacy_premise(udir).strip() or premise_from_soul(udir).strip()
    )
    targets = _read_json(udir / "work_targets.json")
    has_work = isinstance(targets, list) and any(
        t.get("lifecycle") == "active" for t in targets if isinstance(t, dict)
    )
    is_paused = (udir / ".pause").exists()
    last_activity = _last_activity_at(udir, status)
    staleness = _staleness_bucket(last_activity)

    raw_phase: str | None = None
    if status and isinstance(status, dict):
        # status.json uses `current_phase`; older callers wrote `phase`.
        # Accept both for defense in depth, prefer the canonical name.
        raw_phase = status.get("current_phase") or status.get("phase")

    accept_rate, accept_sample = _compute_accept_rate_from_db(udir)
    # word_count comes from prose on disk, NOT status.json — the cached
    # value there is a DashboardMetrics snapshot that drifts across
    # universe switches. Reading files is slower but truthful.
    word_count, word_count_sample = _compute_word_count_from_files(udir)

    return {
        "phase": raw_phase or "offline",
        "phase_human": _phase_human(
            raw_phase, has_premise, has_work, is_paused, staleness,
        ),
        "is_paused": is_paused,
        "has_premise": has_premise,
        "has_soul": has_soul(udir),
        "has_work": has_work,
        "last_activity_at": last_activity,
        "staleness": staleness,
        "word_count": word_count,
        "word_count_sample": word_count_sample,
        "accept_rate": accept_rate,
        "accept_rate_sample": accept_sample,
    }


def _action_list_universes(**_kwargs: Any) -> str:
    base = _base_path()
    if not base.is_dir():
        return json.dumps({
            "universes": [],
            "count": 0,
            "note": f"Base directory does not exist: {base}",
        })

    try:
        all_entries = list(base.iterdir())
    except OSError as exc:
        return json.dumps({
            "universes": [],
            "count": 0,
            "note": f"Base directory unreadable ({base}): {exc}",
        })

    universes = []
    for child in sorted(all_entries):
        if not child.is_dir() or child.name.startswith("."):
            continue
        status = _read_json(child / "status.json")
        liveness = _daemon_liveness(child, status if isinstance(status, dict) else None)
        info: dict[str, Any] = {
            "id": child.name,
            "has_premise": liveness["has_premise"],
            "has_soul": liveness["has_soul"],
            "word_count": liveness["word_count"],
            "phase": liveness["phase"],
            "phase_human": liveness["phase_human"],
            "staleness": liveness["staleness"],
            "last_activity_at": liveness["last_activity_at"],
            "accept_rate": liveness["accept_rate"],
        }
        universes.append(info)

    result: dict[str, Any] = {"universes": universes, "count": len(universes)}
    if not universes:
        if not all_entries:
            result["note"] = f"Base directory is empty: {base}"
        else:
            result["note"] = (
                f"Base directory has {len(all_entries)} entries but none "
                f"are valid universes (all hidden or non-directories): {base}"
            )
    return json.dumps(result)


def _action_inspect_universe(universe_id: str = "", **_kwargs: Any) -> str:
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)

    if not udir.is_dir():
        return json.dumps({
            "error": f"Universe '{uid}' not found.",
            "available": [
                d.name for d in _base_path().iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ] if _base_path().is_dir() else [],
        })

    result: dict[str, Any] = {"universe_id": uid}

    # Daemon liveness block — always present, so downstream readers (humans
    # and chat clients) can always tell whether the daemon is alive, why
    # it's stuck, and whether the premise and work exist.
    status = _read_json(udir / "status.json")
    liveness = _daemon_liveness(udir, status if isinstance(status, dict) else None)
    result["daemon"] = {
        "phase": liveness["phase"],
        "phase_human": liveness["phase_human"],
        "is_paused": liveness["is_paused"],
        "has_premise": liveness["has_premise"],
        "has_soul": liveness["has_soul"],
        "has_work": liveness["has_work"],
        "last_activity_at": liveness["last_activity_at"],
        "staleness": liveness["staleness"],
        "word_count": liveness["word_count"],
        "word_count_sample": liveness["word_count_sample"],
        "accept_rate": liveness["accept_rate"],
        "accept_rate_sample": liveness["accept_rate_sample"],
    }

    soul = read_universe_soul(udir)
    if soul is not None:
        result["has_soul"] = True
        result["soul"] = soul.summary()

    # Premise remains the public compatibility field. The durable source is
    # now soul.md when PROGRAM.md is absent or empty.
    program = _normalize_escaped_text(read_legacy_premise(udir))
    premise = program.strip() or (soul.purpose if soul is not None else "")
    result["has_premise"] = bool(premise)
    if premise:
        result["premise"] = premise[:500] + ("..." if len(premise) > 500 else "")
        result["premise_source"] = (
            "PROGRAM.md" if program.strip() else SOUL_FILENAME
        )

    # Notes summary
    notes = _read_json(udir / "notes.json")
    if notes and isinstance(notes, list):
        recent = notes[-5:]
        result["recent_notes"] = [
            {
                "source": n.get("source"),
                "category": n.get("category"),
                "text": n.get("text", "")[:200],
                "timestamp": n.get("timestamp"),
            }
            for n in recent
        ]

    # Work targets
    targets = _read_json(udir / "work_targets.json")
    if targets and isinstance(targets, list):
        active = [t for t in targets if t.get("lifecycle") == "active"][:5]
        result["active_targets"] = [
            {
                "id": t.get("target_id"),
                "title": t.get("title"),
                "role": t.get("role"),
                "intent": t.get("current_intent"),
            }
            for t in active
        ]

    # Output files
    output_dir = udir / "output"
    if output_dir.is_dir():
        result["output_files"] = _list_output_tree(output_dir)

    # Activity tail
    activity = _read_text(udir / "activity.log")
    if activity:
        lines = activity.strip().splitlines()
        result["recent_activity"] = lines[-10:]

    # Pending requests
    from workflow.work_targets import REQUESTS_FILENAME
    requests = _read_json(udir / REQUESTS_FILENAME)
    if requests and isinstance(requests, list):
        pending = [r for r in requests if r.get("status") == "pending"]
        if pending:
            result["pending_requests"] = len(pending)

    # Cross-surface hint — helps chatbots discover cross-domain work even
    # when the active universe is themed (e.g. a particular novel or
    # standup tracker). The workspace is one container; goals, branches,
    # and wiki span all domains.
    result["cross_surface_hint"] = {
        "note": (
            "This workspace is one container; cross-domain branches and Goals "
            "live at extensions + goals + wiki regardless of this workspace's theme."
        ),
        "paths": [
            {
                "action": "extensions action=list_branches",
                "purpose": "All workflows across all domains",
            },
            {
                "action": "goals action=list",
                "purpose": (
                    "Domain-agnostic intents "
                    "(research, software, science, fantasy, etc.)"
                ),
            },
            {
                "action": "wiki action=search",
                "purpose": "Cross-domain notes, bugs, and design plans",
            },
            {
                "action": "universe action=list",
                "purpose": "Other workspaces if multiple exist",
            },
        ],
    }

    return json.dumps(result, default=str)


def _list_output_tree(output_dir: Path, max_depth: int = 3) -> list[str]:
    """Walk the output directory and return relative paths."""
    files = []
    for root, dirs, filenames in os.walk(output_dir):
        depth = len(Path(root).relative_to(output_dir).parts)
        if depth >= max_depth:
            dirs.clear()
            continue
        for f in sorted(filenames):
            rel = Path(root, f).relative_to(output_dir)
            if not f.startswith("."):
                files.append(str(rel))
    return files[:50]


def _action_read_output(universe_id: str = "", path: str = "", **_kwargs: Any) -> str:
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    target = (udir / "output" / path).resolve()

    if not target.is_relative_to((udir / "output").resolve()):
        return json.dumps({"error": "Path traversal not allowed."})
    if not target.exists():
        return json.dumps({"error": f"File not found: {path}"})

    content = _read_text(target)
    if len(content) > 10000:
        return json.dumps({
            "universe_id": uid,
            "path": path,
            "content": content[:10000],
            "truncated": True,
            "total_chars": len(content),
            "note": "File truncated to 10K chars. Request specific sections if needed.",
        })
    return json.dumps({
        "universe_id": uid,
        "path": path,
        "content": content,
        "truncated": False,
    })


_SUBMIT_REQUEST_MAX_BYTES = 8192


def _action_submit_request(
    universe_id: str = "",
    text: str = "",
    request_type: str = "scene_direction",
    branch_id: str = "",
    priority_weight: float = 0.0,
    pickup_incentive: str = "",
    directed_daemon_id: str = "",
    directed_daemon_instruction: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.api.market import (
        PATCH_REQUEST_AUTHORITY_BOUNDARY,
        classify_patch_request,
        normalize_patch_request_incentive,
    )
    from workflow.branch_tasks import BranchTask, append_task, new_task_id
    from workflow.work_targets import REQUESTS_FILENAME

    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})

    # 8 KiB cap keeps requests.json bounded and discourages pasting
    # entire drafts into the request channel (add_canon is the right
    # tool for that). UTF-8 byte length, not char count.
    text_bytes = len(text.encode("utf-8"))
    if text_bytes > _SUBMIT_REQUEST_MAX_BYTES:
        return json.dumps({
            "error": (
                f"Request text exceeds {_SUBMIT_REQUEST_MAX_BYTES} bytes "
                f"({text_bytes} submitted). Summarize or split into "
                "multiple requests. For long prose, use `add_canon` "
                "instead."
            ),
        })

    valid_types = {
        "scene_direction", "revision", "canon_change",
        "branch_proposal", "general",
    }
    if request_type not in valid_types:
        request_type = "general"

    # Invariant 9: priority_weight cap. Negative values reject for all
    # actors. Non-host clamped to 0 silently (preflight §4.3 #9).
    try:
        pw = float(priority_weight)
    except (TypeError, ValueError):
        pw = 0.0
    if pw < 0:
        return json.dumps({
            "error": "priority_weight must be >= 0.",
        })
    source = os.environ.get("UNIVERSE_SERVER_USER", "anonymous")
    can_prioritize = _env_actor_can(
        ACTION_SUBMIT_PRIORITY_REQUEST,
        universe_id=uid,
    )
    if not can_prioritize:
        pw = 0.0

    request_id = f"req_{int(time.time())}_{os.urandom(4).hex()}"
    incentive = normalize_patch_request_incentive(
        str(pickup_incentive or ""),
        requester_id=source,
    )
    authority_boundary = dict(PATCH_REQUEST_AUTHORITY_BOUNDARY)
    requester_directed_daemon: dict[str, Any] | None = None
    if directed_daemon_id.strip():
        from workflow.daemon_registry import (
            build_requester_directed_daemon_assignment,
        )

        requester_directed_daemon = build_requester_directed_daemon_assignment(
            _base_path(),
            daemon_id=directed_daemon_id.strip(),
            requester_id=source,
            patch_request_id=request_id,
            instruction=directed_daemon_instruction or text,
        )
        if requester_directed_daemon.get("effect") == "refused":
            return json.dumps({
                "error": "directed_daemon_not_authorized",
                "requester_directed_daemon": requester_directed_daemon,
            })
    request_classification = classify_patch_request(
        text=text,
        request_type=request_type,
        requester_id=source,
        priority_authorized=can_prioritize,
        directed_daemon=requester_directed_daemon is not None,
    )
    request_obj = {
        "id": request_id,
        "type": request_type,
        "text": text,
        "branch_id": branch_id or None,
        "status": "pending",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "pickup_incentive": incentive,
        "authority_boundary": authority_boundary,
        "request_classification": request_classification,
    }
    if requester_directed_daemon is not None:
        request_obj["requester_directed_daemon"] = requester_directed_daemon

    requests_path = udir / REQUESTS_FILENAME
    existing = _read_json(requests_path)
    if not isinstance(existing, list):
        existing = []
    existing.append(request_obj)

    try:
        udir.mkdir(parents=True, exist_ok=True)
        requests_path.write_text(
            json.dumps(existing, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError as exc:
        return json.dumps({"error": f"Failed to write request: {exc}"})

    # Phase E: also queue a BranchTask so the dispatcher can score +
    # schedule. host submissions land as host_request tier; anyone
    # else lands as user_request. The WorkTarget still gets
    # materialized by UserRequestProducer from requests.json on the
    # next producer cycle — BranchTask wraps the execution intent.
    branch_task_id = ""
    try:
        task = BranchTask(
            branch_task_id=new_task_id(),
            branch_def_id="fantasy_author:universe_cycle_wrapper",
            universe_id=uid,
            inputs={
                "work_target_ref": None,
                "request_id": request_id,
                "request_type": request_type,
                "branch_id": branch_id or "",
                "pickup_incentive": incentive,
                "authority_boundary": authority_boundary,
                "request_classification": request_classification,
                "requester_directed_daemon": requester_directed_daemon,
            },
            trigger_source=(
                "owner_queued"
                if requester_directed_daemon is not None
                else "operator_request" if can_prioritize else "user_request"
            ),
            priority_weight=pw,
            pickup_signal_weight=float(incentive.get("pickup_signal_weight") or 0.0),
            directed_daemon_id=(
                str(requester_directed_daemon.get("daemon_id", ""))
                if requester_directed_daemon is not None else ""
            ),
        )
        append_task(udir, task)
        branch_task_id = task.branch_task_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to queue BranchTask for %s: %s", request_id, exc)

    pending_count = sum(
        1 for r in existing
        if isinstance(r, dict) and r.get("status") == "pending"
    )
    ahead = max(0, pending_count - 1)
    if ahead == 0:
        position_note = "yours is next in the daemon's queue"
    elif ahead == 1:
        position_note = "1 other request is ahead of yours"
    else:
        position_note = f"{ahead} other requests are ahead of yours"

    return json.dumps({
        "universe_id": uid,
        "request_id": request_id,
        "branch_task_id": branch_task_id,
        "status": "pending",
        "priority_weight": pw,
        "pickup_incentive": incentive,
        "authority_boundary": authority_boundary,
        "request_classification": request_classification,
        "requester_directed_daemon": requester_directed_daemon,
        "queue_position": pending_count,
        "ahead_of_yours": ahead,
        "what_happens_next": (
            f"The daemon will see your request on its next review cycle; "
            f"{position_note}. Use `universe action=inspect universe_id={uid}` "
            "to watch the queue or check whether your request is now active work."
        ),
    })


def _action_queue_list(
    universe_id: str = "",
    **_kwargs: Any,
) -> str:
    """Read ``branch_tasks.json`` fresh (no in-memory cache) and
    return sorted+scored queue. Includes ``tier_status`` per R11.
    """
    from workflow.branch_tasks import read_queue
    from workflow.dispatcher import (
        load_dispatcher_config,
        score_task,
    )

    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})

    try:
        queue = read_queue(udir)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({
            "universe_id": uid,
            "error": f"Failed to read queue: {exc}",
        })

    cfg = load_dispatcher_config(udir)
    now_iso = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for task in queue:
        row = task.to_dict()
        row["score"] = score_task(task, now_iso=now_iso, config=cfg)
        row["tier_enabled"] = cfg.tier_enabled(task.trigger_source)
        rows.append(row)
    # Primary: status pending first, then score desc. Non-pending
    # sorted by queued_at desc.
    rows.sort(
        key=lambda r: (
            0 if r.get("status") == "pending" else 1,
            -float(r.get("score", 0.0)),
            r.get("queued_at", ""),
        ),
    )

    return json.dumps({
        "universe_id": uid,
        "queue": rows,
        "pending_count": sum(1 for r in rows if r.get("status") == "pending"),
        "running_count": sum(1 for r in rows if r.get("status") == "running"),
        "tier_status": cfg.tier_status_map(),
    })


# ---------------------------------------------------------------------------
# Daemon roster + runtime actions
# ---------------------------------------------------------------------------


def _parse_inputs_object(inputs_json: str) -> tuple[dict[str, Any], str | None]:
    if not inputs_json.strip():
        return {}, None
    try:
        parsed = json.loads(inputs_json)
    except json.JSONDecodeError as exc:
        return {}, f"inputs_json invalid JSON: {exc}"
    if not isinstance(parsed, dict):
        return {}, "inputs_json must be a JSON object."
    return parsed, None


def _action_daemon_list(
    universe_id: str = "",
    limit: Any = 30,
    **_kwargs: Any,
) -> str:
    from workflow.daemon_registry import list_daemons, list_runtime_instances

    uid = universe_id or _default_universe()
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 30
    if n <= 0:
        n = 30
    daemons = list_daemons(_base_path())[:n]
    runtimes = list_runtime_instances(_base_path(), universe_id=uid)
    return json.dumps({
        "universe_id": uid,
        "daemons": daemons,
        "runtimes": runtimes,
        "count": len(daemons),
        "runtime_count": len(runtimes),
    }, default=str)


def _action_daemon_get(
    inputs_json: str = "",
    node_def_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.daemon_registry import get_daemon

    data, err = _parse_inputs_object(inputs_json)
    if err:
        return json.dumps({"error": err})
    daemon_id = str(data.get("daemon_id") or node_def_id or "").strip()
    if not daemon_id:
        return json.dumps({"error": "daemon_id is required."})
    try:
        daemon = get_daemon(
            _base_path(),
            daemon_id=daemon_id,
            include_soul=bool(data.get("include_soul", False)),
        )
    except KeyError:
        return json.dumps({"error": f"Daemon '{daemon_id}' not found."})
    return json.dumps({"daemon": daemon}, default=str)


def _action_daemon_create(
    universe_id: str = "",
    inputs_json: str = "",
    text: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.daemon_registry import create_daemon

    data, err = _parse_inputs_object(inputs_json)
    if err:
        return json.dumps({"error": err})
    display_name = str(data.get("display_name") or text or "").strip()
    if not display_name:
        return json.dumps({"error": "display_name is required."})
    try:
        daemon = create_daemon(
            _base_path(),
            display_name=display_name,
            created_by=_current_actor(),
            soul_mode=str(data.get("soul_mode") or "").strip() or None,
            soul_text=str(data.get("soul_text") or ""),
            domain_claims=data.get("domain_claims")
            if isinstance(data.get("domain_claims"), list)
            else None,
            lineage_parent_id=str(data.get("lineage_parent_id") or "").strip() or None,
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({
        "universe_id": universe_id or _default_universe(),
        "daemon": daemon,
    }, default=str)


def _action_daemon_summon(
    universe_id: str = "",
    inputs_json: str = "",
    branch_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.daemon_registry import summon_daemon

    data, err = _parse_inputs_object(inputs_json)
    if err:
        return json.dumps({"error": err})
    daemon_id = str(data.get("daemon_id") or "").strip()
    provider_name = str(data.get("provider_name") or "").strip()
    model_name = str(data.get("model_name") or provider_name).strip()
    uid = universe_id or str(data.get("universe_id") or "").strip() or _default_universe()
    if not daemon_id:
        return json.dumps({"error": "daemon_id is required."})
    if not provider_name:
        return json.dumps({"error": "provider_name is required."})
    try:
        runtime = summon_daemon(
            _base_path(),
            daemon_id=daemon_id,
            universe_id=uid,
            provider_name=provider_name,
            model_name=model_name,
            branch_id=branch_id or data.get("branch_id") or None,
            created_by=_current_actor(),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
        )
    except KeyError:
        return json.dumps({"error": f"Daemon '{daemon_id}' not found."})
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"universe_id": uid, "runtime": runtime}, default=str)


def _action_daemon_banish(
    universe_id: str = "",
    inputs_json: str = "",
    branch_task_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.daemon_registry import control_runtime_instance

    data, err = _parse_inputs_object(inputs_json)
    if err:
        return json.dumps({"error": err})
    runtime_id = str(data.get("runtime_instance_id") or branch_task_id or "").strip()
    if not runtime_id:
        return json.dumps({"error": "runtime_instance_id is required."})
    try:
        result = control_runtime_instance(
            _base_path(),
            runtime_instance_id=runtime_id,
            actor_id=_current_actor(),
            action="banish",
        )
    except KeyError:
        return json.dumps({"error": f"Runtime '{runtime_id}' not found."})
    result["universe_id"] = universe_id or _default_universe()
    return json.dumps(result, default=str)


def _action_daemon_runtime_control(
    action_name: str,
    *,
    universe_id: str = "",
    inputs_json: str = "",
    branch_task_id: str = "",
) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.daemon_registry import control_runtime_instance

    data, err = _parse_inputs_object(inputs_json)
    if err:
        return json.dumps({"error": err})
    runtime_id = str(data.get("runtime_instance_id") or branch_task_id or "").strip()
    if not runtime_id:
        return json.dumps({"error": "runtime_instance_id is required."})
    try:
        result = control_runtime_instance(
            _base_path(),
            runtime_instance_id=runtime_id,
            actor_id=_current_actor(),
            action=action_name,
        )
    except KeyError:
        return json.dumps({"error": f"Runtime '{runtime_id}' not found."})
    result["universe_id"] = universe_id or _default_universe()
    return json.dumps(result, default=str)


def _action_daemon_pause(
    universe_id: str = "",
    inputs_json: str = "",
    branch_task_id: str = "",
    **_kwargs: Any,
) -> str:
    return _action_daemon_runtime_control(
        "pause",
        universe_id=universe_id,
        inputs_json=inputs_json,
        branch_task_id=branch_task_id,
    )


def _action_daemon_resume(
    universe_id: str = "",
    inputs_json: str = "",
    branch_task_id: str = "",
    **_kwargs: Any,
) -> str:
    return _action_daemon_runtime_control(
        "resume",
        universe_id=universe_id,
        inputs_json=inputs_json,
        branch_task_id=branch_task_id,
    )


def _action_daemon_restart(
    universe_id: str = "",
    inputs_json: str = "",
    branch_task_id: str = "",
    **_kwargs: Any,
) -> str:
    return _action_daemon_runtime_control(
        "restart",
        universe_id=universe_id,
        inputs_json=inputs_json,
        branch_task_id=branch_task_id,
    )


def _action_daemon_update_behavior(
    universe_id: str = "",
    inputs_json: str = "",
    text: str = "",
    node_def_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.daemon_registry import update_daemon_behavior

    data, err = _parse_inputs_object(inputs_json)
    if err:
        return json.dumps({"error": err})
    daemon_id = str(data.get("daemon_id") or node_def_id or "").strip()
    if not daemon_id:
        return json.dumps({"error": "daemon_id is required."})
    behavior = data.get("behavior_update")
    if not isinstance(behavior, dict):
        behavior = {"note": text.strip()} if text.strip() else {}
    if not behavior:
        return json.dumps({"error": "behavior_update is required."})
    try:
        result = update_daemon_behavior(
            _base_path(),
            daemon_id=daemon_id,
            actor_id=_current_actor(),
            behavior_update=behavior,
            apply_now=bool(data.get("apply_now") or data.get("apply")),
        )
    except KeyError:
        return json.dumps({"error": f"Daemon '{daemon_id}' not found."})
    result["universe_id"] = universe_id or _default_universe()
    return json.dumps(result, default=str)


def _action_daemon_control_status(
    universe_id: str = "",
    inputs_json: str = "",
    node_def_id: str = "",
    branch_task_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.daemon_registry import daemon_control_status

    data, err = _parse_inputs_object(inputs_json)
    if err:
        return json.dumps({"error": err})
    result = daemon_control_status(
        _base_path(),
        actor_id=_current_actor(),
        daemon_id=str(data.get("daemon_id") or node_def_id or "").strip() or None,
        runtime_instance_id=(
            str(data.get("runtime_instance_id") or branch_task_id or "").strip()
            or None
        ),
        universe_id=universe_id or str(data.get("universe_id") or "").strip() or None,
    )
    result["universe_id"] = universe_id or _default_universe()
    return json.dumps(result, default=str)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_string_list(value: Any) -> list[str] | None:
    if value is None or value == "":
        return None
    if isinstance(value, list):
        out = [str(item).strip() for item in value if str(item).strip()]
        return out or None
    if isinstance(value, str):
        out = [part.strip() for part in value.split(",") if part.strip()]
        return out or None
    return None


def _daemon_memory_inputs(
    inputs_json: str,
    *,
    node_def_id: str = "",
) -> tuple[dict[str, Any], str, str | None]:
    data, err = _parse_inputs_object(inputs_json)
    if err:
        return {}, "", err
    daemon_id = str(data.get("daemon_id") or node_def_id or "").strip()
    if not daemon_id:
        return data, "", "daemon_id is required."
    return data, daemon_id, None


def _action_daemon_memory_capture(
    universe_id: str = "",
    inputs_json: str = "",
    text: str = "",
    node_def_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.daemon_brain import capture_daemon_memory

    uid = universe_id or _default_universe()
    data, daemon_id, err = _daemon_memory_inputs(inputs_json, node_def_id=node_def_id)
    if err:
        return json.dumps({"universe_id": uid, "error": err})
    content = str(data.get("content") or text or "").strip()
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else None
    temporal_bounds = (
        data.get("temporal_bounds") if isinstance(data.get("temporal_bounds"), dict)
        else None
    )
    try:
        entry = capture_daemon_memory(
            _base_path(),
            daemon_id=daemon_id,
            content=content,
            memory_kind=str(data.get("memory_kind") or "semantic"),
            source_type=str(data.get("source_type") or "manual"),
            source_id=str(data.get("source_id") or _current_actor() or "manual"),
            source_path=str(data.get("source_path") or ""),
            source_hash=str(data.get("source_hash") or ""),
            reliability=str(data.get("reliability") or ""),
            temporal_bounds=temporal_bounds,
            language_type=str(data.get("language_type") or ""),
            confidence=float(data.get("confidence", 0.5)),
            importance=float(data.get("importance", 0.5)),
            sensitivity_tier=str(data.get("sensitivity_tier") or "normal"),
            visibility=str(data.get("visibility") or "host_private"),
            promotion_state=str(data.get("promotion_state") or "candidate"),
            supersedes_entry_id=(
                str(data.get("supersedes_entry_id")).strip()
                if data.get("supersedes_entry_id") else None
            ),
            metadata=metadata,
        )
    except (KeyError, ValueError, TypeError) as exc:
        return json.dumps({"universe_id": uid, "error": str(exc)})
    return json.dumps({"universe_id": uid, "daemon_id": daemon_id, "entry": entry}, default=str)


def _action_daemon_memory_search(
    universe_id: str = "",
    inputs_json: str = "",
    text: str = "",
    filter_text: str = "",
    limit: Any = 5,
    node_def_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.daemon_brain import search_daemon_memory

    uid = universe_id or _default_universe()
    data, daemon_id, err = _daemon_memory_inputs(inputs_json, node_def_id=node_def_id)
    if err:
        return json.dumps({"universe_id": uid, "error": err})
    query = str(data.get("query") or text or filter_text or "").strip()
    try:
        result = search_daemon_memory(
            _base_path(),
            daemon_id=daemon_id,
            query=query,
            limit=int(data.get("limit", limit)),
            min_score=float(data.get("min_score", 0.0)),
            include_superseded=_as_bool(data.get("include_superseded", False)),
            memory_kinds=_as_string_list(data.get("memory_kinds")),
            visibility=(
                str(data.get("visibility")).strip()
                if data.get("visibility") else None
            ),
        )
    except (KeyError, ValueError, TypeError) as exc:
        return json.dumps({"universe_id": uid, "error": str(exc)})
    result["universe_id"] = uid
    return json.dumps(result, default=str)


def _action_daemon_memory_list(
    universe_id: str = "",
    inputs_json: str = "",
    limit: Any = 50,
    node_def_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.daemon_brain import list_daemon_memory

    uid = universe_id or _default_universe()
    data, daemon_id, err = _daemon_memory_inputs(inputs_json, node_def_id=node_def_id)
    if err:
        return json.dumps({"universe_id": uid, "error": err})
    try:
        result = list_daemon_memory(
            _base_path(),
            daemon_id=daemon_id,
            limit=int(data.get("limit", limit)),
            include_superseded=_as_bool(data.get("include_superseded", False)),
            memory_kinds=_as_string_list(data.get("memory_kinds")),
        )
    except (KeyError, ValueError, TypeError) as exc:
        return json.dumps({"universe_id": uid, "error": str(exc)})
    result["universe_id"] = uid
    return json.dumps(result, default=str)


def _action_daemon_memory_review(
    universe_id: str = "",
    inputs_json: str = "",
    text: str = "",
    branch_task_id: str = "",
    node_def_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.daemon_brain import review_daemon_memory

    uid = universe_id or _default_universe()
    data, daemon_id, err = _daemon_memory_inputs(inputs_json, node_def_id=node_def_id)
    if err:
        return json.dumps({"universe_id": uid, "error": err})
    entry_id = str(data.get("entry_id") or branch_task_id or "").strip()
    if not entry_id:
        return json.dumps({"universe_id": uid, "error": "entry_id is required."})
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else None
    try:
        result = review_daemon_memory(
            _base_path(),
            daemon_id=daemon_id,
            entry_id=entry_id,
            decision=str(data.get("decision") or text or ""),
            reviewer_id=str(data.get("reviewer_id") or _current_actor() or "host"),
            note=str(data.get("note") or ""),
            superseded_by_entry_id=(
                str(data.get("superseded_by_entry_id")).strip()
                if data.get("superseded_by_entry_id") else None
            ),
            metadata=metadata,
        )
    except (KeyError, ValueError, TypeError) as exc:
        return json.dumps({"universe_id": uid, "error": str(exc)})
    result["universe_id"] = uid
    return json.dumps(result, default=str)


def _action_daemon_memory_promote(
    universe_id: str = "",
    inputs_json: str = "",
    text: str = "",
    branch_task_id: str = "",
    node_def_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.daemon_brain import promote_daemon_memory_to_wiki

    uid = universe_id or _default_universe()
    data, daemon_id, err = _daemon_memory_inputs(inputs_json, node_def_id=node_def_id)
    if err:
        return json.dumps({"universe_id": uid, "error": err})
    entry_ids = _as_string_list(data.get("entry_ids")) or _as_string_list(branch_task_id)
    summary = str(data.get("summary") or text or "").strip()
    target_rel_path = str(data.get("target_rel_path") or "pages/brain/review.md")
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else None
    try:
        result = promote_daemon_memory_to_wiki(
            _base_path(),
            daemon_id=daemon_id,
            entry_ids=entry_ids or [],
            summary=summary,
            target_rel_path=target_rel_path,
            metadata=metadata,
        )
    except (KeyError, ValueError, TypeError) as exc:
        return json.dumps({"universe_id": uid, "error": str(exc)})
    result["universe_id"] = uid
    return json.dumps(result, default=str)


def _action_daemon_memory_status(
    universe_id: str = "",
    inputs_json: str = "",
    node_def_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.daemon_brain import memory_observability_status

    uid = universe_id or _default_universe()
    data, daemon_id, err = _daemon_memory_inputs(inputs_json, node_def_id=node_def_id)
    if err:
        return json.dumps({"universe_id": uid, "error": err})
    try:
        result = memory_observability_status(_base_path(), daemon_id=daemon_id)
    except (KeyError, ValueError, TypeError) as exc:
        return json.dumps({"universe_id": uid, "error": str(exc)})
    result["universe_id"] = uid
    return json.dumps(result, default=str)


def _action_treasury_status(
    universe_id: str = "",
    limit: Any = 10,
    **_kwargs: Any,
) -> str:
    from workflow.treasury import treasury_status

    uid = universe_id or _default_universe()
    try:
        result = treasury_status(_base_path(), limit=int(limit))
    except (ValueError, TypeError) as exc:
        return json.dumps({"universe_id": uid, "error": str(exc)})
    result["universe_id"] = uid
    return json.dumps(result, default=str)


# ---------------------------------------------------------------------------
# Phase H — daemon_overview + set_tier_config (aggregated MCP surface)
# ---------------------------------------------------------------------------

# 1-second TTL cache per universe for daemon_overview (R1 invariant 1).
_OVERVIEW_CACHE: dict[str, tuple[float, str, str]] = {}
_OVERVIEW_TTL_SECONDS = 1.0

# Per-caller reasonable limits (R14 response-size). Overridable via `limit`.
_OVERVIEW_DEFAULT_LIMITS = {
    "queue_top": 20,
    "bids_top": 20,
    "settlements_recent": 10,
    "gates_recent": 10,
    "activity_tail": 30,
}
# Absolute cap even when `limit=full` — prevents pathological responses.
_OVERVIEW_ABSOLUTE_CAP = {
    "queue_top": 500,
    "bids_top": 500,
    "settlements_recent": 500,
    "gates_recent": 200,
    "activity_tail": 1000,
}

# R14 serialized-byte cap. Per-field caps above are necessary but not
# sufficient: a dense queue + long activity_tail + many bids can still
# blow past Claude.ai token limits even with each field individually
# bounded. If the serialized response exceeds this threshold, trim in
# priority order (see _OVERVIEW_TRIM_ORDER). Gates + dispatcher +
# subscriptions are NEVER trimmed (load-bearing per reviewer polish
# #5).
DAEMON_OVERVIEW_MAX_BYTES = 32_768

# Trim priority when the byte cap fires. Each entry is
# ``(key, subkey, keep_side)``:
# - ``key``: top-level response field.
# - ``subkey``: nested key (e.g. ``response["bids"]["recent"]``) or
#   None for top-level lists.
# - ``keep_side``: "head" keeps the front of the list (sorted
#   descending — top-N); "tail" keeps the back (chronological —
#   latest entries).
_OVERVIEW_TRIM_ORDER = (
    ("activity_tail", None, "tail"),
    ("settlements", "recent", "head"),
    ("bids", "recent", "head"),
    ("queue", "top", "head"),
)


def _trim_overview_for_bytes(
    response: dict[str, Any], *, cap: int = DAEMON_OVERVIEW_MAX_BYTES,
) -> str:
    """Serialize ``response`` and trim until ``<= cap`` bytes.

    Mutates ``response`` in place as fields shrink. When any trim
    lands, sets ``response["truncated"] = True`` so consumers know
    counters (``*_count`` fields) are authoritative over the trimmed
    lists. Gates + dispatcher + subscriptions are never in the trim
    order (load-bearing). Returns the final serialized JSON.
    """
    serialized = json.dumps(response, default=str)
    if len(serialized.encode("utf-8")) <= cap:
        return serialized
    response["truncated"] = True
    for key, subkey, keep_side in _OVERVIEW_TRIM_ORDER:
        container: Any = response.get(key)
        if subkey is not None:
            container = container.get(subkey) if isinstance(container, dict) else None
        if not isinstance(container, list):
            continue
        while container:
            if len(container) <= 1:
                container.clear()
            elif keep_side == "tail":
                # Halve from the front, keep the latest entries.
                del container[: len(container) // 2]
            else:
                # Halve from the back, keep top-ranked entries.
                del container[len(container) // 2:]
            serialized = json.dumps(response, default=str)
            if len(serialized.encode("utf-8")) <= cap:
                return serialized
    return serialized


def _overview_limits(limit_param: Any) -> dict[str, int]:
    """Resolve per-field limits from the `limit` param.

    `limit` int → applies that value to all top-N lists (bounded by
    absolute cap). `limit="full"` → absolute cap (not truly unbounded).
    Default / invalid → documented defaults.
    """
    if isinstance(limit_param, str) and limit_param.strip().lower() == "full":
        return dict(_OVERVIEW_ABSOLUTE_CAP)
    try:
        n = int(limit_param)
    except (TypeError, ValueError):
        return dict(_OVERVIEW_DEFAULT_LIMITS)
    if n <= 0:
        return dict(_OVERVIEW_DEFAULT_LIMITS)
    return {
        key: min(n, _OVERVIEW_ABSOLUTE_CAP[key])
        for key in _OVERVIEW_DEFAULT_LIMITS
    }


def _tail_file_lines(path: Path, n: int) -> list[str]:
    """Return the last `n` lines of `path`, or empty list on missing/error."""
    if not path.exists() or n <= 0:
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            # Naive tail — OK up to 1000 lines for activity.log sized files.
            lines = fh.readlines()
        return [ln.rstrip("\n") for ln in lines[-n:]]
    except OSError:
        return []


_CHANGE_LOOP_PLAN_HEADINGS = (
    "Scoping Rules",
    "Work Targets And Review Gates",
    "Multiplayer Daemon Platform",
    "Multi-User Evolutionary Design",
)


def _repo_root() -> Path:
    override = os.environ.get("WORKFLOW_REPO_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2]


def _shorten(value: Any, max_chars: int) -> str:
    text = "" if value is None else str(value)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 15)].rstrip() + "\n...[truncated]"


def _github_repo() -> str:
    return os.environ.get("WORKFLOW_GITHUB_REPO", "Jonnyton/Workflow")


def _github_get_json(
    path: str,
    *,
    params: dict[str, str | int] | None = None,
    timeout: float = 10.0,
) -> Any:
    api = os.environ.get("WORKFLOW_GITHUB_API", "https://api.github.com")
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{api.rstrip('/')}{path}{query}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "workflow-community-change-context/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _github_read(
    path: str,
    *,
    params: dict[str, str | int] | None = None,
) -> tuple[Any | None, str | None]:
    try:
        return _github_get_json(path, params=params), None
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        return None, f"GitHub HTTP {exc.code} for {path}: {body}"
    except (TimeoutError, OSError, urllib.error.URLError) as exc:
        return None, f"GitHub request failed for {path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"GitHub response was not JSON for {path}: {exc}"


def _issue_label_names(item: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for label in item.get("labels", []) or []:
        if isinstance(label, str):
            labels.append(label)
        elif isinstance(label, dict) and label.get("name"):
            labels.append(str(label["name"]))
    return labels


def _extract_plan_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = None
    marker = f"## {heading}"
    for idx, line in enumerate(lines):
        if line.strip() == marker:
            start = idx
            break
    if start is None:
        return ""
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return "\n".join(lines[start:end]).strip()


def _change_loop_plan_context() -> dict[str, str]:
    plan_path = _repo_root() / "PLAN.md"
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    sections: dict[str, str] = {}
    for heading in _CHANGE_LOOP_PLAN_HEADINGS:
        excerpt = _extract_plan_section(text, heading)
        if excerpt:
            sections[heading] = _shorten(excerpt, 2400)
    return sections


def _summarize_pr(pr: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "state": pr.get("state"),
        "draft": pr.get("draft"),
        "html_url": pr.get("html_url"),
        "head": (pr.get("head") or {}).get("ref"),
        "head_sha": (pr.get("head") or {}).get("sha"),
        "base": (pr.get("base") or {}).get("ref"),
        "labels": _issue_label_names(pr),
        "created_at": pr.get("created_at"),
        "updated_at": pr.get("updated_at"),
        "body_excerpt": _shorten(pr.get("body", ""), 1000),
    }


def _summarize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "html_url": issue.get("html_url"),
        "labels": _issue_label_names(issue),
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "body_excerpt": _shorten(issue.get("body", ""), 1200),
    }


def _comments_excerpt(comments: list[dict[str, Any]], max_items: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for comment in comments[-max_items:]:
        user = comment.get("user") or {}
        rows.append({
            "author": str(user.get("login", "unknown")),
            "created_at": str(comment.get("created_at", "")),
            "body_excerpt": _shorten(comment.get("body", ""), 1400),
        })
    return rows


def _action_community_change_context(
    *,
    filter_text: str = "",
    limit: int = 10,
    **_kwargs: Any,
) -> str:
    """Read-only community change-loop context for chatbot review.

    `filter_text` selects the slice:
    - empty / "queue": open PRs, auto-change PRs, open change requests,
      latest auto-fix runs, and relevant PLAN.md sections.
    - "pr:NUMBER": PR metadata, changed files, patch excerpts, comments, and
      reviews.
    - "issue:NUMBER": issue metadata and recent comments.
    """
    repo = _github_repo()
    selector = (filter_text or "").strip().lower()
    try:
        n_limit = max(1, min(int(limit or 10), 25))
    except (TypeError, ValueError):
        n_limit = 10

    result: dict[str, Any] = {
        "kind": "community_change_context",
        "repo": repo,
        "selector": selector or "queue",
        "plan_sections": _change_loop_plan_context(),
        "review_standard": [
            "Judge design fit against PLAN.md, not only test status.",
            "Prefer minimal primitives and community-build paths over convenience tools.",
            "Reject patch-on-patch fixes that hide missing base capability.",
            "For Codex-written PRs, require Claude-family checker before merge.",
        ],
        "errors": [],
    }

    if selector.startswith("pr:") or (
        selector.startswith("#") and selector[1:].isdigit()
    ):
        number_text = selector.split(":", 1)[1] if ":" in selector else selector[1:]
        try:
            pr_number = int(number_text)
        except ValueError:
            return json.dumps({"error": f"Invalid PR selector: {filter_text!r}"})
        pr, err = _github_read(f"/repos/{repo}/pulls/{pr_number}")
        if err:
            result["errors"].append(err)
        files, files_err = _github_read(
            f"/repos/{repo}/pulls/{pr_number}/files",
            params={"per_page": n_limit},
        )
        if files_err:
            result["errors"].append(files_err)
        comments, comments_err = _github_read(
            f"/repos/{repo}/issues/{pr_number}/comments",
            params={"per_page": n_limit},
        )
        if comments_err:
            result["errors"].append(comments_err)
        reviews, reviews_err = _github_read(
            f"/repos/{repo}/pulls/{pr_number}/reviews",
            params={"per_page": n_limit},
        )
        if reviews_err:
            result["errors"].append(reviews_err)

        result["target"] = f"pr:{pr_number}"
        if isinstance(pr, dict):
            result["pr"] = _summarize_pr(pr)
        if isinstance(files, list):
            result["files"] = [
                {
                    "filename": f.get("filename"),
                    "status": f.get("status"),
                    "additions": f.get("additions"),
                    "deletions": f.get("deletions"),
                    "changes": f.get("changes"),
                    "patch_excerpt": _shorten(f.get("patch", ""), 1800),
                }
                for f in files[:n_limit]
            ]
        if isinstance(comments, list):
            result["comments"] = _comments_excerpt(comments, n_limit)
        if isinstance(reviews, list):
            result["reviews"] = [
                {
                    "author": str((r.get("user") or {}).get("login", "unknown")),
                    "state": r.get("state"),
                    "submitted_at": r.get("submitted_at"),
                    "body_excerpt": _shorten(r.get("body", ""), 1200),
                }
                for r in reviews[-n_limit:]
            ]
        return json.dumps(result, default=str)

    if selector.startswith("issue:"):
        try:
            issue_number = int(selector.split(":", 1)[1])
        except ValueError:
            return json.dumps({"error": f"Invalid issue selector: {filter_text!r}"})
        issue, err = _github_read(f"/repos/{repo}/issues/{issue_number}")
        if err:
            result["errors"].append(err)
        comments, comments_err = _github_read(
            f"/repos/{repo}/issues/{issue_number}/comments",
            params={"per_page": n_limit},
        )
        if comments_err:
            result["errors"].append(comments_err)
        result["target"] = f"issue:{issue_number}"
        if isinstance(issue, dict):
            result["issue"] = _summarize_issue(issue)
        if isinstance(comments, list):
            result["comments"] = _comments_excerpt(comments, n_limit)
        return json.dumps(result, default=str)

    prs, prs_err = _github_read(
        f"/repos/{repo}/pulls",
        params={"state": "open", "per_page": n_limit},
    )
    if prs_err:
        result["errors"].append(prs_err)
    issues, issues_err = _github_read(
        f"/repos/{repo}/issues",
        params={"state": "open", "per_page": n_limit},
    )
    if issues_err:
        result["errors"].append(issues_err)
    runs, runs_err = _github_read(
        f"/repos/{repo}/actions/workflows/auto-fix-bug.yml/runs",
        params={"per_page": min(n_limit, 10)},
    )
    if runs_err:
        result["errors"].append(runs_err)

    if isinstance(prs, list):
        result["open_prs"] = [_summarize_pr(pr) for pr in prs[:n_limit]]
        result["open_auto_change_prs"] = [
            _summarize_pr(pr)
            for pr in prs
            if str(pr.get("title", "")).startswith("[auto-change]")
            or str((pr.get("head") or {}).get("ref", "")).startswith("auto-change/")
        ]
    if isinstance(issues, list):
        change_requests = [
            _summarize_issue(issue) for issue in issues if "pull_request" not in issue
        ]
        result["open_change_requests"] = change_requests
        result["open_daemon_request_issues"] = [
            issue for issue in change_requests if "daemon-request" in issue["labels"]
        ]
    if isinstance(runs, dict):
        result["latest_auto_fix_runs"] = [
            {
                "id": run.get("id"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "event": run.get("event"),
                "head_sha": run.get("head_sha"),
                "created_at": run.get("created_at"),
                "html_url": run.get("html_url"),
            }
            for run in runs.get("workflow_runs", [])[: min(n_limit, 10)]
        ]
    result["usage"] = (
        "Use filter_text='pr:NUMBER' for changed files/comments/reviews, "
        "or filter_text='issue:NUMBER' for the request thread."
    )
    return json.dumps(result, default=str)


def _action_daemon_overview(
    universe_id: str = "",
    limit: Any = None,
    **_kwargs: Any,
) -> str:
    """Aggregated read-through per preflight §4.1 #1 (Phase H).

    Composes queue + subscriptions + bids + settlements + gates +
    activity tail + run state into one response. 1s TTL cache keyed
    on (universe_id, limit) keeps hot-path cost bounded (R1).

    Read-only: no mutations. Absent features gracefully degrade
    (empty lists / zero counts) rather than error.
    """
    import time as _time

    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})

    limit_key = (
        "full" if isinstance(limit, str)
        and limit.strip().lower() == "full" else str(limit)
    )
    cache_key = f"{uid}::{limit_key}"
    now_s = _time.time()
    cached = _OVERVIEW_CACHE.get(cache_key)
    if cached and (now_s - cached[0]) < _OVERVIEW_TTL_SECONDS:
        return cached[2]

    limits = _overview_limits(limit)
    response: dict[str, Any] = {"universe_id": uid}

    # Dispatcher config + tier_status_map.
    try:
        from workflow.dispatcher import load_dispatcher_config
        cfg = load_dispatcher_config(udir)
        response["dispatcher"] = {
            "tier_status_map": cfg.tier_status_map(),
            "config": {
                "accept_external_requests": cfg.accept_external_requests,
                "accept_goal_pool": cfg.accept_goal_pool,
                "accept_paid_bids": cfg.accept_paid_bids,
                "allow_opportunistic": cfg.allow_opportunistic,
                "bid_coefficient": cfg.bid_coefficient,
                "bid_term_cap": cfg.bid_term_cap,
            },
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("daemon_overview: dispatcher read failed: %s", exc)
        response["dispatcher"] = {}

    # Queue top-N.
    try:
        from workflow.branch_tasks import read_queue
        from workflow.dispatcher import score_task
        queue = read_queue(udir)
        q_cfg = load_dispatcher_config(udir)
        now_iso = datetime.now(timezone.utc).isoformat()
        scored: list[tuple[float, dict]] = []
        pending = 0
        for task in queue:
            if task.status == "pending":
                pending += 1
                row = task.to_dict()
                row["score"] = score_task(
                    task, now_iso=now_iso, config=q_cfg,
                )
                scored.append((row["score"], row))
        scored.sort(key=lambda p: -p[0])
        response["queue"] = {
            "pending_count": pending,
            "top": [row for _, row in scored[: limits["queue_top"]]],
            "archived_recent_count": 0,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("daemon_overview: queue read failed: %s", exc)
        response["queue"] = {"pending_count": 0, "top": [],
                             "archived_recent_count": 0}

    # Subscriptions + drift.
    try:
        from workflow.producers.goal_pool import (
            POOL_DIRNAME,
            goal_pool_enabled,
            repo_root_path,
        )
        from workflow.subscriptions import list_subscriptions
        goals = list_subscriptions(udir)
        counts: dict[str, int] = {g: 0 for g in goals}
        try:
            repo_root = repo_root_path(udir)
            pool_root = repo_root / POOL_DIRNAME
            for g in goals:
                gdir = pool_root / g
                if gdir.is_dir():
                    counts[g] = sum(1 for _ in gdir.glob("*.yaml"))
        except RuntimeError:
            pass
        if cfg.accept_goal_pool and not goals:
            drift = "pool_enabled_no_subs"
        elif goals and not cfg.accept_goal_pool:
            drift = "subs_but_pool_disabled"
        else:
            drift = "ok"
        response["subscriptions"] = {
            "goals": goals,
            "drift_flag": drift,
            "pool_status_per_goal": counts,
            "pool_flag_enabled": goal_pool_enabled(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("daemon_overview: subscriptions read failed: %s", exc)
        response["subscriptions"] = {"goals": [], "drift_flag": "ok",
                                     "pool_status_per_goal": {}}

    # Bids + daemon capabilities.
    try:
        from workflow.bid.node_bid import read_node_bids
        from workflow.producers.goal_pool import repo_root_path
        from workflow.producers.node_bid import paid_market_enabled
        try:
            bid_repo_root = repo_root_path(udir)
            bids = read_node_bids(bid_repo_root)
        except RuntimeError:
            bids = []
        open_bids = [b.to_dict() for b in bids if b.status == "open"]
        claimed = sum(1 for b in bids if b.status.startswith("claimed:"))
        response["bids"] = {
            "open_count": len(open_bids),
            "claimed_count": claimed,
            "top_open": open_bids[: limits["bids_top"]],
            "daemon_capabilities": {
                "serves_llm_types": sorted(
                    os.environ.get("FANTASY_DAEMON_LLM_TYPES", "").split(",")
                    if os.environ.get("FANTASY_DAEMON_LLM_TYPES")
                    else [],
                ),
                "paid_market_enabled": paid_market_enabled(),
                "bid_coefficient": cfg.bid_coefficient,
            },
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("daemon_overview: bids read failed: %s", exc)
        response["bids"] = {"open_count": 0, "claimed_count": 0,
                            "top_open": []}

    # Settlements.
    try:
        import yaml as _yaml

        from workflow.bid.settlements import settlements_dir
        from workflow.producers.goal_pool import repo_root_path
        try:
            sroot = settlements_dir(repo_root_path(udir))
        except RuntimeError:
            sroot = None
        s_entries: list[dict] = []
        s_total = 0
        s_unsettled = 0
        if sroot and sroot.is_dir():
            for p in sorted(sroot.glob("*.yaml")):
                s_total += 1
                try:
                    raw = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                except Exception:  # noqa: BLE001
                    continue
                if not isinstance(raw, dict):
                    continue
                if not raw.get("settled"):
                    s_unsettled += 1
                s_entries.append(raw)
        s_entries.sort(
            key=lambda r: str(r.get("completed_at", "")), reverse=True,
        )
        response["settlements"] = {
            "count_total": s_total,
            "count_unsettled": s_unsettled,
            "recent": s_entries[: limits["settlements_recent"]],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "daemon_overview: settlements read failed: %s", exc,
        )
        response["settlements"] = {
            "count_total": 0, "count_unsettled": 0, "recent": [],
        }

    # Gates — best-effort; counts only (full gates data is expensive).
    try:
        from workflow.daemon_server import list_gate_claims
        claims = list_gate_claims(_base_path()) or []
        # Filter to claims whose branch lives in this universe — for v1
        # we report all claims and let the caller filter; universe-
        # scoping needs the branch-to-universe mapping which isn't
        # always populated.
        response["gates"] = {
            "ladder_count_on_bound_goal": 0,
            "claims_on_this_universe": 0,
            "total_claims": len(claims),
            "recent_claims": (claims or [])[: limits["gates_recent"]],
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("daemon_overview: gates read failed: %s", exc)
        response["gates"] = {"total_claims": 0, "recent_claims": []}

    # Activity tail (raw file, not a parse).
    response["activity_tail"] = _tail_file_lines(
        udir / "activity.log", limits["activity_tail"],
    )

    # Run state (status.json — best-effort).
    try:
        status = _read_json(udir / "status.json") or {}
        if isinstance(status, dict):
            response["run_state"] = {
                "current_phase": status.get("current_phase", ""),
                "status": status.get("daemon_state", ""),
                "last_verdict": status.get("last_verdict", ""),
                "total_words": status.get("total_words", 0),
                "total_chapters": status.get("total_chapters", 0),
                "last_updated": status.get("last_updated", ""),
            }
        else:
            response["run_state"] = {}
    except Exception:  # noqa: BLE001
        response["run_state"] = {}

    serialized = _trim_overview_for_bytes(response)
    _OVERVIEW_CACHE[cache_key] = (now_s, cache_key, serialized)
    # Cap cache size — prune to last 8 universes worth of keys.
    if len(_OVERVIEW_CACHE) > 16:
        oldest = sorted(_OVERVIEW_CACHE.items(), key=lambda kv: kv[1][0])[:8]
        for k, _ in oldest:
            _OVERVIEW_CACHE.pop(k, None)
    return serialized


_VALID_TIER_KEYS = frozenset({
    "external_requests", "goal_pool", "paid_bids", "opportunistic",
})
_TIER_KEY_TO_CONFIG_FIELD = {
    "external_requests": "accept_external_requests",
    "goal_pool": "accept_goal_pool",
    "paid_bids": "accept_paid_bids",
    "opportunistic": "allow_opportunistic",
}


def _action_set_tier_config(
    universe_id: str = "",
    tier: str = "",
    enabled: bool = False,
    **_kwargs: Any,
) -> str:
    """Phase H: persist a tier toggle into ``dispatcher_config.yaml``.

    Takes effect at the next dispatcher cycle (R2 invariant 3);
    in-flight tasks complete normally. Round-trips YAML so other
    config fields are preserved.
    """
    import yaml as _yaml

    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})

    tier_name = (tier or "").strip().lower()
    if tier_name not in _VALID_TIER_KEYS:
        return json.dumps({
            "status": "rejected",
            "error": "unknown_tier",
            "available_tiers": sorted(_VALID_TIER_KEYS),
        })

    field_name = _TIER_KEY_TO_CONFIG_FIELD[tier_name]
    cfg_path = udir / "dispatcher_config.yaml"
    existing: dict[str, Any] = {}
    if cfg_path.exists():
        try:
            loaded = _yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except Exception as exc:  # noqa: BLE001
            return json.dumps({
                "status": "rejected",
                "error": f"config_corrupt: {exc}",
            })

    existing[field_name] = bool(enabled)

    try:
        udir.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(
            _yaml.safe_dump(existing, sort_keys=True,
                            default_flow_style=False),
            encoding="utf-8",
        )
    except OSError as exc:
        return json.dumps({
            "status": "rejected",
            "error": f"config_write_failed: {exc}",
        })

    # Invalidate the overview cache for this universe so the next
    # `daemon_overview` reflects the change immediately (tests rely
    # on this; production clients also benefit).
    for key in list(_OVERVIEW_CACHE.keys()):
        if key.startswith(f"{uid}::"):
            _OVERVIEW_CACHE.pop(key, None)

    return json.dumps({
        "universe_id": uid,
        "status": "ok",
        "tier": tier_name,
        "enabled": bool(enabled),
        "takes_effect": "next_dispatcher_cycle",
    })


def _action_queue_cancel(
    universe_id: str = "",
    branch_task_id: str = "",
    **_kwargs: Any,
) -> str:
    """Cancel a BranchTask.

    Pending: hard-marks ``cancelled`` via ``mark_status``.
    Running: cooperative cancel — sets ``cancel_requested=True`` so
    the daemon's stream loop observes the flag at the next
    inter-node event and finalizes as ``cancelled``. Authorization:
    the task's ``claimed_by`` daemon (self-cancel) OR host identity.
    Other actors get ``cancel_not_authorized``.
    """
    from workflow.branch_tasks import (
        mark_status,
        read_queue,
        request_task_cancel,
    )

    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})
    if not branch_task_id:
        return json.dumps({"error": "branch_task_id required."})

    try:
        queue = read_queue(udir)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"Failed to read queue: {exc}"})

    target = next(
        (t for t in queue if t.branch_task_id == branch_task_id),
        None,
    )
    if target is None:
        return json.dumps({
            "universe_id": uid,
            "status": "not_found",
            "branch_task_id": branch_task_id,
        })
    if target.status == "running":
        source = os.environ.get("UNIVERSE_SERVER_USER", "anonymous")
        is_owner = bool(target.claimed_by) and source == target.claimed_by
        can_cancel = _env_actor_can(
            ACTION_CANCEL_BRANCH_TASK,
            universe_id=uid,
        )
        if not (can_cancel or is_owner):
            return json.dumps({
                "universe_id": uid,
                "status": "rejected",
                "error": "cancel_not_authorized",
                "branch_task_id": branch_task_id,
                "hint": (
                    "Running-task cancel requires the claiming daemon "
                    f"or the {ACTION_CANCEL_BRANCH_TASK!r} capability "
                    f"in {ENV_CAPABILITIES_VAR}."
                ),
            })
        try:
            ok = request_task_cancel(udir, branch_task_id)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"Failed to request cancel: {exc}"})
        if not ok:
            # Race: task reached terminal between read_queue and now.
            return json.dumps({
                "universe_id": uid,
                "status": "rejected",
                "error": "task_already_terminal",
                "branch_task_id": branch_task_id,
            })
        return json.dumps({
            "universe_id": uid,
            "status": "cancel_requested",
            "branch_task_id": branch_task_id,
            "note": (
                "cooperative cancel — observed at next inter-node "
                "event; daemon finalizes as cancelled"
            ),
        })
    if target.status != "pending":
        return json.dumps({
            "universe_id": uid,
            "status": target.status,
            "branch_task_id": branch_task_id,
            "note": "task is already in a terminal state",
        })

    try:
        mark_status(udir, branch_task_id, status="cancelled")
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"Failed to cancel: {exc}"})

    return json.dumps({
        "universe_id": uid,
        "status": "cancelled",
        "branch_task_id": branch_task_id,
    })


def _goal_pool_not_available() -> str:
    return json.dumps({
        "status": "not_available",
        "hint": "WORKFLOW_GOAL_POOL=on required",
    })


def _action_subscribe_goal(
    universe_id: str = "",
    goal_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.producers.goal_pool import goal_pool_enabled
    from workflow.subscriptions import subscribe

    if not goal_pool_enabled():
        return _goal_pool_not_available()
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})
    if not goal_id:
        return json.dumps({"error": "goal_id required."})
    try:
        goals = subscribe(udir, goal_id)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"subscribe failed: {exc}"})
    return json.dumps({
        "universe_id": uid,
        "goal_id": goal_id,
        "status": "subscribed",
        "goals": goals,
    })


def _action_unsubscribe_goal(
    universe_id: str = "",
    goal_id: str = "",
    **_kwargs: Any,
) -> str:
    from workflow.producers.goal_pool import goal_pool_enabled
    from workflow.subscriptions import unsubscribe

    if not goal_pool_enabled():
        return _goal_pool_not_available()
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})
    if not goal_id:
        return json.dumps({"error": "goal_id required."})
    try:
        goals = unsubscribe(udir, goal_id)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"unsubscribe failed: {exc}"})
    return json.dumps({
        "universe_id": uid,
        "goal_id": goal_id,
        "status": "unsubscribed",
        "goals": goals,
    })


def _action_list_subscriptions(
    universe_id: str = "",
    **_kwargs: Any,
) -> str:
    """List subscriptions + drift detection + per-goal pool counts.

    Preflight §4.1 #4 drift flag values:
      - "ok"
      - "pool_enabled_no_subs"  (F on + accept_goal_pool=true + zero subs)
      - "subs_but_pool_disabled" (subs exist + accept_goal_pool=false)
    """
    from workflow.dispatcher import load_dispatcher_config
    from workflow.producers.goal_pool import (
        POOL_DIRNAME,
        goal_pool_enabled,
        repo_root_path,
    )
    from workflow.subscriptions import list_subscriptions as _list

    if not goal_pool_enabled():
        return _goal_pool_not_available()
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})

    try:
        goals = _list(udir)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"list_subscriptions failed: {exc}"})

    # Per-goal pool counts.
    counts: dict[str, int] = {g: 0 for g in goals}
    try:
        repo_root = repo_root_path(udir)
        pool_root = repo_root / POOL_DIRNAME
        for g in goals:
            gdir = pool_root / g
            if gdir.is_dir():
                counts[g] = sum(1 for _ in gdir.glob("*.yaml"))
    except RuntimeError:
        # repo_root unresolvable — counts stay zero
        pass

    cfg = load_dispatcher_config(udir)
    if cfg.accept_goal_pool and not goals:
        drift = "pool_enabled_no_subs"
    elif goals and not cfg.accept_goal_pool:
        drift = "subs_but_pool_disabled"
    else:
        drift = "ok"

    return json.dumps({
        "universe_id": uid,
        "goals": goals,
        "pool_status_per_goal": counts,
        "config_vs_subscriptions_drift": drift,
    })


def _action_post_to_goal_pool(
    universe_id: str = "",
    goal_id: str = "",
    branch_def_id: str = "",
    inputs_json: str = "",
    priority_weight: float = 0.0,
    **_kwargs: Any,
) -> str:
    """Write a pool YAML to ``<repo_root>/goal_pool/<goal_id>/<id>.yaml``.

    Response includes a ``next_step`` hint for cross-host visibility
    (git add/commit/push).
    """
    from workflow.producers.goal_pool import (
        goal_pool_enabled,
        repo_root_path,
        validate_pool_task_inputs,
        write_pool_post,
    )

    if not goal_pool_enabled():
        return _goal_pool_not_available()
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})
    if not goal_id:
        return json.dumps({"error": "goal_id required."})
    if not branch_def_id:
        return json.dumps({"error": "branch_def_id required."})

    # Parse inputs_json. Empty string → {}.
    if inputs_json.strip():
        try:
            inputs = json.loads(inputs_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"inputs_json invalid JSON: {exc}"})
    else:
        inputs = {}
    ok, reason = validate_pool_task_inputs(inputs)
    if not ok:
        return json.dumps({
            "status": "rejected",
            "error": f"invalid_inputs: {reason}",
        })

    # priority_weight clamp per Phase E invariant 9 (extended to pool posts).
    try:
        pw = float(priority_weight)
    except (TypeError, ValueError):
        pw = 0.0
    if pw < 0:
        return json.dumps({
            "status": "rejected",
            "error": "priority_weight must be >= 0.",
        })
    source = os.environ.get("UNIVERSE_SERVER_USER", "anonymous")
    if not _env_actor_can(ACTION_POST_PRIORITY_GOAL_POOL, universe_id=uid):
        pw = 0.0

    try:
        repo_root = repo_root_path(udir)
    except RuntimeError as exc:
        return json.dumps({
            "status": "rejected",
            "error": "repo_root_not_resolvable",
            "hint": (
                "Set WORKFLOW_REPO_ROOT or run the daemon from inside "
                "a git checkout. Detail: " + str(exc)
            ),
        })

    try:
        out_path = write_pool_post(
            repo_root,
            goal_id,
            branch_def_id=branch_def_id,
            inputs=inputs,
            priority_weight=pw,
            posted_by=source,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"post failed: {exc}"})

    rel_path = out_path.relative_to(repo_root) if out_path.is_relative_to(
        repo_root,
    ) else out_path
    return json.dumps({
        "universe_id": uid,
        "status": "posted",
        "goal_id": goal_id,
        "branch_def_id": branch_def_id,
        "path": str(out_path),
        "priority_weight": pw,
        "next_step": (
            f"To make this post visible to cross-host subscribers, run: "
            f"git add {rel_path} && git commit && git push"
        ),
    })


def _paid_market_not_available() -> str:
    return json.dumps({
        "status": "not_available",
        "hint": "WORKFLOW_PAID_MARKET=on required",
    })


def _action_submit_node_bid(
    universe_id: str = "",
    node_def_id: str = "",
    required_llm_type: str = "",
    inputs_json: str = "",
    bid: float = 0.0,
    **_kwargs: Any,
) -> str:
    """Phase G: write a NodeBid YAML to ``<repo_root>/bids/<id>.yaml``.

    Flag-gated on ``WORKFLOW_PAID_MARKET=on``. Flat-dict inputs only.
    Response includes a ``next_step`` git push hint, mirroring
    ``post_to_goal_pool``.
    """
    from workflow.bid.node_bid import (
        new_node_bid_id,
        validate_node_bid_inputs,
        write_node_bid_post,
    )
    from workflow.producers.goal_pool import repo_root_path
    from workflow.producers.node_bid import paid_market_enabled

    if not paid_market_enabled():
        return _paid_market_not_available()
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})
    if not node_def_id:
        return json.dumps({"error": "node_def_id required."})

    if inputs_json.strip():
        try:
            inputs = json.loads(inputs_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"inputs_json invalid JSON: {exc}"})
    else:
        inputs = {}
    ok, reason = validate_node_bid_inputs(inputs)
    if not ok:
        return json.dumps({
            "status": "rejected",
            "error": f"invalid_inputs: {reason}",
        })

    try:
        bid_value = float(bid)
    except (TypeError, ValueError):
        return json.dumps({
            "status": "rejected",
            "error": "bid must be numeric",
        })
    if bid_value < 0:
        return json.dumps({
            "status": "rejected",
            "error": "bid must be >= 0",
        })

    try:
        repo_root = repo_root_path(udir)
    except RuntimeError as exc:
        return json.dumps({
            "status": "rejected",
            "error": "repo_root_not_resolvable",
            "hint": (
                "Set WORKFLOW_REPO_ROOT or run the daemon from inside "
                "a git checkout. Detail: " + str(exc)
            ),
        })

    source = os.environ.get("UNIVERSE_SERVER_USER", "anonymous")
    node_bid_id = new_node_bid_id()
    payload = {
        "node_bid_id": node_bid_id,
        "node_def_id": node_def_id,
        "required_llm_type": required_llm_type or "",
        "inputs": dict(inputs),
        "bid": bid_value,
        "submitted_by": source,
        "status": "open",
        "evidence_url": "",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        out_path = write_node_bid_post(repo_root, payload)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"post failed: {exc}"})

    rel_path = (
        out_path.relative_to(repo_root)
        if out_path.is_relative_to(repo_root)
        else out_path
    )
    return json.dumps({
        "universe_id": uid,
        "status": "posted",
        "node_bid_id": node_bid_id,
        "node_def_id": node_def_id,
        "path": str(out_path),
        "bid": bid_value,
        "required_llm_type": required_llm_type or "",
        "next_step": (
            f"To make this bid visible to cross-host daemons, run: "
            f"git add {rel_path} && git commit && git push"
        ),
    })


def _action_give_direction(
    universe_id: str = "",
    text: str = "",
    category: str = "direction",
    target: str = "",
    anchor_json: str = "",
    **_kwargs: Any,
) -> str:
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})

    valid_categories = {"direction", "protect", "concern", "observation", "error"}
    if category not in valid_categories:
        category = "direction"

    try:
        from workflow.notes import add_note as _add_note

        anchor: dict[str, Any] = {}
        if anchor_json.strip():
            parsed_anchor = json.loads(anchor_json)
            if not isinstance(parsed_anchor, dict):
                return json.dumps({"error": "anchor_json must be a JSON object."})
            anchor = parsed_anchor

        udir.mkdir(parents=True, exist_ok=True)
        note = _add_note(
            udir,
            source="user",
            text=text,
            category=category,
            target=target or None,
            anchor=anchor,
        )
        return json.dumps({
            "universe_id": uid,
            "note_id": note.id,
            "category": category,
            "target": note.target,
            "anchor": note.anchor,
            "status": "written",
            "note": "Direction delivered. The daemon reads notes at scene boundaries.",
        })
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid anchor_json: {exc.msg}"})
    except Exception as exc:
        return json.dumps({"error": f"Failed to add note: {exc}"})


def _action_query_world(
    universe_id: str = "",
    query_type: str = "facts",
    filter_text: str = "",
    limit: int = 20,
    **_kwargs: Any,
) -> str:
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})

    if query_type == "characters":
        data = _read_json(udir / "characters.json")
    elif query_type == "promises":
        data = _read_json(udir / "promises.json")
    elif query_type == "timeline":
        data = _read_json(udir / "timeline.json")
    else:
        data = _read_json(udir / "facts.json")

    if data is None:
        return _query_world_db(udir, uid, query_type, filter_text, limit)

    if isinstance(data, list) and filter_text:
        lower_filter = filter_text.lower()
        data = [
            item for item in data
            if lower_filter in json.dumps(item, default=str).lower()
        ]

    if isinstance(data, list):
        data = data[:limit]

    return json.dumps({
        "universe_id": uid,
        "query_type": query_type,
        "results": data,
        "count": len(data) if isinstance(data, list) else 1,
    }, default=str)


def _query_world_db(
    udir: Path, uid: str, query_type: str, filter_text: str, limit: int,
) -> str:
    """Query the SQLite world-state stores.

    World state is split across two DBs today:
      - story.db       — extracted_facts, character_states, promises
                         (written by the commit pipeline)
      - knowledge.db   — entities, facts, edges, communities
                         (written by the KG pipeline)

    A single `query_type` may live in either DB. We probe known candidate
    (db, table) pairs in priority order and return the first one that
    contains data. This is the source-of-truth routing — previous versions
    of this function pointed `characters -> entities` in story.db, which
    never existed and surfaced to users as "entities table missing". The
    actual character data is in story.db::character_states.
    """
    # Each entry: (db_filename, table_name). Order is priority: first table
    # that exists AND has rows wins. If none have rows, the first table that
    # exists is queried (possibly returning an empty list but not "missing").
    SOURCES: dict[str, list[tuple[str, str]]] = {
        "facts": [
            # commit-pipeline facts (richest: 282 rows on sporemarch)
            ("story.db", "extracted_facts"),
            # KG-native facts (written by the knowledge pipeline)
            ("knowledge.db", "facts"),
        ],
        "characters": [
            ("story.db", "character_states"),
            ("knowledge.db", "entities"),
        ],
        "promises": [
            ("story.db", "promises"),
        ],
        "timeline": [
            # No timeline table exists in either DB today. Reserved for a
            # future world-state pipeline; surfaces as "not recorded yet"
            # rather than "missing".
        ],
    }

    candidates = SOURCES.get(query_type, SOURCES["facts"])
    if not candidates:
        return json.dumps({
            "universe_id": uid,
            "query_type": query_type,
            "results": [],
            "count": 0,
            "note": (
                f"No store for query_type='{query_type}' yet. "
                "Valid types: facts, characters, promises."
            ),
        })

    import sqlite3

    # Pick the first (db, table) pair that exists. Prefer ones with data.
    chosen: tuple[str, str] | None = None
    fallback_empty: tuple[str, str] | None = None
    checked: list[str] = []
    for dbname, table in candidates:
        db_path = udir / dbname
        checked.append(f"{dbname}::{table}")
        if not db_path.exists():
            continue
        try:
            probe = sqlite3.connect(str(db_path))
            try:
                row = probe.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                if not row:
                    continue
                count_row = probe.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()
                has_rows = count_row and count_row[0] > 0
            finally:
                probe.close()
        except sqlite3.Error:
            continue
        if has_rows:
            chosen = (dbname, table)
            break
        if fallback_empty is None:
            fallback_empty = (dbname, table)

    if chosen is None and fallback_empty is None:
        return json.dumps({
            "universe_id": uid,
            "query_type": query_type,
            "results": [],
            "count": 0,
            "note": (
                f"World-state not initialized for query_type='{query_type}'. "
                f"Checked: {', '.join(checked)}."
            ),
        })

    dbname, table = chosen or fallback_empty  # type: ignore[misc]
    db_path = udir / dbname

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if filter_text:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [row["name"] for row in cursor.fetchall()]
            text_cols = [c for c in columns if c not in ("id", "rowid")]

            where_parts = [f"{c} LIKE ?" for c in text_cols]
            where_clause = " OR ".join(where_parts) if where_parts else "1=1"
            params = [f"%{filter_text}%" for _ in text_cols]

            cursor.execute(
                f"SELECT * FROM {table} WHERE {where_clause} LIMIT ?",
                params + [limit],
            )
        else:
            cursor.execute(f"SELECT * FROM {table} LIMIT ?", (limit,))

        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()

        response: dict[str, Any] = {
            "universe_id": uid,
            "query_type": query_type,
            "results": rows,
            "count": len(rows),
            "source": f"{dbname}::{table}",
        }
        if not rows and chosen is None:
            response["note"] = (
                f"Table '{table}' exists in {dbname} but has no rows yet."
            )
        return json.dumps(response, default=str)

    except Exception as exc:
        return json.dumps({"error": f"DB query failed: {exc}"})


def _action_read_premise(universe_id: str = "", **_kwargs: Any) -> str:
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    content = _normalize_escaped_text(read_legacy_premise(udir))
    source = "PROGRAM.md"
    if not content.strip():
        soul = read_universe_soul(udir)
        content = soul.purpose if soul is not None else ""
        source = SOUL_FILENAME
    else:
        soul = read_universe_soul(udir)

    if not content.strip():
        return json.dumps({
            "universe_id": uid,
            "premise": None,
            "has_soul": soul is not None,
            "soul": soul.summary() if soul is not None else None,
            "note": "No premise set. Use action='set_premise' to create one.",
        })
    return json.dumps({
        "universe_id": uid,
        "premise": content,
        "source": source,
        "has_soul": soul is not None,
        "soul": soul.summary() if soul is not None else None,
    })


def _normalize_escaped_text(text: str) -> str:
    """Convert literal escape sequences (``\\n``, ``\\r``, ``\\t``) to real
    characters when the input looks accidentally double-encoded.

    Some MCP clients transmit multi-line strings as JSON string literals
    and the receiving end sees the escape sequences verbatim. Premise
    markdown is prose — writers essentially never want the 2-character
    literal ``\\n`` sequence in that prose. A text with literal ``\\n``
    sequences is therefore treated as double-encoded, even if it also has
    one or two real newlines (e.g. a trailing file-end newline). If a
    future caller legitimately needs the literal 2-char sequence, they
    can double-escape as ``\\\\n``.
    """
    if not text:
        return text
    if "\\n" not in text and "\\r" not in text and "\\t" not in text:
        return text
    return (
        text
        .replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
        .replace("\\t", "\t")
    )


def _action_set_premise(universe_id: str = "", text: str = "", **_kwargs: Any) -> str:
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)

    if not text.strip():
        return json.dumps({"error": "Premise text cannot be empty."})
    text = _normalize_escaped_text(text)
    try:
        udir.mkdir(parents=True, exist_ok=True)
        soul = write_universe_soul(
            udir, purpose=text, lineage="created-from-premise",
        )
        legacy_premise_path(udir).write_text(text, encoding="utf-8")
        return json.dumps({
            "universe_id": uid,
            "status": "updated",
            "has_soul": True,
            "soul": soul.summary(),
            "note": "Premise saved. The daemon will read it at next startup.",
        })
    except OSError as exc:
        return json.dumps({"error": f"Failed to write premise: {exc}"})


_CANON_SAME_FILENAME_BEHAVIOR = (
    "A later add_canon call with the same filename replaces the stored "
    "source bytes and manifest entry when the content hash changes; "
    "identical bytes are treated as unchanged."
)


def _canon_source_operation(canon_dir: Path, filename: str, data: bytes) -> str:
    from workflow.ingestion.core import SourceManifest

    existing = SourceManifest.load(canon_dir).get(filename)
    if existing is None:
        return "created"
    if existing.sha256 == sha256(data).hexdigest():
        return "unchanged"
    return "replaced"


def _canon_version_semantics(filename: str, routed_to: str) -> dict[str, Any]:
    identity = f"canon/{filename}"
    if routed_to == "sources":
        identity = f"canon/sources/{filename}"
    return {
        "mode": "filename_upsert",
        "identity": identity,
        "same_filename_behavior": _CANON_SAME_FILENAME_BEHAVIOR,
        "history_retained": False,
        "supersede_supported": False,
        "deprecate_supported": False,
    }


def _action_add_canon(
    universe_id: str = "",
    filename: str = "",
    text: str = "",
    provenance_tag: str = "",
    **_kwargs: Any,
) -> str:
    """Add inline canon text. Small uploads only; large files should use
    ``add_canon_from_path`` so the LLM never has to copy content verbatim
    into the tool-call arg.

    Memory-scope Stage 2b landed the ``synthesize_source`` signal as the
    trigger for premise/canon/entity synthesis. This path now routes
    through :func:`workflow.ingestion.core.ingest_file` so the signal
    fires (the earlier direct-write path bypassed it, breaking MCP
    uploads). Files still land under ``canon/sources/`` on user
    uploads; the daemon's worldbuild node picks up the signal and
    synthesizes canon from the source.
    """
    from workflow.api.engine_helpers import _current_actor
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    canon_dir = udir / "canon"

    safe_name = Path(filename).name
    if not safe_name:
        return json.dumps({"error": "Invalid filename."})

    try:
        data = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        return json.dumps({"error": f"Failed to encode text as UTF-8: {exc}"})

    from workflow.ingestion.core import ingest_file

    try:
        canon_dir.mkdir(parents=True, exist_ok=True)
        source_operation = _canon_source_operation(canon_dir, safe_name, data)
        result = ingest_file(
            canon_dir=canon_dir,
            filename=safe_name,
            data=data,
            universe_path=udir,
            user_upload=True,
        )

        if provenance_tag:
            meta_path = canon_dir / f".{safe_name}.meta.json"
            meta = {
                "provenance": provenance_tag,
                "added": datetime.now(timezone.utc).isoformat(),
                "source": _current_actor(),
            }
            meta_path.write_text(json.dumps(meta), encoding="utf-8")

        return json.dumps({
            "universe_id": uid,
            "filename": safe_name,
            "status": "written",
            "provenance": provenance_tag or "untagged",
            "routed_to": result.routed_to,
            "bytes_written": result.byte_count,
            "synthesis_signal_emitted": result.signal_emitted,
            "source_operation": source_operation,
            "version_semantics": _canon_version_semantics(
                safe_name, result.routed_to,
            ),
            "note": (
                "Canon file ingested via ingest_file(). The daemon will "
                "pick up the synthesize_source signal on its next cycle."
            ),
        })
    except OSError as exc:
        return json.dumps({"error": f"Failed to write canon file: {exc}"})


def _action_add_canon_from_path(
    universe_id: str = "",
    path: str = "",
    filename: str = "",
    provenance_tag: str = "",
    **_kwargs: Any,
) -> str:
    """Ingest a file from the server's filesystem into a universe's canon.

    Solves the "copy-through-tool-arg" defect of ``add_canon``: for
    large uploads (>20K tokens) the LLM cannot reliably reproduce the
    file content verbatim in a tool-call arg — summarization drift,
    max-output cutoff, and JSON-escaping errors silently corrupt the
    upload. This path reads the file server-side instead, preserving
    the "user uploads are authoritative" hard rule.

    Trust-model mitigations (task #15):

    - ``WORKFLOW_UPLOAD_WHITELIST`` (env var, optional): colon/
      semicolon-separated absolute-path prefixes. When set, a path
      not under any prefix is rejected with a clear error. When
      unset, any absolute path is accepted and a WARNING is logged
      at startup. The whitelist is opt-in enforcement — the demo
      UX is open-by-default.
    - Response includes ``preview_first_200_bytes``: the first ~200
      UTF-8 characters of the ingested file so the host can see in
      the MCP response what was actually stored (silent substitution
      becomes detectable without an out-of-band read).

    Parameters
    ----------
    universe_id : str
        Target universe. Defaults to the active universe.
    path : str
        **Absolute** path on the server's filesystem. The MCP client's
        LLM never reads the file content through this param — it just
        references a path the host has already placed.
    filename : str, optional
        Filename to store the file under in ``canon/sources/``. Defaults
        to the basename of ``path``.
    provenance_tag : str, optional
        Source tag (e.g. "published novel", "rough notes"). Defaults
        to "user_upload".
    """
    from workflow.api.engine_helpers import _current_actor, _upload_whitelist_prefixes
    if not path:
        return json.dumps({"error": "path is required."})

    src = Path(path)
    if not src.is_absolute():
        return json.dumps({
            "error": (
                "path must be absolute — this action reads from the "
                "server's filesystem, not the MCP client's context."
            ),
        })

    # Whitelist enforcement (opt-in via WORKFLOW_UPLOAD_WHITELIST).
    # Resolve src to handle symlinks + ``..`` traversals before the
    # prefix check; otherwise ``/allowed/../secret`` would slip past.
    whitelist = _upload_whitelist_prefixes()
    if whitelist is not None:
        try:
            resolved = src.resolve(strict=False)
        except OSError as exc:
            return json.dumps({"error": f"Failed to resolve path: {exc}"})
        if not any(
            resolved.is_relative_to(prefix) for prefix in whitelist
        ):
            return json.dumps({
                "error": (
                    f"Path is not under any WORKFLOW_UPLOAD_WHITELIST "
                    f"prefix. Resolved={resolved!s}, "
                    f"allowed_prefixes={[str(p) for p in whitelist]}."
                ),
            })

    if not src.exists():
        return json.dumps({"error": f"File not found: {path}"})
    if not src.is_file():
        return json.dumps({"error": f"Not a regular file: {path}"})

    try:
        data = src.read_bytes()
    except OSError as exc:
        return json.dumps({"error": f"Failed to read file: {exc}"})

    # Reject non-UTF-8 early with a clear error. The daemon's canon
    # pipeline assumes UTF-8; binary or latin-1 files would silently
    # corrupt synthesis.
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return json.dumps({
            "error": (
                f"File is not valid UTF-8 ({exc.reason} at byte "
                f"{exc.start}). Convert to UTF-8 before ingesting."
            ),
        })

    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    canon_dir = udir / "canon"
    safe_name = Path(filename).name if filename else src.name
    if not safe_name:
        return json.dumps({"error": "Invalid filename."})

    from workflow.ingestion.core import ingest_file

    try:
        canon_dir.mkdir(parents=True, exist_ok=True)
        source_operation = _canon_source_operation(canon_dir, safe_name, data)
        result = ingest_file(
            canon_dir=canon_dir,
            filename=safe_name,
            data=data,
            universe_path=udir,
            user_upload=True,
        )

        tag = provenance_tag or "user_upload"
        meta_path = canon_dir / f".{safe_name}.meta.json"
        meta = {
            "provenance": tag,
            "source_path": str(src),
            "added": datetime.now(timezone.utc).isoformat(),
            "source": _current_actor(),
        }
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        return json.dumps({
            "universe_id": uid,
            "filename": safe_name,
            "canonical_path": str(canon_dir / "sources" / safe_name),
            "bytes_written": result.byte_count,
            "synthesis_signal_emitted": result.signal_emitted,
            "routed_to": result.routed_to,
            "provenance": tag,
            "source_operation": source_operation,
            "version_semantics": _canon_version_semantics(
                safe_name, result.routed_to,
            ),
            # Task #15: echo the first 200 decoded chars so the host
            # can confirm in the MCP response what was ingested —
            # silent file-swap becomes detectable without an
            # out-of-band read.
            "preview_first_200_bytes": decoded[:200],
            "note": (
                "File ingested from server path. The daemon will pick "
                "up the synthesize_source signal on its next cycle."
            ),
        })
    except OSError as exc:
        return json.dumps({"error": f"Failed to ingest file: {exc}"})


def _action_list_canon(
    universe_id: str = "",
    **_kwargs: Any,
) -> str:
    """List all canon documents in a universe with metadata."""
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    canon_dir = udir / "canon"

    if not canon_dir.is_dir():
        return json.dumps({"universe_id": uid, "canon_files": [], "note": "No canon directory."})

    files = []
    for f in sorted(canon_dir.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            entry: dict[str, Any] = {
                "filename": f.name,
                "size_bytes": f.stat().st_size,
            }
            # Check for provenance metadata
            meta_path = canon_dir / f".{f.name}.meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    entry["provenance"] = meta.get("provenance", "")
                    entry["added"] = meta.get("added", "")
                    entry["source"] = meta.get("source", "")
                except (json.JSONDecodeError, OSError):
                    pass
            files.append(entry)

    return json.dumps({"universe_id": uid, "canon_files": files, "count": len(files)})


def _source_sidecar_meta(canon_dir: Path, filename: str) -> dict[str, Any]:
    meta_path = canon_dir / f".{filename}.meta.json"
    if not meta_path.exists():
        return {}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return meta if isinstance(meta, dict) else {}


def _manifest_data(canon_dir: Path) -> dict[str, Any]:
    manifest_path = canon_dir / ".manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _source_file_entry(
    path: Path,
    canon_dir: Path,
    manifest: dict[str, Any],
    raw: bytes | None = None,
) -> dict[str, Any]:
    stat = path.stat()
    meta = _source_sidecar_meta(canon_dir, path.name)
    manifest_entry = manifest.get(path.name, {})
    if not isinstance(manifest_entry, dict):
        manifest_entry = {}
    synthesized_docs = manifest_entry.get("synthesized_docs", [])
    if not isinstance(synthesized_docs, list):
        synthesized_docs = []
    manifest_sha = manifest_entry.get("sha256", "")
    current_sha = hashlib.sha256(raw).hexdigest() if raw is not None else manifest_sha

    entry: dict[str, Any] = {
        "filename": path.name,
        "source_path": f"sources/{path.name}",
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc,
        ).isoformat(),
        "sha256": current_sha,
        "provenance": meta.get("provenance", ""),
        "added": meta.get("added", ""),
        "source": meta.get("source", ""),
        "original_source_path": meta.get("source_path", ""),
        "file_type": manifest_entry.get("file_type", "unknown"),
        "mime_type": manifest_entry.get("mime_type", ""),
        "manifest_sha256": manifest_sha,
        "ingested_at": manifest_entry.get("ingested_at", ""),
        "synthesized_docs": synthesized_docs,
        "synthesis_complete": bool(synthesized_docs),
        "synthesis_failed": bool(manifest_entry.get("synthesis_failed")),
    }
    if isinstance(manifest_entry.get("last_bite_outcomes"), dict):
        entry["last_bite_outcomes"] = manifest_entry["last_bite_outcomes"]
    return entry


def _action_list_sources(
    universe_id: str = "",
    **_kwargs: Any,
) -> str:
    """List uploaded source documents with attestation metadata."""
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    canon_dir = udir / "canon"
    sources_dir = canon_dir / "sources"

    if not sources_dir.is_dir():
        return json.dumps({
            "universe_id": uid,
            "source_files": [],
            "source_count": 0,
            "note": "No canon/sources directory.",
        })

    manifest = _manifest_data(canon_dir)
    source_files: list[dict[str, Any]] = []
    try:
        for path in sorted(sources_dir.iterdir()):
            if path.is_file() and not path.name.startswith("."):
                source_files.append(_source_file_entry(path, canon_dir, manifest))
    except OSError as exc:
        return json.dumps({"error": f"Failed to list source files: {exc}"})

    return json.dumps({
        "universe_id": uid,
        "source_files": source_files,
        "source_count": len(source_files),
    })


def _action_read_source(
    universe_id: str = "",
    filename: str = "",
    limit: int = 30,
    **_kwargs: Any,
) -> str:
    """Read one uploaded source document verbatim with checksum metadata."""
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    canon_dir = udir / "canon"
    sources_dir = canon_dir / "sources"

    safe_name = Path(filename).name
    if not safe_name or safe_name != filename:
        return json.dumps({
            "error": "Filename required. Use list_sources to see available files.",
        })

    target = (sources_dir / safe_name).resolve()
    if not target.is_relative_to(sources_dir.resolve()):
        return json.dumps({"error": "Path traversal not allowed."})
    if not target.is_file():
        return json.dumps({
            "error": f"Source file '{safe_name}' not found.",
            "hint": "Use list_sources to see available files.",
        })

    try:
        raw = target.read_bytes()
        content = raw.decode("utf-8")
        manifest = _manifest_data(canon_dir)
        entry = _source_file_entry(target, canon_dir, manifest, raw=raw)
    except UnicodeDecodeError as exc:
        return json.dumps({
            "error": (
                f"Source file '{safe_name}' is not valid UTF-8 "
                f"({exc.reason} at byte {exc.start})."
            ),
        })
    except OSError as exc:
        return json.dumps({"error": f"Failed to read source file: {exc}"})

    # ChatGPT's connector wrapper can stop rendering downstream writes after
    # several large source reads. Keep the default preview compact, while still
    # allowing an explicit larger preview through the existing MCP `limit` arg.
    preview_chars = 4000
    if limit and limit > 100:
        preview_chars = min(limit, 10000)

    truncated = len(content) > preview_chars
    entry.update({
        "universe_id": uid,
        "content": content[:preview_chars] if truncated else content,
        "truncated": truncated,
        "content_preview_chars": preview_chars,
        "next_action_hint": (
            "If the user requested a create or update, continue with that write "
            "action now; do not stop after reading sources."
        ),
    })
    if truncated:
        entry["total_chars"] = len(content)
        entry["note"] = (
            f"Source file preview truncated to {preview_chars} chars. "
            "Pass limit=10000 for the largest supported preview."
        )
    return json.dumps(entry)


def _action_read_canon(
    universe_id: str = "",
    filename: str = "",
    **_kwargs: Any,
) -> str:
    """Read the contents of a specific canon document."""
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    canon_dir = udir / "canon"

    safe_name = Path(filename).name
    if not safe_name:
        return json.dumps({"error": "Filename required. Use list_canon to see available files."})

    target = canon_dir / safe_name
    if not target.is_file():
        return json.dumps({
            "error": f"Canon file '{safe_name}' not found.",
            "hint": "Use list_canon to see available files.",
        })

    try:
        content = target.read_text(encoding="utf-8")
        entry: dict[str, Any] = {
            "universe_id": uid,
            "filename": safe_name,
            "size_bytes": target.stat().st_size,
            "content": content,
        }
        # Attach provenance if available
        meta_path = canon_dir / f".{safe_name}.meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                entry["provenance"] = meta.get("provenance", "")
            except (json.JSONDecodeError, OSError):
                pass
        return json.dumps(entry)
    except OSError as exc:
        return json.dumps({"error": f"Failed to read canon file: {exc}"})


def _action_control_daemon(
    universe_id: str = "",
    text: str = "",
    **_kwargs: Any,
) -> str:
    action = text.strip().lower()
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({"error": f"Universe '{uid}' not found."})

    pause_path = udir / ".pause"

    if action == "pause":
        try:
            udir.mkdir(parents=True, exist_ok=True)
            pause_path.write_text(
                datetime.now(timezone.utc).isoformat(), encoding="utf-8",
            )
            return json.dumps({
                "universe_id": uid,
                "action": "pause",
                "status": "signal_written",
                "note": "Daemon will pause at the next scene boundary.",
            })
        except OSError as exc:
            return json.dumps({"error": f"Failed to write pause signal: {exc}"})

    elif action == "resume":
        if not pause_path.exists():
            return json.dumps({
                "universe_id": uid,
                "action": "resume",
                "status": "not_paused",
                "note": "Daemon was not paused.",
            })
        try:
            pause_path.unlink()
            return json.dumps({
                "universe_id": uid,
                "action": "resume",
                "status": "resumed",
                "note": "Pause signal removed. Daemon will resume.",
            })
        except OSError as exc:
            return json.dumps({"error": f"Failed to remove pause: {exc}"})

    elif action == "status":
        status = _read_json(udir / "status.json")
        liveness = _daemon_liveness(
            udir, status if isinstance(status, dict) else None,
        )
        # Count pending unreconciled writes so host sees drift when a
        # git commit failed but SQLite accepted the write.
        try:
            pending = list_unreconciled_writes(_base_path(), limit=500)
            pending_count = len(pending)
        except Exception:
            pending_count = 0
        return json.dumps({
            "universe_id": uid,
            "action": "status",
            "phase": liveness["phase"],
            "phase_human": liveness["phase_human"],
            "is_paused": liveness["is_paused"],
            "has_premise": liveness["has_premise"],
            "has_work": liveness["has_work"],
            "last_activity_at": liveness["last_activity_at"],
            "staleness": liveness["staleness"],
            "word_count": liveness["word_count"],
            "word_count_sample": liveness["word_count_sample"],
            "accept_rate": liveness["accept_rate"],
            "accept_rate_sample": liveness["accept_rate_sample"],
            "unreconciled_writes_count": pending_count,
        })

    else:
        return json.dumps({
            "error": f"Unknown daemon action '{action}'. Use: pause, resume, status.",
        })


def _action_get_activity(
    universe_id: str = "",
    limit: int = 30,
    **_kwargs: Any,
) -> str:
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    log_path = udir / "activity.log"

    limit = min(max(limit, 1), 200)

    content = _read_text(log_path)
    if not content:
        return json.dumps({
            "universe_id": uid,
            "lines": [],
            "note": "No activity log found. The daemon may not have run yet.",
        })

    all_lines = content.strip().splitlines()
    tail = all_lines[-limit:]
    return json.dumps({
        "universe_id": uid,
        "lines": tail,
        "count": len(tail),
        "total": len(all_lines),
    })


# Pattern: "[2026-04-19 20:30:00] [dispatch_guard] message body" or
# legacy "[2026-04-19 20:30:00] untagged message". Lenient — any line
# that can't be parsed is surfaced in the 'raw' field so callers still
# see the source text when they need it.
_ACTIVITY_LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\](?:\s*\[(?P<tag>[^\]]+)\])?\s*(?P<msg>.*)$"
)

# Domain caveat for dispatch_guard queries with zero matching events.
# dispatch_guard only emits when the daemon actively dispatches a scene;
# empty results could mean (a) no overshoots fired, OR (b) the daemon did
# not dispatch at all in this window (endpoint unbound, daemon paused,
# universe idle). Chatbot must not read empty-list as "no overshoots."
_DISPATCH_GUARD_ABSENCE_CAVEAT = (
    "Empty dispatch_guard list does not prove no overshoots — the daemon "
    "may not have dispatched any scenes in this window (endpoint unbound, "
    "daemon paused, or universe idle). Verify daemon ran before inferring "
    "'guard never needed to fire'."
)


def _parse_activity_line(line: str) -> dict[str, str]:
    """Split ``[TS] [TAG] MSG`` (or legacy ``[TS] MSG``) into fields.

    Returns dict with keys ``ts``, ``tag`` (empty when untagged),
    ``message``, ``raw``. Unparseable lines fall back to all-empty
    fields + ``raw`` holding the original string.
    """
    line = line.rstrip("\n")
    match = _ACTIVITY_LINE_RE.match(line)
    if not match:
        return {"ts": "", "tag": "", "message": "", "raw": line}
    return {
        "ts": match.group("ts") or "",
        "tag": match.group("tag") or "",
        "message": match.group("msg") or "",
        "raw": line,
    }


def _action_get_recent_events(
    universe_id: str = "",
    tag: str = "",
    limit: int = 30,
    **_kwargs: Any,
) -> str:
    """Tag-filterable view of activity.log for chatbot observability.

    Reads the universe's ``activity.log`` tail and returns entries as
    structured dicts (``ts`` / ``tag`` / ``message`` / ``raw``). When
    ``tag`` is non-empty, only entries whose tag starts with ``tag``
    are returned — tag prefix-match so a caller can filter ``"dispatch"``
    and get both ``dispatch_guard`` and ``dispatch_execution``.

    Evidence + caveat fields follow the self-auditing-tools pattern:
      - ``events``: matching structured entries (most recent first).
      - ``source``: ``"activity.log"`` — the audit surface backing the
        answer.
      - ``caveats``: list of strings explaining any observation caveats
        (e.g. "log file missing", "tag filter matched 0 of N entries").

    Args:
        universe_id: Target universe (falls back to default).
        tag: Optional tag prefix filter (empty = all entries).
        limit: Max entries to return (1..500, clamped).
    """
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    log_path = udir / "activity.log"

    limit = min(max(limit, 1), 500)
    caveats: list[str] = []

    content = _read_text(log_path)
    if not content:
        missing_caveats = [
            "No activity.log found. The daemon may not have run yet "
            "in this universe, or the log was cleared.",
        ]
        if tag == "dispatch_guard":
            missing_caveats.append(_DISPATCH_GUARD_ABSENCE_CAVEAT)
        return json.dumps({
            "universe_id": uid,
            "events": [],
            "source": "activity.log",
            "tag_filter": tag,
            "caveats": missing_caveats,
        })

    all_lines = content.strip().splitlines()
    parsed = [_parse_activity_line(line) for line in all_lines]

    if tag:
        matched = [p for p in parsed if p["tag"].startswith(tag)]
        if not matched:
            caveats.append(
                f"Tag filter {tag!r} matched 0 of {len(parsed)} entries. "
                f"Known tags in file: "
                f"{sorted({p['tag'] for p in parsed if p['tag']})[:10]}."
            )
            if tag == "dispatch_guard":
                caveats.append(_DISPATCH_GUARD_ABSENCE_CAVEAT)
    else:
        matched = parsed

    # Return most-recent first so chatbot readers see newest events at top.
    tail = matched[-limit:]
    events = list(reversed(tail))

    untagged_count = sum(1 for p in parsed if not p["tag"])
    if untagged_count and not tag:
        caveats.append(
            f"{untagged_count} of {len(parsed)} activity lines carry no tag "
            "(pre-tagging call sites or legacy entries)."
        )

    return json.dumps({
        "universe_id": uid,
        "events": events,
        "source": "activity.log",
        "tag_filter": tag,
        "total_lines": len(all_lines),
        "matched": len(matched),
        "returned": len(events),
        "caveats": caveats,
    })


def _action_get_ledger(universe_id: str = "", limit: int = 50, **_kwargs: Any) -> str:
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)

    ledger_path = udir / "ledger.json"
    data = _read_json(ledger_path)
    if not data or not isinstance(data, list):
        return json.dumps({"universe_id": uid, "entries": [], "note": "No ledger entries yet."})

    entries = list(reversed(data))[:limit]
    return json.dumps({"universe_id": uid, "entries": entries, "count": len(entries)})


def _action_switch_universe(universe_id: str = "", **_kwargs: Any) -> str:
    if not universe_id:
        return json.dumps({"error": "universe_id is required."})

    uid = universe_id
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return json.dumps({
            "error": f"Universe '{uid}' not found.",
            "available": [
                d.name for d in _base_path().iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ] if _base_path().is_dir() else [],
        })

    # Write the active universe marker — the tray app watches this file
    marker = _base_path() / ".active_universe"
    try:
        marker.write_text(uid, encoding="utf-8")
    except OSError as exc:
        return json.dumps({"error": f"Failed to write active universe marker: {exc}"})

    return json.dumps({
        "universe_id": uid,
        "status": "switching",
        "note": f"Daemon will restart on '{uid}' within ~10 seconds.",
    })


def _action_create_universe(
    universe_id: str = "",
    text: str = "",
    **_kwargs: Any,
) -> str:
    if not universe_id:
        return json.dumps({"error": "universe_id is required."})

    uid = universe_id
    base = _base_path()
    udir = base / uid

    # Sanitize
    if "/" in uid or "\\" in uid or uid.startswith("."):
        return json.dumps({"error": "Invalid universe_id."})
    if udir.exists():
        return json.dumps({"error": f"Universe '{uid}' already exists."})

    try:
        udir.mkdir(parents=True, exist_ok=True)
        normalized_text = _normalize_escaped_text(text) if text.strip() else ""
        soul = ensure_universe_soul(udir, purpose=normalized_text)
        # Write premise if provided
        if normalized_text.strip():
            legacy_premise_path(udir).write_text(normalized_text, encoding="utf-8")

        # Initialize empty state files
        (udir / "notes.json").write_text("[]", encoding="utf-8")
        (udir / "activity.log").write_text("", encoding="utf-8")

        result: dict[str, Any] = {
            "universe_id": uid,
            "status": "created",
            "has_premise": bool(normalized_text.strip()),
            "has_soul": True,
            "soul": soul.summary(),
            "first_run_checklist": _synthesis_first_run_checklist(
                has_premise=bool(normalized_text.strip()),
            ),
        }

        # Auto-switch the daemon to the new universe
        marker = base / ".active_universe"
        marker.write_text(uid, encoding="utf-8")
        result["note"] = (
            f"Universe '{uid}' created. "
            "Daemon will switch to it within ~10 seconds."
        )

        return json.dumps(result)
    except OSError as exc:
        return json.dumps({"error": f"Failed to create universe: {exc}"})


# ───────────────────────────────────────────────────────────────────────────
# Pattern A2 body for the ``universe()`` MCP tool. The decorator + 23-arg
# signature + chatbot-facing docstring stays in ``workflow/universe_server.py``
# wrapping a delegation to this function. Same shape as ``goals()`` /
# ``gates()`` (Step 7), ``branch_design_guide`` (Step 8).
# ───────────────────────────────────────────────────────────────────────────


def _universe_impl(
    action: str,
    universe_id: str = "",
    text: str = "",
    path: str = "",
    category: str = "",
    target: str = "",
    query_type: str = "",
    filter_text: str = "",
    request_type: str = "scene_direction",
    branch_id: str = "",
    filename: str = "",
    provenance_tag: str = "",
    limit: int = 30,
    priority_weight: float = 0.0,
    pickup_incentive: str = "",
    directed_daemon_id: str = "",
    directed_daemon_instruction: str = "",
    branch_task_id: str = "",
    goal_id: str = "",
    branch_def_id: str = "",
    inputs_json: str = "",
    node_def_id: str = "",
    required_llm_type: str = "",
    bid: float = 0.0,
    tier: str = "",
    enabled: bool = False,
    tag: str = "",
    anchor_json: str = "",
) -> str:
    """Pattern A2 body — see ``workflow.universe_server.universe`` for the
    chatbot-facing docstring. Behavior is identical; the decorator wrapper
    forwards every argument unchanged.
    """
    dispatch = {
        "list": _action_list_universes,
        "inspect": _action_inspect_universe,
        "read_output": _action_read_output,
        "query_world": _action_query_world,
        "get_activity": _action_get_activity,
        "get_recent_events": _action_get_recent_events,
        "get_ledger": _action_get_ledger,
        "submit_request": _action_submit_request,
        "give_direction": _action_give_direction,
        "read_premise": _action_read_premise,
        "set_premise": _action_set_premise,
        "add_canon": _action_add_canon,
        "add_canon_from_path": _action_add_canon_from_path,
        "list_canon": _action_list_canon,
        "read_canon": _action_read_canon,
        "list_sources": _action_list_sources,
        "read_source": _action_read_source,
        "control_daemon": _action_control_daemon,
        "switch_universe": _action_switch_universe,
        "create_universe": _action_create_universe,
        "queue_list": _action_queue_list,
        "queue_cancel": _action_queue_cancel,
        "subscribe_goal": _action_subscribe_goal,
        "unsubscribe_goal": _action_unsubscribe_goal,
        "list_subscriptions": _action_list_subscriptions,
        "post_to_goal_pool": _action_post_to_goal_pool,
        "submit_node_bid": _action_submit_node_bid,
        "community_change_context": _action_community_change_context,
        "daemon_overview": _action_daemon_overview,
        "daemon_list": _action_daemon_list,
        "daemon_get": _action_daemon_get,
        "daemon_create": _action_daemon_create,
        "daemon_summon": _action_daemon_summon,
        "daemon_pause": _action_daemon_pause,
        "daemon_resume": _action_daemon_resume,
        "daemon_restart": _action_daemon_restart,
        "daemon_banish": _action_daemon_banish,
        "daemon_update_behavior": _action_daemon_update_behavior,
        "daemon_control_status": _action_daemon_control_status,
        "daemon_memory_capture": _action_daemon_memory_capture,
        "daemon_memory_search": _action_daemon_memory_search,
        "daemon_memory_list": _action_daemon_memory_list,
        "daemon_memory_review": _action_daemon_memory_review,
        "daemon_memory_promote": _action_daemon_memory_promote,
        "daemon_memory_status": _action_daemon_memory_status,
        "treasury_status": _action_treasury_status,
        "set_tier_config": _action_set_tier_config,
    }

    handler = dispatch.get(action)
    if handler is None:
        return json.dumps({
            "error": f"Unknown action '{action}'.",
            "available_actions": sorted(dispatch.keys()),
        })

    # Build kwargs from all optional params
    kwargs: dict[str, Any] = {
        "universe_id": universe_id,
        "text": text,
        "path": path,
        "category": category,
        "target": target,
        "query_type": query_type,
        "filter_text": filter_text,
        "request_type": request_type,
        "branch_id": branch_id,
        "filename": filename,
        "provenance_tag": provenance_tag,
        "limit": limit,
        "priority_weight": priority_weight,
        "pickup_incentive": pickup_incentive,
        "directed_daemon_id": directed_daemon_id,
        "directed_daemon_instruction": directed_daemon_instruction,
        "branch_task_id": branch_task_id,
        "goal_id": goal_id,
        "branch_def_id": branch_def_id,
        "inputs_json": inputs_json,
        "node_def_id": node_def_id,
        "required_llm_type": required_llm_type,
        "bid": bid,
        "tier": tier,
        "enabled": enabled,
        "tag": tag,
        "anchor_json": anchor_json,
    }

    # All WRITE actions are funneled through the ledger wrapper. READ actions
    # pass through untouched. See WRITE_ACTIONS for the authoritative set.
    return _dispatch_with_ledger(action, handler, kwargs)
