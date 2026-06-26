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

from workflow.effectors.github_merge import (
    EXTERNAL_WRITE_SINK_GITHUB_MERGE,
    run_github_merge_effector,
)
from workflow.effectors.github_pr import (
    EXTERNAL_WRITE_SINK_GITHUB_PR,
    run_github_pr_effector,
)
from workflow.effectors.github_pr import (
    run_effects_for_branch as _run_github_pr_effects_for_branch,
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
from workflow.effectors.validate_patch import (
    register_validate_patch,
    validate_patch,
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
register_validate_patch()


def _branch_without_github_merge(branch):
    """Return a branch-like view with github_merge removed from effects."""
    from types import SimpleNamespace

    filtered_nodes = []
    for node in getattr(branch, "node_defs", None) or []:
        effects = list(getattr(node, "effects", None) or [])
        kept = [sink for sink in effects if sink != EXTERNAL_WRITE_SINK_GITHUB_MERGE]
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


def run_effects_for_branch(
    *,
    branch,
    run_state,
    base_path=None,
    run_id="",
    dry_run=None,
):
    """Dispatch all branch effects, including the PR-175 merge effector."""
    evidence_map = _run_github_pr_effects_for_branch(
        branch=_branch_without_github_merge(branch),
        run_state=run_state,
        base_path=base_path,
        run_id=run_id,
        dry_run=dry_run,
    )
    for node in getattr(branch, "node_defs", None) or []:
        effects = list(getattr(node, "effects", None) or [])
        if EXTERNAL_WRITE_SINK_GITHUB_MERGE not in effects:
            continue
        node_id = getattr(node, "node_id", "")
        output_keys = list(getattr(node, "output_keys", None) or [])
        per_node = evidence_map.setdefault(node_id, {})
        try:
            result = run_github_merge_effector(
                node_id=node_id,
                output_keys=output_keys,
                run_state=run_state,
                base_path=base_path,
                run_id=run_id,
                dry_run=bool(dry_run),
            )
        except Exception as exc:  # defensive: never raise from completion path
            result = {
                "error": f"effector crashed: {exc}",
                "error_kind": "effector_crashed",
            }
        per_node[EXTERNAL_WRITE_SINK_GITHUB_MERGE] = result
    return evidence_map


__all__ = [
    "EXTERNAL_WRITE_SINK_GITHUB_MERGE",
    "EXTERNAL_WRITE_SINK_GITHUB_PR",
    "EXTERNAL_WRITE_SINK_TWITTER_POST",
    "EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME",
    "EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK",
    "read_repo_files",
    "register_read_repo_files",
    "search_repo_files",
    "register_search_repo_files",
    "validate_patch",
    "register_validate_patch",
    "run_github_merge_effector",
    "run_github_pr_effector",
    "run_twitter_post_effector",
    "run_windows_desktop_effector",
    "run_wiki_write_back_effector",
    "run_effects_for_branch",
]
