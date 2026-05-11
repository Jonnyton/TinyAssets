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
BUG_INVESTIGATION_GOAL_ID = os.environ.get("WORKFLOW_BUG_INVESTIGATION_GOAL_ID", "")

_PAYLOAD_KEYS = (
    "bug_id",
    "title",
    "component",
    "severity",
    "kind",
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
    from workflow.storage import wiki_path

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

# Env var: set to the branch_def_id of the canonical bug-investigation branch.
# When set, enqueue_investigation_request routes through the general dispatcher.
BUG_INVESTIGATION_BRANCH_DEF_ID = os.environ.get(
    "WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", ""
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
            process's WORKFLOW_REQUEST_TYPE_PRIORITIES config (so callers can
            fall back to direct run_branch in degraded mode).
    """
    from datetime import datetime, timezone

    from workflow.branch_tasks import BranchTask, append_task
    from workflow.dispatcher import prefers_request_type

    if not canonical_branch_def_id:
        raise ValueError("canonical_branch_def_id is required")

    if not prefers_request_type(REQUEST_TYPE_BUG_INVESTIGATION):
        raise RuntimeError(
            f"request_type={REQUEST_TYPE_BUG_INVESTIGATION!r} not in "
            "WORKFLOW_REQUEST_TYPE_PRIORITIES; cannot enqueue via dispatcher"
        )

    import uuid
    base = Path(base_path)
    uid = universe_id or base.name
    request_id = str(uuid.uuid4())

    task = BranchTask(
        branch_task_id=request_id,
        branch_def_id=canonical_branch_def_id,
        universe_id=uid,
        inputs=build_run_payload(bug_ref),
        trigger_source="owner_queued",
        priority_weight=float(priority),
        queued_at=datetime.now(timezone.utc).isoformat(),
        request_type=REQUEST_TYPE_BUG_INVESTIGATION,
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
) -> str | None:
    """Forward-trigger seam for `_wiki_file_bug` post-write.

    Reads `WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID` at call time; when set,
    enqueues a dispatcher request for the freshly-filed bug. Swallows
    dispatcher-rejection (RuntimeError) and bad-input (ValueError) so a
    filing never breaks because of investigation-pipeline misconfiguration.

    Returns request_id when enqueued, None when skipped or recovered from error.
    """
    canonical = os.environ.get("WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", "").strip()
    if not canonical:
        return None
    if not bug_id:
        _logger.info("_maybe_enqueue_investigation | skipped | missing bug_id")
        return None
    bug_ref = dict(frontmatter or {})
    bug_ref["bug_id"] = bug_id
    # Module-attribute lookup (NOT bare-name) so `patch("workflow.bug_investigation
    # .enqueue_investigation_request", ...)` reliably takes effect across full-suite
    # ordering. Bare-name lookup races with sibling tests that hold local-name
    # bindings to the original function.
    enqueue = getattr(sys.modules[__name__], "enqueue_investigation_request")
    try:
        return enqueue(
            bug_ref=bug_ref,
            canonical_branch_def_id=canonical,
            base_path=base_path,
            universe_id=universe_id,
        )
    except (RuntimeError, ValueError) as exc:
        _logger.info(
            "_maybe_enqueue_investigation | %s | recovered: %s", bug_id, exc
        )
        return None
