"""Tests for the blank OKF soul-bundle seeder (universe-creation D4/D5).

Covers the spec's baseline-file, OKF-shape, link-closure, soul.edit,
projects/goals, body, and orgchart scenarios.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tinyassets.universe_bundle import (
    BASELINE_FILES,
    FORBIDDEN_BASELINE,
    OKF_SPEC_URL,
    SOUL_EDIT_GOVERNED,
    seed_okf_bundle,
)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Parse the ``---`` YAML frontmatter block with a REAL YAML parser.

    Using yaml.safe_load (not naive colon-splitting) is the OKF conformance
    check: a description/URL value containing ``: `` must still parse.
    """
    assert text.startswith("---\n"), "file must start with frontmatter"
    end = text.index("\n---", 4)
    block = text[4:end]
    body = text[end + 4:]
    meta = yaml.safe_load(block)
    assert isinstance(meta, dict), "frontmatter must be a YAML mapping"
    return meta, body


# OKF (Codex 2026-07-02 adapt): index.md / log.md / soul_versions/index.md are
# RESERVED structural files — no concept `type` frontmatter. Root index.md
# permits only `okf_version`; log.md and soul_versions/index.md are plain.
RESERVED_FILES = {"index.md", "log.md", "soul_versions/index.md"}


def test_all_frontmatter_parses_as_yaml(tmp_path: Path):
    udir = tmp_path / "u-yaml"
    udir.mkdir()
    seed_okf_bundle(udir, purpose="track my recipes: fast", loop_branch_def_id="b-1")
    for rel in BASELINE_FILES:
        if rel in RESERVED_FILES:
            continue
        text = (udir / rel).read_text(encoding="utf-8")
        meta, _ = _split_frontmatter(text)  # raises if YAML is invalid
        assert isinstance(meta.get("type"), str) and meta["type"], rel


@pytest.fixture
def seeded(tmp_path: Path) -> Path:
    udir = tmp_path / "u-01test"
    udir.mkdir()
    seed_okf_bundle(udir)
    return udir


def test_all_baseline_files_written(seeded: Path):
    for rel in BASELINE_FILES:
        assert (seeded / rel).is_file(), rel


def test_forbidden_baseline_not_created(seeded: Path):
    for name in FORBIDDEN_BASELINE:
        assert not (seeded / name).exists(), name


def test_non_reserved_files_have_okf_frontmatter_with_type(seeded: Path):
    for rel in BASELINE_FILES:
        text = (seeded / rel).read_text(encoding="utf-8")
        if rel in RESERVED_FILES:
            continue
        meta, _ = _split_frontmatter(text)
        assert meta.get("type"), f"{rel} missing non-empty type"


def test_reserved_files_carry_no_concept_frontmatter(seeded: Path):
    # log.md + soul_versions/index.md: plain markdown, no frontmatter at all.
    for rel in ("log.md", "soul_versions/index.md"):
        text = (seeded / rel).read_text(encoding="utf-8")
        assert not text.startswith("---"), f"{rel} must not carry frontmatter"
    # Root index.md: ONLY okf_version in frontmatter (no concept type).
    text = (seeded / "index.md").read_text(encoding="utf-8")
    meta, _ = _split_frontmatter(text)
    assert set(meta) == {"okf_version"}, meta


def test_soul_md_is_okf_shaped_and_tracks_latest(seeded: Path):
    meta, body = _split_frontmatter((seeded / "soul.md").read_text(encoding="utf-8"))
    assert meta["type"] == "Universe Soul"
    assert meta.get("okf_source") == OKF_SPEC_URL
    assert meta.get("okf_tracking") == "latest-main"
    # declares edit authority + links the edit policy
    assert "soul.edit" in body
    assert "soul.edit.md" in body


def test_soul_md_links_resolve_to_generated_files(seeded: Path):
    body = (seeded / "soul.md").read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)]+)\)", body)
    assert links
    for target in links:
        # ignore external http links; local links must resolve
        if target.startswith("http"):
            continue
        assert (seeded / target).exists(), target
    # soul.md lists orgchart.md among the open questions
    assert "orgchart.md" in body
    assert "Open Questions" in body


def test_link_closure_every_file_pointed_to(seeded: Path):
    anchors = "\n".join(
        (seeded / a).read_text(encoding="utf-8")
        for a in ("index.md", "log.md", "soul.md", "soul_versions/index.md")
    )
    for rel in BASELINE_FILES:
        name = rel.split("/")[-1]
        if rel in ("index.md",):
            continue  # index is the root anchor
        assert name in anchors, f"{rel} not linked from any anchor file"


def _norm(text: str) -> str:
    """Lowercase + collapse whitespace so phrase checks ignore line wrapping."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def test_soul_edit_policy(seeded: Path):
    meta, body = _split_frontmatter(
        (seeded / "soul.edit.md").read_text(encoding="utf-8")
    )
    assert meta["type"] == "Soul Edit Policy"
    assert meta.get("id") == "soul.edit"
    # Each governed file appears as a governed bullet (orgchart.md joined this set
    # 2026-08-23 so the agent can record its org chart via write_brain).
    for governed in SOUL_EDIT_GOVERNED:
        assert f"`{governed}`" in body, governed
    # projects/goals stay learned/runtime — NOT governed bullets.
    for ungoverned in ("projects.md", "goals.md"):
        assert f"- `{ungoverned}`" not in body, ungoverned
    assert "log" in body and "soul_versions" in body


def test_body_is_learned_embodiment(seeded: Path):
    meta, body = _split_frontmatter((seeded / "body.md").read_text(encoding="utf-8"))
    assert meta["type"] == "Body"
    low = _norm(body)
    assert "not learned yet" in low
    for concept in ("brain", "voice", "hands"):
        assert concept in low, concept


def test_orgchart_founder_anchor(seeded: Path):
    meta, body = _split_frontmatter(
        (seeded / "orgchart.md").read_text(encoding="utf-8")
    )
    assert meta["type"] == "Org Chart"
    low = _norm(body)
    assert "founder is always the top" in low
    # Default (2026-08-23): the founder is the SOLE member and the file seeds
    # LEARNED, so the agent does not treat it as an open question and re-ask. It is
    # writable via write_brain (orgchart joined SOUL_EDIT_GOVERNED + _BRAIN_SECTIONS).
    assert "sole member" in low
    assert "not learned yet" not in low
    assert meta.get("status") == "learned"


def test_projects_and_goals_boundary(seeded: Path):
    projects = (seeded / "projects.md").read_text(encoding="utf-8").lower()
    goals = (seeded / "goals.md").read_text(encoding="utf-8").lower()
    assert "one-line" in projects
    assert "not learned yet" in projects
    assert "runtime goals" in goals
    assert "projects.md" in goals  # goals points founder projects to projects.md
    assert "attached to" in goals  # branch uses attach to goals


def test_identity_not_learned(seeded: Path):
    body = (seeded / "identity.md").read_text(encoding="utf-8").lower()
    assert "not learned yet" in body


def test_soul_version_snapshot_matches_soul(seeded: Path):
    soul = (seeded / "soul.md").read_text(encoding="utf-8")
    snap = (seeded / "soul_versions" / "0001.md").read_text(encoding="utf-8")
    assert snap == soul


def test_blank_universe_reads_back_unnamed(seeded: Path):
    from tinyassets.universe_soul import read_universe_soul

    soul = read_universe_soul(seeded)
    assert soul is not None
    assert soul.name == ""  # unnamed at creation


def test_purpose_and_loop_are_recoverable_when_provided(tmp_path: Path):
    udir = tmp_path / "u-02test"
    udir.mkdir()
    seed_okf_bundle(udir, purpose="track my recipes", loop_branch_def_id="branch-9")
    from tinyassets.universe_soul import read_universe_soul

    soul = read_universe_soul(udir)
    assert soul is not None
    assert "recipes" in soul.purpose
    assert soul.loop_branch_def_id == "branch-9"


# --------------------------------------------------------------------------- #
# Cross-file grounding-set consistency (guards the "parallel lists drift" bug
# class: orgchart.md was seeded + a seed-question but absent from the governed
# set and _BRAIN_SECTIONS, so the agent could never write it and re-asked forever,
# 2026-08-23). These assertions fail CI if any grounding file is wired into one
# list but not the others it needs.
# --------------------------------------------------------------------------- #


def test_every_brain_section_is_governed_and_seeded():
    """A write_brain section that is not governed is SILENTLY DROPPED by
    commit_learning (the orgchart bug); one that is not in the baseline has no file
    to write. Every _BRAIN_SECTIONS file MUST be both governed and seeded."""
    from tinyassets.engine_mcp_server import _BRAIN_SECTIONS
    from tinyassets.universe_bundle import BASELINE_FILES, SOUL_EDIT_GOVERNED

    for section, fname in _BRAIN_SECTIONS.items():
        assert fname in SOUL_EDIT_GOVERNED, (
            f"_BRAIN_SECTIONS[{section!r}] = {fname!r} is not in SOUL_EDIT_GOVERNED — "
            f"write_brain would silently drop it (commit_learning filters to governed)."
        )
        assert fname in BASELINE_FILES, (
            f"_BRAIN_SECTIONS[{section!r}] = {fname!r} is not seeded in BASELINE_FILES — "
            f"there is no file on disk to write."
        )


def test_governed_files_exist_in_baseline():
    """Every soul-edit-governed file must be a real seeded bundle file."""
    from tinyassets.universe_bundle import BASELINE_FILES, SOUL_EDIT_GOVERNED

    for fname in SOUL_EDIT_GOVERNED:
        assert fname in BASELINE_FILES, (
            f"SOUL_EDIT_GOVERNED names {fname!r} which is not in BASELINE_FILES."
        )


def test_seed_questions_map_to_seeded_files():
    """Every self-model seed question must point at a real seeded bundle file."""
    from tinyassets.universe_bundle import BASELINE_FILES
    from tinyassets.universe_self_model import SEED_QUESTIONS

    for q in SEED_QUESTIONS:
        assert q.path in BASELINE_FILES, (
            f"SEED_QUESTIONS slug {q.slug!r} points at {q.path!r} which is not seeded."
        )


def test_orgchart_is_fully_wired_regression():
    """Direct regression pin for the 2026-08-23 orgchart-unwritable bug: orgchart.md
    must be seeded, governed, and a brain section (writable via write_brain)."""
    from tinyassets.engine_mcp_server import _BRAIN_SECTIONS
    from tinyassets.universe_bundle import BASELINE_FILES, SOUL_EDIT_GOVERNED

    assert "orgchart.md" in BASELINE_FILES
    assert "orgchart.md" in SOUL_EDIT_GOVERNED
    assert _BRAIN_SECTIONS.get("orgchart") == "orgchart.md"
