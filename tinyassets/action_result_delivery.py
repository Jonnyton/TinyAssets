"""Deliver an async action's terminal result as a governed follow-up (Slice 3).

A tick over the :mod:`tinyassets.storage.action_result_outbox`: for each pending
entry whose background run has reached a terminal status, compose a TRUTHFUL,
content-safe summary and deliver it once through the governed outbound adapter.

Fail-closed + idempotent:
- A still-running run is left pending (not delivered).
- A ``failed`` run is reported honestly, never as success, and leaks no internal
  detail.
- Authority is re-resolved FRESH at delivery time; if it cannot be authorized now,
  the follow-up is HELD (not posted, not dropped).
- Delivery is at most once per terminal revision: the outbox ``delivered`` state is
  the primary guard, and the outbound adapter's own idempotent receipt store is the
  crash-safety backstop (a crash between deliver and mark re-delivers into the same
  key and is short-circuited, never double-posted).

The ``get_run`` / ``authorize`` / ``adapter`` seams are injected so the core
decision logic is testable without standing up a live run queue or Slack transport.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tinyassets.storage import action_result_outbox as outbox

logger = logging.getLogger(__name__)

_TERMINAL = ("completed", "failed")


def compose_summary(run: dict[str, Any]) -> str:
    """A truthful, content-safe follow-up line for a terminal run.

    Never claims success on a failed run; never leaks internal detail — only the
    terminal status and, on success, a run-provided PUBLIC result reference if
    present.
    """
    status = str(run.get("status") or "")
    if status == "completed":
        ref = str(run.get("public_result_ref") or run.get("result_url") or "").strip()
        tail = f" {ref}" if ref else ""
        return f"Done — the background job you asked for has finished.{tail}".rstrip()
    # failed (or any non-completed terminal we were asked to deliver)
    phase = str(run.get("failed_phase") or run.get("terminal_phase") or "").strip()
    where = f" at the {phase} step" if phase else ""
    return (
        f"The background job you asked for didn't finish{where}. "
        "I've kept the request — say the word and I'll try it again."
    )


def deliver_pending_action_results(
    base_path: str | Path,
    *,
    get_run: Callable[[str | Path, str], dict[str, Any] | None],
    authorize: Callable[[dict[str, Any], str], Any | None],
    adapter: Any,
    now: float | None = None,
    limit: int = 200,
) -> dict[str, int]:
    """Deliver every pending outbox entry whose run is terminal. Returns counts.

    - ``get_run(base, run_id)`` -> run dict or None.
    - ``authorize(entry, response)`` -> a reply authorization, or None to HOLD
      (unauthorized right now — do not post, leave pending).
    - ``adapter.deliver(authorization, response)`` -> receipt (idempotent).
    """
    base = Path(base_path)
    counts = {"delivered": 0, "skipped_running": 0, "held": 0}
    for entry in outbox.list_pending(base, limit=limit):
        run_id = entry["run_id"]
        run = get_run(base, run_id)
        status = str(run.get("status") or "") if isinstance(run, dict) else ""
        if not isinstance(run, dict) or status not in _TERMINAL:
            counts["skipped_running"] += 1
            continue  # still running / unknown — leave pending
        summary = compose_summary(run)
        try:
            authorization = authorize(entry, summary)
        except Exception:  # noqa: BLE001 - an authorize failure must HOLD, not post
            logger.exception("action-result: authorize failed for run %s (holding)", run_id)
            counts["held"] += 1
            continue
        if authorization is None:
            # Cannot authorize this delivery right now — hold fail-closed.
            counts["held"] += 1
            continue
        try:
            adapter.deliver(authorization, summary)
        except Exception:  # noqa: BLE001 - a delivery failure must HOLD, not drop
            logger.exception("action-result: delivery failed for run %s (holding)", run_id)
            counts["held"] += 1
            continue
        revision = run.get("revision")
        outbox.mark_delivered(
            base, run_id=run_id,
            terminal_revision=int(revision) if isinstance(revision, int) else None,
            now=now,
        )
        counts["delivered"] += 1
    return counts
