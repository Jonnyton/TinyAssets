"""Repo-relative path resolution for git-native storage.

Directory shape follows dev-3's Option D (flat + lineage index).
The spec explicitly nests nodes per-branch (per Phase 7 spec §What-
stays-vs-moves) even though dev-3's doc argued for a single canonical
``nodes/<id>.yaml``. We follow the spec — reuse-consolidation can
land after #62's node_ref primitive is live across branches.

```
<repo>/
  branches/<slug>.yaml          # one file per BranchDefinition
  goals/<slug>.yaml             # one file per Goal
  nodes/<branch_slug>/<node_id>.yaml  # per-branch node definitions
  authors/<slug>.yaml           # author definitions (empty in 7.1)
  <universe>/
    rules.yaml
    notes/<timestamp>.md
    targets.yaml
    priorities.yaml
  indexes/                      # derived; CI-regenerated (7.5+)
```
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["YamlRepoLayout", "slugify"]


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, *, fallback: str = "item") -> str:
    """Normalise free-form text into a filesystem-safe slug.

    Lowercases, replaces runs of non-alphanumerics with a single
    hyphen, strips leading/trailing hyphens. Falls back to ``fallback``
    when the result would be empty.
    """
    cleaned = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return cleaned or fallback


class YamlRepoLayout:
    """Resolve repo-relative paths without touching disk.

    Pure path logic — no I/O. Callers hand a ``repo_root`` in and ask
    for the canonical location of each artifact. Tests exercise this
    against ``tmp_path`` without spinning up a real repo.
    """

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()

    # ── Branches ──────────────────────────────────────────────────────

    def branch_path(self, branch_slug: str) -> Path:
        """Path to ``branches/<slug>.yaml``."""
        return self.repo_root / "branches" / f"{branch_slug}.yaml"

    def branches_dir(self) -> Path:
        return self.repo_root / "branches"

    # ── Goals ─────────────────────────────────────────────────────────

    def goal_path(self, goal_slug: str) -> Path:
        return self.repo_root / "goals" / f"{goal_slug}.yaml"

    def goals_dir(self) -> Path:
        return self.repo_root / "goals"

    # ── Nodes ─────────────────────────────────────────────────────────

    def node_dir(self, branch_slug: str) -> Path:
        """Directory containing a branch's node files."""
        return self.repo_root / "nodes" / branch_slug

    def node_path(self, branch_slug: str, node_id: str) -> Path:
        return self.node_dir(branch_slug) / f"{node_id}.yaml"

    # ── Authors (Phase 7.1 writes definitions only) ──────────────────

    def author_path(self, author_slug: str) -> Path:
        return self.repo_root / "authors" / f"{author_slug}.yaml"

    # ── Outcome gates (Phase 6.3) ────────────────────────────────────

    def gates_dir(self, goal_slug: str) -> Path:
        """Directory holding a Goal's gate-claim YAMLs."""
        return self.repo_root / "gates" / goal_slug

    def gate_claim_path(
        self, goal_slug: str, branch_slug: str, rung_key: str,
    ) -> Path:
        """Path to one claim YAML. One file per ``(branch, rung)``.

        Retractions rewrite the same file with ``retracted_at``
        populated rather than deleting, so git history preserves the
        retraction reason.
        """
        return self.gates_dir(goal_slug) / f"{branch_slug}__{rung_key}.yaml"

    # ── Universe-scoped artifacts ─────────────────────────────────────

    def universe_dir(self, universe_slug: str) -> Path:
        return self.repo_root / universe_slug

    def universe_rules_path(self, universe_slug: str) -> Path:
        return self.universe_dir(universe_slug) / "rules.yaml"

    def universe_targets_path(self, universe_slug: str) -> Path:
        return self.universe_dir(universe_slug) / "targets.yaml"

    def universe_priorities_path(self, universe_slug: str) -> Path:
        return self.universe_dir(universe_slug) / "priorities.yaml"

    def universe_note_path(
        self, universe_slug: str, timestamp_slug: str,
    ) -> Path:
        return (
            self.universe_dir(universe_slug) / "notes"
            / f"{timestamp_slug}.md"
        )
