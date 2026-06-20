"""External-write effectors — PR-122 Phase 1.

Effectors translate ``external_write_packet``-shaped outputs from a node's
``output_keys`` into real-world side effects (open a GitHub PR, post a
tweet, etc.). They are NOT a new substrate primitive type; they are
glue that reads a documented packet shape out of a run's final state
and invokes an external tool.

Per the canonical 6+5 vocabulary, ``effects`` is a NodeDefinition
attribute, not a fifth primitive. The effector functions in this
package are called from the run-completion path in ``workflow.runs``;
errors are captured into the run's metadata, never raised to the user.

See: pages/patch-requests/pr-122-external-write-primitive-needed-for-
user-buildable-loop-2-to.md
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from workflow.effectors.github_pr import (
    EXTERNAL_WRITE_SINK_GITHUB_PR,
    run_effects_for_branch as _run_github_pr_effects_for_branch,
    run_github_pr_effector,
)
from workflow.effectors.github_read import (
    read_repo_files,
    register_read_repo_files,
)
from workflow.effectors.github_search import (
    register_search_repo_files,
    search_repo_files,
)
from workflow.effectors.twitter_post import (
    EXTERNAL_WRITE_SINK_TWITTER_POST,
    run_twitter_post_effector,
)
from workflow.effectors.wiki_write_back import (
    EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK,
    run_wiki_write_back_effector,
)
from workflow.effectors.windows_desktop import (
    EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
    run_windows_desktop_effector,
)

# Register the opaque domain callables at package import so a branch that uses
# them resolves a body at compile time (read + search side of the loop).
register_read_repo_files()
register_search_repo_files()

logger = logging.getLogger(__name__)


def _branch_without_twitter_post(branch: Any) -> SimpleNamespace:
    """Return a branch-like view with twitter_post removed from effects."""
    filtered_nodes = []
    for node in getattr(branch, "node_defs", None) or []:
        effects = list(getattr(node, "effects", None) or [])
        kept = [sink for sink in effects if sink != EXTERNAL_WRITE_SINK_TWITTER_POST]
        if not kept:
            continue
        filtered_nodes.append(
            SimpleNamespace(
                node_id=getattr(node, "node_id", ""),
                output_keys=list(getattr(node, "output_keys", None) or []),
                effects=kept,
            )
        )
    return SimpleNamespace(node_defs=filtered_nodes)


def _has_twitter_post_packet(
    *,
    output_keys: list[str],
    run_state: dict[str, Any],
) -> bool:
    for key in output_keys:
        if key not in run_state:
            continue
        value = run_state.get(key)
        if isinstance(value, dict):
            if value.get("sink") == EXTERNAL_WRITE_SINK_TWITTER_POST:
                return True
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped.startswith("{"):
                continue
            try:
                parsed = json.loads(stripped)
            except (TypeError, ValueError):
                continue
            if (
                isinstance(parsed, dict)
                and parsed.get("sink") == EXTERNAL_WRITE_SINK_TWITTER_POST
            ):
                return True
    return False


def run_effects_for_branch(
    *,
    branch: Any,
    run_state: dict[str, Any],
    base_path: str | Path | None = None,
    run_id: str = "",
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """Dispatch all external-write effects, including PR-173 twitter_post."""
    evidence_map = _run_github_pr_effects_for_branch(
        branch=_branch_without_twitter_post(branch),
        run_state=run_state,
        base_path=base_path,
        run_id=run_id,
        dry_run=dry_run,
    )
    for node in getattr(branch, "node_defs", None) or []:
        effects = list(getattr(node, "effects", None) or [])
        if EXTERNAL_WRITE_SINK_TWITTER_POST not in effects:
            continue
        node_id = getattr(node, "node_id", "")
        output_keys = list(getattr(node, "output_keys", None) or [])
        if not _has_twitter_post_packet(output_keys=output_keys, run_state=run_state):
            evidence_map.setdefault(node_id, {})[EXTERNAL_WRITE_SINK_TWITTER_POST] = {
                "error": (
                    f"unknown effect sink '{EXTERNAL_WRITE_SINK_TWITTER_POST}'"
                ),
                "error_kind": "unknown_sink",
            }
            continue
        try:
            result = run_twitter_post_effector(
                node_id=node_id,
                output_keys=output_keys,
                run_state=run_state,
                base_path=base_path,
                run_id=run_id,
            )
        except Exception as exc:  # defensive - never raise
            logger.exception("twitter_post effector crashed for node %s", node_id)
            result = {
                "error": f"effector crashed: {exc}",
                "error_kind": "effector_crashed",
            }
        evidence_map.setdefault(node_id, {})[EXTERNAL_WRITE_SINK_TWITTER_POST] = result
    return evidence_map


__all__ = [
    "EXTERNAL_WRITE_SINK_GITHUB_PR",
    "EXTERNAL_WRITE_SINK_TWITTER_POST",
    "EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME",
    "EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK",
    "read_repo_files",
    "register_read_repo_files",
    "search_repo_files",
    "register_search_repo_files",
    "run_github_pr_effector",
    "run_twitter_post_effector",
    "run_windows_desktop_effector",
    "run_wiki_write_back_effector",
    "run_effects_for_branch",
]
