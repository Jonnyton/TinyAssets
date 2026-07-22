"""Phase 7.1 — YamlRepoLayout path tests.

Pure path resolution. No disk I/O. Pins the directory shape against
the spec + dev-3's directory layout doc (Option D: flat + indexes).
"""

from __future__ import annotations

from pathlib import Path

from tinyassets.catalog import YamlRepoLayout
from tinyassets.catalog.layout import slugify


def test_branch_path_goes_under_branches(tmp_path):
    layout = YamlRepoLayout(tmp_path)
    assert layout.branch_path("my-workflow") == (
        tmp_path / "branches" / "my-workflow.yaml"
    ).resolve()


def test_goal_path_goes_under_goals(tmp_path):
    layout = YamlRepoLayout(tmp_path)
    assert layout.goal_path("produce-academic-paper") == (
        tmp_path / "goals" / "produce-academic-paper.yaml"
    ).resolve()


def test_node_path_is_nested_per_branch(tmp_path):
    """Per Phase 7 spec §What-stays: nodes live at
    `nodes/<branch_slug>/<node_id>.yaml`, NOT flat."""
    layout = YamlRepoLayout(tmp_path)
    assert layout.node_path("my-workflow", "literature_scan") == (
        tmp_path / "nodes" / "my-workflow" / "literature_scan.yaml"
    ).resolve()


def test_author_path_goes_under_authors(tmp_path):
    layout = YamlRepoLayout(tmp_path)
    assert layout.author_path("dev-3") == (
        tmp_path / "authors" / "dev-3.yaml"
    ).resolve()


def test_universe_rules_path(tmp_path):
    layout = YamlRepoLayout(tmp_path)
    assert layout.universe_rules_path("sporemarch") == (
        tmp_path / "sporemarch" / "rules.yaml"
    ).resolve()


def test_universe_note_path(tmp_path):
    layout = YamlRepoLayout(tmp_path)
    assert layout.universe_note_path(
        "sporemarch", "2026-04-13T03-00-00",
    ) == (
        tmp_path / "sporemarch" / "notes"
        / "2026-04-13T03-00-00.md"
    ).resolve()


def test_layout_resolves_repo_root(tmp_path):
    """YamlRepoLayout normalises its repo root once so callers can
    pass a relative path safely."""
    # Pass a Path to tmp_path's name — will be resolved against CWD.
    layout = YamlRepoLayout(str(tmp_path))
    assert layout.repo_root == Path(tmp_path).resolve()


def test_slugify_is_lowercase_and_hyphenated():
    assert slugify("Research Paper Pipeline") == "research-paper-pipeline"


def test_slugify_collapses_non_alphanumerics():
    assert slugify("Hello, world!!! (v2)") == "hello-world-v2"


def test_slugify_strips_edge_hyphens():
    assert slugify("---messy---") == "messy"


def test_slugify_falls_back_on_empty():
    assert slugify("") == "item"
    assert slugify("!!!", fallback="anon") == "anon"


def test_slugify_is_idempotent():
    once = slugify("Research Paper Pipeline")
    assert slugify(once) == once
