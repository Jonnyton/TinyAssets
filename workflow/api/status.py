"""Status subsystem — extracted from workflow/universe_server.py (Task #10).

Houses the `get_status` MCP-tool body and its `_policy_hash` helper. The MCP
tool decoration stays in `workflow/universe_server.py` (Pattern A2 from
``docs/exec-plans/active/2026-04-26-decomp-step-2-prep.md`` §4 — same as Task
#9 wiki extraction). The decorated tool there delegates to the plain
``get_status(...)`` function below.

Public implementation surface:
    get_status(universe_id="")  → str: full daemon status JSON
    _policy_hash(payload)       → str: deterministic sha256 of policy payload

Cross-module note: ``_parse_activity_line`` lives in ``workflow.api.universe``
and is lazy-imported inside ``get_status`` to keep status startup cheap. Other
lazy imports (dispatcher, storage, providers.router, providers.base,
storage.rotation) follow the pattern that was already in place pre-extraction.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from workflow.api.helpers import _base_path, _default_universe, _universe_dir
from workflow.providers.base import API_KEY_PROVIDER_ENV_VARS, api_key_providers_enabled


def _policy_hash(payload: dict[str, Any]) -> str:
    """Deterministic sha256 of sorted-JSON policy payload.

    Chatbot-side callers can compare the hash across calls to detect
    config drift. Hashing sorted JSON means key-order + whitespace
    don't perturb the fingerprint.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Heartbeat refresh interval observed in fantasy_daemon's BUG-011 Phase A
# implementation (PR #212). 2x interval is the threshold for "stale heartbeat".
_HEARTBEAT_REFRESH_INTERVAL_S = 60
_HEARTBEAT_STALE_THRESHOLD_S = _HEARTBEAT_REFRESH_INTERVAL_S * 2

# Threshold for "stuck pending" — a pending task older than this without
# claim implies dispatcher pickup or worker liveness issue (today's
# BUG-009 class).
_STUCK_PENDING_THRESHOLD_S = 120

# Auto-ship observation window surfaced in get_status.auto_ship_health.
_AUTO_SHIP_OBSERVATION_WINDOW_S = 24 * 60 * 60
_AUTO_SHIP_RECENT_ATTEMPT_LIMIT = 10
_AUTO_SHIP_TEXT_FIELD_LIMIT = 500
_RELEASE_STATE_FIELDS = (
    "git_sha",
    "image_tag",
    "image_digest",
    "build_run_id",
    "build_run_url",
    "deploy_run_id",
    "deploy_run_url",
    "config_hash",
    "config_version",
    "schema_migration_rev",
    "canary_bundle_status",
    "deployed_at",
    "rollback_target",
    "actor",
    "repository",
    "workflow_event",
)


def _parse_iso_to_epoch(value: str) -> float | None:
    """Best-effort ISO-8601 parser; returns None on empty/unparseable input.

    Defensive — never raises so a malformed lease timestamp can't break
    the status probe. Pre-#212 BranchTasks have empty strings for the new
    fields; this returns None for those.
    """
    if not value:
        return None
    try:
        from datetime import datetime
        # fromisoformat handles "+00:00" but not "Z" suffix on older Pythons.
        cleaned = value.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).timestamp()
    except Exception:  # noqa: BLE001
        return None


def _auto_ship_window_seconds() -> tuple[int, list[str]]:
    """Return configured auto-ship observation window with warnings.

    Invalid config is surfaced in status warnings and falls back to the
    conservative 24h default instead of breaking the public status probe.
    """
    raw = os.environ.get("WORKFLOW_AUTO_SHIP_OBSERVATION_WINDOW_SECONDS", "")
    raw = raw.strip()
    if not raw:
        return _AUTO_SHIP_OBSERVATION_WINDOW_S, []
    try:
        value = int(raw)
    except ValueError:
        return _AUTO_SHIP_OBSERVATION_WINDOW_S, [
            "invalid_window_seconds: "
            f"WORKFLOW_AUTO_SHIP_OBSERVATION_WINDOW_SECONDS={raw!r}; "
            f"using {_AUTO_SHIP_OBSERVATION_WINDOW_S}"
        ]
    if value <= 0:
        return _AUTO_SHIP_OBSERVATION_WINDOW_S, [
            "invalid_window_seconds: "
            f"WORKFLOW_AUTO_SHIP_OBSERVATION_WINDOW_SECONDS must be > 0; "
            f"using {_AUTO_SHIP_OBSERVATION_WINDOW_S}"
        ]
    return value, []


def _compact_status_text(value: str) -> str:
    if len(value) <= _AUTO_SHIP_TEXT_FIELD_LIMIT:
        return value
    return value[:_AUTO_SHIP_TEXT_FIELD_LIMIT] + "...[truncated]"


def _release_state_path() -> Path:
    override = os.environ.get("WORKFLOW_RELEASE_STATE_PATH", "").strip()
    if override:
        return Path(override)
    return _base_path() / "release-state.json"


def _load_release_state() -> dict[str, Any]:
    """Read the deploy-published release receipt for public status.

    The deploy pipeline owns writes. This status helper is deliberately
    read-only and best-effort so a missing or malformed receipt cannot break
    the core MCP health probe.
    """
    path = _release_state_path()
    out: dict[str, Any] = {
        "receipt_available": False,
        "receipt_path": str(path),
        "warnings": [],
    }

    try:
        if not path.is_file():
            out["warnings"].append("release_state_receipt_missing")
            return out
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — status probe must survive bad I/O
        out["warnings"].append(f"release_state_read_failed: {exc}")
        return out

    if not isinstance(payload, dict):
        out["warnings"].append("release_state_receipt_not_object")
        return out

    out["receipt_available"] = True
    for field in _RELEASE_STATE_FIELDS:
        value = payload.get(field, "")
        out[field] = value if value is not None else ""

    extra = {
        str(key): value
        for key, value in payload.items()
        if key not in _RELEASE_STATE_FIELDS
    }
    if extra:
        out["extra"] = extra

    missing = [field for field in _RELEASE_STATE_FIELDS if not out.get(field)]
    if missing:
        out["warnings"].append(
            "release_state_missing_fields: " + ", ".join(missing)
        )
    return out


def _compact_ship_attempt(attempt: Any) -> dict[str, Any]:
    """Compact chatbot-facing summary of an auto-ship ledger row.

    Omits empty optional fields and potentially bulky fields such as
    changed_paths_json. The full structured ledger remains the source of
    truth on disk.
    """
    summary = {
        "ship_attempt_id": attempt.ship_attempt_id,
        "request_id": attempt.request_id,
        "release_gate_result": attempt.release_gate_result,
        "ship_class": attempt.ship_class,
        "ship_status": attempt.ship_status,
        "would_open_pr": attempt.would_open_pr,
        "updated_at": attempt.updated_at,
    }
    for field in (
        "parent_run_id",
        "child_run_id",
        "branch_def_id",
        "pr_url",
        "commit_sha",
        "ci_status",
        "rollback_handle",
        "stable_evidence_handle",
        "observation_status",
        "observation_status_at",
        "error_class",
        "error_message",
    ):
        value = getattr(attempt, field)
        if not value:
            continue
        if field == "error_message":
            value = _compact_status_text(value)
        summary[field] = value
    return summary


def _observation_window_remaining_s(
    attempt: Any,
    *,
    now_ts: float,
    window_seconds: int,
) -> int | None:
    anchor = (
        attempt.observation_status_at
        or attempt.updated_at
        or attempt.created_at
        or ""
    )
    anchor_ts = _parse_iso_to_epoch(anchor)
    if anchor_ts is None:
        return None
    elapsed = max(0, int(now_ts - anchor_ts))
    return max(0, window_seconds - elapsed)


def _opened_pr_summary(
    attempt: Any,
    *,
    now_ts: float,
    window_seconds: int,
) -> dict[str, Any]:
    summary = {
        "ship_attempt_id": attempt.ship_attempt_id,
        "request_id": attempt.request_id,
        "pr_url": attempt.pr_url,
        "ship_status": attempt.ship_status,
        "ci_status": attempt.ci_status,
        "observation_status": attempt.observation_status or "observing",
        "observation_status_at": attempt.observation_status_at,
        "observation_window_remaining_s": _observation_window_remaining_s(
            attempt,
            now_ts=now_ts,
            window_seconds=window_seconds,
        ),
        "rollback_handle": attempt.rollback_handle,
        "updated_at": attempt.updated_at,
    }
    return summary


def _rollback_recommendation_summary(attempt: Any) -> dict[str, Any]:
    return {
        "ship_attempt_id": attempt.ship_attempt_id,
        "request_id": attempt.request_id,
        "ship_status": attempt.ship_status,
        "pr_url": attempt.pr_url,
        "commit_sha": attempt.commit_sha,
        "rollback_handle": attempt.rollback_handle,
        "observation_status": attempt.observation_status,
        "observation_status_at": attempt.observation_status_at,
        "reason": (
            _compact_status_text(attempt.error_message)
            if attempt.error_message
            else "observation_status=regressed"
        ),
        "updated_at": attempt.updated_at,
    }


def _compute_auto_ship_health(
    udir: Any,
    *,
    now_ts: float | None = None,
) -> dict[str, Any]:
    """Summarize the auto-ship attempt ledger for public get_status.

    Slice B is read-only observability: no polling, no rollback, no
    state mutation. The helper returns compact rows so chatbots can see
    the loop's recent ship/audit state without loading the full ledger.
    """
    import time as _time
    if now_ts is None:
        now_ts = _time.time()

    window_seconds, warnings = _auto_ship_window_seconds()
    out: dict[str, Any] = {
        "recent_attempts": [],
        "opened_prs": [],
        "rollback_recommendations": [],
        "window_seconds": window_seconds,
        "ledger_available": True,
        "warnings": warnings,
    }

    try:
        from workflow.auto_ship_ledger import read_attempts
        attempts = read_attempts(Path(udir))
    except Exception as exc:  # noqa: BLE001 — surfaced, not silent
        out["ledger_available"] = False
        out["warnings"].append(f"ledger_read_failed: {exc}")
        return out

    if not attempts:
        return out

    recent_attempts = list(reversed(attempts[-_AUTO_SHIP_RECENT_ATTEMPT_LIMIT:]))
    opened_attempts = [
        attempt for attempt in reversed(attempts)
        if attempt.ship_status == "opened"
    ]
    regressed_attempts = [
        attempt for attempt in reversed(attempts)
        if attempt.ship_status in {"opened", "merged"}
        and attempt.observation_status == "regressed"
    ]

    out["recent_attempts"] = [
        _compact_ship_attempt(attempt) for attempt in recent_attempts
    ]
    out["opened_prs"] = [
        _opened_pr_summary(
            attempt,
            now_ts=now_ts,
            window_seconds=window_seconds,
        )
        for attempt in opened_attempts
    ]
    out["rollback_recommendations"] = [
        _rollback_recommendation_summary(attempt)
        for attempt in regressed_attempts
    ]
    return out


def _compute_supervisor_liveness(
    udir: Any,
    *,
    now_ts: float | None = None,
) -> dict[str, Any]:
    """Aggregate BranchTask queue + BUG-011 Phase A lease fields into a
    structured liveness snapshot.

    Pairs with PR #212 (write-only lease metadata fields). Uses
    ``getattr`` with defaults so this works both pre- and post-PR-#212
    deployment: pre-#212 BranchTasks lack the lease fields and surface
    as ``"lease_data_unavailable"`` rather than crashing the probe.

    Surfaces the diagnostic the BUG-009 incident (2026-05-02) cost an
    hour of triage to find: container alive but daemon subprocess
    wedged. With this field, the same diagnosis becomes
    ``stuck_pending_max_age_s`` + ``stale_running_tasks`` readable from
    ``get_status``.
    """
    import time as _time
    if now_ts is None:
        now_ts = _time.time()

    out: dict[str, Any] = {
        "queue_state": {
            "depth": 0,
            "pending": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "cancelled": 0,
            "policy_parked_pending": 0,
            "stuck_pending_max_age_s": 0,
            "policy_parked_pending_max_age_s": 0,
            "stuck_running_max_age_s": 0,
        },
        "running_tasks_lease": [],
        "stale_running_tasks": [],
        "warnings": [],
        "lease_data_available": True,
    }

    try:
        from workflow.branch_tasks import read_queue
        queue = read_queue(udir)
    except Exception as exc:  # noqa: BLE001 — best-effort observability
        out["warnings"].append(f"queue_read_failed: {exc}")
        return out

    out["queue_state"]["depth"] = len(queue)
    if not queue:
        return out

    try:
        from workflow.dispatcher import load_dispatcher_config
        dispatcher_config = load_dispatcher_config(Path(udir))
    except Exception as exc:  # noqa: BLE001 — status must remain best-effort
        dispatcher_config = None
        out["warnings"].append(f"dispatcher_config_read_failed: {exc}")

    any_lease_field_seen = False
    pending_ages: list[float] = []
    policy_parked_pending_ages: list[float] = []
    running_ages: list[float] = []

    for task in queue:
        status = getattr(task, "status", "") or ""
        if status in out["queue_state"]:
            out["queue_state"][status] = out["queue_state"].get(status, 0) + 1

        # Pending-task age (queued_at -> now). Detects dispatcher pickup
        # gaps even before a task gets claimed (today's BUG-009 pattern).
        queued_at = getattr(task, "queued_at", "") or ""
        queued_ts = _parse_iso_to_epoch(queued_at) if queued_at else None
        if status == "pending" and queued_ts is not None:
            age = max(0.0, now_ts - queued_ts)
            trigger_source = getattr(task, "trigger_source", "") or ""
            if (
                dispatcher_config is not None
                and not dispatcher_config.tier_enabled(trigger_source)
            ):
                out["queue_state"]["policy_parked_pending"] += 1
                policy_parked_pending_ages.append(age)
            else:
                pending_ages.append(age)

        if status != "running":
            continue

        # Lease metadata (PR #212). Defensive getattr so pre-#212 tasks
        # surface as empty strings rather than AttributeError.
        worker_owner_id = getattr(task, "worker_owner_id", "") or ""
        lease_expires_at = getattr(task, "lease_expires_at", "") or ""
        heartbeat_at = getattr(task, "heartbeat_at", "") or ""
        last_progress_at = getattr(task, "last_progress_at", "") or ""

        if worker_owner_id or lease_expires_at or heartbeat_at:
            any_lease_field_seen = True

        lease_expires_ts = _parse_iso_to_epoch(lease_expires_at)
        heartbeat_ts = _parse_iso_to_epoch(heartbeat_at)
        progress_ts = _parse_iso_to_epoch(last_progress_at)

        lease_remaining_s: int | None = None
        if lease_expires_ts is not None:
            lease_remaining_s = int(lease_expires_ts - now_ts)

        heartbeat_age_s: int | None = None
        if heartbeat_ts is not None:
            heartbeat_age_s = max(0, int(now_ts - heartbeat_ts))

        progress_age_s: int | None = None
        if progress_ts is not None:
            progress_age_s = max(0, int(now_ts - progress_ts))

        # Running-task age tracked for the queue summary even if no lease
        # data exists (pre-#212 fallback).
        if heartbeat_ts is not None:
            running_ages.append(now_ts - heartbeat_ts)
        elif queued_ts is not None:
            running_ages.append(max(0.0, now_ts - queued_ts))

        record = {
            "branch_task_id": getattr(task, "branch_task_id", ""),
            "worker_owner_id": worker_owner_id,
            "lease_expires_at": lease_expires_at,
            "lease_remaining_s": lease_remaining_s,
            "heartbeat_at": heartbeat_at,
            "heartbeat_age_s": heartbeat_age_s,
            "last_progress_at": last_progress_at,
            "progress_age_s": progress_age_s,
        }
        out["running_tasks_lease"].append(record)

        # Stale detection: heartbeat older than 2x refresh OR lease
        # expired. Both signal the daemon owning this task is dead/wedged.
        # Phase C (Codex) will use the same predicate to actively
        # reclaim; this field lets operators see the condition before
        # that ships.
        is_stale = False
        stale_reasons: list[str] = []
        if (
            heartbeat_age_s is not None
            and heartbeat_age_s > _HEARTBEAT_STALE_THRESHOLD_S
        ):
            is_stale = True
            stale_reasons.append(
                f"heartbeat_age_s={heartbeat_age_s} > "
                f"threshold={_HEARTBEAT_STALE_THRESHOLD_S}"
            )
        if lease_remaining_s is not None and lease_remaining_s <= 0:
            is_stale = True
            stale_reasons.append(
                f"lease_expired ({lease_remaining_s}s ago)"
            )

        if is_stale:
            stale = dict(record)
            stale["stale_reasons"] = stale_reasons
            out["stale_running_tasks"].append(stale)

    if pending_ages:
        out["queue_state"]["stuck_pending_max_age_s"] = int(max(pending_ages))
    if policy_parked_pending_ages:
        out["queue_state"]["policy_parked_pending_max_age_s"] = int(
            max(policy_parked_pending_ages)
        )
    if running_ages:
        out["queue_state"]["stuck_running_max_age_s"] = int(max(running_ages))

    # If any pending task is past the stuck threshold, surface a
    # warning. Today's BUG-009 RCA: a pending task that sits >2min
    # without claim means the supervisor restart logic isn't reaching
    # the queue (the exact pattern PR #205 fixed).
    if (
        out["queue_state"]["stuck_pending_max_age_s"]
        > _STUCK_PENDING_THRESHOLD_S
    ):
        out["warnings"].append(
            f"stuck_pending: oldest pending task is "
            f"{out['queue_state']['stuck_pending_max_age_s']}s old "
            f"(threshold {_STUCK_PENDING_THRESHOLD_S}s). Likely "
            "supervisor restart loop, dispatcher disabled, or daemon "
            "subprocess wedged. See PR #206 spec for incident pattern."
        )

    if out["queue_state"]["running"] > 0 and not any_lease_field_seen:
        out["lease_data_available"] = False
        out["warnings"].append(
            "lease_data_unavailable: running tasks present but no lease "
            "fields populated. Either pre-PR-#212 deploy, or daemon is "
            "not stamping heartbeats. Reclaim heuristics cannot run."
        )

    if out["stale_running_tasks"]:
        out["warnings"].append(
            f"{len(out['stale_running_tasks'])} stale running task(s) "
            "(heartbeat past threshold or lease expired). BUG-011 "
            "Phase C reclaim would reclaim these once shipped."
        )

    return out


def get_status(universe_id: str = "") -> str:
    """Factual snapshot of the daemon's identity + routing config.

    See the chatbot-facing docstring on the @mcp.tool wrapper in
    ``workflow.universe_server`` — this implementation is what the
    decorated tool delegates to.
    """
    uid = universe_id or _default_universe()
    udir = _universe_dir(uid)
    universe_exists = udir.is_dir()
    host_id = os.environ.get("UNIVERSE_SERVER_HOST_USER", "host")

    # Load the dispatcher config for the universe.
    try:
        from workflow.dispatcher import (
            DispatcherConfig,
            load_dispatcher_config,
            paid_market_enabled,
        )
        cfg: DispatcherConfig = load_dispatcher_config(udir)
    except Exception as exc:
        return json.dumps({
            "error": "config_load_failed",
            "detail": str(exc),
            "universe_id": uid,
            "universe_exists": universe_exists,
        })

    served_llm_type = (cfg.served_llm_type or "").strip()
    import shutil as _shutil
    api_key_enabled = api_key_providers_enabled()
    api_key_vars_present = [
        name for name in API_KEY_PROVIDER_ENV_VARS if os.environ.get(name)
    ]
    codex_auth_file = Path.home() / ".codex" / "auth.json"
    # Priority chain mirrors the provider-router's preference order:
    # local/subscription endpoints beat API-key-only providers. Ollama is
    # always-local; codex+claude are subprocess-bound CLIs the daemon can drive;
    # xai/gemini/groq are API-key-backed network providers and are ignored
    # unless WORKFLOW_ALLOW_API_KEY_PROVIDERS is explicitly enabled.
    if os.environ.get("OLLAMA_HOST"):
        endpoint_hint = "ollama"
    elif api_key_enabled and os.environ.get("ANTHROPIC_BASE_URL"):
        endpoint_hint = "anthropic"
    elif _shutil.which("codex") and codex_auth_file.is_file():
        endpoint_hint = "codex"
    elif _shutil.which("claude"):
        endpoint_hint = "claude"
    elif api_key_enabled and os.environ.get("OPENAI_API_KEY") and _shutil.which("codex"):
        endpoint_hint = "codex"
    elif api_key_enabled and os.environ.get("XAI_API_KEY"):
        endpoint_hint = "xai"
    elif api_key_enabled and os.environ.get("GEMINI_API_KEY"):
        endpoint_hint = "gemini"
    elif api_key_enabled and os.environ.get("GROQ_API_KEY"):
        endpoint_hint = "groq"
    else:
        endpoint_hint = "unset"

    tier_routing_policy = {
        "served_llm_type": served_llm_type or "any",
        "accept_external_requests": cfg.accept_external_requests,
        "accept_goal_pool": cfg.accept_goal_pool,
        "accept_paid_bids": cfg.accept_paid_bids,
        "allow_opportunistic": cfg.allow_opportunistic,
        "paid_market_flag_on": paid_market_enabled(),
        "tier_status_map": cfg.tier_status_map(),
    }

    # Pull the last N lines of activity.log for evidence of what actually
    # ran recently — chatbot cites this when narrating trust claims.
    activity_tail: list[str] = []
    last_n_calls: list[dict[str, str]] = []
    last_completed_llm = "unknown"
    total_log_lines = 0
    log_path = udir / "activity.log"
    log_read_ok = True
    if log_path.exists():
        try:
            content = log_path.read_text(encoding="utf-8").strip()
            if content:
                # Lazy-import _parse_activity_line so status startup stays cheap.
                from workflow.api.universe import _parse_activity_line
                lines = content.splitlines()
                total_log_lines = len(lines)
                activity_tail = lines[-20:]
                # last_n_calls: structured parse of most-recent entries,
                # newest-first. Reuses _parse_activity_line so the shape
                # matches get_recent_events (dispatch_evidence idiom).
                last_n_calls = [
                    _parse_activity_line(line)
                    for line in reversed(lines[-10:])
                ]
                # Best-effort scan for "llm=" or "provider=" tokens in
                # recent lines. Legacy format varies; chatbot verifies by
                # reading the tail itself if this heuristic misses.
                for line in reversed(lines):
                    for token in ("llm=", "provider=", "model="):
                        idx = line.find(token)
                        if idx >= 0:
                            rest = line[idx + len(token):].split()[0]
                            last_completed_llm = rest.rstrip(",;)")
                            break
                    if last_completed_llm != "unknown":
                        break
        except Exception:  # noqa: BLE001 — best-effort evidence
            log_read_ok = False

    # Per-field caveats — chatbot cites only the degenerate keys instead
    # of wrapping every claim in the global caveat list.
    evidence_caveats: dict[str, list[str]] = {}
    if last_completed_llm == "unknown":
        evidence_caveats["last_completed_request_llm_used"] = [
            "Heuristic found no llm=/provider=/model= token in recent "
            "activity. Either the daemon has not completed a request, or "
            "the log format does not emit a provider token. Do not read "
            "'unknown' as 'no provider routing happened'."
        ]
    if not activity_tail:
        tail_caveats = [
            "activity.log is empty or missing — daemon has not run in "
            "this universe, or the log was cleared."
        ]
        if not log_read_ok:
            tail_caveats.append(
                "activity.log read failed (I/O error). Tail not available."
            )
        evidence_caveats["activity_log_tail"] = tail_caveats
        evidence_caveats["last_n_calls"] = tail_caveats
    else:
        untagged = sum(1 for c in last_n_calls if not c.get("tag"))
        if untagged:
            evidence_caveats["last_n_calls"] = [
                f"{untagged} of {len(last_n_calls)} recent entries carry "
                "no tag (pre-tagging call sites or legacy entries). "
                "Tag-based filtering on these is unreliable."
            ]

    # Global caveats — apply regardless of which evidence field is read.
    caveats: list[str] = []
    if not served_llm_type:
        caveats.append(
            "served_llm_type is unset — daemon accepts ANY LLM type. "
            "Not a local-only guarantee."
        )
    if endpoint_hint == "unset":
        caveats.append(
            "No default LLM provider detected (checked: OLLAMA_HOST, Codex CLI "
            "with subscription auth, and Claude CLI). API-key providers are "
            "ignored unless WORKFLOW_ALLOW_API_KEY_PROVIDERS=1."
        )
    if api_key_vars_present and not api_key_enabled:
        caveats.append(
            "API-key provider env vars are present but ignored by default: "
            f"{', '.join(api_key_vars_present)}. Set "
            "WORKFLOW_ALLOW_API_KEY_PROVIDERS=1 only for an intentional "
            "API-key daemon."
        )
    caveats.append(
        "Legacy surface does NOT enforce per-universe sensitivity_tier. "
        "Full enforcement ships with spec #79 §13 tray observability in "
        "the rewrite. For confidential work today: pin served_llm_type + "
        "run locally + verify via this tool's evidence field."
    )

    # Actionable next steps — §10.7 canonical shape. Only surfaced when
    # the chatbot has something concrete it can do or recommend.
    actionable_next_steps: list[str] = []
    if not served_llm_type:
        actionable_next_steps.append(
            "Set served_llm_type in the dispatcher config to constrain "
            "which LLM types this daemon will accept work for."
        )
    if endpoint_hint == "unset":
        actionable_next_steps.append(
            "Bind a default LLM provider: set OLLAMA_HOST (local Ollama), "
            "install Claude CLI subscription auth, or install Codex CLI with "
            "subscription auth at ~/.codex/auth.json. API-key providers require "
            "explicit WORKFLOW_ALLOW_API_KEY_PROVIDERS=1 opt-in."
        )
    if last_completed_llm == "unknown" and activity_tail:
        actionable_next_steps.append(
            "Inspect the full activity_log_tail — provider token heuristic "
            "may have missed a non-standard format."
        )

    policy_payload = {
        "active_host": {
            "host_id": host_id,
            "served_llm_type": served_llm_type or "any",
            "llm_endpoint_bound": endpoint_hint,
            "api_key_providers_enabled": api_key_enabled,
        },
        "tier_routing_policy": tier_routing_policy,
    }

    if not universe_exists:
        caveats.append(
            f"Universe '{uid}' does not exist on disk. Daemon is reporting "
            "default-fallback identity, not a live universe. Call "
            "universe action=list to see what exists; universe action=create "
            "to bootstrap."
        )
        actionable_next_steps.append(
            f"Create universe '{uid}' or pick an existing one via universe "
            "action=list."
        )

    # BUG-023 Phase 1 — surface per-subsystem disk observability so
    # operators can see a storage-pressure signal via the same MCP probe
    # that carries routing evidence. Uptime canary pages on
    # pressure_level in {warn, critical}; this block never raises so a
    # bad stat call can't break the status probe.
    try:
        from workflow.storage import inspect_storage_utilization, path_size_bytes
        storage_utilization = inspect_storage_utilization()
        # BUG-032 — activity_log + universe_outputs live inside the universe
        # directory, not at data_dir() root; patch the per-subsystem byte
        # counts using the already-resolved udir.
        if "per_subsystem" in storage_utilization:
            checkpoint_bytes = path_size_bytes(udir / "checkpoints.db")
            storage_utilization["per_subsystem"]["checkpoint_db"] = {
                "bytes": checkpoint_bytes,
                "path": str(udir / "checkpoints.db"),
            }
            storage_utilization["per_subsystem"]["activity_log"] = {
                "bytes": path_size_bytes(udir / "activity.log"),
                "path": str(udir / "activity.log"),
            }
            storage_utilization["per_subsystem"]["universe_outputs"] = {
                "bytes": path_size_bytes(udir / "output"),
                "path": str(udir / "output"),
            }
            try:
                from workflow.storage.caps import subsystem_cap_snapshot

                storage_utilization["subsystem_caps"] = subsystem_cap_snapshot({
                    "checkpoints": checkpoint_bytes,
                    "logs": storage_utilization["per_subsystem"]
                    .get("activity_log", {})
                    .get("bytes", 0),
                    "run_artifacts": storage_utilization["per_subsystem"]
                    .get("run_transcripts", {})
                    .get("bytes", 0),
                })
            except Exception:  # noqa: BLE001 — keep status best-effort
                pass
    except Exception as exc:  # noqa: BLE001 — best-effort observability
        storage_utilization = {
            "error": "inspect_failed",
            "detail": str(exc),
        }

    # session_boundary — explicit tool fact so the chatbot can ground
    # "no prior session context" without relying solely on prompt rules.
    # Scans the activity.log for any entry within the last 30 days that
    # can be attributed to the current account user. Best-effort; never
    # raises so a log-read error doesn't break the status probe.
    account_user = os.environ.get("UNIVERSE_SERVER_USER", "anonymous")
    prior_session_ts: str | None = None
    try:
        if activity_tail:
            import re as _re
            for line in reversed(activity_tail):
                if account_user in line:
                    ts_match = _re.match(r"\[(\d{4}-\d{2}-\d{2}[^\]]*)\]", line)
                    if ts_match:
                        prior_session_ts = ts_match.group(1)
                        break
    except Exception:  # noqa: BLE001
        pass

    if prior_session_ts:
        session_boundary = {
            "prior_session_context_available": True,
            "account_user": account_user,
            "last_session_ts": prior_session_ts,
            "note": (
                f"Activity log contains entries for account '{account_user}'. "
                "Prior session context may be available in the log."
            ),
        }
    else:
        session_boundary = {
            "prior_session_context_available": False,
            "account_user": account_user,
            "last_session_ts": None,
            "note": (
                f"No activity log entries found for account '{account_user}' "
                "in this universe's log. Chatbot has no prior session record "
                "to reference — do not assert prior session context."
            ),
        }

    # per_provider_cooldown_remaining (BUG-029 Part A observability): expose
    # per-provider cooldown seconds so the chatbot can narrate "claude-code:
    # 87s remaining" to an operator asking why nothing is happening.
    # Best-effort — a missing router or quota object yields an empty dict.
    per_provider_cooldown_remaining: dict[str, int] = {}
    try:
        from workflow.providers.router import FALLBACK_CHAINS
        all_provider_names: list[str] = list(
            dict.fromkeys(p for chain in FALLBACK_CHAINS.values() for p in chain)
        )
        from workflow.graph_compiler import _get_shared_router
        router = _get_shared_router()
        if router is not None and hasattr(router, "_quota"):
            per_provider_cooldown_remaining = (
                router._quota.cooldown_remaining_dict(all_provider_names)
            )
    except Exception:  # noqa: BLE001 — best-effort observability
        pass

    # sandbox_status: probe bwrap availability once per process (cached).
    # Never raises — a probe error shows as bwrap_available=False with reason.
    try:
        from workflow.providers.base import get_sandbox_status
        sandbox_status = get_sandbox_status()
    except Exception as exc:  # noqa: BLE001 — best-effort observability
        sandbox_status = {"bwrap_available": False, "reason": f"probe_error: {exc}"}

    # BUG-027 — probe required static data files so operators can see which
    # files are absent in the cloud image without waiting for ASP to fail.
    try:
        from workflow.storage.rotation import startup_file_probe
        missing_data_files = startup_file_probe()
    except Exception:  # noqa: BLE001 — best-effort observability
        missing_data_files = []

    # supervisor_liveness — BUG-009 incident (2026-05-02) cost ~1hr of
    # triage finding "container alive but daemon subprocess wedged"
    # without SSH. This block surfaces the diagnosis from the public MCP
    # probe: queue counts + per-running-task lease/heartbeat ages +
    # stale-detection. Pairs with PR #212 (BUG-011 Phase A lease metadata
    # writes); the helper is defensive so a missing branch_tasks file or
    # pre-#212 task shape cannot break the status probe.
    try:
        supervisor_liveness = _compute_supervisor_liveness(udir)
    except Exception as exc:  # noqa: BLE001 — best-effort observability
        supervisor_liveness = {
            "error": "compute_failed",
            "detail": str(exc),
            "lease_data_available": False,
        }

    # auto_ship_health — PR #198 option-2 Slice B. Read-only summary of
    # the append-only auto_ship_attempts ledger so the loop can observe
    # recent ship attempts, open PR observation windows, and regressed
    # attempts that need rollback consideration without SSH or ad hoc
    # file reads.
    try:
        auto_ship_health = _compute_auto_ship_health(udir)
    except Exception as exc:  # noqa: BLE001 — best-effort observability
        auto_ship_health = {
            "error": "compute_failed",
            "detail": str(exc),
            "ledger_available": False,
        }

    # open_brain — PR-119 Slice C. Read-only status surface over daemon
    # mini-brain cost ledgers. This only derives estimates from existing
    # entries/events; it does not trigger memory capture, review, promotion,
    # compaction, or any autonomous scheduling decision.
    try:
        from workflow.daemon_brain import open_brain_status_surface
        open_brain = open_brain_status_surface(_base_path())
    except Exception as exc:  # noqa: BLE001 — best-effort observability
        open_brain = {
            "error": "compute_failed",
            "detail": str(exc),
            "read_only": True,
        }

    release_state = _load_release_state()

    response = {
        "schema_version": 1,
        "active_host": policy_payload["active_host"],
        "tier_routing_policy": tier_routing_policy,
        "evidence": {
            "last_completed_request_llm_used": last_completed_llm,
            "activity_log_tail": activity_tail,
            "activity_log_line_count": total_log_lines,
            "last_n_calls": last_n_calls,
            "policy_hash": _policy_hash(policy_payload),
        },
        "evidence_caveats": evidence_caveats,
        "caveats": caveats,
        "actionable_next_steps": actionable_next_steps,
        "session_boundary": session_boundary,
        "storage_utilization": storage_utilization,
        "per_provider_cooldown_remaining": per_provider_cooldown_remaining,
        "sandbox_status": sandbox_status,
        "missing_data_files": missing_data_files,
        "supervisor_liveness": supervisor_liveness,
        "auto_ship_health": auto_ship_health,
        "open_brain": open_brain,
        "release_state": release_state,
        "universe_id": uid,
        "universe_exists": universe_exists,
    }
    return json.dumps(response)
