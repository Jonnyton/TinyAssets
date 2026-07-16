"""GitHub merge effector for owner-controlled PR merge authorization.

This is the first PR-175 adapter: GitHub branch protection is the
authorization surface, and the effector binds the merge request to the exact
current PR head SHA. Wiki position records may describe review context, but
they are not accepted as merge authorization.
"""

from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tinyassets.effectors.github_pr import (
    _DRY_RUN_ENV,
    _GH_PR_TIMEOUT_S,
    _GITHUB_API,
    _env_truthy,
    _read_capability,
    _resolve_universe_dir,
)

EXTERNAL_WRITE_SINK_GITHUB_MERGE = "github_merge"
AUTHORIZATION_MODE_GITHUB_BRANCH_PROTECTION = "github_branch_protection"

_REPO_RE = re.compile(r"[\w.-]+/[\w.-]+")
_SHA_RE = re.compile(r"[0-9a-fA-F]{40}")
_MERGE_METHODS = frozenset({"merge", "squash", "rebase"})


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


def _error(kind: str, message: str, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"error": message, "error_kind": kind, **extra}
    return result


def _github_api(
    *,
    method: str,
    path: str,
    capability_token: str,
    body: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any] | None]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{_GITHUB_API}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {capability_token}",
            "Content-Type": "application/json",
            "User-Agent": "tinyassets-github-merge-effector/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_GH_PR_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8")
            return (json.loads(raw) if raw.strip() else {}), None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return None, {"http_status": exc.code, "detail": detail}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, {"http_status": None, "detail": str(exc)}
    except (TypeError, ValueError) as exc:
        return None, {"http_status": None, "detail": f"parse error: {exc}"}


def _merge_error_kind(error: dict[str, Any]) -> str:
    status = error.get("http_status")
    if status == 404:
        return "github_pr_not_found"
    if status in (401, 403):
        return "github_merge_denied"
    if status in (405, 409, 422):
        return "github_merge_blocked"
    return "github_api_error"


def _payload_authorization_mode(packet: dict[str, Any], payload: dict[str, Any]) -> str:
    raw = payload.get("authorization_mode") or packet.get("authorization_mode")
    if isinstance(raw, str):
        return raw.strip()
    authorization = payload.get("authorization")
    if authorization is None:
        authorization = packet.get("authorization")
    if isinstance(authorization, dict):
        mode = authorization.get("mode")
        if isinstance(mode, str):
            return mode.strip()
    return ""


def _payload_pr_number(payload: dict[str, Any]) -> int | None:
    raw = payload.get("pr_number")
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
        return value if value > 0 else None
    return None


def _payload_expected_head_sha(payload: dict[str, Any]) -> str:
    raw = payload.get("expected_head_sha") or payload.get("head_sha") or ""
    if not isinstance(raw, str):
        return ""
    value = raw.strip()
    return value if _SHA_RE.fullmatch(value) else ""


_TRUE_STRINGS = frozenset({"1", "true", "yes", "on"})
_FALSE_STRINGS = frozenset({"0", "false", "no", "off", ""})


class _StrictBoolError(ValueError):
    """A bool packet flag held a value that is neither a bool nor a recognized
    true/false string — fail loud rather than fail-open (Fable F2)."""


def _payload_bool_strict(payload: dict[str, Any], key: str) -> bool:
    """Parse a bool flag strictly: a bool, an int, or a KNOWN true/false string.
    Anything else raises ``_StrictBoolError`` (never silently False — the old
    fail-open parse turned an OAuth flag OFF for values like "required")."""
    raw = payload.get(key)
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        return raw != 0
    if isinstance(raw, str):
        t = raw.strip().lower()
        if t in _TRUE_STRINGS:
            return True
        if t in _FALSE_STRINGS:
            return False
    raise _StrictBoolError(
        f"packet flag {key!r} must be a bool or one of "
        f"{sorted(_TRUE_STRINGS | _FALSE_STRINGS)}; got {raw!r}"
    )


#: Effector-consent sink that a server-side owner grant uses to authorize a raw
#: (non-patch-loop) merge. A packet flag can NEVER authorize a queue bypass
#: (Codex R6 C3) — only a durable owner consent grant for this sink can.
RAW_MERGE_CONSENT_SINK = "github_raw_merge"


def _evaluate_merge_policy_gate(
    *,
    payload: dict[str, Any],
    universe_dir: Path | None,
    destination: str,
    pr_number: int,
    actual_head_sha: str,
    canonical_verdict: str,
    github_mergeable_state: Any,
    matched_key: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Patch-loop S4 gate: resolves the GOVERNING merge policy from TRUSTED
    DURABLE review-queue state (not the caller's packet) and enforces it.

    Trust boundary (Codex R6):
    - **Policy authority (C1/C2):** the queue item's stored
      ``merge_policy`` / ``founder_oauth_per_merge`` / ``merge_timer_delay_s``
      GOVERN. Those were written by the present node from the OWNER-BOUND config
      (not a model packet). A packet may only NARROW (stricter policy, enabling
      OAuth) — never disable a gate; omitting policy can never bypass gating.
    - **Verify (C2):** the verify verdict is ``canonical_verdict`` derived from
      GitHub's own ``mergeable_state`` (required checks + no conflicts), NOT a
      model-emitted string.
    - **Raw merge (C3):** a merge for a PR with no queue item is a
      server-authorized path — it requires a durable owner effector-consent
      grant (``RAW_MERGE_CONSENT_SINK``), never a packet flag.
    - **Token regime (C1):** founder-OAuth approvals are checked/consumed under
      the item's CURRENT policy signature (a toggled regime invalidates them).

    Returns ``(error_or_None, gate_info)``. A consent-authorized raw merge (no
    queue item) is a no-op ``(None, {"raw_merge": True})`` — branch-protection
    authorization alone. ``gate_info`` is merged into the success payload.
    """
    from tinyassets import merge_policy as mp
    from tinyassets.storage import review_queue as rq

    # Resolve the queue item — the TRUSTED durable governing state.
    item = None
    if universe_dir is not None:
        for candidate in rq.list_queue(
            universe_dir, destination=destination, limit=0
        ):
            if candidate.get("pr_number") == pr_number:
                item = candidate
                break

    if item is None:
        # No durable patch-loop item. A raw merge requires a SERVER-SIDE owner
        # grant — a durable effector consent for the raw-merge sink. A packet
        # flag alone can NEVER authorize a queue bypass (Codex R6 C3).
        raw_authorized = False
        if universe_dir is not None:
            try:
                from tinyassets.storage.effector_consents import is_consent_active

                raw_authorized = is_consent_active(
                    universe_dir,
                    sink=RAW_MERGE_CONSENT_SINK,
                    destination=destination,
                )
            except Exception:  # noqa: BLE001 — treat consent-read failure as denied
                raw_authorized = False
        if raw_authorized:
            return None, {"raw_merge": True}
        return _error(
            "merge_gate_required",
            (
                f"PR #{pr_number} has no owner-review-queue item; a patch-loop "
                "merge must be enqueued first, or an owner must grant an "
                f"effector consent for sink={RAW_MERGE_CONSENT_SINK!r} "
                f"destination={destination!r} to authorize a raw merge"
            ),
            destination=destination,
            pr_number=pr_number,
            matched_output_key=matched_key,
        ), {}

    # Governing policy from the item; a packet policy may only NARROW (stricter).
    governing_policy = mp.normalize_policy(
        item.get("merge_policy") or mp.DEFAULT_MERGE_POLICY
    )
    policy = governing_policy
    packet_policy_raw = payload.get(mp.MERGE_POLICY_STATE_FIELD)
    if packet_policy_raw is not None and str(packet_policy_raw).strip():
        packet_policy = mp.normalize_policy(packet_policy_raw)
        if mp.is_at_least_as_strict(packet_policy, governing_policy):
            policy = packet_policy  # narrowing toward stricter is allowed

    # Founder-OAuth: governing from the item; the packet may only ENABLE it.
    governing_oauth = bool(item.get("founder_oauth_per_merge"))
    try:
        packet_oauth = _payload_bool_strict(payload, mp.FOUNDER_OAUTH_STATE_FIELD)
    except _StrictBoolError as exc:
        return _error(
            "invalid_bool_flag", str(exc),
            destination=destination, pr_number=pr_number, policy=policy,
            matched_output_key=matched_key,
        ), {}
    founder_oauth_per_merge = governing_oauth or packet_oauth  # OR = narrowing

    # Bind the merge to the REVIEWED head (Codex R5 C1): the item's verify /
    # approval facts describe the exact reviewed commit; refuse if the live head
    # moved since, even when it matches the packet's expected_head_sha.
    reviewed_head = (item.get("head_sha") or "").strip()
    if reviewed_head != actual_head_sha:
        return _error(
            "review_head_stale",
            (
                f"PR #{pr_number} live head {actual_head_sha} does not match the "
                f"reviewed head {reviewed_head or '(unrecorded)'}; the PR changed "
                "since review — refusing to merge an unreviewed head"
            ),
            destination=destination,
            pr_number=pr_number,
            policy=policy,
            reviewed_head_sha=reviewed_head,
            actual_head_sha=actual_head_sha,
            matched_output_key=matched_key,
        ), {}

    # Timer delay from the DURABLE item (not the packet); validate defensively
    # (Codex R5 REQUIRED 2 — enqueue already rejects malformed, this is
    # belt-and-braces if a value was tampered directly).
    timer_delay_s = 0.0
    if policy == mp.MERGE_POLICY_TIMER:
        raw_delay = item.get("merge_timer_delay_s", 0.0)
        try:
            timer_delay_s = float(raw_delay)
        except (TypeError, ValueError):
            timer_delay_s = float("nan")
        if not math.isfinite(timer_delay_s) or timer_delay_s < 0:
            return _error(
                "timer_delay_invalid",
                (
                    f"timer merge of PR #{pr_number} requires a finite, "
                    f"non-negative {mp.TIMER_DELAY_STATE_FIELD}; got {raw_delay!r}"
                ),
                destination=destination,
                pr_number=pr_number,
                policy=policy,
                timer_delay_raw=repr(raw_delay),
                matched_output_key=matched_key,
            ), {}

    # The founder-OAuth token is bound to the item's CURRENT policy regime
    # (Codex R6 C1) — a token minted under a different regime does not satisfy.
    policy_generation = rq._policy_signature(
        item.get("merge_policy"), item.get("founder_oauth_per_merge")
    )
    fresh_approval_present = rq.has_fresh_merge_approval(
        universe_dir,
        destination=destination,
        pr_number=pr_number,
        head_sha=actual_head_sha,
        policy_generation=policy_generation,
    )

    decision = mp.evaluate_merge_eligibility(
        policy=policy,
        # Canonical GitHub verify signal, NOT the model-emitted stored verdict
        # (Codex R6 C2).
        verify_verdict=canonical_verdict,
        item_status=item.get("status", ""),
        founder_oauth_required=founder_oauth_per_merge,
        fresh_approval_present=fresh_approval_present,
        # Timer counts from when the CURRENT head was queued, not the first-ever
        # enqueue — a re-pushed head resets the clock (Codex R2 REQUIRED 2).
        created_at=item.get("head_queued_at", item.get("created_at")),
        now=time.time(),
        timer_delay_s=timer_delay_s,
    )
    if not decision.get("eligible"):
        return _error(
            "merge_policy_blocked",
            (
                f"merge policy '{policy}' blocked PR #{pr_number}: "
                f"{decision.get('reason')}"
            ),
            destination=destination,
            pr_number=pr_number,
            policy=policy,
            policy_reason=decision.get("reason"),
            verify_verdict=canonical_verdict,
            github_mergeable_state=github_mergeable_state,
            item_status=item.get("status"),
            founder_oauth_per_merge=founder_oauth_per_merge,
            matched_output_key=matched_key,
        ), {}

    # Atomically CLAIM the item (→ merging) BEFORE touching GitHub, binding the
    # claim to the eligibility FACTS via the row-version generation token — a
    # same-head re-enqueue that flipped verify pass→fail between this read and
    # the claim changes updated_at and fails the claim (Codex R5 C1 + R6 C2).
    claim = rq.claim_for_merge(
        universe_dir,
        item_id=item["item_id"],
        expected_head_sha=actual_head_sha,
        expected_updated_at=item.get("updated_at"),
    )
    if not claim.get("claimed"):
        return _error(
            "merge_claim_lost",
            (
                f"could not claim PR #{pr_number} for merge "
                f"({claim.get('reason')}); an owner decision or head change "
                "landed first — refusing to merge"
            ),
            destination=destination,
            pr_number=pr_number,
            policy=policy,
            claim_reason=claim.get("reason"),
            current_status=claim.get("current_status"),
            matched_output_key=matched_key,
        ), {}
    prior_status = claim.get("prior_status", "")

    consumed_approval_id = ""
    if founder_oauth_per_merge:
        consumed_approval_id = rq.consume_merge_approval(
            universe_dir,
            destination=destination,
            pr_number=pr_number,
            head_sha=actual_head_sha,
            policy_generation=policy_generation,
        )
        if not consumed_approval_id:
            # Race: eligibility saw a fresh token but it was consumed/revoked
            # before we could claim it. Release the merge claim and fail closed.
            rq.release_merge_claim(
                universe_dir, item_id=item["item_id"], restore_status=prior_status
            )
            return _error(
                "founder_oauth_approval_unavailable",
                (
                    f"founder-OAuth merge of PR #{pr_number} requires a fresh "
                    "single-use approval bound to this head; none was available "
                    "to consume"
                ),
                destination=destination,
                pr_number=pr_number,
                policy=policy,
                matched_output_key=matched_key,
            ), {}

    gate_info = {
        "merge_policy": policy,
        "policy_reason": decision.get("reason"),
        "founder_oauth_per_merge": founder_oauth_per_merge,
        "review_queue_item_id": item.get("item_id"),
        "merge_claim_prior_status": prior_status,
    }
    if consumed_approval_id:
        gate_info["consumed_approval_id"] = consumed_approval_id
    return None, gate_info


def _release_merge_claim_if_held(
    universe_dir: Path | None, gate_info: dict[str, Any]
) -> None:
    """Release a merge claim taken by the gate when the GitHub PUT fails, so the
    item returns to its prior reviewable state rather than being stuck in
    ``merging`` (Codex R5 CRITICAL 1). Best-effort; only acts when a claim was
    actually taken (``merge_claim_prior_status`` present)."""
    item_id = gate_info.get("review_queue_item_id")
    if not item_id or universe_dir is None:
        return
    if "merge_claim_prior_status" not in gate_info:
        return
    try:
        from tinyassets.storage import review_queue as rq

        rq.release_merge_claim(
            universe_dir,
            item_id=item_id,
            restore_status=gate_info["merge_claim_prior_status"],
        )
    except Exception:  # noqa: BLE001 — release is best-effort cleanup
        pass


def run_github_merge_effector(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | None = None,
    run_id: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Merge a GitHub PR only through head-SHA-bound server authorization.

    The initial authorization adapter is GitHub branch protection. The packet
    must explicitly opt into that mode, the effector verifies the current head
    SHA before attempting the merge, and GitHub enforces founder review/status
    checks on the merge endpoint. Missing or stale authorization fails closed.
    """
    del run_id, dry_run
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
            "dry_run": True,
            "phase": "phase_2",
            "reason": "operator_kill_switch_active",
            "kill_switch_env": _DRY_RUN_ENV,
            "intent": packet,
            "matched_output_key": matched_key,
        }

    destination_raw = packet.get("destination", "")
    destination = destination_raw.strip().strip("/") if isinstance(destination_raw, str) else ""
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

    authorization_mode = _payload_authorization_mode(packet, payload)
    if authorization_mode != AUTHORIZATION_MODE_GITHUB_BRANCH_PROTECTION:
        return _error(
            "missing_merge_authorization",
            (
                "github_merge requires authorization.mode="
                f"{AUTHORIZATION_MODE_GITHUB_BRANCH_PROTECTION!r}; wiki position records "
                "are audit context only and cannot authorize a merge"
            ),
            destination=destination,
            authorization_mode=authorization_mode,
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

    capability = _read_capability(destination, universe_dir)
    if not capability:
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "missing_capability",
            "destination": destination,
            "matched_output_key": matched_key,
            "hint": (
                "Add a vcs/github/write credential to this universe's "
                f'per-universe credential vault under destination "{destination}".'
            ),
            "intent": packet,
        }

    pr_obj, err = _github_api(
        method="GET",
        path=f"/repos/{destination}/pulls/{pr_number}",
        capability_token=capability,
    )
    if err is not None:
        return _error(
            _merge_error_kind(err),
            f"GitHub PR lookup failed: {err.get('detail')}",
            destination=destination,
            pr_number=pr_number,
            http_status=err.get("http_status"),
            matched_output_key=matched_key,
        )
    if not isinstance(pr_obj, dict):
        return _error(
            "github_api_error",
            "GitHub PR lookup returned a non-object response",
            destination=destination,
            pr_number=pr_number,
            matched_output_key=matched_key,
        )

    if pr_obj.get("state") != "open":
        return _error(
            "pr_not_open",
            f"PR #{pr_number} is not open",
            destination=destination,
            pr_number=pr_number,
            matched_output_key=matched_key,
        )
    if bool(pr_obj.get("draft")):
        return _error(
            "pr_is_draft",
            f"PR #{pr_number} is still draft",
            destination=destination,
            pr_number=pr_number,
            matched_output_key=matched_key,
        )

    actual_head_sha = ((pr_obj.get("head") or {}).get("sha") or "").strip()
    if actual_head_sha != expected_head_sha:
        return _error(
            "head_sha_mismatch",
            (
                f"PR #{pr_number} head SHA is {actual_head_sha or '(missing)'}, "
                f"not expected {expected_head_sha}; refusing stale authorization"
            ),
            destination=destination,
            pr_number=pr_number,
            expected_head_sha=expected_head_sha,
            actual_head_sha=actual_head_sha,
            matched_output_key=matched_key,
        )

    # Canonical verify signal (Codex R6 C2): do NOT trust a model-emitted
    # "green" — derive merge-eligibility verification from GitHub's own
    # mergeable_state (required-checks + no-conflict). Until a real sandboxed
    # verify runner exists (future slice), GitHub checks ARE the canonical
    # autonomous verify signal. ``clean`` = all required checks pass, mergeable,
    # up to date; anything else is treated as red.
    canonical_verdict = (
        "pass" if (pr_obj.get("mergeable_state") == "clean") else "fail"
    )

    # Patch-loop S4 (G6): gate the merge on durable owner-review-queue state +
    # the OWNER-BOUND policy + founder-OAuth-per-merge, on top of the
    # branch-protection authorization above. A raw (non-patch-loop) merge is a
    # server-authorized path (effector consent), never a packet flag.
    gate_error, gate_info = _evaluate_merge_policy_gate(
        payload=payload,
        universe_dir=universe_dir,
        destination=destination,
        pr_number=pr_number,
        actual_head_sha=actual_head_sha,
        canonical_verdict=canonical_verdict,
        github_mergeable_state=pr_obj.get("mergeable_state"),
        matched_key=matched_key,
    )
    if gate_error is not None:
        return gate_error

    merge_body: dict[str, Any] = {
        "sha": expected_head_sha,
        "merge_method": merge_method,
    }
    for source_key, api_key in (
        ("commit_title", "commit_title"),
        ("commit_message", "commit_message"),
    ):
        value = payload.get(source_key)
        if isinstance(value, str) and value.strip():
            merge_body[api_key] = value

    merge_obj, err = _github_api(
        method="PUT",
        path=f"/repos/{destination}/pulls/{pr_number}/merge",
        capability_token=capability,
        body=merge_body,
    )
    if err is not None:
        # PUT failed — release the merge claim so the item is decidable again.
        _release_merge_claim_if_held(universe_dir, gate_info)
        return _error(
            _merge_error_kind(err),
            f"GitHub merge refused: {err.get('detail')}",
            destination=destination,
            pr_number=pr_number,
            expected_head_sha=expected_head_sha,
            http_status=err.get("http_status"),
            matched_output_key=matched_key,
        )
    if not isinstance(merge_obj, dict) or merge_obj.get("merged") is not True:
        _release_merge_claim_if_held(universe_dir, gate_info)
        return _error(
            "github_merge_blocked",
            f"GitHub merge response did not confirm merged=true: {merge_obj!r}",
            destination=destination,
            pr_number=pr_number,
            expected_head_sha=expected_head_sha,
            matched_output_key=matched_key,
        )

    merge_commit_sha = merge_obj.get("sha") if isinstance(merge_obj.get("sha"), str) else ""
    result = {
        "phase": "phase_2",
        "destination": destination,
        "matched_output_key": matched_key,
        "authorization_mode": AUTHORIZATION_MODE_GITHUB_BRANCH_PROTECTION,
        "pr_number": pr_number,
        "head_sha": expected_head_sha,
        "merge_method": merge_method,
        "merged": True,
        "merge_commit_sha": merge_commit_sha,
        "message": merge_obj.get("message") if isinstance(merge_obj.get("message"), str) else "",
    }
    result.update(gate_info)

    # Codex REQUIRED 4: a confirmed merge must transition the owner review-queue
    # item to terminal 'merged' so owner surfaces stop showing it as
    # pending/approved. Best-effort: the merge already landed on GitHub and
    # cannot be un-done, so a local queue-update failure is surfaced, not raised.
    review_item_id = gate_info.get("review_queue_item_id")
    if review_item_id and universe_dir is not None:
        try:
            from tinyassets.storage import review_queue as rq

            marked = rq.mark_merged(
                universe_dir,
                item_id=review_item_id,
                merge_commit_sha=merge_commit_sha,
            )
            # mark_merged requires the FROM-merging transition. None means the
            # claim was cleared out from under us (e.g. a stale-timeout reclaim)
            # — the merge landed on GitHub but the queue reflects an owner
            # decision. Surface the conflict rather than overwriting it.
            result["review_queue_status"] = (
                "merged" if marked is not None else "mark_merged_conflict"
            )
        except Exception as exc:  # noqa: BLE001 — never fail a landed merge
            result["review_queue_status"] = "mark_merged_failed"
            result["review_queue_error"] = str(exc)

    return result
