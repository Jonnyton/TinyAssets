"""PR projection + workflow-coordination store — patch-loop S4 (GitHub-native).

**Redirected 2026-07-16 (host decision).** GitHub is the source of truth for PR
review and merge state. This module is NO LONGER a local approval/merge state
machine. The previous design (local ``approved → merging → merged`` authority,
head-bound single-use approval tokens, ``policy_generation`` signatures,
merge-claim leases + CAS, and a classic-branch-protection required-checks
reconstruction) is deleted — GitHub owns that transaction atomically, so those
races no longer exist.

What TinyAssets keeps (this module):

- **PR projection** (``pr_projection``) — the job ↔ PR ↔ universe/run linkage
  plus a *reconciliation cache* of GitHub's own PR state (state / review
  decision / mergeability / merge commit), reread from GitHub, never authored
  here.
- **Owner workflow intent + terminal outcome** — the owner's recorded chat
  decision (approve / reshape / reject) and the exact GitHub call that decision
  will run (Phase 1 records; Phase 2 executes), plus a TinyAssets-side workflow
  outcome + notes. This is coordination state, NOT merge authority.
- **Merge preference binding** (``merge_preference_bindings``) — the off-GitHub
  product preference (manual / auto / not_before) per remix design.
- **Reshape outbox** (``reshape_outbox``) — the durable ``draft_patch`` resume
  identity the loop's Phase-2 revision consumer will read.
- **``not_before`` timers** (``not_before_timers``) — the single durable timer
  the ``not_before`` preference needs (GitHub has no PR-level "merge after T").

Per-universe (``${universe_dir}/.review_queue.db``), mirroring the
``effector_consents`` store plumbing (WAL + ``BEGIN IMMEDIATE``). See
``docs/design-notes/2026-07-16-s4-github-native-redirect.md``.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_DB_FILENAME = ".review_queue.db"

_INIT_LOCK = threading.Lock()
_INITIALIZED: set[str] = set()

#: Verify verdicts carried on the projection (advisory: GitHub's required checks
#: are the authoritative gate). ``pass`` is the only green value.
VERIFY_PASS = "pass"
VERIFY_FAIL = "fail"
VERIFY_UNKNOWN = "unknown"

#: TinyAssets-side workflow outcome for a projected PR. This is coordination
#: state, NOT merge authority — ``merged`` is set only when GitHub reports the PR
#: merged (via :func:`reconcile_projection`). GitHub has no irreversible
#: "rejected forever" state (a PR can be reopened), so ``reshaped`` / ``rejected``
#: record the owner's workflow decision, not an immutable GitHub fact.
WORKFLOW_OPEN = "open"
WORKFLOW_APPROVED = "approved"
WORKFLOW_RESHAPED = "reshaped"
WORKFLOW_REJECTED = "rejected"
WORKFLOW_MERGED = "merged"

VALID_WORKFLOW_OUTCOMES: frozenset[str] = frozenset(
    {WORKFLOW_OPEN, WORKFLOW_APPROVED, WORKFLOW_RESHAPED, WORKFLOW_REJECTED, WORKFLOW_MERGED}
)

#: Owner chat intents recorded on the projection.
INTENT_APPROVE = "approve"
INTENT_RESHAPE = "reshape"
INTENT_REJECT = "reject"

_LIST_DEFAULT_LIMIT = 50
_LIST_MAX_LIMIT = 200


class ReviewHeadChanged(Exception):
    """Raised when a decision names a head the PR has moved past — the owner
    reviewed one commit and the PR head is now another. GitHub also enforces this
    (review ``commit_id`` + latest-push-approval rules); recording it here keeps
    the projection honest before the Phase-2 call runs."""


def review_queue_db_path(universe_dir: str | Path) -> Path:
    """Resolve the per-universe review-queue DB path."""
    return Path(universe_dir) / _DB_FILENAME


@contextmanager
def _connect(universe_dir: str | Path) -> Iterator[sqlite3.Connection]:
    """Open the DB with WAL + a 30s busy timeout (hard rule 1). The handle is
    ALWAYS closed in ``finally`` so Windows can later delete the db file."""
    path = review_queue_db_path(universe_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        yield conn
    finally:
        conn.close()


@contextmanager
def _write(conn: sqlite3.Connection) -> Iterator[None]:
    """Serialize writers with an upfront ``BEGIN IMMEDIATE`` write lock."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS pr_projection (
    destination    TEXT NOT NULL,
    pr_number      INTEGER NOT NULL,
    pr_url         TEXT NOT NULL DEFAULT '',
    head_sha       TEXT NOT NULL DEFAULT '',
    request_ref    TEXT NOT NULL DEFAULT '',
    verify_verdict TEXT NOT NULL DEFAULT 'unknown',
    universe_id    TEXT NOT NULL DEFAULT '',
    branch_def_id  TEXT NOT NULL DEFAULT '',
    run_id         TEXT NOT NULL DEFAULT '',
    -- Reconciliation cache of GitHub's own state (reread from GitHub):
    github_state           TEXT NOT NULL DEFAULT 'unknown',
    github_review_decision TEXT NOT NULL DEFAULT 'unknown',
    github_mergeable       TEXT NOT NULL DEFAULT 'unknown',
    merge_commit_sha       TEXT NOT NULL DEFAULT '',
    synced_at              REAL NOT NULL DEFAULT 0,
    -- Owner workflow intent + the exact GitHub call it will run + outcome:
    owner_intent     TEXT NOT NULL DEFAULT '',
    recorded_call    TEXT NOT NULL DEFAULT '',
    workflow_outcome TEXT NOT NULL DEFAULT 'open',
    notes            TEXT NOT NULL DEFAULT '',
    decided_by       TEXT NOT NULL DEFAULT '',
    decided_at       REAL,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL,
    PRIMARY KEY (destination, pr_number)
);

CREATE INDEX IF NOT EXISTS idx_pr_projection_outcome
    ON pr_projection(workflow_outcome);

CREATE TABLE IF NOT EXISTS merge_preference_bindings (
    branch_def_id      TEXT PRIMARY KEY,
    merge_preference   TEXT NOT NULL DEFAULT 'manual',
    not_before_delay_s REAL NOT NULL DEFAULT 0,
    review_required    INTEGER NOT NULL DEFAULT 1,
    bound_by           TEXT NOT NULL DEFAULT '',
    bound_at           REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reshape_outbox (
    outbox_id     TEXT PRIMARY KEY,
    destination   TEXT NOT NULL DEFAULT '',
    pr_number     INTEGER NOT NULL DEFAULT 0,
    target_node   TEXT NOT NULL DEFAULT 'draft_patch',
    universe_id   TEXT NOT NULL DEFAULT '',
    branch_def_id TEXT NOT NULL DEFAULT '',
    run_id        TEXT NOT NULL DEFAULT '',
    owner_notes   TEXT NOT NULL DEFAULT '',
    recorded_call TEXT NOT NULL DEFAULT '',
    created_at    REAL NOT NULL,
    consumed_at   REAL
);

CREATE INDEX IF NOT EXISTS idx_reshape_outbox_pending
    ON reshape_outbox(created_at) WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS not_before_timers (
    destination TEXT NOT NULL,
    pr_number   INTEGER NOT NULL,
    not_before  REAL NOT NULL,
    enqueued_at REAL NOT NULL,
    fired_at    REAL,
    PRIMARY KEY (destination, pr_number)
);

CREATE INDEX IF NOT EXISTS idx_not_before_pending
    ON not_before_timers(not_before) WHERE fired_at IS NULL;
"""


def initialize_review_queue_db(universe_dir: str | Path) -> Path:
    """Ensure the projection DB exists. Idempotent + cached per db path."""
    path = review_queue_db_path(universe_dir)
    key = str(path)
    if key in _INITIALIZED and path.exists():
        return path
    with _INIT_LOCK:
        with _connect(universe_dir) as conn:
            conn.executescript(_SCHEMA)
        _INITIALIZED.add(key)
    return path


def _now(now: float | None) -> float:
    return now if now is not None else time.time()


def _projection_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    recorded = d.get("recorded_call") or ""
    try:
        d["recorded_call"] = json.loads(recorded) if recorded else None
    except (ValueError, TypeError):
        d["recorded_call"] = None
    return d


# ── PR projection ───────────────────────────────────────────────────────────


def project_pr(
    universe_dir: str | Path,
    *,
    destination: str,
    pr_number: int,
    pr_url: str = "",
    head_sha: str = "",
    request_ref: str = "",
    verify_verdict: str = VERIFY_UNKNOWN,
    universe_id: str = "",
    branch_def_id: str = "",
    run_id: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    """Upsert the projection for one GitHub PR (keyed by repo + PR number).

    Re-projecting an existing PR (e.g. the loop re-pushed the head) refreshes the
    head + verify verdict and RESETS the owner's recorded intent/outcome back to
    ``open`` — the prior decision was about a head that no longer exists, exactly
    the stale-approval case GitHub's own latest-push rules also cover.
    """
    initialize_review_queue_db(universe_dir)
    ts = _now(now)
    dest = (destination or "").strip()
    if not dest:
        raise ValueError("project_pr requires non-empty destination")
    if not isinstance(pr_number, int):
        raise ValueError("project_pr requires an integer pr_number")
    with _connect(universe_dir) as conn:
        with _write(conn):
            existing = conn.execute(
                "SELECT head_sha FROM pr_projection WHERE destination = ? AND pr_number = ?",
                (dest, pr_number),
            ).fetchone()
            head_changed = existing is not None and (existing["head_sha"] or "") != (head_sha or "")
            conn.execute(
                """
                INSERT INTO pr_projection (
                    destination, pr_number, pr_url, head_sha, request_ref,
                    verify_verdict, universe_id, branch_def_id, run_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(destination, pr_number) DO UPDATE SET
                    pr_url = excluded.pr_url,
                    head_sha = excluded.head_sha,
                    request_ref = excluded.request_ref,
                    verify_verdict = excluded.verify_verdict,
                    universe_id = excluded.universe_id,
                    branch_def_id = excluded.branch_def_id,
                    run_id = excluded.run_id,
                    updated_at = excluded.updated_at
                """,
                (
                    dest, pr_number, pr_url, head_sha, request_ref, verify_verdict,
                    universe_id, branch_def_id, run_id, ts, ts,
                ),
            )
            if head_changed:
                # The reviewed head is gone → reset the recorded owner decision.
                conn.execute(
                    """
                    UPDATE pr_projection SET
                        owner_intent = '', recorded_call = '',
                        workflow_outcome = ?, decided_by = '', decided_at = NULL
                    WHERE destination = ? AND pr_number = ?
                    """,
                    (WORKFLOW_OPEN, dest, pr_number),
                )
            row = conn.execute(
                "SELECT * FROM pr_projection WHERE destination = ? AND pr_number = ?",
                (dest, pr_number),
            ).fetchone()
    return _projection_to_dict(row)


def get_projection(
    universe_dir: str | Path, *, destination: str, pr_number: int
) -> dict[str, Any] | None:
    initialize_review_queue_db(universe_dir)
    with _connect(universe_dir) as conn:
        row = conn.execute(
            "SELECT * FROM pr_projection WHERE destination = ? AND pr_number = ?",
            ((destination or "").strip(), pr_number),
        ).fetchone()
    return _projection_to_dict(row) if row is not None else None


def list_projections(
    universe_dir: str | Path,
    *,
    destination: str | None = None,
    workflow_outcome: str | None = None,
    limit: int = _LIST_DEFAULT_LIMIT,
    offset: int = 0,
) -> list[dict[str, Any]]:
    initialize_review_queue_db(universe_dir)
    limit = max(1, min(int(limit or _LIST_DEFAULT_LIMIT), _LIST_MAX_LIMIT))
    offset = max(0, int(offset or 0))
    clauses: list[str] = []
    params: list[Any] = []
    if destination:
        clauses.append("destination = ?")
        params.append(destination.strip())
    if workflow_outcome:
        clauses.append("workflow_outcome = ?")
        params.append(workflow_outcome.strip().lower())
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.extend([limit, offset])
    with _connect(universe_dir) as conn:
        rows = conn.execute(
            f"SELECT * FROM pr_projection{where} "
            "ORDER BY created_at DESC, pr_number DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    return [_projection_to_dict(r) for r in rows]


def record_owner_intent(
    universe_dir: str | Path,
    *,
    destination: str,
    pr_number: int,
    intent: str,
    workflow_outcome: str,
    decided_by: str,
    expected_head_sha: str,
    recorded_call: dict[str, Any] | None = None,
    notes: str = "",
    now: float | None = None,
) -> dict[str, Any] | None:
    """Record the owner's chat decision on a projected PR: the ``intent``
    (approve/reshape/reject), the resulting TinyAssets ``workflow_outcome``, and
    the exact GitHub call (``recorded_call``) that decision will run in Phase 2.

    Head-bound: ``expected_head_sha`` must match the projection's current head or
    :class:`ReviewHeadChanged` is raised (the owner decided on a head the PR has
    moved past). Returns the updated projection, or ``None`` if no projection
    exists for the PR.
    """
    if workflow_outcome not in VALID_WORKFLOW_OUTCOMES:
        raise ValueError(f"invalid workflow_outcome {workflow_outcome!r}")
    initialize_review_queue_db(universe_dir)
    ts = _now(now)
    dest = (destination or "").strip()
    want_head = (expected_head_sha or "").strip()
    with _connect(universe_dir) as conn:
        with _write(conn):
            row = conn.execute(
                "SELECT * FROM pr_projection WHERE destination = ? AND pr_number = ?",
                (dest, pr_number),
            ).fetchone()
            if row is None:
                return None
            current_head = (row["head_sha"] or "").strip()
            if want_head != current_head:
                raise ReviewHeadChanged(
                    f"decision head {want_head[:8] or '(none)'} != current PR head "
                    f"{current_head[:8] or '(none)'} on {dest}#{pr_number}"
                )
            conn.execute(
                """
                UPDATE pr_projection SET
                    owner_intent = ?, workflow_outcome = ?, recorded_call = ?,
                    notes = ?, decided_by = ?, decided_at = ?, updated_at = ?
                WHERE destination = ? AND pr_number = ?
                """,
                (
                    intent, workflow_outcome,
                    json.dumps(recorded_call) if recorded_call else "",
                    notes, decided_by, ts, ts, dest, pr_number,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM pr_projection WHERE destination = ? AND pr_number = ?",
                (dest, pr_number),
            ).fetchone()
    return _projection_to_dict(updated)


def reconcile_projection(
    universe_dir: str | Path,
    *,
    destination: str,
    pr_number: int,
    github_state: str = "unknown",
    review_decision: str = "unknown",
    mergeable_state: str = "unknown",
    merge_commit_sha: str = "",
    head_sha: str | None = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Write GitHub's own PR state into the projection cache after a reread.

    A ``merged`` GitHub state promotes the workflow outcome to ``merged`` — the
    ONLY path to the ``merged`` outcome, since GitHub owns the merge. Returns the
    updated projection, or ``None`` if the PR is not projected.
    """
    initialize_review_queue_db(universe_dir)
    ts = _now(now)
    dest = (destination or "").strip()
    with _connect(universe_dir) as conn:
        with _write(conn):
            row = conn.execute(
                "SELECT workflow_outcome FROM pr_projection "
                "WHERE destination = ? AND pr_number = ?",
                (dest, pr_number),
            ).fetchone()
            if row is None:
                return None
            outcome = row["workflow_outcome"]
            if str(github_state).strip().lower() == "merged":
                outcome = WORKFLOW_MERGED
            sets = [
                "github_state = ?", "github_review_decision = ?",
                "github_mergeable = ?", "merge_commit_sha = ?",
                "workflow_outcome = ?", "synced_at = ?", "updated_at = ?",
            ]
            vals: list[Any] = [
                str(github_state).strip().lower(),
                str(review_decision).strip().lower(),
                str(mergeable_state).strip().lower(),
                merge_commit_sha, outcome, ts, ts,
            ]
            if head_sha is not None:
                sets.append("head_sha = ?")
                vals.append((head_sha or "").strip())
            vals.extend([dest, pr_number])
            conn.execute(
                f"UPDATE pr_projection SET {', '.join(sets)} "
                "WHERE destination = ? AND pr_number = ?",
                vals,
            )
            updated = conn.execute(
                "SELECT * FROM pr_projection WHERE destination = ? AND pr_number = ?",
                (dest, pr_number),
            ).fetchone()
    return _projection_to_dict(updated)


# ── Reshape outbox (durable draft_patch resume — Phase-2 consumer seam) ──────


def enqueue_reshape(
    universe_dir: str | Path,
    *,
    destination: str,
    pr_number: int,
    universe_id: str = "",
    branch_def_id: str = "",
    run_id: str = "",
    owner_notes: str = "",
    recorded_call: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Persist a durable reshape resume row. The Phase-2 revision consumer (NOT
    built here) reads this to re-run ``draft_patch`` with the owner's notes.
    Returns the outbox row including a ``route_back`` resume identity."""
    initialize_review_queue_db(universe_dir)
    ts = _now(now)
    outbox_id = f"rsh-{uuid.uuid4().hex[:16]}"
    with _connect(universe_dir) as conn:
        with _write(conn):
            conn.execute(
                """
                INSERT INTO reshape_outbox (
                    outbox_id, destination, pr_number, target_node,
                    universe_id, branch_def_id, run_id, owner_notes,
                    recorded_call, created_at
                ) VALUES (?, ?, ?, 'draft_patch', ?, ?, ?, ?, ?, ?)
                """,
                (
                    outbox_id, (destination or "").strip(), pr_number,
                    universe_id, branch_def_id, run_id, owner_notes,
                    json.dumps(recorded_call) if recorded_call else "", ts,
                ),
            )
    return {
        "outbox_id": outbox_id,
        "destination": (destination or "").strip(),
        "pr_number": pr_number,
        "route_back": {
            "target_node": "draft_patch",
            "universe_id": universe_id,
            "branch_def_id": branch_def_id,
            "run_id": run_id,
            "owner_notes": owner_notes,
        },
        "recorded_call": recorded_call,
        "created_at": ts,
        "consumed_at": None,
    }


def list_pending_reshapes(universe_dir: str | Path) -> list[dict[str, Any]]:
    initialize_review_queue_db(universe_dir)
    with _connect(universe_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM reshape_outbox WHERE consumed_at IS NULL ORDER BY created_at",
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        d["route_back"] = {
            "target_node": d.get("target_node") or "draft_patch",
            "universe_id": d.get("universe_id") or "",
            "branch_def_id": d.get("branch_def_id") or "",
            "run_id": d.get("run_id") or "",
            "owner_notes": d.get("owner_notes") or "",
        }
        out.append(d)
    return out


# ── Merge preference binding (off-GitHub product config) ─────────────────────


def _preference_default(branch_def_id: str) -> dict[str, Any]:
    return {
        "branch_def_id": branch_def_id,
        "merge_preference": "manual",
        "not_before_delay_s": 0.0,
        "review_required": True,
        "bound": False,
        "bound_by": "",
        "bound_at": 0.0,
    }


def set_merge_preference_binding(
    universe_dir: str | Path,
    *,
    branch_def_id: str,
    merge_preference: str = "manual",
    not_before_delay_s: float = 0.0,
    review_required: bool = True,
    bound_by: str,
    now: float | None = None,
) -> dict[str, Any]:
    """Owner-bind the off-GitHub merge preference for a remix design. Validates a
    finite, non-negative ``not_before`` delay; raises on empty
    ``branch_def_id`` / ``bound_by``."""
    bdid = (branch_def_id or "").strip()
    if not bdid:
        raise ValueError("set_merge_preference_binding requires non-empty branch_def_id")
    bound_by = (bound_by or "").strip()
    if not bound_by:
        raise ValueError("set_merge_preference_binding requires non-empty bound_by")
    pref = (merge_preference or "manual").strip().lower() or "manual"
    try:
        delay = float(not_before_delay_s if not_before_delay_s is not None else 0.0)
    except (TypeError, ValueError):
        raise ValueError("not_before_delay_s must be a finite non-negative number") from None
    if delay != delay or delay in (float("inf"), float("-inf")) or delay < 0:
        raise ValueError("not_before_delay_s must be finite and non-negative")
    initialize_review_queue_db(universe_dir)
    ts = _now(now)
    with _connect(universe_dir) as conn:
        with _write(conn):
            conn.execute(
                """
                INSERT INTO merge_preference_bindings (
                    branch_def_id, merge_preference, not_before_delay_s,
                    review_required, bound_by, bound_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(branch_def_id) DO UPDATE SET
                    merge_preference = excluded.merge_preference,
                    not_before_delay_s = excluded.not_before_delay_s,
                    review_required = excluded.review_required,
                    bound_by = excluded.bound_by,
                    bound_at = excluded.bound_at
                """,
                (bdid, pref, delay, 1 if review_required else 0, bound_by, ts),
            )
    return {
        "branch_def_id": bdid,
        "merge_preference": pref,
        "not_before_delay_s": delay,
        "review_required": bool(review_required),
        "bound": True,
        "bound_by": bound_by,
        "bound_at": ts,
    }


def resolve_merge_preference_binding(
    universe_dir: str | Path, *, branch_def_id: str
) -> dict[str, Any]:
    """Resolve the owner-bound merge preference for a remix design, or the
    default (``manual``, ``bound=False``) when none is bound."""
    bdid = (branch_def_id or "").strip()
    initialize_review_queue_db(universe_dir)
    with _connect(universe_dir) as conn:
        row = conn.execute(
            "SELECT * FROM merge_preference_bindings WHERE branch_def_id = ?",
            (bdid,),
        ).fetchone()
    if row is None:
        return _preference_default(bdid)
    return {
        "branch_def_id": row["branch_def_id"],
        "merge_preference": row["merge_preference"],
        "not_before_delay_s": row["not_before_delay_s"],
        "review_required": bool(row["review_required"]),
        "bound": True,
        "bound_by": row["bound_by"],
        "bound_at": row["bound_at"],
    }


# ── not_before timers (the single durable timer the preference needs) ────────


def schedule_not_before(
    universe_dir: str | Path,
    *,
    destination: str,
    pr_number: int,
    not_before: float,
    now: float | None = None,
) -> dict[str, Any]:
    """Schedule (or reschedule) the single ``not_before`` timer for a PR. A
    re-push reschedules by upserting a fresh fire time and clearing ``fired_at``."""
    initialize_review_queue_db(universe_dir)
    ts = _now(now)
    dest = (destination or "").strip()
    fire = float(not_before)
    if fire != fire or fire in (float("inf"), float("-inf")):
        raise ValueError("not_before must be a finite timestamp")
    with _connect(universe_dir) as conn:
        with _write(conn):
            conn.execute(
                """
                INSERT INTO not_before_timers (
                    destination, pr_number, not_before, enqueued_at, fired_at
                ) VALUES (?, ?, ?, ?, NULL)
                ON CONFLICT(destination, pr_number) DO UPDATE SET
                    not_before = excluded.not_before,
                    enqueued_at = excluded.enqueued_at,
                    fired_at = NULL
                """,
                (dest, pr_number, fire, ts),
            )
    return {
        "destination": dest, "pr_number": pr_number,
        "not_before": fire, "enqueued_at": ts, "fired_at": None,
    }


def due_not_before_timers(
    universe_dir: str | Path, *, now: float | None = None
) -> list[dict[str, Any]]:
    """Return unfired timers whose ``not_before`` has elapsed. The scheduler
    fires each (enable GitHub auto-merge) then calls :func:`mark_timer_fired`."""
    initialize_review_queue_db(universe_dir)
    ts = _now(now)
    with _connect(universe_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM not_before_timers WHERE fired_at IS NULL AND not_before <= ? "
            "ORDER BY not_before",
            (ts,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_timer_fired(
    universe_dir: str | Path, *, destination: str, pr_number: int, now: float | None = None
) -> dict[str, Any] | None:
    initialize_review_queue_db(universe_dir)
    ts = _now(now)
    dest = (destination or "").strip()
    with _connect(universe_dir) as conn:
        with _write(conn):
            cur = conn.execute(
                "UPDATE not_before_timers SET fired_at = ? "
                "WHERE destination = ? AND pr_number = ? AND fired_at IS NULL",
                (ts, dest, pr_number),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM not_before_timers WHERE destination = ? AND pr_number = ?",
                (dest, pr_number),
            ).fetchone()
    return dict(row) if row is not None else None


def cancel_not_before(
    universe_dir: str | Path, *, destination: str, pr_number: int
) -> bool:
    """Cancel a pending timer (owner tightened to manual, or held). Returns True
    if a pending timer was removed."""
    initialize_review_queue_db(universe_dir)
    dest = (destination or "").strip()
    with _connect(universe_dir) as conn:
        with _write(conn):
            cur = conn.execute(
                "DELETE FROM not_before_timers WHERE destination = ? AND pr_number = ? "
                "AND fired_at IS NULL",
                (dest, pr_number),
            )
            removed = cur.rowcount
    return removed > 0


__all__ = [
    "VERIFY_PASS",
    "VERIFY_FAIL",
    "VERIFY_UNKNOWN",
    "WORKFLOW_OPEN",
    "WORKFLOW_APPROVED",
    "WORKFLOW_RESHAPED",
    "WORKFLOW_REJECTED",
    "WORKFLOW_MERGED",
    "VALID_WORKFLOW_OUTCOMES",
    "INTENT_APPROVE",
    "INTENT_RESHAPE",
    "INTENT_REJECT",
    "ReviewHeadChanged",
    "review_queue_db_path",
    "initialize_review_queue_db",
    "project_pr",
    "get_projection",
    "list_projections",
    "record_owner_intent",
    "reconcile_projection",
    "enqueue_reshape",
    "list_pending_reshapes",
    "set_merge_preference_binding",
    "resolve_merge_preference_binding",
    "schedule_not_before",
    "due_not_before_timers",
    "mark_timer_fired",
    "cancel_not_before",
]
