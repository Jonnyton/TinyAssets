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

    # ── autonomous (auto / not_before): FAIL-CLOSED setup verification ────────
    if github_api is None:
        return _error(
            "review_gate_unverifiable",
            (
                f"'{preference}' is autonomous and requires a verified GitHub "
                "review gate, but no GitHub client is wired. Refusing autonomous "
                "merge; 'manual' stays available."
            ),
            **common,
        )

    # Read the PR's ACTUAL base branch + node id + head from GitHub — never trust
    # the packet's base_ref for the gate (Codex r11 #1).
    try:
        pull = github_api.get_pull(destination=destination, pr_number=pr_number)
    except Exception as exc:  # noqa: BLE001 — uninspectable ⇒ fail closed
        return _error(
            "pull_unreadable",
            f"could not read {destination}#{pr_number} from GitHub: {exc}",
            **common,
        )
    real_base = (pull.get("base_ref") or "").strip() or base_ref
    pr_node_id = (pull.get("node_id") or "").strip()

    gated, setup = github_native.verify_review_gate_active(
        github_api, destination=destination, branch=real_base,
        app_actor_id=app_actor_id, expected_owner=expected_owner,
    )
    if not gated:
        return _error(
            "review_gate_not_configured",
            (
                f"{destination}@{real_base} is not verifiably review-gated; "
                "configure a ruleset requiring PR + code-owner review + required "
                "status checks + stale-dismissal + latest-push approval, a "
                "CODEOWNERS '* @owner' catch-all, and a known App identity that "
                "is NOT a bypass actor before enabling an autonomous merge "
                "preference. 'manual' stays available (with a warning)."
            ),
            setup=setup, base_ref=real_base,
            **common,
        )

    def _enable_call() -> dict[str, Any]:
        return github_native.enable_auto_merge(
            destination=destination, pr_number=pr_number,
            expected_head_sha=expected_head_sha, pull_request_id=pr_node_id,
        ).to_dict()

    if preference == mp.MERGE_PREFERENCE_AUTO:
        return {
            **common,
            "action": "enable_auto_merge",
            "base_ref": real_base,
            "github_call": _enable_call(),
            "setup": setup,
            "note": (
                "auto preference: GitHub merges the PR the moment its own "
                "required reviews/checks pass; the enable call is head-bound."
            ),
        }

    # not_before: schedule the single durable timer, persisting the expected head
    # SHA + binding revision so the fire path can re-read GitHub + re-authorize
    # against the current binding before acting (Codex r11 #2).
    delay = float(binding.get("not_before_delay_s") or 0.0)
    fire_at = ts + delay
    rq.schedule_not_before(
        universe_dir, destination=destination, pr_number=pr_number,
        not_before=fire_at, now=ts, expected_head_sha=expected_head_sha,
        branch_def_id=branch_def_id, binding_revision=int(binding.get("revision") or 0),
    )
    return {
        **common,
        "action": "scheduled_not_before",
        "base_ref": real_base,
        "not_before": fire_at,
        "delay_s": delay,
        "github_call_on_fire": _enable_call(),
        "setup": setup,
        "note": (
            "not_before preference: a single durable timer (bound to this head + "
            "binding revision) will re-read GitHub, re-authorize, then enable "
            "auto-merge when it fires."
        ),
    }


__all__ = [
    "EXTERNAL_WRITE_SINK_GITHUB_MERGE",
    "run_github_merge_effector",
]
