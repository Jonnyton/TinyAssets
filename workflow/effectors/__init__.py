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

from workflow.effectors.github_pr import (
    EXTERNAL_WRITE_SINK_GITHUB_PR,
    run_effects_for_branch,
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
from workflow.effectors.windows_desktop import (
    EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
    run_windows_desktop_effector,
)

# Register the opaque domain callables at package import so a branch that uses
# them resolves a body at compile time (read + search side of the loop).
register_read_repo_files()
register_search_repo_files()

__all__ = [
    "EXTERNAL_WRITE_SINK_GITHUB_PR",
    "EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME",
    "read_repo_files",
    "register_read_repo_files",
    "search_repo_files",
    "register_search_repo_files",
    "run_github_pr_effector",
    "run_windows_desktop_effector",
    "run_effects_for_branch",
]
