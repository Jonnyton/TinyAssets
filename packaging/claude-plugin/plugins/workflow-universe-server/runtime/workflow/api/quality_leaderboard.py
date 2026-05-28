"""Quality leaderboard + parent-selection — DESIGN-008 (user-buildable selectors).

PR-123 originally shipped this surface with a platform-opinionated
scoring formula baked into Python — weights for runs / forks /
judgments / recency / gates / safe_to_publish all chosen by the
platform. PR #978 tried to patch a bug in that formula (timestamp
coercion); the host closed PR #978 because patching the formula
entrenches the wrong architecture.

DESIGN-008 (host reframe 2026-05-21): selection logic is per-Goal
**user-buildable**. The substrate collects signals; a Goal-bound
**selector branch** synthesizes them into rankings. Selector
branches are normal published Workflow branches conforming to the
contract documented in
``drafts/concepts/selector-branch-contract.md``.

This module now:

* Collects signals per candidate branch (unchanged from the prior
  shape — these are inputs to the selector, not opinion).
* Resolves the Goal's selector branch_version (explicit binding via
  ``set_selector`` OR platform default, see
  ``workflow.api.selector_dispatch``).
* Dispatches the selector synchronously (with timeout) via
  ``execute_branch_version_async`` + ``wait_for``.
* Parses + validates the ``ranked_entries`` output.
* Returns the ranked leaderboard.

What was DELETED in DESIGN-008
------------------------------

* ``W_JUDGMENT`` / ``W_RUNS`` / ``W_FORKS`` / ``W_RECENCY`` /
  ``W_GATE`` / ``W_SAFE_PUBLISH`` / ``W_FAILED_PENALTY`` constants.
  Weights now live in the default selector's prompt.
* ``RECENCY_HALFLIFE_DAYS``, ``JUDGMENT_MAX_SCALE``. Same story.
* ``_score_components`` — the per-term formula application.
* ``_entry_sort_key`` — sort order is selector-emitted ``score``
  desc; ties tolerated.
* ``_formula_disclosure`` — there's no platform formula to
  disclose. Selectors disclose their own logic in their prompt.
* ``_build_rationale`` — rationale is selector-emitted per entry.
* ``_timestamp_to_epoch`` (the PR #978 patch) — never landed on
  main, but the original ``float(...)`` coercion that crashed on
  ISO strings is also gone because signals are now passed as a
  list of dicts to the selector branch, not consumed by Python
  scoring code.

Visibility / auth-boundary contract (preserved from round-2)
------------------------------------------------------------

``viewer`` is the actor identity for which visibility is resolved
and MUST be derived server-side by the caller (never accepted from
an MCP input). Pass an empty string for the strictly-public view.
Private branches authored by the viewer are surfaced in the
candidate set passed to the selector; private branches authored by
other actors are filtered out. The selector's ranking output is
relative to that visibility-bounded candidate set.

Cost note
---------

Each leaderboard build now triggers one LLM call (the selector
run). The old formula was free. Acceptable trade for the
architectural win; a future slice may add caching keyed by
(goal_id, candidate fingerprint) for N minutes.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Module-level import so test code can monkeypatch
# ``workflow.api.quality_leaderboard.dispatch_selector``.
from workflow.api.selector_dispatch import dispatch_selector

logger = logging.getLogger(__name__)


# Numeric judgment-tag pattern: ``key:N`` where N is integer/float.
# Examples that match: ``quality:8``, ``quality:8.2``, ``novelty:7.5``,
# ``risk:3``. Negative numbers and tags without ``:N`` are ignored.
# Preserved from the round-1 implementation because it's pure parsing,
# not opinion: ``_judgment_stats`` produces a signal the selector
# branches consume.
_NUMERIC_TAG_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_\-]*)\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*$"
)

# Tag names that contribute to the average quality signal. Tags outside
# this set are bucketed under ``other_numeric_tags`` for the selector
# to surface or ignore at its discretion.
_QUALITY_TAG_KEYS = frozenset({"quality", "novelty", "score"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_quality_leaderboard(
    base_path: str | Path,
    *,
    goal_id: str,
    viewer: str,
    now: float | None = None,
    provider_call: Any = None,
) -> dict[str, Any]:
    """Compute the ranked list of branches bound to ``goal_id``.

    DESIGN-008: dispatches the Goal's selector branch (explicit
    binding or platform default) over the collected signals and
    returns its ``ranked_entries`` as the leaderboard.

    Returns one of:

    Success::

        {
            "ok": True,
            "goal_id": "...",
            "goal": <goal-row | None>,
            "entries": [
                {
                    "rank": 1,
                    "branch_def_id": "...",
                    "branch_version_id": "...",
                    "name": "...",
                    "author": "...",
                    "score": <float>,
                    "rationale": "<selector-emitted explanation>",
                    "signals": {<the signal map for transparency>},
                },
                ...
            ],
            "selector": {
                "branch_version_id": "...",
                "source": "goal_binding" | "platform_default",
                "run_id": "...",
            },
            "generated_at": <unix>,
        }

    Selector failure (selector unresolvable, dispatch failed,
    timeout, invalid output)::

        {
            "ok": False,
            "error_kind": "<see selector_dispatch error_kinds>",
            "error": "...",
            "goal_id": "...",
            "goal": <goal-row | None>,
            "entries": [],
            "selector": {...partial selector context...},
            "generated_at": <unix>,
        }

    Visibility: ``viewer`` is the server-derived actor identity.
    Empty string means strictly-public. Private branches authored by
    other actors are filtered before the selector sees them.

    ``base_path`` is the daemon's data root.
    """
    if now is None:
        import time as _time
        now = _time.time()

    goal_row = _safe_get_goal(base_path, goal_id)

    from workflow.daemon_server import list_branch_definitions
    branches = list_branch_definitions(
        base_path,
        goal_id=goal_id,
        viewer=viewer,
        include_private=False,
    )

    # Collect signals per candidate. The signal shape is the same as
    # the round-1 implementation — those primitives are inputs, not
    # opinion. The selector branch consumes them.
    candidates: list[dict[str, Any]] = []
    signals_by_branch: dict[str, dict[str, Any]] = {}
    branch_meta_by_id: dict[str, dict[str, Any]] = {}
    for branch in branches:
        bid = branch["branch_def_id"]
        signals = _collect_signals_for_branch(
            base_path, branch, now=now, viewer=viewer,
        )
        signals_by_branch[bid] = signals
        latest_bvid = _latest_active_version_id(base_path, bid)
        candidate = {
            "branch_def_id": bid,
            "branch_version_id": latest_bvid,
            "name": branch.get("name", ""),
            "author": branch.get("author", ""),
            "description": branch.get("description", ""),
            "signals": signals,
        }
        candidates.append(candidate)
        branch_meta_by_id[bid] = {
            "name": branch.get("name", ""),
            "author": branch.get("author", ""),
            "description": branch.get("description", ""),
            "created_at": _timestamp_seconds(branch.get("created_at")),
            "updated_at": _timestamp_seconds(branch.get("updated_at")),
            "branch_version_id": latest_bvid,
        }

    # Dispatch the selector. Empty candidate set short-circuits to
    # an empty leaderboard without burning an LLM call.
    dispatch_result = dispatch_selector(
        base_path,
        goal_id=goal_id,
        candidate_branches=candidates,
        actor=viewer or "anonymous",
        provider_call=provider_call,
    )

    if not dispatch_result.get("ok"):
        return {
            "ok": False,
            "error_kind": dispatch_result.get(
                "error_kind", "selector_invalid_output",
            ),
            "error": dispatch_result.get("error", ""),
            "goal_id": goal_id,
            "goal": goal_row,
            "entries": [],
            "selector": {
                "branch_version_id": dispatch_result.get(
                    "branch_version_id",
                ),
                "run_id": dispatch_result.get("run_id"),
            },
            "generated_at": now,
        }

    raw_entries = dispatch_result.get("ranked_entries") or []
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    phantom_ids: list[str] = []
    # P1.A (DESIGN-008 round 3): track selector-emitted version_id
    # mismatches against the candidate set's authoritative version.
    # The selector's value is always ignored; this list surfaces the
    # spoof attempts so audit tools can detect a misbehaving /
    # adversarial selector without scraping logs.
    selector_bvid_spoofs: list[dict[str, str]] = []
    # Rank is assigned post-filter so phantom/dupe/blank rows do
    # not leave gaps in the user-facing rank sequence.
    for raw in raw_entries:
        bid = (raw.get("branch_def_id") or "").strip()
        if not bid or bid in seen:
            # Skip dupes / blanks defensively — the selector should
            # not emit them, but a misbehaving selector shouldn't
            # corrupt the response.
            continue
        # P1.2 (DESIGN-008 round 2): selector output can fabricate
        # branch_def_ids — including private ones the viewer cannot
        # see — and inject them into the leaderboard. Reject any
        # branch_def_id that was not in the input candidate set.
        # ``branch_meta_by_id`` is the authoritative source of
        # visible candidates (already filtered by viewer +
        # include_private=False at list_branch_definitions).
        if bid not in branch_meta_by_id:
            phantom_ids.append(bid)
            continue
        seen.add(bid)
        meta = branch_meta_by_id[bid]
        signals = signals_by_branch.get(bid, {})
        # P1.A (DESIGN-008 round 3): the selector MUST NOT influence
        # which branch_version_id surfaces in the leaderboard. The
        # candidate set already carries the authoritative latest
        # active version per def_id (resolved from
        # ``branch_versions.status='active'`` at signal collection
        # time). Trusting ``raw.get("branch_version_id")`` would let
        # a selector return a real visible def_id paired with a
        # private / rolled-back / fabricated version id, and the
        # chatbot would surface it via recommend_parent_for_fork.
        # The selector's emitted version_id is ignored — only the
        # candidate set's authoritative bvid is surfaced. A future
        # slice may allow selectors to pin a specific historical
        # version, but it must come through a separate validated
        # mechanism (e.g. selector claims a version, substrate
        # checks visibility + status='active'), not blind passthrough.
        spoof_attempt = (raw.get("branch_version_id") or "").strip()
        authoritative_bvid = (meta.get("branch_version_id") or "")
        if spoof_attempt and spoof_attempt != authoritative_bvid:
            logger.warning(
                "selector emitted branch_version_id=%r for "
                "branch_def_id=%r that disagrees with the "
                "authoritative active version %r (goal=%s "
                "selector=%s); selector value ignored",
                spoof_attempt, bid, authoritative_bvid, goal_id,
                dispatch_result.get("branch_version_id"),
            )
            selector_bvid_spoofs.append({
                "branch_def_id": bid,
                "selector_emitted": spoof_attempt,
                "authoritative": authoritative_bvid,
            })
        entries.append({
            "branch_def_id": bid,
            "branch_version_id": authoritative_bvid,
            "name": meta.get("name", ""),
            "author": meta.get("author", ""),
            "description": meta.get("description", ""),
            "created_at": _timestamp_seconds(meta.get("created_at")),
            "updated_at": _timestamp_seconds(meta.get("updated_at")),
            "score": float(raw.get("score") or 0.0),
            "rationale": raw.get("rationale", ""),
            # Pass the signal map through so the chatbot can surface
            # "why this ranked here" without re-querying storage.
            "signals": signals,
        })
    # Assign ranks now that phantom entries have been filtered out.
    for rank_idx, entry in enumerate(entries, start=1):
        entry["rank"] = rank_idx
    # Emit a structured warning when the selector tried to inject
    # phantom IDs. The operator can spot a misbehaving (or
    # adversarial) selector in their logs / event feed.
    if phantom_ids:
        logger.warning(
            "selector fabricated %d phantom branch_def_id(s) for goal=%s "
            "selector=%s: %s — entries dropped",
            len(phantom_ids),
            goal_id,
            dispatch_result.get("branch_version_id"),
            phantom_ids,
        )

    return {
        "ok": True,
        "goal_id": goal_id,
        "goal": goal_row,
        "entries": entries,
        # P1.2 — surface phantom branch_def_id rejections in the
        # structured payload so programmatic consumers (and audit
        # tools) can detect a misbehaving selector without scraping
        # logs. Empty list when the selector is well-behaved.
        "phantom_branch_def_ids": phantom_ids,
        # P1.A (round 3) — surface selector-emitted branch_version_id
        # spoof attempts. Each entry: {branch_def_id, selector_emitted,
        # authoritative}. Empty list when the selector is well-behaved.
        # Selector values are ALWAYS ignored regardless; this is audit.
        "selector_bvid_spoofs": selector_bvid_spoofs,
        "selector": {
            "branch_version_id": dispatch_result.get("branch_version_id"),
            "source": dispatch_result.get("source"),
            "run_id": dispatch_result.get("run_id"),
            # P1.C (round 4) — when the bound selector_branch_version_id
            # was inactive at dispatch time, the substrate fell back to
            # the platform default. ``fellback_from`` carries the old
            # binding + reason so the chatbot can prompt the operator
            # to re-bind. None when no fallback happened.
            "fellback_from": dispatch_result.get("fellback_from"),
        },
        "generated_at": now,
    }


def recommend_parent_for_fork(
    base_path: str | Path,
    *,
    goal_id: str,
    viewer: str,
    now: float | None = None,
    provider_call: Any = None,
) -> dict[str, Any]:
    """Return the top selector-ranked entry plus its rationale.

    Returns one of:

    Success with parent::

        {
            "ok": True,
            "goal_id": "...",
            "recommended_parent": <entry>,
            "rationale": "<selector-emitted>",
            "leaderboard_size": <int>,
            "selector": {...},
            "generated_at": <unix>,
        }

    No parent (no candidates / empty leaderboard)::

        {
            "ok": True,
            "goal_id": "...",
            "recommended_parent": None,
            "rationale": "<friendly explanation>",
            "leaderboard_size": 0,
            ...
        }

    Selector failure surfaces the same error_kind as
    :func:`build_quality_leaderboard`.
    """
    board = build_quality_leaderboard(
        base_path,
        goal_id=goal_id,
        viewer=viewer,
        now=now,
        provider_call=provider_call,
    )
    if not board.get("ok"):
        return {
            "ok": False,
            "error_kind": board.get("error_kind"),
            "error": board.get("error", ""),
            "goal_id": goal_id,
            "recommended_parent": None,
            "rationale": "",
            "leaderboard_size": 0,
            "selector": board.get("selector") or {},
            "generated_at": board.get("generated_at"),
        }
    entries = board["entries"]
    if not entries:
        return {
            "ok": True,
            "goal_id": goal_id,
            "recommended_parent": None,
            "rationale": (
                "No Branch is bound to this Goal yet. Create the first "
                "Branch via extensions action=build_branch goal_id=… or "
                "fork from a peer Goal's leaderboard."
            ),
            "leaderboard_size": 0,
            "selector": board.get("selector") or {},
            "generated_at": board["generated_at"],
        }
    top = entries[0]
    rationale = top.get("rationale") or ""
    if not rationale:
        rationale = (
            f"'{top.get('name') or top['branch_def_id']}' "
            f"(#{top['branch_def_id']}) ranked first of "
            f"{len(entries)} bound Branches with score "
            f"{top.get('score', 0.0):.2f}. (Selector did not provide "
            "a per-entry rationale.)"
        )
    return {
        "ok": True,
        "goal_id": goal_id,
        "recommended_parent": top,
        "rationale": rationale,
        "leaderboard_size": len(entries),
        "selector": board.get("selector") or {},
        "generated_at": board["generated_at"],
    }


# ---------------------------------------------------------------------------
# Signal collection (preserved — these are selector inputs, not opinion)
# ---------------------------------------------------------------------------


def _collect_signals_for_branch(
    base_path: str | Path,
    branch: dict[str, Any],
    *,
    now: float,
    viewer: str,
) -> dict[str, Any]:
    bid = branch["branch_def_id"]
    goal_id = branch.get("goal_id") or ""

    run_stats = _run_stats(base_path, bid)
    judgment_stats = _judgment_stats(base_path, bid)
    fork_count = _fork_count(base_path, bid, viewer=viewer)
    gate_rung_top = _gate_rung_top(base_path, bid, goal_id)
    safe_to_publish = _safe_to_publish(branch)

    last_ok = run_stats["last_successful_run_at"]
    if last_ok and last_ok > 0:
        age_days = max(0.0, (now - last_ok) / 86400.0)
    else:
        age_days = None

    return {
        "total_run_count": run_stats["total"],
        "completed_run_count": run_stats["completed"],
        "failed_run_count": run_stats["failed"],
        "last_successful_run_at": last_ok,
        "age_days_since_success": age_days,
        "judgment_count": judgment_stats["count"],
        "judgment_score_avg": judgment_stats["score_avg"],
        "judgment_score_samples": judgment_stats["score_samples"],
        "other_numeric_tags": judgment_stats["other_numeric_tags"],
        "fork_count": fork_count,
        "gate_rung_top": gate_rung_top,
        "has_gate_rung": gate_rung_top is not None,
        "safe_to_publish": safe_to_publish,
    }


def _run_stats(base_path: str | Path, branch_def_id: str) -> dict[str, Any]:
    """Aggregate counts + last_successful_run_at directly against runs DB."""
    from workflow.runs import _connect, initialize_runs_db

    initialize_runs_db(base_path)
    with _connect(base_path) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'failed'    THEN 1 ELSE 0 END) AS failed
            FROM runs
            WHERE branch_def_id = ?
            """,
            (branch_def_id,),
        ).fetchone()
        finished_rows = conn.execute(
            """
            SELECT finished_at
            FROM runs
            WHERE branch_def_id = ? AND status = 'completed'
            """,
            (branch_def_id,),
        ).fetchall()
    if row is None:
        return {
            "total": 0, "completed": 0, "failed": 0,
            "last_successful_run_at": 0.0,
        }
    # SQLite type-affinity permits mixed REAL/TEXT values in finished_at.
    # Normalize in Python before max selection so an ISO text row cannot win
    # lexicographically over a later numeric timestamp.
    last_ok = max(
        (_timestamp_seconds(finished_row["finished_at"]) for finished_row in finished_rows),
        default=0.0,
    )
    return {
        "total": int(row["total"] or 0),
        "completed": int(row["completed"] or 0),
        "failed": int(row["failed"] or 0),
        "last_successful_run_at": last_ok,
    }


def _timestamp_seconds(value: Any) -> float:
    """Normalize Unix seconds or ISO timestamps to epoch seconds."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _judgment_stats(
    base_path: str | Path, branch_def_id: str,
) -> dict[str, Any]:
    """Parse numeric scores out of judgment tags scoped to this branch."""
    from workflow.runs import _connect, initialize_runs_db
    from workflow.storage import _json_loads

    initialize_runs_db(base_path)
    with _connect(base_path) as conn:
        rows = conn.execute(
            """
            SELECT j.tags_json
              FROM run_judgments j
              JOIN runs r ON r.run_id = j.run_id
             WHERE r.branch_def_id = ?
            """,
            (branch_def_id,),
        ).fetchall()
    count = len(rows)
    quality_scores: list[float] = []
    other_counts: dict[str, int] = {}
    for row in rows:
        tags = _json_loads(row["tags_json"], []) or []
        if not isinstance(tags, list):
            continue
        for tag in tags:
            if not isinstance(tag, str):
                continue
            m = _NUMERIC_TAG_RE.match(tag)
            if not m:
                continue
            key = m.group(1).lower()
            try:
                value = float(m.group(2))
            except (TypeError, ValueError):
                continue
            if key in _QUALITY_TAG_KEYS:
                quality_scores.append(value)
            else:
                other_counts[key] = other_counts.get(key, 0) + 1
    score_avg = (
        sum(quality_scores) / len(quality_scores)
        if quality_scores else None
    )
    return {
        "count": count,
        "score_avg": (round(score_avg, 4) if score_avg is not None else None),
        "score_samples": len(quality_scores),
        "other_numeric_tags": other_counts,
    }


def _fork_count(
    base_path: str | Path,
    branch_def_id: str,
    *,
    viewer: str,
) -> int:
    """Count descendants the ``viewer`` can see.

    Same visibility-respecting query as the round-1 implementation
    (the auth-boundary contract from PR-970 round 2 P1.2). The
    selector branch consumes the count; visibility filtering happens
    here.
    """
    from workflow.storage import _connect

    if viewer:
        sql = (
            "SELECT COUNT(*) AS n "
            "FROM branch_definitions "
            "WHERE (parent_def_id = ? OR fork_from = ?) "
            "AND (visibility = 'public' OR author = ?)"
        )
        params: tuple[Any, ...] = (branch_def_id, branch_def_id, viewer)
    else:
        sql = (
            "SELECT COUNT(*) AS n "
            "FROM branch_definitions "
            "WHERE (parent_def_id = ? OR fork_from = ?) "
            "AND visibility = 'public'"
        )
        params = (branch_def_id, branch_def_id)
    with _connect(base_path) as conn:
        row = conn.execute(sql, params).fetchone()
    return int(row["n"] or 0) if row is not None else 0


def _gate_rung_top(
    base_path: str | Path,
    branch_def_id: str,
    goal_id: str,
) -> str | None:
    """Return the highest active gate rung for (branch, goal), or None.

    Lexicographically-greatest among non-retracted claims.
    Goal-ladder-aware ordering is a follow-on once ladder shape is
    stable per-Goal.
    """
    if not goal_id:
        return None
    from workflow.daemon_server import list_gate_claims

    try:
        claims = list_gate_claims(
            base_path,
            branch_def_id=branch_def_id,
            include_retracted=False,
            limit=200,
        )
    except Exception:
        return None
    candidates = [
        (c.get("rung_key") or "")
        for c in claims
        if (c.get("goal_id") or "") == goal_id
        and not c.get("retracted_at")
    ]
    candidates = [r for r in candidates if r]
    if not candidates:
        return None
    return max(candidates)


def _safe_to_publish(branch: dict[str, Any]) -> bool:
    """Best-effort lookup of a Loop-2-style next_action_packet flag."""
    stats = branch.get("stats")
    if not isinstance(stats, dict):
        return False
    packet = stats.get("next_action_packet")
    if not isinstance(packet, dict):
        return False
    return bool(packet.get("safe_to_publish"))


def _safe_get_goal(
    base_path: str | Path, goal_id: str,
) -> dict[str, Any] | None:
    from workflow.daemon_server import get_goal
    try:
        return get_goal(base_path, goal_id=goal_id)
    except KeyError:
        return None
    except Exception:
        return None


def _latest_active_version_id(
    base_path: str | Path, branch_def_id: str,
) -> str:
    """Return the newest active ``branch_version_id`` for the def, or "".

    Returns ``""`` when the branch has not been published yet OR
    every published version has been rolled back / superseded.
    Matches the PR-127 round-2 active-only filter on
    ``canonical_dispatch._latest_published_version_id``.
    """
    if not branch_def_id:
        return ""
    try:
        from workflow.branch_versions import list_branch_versions
        versions = list_branch_versions(
            base_path, branch_def_id=branch_def_id, limit=50,
        )
    except Exception:
        return ""
    for v in versions:
        if getattr(v, "status", "active") == "active":
            return v.branch_version_id or ""
    return ""


__all__ = [
    "build_quality_leaderboard",
    "recommend_parent_for_fork",
]
