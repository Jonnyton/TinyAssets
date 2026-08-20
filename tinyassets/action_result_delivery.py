"""Deliver an async action's terminal result as a governed follow-up (Slice 3).

A tick over the :mod:`tinyassets.storage.action_result_outbox`: for each pending
entry whose background run has reached a terminal status, atomically CLAIM it,
compose a TRUTHFUL, content-safe summary, and deliver it once through the governed
outbound adapter.

Hardening (Codex round-1):
- **At most once, even under concurrency / crashes.** Each terminal entry is CLAIMED
  (``pending`` -> ``in_flight``) before the external post; a second concurrent tick
  loses the claim and skips. A crash between post and mark leaves the entry
  ``in_flight`` (reclaimed after a timeout) and the adapter's own idempotency key
  (``action-result:{run_id}:{revision}``) short-circuits the re-post.
- **Never success-on-failure, no leak.** A ``failed`` / ``cancelled`` / ``interrupted``
  run is reported honestly; the only run-derived text is a public result reference or a
  phase name, each passed through a strict allowlist and length cap.
- **Fail-closed.** If authority cannot be re-resolved, the adapter raises, OR the
  adapter returns no receipt (a non-throwing transport failure), the entry is HELD
  (released back to ``pending``, retried) — never delivered without authorization,
  never marked delivered without a receipt, never dropped.
- **No starvation.** All pending pages are walked (cursor by rowid), so a backlog of
  still-running entries cannot hide a newer terminal one.

The ``get_run`` / ``authorize`` / ``adapter`` seams are injected so the core decision
logic is testable without standing up a live run queue or Slack transport.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tinyassets.storage import action_result_outbox as outbox

logger = logging.getLogger(__name__)

#: Terminal run statuses we deliver a follow-up for. Anything not ``completed`` is
#: reported as "didn't finish" — so a ``cancelled`` / ``interrupted`` run is delivered
#: honestly rather than left pending forever (Codex round-1).
_TERMINAL = ("completed", "failed", "cancelled", "interrupted")

#: A public result reference is emitted ONLY if it is a TRUSTED STRUCTURED HANDLE —
#: every path segment a bounded safe identifier — not "any URL minus bad words".
#: Denylisting secret markers cannot make arbitrary run-derived text safe: a markerless
#: credential (``AKIAIOSFODNN7EXAMPLE``) or an off-allowlist host (``https://x.io/…``)
#: slips straight through a denylist (Codex re-review). So we ALLOWLIST the exact
#: handle shapes we are willing to emit — a github.com PR/issue URL with validated
#: owner/repo/number segments, or a bare PR/issue number — and drop everything else.
#: A strict anchored match leaves no room for a query string, fragment, userinfo,
#: alternate host, or free-form token to ride along.
_SAFE_REF_RES = (
    re.compile(
        r"^https://github\.com/[A-Za-z0-9][A-Za-z0-9._-]{0,99}"
        r"/[A-Za-z0-9][A-Za-z0-9._-]{0,99}/(?:pull|issues)/[0-9]{1,9}$"
    ),
    re.compile(r"^PR #[0-9]{1,9}$"),
    re.compile(r"^#[0-9]{1,9}$"),
)

#: A failure phase is surfaced ONLY if it is one of these application-owned, known
#: pipeline phase names — an allowlist ENUM, not a shape check. An unbounded
#: run-internal string (a markerless credential, ``node_42 token=xoxb-secret``) is
#: simply not a member and is dropped. Shape alone cannot make an arbitrary phase
#: content-safe; only an application-owned enum can (Codex re-review).
_KNOWN_PHASES = frozenset(
    {
        "plan", "research", "writer", "judge", "review", "extract", "converge",
        "render", "build", "test", "deploy", "publish", "candidate_discovery",
        "compile", "validate", "merge",
    }
)


def _safe_ref(value: str) -> str:
    """The value iff it is a trusted structured handle (see :data:`_SAFE_REF_RES`),
    else "". The strict structural match is the whole guard — there is no separate
    denylist because there is nothing arbitrary left to deny."""
    value = (value or "").strip()
    return value if any(rx.match(value) for rx in _SAFE_REF_RES) else ""


def _safe_phase(value: str) -> str:
    """The phase iff it is a member of the application-owned :data:`_KNOWN_PHASES`
    enum, else "". Membership — not shape — is the guard, so no arbitrary run string
    can be surfaced."""
    return value if (value or "").strip() in _KNOWN_PHASES else ""


def compose_summary(run: dict[str, Any]) -> str:
    """A truthful, content-safe follow-up line for a terminal run.

    Never claims success on a non-``completed`` run. The ONLY run-derived text that may
    appear is (success) a public result reference that is a trusted structured handle,
    or (failure) a phase name drawn from an application-owned enum — each an allowlist,
    so nothing arbitrary is interpolated. A non-matching ref/phase is dropped and the
    line stays truthful without it.
    """
    status = str(run.get("status") or "")
    if status == "completed":
        ref = _safe_ref(str(run.get("public_result_ref") or run.get("result_url") or ""))
        tail = f" {ref}" if ref else ""
        return f"Done — the background job you asked for has finished.{tail}".rstrip()
    # failed / cancelled / interrupted (any non-completed terminal)
    phase = _safe_phase(str(run.get("failed_phase") or run.get("terminal_phase") or ""))
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
    page_limit: int = 200,
    reclaim_after_s: float = 900.0,
) -> dict[str, int]:
    """Deliver every pending outbox entry whose run is terminal. Returns counts.

    - ``get_run(base, run_id)`` -> run dict or None.
    - ``authorize(entry, response)`` -> a reply authorization, or None to HOLD.
    - ``adapter.deliver(authorization, response, idempotency_key=...)`` -> a receipt
      (falsy = transport failure -> HOLD).
    """
    base = Path(base_path)
    counts = {"delivered": 0, "skipped_running": 0, "held": 0}
    # Crash recovery: free entries a dead tick left claimed, so they retry.
    outbox.reclaim_stale(base, older_than_s=reclaim_after_s, now=now)

    after_rowid = 0
    while True:
        page = outbox.list_pending(base, after_rowid=after_rowid, limit=page_limit)
        if not page:
            break
        after_rowid = page[-1]["rowid"]
        for entry in page:
            run_id = entry["run_id"]
            try:
                run = get_run(base, run_id)
            except Exception:  # noqa: BLE001 - one unreadable run must not abort the tick
                logger.exception("action-result: get_run failed for %s (skipping)", run_id)
                counts["skipped_running"] += 1
                continue  # poison-row isolation (Codex hardening #5)
            status = str(run.get("status") or "") if isinstance(run, dict) else ""
            if not isinstance(run, dict) or status not in _TERMINAL:
                counts["skipped_running"] += 1
                continue  # still running / unknown — leave pending

            # CLAIM before posting: exactly one tick delivers each terminal entry. The
            # returned token FENCES release/mark so a stale worker cannot touch a newer
            # claim (Codex hardening #1).
            token = outbox.claim(base, run_id=run_id, now=now)
            if token is None:
                counts["skipped_running"] += 1  # a concurrent tick owns it
                continue

            summary = compose_summary(run)
            revision = run.get("revision")
            rev_int = int(revision) if isinstance(revision, int) else None
            idem = f"action-result:{run_id}:{rev_int if rev_int is not None else 'terminal'}"

            try:
                authorization = authorize(entry, summary)
            except Exception:  # noqa: BLE001 - an authorize failure must HOLD, not post
                logger.exception("action-result: authorize failed for run %s (holding)", run_id)
                outbox.release(base, run_id=run_id, claim_token=token)
                counts["held"] += 1
                continue
            if authorization is None:
                # Cannot authorize this delivery right now — hold fail-closed.
                outbox.release(base, run_id=run_id, claim_token=token)
                counts["held"] += 1
                continue

            try:
                receipt = adapter.deliver(authorization, summary, idempotency_key=idem)
            except Exception:  # noqa: BLE001 - a delivery failure must HOLD, not drop
                logger.exception("action-result: delivery failed for run %s (holding)", run_id)
                outbox.release(base, run_id=run_id, claim_token=token)
                counts["held"] += 1
                continue
            if not receipt:
                # A non-throwing transport failure (falsy receipt) is NOT a delivery —
                # do not mark delivered; hold and retry (Codex round-1).
                logger.warning(
                    "action-result: adapter returned no receipt for run %s (holding)",
                    run_id,
                )
                outbox.release(base, run_id=run_id, claim_token=token)
                counts["held"] += 1
                continue

            outbox.mark_delivered(
                base, run_id=run_id, terminal_revision=rev_int, claim_token=token, now=now,
            )
            counts["delivered"] += 1
    return counts
