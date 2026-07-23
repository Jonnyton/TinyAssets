"""GitHub-native merge effector (Phase-1 shape) — patch-loop S4.

**Redirected 2026-07-16 (host decision).** GitHub owns review + merge state.
This effector no longer reconstructs branch protection, mints/consumes local
approval tokens, or drives a local ``approved → merging → merged`` transaction
(all deleted — GitHub enforces its own aggregate rulesets + required checks
atomically at merge). Instead it maps the loop's merge node to the RIGHT native
action for the owner-bound merge PREFERENCE, and RECORDS the exact GitHub call
(Phase 1). Phase 2 wires the live GitHub App and executes the recorded call.

- ``manual`` — no autonomous action; the owner triggers the merge from chat
  after approving. The effector records the ``merge_pr`` call the chat action
  will run (GitHub rechecks its own rules + the expected head SHA atomically).
- ``auto`` — FAIL-CLOSED setup verification (the required-review ruleset must be
  active, ``CODEOWNERS`` present, the App not a bypass actor); if verified,
  records the ``enablePullRequestAutoMerge`` call. If not verified, REFUSES and
  tells the owner what to configure.
- ``not_before`` — same setup verification, then schedules the single durable
  timer; the scheduler enables auto-merge when it fires.

Steady-state GitHub App permissions reduce to ``Contents: write`` +
``Pull requests: write`` (reading rulesets needs only ``Metadata: read`` — the
deleted classic-branch-protection path is what required ``Administration:read``).

The ``github_api`` parameter is the injected read client used for setup
verification; Phase 2 supplies a real GitHub App client, tests supply an
in-memory fake. Without a client, autonomous preferences fail closed. See
``docs/design-notes/2026-07-16-s4-github-native-redirect.md``.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from tinyassets import github_native
from tinyassets import merge_policy as mp
from tinyassets.effectors.github_pr import (
    _DRY_RUN_ENV,
    _env_truthy,
    _resolve_universe_dir,
)
from tinyassets.storage import review_queue as rq

EXTERNAL_WRITE_SINK_GITHUB_MERGE = "github_merge"

_REPO_RE = re.compile(r"[\w.-]+/[\w.-]+")
_SHA_RE = re.compile(r"[0-9a-fA-F]{40}")
_MERGE_METHODS = frozenset({"merge", "squash", "rebase"})


def _error(kind: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"error": message, "error_kind": kind, **extra}


def _parse_packet(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        packet = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped or not stripped.startswith("{"):
            return None
        try:
            packet = json.loads(stripped)
        except (TypeError, ValueError):
            return None
        if not isinstance(packet, dict):
            return None
    else:
        return None
    if packet.get("sink") != EXTERNAL_WRITE_SINK_GITHUB_MERGE:
        return None
    return packet


def _payload_pr_number(payload: dict[str, Any]) -> int | None:
    raw = payload.get("pr_number")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        n = int(raw.strip())
        return n if n > 0 else None
    return None


def _payload_expected_head_sha(payload: dict[str, Any]) -> str:
    raw = payload.get("expected_head_sha")
    if isinstance(raw, str) and _SHA_RE.fullmatch(raw.strip()):
        return raw.strip()
    return ""


def run_github_merge_effector(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | None = None,
    run_id: str = "",
    dry_run: bool = True,
    authoritative_branch_def_id: str = "",
    github_api: Any = None,
    verifier_api: Any = None,
    app_actor_id: Any = None,
    expected_owner: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    """Map the loop's merge node to the native GitHub action for the owner-bound
    merge preference, RECORDING the exact call (Phase 1). Never a live merge.

    ``authoritative_branch_def_id`` selects the owner-bound preference from the
    run context (the packet is advisory — a model-emitted packet cannot point at
    another branch's binding). ``github_api`` is the injected read client for
    fail-closed setup verification (autonomous preferences only); when present
    the gate is verified against the PR's ACTUAL base branch (read from GitHub,
    never the packet's base_ref — Codex r11 #1) and the recorded auto-merge call
    is head-bound with the resolved PR node id + expected head (Codex r11 #4).
    ``expected_owner`` is the founder's GitHub handle the CODEOWNERS catch-all
    must name.
    """
    del run_id, dry_run  # Phase 1 records/schedules; no live merge here.
    ts = now if now is not None else time.time()
    universe_dir = _resolve_universe_dir(base_path)

    matched_key: str | None = None
    packet: dict[str, Any] | None = None
    for key in output_keys or []:
        if not isinstance(key, str) or key not in run_state:
            continue
        candidate = _parse_packet(run_state.get(key))
        if candidate is None:
            continue
        matched_key = key
        packet = candidate
        break
    if packet is None:
        return _error(
            "no_matching_packet",
            (
                f"node '{node_id}' declared effects=[github_merge] but no output_key "
                "held a parseable external_write_packet with sink='github_merge'"
            ),
        )

    if _env_truthy(_DRY_RUN_ENV):
        return {
            "phase": "phase_1",
            "recorded": False,
            "reason": "operator_kill_switch_active",
            "kill_switch_env": _DRY_RUN_ENV,
            "intent": packet,
            "matched_output_key": matched_key,
        }

    destination_raw = packet.get("destination", "")
    destination = (
        destination_raw.strip().strip("/") if isinstance(destination_raw, str) else ""
    )
    if not destination or not _REPO_RE.fullmatch(destination):
        return _error(
            "invalid_destination",
            f"packet.destination must be an owner/repo GitHub repository, got {destination_raw!r}",
            matched_output_key=matched_key,
        )

    payload = packet.get("payload")
    if not isinstance(payload, dict):
        return _error(
            "invalid_payload",
            "packet.payload must be a JSON object",
            destination=destination,
            matched_output_key=matched_key,
        )

    pr_number = _payload_pr_number(payload)
    if pr_number is None:
        return _error(
            "invalid_pr_number",
            "packet.payload.pr_number must be a positive integer",
            destination=destination,
            matched_output_key=matched_key,
        )

    expected_head_sha = _payload_expected_head_sha(payload)
    if not expected_head_sha:
        return _error(
            "missing_expected_head_sha",
            "packet.payload.expected_head_sha must be a 40-character commit SHA",
            destination=destination,
            pr_number=pr_number,
            matched_output_key=matched_key,
        )

    merge_method = payload.get("merge_method") or "squash"
    if not isinstance(merge_method, str) or merge_method not in _MERGE_METHODS:
        return _error(
            "invalid_merge_method",
            "packet.payload.merge_method must be one of merge, squash, or rebase",
            destination=destination,
            pr_number=pr_number,
            matched_output_key=matched_key,
        )

    base_ref = payload.get("base_ref")
    base_ref = base_ref.strip() if isinstance(base_ref, str) and base_ref.strip() else "main"

    # Preference comes from the OWNER-BOUND binding resolved by the authoritative
    # branch_def_id (run context), never from the model packet.
    branch_def_id = (authoritative_branch_def_id or "").strip()
    if not branch_def_id:
        raw_bdid = payload.get("branch_def_id")
        branch_def_id = raw_bdid.strip() if isinstance(raw_bdid, str) else ""
    binding = rq.resolve_merge_preference_binding(
        universe_dir, branch_def_id=branch_def_id
    )
    preference = mp.normalize_preference(binding["merge_preference"])
    if preference not in mp.MERGE_PREFERENCES:
        return _error(
            "unsupported_preference",
            f"unknown merge preference {preference!r} bound for {branch_def_id!r}",
            destination=destination,
            pr_number=pr_number,
            matched_output_key=matched_key,
        )

    common: dict[str, Any] = {
        "phase": "phase_1",
        "recorded": True,
        "destination": destination,
        "pr_number": pr_number,
        "expected_head_sha": expected_head_sha,
        "merge_preference": preference,
        "branch_def_id": branch_def_id,
        "matched_output_key": matched_key,
    }

    # ── manual: the owner triggers the merge from chat; no autonomous action ──
    if preference == mp.MERGE_PREFERENCE_MANUAL:
        call = github_native.merge_pr(
            destination=destination, pr_number=pr_number,
            expected_head_sha=expected_head_sha, merge_method=merge_method,
        )
        return {
            **common,
            "action": "await_owner_merge",
            "github_call": call.to_dict(),
            "note": (
                "manual preference: the owner triggers the merge from chat after "
                "approving; GitHub rechecks its own required reviews/checks and "
                "the expected head SHA atomically."
            ),
        }

    # ── autonomous (auto / not_before): delegate to THE ONE shared fail-closed
    # executor (Codex r14 #2), so the initial effector, the resumed continuation,
    # and the timer fire all run the identical gate against fresh GitHub state.
    result = run_autonomous_merge(
        universe_dir, destination=destination, pr_number=pr_number,
        branch_def_id=branch_def_id, expected_head_sha=expected_head_sha,
        base_ref_hint=base_ref, github_api=github_api, verifier_api=verifier_api,
        app_actor_id=app_actor_id, expected_owner=expected_owner, now=ts,
    )
    if not result.get("ok"):
        return _error(
            result.get("error_kind", "autonomous_merge_refused"),
            result.get("error", "autonomous merge refused"),
            setup=result.get("setup"), base_ref=result.get("base_ref"),
            **common,
        )
    return {**common, **{k: v for k, v in result.items() if k != "ok"}}


def run_autonomous_merge(
    universe_dir: Any,
    *,
    destination: str,
    pr_number: int,
    branch_def_id: str,
    expected_head_sha: str,
    base_ref_hint: str = "main",
    github_api: Any,
    verifier_api: Any = None,
    app_actor_id: Any = None,
    expected_owner: str = "",
    firing: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    """THE ONE fail-closed autonomous-merge executor (Codex r14 #2/#5), shared by
    the initial effector, the resumed continuation, AND the timer fire. Re-runs
    the FULL gate against FRESH GitHub state (the PR's actual base ref + head +
    node id, read now) via the ruleset-read VERIFIER identity every time — state
    can change between review and merge, so the gate must re-run before ANY
    autonomous action.

    ``preference`` is resolved from the OWNER binding here (never a packet).
    Returns ``{"ok": bool, "action"|"error_kind", "state"?, "effects"?,
    "not_before"?, ...}``. Fails closed on: no merge client, no verifier
    identity, unreadable PR, or an unverified gate.
    """
    ts = now if now is not None else time.time()
    binding = rq.resolve_merge_preference_binding(
        universe_dir, branch_def_id=branch_def_id,
    )
    preference = mp.normalize_preference(binding["merge_preference"])
    # The CODEOWNERS owner is resolved from the AUTHORITATIVE binding (Codex r14
    # #2), never a packet / undefined branch field. An explicit arg overrides.
    expected_owner = expected_owner or (binding.get("founder_github_handle") or "")
    if preference == mp.MERGE_PREFERENCE_MANUAL:
        # Manual never merges autonomously — the owner triggers it, GitHub
        # enforces the ruleset at merge. Nothing for the executor to do.
        return {"ok": True, "action": "await_owner_merge", "state": "await_owner_merge"}
    if github_api is None:
        return {"ok": False, "error_kind": "review_gate_unverifiable",
                "error": ("no GitHub merge client wired; refusing autonomous "
                          "merge — 'manual' stays available")}
    if verifier_api is None:
        return {"ok": False, "error_kind": "autonomous_requires_verifier",
                "error": (
                    "autonomous merge needs the ruleset-read verifier identity "
                    "(the App's minimal scope can't see bypass_actors); 'manual' "
                    "stays available")}
    try:
        pull = github_api.get_pull(destination=destination, pr_number=pr_number)
    except Exception as exc:  # noqa: BLE001 — uninspectable ⇒ fail closed
        return {"ok": False, "error_kind": "pull_unreadable", "error": str(exc)}
    real_base = (pull.get("base_ref") or "").strip() or base_ref_hint
    pr_node_id = (pull.get("node_id") or "").strip()
    live_head = (pull.get("head_sha") or "").strip()
    # Head-bind against FRESH GitHub state: if the PR head moved since the
    # decision, refuse (the reviewed content is gone).
    want_head = (expected_head_sha or "").strip()
    if want_head and live_head and want_head != live_head:
        return {"ok": False, "error_kind": "head_moved",
                "error": f"reviewed head {want_head[:8]} != live head {live_head[:8]}"}
    gated, setup = github_native.verify_review_gate_active(
        verifier_api, destination=destination, branch=real_base,
        app_actor_id=app_actor_id, expected_owner=expected_owner,
    )
    if not gated:
        return {"ok": False, "error_kind": "review_gate_not_configured",
                "setup": setup, "base_ref": real_base,
                "error": f"{destination}@{real_base} is not verifiably review-gated"}

    # `auto` enables now; `not_before` enables now ONLY when the timer is FIRING
    # (its delay already elapsed) — otherwise it (re)schedules the timer.
    if preference == mp.MERGE_PREFERENCE_AUTO or (
        preference == mp.MERGE_PREFERENCE_NOT_BEFORE and firing
    ):
        call = github_native.enable_auto_merge(
            destination=destination, pr_number=pr_number,
            expected_head_sha=want_head, pull_request_id=pr_node_id,
        )
        return {"ok": True, "action": "enable_auto_merge",
                "state": "approved_auto_merge_enabled", "github_call": call.to_dict(),
                "base_ref": real_base, "setup": setup}

    # not_before: honor the FULL configured delay + persist the safety anchors
    # (Codex r14 #5). The timer-watcher re-runs THIS executor at fire.
    delay = float(binding.get("not_before_delay_s") or 0.0)
    fire_at = ts + delay
    rq.schedule_not_before(
        universe_dir, destination=destination, pr_number=pr_number,
        not_before=fire_at, now=ts, expected_head_sha=want_head,
        branch_def_id=branch_def_id, binding_revision=int(binding.get("revision") or 0),
    )
    on_fire = github_native.enable_auto_merge(
        destination=destination, pr_number=pr_number,
        expected_head_sha=want_head, pull_request_id=pr_node_id,
    )
    return {"ok": True, "action": "scheduled_not_before", "not_before": fire_at,
            "delay_s": delay, "state": "approved_timer_scheduled",
            "github_call_on_fire": on_fire.to_dict(), "base_ref": real_base,
            "setup": setup}


__all__ = [
    "EXTERNAL_WRITE_SINK_GITHUB_MERGE",
    "run_github_merge_effector",
    "run_autonomous_merge",
]
