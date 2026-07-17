"""Helpers for the file_bug → canonical investigation branch pipeline (Task #33).

When a chatbot files a bug via wiki action=file_bug, the canonical
bug-investigation branch is auto-queued with the bug payload. This module
holds the constant Goal id + payload mapping + result-comment-attach helper.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

_logger = logging.getLogger(__name__)

_BUGS_CATEGORY = "bugs"
_PATCH_PACKET_HEADING = "## Patch Packet"

# Goal id for the bug_investigation Goal. Set via env when Phase 0 completes
# (Mark's branch bound + canonical). Default empty = auto-trigger disabled
# (filing falls back to wiki-write-only).
BUG_INVESTIGATION_GOAL_ID = os.environ.get("TINYASSETS_BUG_INVESTIGATION_GOAL_ID", "")

_PAYLOAD_KEYS = (
    "bug_id",
    "title",
    "component",
    "severity",
    "kind",
    "effort_class",
    "effort_attention",
    "effort_dispatch_lane",
    "observed",
    "expected",
    "repro",
    "workaround",
)


def is_auto_trigger_enabled() -> bool:
    """True if a canonical bug-investigation branch is configured to auto-run."""
    return bool(BUG_INVESTIGATION_GOAL_ID)


def build_run_payload(bug_frontmatter: dict) -> dict:
    """Map BUG-NNN frontmatter → canonical investigation branch input shape."""
    payload = {k: bug_frontmatter.get(k, "") for k in _PAYLOAD_KEYS}
    if bug_frontmatter.get("effort_classification"):
        payload["effort_classification"] = bug_frontmatter["effort_classification"]
    if bug_frontmatter.get("effort_dispatch_route"):
        payload["effort_dispatch_route"] = bug_frontmatter["effort_dispatch_route"]
    payload["request_text"] = str(
        bug_frontmatter.get("request_text") or _format_request_text(payload)
    )
    return payload


def _format_request_text(payload: dict) -> str:
    kind = str(payload.get("kind") or "bug").strip() or "bug"
    bug_id = str(payload.get("bug_id") or "untracked").strip() or "untracked"
    title = str(payload.get("title") or "Untitled").strip() or "Untitled"
    lines = [f"{kind} {bug_id}: {title}", ""]
    for label, key in (
        ("Component", "component"),
        ("Severity", "severity"),
        ("Effort Class", "effort_class"),
        ("Dispatch Lane", "effort_dispatch_lane"),
        ("Observed", "observed"),
        ("Expected", "expected"),
        ("Repro", "repro"),
        ("Workaround", "workaround"),
    ):
        value = str(payload.get(key) or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines).strip()


def format_investigation_comment(
    run_id: str = "",
    status: str = "queued",
    request_id: str = "",
) -> str:
    """Format the Investigation section appended to the bug page."""
    if request_id:
        return (
            f"\n\n## Investigation\n\n"
            f"Queued: dispatcher_request_id=`{request_id}` (status={status})\n"
        )
    return (
        f"\n\n## Investigation\n\n"
        f"Queued: investigation_run_id=`{run_id}` (status={status})\n"
    )


def format_patch_packet_comment(patch_packet: dict) -> str:
    """Format the Patch Packet section appended to the bug page after run completes."""
    sections = []
    for key in ("minimal_repro", "root_cause", "test_plan", "implementation_sketch"):
        if patch_packet.get(key):
            label = key.replace("_", " ").title()
            sections.append(f"### {label}\n\n{patch_packet[key]}")
    if not sections:
        return ""
    return "\n\n## Patch Packet\n\n" + "\n\n".join(sections)


def _slug_from_bug_id(bug_id: str) -> str:
    """Convert BUG-NNN (or bug-nnn) to the canonical lowercase slug prefix."""
    return re.sub(r"[^a-z0-9-]", "-", bug_id.lower()).strip("-")


def _find_bug_page(bug_id: str) -> Path | None:
    """Locate the bug page file in pages/bugs/ resolving case aliases."""
    from tinyassets.storage import wiki_path

    bugs_dir = wiki_path() / "pages" / _BUGS_CATEGORY
    if not bugs_dir.is_dir():
        return None

    slug_prefix = _slug_from_bug_id(bug_id)
    # Exact prefix match (lowercase) — the file starts with the bug slug
    for candidate in bugs_dir.glob("*.md"):
        if candidate.stem.lower().startswith(slug_prefix):
            return candidate
    return None


def attach_patch_packet_comment(
    bug_id: str,
    patch_packet: dict,
    base_path: "Path | str | None" = None,  # noqa: F821 — accepted but unused; wiki root resolves independently
) -> dict:
    """Append (or replace) a Patch Packet section on the bug's wiki page.

    Returns:
        {"status": "attached", "bug_id": ..., "patch_packet_size_bytes": ...}
        {"status": "error",    "bug_id": ..., "error": "<reason>"}
    """
    if not patch_packet or not any(patch_packet.get(k) for k in (
        "minimal_repro", "root_cause", "test_plan", "implementation_sketch"
    )):
        return {
            "status": "error",
            "bug_id": bug_id,
            "error": "patch_packet is empty — nothing to attach",
        }

    page_path = _find_bug_page(bug_id)
    if page_path is None:
        return {
            "status": "error",
            "bug_id": bug_id,
            "error": f"Bug page not found for {bug_id}",
        }

    try:
        existing = page_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"status": "error", "bug_id": bug_id, "error": f"Read failed: {exc}"}

    packet_section = format_patch_packet_comment(patch_packet)

    # Replace existing Patch Packet section if present, otherwise append.
    if _PATCH_PACKET_HEADING in existing:
        # Trim from the heading to end-of-file (or next same-level heading).
        head_idx = existing.index(_PATCH_PACKET_HEADING)
        # Find next ## heading after the patch packet (if any)
        next_h2 = re.search(r"\n## ", existing[head_idx + len(_PATCH_PACKET_HEADING):])
        if next_h2:
            tail = existing[head_idx + len(_PATCH_PACKET_HEADING) + next_h2.start():]
            body = existing[:head_idx].rstrip() + packet_section + "\n\n" + tail.lstrip("\n")
        else:
            body = existing[:head_idx].rstrip() + packet_section + "\n"
    else:
        body = existing.rstrip() + packet_section + "\n"

    try:
        page_path.write_text(body, encoding="utf-8")
    except OSError as exc:
        return {"status": "error", "bug_id": bug_id, "error": f"Write failed: {exc}"}

    _logger.info("attach_patch_packet_comment | %s | %s", bug_id, page_path.name)
    return {
        "status": "attached",
        "bug_id": bug_id,
        "patch_packet_size_bytes": len(packet_section.encode()),
    }


# ── Dispatcher integration ─────────────────────────────────────────────────────

REQUEST_TYPE_BUG_INVESTIGATION = "bug_investigation"


class HandlerDeletedError(RuntimeError):
    """The investigation handler branch was DELETED between the upstream
    existence check and the durable enqueue (Codex r14 #4 G4 deletion race).

    Raised at ``append_task`` time (the durable boundary) so a concurrent delete
    can never persist a task against a dead reference. A RuntimeError subclass so
    the existing ``_maybe_enqueue_investigation`` recovery (filing survives,
    nothing queued) catches it."""

# Env var: set to the branch_def_id of the canonical bug-investigation branch.
# When set, enqueue_investigation_request routes through the general dispatcher.
BUG_INVESTIGATION_BRANCH_DEF_ID = os.environ.get(
    "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", ""
)


def enqueue_investigation_request(
    bug_ref: dict,
    canonical_branch_def_id: str,
    base_path: "Path | str",
    universe_id: str = "",
    priority: int = 0,
    request_id: str = "",
) -> str:
    """Enqueue a bug-investigation dispatcher request.

    Creates a BranchTask with request_type=bug_investigation and appends it
    to the universe's branch_tasks.json queue. Returns the request_id
    (branch_task_id). Does NOT start a run — a daemon claims it later.

    Args:
        bug_ref: dict with at least bug_id; full frontmatter is passed as inputs.
        canonical_branch_def_id: branch_def_id of the investigation branch.
        base_path: universe directory (Path or str).
        universe_id: universe id; inferred from base_path.name if empty.
        priority: priority_weight for the task (higher = claimed sooner).

    Raises:
        ValueError: if canonical_branch_def_id is empty.
        RuntimeError: if the dispatcher request type is not accepted by this
            process's TINYASSETS_REQUEST_TYPE_PRIORITIES config (so callers can
            fall back to direct run_branch in degraded mode).
    """
    from datetime import datetime, timezone

    from tinyassets.api.market import filing_effort_dispatch_route
    from tinyassets.branch_tasks import BranchTask, append_task_if_absent
    from tinyassets.dispatcher import prefers_request_type

    if not canonical_branch_def_id:
        raise ValueError("canonical_branch_def_id is required")

    if not prefers_request_type(REQUEST_TYPE_BUG_INVESTIGATION):
        raise RuntimeError(
            f"request_type={REQUEST_TYPE_BUG_INVESTIGATION!r} not in "
            "TINYASSETS_REQUEST_TYPE_PRIORITIES; cannot enqueue via dispatcher"
        )

    import uuid
    base = Path(base_path)
    uid = universe_id or base.name
    # Codex r22 #1: a caller may pass a STABLE ``request_id`` (the retry consumer
    # derives one deterministically from the receipt) so a re-poll / crash / two
    # concurrent pollers can't double-enqueue — the idempotent append below dedups
    # on it. The happy path passes none -> a fresh uuid4 that never collides.
    request_id = request_id or str(uuid.uuid4())
    effort_route = filing_effort_dispatch_route(
        bug_ref.get("effort_classification")
    )
    bug_payload = dict(bug_ref)
    bug_payload["effort_dispatch_route"] = effort_route
    bug_payload["effort_dispatch_lane"] = effort_route["lane"]

    task = BranchTask(
        branch_task_id=request_id,
        branch_def_id=canonical_branch_def_id,
        universe_id=uid,
        inputs=build_run_payload(bug_payload),
        trigger_source="owner_queued",
        priority_weight=float(priority),
        pickup_signal_weight=float(effort_route.get("pickup_signal_weight") or 0.0),
        queued_at=datetime.now(timezone.utc).isoformat(),
        request_type=REQUEST_TYPE_BUG_INVESTIGATION,
    )
    # G4 deletion race (Codex r14 #4): the handler was existence-checked upstream
    # (resolve time), but a concurrent delete may have removed it since. Revalidate
    # at the enqueue boundary — immediately before append_task. This NARROWS the
    # window but does NOT fully close it (Codex r15 #5): the registry (SQLite) and
    # the queue (JSON) are not atomically joinable, and a delete can still land
    # after this check or while the task sits queued. FULL closure is the
    # CONSUMPTION-time revalidation at claim (``revalidate_investigation_handler``
    # / the ``claim_task`` dead-ref guard below), which refuses to RUN a task
    # whose handler is gone. Fail here with a structured HandlerDeletedError (the
    # caller recovers it; filing persists, nothing queued).
    if not _handler_branch_exists(base_path, canonical_branch_def_id):
        _logger.warning(
            "enqueue_investigation_request | %s | handler %s deleted before enqueue "
            "(race) — refusing to queue a dead reference",
            bug_ref.get("bug_id", "?"), canonical_branch_def_id,
        )
        raise HandlerDeletedError(
            f"investigation handler {canonical_branch_def_id!r} was deleted before "
            "enqueue (concurrent delete race); refusing to queue a dead reference"
        )
    # IDEMPOTENT append (Codex r22 #1): dedup on branch_task_id under the queue
    # lock so a stable-id re-enqueue is exactly-once. ``appended`` False means the
    # task was already present (a prior poll / crash-recovery) — still success.
    appended = append_task_if_absent(base, task)
    _logger.info(
        "enqueue_investigation_request | %s | %s | appended=%s",
        bug_ref.get("bug_id", "?"), request_id, appended,
    )
    return request_id


def revalidate_investigation_handler(
    base_path: "Path | str", branch_def_id: str,
) -> tuple[str, str]:
    """CONSUMPTION-time revalidation of an investigation handler (Codex r15 #5),
    now TRI-STATE (Codex r19 #2).

    The enqueue-boundary check only narrows the deletion-race window; a delete can
    still land while the task sits queued. So the CONSUMER (claim / run path) must
    revalidate the handler before running a claimed task — but must distinguish a
    DEFINITIVE deletion (terminal) from a TRANSIENT storage error (retryable), or
    a momentary SQLite lock permanently discards the task.

    Returns ``(status, reason)``:
    - ``("ok", "ok")`` — the handler exists; proceed.
    - ``("dead", "handler_deleted:<id>")`` — DEFINITIVELY gone; terminal dead_ref.
    - ``("unavailable", "handler_unavailable:<id>")`` — TRANSIENT registry error;
      leave the task RETRYABLE (do not claim, do not terminate).
    Never raises."""
    if not branch_def_id:
        return "dead", "handler_missing:empty"
    st = _handler_branch_status(base_path, branch_def_id)
    if st == "exists":
        return "ok", "ok"
    if st == "unavailable":
        return "unavailable", f"handler_unavailable:{branch_def_id}"
    return "dead", f"handler_deleted:{branch_def_id}"


def investigation_task_id(trigger_attempt_id: str) -> str:
    """The STABLE, deterministic dispatcher task id for an investigation trigger
    receipt (Codex r23 #1). BOTH the INITIAL file_bug enqueue AND the retry
    consumer derive the task's ``branch_task_id`` from this, so an
    initial-enqueue -> crash-before-mark_queued -> retry collapses to ONE task via
    ``append_task_if_absent`` — exactly-once across the REAL crash window, not just
    retry<->retry. Empty ``trigger_attempt_id`` (no receipt) -> "" so the caller
    falls back to a fresh uuid4."""
    return f"inv:{trigger_attempt_id}" if trigger_attempt_id else ""


def _maybe_enqueue_investigation(
    bug_id: str,
    frontmatter: dict,
    base_path: "Path | str",
    universe_id: str = "",
    resolved_branch_def_id: str | None = None,
    request_id: str = "",
) -> str | None:
    """Forward-trigger seam for `_wiki_file_bug` post-write.

    Resolution order (PR-127 / M6 cutover Step 4):

      1. If ``TINYASSETS_BUG_INVESTIGATION_GOAL_ID`` is set AND that
         Goal has a ``canonical_branch_version_id`` (set via
         ``goals action=set_canonical`` or auto-refreshed from the
         leaderboard when ``auto_canonical_via_leaderboard`` is on),
         resolve the canonical to a ``branch_def_id`` and enqueue
         a dispatcher request against it.
      2. Otherwise, fall back to
         ``TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID`` — the round-1
         cheat-loop env. This fallback is intentional graceful
         degradation: the cutover plan removes the env in a
         subsequent slice (Step 5/6) once the canonical handler has
         been observation-window'd.

    Returns request_id when enqueued, None when skipped or recovered
    from error. Swallows dispatcher-rejection (RuntimeError) and
    bad-input (ValueError) so a filing never breaks because of
    investigation-pipeline misconfiguration.

    Single-resolution (Codex S1 latest-model Finding 3): the caller resolves the
    handler ONCE (for the receipt) and threads it in via
    ``resolved_branch_def_id`` so the receipt and the enqueue reflect the SAME
    resolution — a canonical change/removal between two separate resolutions
    would otherwise yield mismatched provenance. When ``None`` (other callers)
    this resolves internally as before.
    """
    if not bug_id:
        _logger.info("_maybe_enqueue_investigation | skipped | missing bug_id")
        return None

    if resolved_branch_def_id is None:
        canonical_branch_def_id = _resolve_investigation_handler(base_path)
    else:
        canonical_branch_def_id = resolved_branch_def_id
    if not canonical_branch_def_id:
        return None

    bug_ref = dict(frontmatter or {})
    bug_ref["bug_id"] = bug_id
    # Module-attribute lookup (NOT bare-name) so `patch("tinyassets.bug_investigation
    # .enqueue_investigation_request", ...)` reliably takes effect across full-suite
    # ordering. Bare-name lookup races with sibling tests that hold local-name
    # bindings to the original function.
    enqueue = getattr(sys.modules[__name__], "enqueue_investigation_request")
    try:
        return enqueue(
            bug_ref=bug_ref,
            canonical_branch_def_id=canonical_branch_def_id,
            base_path=base_path,
            universe_id=universe_id,
            # Codex r23 #1: the caller threads the STABLE receipt-derived task id
            # so the INITIAL enqueue and any later retry produce ONE task.
            request_id=request_id,
        )
    except (RuntimeError, ValueError) as exc:
        _logger.info(
            "_maybe_enqueue_investigation | %s | recovered: %s", bug_id, exc
        )
        return None


def _handler_branch_status(base_path: "Path | str", branch_def_id: str) -> str:
    """TRI-STATE existence of a handler branch in the registry (Codex r19 #2):

    - ``"exists"`` — the branch definition is present.
    - ``"missing"`` — DEFINITIVE: a KeyError, i.e. the registry read SUCCEEDED
      and the id is genuinely not there (a truly deleted handler). Terminal.
    - ``"unavailable"`` — the registry read itself FAILED for ANY other reason
      (SQLite locked/busy, PermissionError, I/O OSError, an uninitialized
      "no such table" registry, …). This is NOT proof the handler is gone, so
      the caller must treat it as RETRYABLE, never permanently discard the task.

    Codex r21 #1b: ONLY a KeyError proves deletion. The r20 version classified
    every non-lock error as "missing", so a PermissionError or I/O OSError could
    terminally dead_ref a VALID task — too aggressive. Fail toward RETRY, not
    permanent discard. (Conflating the two the OTHER way — the pre-r19 bug —
    turned a momentary lock into a permanent dead_ref.)
    """
    if not branch_def_id:
        return "missing"
    try:
        from tinyassets.api.helpers import _base_path
        from tinyassets.daemon_server import get_branch_definition

        # The branch registry lives at the CANONICAL data root — callers of the
        # investigation pipeline pass per-universe paths (the queue location),
        # which do not carry the registry DB. Resolve the root explicitly so an
        # existing handler is never false-negatived (and per the env-var
        # invariant: path defaults go through the resolver APIs).
        del base_path  # documented: intentionally not the registry root
        get_branch_definition(_base_path(), branch_def_id=branch_def_id)
        return "exists"
    except KeyError:
        # DEFINITIVE deletion: the read succeeded, the id is not in the registry.
        return "missing"
    except Exception as exc:  # noqa: BLE001
        # EVERY other read failure stays RETRYABLE (Codex r21 #1b): a
        # PermissionError, I/O OSError, uninitialized registry, SQLite
        # contention, etc. are NOT proof of deletion. A real deployment always
        # has the registry initialized, so a live nonexistent handler raises
        # KeyError above; here we refuse to permanently discard a valid task on
        # an environmental/transient failure.
        _logger.warning(
            "_handler_branch_status | registry read failed for %s (%s) — "
            "UNAVAILABLE/retryable, NOT a definitive miss", branch_def_id, exc,
        )
        return "unavailable"


def _handler_branch_exists(base_path: "Path | str", branch_def_id: str) -> bool:
    """True only when the handler DEFINITELY exists. Fail-closed bool wrapper for
    the ENQUEUE boundary: a handler we cannot confirm (missing OR transiently
    unavailable) is not enqueued against — the filing persists and can re-file,
    so nothing is permanently discarded at enqueue. The CONSUMPTION path uses the
    tri-state directly so a transient error stays retryable (Codex r19 #2)."""
    return _handler_branch_status(base_path, branch_def_id) == "exists"


def resolve_investigation_handler_with_provenance(
    base_path: "Path | str",
) -> "tuple[str, str, str, str]":
    """Resolve the investigation handler with PROVENANCE (Codex r22 #3).

    Returns ``(branch_def_id, reason, resolution_source, goal_id)``:
    - ``branch_def_id`` is a REAL branch id (or "" — NEVER synthetic ``goal:``
      text; the goal is in ``goal_id``).
    - ``reason`` is ``"ok"`` / ``"handler_not_found:<id>"`` /
      ``"handler_unavailable:..."`` / ``"not_configured"`` (as before).
    - ``resolution_source`` is ``"goal_canonical"`` / ``"env_fallback"`` / ""
      — how the handler was picked, so the receipt/task can record it.
    - ``goal_id`` is the configured goal (when goal-canonical), else "".

    The FIRST yielded candidate is authoritative (goal-canonical when a goal is
    configured with a canonical, else env fallback). A dead authoritative handler
    FAILS the trigger — it must NOT fall through to a different handler.
    """
    try:
        primary = next(_iter_handler_candidates(base_path), None)
    except _CanonicalResolutionUnavailable as exc:
        # Codex r21 #1a: goal-canonical resolution failed TRANSIENTLY — do NOT
        # fall back to the env handler and do NOT dead_ref. Surface RETRYABLE.
        # goal id lives in goal_id (4th value), NEVER in branch_def_id.
        _logger.warning(
            "resolve_investigation_handler | canonical resolution UNAVAILABLE "
            "for goal %s (%s) — retryable, NOT env fallback / dead ref",
            exc.goal_id, exc.cause,
        )
        return "", "handler_unavailable:goal", "goal_canonical", exc.goal_id
    if primary is None:
        return "", "not_configured", "", ""
    bdid, source, goal_id = primary
    # Tri-state (Codex r20 #2): exists -> ok; unavailable -> retryable; missing -> dead.
    status = _handler_branch_status(base_path, bdid)
    if status == "exists":
        return bdid, "ok", source, goal_id
    if status == "unavailable":
        _logger.warning(
            "resolve_investigation_handler | registry UNAVAILABLE for %s "
            "(transient) — RETRYABLE, not a dead ref; refusing to enqueue now",
            bdid,
        )
        return "", "handler_unavailable:" + bdid, source, goal_id
    _logger.error(
        "resolve_investigation_handler | authoritative handler %s does NOT "
        "exist in the branch registry (dead ref) — refusing to enqueue",
        bdid,
    )
    return "", "handler_not_found:" + bdid, source, goal_id


def resolve_investigation_handler_detail(
    base_path: "Path | str",
) -> "tuple[str, str]":
    """Thin 2-tuple wrapper over
    ``resolve_investigation_handler_with_provenance`` — ``(branch_def_id, reason)``
    for existing callers (Codex r22 #3 kept the old signature stable)."""
    bdid, reason, _source, _goal = resolve_investigation_handler_with_provenance(
        base_path
    )
    return bdid, reason


def _resolve_investigation_handler(base_path: "Path | str") -> str:
    """Pick the ``branch_def_id`` that should handle a fresh bug.

    Two paths, in order:

      1. **Goal-canonical (PR-127 cutover):** read
         ``TINYASSETS_BUG_INVESTIGATION_GOAL_ID``; if set, look up the
         Goal and resolve ``canonical_branch_version_id`` → its
         ``branch_def_id``. When ``auto_canonical_via_leaderboard``
         is enabled on the Goal, the canonical is auto-refreshed
         here too (subject to the threshold + in-flight gate) so a
         file_bug burst doesn't have to wait for an MCP-driven
         ``run_canonical`` to refresh the pick.
      2. **Cheat-loop env fallback:** read
         ``TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID`` directly. Kept
         in place until Cutover plan Steps 5/6 retire it. The env
         lets the host roll out PR-127 before any Goal has a
         canonical set.

    G4 (2026-07-15): every candidate is validated against the branch registry
    before being returned — a resolved-but-dead ref yields "" (see
    ``resolve_investigation_handler_detail`` for the reason surface).

    Returns "" when neither path produces an EXISTING handler. Never raises.
    """
    branch_def_id, _reason = resolve_investigation_handler_detail(base_path)
    return branch_def_id


def retry_pending_investigation_triggers(
    base_path: "Path | str", *, universe_id: str = "",
) -> dict:
    """RE-ATTEMPT pending investigation triggers — the REAL retry consumer for the
    retryable outcome (Codex r21 #1c).

    The r19/r20/r21 retryable path (handler transiently unavailable) leaves a
    trigger RECEIPT pending; without a consumer that receipt sits forever
    (re-filing dedups to ``similar_found``, so "later re-file" is NOT operational).
    This drains them: re-resolve the handler ONCE for this universe's config, then
    for each pending receipt —
      - resolves now (registry recovered) -> enqueue the investigation + mark the
        receipt QUEUED,
      - DEFINITIVELY missing now -> mark the receipt FAILED (terminal),
      - still transiently unavailable / not configured -> leave PENDING for the
        next sweep.
    Wired into the dispatcher poll (``select_next_task``) so every daemon tick
    drains recoverable triggers. Never raises — best-effort; returns a summary.

    EXACTLY-ONCE (Codex r22 #1): each receipt enqueues a task with a STABLE
    ``branch_task_id`` derived from the receipt id, via an idempotent
    append-if-absent — so two concurrent pollers, or a crash after enqueue but
    before mark_queued, can never double-enqueue one receipt.
    CONTENT (Codex r22 #2): the enqueued ``bug_ref`` is the receipt's ORIGINAL
    persisted filing payload, not a bare {"bug_id": ...} that loses title etc.
    PROVENANCE + REBINDING (Codex r22 #3): retry REBINDS to the CURRENTLY-resolved
    handler (the canonical may have legitimately changed since filing) and records
    the ACTUAL handler + goal + resolution source on both the task and the receipt.
    """
    from tinyassets.wiki import trigger_receipts as _tr

    summary: dict[str, list[str]] = {"queued": [], "failed": [], "still_pending": []}
    uid = universe_id or None
    try:
        pending = _tr.pending_attempts(universe_id=uid)
    except Exception:  # noqa: BLE001 — best-effort, never break the dispatcher
        _logger.exception("retry_pending_investigation_triggers | list failed")
        return summary
    if not pending:
        return summary

    # Resolve ONCE (with provenance) — all pending receipts share the current
    # goal/env config; the retry REBINDS every receipt to this current handler.
    resolved, reason, source, goal_id = (
        resolve_investigation_handler_with_provenance(base_path)
    )
    for receipt in pending:
        request_id = receipt.request_id
        if not request_id:
            continue
        if resolved:
            # STABLE, deterministic task id (idempotency key) + ORIGINAL payload.
            stable_id = investigation_task_id(receipt.trigger_attempt_id)
            bug_ref = _reconstruct_bug_ref(receipt, request_id)
            try:
                enqueue_investigation_request(
                    bug_ref=bug_ref,
                    canonical_branch_def_id=resolved,
                    base_path=base_path,
                    universe_id=universe_id,
                    request_id=stable_id,
                )
                # Codex r24 #1: derive receipt provenance from the ACTUAL PERSISTED
                # task, NEVER from this retry's own resolution. If the canonical
                # changed during the crash window (or a concurrent poll resolved
                # differently), a PRIOR task (handler A) already owns the stable
                # id and our enqueue DEDUP'd — so this retry (handler B) is a
                # dedup LOSER and must record A, not overwrite it with B.
                persisted_handler = _persisted_task_handler(base_path, stable_id)
                if persisted_handler is None or persisted_handler == resolved:
                    # We own the task (fresh append, or an identical resolution)
                    # -> record full provenance incl. goal + source (r23 #3:
                    # goal passed RAW so an env rebind CLEARS a stale goal).
                    _tr.mark_queued(
                        receipt,
                        dispatcher_request_id=stable_id,
                        branch_def_id=(persisted_handler or resolved),
                        goal_id=goal_id,
                        resolution_source=source,
                    )
                else:
                    # Dedup LOSER: a prior task with a DIFFERENT handler already
                    # exists. Record the WINNER's handler; do NOT overwrite the
                    # winner's goal/source with ours.
                    _tr.mark_queued(
                        receipt,
                        dispatcher_request_id=stable_id,
                        branch_def_id=persisted_handler,
                    )
                summary["queued"].append(request_id)
                _logger.info(
                    "retry | pending trigger %s RECOVERED -> queued %s "
                    "(handler=%s persisted=%s src=%s)",
                    request_id, stable_id, resolved, persisted_handler, source,
                )
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "retry | enqueue failed for %s (%s) — still pending",
                    request_id, exc,
                )
                summary["still_pending"].append(request_id)
        elif reason.startswith("handler_not_found:"):
            try:
                _tr.mark_failed(
                    receipt, error_class="handler_not_found", error_message=reason,
                )
            except Exception:  # noqa: BLE001
                pass
            summary["failed"].append(request_id)
            _logger.warning(
                "retry | pending trigger %s handler DEFINITIVELY missing -> failed",
                request_id,
            )
        else:
            # handler_unavailable / not_configured -> still retryable next sweep.
            summary["still_pending"].append(request_id)
    return summary


def _persisted_task_handler(base_path: "Path | str", branch_task_id: str) -> str | None:
    """The ``branch_def_id`` of the task CURRENTLY in the queue under
    ``branch_task_id``, or None if absent (Codex r24 #1). The retry derives
    receipt provenance from the ACTUAL persisted task so a dedup loser can never
    overwrite the winner's handler."""
    from tinyassets.branch_tasks import read_queue

    try:
        for t in read_queue(Path(base_path)):
            if t.branch_task_id == branch_task_id:
                return t.branch_def_id
    except Exception:  # noqa: BLE001 — best-effort; fall back to our resolution
        return None
    return None


def _reconstruct_bug_ref(receipt: object, request_id: str) -> dict:
    """Rebuild the ORIGINAL filing bug_ref from the receipt's persisted payload
    (Codex r22 #2) so a retried trigger enqueues the SAME content — title,
    component, severity, observed, expected, repro. Falls back to a bare
    {"bug_id": ...} only for legacy receipts with no persisted payload."""
    payload_json = getattr(receipt, "payload_json", None)
    if payload_json:
        try:
            import json as _json

            payload = _json.loads(payload_json)
            if isinstance(payload, dict):
                payload = dict(payload)
                payload["bug_id"] = payload.get("bug_id") or request_id
                return payload
        except Exception:  # noqa: BLE001 — corrupt payload; degrade to bug_id
            _logger.warning(
                "retry | payload_json parse failed for %s; using bare bug_id",
                request_id,
            )
    return {"bug_id": request_id}


class _CanonicalResolutionUnavailable(Exception):
    """Goal-canonical resolution failed TRANSIENTLY (a crash, or a transient
    ``goal_load_failed`` result) — NOT a definitive "no canonical configured".

    Codex r21 #1a: the env fallback must be reached ONLY after a SUCCESSFUL,
    DEFINITIVE "no canonical" result — never on an exception/error. Silently
    falling back to the env handler on a transient goal-resolution failure runs a
    DIFFERENT branch on what should be a retry (a forced OSError produced
    ``('env-fallback', 'ok')``). This signals the caller to leave a retryable
    trigger instead."""

    def __init__(self, goal_id: str, cause: object) -> None:
        self.goal_id = goal_id
        self.cause = cause
        super().__init__(
            f"canonical resolution unavailable for goal {goal_id}: {cause}"
        )


# error_kinds from ``resolve_canonical_for_run`` that are TRANSIENT (retryable),
# NOT a definitive "no canonical configured". ``goal_load_failed`` = the goal row
# read itself failed (e.g. a locked / broken store). The DEFINITIVE kinds
# (no_goal / no_canonical_handler / no_published_version_for_candidate) legitimately
# mean "no canonical" and MAY fall back to the env handler.
_TRANSIENT_CANONICAL_ERROR_KINDS = frozenset({"goal_load_failed"})


def _iter_handler_candidates(base_path: "Path | str"):
    """Yield handler branch ids in resolution order (goal canonical, then env).

    Pure resolution — existence validation happens in
    ``resolve_investigation_handler_detail`` (G4). Goals + branch versions live
    at the CANONICAL data root, NOT the per-universe queue path callers pass in
    (that path is only for enqueueing into the target universe), so canonical
    resolution reads ``_base_path()`` — otherwise a valid root goal canonical is
    missed on the real file_bug path (Codex S1 review).

    Raises ``_CanonicalResolutionUnavailable`` when goal-canonical resolution
    fails TRANSIENTLY, so the caller does NOT silently fall back to the env
    handler on a retryable error (Codex r21 #1a). The env fallback is reached
    only after a DEFINITIVE "no canonical configured" result (or no goal set).
    """
    from tinyassets.api.helpers import _base_path

    del base_path  # documented: not the registry root; resolution uses _base_path()
    registry_root = _base_path()
    goal_id = os.environ.get(
        "TINYASSETS_BUG_INVESTIGATION_GOAL_ID", "",
    ).strip()
    if goal_id:
        try:
            from tinyassets.api.canonical_dispatch import (
                resolve_canonical_for_run,
            )
            resolution = resolve_canonical_for_run(
                registry_root,
                goal_id=goal_id,
                # No actor context inside the wiki-write hook — use
                # the empty-viewer (strictly-public) lookup so private
                # branches cannot serve as a public bug-investigation
                # canonical.
                viewer="",
            )
        except Exception as exc:  # noqa: BLE001
            # resolve_canonical_for_run is documented never-raise, but defend:
            # a CRASH is TRANSIENT — signal unavailable, do NOT fall to env.
            _logger.exception(
                "_iter_handler_candidates | canonical resolution CRASHED for "
                "goal %s — UNAVAILABLE (retryable), NOT falling back to env",
                goal_id,
            )
            raise _CanonicalResolutionUnavailable(goal_id, exc) from exc
        if resolution.get("ok"):
            bdid = (resolution.get("branch_def_id") or "").strip()
            if bdid:
                _logger.info(
                    "_iter_handler_candidates | goal=%s "
                    "canonical=%s source=%s",
                    goal_id,
                    resolution.get("branch_version_id"),
                    resolution.get("source"),
                )
                # Codex r22 #3: yield (branch_id, resolution_source, goal_id) so
                # provenance is exact (goal_canonical vs env_fallback).
                yield bdid, "goal_canonical", goal_id
                return  # goal is authoritative; do NOT also offer the env handler
        else:
            error_kind = resolution.get("error_kind") or "unknown"
            if error_kind in _TRANSIENT_CANONICAL_ERROR_KINDS or error_kind == "unknown":
                # TRANSIENT / unexpected canonical-resolution failure — do NOT
                # fall back to a DIFFERENT handler on a retryable error.
                _logger.warning(
                    "_iter_handler_candidates | goal=%s canonical resolution "
                    "TRANSIENTLY unavailable (%s) — retryable, NOT env fallback",
                    goal_id, error_kind,
                )
                raise _CanonicalResolutionUnavailable(goal_id, error_kind)
            # DEFINITIVE "no canonical configured" (no_goal / no_canonical_handler
            # / no_published_version_for_candidate) — env fallback is intended
            # graceful degradation.
            _logger.info(
                "_iter_handler_candidates | goal=%s no canonical "
                "configured (%s); falling back to env",
                goal_id, error_kind,
            )

    # Cheat-loop fallback.
    fallback = os.environ.get(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "",
    ).strip()
    if fallback:
        _logger.info(
            "_iter_handler_candidates | using env fallback "
            "branch_def_id=%s (cutover plan Step 5/6 retires this path)",
            fallback,
        )
        yield fallback, "env_fallback", ""
