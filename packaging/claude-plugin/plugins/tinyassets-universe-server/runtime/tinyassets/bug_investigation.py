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
    from tinyassets.branch_tasks import BranchTask, append_task
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
    request_id = str(uuid.uuid4())
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
    # (resolve time), but a concurrent delete may have removed it since. REVALIDATE
    # at the durable enqueue boundary — immediately before append_task — so we
    # never persist a task pointing at a dead reference. Fail with a structured
    # HandlerDeletedError (the caller recovers it; filing persists, nothing queued).
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
    append_task(base, task)
    _logger.info(
        "enqueue_investigation_request | %s | %s", bug_ref.get("bug_id", "?"), request_id
    )
    return request_id


def _maybe_enqueue_investigation(
    bug_id: str,
    frontmatter: dict,
    base_path: "Path | str",
    universe_id: str = "",
    resolved_branch_def_id: str | None = None,
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
        )
    except (RuntimeError, ValueError) as exc:
        _logger.info(
            "_maybe_enqueue_investigation | %s | recovered: %s", bug_id, exc
        )
        return None


def _handler_branch_exists(base_path: "Path | str", branch_def_id: str) -> bool:
    """True when the branch definition exists in the registry.

    Fail closed on registry read errors: a handler we cannot confirm exists
    must not be enqueued against (the 2026-07-13 volume deletion left env/goal
    pointers at wiped branch ids, and filings queued forever against them —
    G4 in docs/design-notes/2026-07-15-user-patch-loop-reference-design.md).
    """
    if not branch_def_id:
        return False
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
        return True
    except KeyError:
        return False
    except Exception:  # noqa: BLE001 - fail closed, loudly
        _logger.exception(
            "_handler_branch_exists | registry read failed for %s; treating "
            "handler as missing",
            branch_def_id,
        )
        return False


def resolve_investigation_handler_detail(
    base_path: "Path | str",
) -> "tuple[str, str]":
    """Resolve the investigation handler AND report why when there isn't one.

    Returns ``(branch_def_id, reason)``:

    - ``(<id>, "ok")`` — a handler resolved and its branch def EXISTS.
    - ``("", "handler_not_found:<ids>")`` — one or more ids resolved (goal
      canonical and/or env fallback) but none exist in the registry (dead
      refs). Fail loudly on the TRIGGER, never the filing: callers must not
      enqueue, and should surface an explicit failed-trigger status while the
      filing itself persists.
    - ``("", "not_configured")`` — no goal binding and no env fallback set.
    """
    # The FIRST yielded candidate is the AUTHORITATIVE handler for this filing
    # (goal-canonical when a goal is configured with a canonical, else the env
    # fallback). A dead authoritative handler must FAIL the trigger — it must
    # NOT fall through to a different handler, or a misconfigured goal canonical
    # would silently run the wrong investigation branch (Codex S1 review; G4).
    # The env fallback is only reached when the goal path yields no candidate at
    # all (not when its canonical resolves to a dead ref).
    primary = next(_iter_handler_candidates(base_path), None)
    if primary is None:
        return "", "not_configured"
    if _handler_branch_exists(base_path, primary):
        return primary, "ok"
    _logger.error(
        "resolve_investigation_handler | authoritative handler %s does NOT "
        "exist in the branch registry (dead ref) — refusing to enqueue",
        primary,
    )
    return "", "handler_not_found:" + primary


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


def _iter_handler_candidates(base_path: "Path | str"):
    """Yield handler branch ids in resolution order (goal canonical, then env).

    Pure resolution — existence validation happens in
    ``resolve_investigation_handler_detail`` (G4). Goals + branch versions live
    at the CANONICAL data root, NOT the per-universe queue path callers pass in
    (that path is only for enqueueing into the target universe), so canonical
    resolution reads ``_base_path()`` — otherwise a valid root goal canonical is
    missed on the real file_bug path (Codex S1 review).
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
        except Exception:  # pragma: no cover — defensive
            _logger.exception(
                "_iter_handler_candidates | canonical resolution "
                "crashed for goal %s; falling back to env",
                goal_id,
            )
            resolution = {"ok": False}
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
                yield bdid
        else:
            _logger.info(
                "_iter_handler_candidates | goal=%s no canonical "
                "available (%s); falling back to env",
                goal_id, resolution.get("error_kind") or "unknown",
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
        yield fallback
