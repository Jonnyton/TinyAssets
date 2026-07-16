"""Owner review queue for loop-produced pull requests — patch-loop S4 (G3/G6).

A user's patch loop (``patch_loop_reference`` remix) produces **ready-to-merge
PRs** against the owner's bound GitHub repo. Those PRs do not merge on their
own: the project OWNER reviews them from any surface (phone included) whenever
they get around to it — **approve / reshape (send back with notes) / reject** —
and a per-remix merge policy governs *when* an eligible PR actually merges.

This module is the durable storage for that queue. It is per-universe (the
owner's universe directory), mirroring the ``effector_consents`` store shape so
the two authority surfaces compose rather than fork:

- ``effector_consents`` — a **standing** grant ("this universe may write to
  repo X via sink S"). Persists until revoked.
- ``review_queue`` (this module) — the **per-PR** owner decision surface, plus
  the **fresh-per-merge founder-OAuth approvals** that Jonathan's own remix
  requires. A standing consent deliberately does NOT satisfy a founder-OAuth
  approval — see :func:`consume_merge_approval`.

Schema (per-universe, file ``${universe_dir}/.review_queue.db``):

.. code-block:: sql

    CREATE TABLE review_queue (
        item_id        TEXT PRIMARY KEY,
        destination    TEXT NOT NULL,   -- owner/repo
        pr_number      INTEGER NOT NULL,
        pr_url         TEXT NOT NULL,
        head_sha       TEXT NOT NULL DEFAULT '',
        request_ref    TEXT NOT NULL DEFAULT '',  -- originating user-request id
        verify_verdict TEXT NOT NULL DEFAULT 'unknown',  -- pass|fail|unknown
        -- status: pending|approved|merging|reshaped|rejected|merged
        -- (`merging` is the in-flight merge-claim state)
        status         TEXT NOT NULL,
        notes          TEXT NOT NULL DEFAULT '',
        merge_commit_sha TEXT NOT NULL DEFAULT '',   -- set on merged
        -- Governing merge policy (TRUSTED durable state; effector resolves here)
        merge_policy   TEXT NOT NULL DEFAULT 'manual',
        founder_oauth_per_merge INTEGER NOT NULL DEFAULT 0,
        merge_timer_delay_s REAL NOT NULL DEFAULT 0,
        -- Resume identity (lets the loop act on an owner decision)
        universe_id    TEXT NOT NULL DEFAULT '',
        branch_def_id  TEXT NOT NULL DEFAULT '',
        run_id         TEXT NOT NULL DEFAULT '',
        created_at     REAL NOT NULL,
        head_queued_at REAL NOT NULL DEFAULT 0,   -- per-head timer clock
        merge_claimed_at REAL,                    -- set while status='merging'
        updated_at     REAL NOT NULL,             -- row-version generation token
        decided_by     TEXT NOT NULL DEFAULT '',
        decided_at     REAL
    );

    CREATE TABLE merge_approvals (
        approval_id  TEXT PRIMARY KEY,
        item_id      TEXT NOT NULL,
        destination  TEXT NOT NULL,
        pr_number    INTEGER NOT NULL,
        head_sha     TEXT NOT NULL,     -- binds the approval to an exact commit
        approved_by  TEXT NOT NULL,
        approved_at  REAL NOT NULL,
        consumed_at  REAL               -- NULL until a merge consumes it (single-use)
    );

A ``merge_approvals`` row is the founder's *fresh authenticated approval action*
for one merge: it is single-use (``consumed_at`` set on merge) and bound to the
exact ``head_sha`` (a re-pushed PR head invalidates it, forcing re-approval).
That is the concrete difference from a standing consent grant.
"""

from __future__ import annotations

import math
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_DB_FILENAME = ".review_queue.db"

#: Per-process schema-init cache. Running ``executescript`` on every hot-path
#: call caused DDL write-lock contention under concurrency ("database is
#: locked"); the schema is idempotent, so initialize it once per db path and
#: skip it thereafter (Codex R5 CRITICAL 2 concurrency-stress hardening).
_INIT_LOCK = threading.Lock()
_INITIALIZED: set[str] = set()

#: Statuses a queue item may hold. ``merging`` is the in-flight claim state a
#: merge effector CASes an eligible item into before it touches GitHub, so an
#: owner decision cannot race the merge PUT (Codex R5 CRITICAL 1). ``held`` is
#: the owner's non-terminal "pause this auto/timer merge" state (Codex R6 C5).
VALID_STATUSES: frozenset[str] = frozenset(
    {"pending", "approved", "held", "merging", "reshaped", "rejected", "merged"}
)

#: Statuses from which an owner decision (approve/reshape/reject) is INVALID.
#: A rejected/reshaped/merged item is terminal for the reviewed head — it can
#: only re-enter the decision surface via a fresh ``enqueue_pr`` (new head),
#: which re-pends it. This blocks the "reject then resurrect via approve" bug.
_TERMINAL_STATUSES: frozenset[str] = frozenset({"reshaped", "rejected", "merged"})

#: A ``merging`` claim older than this (seconds) is considered stuck — the
#: effector that held it must have crashed between claim and merge/release. An
#: owner decision may then reclaim it; a fresh claim is treated as in-progress
#: and blocks owner decisions. Keep it short: a merge PUT is a few seconds, so a
#: few minutes is comfortably past any healthy run.
_MERGE_CLAIM_TIMEOUT_S = 300.0

#: A fresh founder-OAuth approval token expires after this many seconds — an
#: approval that sat unused is no longer a "fresh, per-merge" authorization
#: (Codex R6 C1 token-regime: policy-generation + expiry checks on approvals).
_APPROVAL_TTL_S = 86400.0

#: List-queue pagination bounds (Codex R6 C6 — chatbot-readiness).
_LIST_DEFAULT_LIMIT = 50
_LIST_MAX_LIMIT = 200


def _policy_signature(
    merge_policy: Any,
    founder_oauth_per_merge: Any,
    branch_def_id: Any = "",
    merge_timer_delay_s: Any = 0.0,
) -> str:
    """Stable signature of the merge-authority REGIME + BINDING a token is minted
    under.

    A founder-OAuth token is bound to this signature; if the item's policy, OAuth
    flag, the owner-bound BRANCH binding it resolved from, or the timer delay
    later changes, the signature differs and the old token is no longer valid —
    a token can't ride to a different regime OR a different binding (Codex R6 C1
    + R7 C2)."""
    policy = str(merge_policy or "manual").strip().lower() or "manual"
    oauth = 1 if founder_oauth_per_merge else 0
    bdid = str(branch_def_id or "").strip()
    try:
        delay = float(merge_timer_delay_s or 0.0)
    except (TypeError, ValueError):
        delay = 0.0
    return f"{policy}|{oauth}|{bdid}|{delay}"


class InvalidReviewTransition(ValueError):
    """Raised when an owner decision is attempted from a terminal status."""


class OwnerRequired(ValueError):
    """Raised when a founder-OAuth-per-merge approval mint is attempted by an
    actor who is not the universe owner — checked INSIDE the mint transaction
    (Codex R6 C1, closing the actions-layer TOCTOU)."""


class MergeInProgress(ValueError):
    """Raised when an owner decision is attempted on an item with a fresh
    (non-stale) ``merging`` claim — a merge PUT is in flight for it."""


class ReviewHeadChanged(ValueError):
    """Raised when an owner decision names an ``expected_head_sha`` that no
    longer matches the item's current head — the PR was re-pushed since the
    owner saw it, so the decision must not silently apply to unseen content
    (Fable F1)."""

#: Verify verdicts. Only ``"pass"`` is green; everything else blocks merge.
VERIFY_PASS = "pass"
VERIFY_FAIL = "fail"
VERIFY_UNKNOWN = "unknown"


def review_queue_db_path(universe_dir: str | Path) -> Path:
    """Resolve the per-universe review-queue DB path."""
    return Path(universe_dir) / _DB_FILENAME


@contextmanager
def _connect(universe_dir: str | Path) -> Iterator[sqlite3.Connection]:
    """Open the review-queue DB with WAL + a 30s busy timeout (hard rule 1).

    The handle is ALWAYS closed in ``finally`` — a raw ``sqlite3.Connection``
    used as ``with conn`` only commits/rolls back the transaction and leaves the
    file handle open, which on Windows blocks deleting ``.review_queue.db``
    (WinError 32).

    Concurrency-safety (Codex R3 CRITICAL 2):

    * The connection enters the ``try`` block IMMEDIATELY after opening, so a
      lock error raised by a ``PRAGMA`` (which happens under contention) still
      closes the handle instead of leaking it.
    * ``busy_timeout`` is set BEFORE the WAL pragma so the WAL switch itself
      waits for a competing writer rather than raising ``database is locked``.
    * ``isolation_level=None`` (autocommit) hands transaction control to the
      caller via :func:`_write`, which opens ``BEGIN IMMEDIATE`` up front so
      concurrent SELECT-then-write paths cannot deadlock on lock upgrade.
    """
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
    """Serialize writers with an upfront write lock.

    ``BEGIN IMMEDIATE`` acquires the write lock before any SELECT, so two
    concurrent enqueues cannot each take a read snapshot and then deadlock
    trying to upgrade to a write (the ``database is locked`` failure mode under
    the 64-thread stress). Commits on success, rolls back on any exception.
    Used with an ``isolation_level=None`` connection (autocommit) so no implicit
    transaction competes with this explicit one.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_queue (
    item_id        TEXT PRIMARY KEY,
    destination    TEXT NOT NULL,
    pr_number      INTEGER NOT NULL,
    pr_url         TEXT NOT NULL,
    head_sha       TEXT NOT NULL DEFAULT '',
    request_ref    TEXT NOT NULL DEFAULT '',
    verify_verdict TEXT NOT NULL DEFAULT 'unknown',
    status         TEXT NOT NULL,
    notes          TEXT NOT NULL DEFAULT '',
    merge_commit_sha TEXT NOT NULL DEFAULT '',
    -- Merge-policy config: the TRUSTED DURABLE governing policy (the present
    -- node writes it from loop state). The merge effector resolves policy from
    -- HERE, not the packet — a packet may only narrow it (Codex R6 C1).
    merge_policy   TEXT NOT NULL DEFAULT 'manual',
    founder_oauth_per_merge INTEGER NOT NULL DEFAULT 0,
    merge_timer_delay_s REAL NOT NULL DEFAULT 0,
    -- Resume identity: what the loop needs to act on an owner decision without
    -- new run machinery (Codex R6 C3).
    universe_id    TEXT NOT NULL DEFAULT '',
    branch_def_id  TEXT NOT NULL DEFAULT '',
    run_id         TEXT NOT NULL DEFAULT '',
    created_at     REAL NOT NULL,
    head_queued_at REAL NOT NULL DEFAULT 0,
    merge_claimed_at REAL,
    updated_at     REAL NOT NULL,
    decided_by     TEXT NOT NULL DEFAULT '',
    decided_at     REAL
);

CREATE INDEX IF NOT EXISTS idx_review_queue_status
    ON review_queue(status);

-- One queue row per (repo, PR): enqueue is upsert-shaped and the UNIQUE index
-- is defense-in-depth against a racing duplicate INSERT (Codex R3 CRITICAL 2b).
CREATE UNIQUE INDEX IF NOT EXISTS idx_review_queue_dest_pr
    ON review_queue(destination, pr_number);

CREATE TABLE IF NOT EXISTS merge_approvals (
    approval_id  TEXT PRIMARY KEY,
    item_id      TEXT NOT NULL,
    destination  TEXT NOT NULL,
    pr_number    INTEGER NOT NULL,
    head_sha     TEXT NOT NULL,
    approved_by  TEXT NOT NULL,
    approved_at  REAL NOT NULL,
    -- Token regime binding (Codex R6 C1): the policy signature the token was
    -- minted under + an expiry. A token only satisfies a merge whose current
    -- regime signature matches AND which is not expired.
    policy_generation TEXT NOT NULL DEFAULT '',
    expires_at   REAL,
    consumed_at  REAL
);

CREATE INDEX IF NOT EXISTS idx_merge_approvals_fresh
    ON merge_approvals(destination, pr_number, head_sha)
    WHERE consumed_at IS NULL;

-- Reshape outbox (Codex R7 C4 — Phase-2 resume seam): a reshape PERSISTS the
-- route_back here as a durable row so the Phase-2 resume consumer can read it
-- (the resume engine + revised-run production is Phase 2 — NOT built here). Not
-- just an ephemeral return dict.
CREATE TABLE IF NOT EXISTS reshape_outbox (
    outbox_id     TEXT PRIMARY KEY,
    item_id       TEXT NOT NULL,
    target_node   TEXT NOT NULL DEFAULT 'draft_patch',
    universe_id   TEXT NOT NULL DEFAULT '',
    branch_def_id TEXT NOT NULL DEFAULT '',
    run_id        TEXT NOT NULL DEFAULT '',
    owner_notes   TEXT NOT NULL DEFAULT '',
    created_at    REAL NOT NULL,
    consumed_at   REAL
);

CREATE INDEX IF NOT EXISTS idx_reshape_outbox_pending
    ON reshape_outbox(created_at) WHERE consumed_at IS NULL;

-- Owner-bound merge-policy config (Codex R6 C2): the governing policy is
-- resolved from HERE by (branch_def_id) — set by the OWNER (S2 remix binding /
-- an owner-gated verb), NOT from a model-emitted packet. The present node reads
-- this to stamp each queued PR. S4 owns the store; S2 converges on it.
CREATE TABLE IF NOT EXISTS merge_policy_bindings (
    branch_def_id TEXT PRIMARY KEY,
    merge_policy   TEXT NOT NULL DEFAULT 'manual',
    founder_oauth_per_merge INTEGER NOT NULL DEFAULT 0,
    merge_timer_delay_s REAL NOT NULL DEFAULT 0,
    bound_by      TEXT NOT NULL DEFAULT '',
    bound_at      REAL NOT NULL DEFAULT 0
);
"""


def initialize_review_queue_db(universe_dir: str | Path) -> Path:
    """Ensure the review-queue DB exists and is migrated. Returns the DB path.

    Idempotent + cached: the schema DDL runs at most once per db path per
    process (serialized by ``_INIT_LOCK``), so the hot path — every enqueue /
    decide — does NOT run ``executescript`` and contend for the write lock under
    concurrency. The ``path.exists()`` recheck re-initializes if the file was
    removed out from under us (e.g. a test that deletes the db)."""
    path = review_queue_db_path(universe_dir)
    key = str(path)
    if key in _INITIALIZED and path.exists():
        return path
    with _INIT_LOCK:
        with _connect(universe_dir) as conn:
            conn.executescript(_SCHEMA)
        _INITIALIZED.add(key)
    return path


def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "item_id": row["item_id"],
        "destination": row["destination"],
        "pr_number": row["pr_number"],
        "pr_url": row["pr_url"],
        "head_sha": row["head_sha"],
        "request_ref": row["request_ref"],
        "verify_verdict": row["verify_verdict"],
        "status": row["status"],
        "notes": row["notes"],
        "merge_commit_sha": row["merge_commit_sha"],
        "merge_policy": row["merge_policy"],
        "founder_oauth_per_merge": bool(row["founder_oauth_per_merge"]),
        "merge_timer_delay_s": row["merge_timer_delay_s"],
        "universe_id": row["universe_id"],
        "branch_def_id": row["branch_def_id"],
        "run_id": row["run_id"],
        "created_at": row["created_at"],
        "head_queued_at": row["head_queued_at"],
        "merge_claimed_at": row["merge_claimed_at"],
        "updated_at": row["updated_at"],
        "decided_by": row["decided_by"],
        "decided_at": row["decided_at"],
    }


def enqueue_pr(
    universe_dir: str | Path,
    *,
    destination: str,
    pr_number: int,
    pr_url: str,
    head_sha: str = "",
    request_ref: str = "",
    verify_verdict: str = VERIFY_UNKNOWN,
    merge_policy: str = "manual",
    founder_oauth_per_merge: bool = False,
    merge_timer_delay_s: float = 0.0,
    universe_id: str = "",
    branch_def_id: str = "",
    run_id: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    """Record a loop-produced PR as ``pending`` on the owner's review queue.

    Called by the loop's ``present`` node once it has opened a ready-to-merge
    PR. Idempotent on ``(destination, pr_number)``: re-presenting the same PR
    (e.g. after a re-push) refreshes ``head_sha`` / ``verify_verdict`` and
    resets the item to ``pending`` so the owner re-reviews the new head, but
    keeps the original ``item_id`` + ``created_at``.

    The **governing merge policy** (``merge_policy`` / ``founder_oauth_per_merge``
    / ``merge_timer_delay_s``) and the **resume identity** (``universe_id`` /
    ``branch_def_id`` / ``run_id``) are stored on the item: the merge effector
    resolves policy from HERE (trusted durable state), and the loop reads the
    resume identity to act on an owner decision (Codex R6 C1/C3).

    **Terminal-decision safety (Codex R3 CRITICAL 1):** re-presenting the SAME
    head of an item the owner already decided (``reshaped`` / ``rejected`` /
    ``merged``) does NOT reopen it — the existing terminal row is returned
    unchanged with ``already_decided=True``. Only a CHANGED ``head_sha`` (new
    work) re-pends a terminal item. This is what stops a rejection from being
    laundered away by re-presenting the identical head.

    ``head_queued_at`` is the per-head clock the timer merge policy counts
    from: it is reset to ``now`` whenever ``head_sha`` changes (initial enqueue
    or a re-push to a new head), so a freshly-pushed head is not instantly
    timer-eligible off the first-ever enqueue timestamp (Codex R2 REQUIRED 2).
    Re-presenting the SAME head keeps the existing ``head_queued_at`` and clears
    any stale ``merge_claimed_at`` when the head changes (Fable F3).

    Raises ``ValueError`` on missing required fields or a malformed
    ``merge_timer_delay_s`` (must be finite, non-negative) — a contract
    violation, fail loud per hard rule 8.
    """
    dest = (destination or "").strip()
    if not dest:
        raise ValueError("enqueue_pr requires non-empty destination")
    if not isinstance(pr_number, int) or pr_number <= 0:
        raise ValueError("enqueue_pr requires a positive integer pr_number")
    url = (pr_url or "").strip()
    if not url:
        raise ValueError("enqueue_pr requires non-empty pr_url")
    verdict = (verify_verdict or VERIFY_UNKNOWN).strip() or VERIFY_UNKNOWN
    policy_str = (merge_policy or "manual").strip().lower() or "manual"
    oauth_int = 1 if founder_oauth_per_merge else 0
    try:
        delay = float(merge_timer_delay_s if merge_timer_delay_s is not None else 0.0)
    except (TypeError, ValueError):
        raise ValueError(
            f"enqueue_pr merge_timer_delay_s must be a finite non-negative "
            f"number, got {merge_timer_delay_s!r}"
        ) from None
    if not math.isfinite(delay) or delay < 0:
        raise ValueError(
            f"enqueue_pr merge_timer_delay_s must be finite and non-negative, "
            f"got {merge_timer_delay_s!r}"
        )
    uid = (universe_id or "").strip()
    bdid = (branch_def_id or "").strip()
    rid = (run_id or "").strip()

    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    already_decided = False
    with _connect(universe_dir) as conn:
        with _write(conn):  # BEGIN IMMEDIATE — atomic select-then-write
            existing = conn.execute(
                "SELECT item_id, created_at, head_sha, head_queued_at, status, "
                "merge_policy, founder_oauth_per_merge, branch_def_id, "
                "merge_timer_delay_s "
                "FROM review_queue WHERE destination = ? AND pr_number = ?",
                (dest, pr_number),
            ).fetchone()
            if existing is not None:
                item_id = existing["item_id"]
                head_changed = (existing["head_sha"] or "") != (head_sha or "")
                regime_changed = _policy_signature(
                    existing["merge_policy"], existing["founder_oauth_per_merge"],
                    existing["branch_def_id"], existing["merge_timer_delay_s"],
                ) != _policy_signature(policy_str, oauth_int, bdid, delay)
                # A same-head re-present of a TERMINAL row must NOT reopen it —
                # the owner already decided this exact head, and silently
                # re-pending would launder a rejection away (Codex R3 CRITICAL
                # 1). A same-head ``merging`` row is an in-flight merge, and a
                # same-head ``held`` row is an owner PAUSE — both must be left
                # untouched, or a model-driven present node could silently defeat
                # the owner's hold / claim (Fable). Only a CHANGED head is new
                # work that re-pends. Non-terminal same-head re-presents refresh.
                if not head_changed and existing["status"] in (
                    _TERMINAL_STATUSES | {"merging", "held"}
                ):
                    already_decided = True
                else:
                    # Invalidate outstanding founder-OAuth tokens when the head
                    # OR the policy regime changes (Codex R6 C1): a token minted
                    # while OAuth was OFF must not satisfy a later OAuth-ON gate.
                    if head_changed or regime_changed:
                        conn.execute(
                            "UPDATE merge_approvals SET consumed_at = ? "
                            "WHERE item_id = ? AND consumed_at IS NULL",
                            (ts, item_id),
                        )
                    # Reset the timer clock only when the head actually changed;
                    # a same-head refresh keeps the original head_queued_at.
                    head_queued_at = ts if head_changed else existing["head_queued_at"]
                    conn.execute(
                        """
                        UPDATE review_queue
                           SET pr_url = ?, head_sha = ?, request_ref = ?,
                               verify_verdict = ?, status = 'pending',
                               notes = '', merge_policy = ?,
                               founder_oauth_per_merge = ?, merge_timer_delay_s = ?,
                               universe_id = ?, branch_def_id = ?, run_id = ?,
                               head_queued_at = ?, merge_claimed_at = NULL,
                               updated_at = ?, decided_by = '', decided_at = NULL
                         WHERE item_id = ?
                        """,
                        (url, head_sha, request_ref, verdict, policy_str,
                         oauth_int, delay, uid, bdid, rid,
                         head_queued_at, ts, item_id),
                    )
            else:
                item_id = f"rq-{uuid.uuid4().hex[:16]}"
                conn.execute(
                    """
                    INSERT INTO review_queue (
                        item_id, destination, pr_number, pr_url, head_sha,
                        request_ref, verify_verdict, status, notes,
                        merge_policy, founder_oauth_per_merge, merge_timer_delay_s,
                        universe_id, branch_def_id, run_id,
                        created_at, head_queued_at, updated_at,
                        decided_by, decided_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '',
                              ?, ?, ?, ?, ?, ?, ?, ?, ?, '', NULL)
                    """,
                    (
                        item_id, dest, pr_number, url, head_sha,
                        request_ref, verdict, policy_str, oauth_int, delay,
                        uid, bdid, rid, ts, ts, ts,
                    ),
                )
            row = conn.execute(
                "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
            ).fetchone()
    result = _row_to_item(row)
    if already_decided:
        # Surface to the present node that the owner's decision on this exact
        # head stands — it must open a new head (changed head_sha) to reopen.
        result["already_decided"] = True
    return result


def get_item(universe_dir: str | Path, *, item_id: str) -> dict[str, Any] | None:
    """Return a single queue item by id, or None if absent."""
    if not item_id:
        return None
    initialize_review_queue_db(universe_dir)
    with _connect(universe_dir) as conn:
        row = conn.execute(
            "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
        ).fetchone()
    return _row_to_item(row) if row is not None else None


def list_queue(
    universe_dir: str | Path,
    *,
    status: str | None = None,
    destination: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return queue items, newest first. Optional ``status`` / ``destination``
    filters. Paginated (Codex R6 C6): ``limit`` defaults to 50 and is capped at
    200; ``offset`` skips rows. Pass ``limit=0`` to disable the cap (internal
    callers that need the whole queue, e.g. the merge effector's PR lookup)."""
    initialize_review_queue_db(universe_dir)
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if destination:
        clauses.append("destination = ?")
        params.append(destination)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    if limit == 0:
        page = ""
    else:
        if limit is None:
            eff_limit = _LIST_DEFAULT_LIMIT
        else:
            eff_limit = max(1, min(int(limit), _LIST_MAX_LIMIT))
        page = " LIMIT ? OFFSET ?"
        params.extend([eff_limit, max(0, int(offset))])
    with _connect(universe_dir) as conn:
        rows = conn.execute(
            f"SELECT * FROM review_queue {where} ORDER BY created_at DESC{page}",
            params,
        ).fetchall()
    return [_row_to_item(row) for row in rows]


# Terminal statuses as a SQL literal tuple, for the conditional UPDATE guard.
_TERMINAL_SQL = "('reshaped', 'rejected', 'merged')"


def _decide_txn(
    conn: sqlite3.Connection,
    *,
    item_id: str,
    new_status: str,
    decided_by: str,
    notes: str,
    ts: float,
    invalidate_approvals: bool,
    expected_head_sha: str | None = None,
) -> dict[str, Any] | None:
    """Perform an owner decision ATOMICALLY inside an already-open ``_write``
    (``BEGIN IMMEDIATE``) transaction.

    Because ``BEGIN IMMEDIATE`` takes the write lock before this read, the read
    is stable against a competing decision on another connection — closing the
    TOCTOU where the terminal-status check happened outside the write
    transaction and a stale decision could resurrect a rejected item (Codex R4
    CRITICAL). Belt-and-braces: the check is enforced BOTH by the in-transaction
    read AND by a conditional ``UPDATE ... WHERE status NOT IN (terminal)`` whose
    ``rowcount`` must be 1 — either alone would suffice; both is cheap insurance.

    Returns the updated item dict, ``None`` if the item does not exist, or raises
    ``InvalidReviewTransition`` when the item is terminal (rolling back the
    surrounding transaction, so no approval insert / approval invalidation from
    the same unit survives). Raises ``MergeInProgress`` when the item carries a
    FRESH ``merging`` claim — a merge PUT is in flight, so an owner decision must
    wait; a STALE claim (crashed effector) is reclaimable and the decision
    proceeds, clearing the claim (Codex R5 CRITICAL 1).
    """
    row = conn.execute(
        "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
    ).fetchone()
    if row is None:
        return None
    # Head-bind the decision (Fable F1): if the caller says which head it saw
    # and the PR has since been re-pushed, the decision must not silently apply
    # to unseen content — fail closed BEFORE any mutation.
    if expected_head_sha is not None and (row["head_sha"] or "") != expected_head_sha:
        raise ReviewHeadChanged(
            f"cannot {new_status} review item {item_id!r}: it now points at head "
            f"{row['head_sha']!r}, not the {expected_head_sha!r} you reviewed; "
            "re-read the PR and decide on the current head"
        )
    if row["status"] in _TERMINAL_STATUSES:
        raise InvalidReviewTransition(
            f"cannot {new_status} review item {item_id!r} in terminal status "
            f"{row['status']!r}; re-present the PR (fresh enqueue / new head) "
            "to re-open it for review"
        )
    if row["status"] == "merging":
        claimed_at = row["merge_claimed_at"]
        if claimed_at is not None and (ts - claimed_at) < _MERGE_CLAIM_TIMEOUT_S:
            raise MergeInProgress(
                f"cannot {new_status} review item {item_id!r}: a merge is in "
                f"progress (claimed {ts - claimed_at:.0f}s ago); retry after it "
                "completes or the claim times out"
            )
        # Stale claim → the effector holding it crashed; the owner may reclaim
        # the item. The decision below clears merge_claimed_at.
    if invalidate_approvals:
        conn.execute(
            "UPDATE merge_approvals SET consumed_at = ? "
            "WHERE item_id = ? AND consumed_at IS NULL",
            (ts, item_id),
        )
    head_clause = ""
    params: list[Any] = [new_status, notes, decided_by, ts, ts, item_id]
    if expected_head_sha is not None:
        head_clause = " AND head_sha = ?"
        params.append(expected_head_sha)
    cur = conn.execute(
        f"""
        UPDATE review_queue
           SET status = ?, notes = ?, decided_by = ?,
               decided_at = ?, updated_at = ?, merge_claimed_at = NULL
         WHERE item_id = ? AND status NOT IN {_TERMINAL_SQL}{head_clause}
        """,
        params,
    )
    if cur.rowcount != 1:
        # Lost the race: another writer moved the item terminal (or re-pushed the
        # head) between our read and update — impossible under BEGIN IMMEDIATE,
        # but the conditional UPDATE makes it fail closed rather than silently
        # resurrect / decide the wrong head.
        raise InvalidReviewTransition(
            f"cannot {new_status} review item {item_id!r}: it was decided "
            "concurrently; re-present the PR (new head) to re-open it"
        )
    updated = conn.execute(
        "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
    ).fetchone()
    return _row_to_item(updated)


def approve_item(
    universe_dir: str | Path,
    *,
    item_id: str,
    approved_by: str,
    notes: str = "",
    expected_head_sha: str | None = None,
    actor_is_owner: bool = True,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Owner approves a queued PR. Sets status ``approved`` and mints a **fresh,
    single-use founder-OAuth approval** bound to the item's current
    ``head_sha`` + ``pr_number`` + policy REGIME, with an expiry.

    ``actor_is_owner`` is checked INSIDE the mint transaction (Codex R6 C1): if
    the item's ``founder_oauth_per_merge`` is set and the actor is not the
    universe owner, ``OwnerRequired`` is raised and nothing is minted — closing
    the actions-layer TOCTOU where the row's flag could change between the
    handler's check and the mint.

    ``expected_head_sha`` head-binds the approval (Fable F1): the credential is
    minted only if the item's current head still matches the head the owner
    reviewed; a re-push in between raises ``ReviewHeadChanged`` and mints
    nothing.

    No token stockpiling (Codex R6 C1): any prior fresh token for the item is
    invalidated before the new one is minted, so at most one token is consumable.

    The minted approval is what a founder-OAuth-per-merge policy consumes at
    merge time (see :func:`consume_merge_approval`). For a manual policy WITHOUT
    founder-OAuth the token is simply unused — the ``approved`` status alone
    releases the merge.

    Returns the updated item (with an ``approval_id`` key), or None when the
    item does not exist.
    """
    if not approved_by:
        raise ValueError("approve_item requires non-empty approved_by")
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    approval_id = f"ap-{uuid.uuid4().hex[:16]}"
    with _connect(universe_dir) as conn:
        with _write(conn):
            # In-txn owner authority check on the OAuth-gated item, BEFORE any
            # mutation (Codex R6 C1). Read the row's governing flag inside the
            # write lock so it can't change under us.
            row = conn.execute(
                "SELECT founder_oauth_per_merge, merge_policy "
                "FROM review_queue WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            if row is not None and row["founder_oauth_per_merge"] and not actor_is_owner:
                raise OwnerRequired(
                    f"approving item {item_id!r} mints a founder-OAuth-per-merge "
                    "credential; only the universe owner/founder may do that"
                )
            # Atomic: terminal-check + head-bind + status update + approval mint
            # are ONE transaction. On a terminal/head-changed row _decide_txn
            # raises and the whole unit rolls back — no approval is minted.
            updated = _decide_txn(
                conn,
                item_id=item_id,
                new_status="approved",
                decided_by=approved_by,
                notes=notes,
                ts=ts,
                invalidate_approvals=False,
                expected_head_sha=expected_head_sha,
            )
            if updated is None:
                return None
            # No stockpiling — invalidate any prior fresh token for the item.
            conn.execute(
                "UPDATE merge_approvals SET consumed_at = ? "
                "WHERE item_id = ? AND consumed_at IS NULL",
                (ts, item_id),
            )
            generation = _policy_signature(
                updated["merge_policy"], updated["founder_oauth_per_merge"],
                updated["branch_def_id"], updated["merge_timer_delay_s"],
            )
            conn.execute(
                """
                INSERT INTO merge_approvals (
                    approval_id, item_id, destination, pr_number, head_sha,
                    approved_by, approved_at, policy_generation, expires_at,
                    consumed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    approval_id, item_id, updated["destination"],
                    updated["pr_number"], updated["head_sha"], approved_by, ts,
                    generation, ts + _APPROVAL_TTL_S,
                ),
            )
    updated["approval_id"] = approval_id
    return updated


def reshape_item(
    universe_dir: str | Path,
    *,
    item_id: str,
    reshaped_by: str,
    notes: str,
    expected_head_sha: str | None = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Owner sends a PR back to the loop with notes. Sets status ``reshaped``
    and returns the item plus a ``route_back`` payload the loop's
    ``draft_patch`` node consumes to produce a revised patch.

    ``notes`` is required — a reshape with no guidance is meaningless; the
    owner must say what to change. Any outstanding fresh approvals for the item
    are invalidated (consumed) so a stale approval can't merge the pre-reshape
    head. ``expected_head_sha`` is honored if given (Fable F1 — optional for
    reshape). The owner notes + resume identity persist on the durable row so
    the loop can act on the reshape (Codex R6 C3).
    """
    reshaped_by = (reshaped_by or "").strip()
    if not reshaped_by:
        raise ValueError("reshape_item requires non-empty reshaped_by")
    if not (notes or "").strip():
        raise ValueError(
            "reshape_item requires non-empty notes — a reshape must tell the "
            "loop what to change"
        )
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    # Terminal-check + approval invalidation + status update + durable outbox
    # write in ONE transaction (Codex R7 C4: persist the route_back, don't just
    # return it).
    outbox_id = f"rb-{uuid.uuid4().hex[:16]}"
    with _connect(universe_dir) as conn:
        with _write(conn):
            updated = _decide_txn(
                conn,
                item_id=item_id,
                new_status="reshaped",
                decided_by=reshaped_by,
                notes=notes,
                ts=ts,
                invalidate_approvals=True,
                expected_head_sha=expected_head_sha,
            )
            if updated is None:
                return None
            conn.execute(
                """
                INSERT INTO reshape_outbox (
                    outbox_id, item_id, target_node, universe_id, branch_def_id,
                    run_id, owner_notes, created_at, consumed_at
                ) VALUES (?, ?, 'draft_patch', ?, ?, ?, ?, ?, NULL)
                """,
                (
                    outbox_id, item_id, updated["universe_id"],
                    updated["branch_def_id"], updated["run_id"], notes, ts,
                ),
            )
    updated["route_back"] = {
        "target_node": "draft_patch",
        "outbox_id": outbox_id,
        "item_id": item_id,
        "destination": updated["destination"],
        "pr_number": updated["pr_number"],
        "request_ref": updated["request_ref"],
        "owner_notes": notes,
        # Resume identity the loop needs to act on the reshape (Codex R6 C3).
        "universe_id": updated["universe_id"],
        "branch_def_id": updated["branch_def_id"],
        "run_id": updated["run_id"],
    }
    return updated


def list_pending_reshape_routes(
    universe_dir: str | Path, *, limit: int = 100
) -> list[dict[str, Any]]:
    """Read unconsumed reshape route_backs (Codex R7 C4). The Phase-2 resume
    consumer reads these durable rows to resume runs; the resume engine +
    revised-run production itself is Phase 2 (NOT built here)."""
    initialize_review_queue_db(universe_dir)
    with _connect(universe_dir) as conn:
        rows = conn.execute(
            "SELECT outbox_id, item_id, target_node, universe_id, branch_def_id, "
            "run_id, owner_notes, created_at FROM reshape_outbox "
            "WHERE consumed_at IS NULL ORDER BY created_at ASC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    return [
        {
            "outbox_id": r["outbox_id"],
            "item_id": r["item_id"],
            "target_node": r["target_node"],
            "universe_id": r["universe_id"],
            "branch_def_id": r["branch_def_id"],
            "run_id": r["run_id"],
            "owner_notes": r["owner_notes"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def reject_item(
    universe_dir: str | Path,
    *,
    item_id: str,
    rejected_by: str,
    notes: str = "",
    expected_head_sha: str | None = None,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Owner rejects a queued PR (terminal). Invalidates outstanding approvals.
    ``expected_head_sha`` is honored if given (Fable F1 — optional for reject)."""
    rejected_by = (rejected_by or "").strip()
    if not rejected_by:
        raise ValueError("reject_item requires non-empty rejected_by")
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        with _write(conn):
            return _decide_txn(
                conn,
                item_id=item_id,
                new_status="rejected",
                decided_by=rejected_by,
                notes=notes,
                ts=ts,
                expected_head_sha=expected_head_sha,
                invalidate_approvals=True,
            )


def claim_for_merge(
    universe_dir: str | Path,
    *,
    item_id: str,
    expected_head_sha: str,
    expected_updated_at: float | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Atomically CLAIM an eligible item for merge, flipping it to ``merging``.

    A merge effector must call this in ONE ``BEGIN IMMEDIATE`` transaction
    BEFORE it fires the GitHub merge PUT, so a concurrent owner reject/reshape
    cannot land during the merge and be overwritten by the post-success
    ``mark_merged`` (Codex R5 CRITICAL 1). The claim is a compare-and-set:

    * the item must still exist, its ``head_sha`` must equal
      ``expected_head_sha`` (the head the effector verified against GitHub), and
      its status must be claimable — NOT terminal, and NOT already ``merging``
      UNLESS that claim is stale (``_MERGE_CLAIM_TIMEOUT_S``);
    * ``expected_updated_at`` is a row-version generation token (Codex R6 C2):
      the effector passes the ``updated_at`` it read when it evaluated
      eligibility, and the claim REFUSES if the row changed since (e.g. a
      same-head re-enqueue flipped ``verify_verdict`` pass→fail). This binds the
      claim to the exact FACTS eligibility saw, not just status + head;
    * on success it flips to ``merging`` + stamps ``merge_claimed_at`` and
      returns ``{"claimed": True, "prior_status": <status>, "item": <row>}``;
    * on failure it returns ``{"claimed": False, "reason": <why>,
      "current_status": <status|None>}`` and the effector must NOT merge.

    Only a successfully-claimed item may proceed to the PUT. On PUT success the
    effector calls :func:`mark_merged` (merging→merged); on PUT failure it calls
    :func:`release_merge_claim` to restore the prior status.
    """
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        with _write(conn):
            row = conn.execute(
                "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
            ).fetchone()
            if row is None:
                return {"claimed": False, "reason": "not_found",
                        "current_status": None}
            status = row["status"]
            if (row["head_sha"] or "") != (expected_head_sha or ""):
                return {"claimed": False, "reason": "head_changed",
                        "current_status": status}
            if (
                expected_updated_at is not None
                and row["updated_at"] != expected_updated_at
            ):
                # The row changed between eligibility evaluation and the claim —
                # the eligibility facts (verify_verdict, timer clock, …) may no
                # longer hold. Refuse (Codex R6 C2).
                return {"claimed": False, "reason": "facts_changed",
                        "current_status": status}
            if status in _TERMINAL_STATUSES:
                return {"claimed": False, "reason": "already_decided",
                        "current_status": status}
            if status == "merging":
                claimed_at = row["merge_claimed_at"]
                fresh = (
                    claimed_at is not None
                    and (ts - claimed_at) < _MERGE_CLAIM_TIMEOUT_S
                )
                if fresh:
                    return {"claimed": False, "reason": "merge_in_progress",
                            "current_status": status}
                # else: stale claim — reclaimable (fall through to CAS below).
            # CAS: flip an eligible (non-terminal) row to merging. Excludes only
            # terminal statuses so a stale `merging` row can be reclaimed; the
            # updated_at guard is belt-and-braces behind the in-txn read.
            head_clause = "" if expected_updated_at is None else " AND updated_at = ?"
            cas_params: list[Any] = [ts, ts, item_id]
            if expected_updated_at is not None:
                cas_params.append(expected_updated_at)
            cur = conn.execute(
                f"""
                UPDATE review_queue
                   SET status = 'merging', merge_claimed_at = ?, updated_at = ?
                 WHERE item_id = ? AND status NOT IN {_TERMINAL_SQL}{head_clause}
                """,
                cas_params,
            )
            if cur.rowcount != 1:
                return {"claimed": False, "reason": "claim_lost",
                        "current_status": status}
            updated = conn.execute(
                "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
            ).fetchone()
    # Normalize the restore target for a reclaimed STALE `merging` claim: restore
    # to a decidable `pending`, not back to `merging` (Fable F3).
    prior_status = status if status != "merging" else "pending"
    return {
        "claimed": True,
        "prior_status": prior_status,
        "item": _row_to_item(updated),
    }


def release_merge_claim(
    universe_dir: str | Path,
    *,
    item_id: str,
    restore_status: str,
    now: float | None = None,
) -> bool:
    """Release a ``merging`` claim back to ``restore_status`` (its prior state)
    after a failed merge PUT. Conditional on the row still being ``merging`` so
    it never clobbers an owner decision that reclaimed a stale claim. Returns
    True when a row was released."""
    # Fable nit: never write an out-of-vocabulary status back into the row.
    if restore_status not in VALID_STATUSES or restore_status == "merging":
        raise ValueError(
            f"release_merge_claim restore_status must be a non-merging valid "
            f"status, got {restore_status!r}"
        )
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        with _write(conn):
            cur = conn.execute(
                """
                UPDATE review_queue
                   SET status = ?, merge_claimed_at = NULL, updated_at = ?
                 WHERE item_id = ? AND status = 'merging'
                """,
                (restore_status, ts, item_id),
            )
            return cur.rowcount == 1


def mark_merged(
    universe_dir: str | Path,
    *,
    item_id: str,
    merge_commit_sha: str = "",
    now: float | None = None,
) -> dict[str, Any] | None:
    """Transition a CLAIMED (``merging``) item to terminal ``merged`` after the
    effector confirms the GitHub merge. Records the merge commit SHA and
    consumes any outstanding approval so the owner surface stops showing the PR
    as pending/approved (Codex REQUIRED 4).

    The transition is REQUIRED to be FROM ``merging`` (conditional UPDATE), so a
    reject/reshape that somehow cleared the claim (stale-timeout reclaim) can
    NEVER be overwritten to merged (Codex R5 CRITICAL 1). Returns the updated
    item; ``None`` if the item is missing OR is not in ``merging`` (a conflict
    the effector surfaces). Idempotent: an already-``merged`` item returns its
    current row.
    """
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        with _write(conn):
            row = conn.execute(
                "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
            ).fetchone()
            if row is None:
                return None
            if row["status"] == "merged":
                return _row_to_item(row)  # idempotent no-op
            if row["status"] != "merging":
                # Not claimed for merge (e.g. a reject reclaimed a stale claim).
                # Refuse to overwrite — the merge landed on GitHub but the queue
                # reflects the owner decision; the effector surfaces the conflict.
                return None
            conn.execute(
                "UPDATE merge_approvals SET consumed_at = ? "
                "WHERE item_id = ? AND consumed_at IS NULL",
                (ts, item_id),
            )
            conn.execute(
                """
                UPDATE review_queue
                   SET status = 'merged', merge_commit_sha = ?,
                       merge_claimed_at = NULL, updated_at = ?
                 WHERE item_id = ? AND status = 'merging'
                """,
                (merge_commit_sha or "", ts, item_id),
            )
            updated = conn.execute(
                "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
            ).fetchone()
    return _row_to_item(updated) if updated is not None else None


def has_fresh_merge_approval(
    universe_dir: str | Path,
    *,
    destination: str,
    pr_number: int,
    head_sha: str,
    policy_generation: str | None = None,
    now: float | None = None,
) -> bool:
    """Return True iff a fresh, unexpired, regime-matching founder-OAuth approval
    exists bound to the exact ``(destination, pr_number, head_sha)``. Read-only.

    ``policy_generation`` (the item's CURRENT regime signature) must match the
    token's minted-under signature, and the token must not be expired (Codex R6
    C1 token regime). A standing effector consent is intentionally invisible —
    this queries only ``merge_approvals``, never ``effector_consents``.
    """
    if not destination or not head_sha or not isinstance(pr_number, int):
        return False
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    clauses = ["destination = ?", "pr_number = ?", "head_sha = ?",
               "consumed_at IS NULL", "(expires_at IS NULL OR expires_at > ?)"]
    params: list[Any] = [destination, pr_number, head_sha, ts]
    if policy_generation is not None:
        clauses.append("policy_generation = ?")
        params.append(policy_generation)
    with _connect(universe_dir) as conn:
        row = conn.execute(
            f"SELECT 1 FROM merge_approvals WHERE {' AND '.join(clauses)} LIMIT 1",
            params,
        ).fetchone()
    return row is not None


def consume_merge_approval(
    universe_dir: str | Path,
    *,
    destination: str,
    pr_number: int,
    head_sha: str,
    policy_generation: str | None = None,
    now: float | None = None,
) -> str | None:
    """Consume (single-use) a fresh founder-OAuth approval for an exact
    ``(destination, pr_number, head_sha)`` and return its ``approval_id``.

    Returns None when no fresh, unexpired, regime-matching approval exists — the
    founder has not performed a fresh authenticated approval for *this* PR head
    under the *current* policy regime. A standing effector consent can NEVER
    satisfy this (different table); an expired, consumed, or wrong-regime token
    can never satisfy it either (Codex R6 C1).
    """
    if not destination or not head_sha or not isinstance(pr_number, int):
        return None
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    clauses = ["destination = ?", "pr_number = ?", "head_sha = ?",
               "consumed_at IS NULL", "(expires_at IS NULL OR expires_at > ?)"]
    params: list[Any] = [destination, pr_number, head_sha, ts]
    if policy_generation is not None:
        clauses.append("policy_generation = ?")
        params.append(policy_generation)
    with _connect(universe_dir) as conn:
        with _write(conn):  # atomic claim — no double-consume under concurrency
            row = conn.execute(
                f"SELECT approval_id FROM merge_approvals "
                f"WHERE {' AND '.join(clauses)} ORDER BY approved_at ASC LIMIT 1",
                params,
            ).fetchone()
            if row is None:
                return None
            approval_id = row["approval_id"]
            # Belt-and-braces: the `consumed_at IS NULL` guard makes the claim
            # idempotent even if two consumers somehow reached the same token.
            cur = conn.execute(
                "UPDATE merge_approvals SET consumed_at = ? "
                "WHERE approval_id = ? AND consumed_at IS NULL",
                (ts, approval_id),
            )
            if cur.rowcount != 1:
                return None
    return approval_id


def hold_item(
    universe_dir: str | Path,
    *,
    item_id: str,
    held_by: str,
    notes: str = "",
    now: float | None = None,
) -> dict[str, Any] | None:
    """Owner PAUSE (non-terminal): move a pending/approved/held item to ``held``,
    which blocks auto/timer merge eligibility until released (Codex R6 C5). Not
    a substitute for reshape/reject. Returns the updated item, None if missing,
    raises on a terminal / in-flight-merging item."""
    held_by = (held_by or "").strip()
    if not held_by:
        raise ValueError("hold_item requires non-empty held_by")
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        with _write(conn):
            return _decide_txn(
                conn, item_id=item_id, new_status="held", decided_by=held_by,
                notes=notes, ts=ts, invalidate_approvals=False,
            )


def release_hold(
    universe_dir: str | Path,
    *,
    item_id: str,
    released_by: str,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Owner RESUME: move a ``held`` item back to ``pending`` so auto/timer merge
    eligibility can proceed again (Codex R6 C5). Returns the updated item, or
    None if the item is missing or not currently held."""
    released_by = (released_by or "").strip()
    if not released_by:
        raise ValueError("release_hold requires non-empty released_by")
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        with _write(conn):
            cur = conn.execute(
                "UPDATE review_queue SET status = 'pending', decided_by = ?, "
                "decided_at = ?, updated_at = ? "
                "WHERE item_id = ? AND status = 'held'",
                (released_by, ts, ts, item_id),
            )
            if cur.rowcount != 1:
                return None
            row = conn.execute(
                "SELECT * FROM review_queue WHERE item_id = ?", (item_id,)
            ).fetchone()
    return _row_to_item(row) if row is not None else None


def set_merge_policy_binding(
    universe_dir: str | Path,
    *,
    branch_def_id: str,
    merge_policy: str = "manual",
    founder_oauth_per_merge: bool = False,
    merge_timer_delay_s: float = 0.0,
    bound_by: str,
    now: float | None = None,
) -> dict[str, Any]:
    """Owner-bind the governing merge policy for a branch (remix) design (Codex
    R6 C2). The present node resolves policy from HERE, never from the packet.
    Validates the timer delay (finite, non-negative). Raises on empty
    branch_def_id / bound_by."""
    bdid = (branch_def_id or "").strip()
    if not bdid:
        raise ValueError("set_merge_policy_binding requires non-empty branch_def_id")
    bound_by = (bound_by or "").strip()
    if not bound_by:
        raise ValueError("set_merge_policy_binding requires non-empty bound_by")
    policy_str = (merge_policy or "manual").strip().lower() or "manual"
    oauth_int = 1 if founder_oauth_per_merge else 0
    try:
        delay = float(merge_timer_delay_s if merge_timer_delay_s is not None else 0.0)
    except (TypeError, ValueError):
        raise ValueError("merge_timer_delay_s must be a finite non-negative number") from None
    if not math.isfinite(delay) or delay < 0:
        raise ValueError("merge_timer_delay_s must be finite and non-negative")
    initialize_review_queue_db(universe_dir)
    ts = now if now is not None else time.time()
    with _connect(universe_dir) as conn:
        with _write(conn):
            conn.execute(
                """
                INSERT INTO merge_policy_bindings (
                    branch_def_id, merge_policy, founder_oauth_per_merge,
                    merge_timer_delay_s, bound_by, bound_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(branch_def_id) DO UPDATE SET
                    merge_policy = excluded.merge_policy,
                    founder_oauth_per_merge = excluded.founder_oauth_per_merge,
                    merge_timer_delay_s = excluded.merge_timer_delay_s,
                    bound_by = excluded.bound_by,
                    bound_at = excluded.bound_at
                """,
                (bdid, policy_str, oauth_int, delay, bound_by, ts),
            )
    return {
        "branch_def_id": bdid,
        "merge_policy": policy_str,
        "founder_oauth_per_merge": bool(oauth_int),
        "merge_timer_delay_s": delay,
        "bound_by": bound_by,
        "bound_at": ts,
    }


def resolve_merge_policy_binding(
    universe_dir: str | Path, *, branch_def_id: str
) -> dict[str, Any]:
    """Resolve the OWNER-BOUND governing merge policy for a branch design (Codex
    R6 C2). Returns the safe default (manual, no OAuth, no delay) when unbound —
    NEVER trusts a packet-supplied policy."""
    default = {
        "merge_policy": "manual",
        "founder_oauth_per_merge": False,
        "merge_timer_delay_s": 0.0,
        "bound": False,
    }
    bdid = (branch_def_id or "").strip()
    if not bdid:
        return default
    initialize_review_queue_db(universe_dir)
    with _connect(universe_dir) as conn:
        row = conn.execute(
            "SELECT merge_policy, founder_oauth_per_merge, merge_timer_delay_s "
            "FROM merge_policy_bindings WHERE branch_def_id = ?",
            (bdid,),
        ).fetchone()
    if row is None:
        return default
    return {
        "merge_policy": row["merge_policy"],
        "founder_oauth_per_merge": bool(row["founder_oauth_per_merge"]),
        "merge_timer_delay_s": row["merge_timer_delay_s"],
        "bound": True,
    }


__all__ = [
    "review_queue_db_path",
    "initialize_review_queue_db",
    "VALID_STATUSES",
    "VERIFY_PASS",
    "VERIFY_FAIL",
    "VERIFY_UNKNOWN",
    "InvalidReviewTransition",
    "OwnerRequired",
    "MergeInProgress",
    "ReviewHeadChanged",
    "enqueue_pr",
    "get_item",
    "list_queue",
    "approve_item",
    "reshape_item",
    "reject_item",
    "hold_item",
    "release_hold",
    "list_pending_reshape_routes",
    "claim_for_merge",
    "release_merge_claim",
    "mark_merged",
    "has_fresh_merge_approval",
    "consume_merge_approval",
    "set_merge_policy_binding",
    "resolve_merge_policy_binding",
]
