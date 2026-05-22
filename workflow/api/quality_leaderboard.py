"""Quality leaderboard + parent-selection — PR-123 substrate (M2).

Surfaces, for any Goal that has competing Branch entries:

- ``quality_leaderboard(goal_id)`` — ranked list of Branches bound to
  the Goal, with the per-entry signal summary that produced the score.
- ``recommended_parent_for_fork(goal_id)`` — the top entry plus a
  human-readable rationale string, intended as a thin handle for the
  community designer asking "what should I fork from?".

Design source: wiki page
``pages/patch-requests/pr-123-goal-archive-with-parent-selection-...``
on the live MCP brain. The PLAN Goals & Gates module names this
surface as ``archive_consultation parent-rank scoring formula`` and
flags it as **open evolution** — a follow-on may turn the scoring
formula into an evolvable Workflow node so the community can iterate
on weights through autoresearch rather than asking the platform to
ship "the right" constants.

This slice is **best-effort v1**: ranking is signal-driven, not
ground-truth-driven. The formula constants are surfaced in every
response under ``formula`` so reviewers can audit and tune them
without re-reading source.

Goal-generic by design — same primitive works for patch-loops AND
fantasy-writing AND recipe-trackers AND any community. No
Loop-2-specific assumptions.

Signals (all read from existing storage; no new tables in this slice):

- ``completed_run_count`` — runs with ``status='completed'``.
- ``failed_run_count`` — runs with ``status='failed'`` (penalty).
- ``total_run_count`` — full count regardless of status.
- ``last_successful_run_at`` — max ``finished_at`` of completed runs.
- ``recency_decay`` — ``exp(-age_days/30)`` against the wall clock;
  0 when the branch never produced a successful run.
- ``judgment_count`` — rows in ``run_judgments`` joined via ``runs``.
- ``judgment_score_avg`` — mean of numeric scores parsed from
  judgment tags like ``quality:8.2``, ``novelty:7``, ``risk:3``.
  None when no numeric tags exist (the signal contributes 0 to the
  score in that case rather than NaN-propagating).
- ``fork_count`` — branches whose ``parent_def_id`` or ``fork_from``
  references this branch. Community votes with their forks.
- ``gate_rung_top`` — the lexicographically-greatest active
  ``rung_key`` from ``gate_claims`` for this (branch, goal).
- ``safe_to_publish`` — best-effort read of
  ``branch.stats.next_action_packet.safe_to_publish``. The packet
  shape isn't on-disk-stable yet; if absent, the signal contributes 0.

Score formula (weights surfaced in the response so they are auditable):

  score = 3.0 * normalized_judgment_score
        + 1.5 * log1p(completed_run_count)
        + 2.0 * log1p(fork_count)
        + 2.0 * recency_decay
        + 1.0 * has_gate_rung
        + 1.5 * safe_to_publish
        - 1.0 * log1p(failed_run_count)

``normalized_judgment_score`` is ``judgment_score_avg / 10.0`` (DGM
scores are on a 0-10 scale) clamped to [0, 1] so the term is bounded.
log1p bounds the impact of high-volume entries; recency / gate /
safe_to_publish are already [0, 1].

Tie-breaks: higher ``last_successful_run_at`` wins; then higher
``created_at`` (newer entry); then ``branch_def_id`` for stability.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Tunable weights — surfaced in the response under ``formula``
# ---------------------------------------------------------------------------

W_JUDGMENT = 3.0
W_RUNS = 1.5
W_FORKS = 2.0
W_RECENCY = 2.0
W_GATE = 1.0
W_SAFE_PUBLISH = 1.5
W_FAILED_PENALTY = 1.0

RECENCY_HALFLIFE_DAYS = 30.0
JUDGMENT_MAX_SCALE = 10.0  # DGM-style 0-10

# Numeric judgment-tag pattern: ``key:N`` where N is integer/float.
# Examples that match: ``quality:8``, ``quality:8.2``, ``novelty:7.5``,
# ``risk:3``. Negative numbers and tags without ``:N`` are ignored.
_NUMERIC_TAG_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_\-]*)\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*$"
)

# Tag names that contribute to the average quality signal. Tags outside
# this set are recorded under ``other_numeric_tags`` so the chatbot can
# surface them without polluting the headline score.
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
) -> dict[str, Any]:
    """Compute the ranked list of branches bound to ``goal_id``.

    Returns ``{"goal_id": ..., "goal": <row | None>, "entries": [...],
    "formula": {...}, "generated_at": ...}``.

    Visibility / auth-boundary contract (round-2 P1.1 fix)
    ------------------------------------------------------
    ``viewer`` is the actor identity for which visibility is resolved
    and MUST be derived server-side by the caller (never accepted from
    an MCP input). Pass an empty string for the "strictly public" view
    (no private branches included). The function does NOT accept an
    ``include_private`` knob — that surface was caller-controllable in
    round-1 and let an MCP caller flip visibility by passing
    ``force=true``. To inspect private branches from a host/internal
    script, build the response directly via the storage helpers; this
    public entry point ALWAYS applies the public-or-author-owned
    visibility filter.

    Each entry is::

        {
            "rank":             1,
            "branch_def_id":    "...",
            "name":             "...",
            "description":      "...",
            "author":           "...",
            "created_at":       <unix>,
            "updated_at":       <unix>,
            "score":            <float>,
            "signals":          {<see Signals section above>},
            "score_components": {<per-term contribution to score>},
        }

    The function returns the ranked entries even when the Goal does not
    exist or has no bound branches — the chatbot can render a friendly
    "no entries yet" page from ``entries == []``.

    ``base_path`` is the daemon's data root (matches the rest of the
    storage layer).
    """
    if now is None:
        import time as _time
        now = _time.time()

    goal_row = _safe_get_goal(base_path, goal_id)

    from workflow.daemon_server import list_branch_definitions
    # P1.1 fix — visibility is ALWAYS the public-or-author-owned filter.
    # ``include_private`` is hard-False at this seam: there's no MCP
    # surface that legitimately needs to bypass this filter, and round-1
    # let a caller-supplied ``force=true`` flip it. If a future internal
    # caller genuinely needs every row, it must reach for the storage
    # helpers directly with explicit ``include_private=True`` — that
    # path is host/internal-only and not reachable from MCP.
    branches = list_branch_definitions(
        base_path,
        goal_id=goal_id,
        viewer=viewer,
        include_private=False,
    )

    entries: list[dict[str, Any]] = []
    for branch in branches:
        signals = _collect_signals_for_branch(
            base_path, branch, now=now, viewer=viewer,
        )
        components = _score_components(signals)
        score = sum(components.values())
        entries.append({
            "branch_def_id": branch["branch_def_id"],
            "name": branch.get("name", ""),
            "description": branch.get("description", ""),
            "author": branch.get("author", ""),
            "created_at": _timestamp_seconds(branch.get("created_at")),
            "updated_at": _timestamp_seconds(branch.get("updated_at")),
            "score": round(score, 4),
            "signals": signals,
            "score_components": {
                k: round(v, 4) for k, v in components.items()
            },
        })

    # Two-pass stable sort. First pass: branch_def_id ascending (string
    # compare). Second pass: primary keys with reverse=True. Python's
    # sort is stable, so the secondary key from the first pass survives
    # within ties of the primary sort.
    entries.sort(key=lambda e: e.get("branch_def_id", ""))
    entries.sort(key=_entry_sort_key, reverse=True)
    for rank, entry in enumerate(entries, start=1):
        entry["rank"] = rank

    return {
        "goal_id": goal_id,
        "goal": goal_row,
        "entries": entries,
        "formula": _formula_disclosure(),
        "generated_at": now,
    }


def recommend_parent_for_fork(
    base_path: str | Path,
    *,
    goal_id: str,
    viewer: str,
    now: float | None = None,
) -> dict[str, Any]:
    """Return the top leaderboard entry plus a human-readable rationale.

    Returns ``{"goal_id": ..., "recommended_parent": <entry | None>,
    "rationale": "...", "leaderboard_size": <int>, "generated_at": ...}``.

    Visibility contract matches :func:`build_quality_leaderboard` —
    ``viewer`` must be server-derived; private branches the viewer does
    not own are excluded.

    When no branch is bound to the Goal the response carries
    ``recommended_parent=None`` and a rationale explaining that no
    parent exists yet — the chatbot should propose "create the first
    branch" rather than "fork from".
    """
    board = build_quality_leaderboard(
        base_path,
        goal_id=goal_id,
        viewer=viewer,
        now=now,
    )
    entries = board["entries"]
    if not entries:
        return {
            "goal_id": goal_id,
            "recommended_parent": None,
            "rationale": (
                "No Branch is bound to this Goal yet. Create the first "
                "Branch via extensions action=build_branch goal_id=… or "
                "fork from a peer Goal's leaderboard."
            ),
            "leaderboard_size": 0,
            "generated_at": board["generated_at"],
        }
    top = entries[0]
    return {
        "goal_id": goal_id,
        "recommended_parent": top,
        "rationale": _build_rationale(top, leaderboard_size=len(entries)),
        "leaderboard_size": len(entries),
        "generated_at": board["generated_at"],
    }


# ---------------------------------------------------------------------------
# Signal collection
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
    # P1.2 fix — fork count respects viewer visibility. Counting raw
    # descendant rows would leak existence of private forks (the row
    # was hidden from the listing but the aggregate count exposed it).
    fork_count = _fork_count(base_path, bid, viewer=viewer)
    gate_rung_top = _gate_rung_top(base_path, bid, goal_id)
    safe_to_publish = _safe_to_publish(branch)

    last_ok = run_stats["last_successful_run_at"]
    if last_ok and last_ok > 0:
        age_days = max(0.0, (now - last_ok) / 86400.0)
        recency_decay = math.exp(-age_days / RECENCY_HALFLIFE_DAYS)
    else:
        age_days = None
        recency_decay = 0.0

    return {
        "total_run_count": run_stats["total"],
        "completed_run_count": run_stats["completed"],
        "failed_run_count": run_stats["failed"],
        "last_successful_run_at": last_ok,
        "age_days_since_success": age_days,
        "recency_decay": round(recency_decay, 4),
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
    """Aggregate counts + last_successful_run_at directly against runs DB.

    A direct SQL aggregate is cheaper than fetching every row via
    ``list_runs`` — this is invoked once per branch on the leaderboard
    and a Goal can carry 50+ branches.
    """
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
    successful_finished_at = [
        _timestamp_seconds(finished_row["finished_at"])
        for finished_row in finished_rows
    ]
    return {
        "total": int(row["total"] or 0),
        "completed": int(row["completed"] or 0),
        "failed": int(row["failed"] or 0),
        "last_successful_run_at": max(successful_finished_at, default=0.0),
    }


def _timestamp_seconds(value: Any) -> float:
    """Normalize storage timestamps to Unix seconds.

    Older rows use Unix floats while runtime helpers can persist ISO-8601
    strings. Invalid or absent timestamps sort as 0.0 instead of crashing
    the leaderboard selector.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            pass
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return 0.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    return 0.0


def _judgment_stats(
    base_path: str | Path, branch_def_id: str,
) -> dict[str, Any]:
    """Parse numeric scores out of judgment tags scoped to this branch.

    Judgments are free-text + tags; the leaderboard reads ``tags_json``
    looking for ``key:N`` patterns where ``key`` is in
    ``_QUALITY_TAG_KEYS`` for the headline score. Other numeric tags are
    bucketed under ``other_numeric_tags`` for surface-level reporting
    but don't contribute to the score in this slice.
    """
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

    Either ``parent_def_id`` or ``fork_from`` may reference this branch
    — count rows whose either column matches AND that pass the same
    visibility filter ``list_branch_definitions`` applies (public OR
    authored by the viewer). This closes the round-2 P1.2 finding: a
    naive raw count exposed the existence of private descendant rows
    even when the rows themselves were hidden from the listing.

    Passing ``viewer=""`` matches the "strictly public" semantics —
    counts only public descendants, never private ones.
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

    "Highest" in this slice is lexicographically-greatest ``rung_key``
    among non-retracted claims. Goal-ladder-aware ordering is a follow-on
    once the ladder shape is stable per-Goal.
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
    """Best-effort lookup of a Loop-2-style next_action_packet flag.

    The packet shape isn't on-disk-stable yet; nodes that emit it write
    into the branch ``stats`` JSON. When absent, the signal is False
    rather than missing — score contribution is 0 either way.
    """
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


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _score_components(signals: dict[str, Any]) -> dict[str, float]:
    """Per-term contributions to score. Surfaced in the response so the
    chatbot can render "why this one ranked first" without re-computing.
    """
    score_avg = signals.get("judgment_score_avg")
    if score_avg is None:
        normalized_judgment = 0.0
    else:
        normalized_judgment = max(0.0, min(1.0, score_avg / JUDGMENT_MAX_SCALE))

    completed = max(0, int(signals.get("completed_run_count") or 0))
    failed = max(0, int(signals.get("failed_run_count") or 0))
    fork_count = max(0, int(signals.get("fork_count") or 0))
    recency = float(signals.get("recency_decay") or 0.0)
    has_gate = 1.0 if signals.get("has_gate_rung") else 0.0
    safe_pub = 1.0 if signals.get("safe_to_publish") else 0.0

    return {
        "judgment":  W_JUDGMENT * normalized_judgment,
        "runs":      W_RUNS * math.log1p(completed),
        "forks":     W_FORKS * math.log1p(fork_count),
        "recency":   W_RECENCY * recency,
        "gate":      W_GATE * has_gate,
        "safe_pub":  W_SAFE_PUBLISH * safe_pub,
        "failed_penalty": -W_FAILED_PENALTY * math.log1p(failed),
    }


def _entry_sort_key(entry: dict[str, Any]) -> tuple:
    """Primary sort key for ranked entries (used with ``reverse=True``).

    Tuple order:
      1. ``score`` — higher is better.
      2. ``last_successful_run_at`` — newer success wins ties.
      3. ``created_at`` — newer branch wins ties.

    Final ``branch_def_id`` tie-break is handled by a separate stable
    sort pass before this one is applied — see ``build_quality_leaderboard``.
    """
    signals = entry.get("signals") or {}
    return (
        float(entry.get("score") or 0.0),
        float(signals.get("last_successful_run_at") or 0.0),
        float(entry.get("created_at") or 0.0),
    )


# ---------------------------------------------------------------------------
# Disclosure + rationale
# ---------------------------------------------------------------------------


def _formula_disclosure() -> dict[str, Any]:
    return {
        "weights": {
            "judgment": W_JUDGMENT,
            "runs": W_RUNS,
            "forks": W_FORKS,
            "recency": W_RECENCY,
            "gate": W_GATE,
            "safe_publish": W_SAFE_PUBLISH,
            "failed_penalty": -W_FAILED_PENALTY,
        },
        "recency_halflife_days": RECENCY_HALFLIFE_DAYS,
        "judgment_max_scale": JUDGMENT_MAX_SCALE,
        "judgment_tag_keys": sorted(_QUALITY_TAG_KEYS),
        "tie_breakers": [
            "last_successful_run_at desc",
            "created_at desc",
            "branch_def_id asc",
        ],
        "notes": (
            "Best-effort v1. Weights are initial guesses surfaced for "
            "audit. Per PLAN Goals & Gates, the parent-rank scoring "
            "formula is open evolution — a follow-on slice will let "
            "the community iterate weights via an evolvable Workflow "
            "node rather than ship constants."
        ),
    }


def _build_rationale(
    top_entry: dict[str, Any], *, leaderboard_size: int,
) -> str:
    """Compose the human-readable rationale string for the top entry."""
    signals = top_entry.get("signals") or {}
    name = top_entry.get("name") or top_entry.get("branch_def_id") or "(unnamed)"
    parts: list[str] = []
    parts.append(
        f"'{name}' (#{top_entry.get('branch_def_id')}) ranked first of "
        f"{leaderboard_size} bound Branches with score "
        f"{top_entry.get('score', 0.0):.2f}."
    )

    score_pieces: list[str] = []
    judgment_avg = signals.get("judgment_score_avg")
    if judgment_avg is not None:
        score_pieces.append(
            f"avg judgment score {judgment_avg:.2f}/{int(JUDGMENT_MAX_SCALE)} "
            f"across {int(signals.get('judgment_score_samples') or 0)} sample(s)"
        )
    completed = int(signals.get("completed_run_count") or 0)
    if completed:
        score_pieces.append(f"{completed} completed run(s)")
    forks = int(signals.get("fork_count") or 0)
    if forks:
        score_pieces.append(f"{forks} community fork(s)")
    age = signals.get("age_days_since_success")
    if age is not None:
        if age < 1:
            age_phrase = "under a day ago"
        elif age < 2:
            age_phrase = "yesterday"
        else:
            age_phrase = f"{int(age)} days ago"
        score_pieces.append(f"most recent successful run {age_phrase}")
    rung = signals.get("gate_rung_top")
    if rung:
        score_pieces.append(f"highest gate rung claimed: '{rung}'")
    if signals.get("safe_to_publish"):
        score_pieces.append("flagged safe_to_publish by its own packet")
    failed = int(signals.get("failed_run_count") or 0)
    if failed:
        score_pieces.append(f"({failed} failed run(s) — penalty applied)")

    if score_pieces:
        parts.append("Signals: " + "; ".join(score_pieces) + ".")
    else:
        parts.append(
            "No quality signals yet — ranking is by recency / author "
            "registration only. Treat as a tentative parent until the "
            "first judgment lands."
        )

    parts.append(
        "Note: this is a best-effort v1 recommendation. Inspect the "
        "score_components in the leaderboard entry to see which "
        "signals dominated the rank."
    )
    return " ".join(parts)


__all__ = [
    "build_quality_leaderboard",
    "recommend_parent_for_fork",
    "W_JUDGMENT",
    "W_RUNS",
    "W_FORKS",
    "W_RECENCY",
    "W_GATE",
    "W_SAFE_PUBLISH",
    "W_FAILED_PENALTY",
    "RECENCY_HALFLIFE_DAYS",
    "JUDGMENT_MAX_SCALE",
]
