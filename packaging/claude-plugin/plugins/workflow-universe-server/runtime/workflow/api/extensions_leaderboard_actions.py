"""MCP action handlers for the quality leaderboard — PR-123 substrate (M2).

Wires ``workflow.api.quality_leaderboard`` into the ``extensions`` MCP
tool surface so chatbots can call:

- ``extensions action=quality_leaderboard goal_id=<goal>`` — ranked
  list of branches bound to this Goal with per-entry signal summaries.
- ``extensions action=recommended_parent_for_fork goal_id=<goal>`` —
  top branch_def_id + rationale string. Thin wrapper for community
  designers asking "what should I fork from?".

Goal-generic by design — same primitive works for patch-loops AND
fantasy-writing AND recipe-trackers AND any community.

The dispatch dict shape matches the other ``_*_ACTIONS`` modules under
``workflow/api/``: each handler takes a single ``kwargs: dict`` and
returns a JSON string for the MCP response. The text channel renders
a phone-legible mermaid-free summary; raw entries live in
``structuredContent`` for downstream tools.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _base_universe_dir():
    from workflow.api.helpers import _base_path
    return _base_path()


def _resolve_caller_viewer() -> str:
    """Resolve the viewer identity ONLY from the daemon-side actor.

    Round-2 P1.1 fix — the round-1 handler trusted a caller-supplied
    ``viewer`` kwarg, which let an MCP caller passing
    ``author="someone-else"`` see that user's private branches. This
    helper drops the kwarg entirely and reads ``_current_actor()`` as
    the single source of truth. Defensive try/except so a misconfigured
    daemon falls back to the "strictly public" filter rather than
    leaking private rows on import failure.
    """
    try:
        from workflow.api.engine_helpers import _current_actor
        return _current_actor() or ""
    except Exception:
        logger.exception("failed to resolve _current_actor for viewer")
        return ""


def _action_quality_leaderboard(kwargs: dict[str, Any]) -> str:
    """Return the ranked leaderboard for a Goal.

    Required: ``goal_id``.

    NOTE: any caller-supplied ``viewer`` / ``include_private`` / ``force``
    keys in ``kwargs`` are IGNORED for visibility purposes. Visibility
    is always derived server-side from the current actor — see the
    round-2 PR comment on #970 for the auth-boundary rationale.
    """
    goal_id = (kwargs.get("goal_id") or "").strip()
    if not goal_id:
        return json.dumps({
            "error": "quality_leaderboard requires 'goal_id'",
            "failure_class": "missing_goal_id",
            "actionable_by": "chatbot",
        })
    viewer = _resolve_caller_viewer()

    try:
        from workflow.api.quality_leaderboard import build_quality_leaderboard
        board = build_quality_leaderboard(
            _base_universe_dir(),
            goal_id=goal_id,
            viewer=viewer,
        )
    except Exception as exc:
        logger.exception("quality_leaderboard failed for %s", goal_id)
        return json.dumps({
            "error": f"quality_leaderboard failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })

    board["text"] = _render_leaderboard_text(board)
    return json.dumps(board, default=str)


def _action_recommended_parent_for_fork(kwargs: dict[str, Any]) -> str:
    """Return the top leaderboard entry + rationale for forking.

    Required: ``goal_id``. Same viewer-derivation rules as
    ``quality_leaderboard`` — visibility is server-side only.
    """
    goal_id = (kwargs.get("goal_id") or "").strip()
    if not goal_id:
        return json.dumps({
            "error": "recommended_parent_for_fork requires 'goal_id'",
            "failure_class": "missing_goal_id",
            "actionable_by": "chatbot",
        })
    viewer = _resolve_caller_viewer()

    try:
        from workflow.api.quality_leaderboard import recommend_parent_for_fork
        result = recommend_parent_for_fork(
            _base_universe_dir(),
            goal_id=goal_id,
            viewer=viewer,
        )
    except Exception as exc:
        logger.exception(
            "recommended_parent_for_fork failed for %s", goal_id,
        )
        return json.dumps({
            "error": f"recommended_parent_for_fork failed: {exc}",
            "failure_class": "storage_error",
            "actionable_by": "host",
        })

    result["text"] = _render_recommendation_text(result)
    return json.dumps(result, default=str)


def _render_leaderboard_text(board: dict[str, Any]) -> str:
    entries = board.get("entries") or []
    goal = board.get("goal") or {}
    goal_label = (
        f"'{goal.get('name')}' ({board.get('goal_id')})"
        if goal else f"Goal {board.get('goal_id')}"
    )
    # DESIGN-008: surface selector failures via the text channel so a
    # misbehaving selector renders cleanly in the chatbot. The
    # structured payload also carries error_kind for programmatic
    # consumers.
    if board.get("ok") is False:
        err_kind = board.get("error_kind", "selector_error")
        err = board.get("error", "")
        return (
            f"Selector failed for {goal_label} (`{err_kind}`): {err}. "
            "Operator action: rebind a working selector via "
            "`goals action=set_selector branch_version_id=…` or "
            "unbind to fall back to the platform default."
        )
    if not entries:
        return (
            f"No Branches are currently bound to {goal_label}. "
            "Use `extensions action=build_branch goal_id=...` to "
            "create the first entry."
        )

    lines: list[str] = [
        f"**Quality leaderboard for {goal_label}** "
        f"({len(entries)} entries):",
        "",
        "| Rank | Branch | Author | Score | Runs | Forks | Recency |",
        "|------|--------|--------|-------|------|-------|---------|",
    ]
    for entry in entries[:15]:
        signals = entry.get("signals") or {}
        name = entry.get("name") or "(unnamed)"
        if len(name) > 30:
            name = name[:30].rstrip() + "…"
        age = signals.get("age_days_since_success")
        if age is None:
            age_text = "never"
        elif age < 1:
            age_text = "<1d"
        else:
            age_text = f"{int(age)}d ago"
        lines.append(
            f"| {entry.get('rank')} "
            f"| `{entry.get('branch_def_id', '')[:12]}` {name} "
            f"| {entry.get('author', '')} "
            f"| {entry.get('score', 0.0):.2f} "
            f"| {int(signals.get('completed_run_count') or 0)} "
            f"| {int(signals.get('fork_count') or 0)} "
            f"| {age_text} |"
        )
    if len(entries) > 15:
        lines.append("")
        lines.append(f"… and {len(entries) - 15} more entries.")
    lines.append("")
    lines.append(
        "_Best-effort v1 ranking. Use "
        "`extensions action=recommended_parent_for_fork goal_id=…` "
        "for the top entry plus a rationale._"
    )
    return "\n".join(lines)


def _render_recommendation_text(result: dict[str, Any]) -> str:
    parent = result.get("recommended_parent")
    rationale = result.get("rationale") or ""
    if parent is None:
        return rationale
    name = parent.get("name") or "(unnamed)"
    bid = parent.get("branch_def_id") or ""
    return (
        f"**Recommended parent for fork:** `{bid}` — '{name}' "
        f"(score {parent.get('score', 0.0):.2f}).\n\n"
        f"{rationale}"
    )


_LEADERBOARD_ACTIONS: dict[str, Any] = {
    "quality_leaderboard": _action_quality_leaderboard,
    "recommended_parent_for_fork": _action_recommended_parent_for_fork,
}


__all__ = [
    "_LEADERBOARD_ACTIONS",
    "_action_quality_leaderboard",
    "_action_recommended_parent_for_fork",
]
