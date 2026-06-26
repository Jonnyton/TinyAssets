"""Blank-slate universe brain — Slice 1: the OKF self-model bundle.

Design note: docs/design-notes/2026-06-25-blank-slate-universe-brain.md (§10).

The self-model is a per-universe OKF v0.1 bundle the brain authors *about
itself* — separate from the operational soul. A blank brain boots with a seed
``index.md`` whose entries are **broken links** to concept files it has not
written yet: per OKF, a link to a not-yet-existing target is "not-yet-written
knowledge", and those gaps ARE the brain's open questions (its curiosity).

Slice 1 only stands up the bundle + seed + read primitives. No wiring to
get_status / persona / setters yet (later slices). Pure addition.
"""

from __future__ import annotations

from pathlib import Path

from workflow.universe_self_model import (
    SEED_QUESTIONS,
    SELF_MODEL_DIR,
    SeedQuestion,
    ensure_self_model,
    read_self_model,
)
from workflow.wiki.okf_export import OKF_VERSION, _validate_index, _validate_log

# ─────────────────────────────────────────────────────────────────────
# Seed bundle creation
# ─────────────────────────────────────────────────────────────────────


def test_ensure_self_model_creates_okf_bundle(tmp_path: Path) -> None:
    bundle = ensure_self_model(tmp_path)
    assert bundle == tmp_path / SELF_MODEL_DIR
    assert (bundle / "index.md").is_file()
    assert (bundle / "log.md").is_file()


def test_self_model_is_sibling_of_soul_not_inside_it(tmp_path: Path) -> None:
    """Identity (self-model) is separate from the operational soul — the bundle
    lives at <universe>/self/, never inside soul.md (Codex ADAPT: identity vs
    operational must not be co-located)."""
    bundle = ensure_self_model(tmp_path)
    assert bundle.parent == tmp_path
    assert bundle.name == "self"
    assert not (bundle / "soul.md").exists()


def test_seed_index_declares_okf_version(tmp_path: Path) -> None:
    bundle = ensure_self_model(tmp_path)
    text = (bundle / "index.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert f'okf_version: "{OKF_VERSION}"' in text
    # OKF: bundle-root index.md is the only place frontmatter is permitted, and
    # only the okf_version key. Reuse the exporter's conformance check.
    valid, meta = _validate_index("index.md", text)
    assert valid, meta


def test_seed_log_is_okf_conformant(tmp_path: Path) -> None:
    bundle = ensure_self_model(tmp_path)
    text = (bundle / "log.md").read_text(encoding="utf-8")
    assert _validate_log(text), text


# ─────────────────────────────────────────────────────────────────────
# Curiosity = OKF broken links
# ─────────────────────────────────────────────────────────────────────


def test_seed_lists_the_universal_open_questions(tmp_path: Path) -> None:
    """Every blank brain seeds the SAME universal questions (identity/name,
    founder, goals, body, existing-vs-new)."""
    bundle = ensure_self_model(tmp_path)
    text = (bundle / "index.md").read_text(encoding="utf-8")
    slugs = {q.slug for q in SEED_QUESTIONS}
    assert slugs == {"identity", "founder", "goals", "body", "origin"}
    for q in SEED_QUESTIONS:
        # each open question is a markdown link to its (not-yet-written) concept
        assert f"({q.slug}.md)" in text


def test_seed_links_are_broken_initially(tmp_path: Path) -> None:
    """The seed's links point to concept files that do NOT exist yet — broken
    links are the open questions, per OKF."""
    bundle = ensure_self_model(tmp_path)
    for q in SEED_QUESTIONS:
        assert not (bundle / f"{q.slug}.md").exists()


# ─────────────────────────────────────────────────────────────────────
# read_self_model — known vs open
# ─────────────────────────────────────────────────────────────────────


def test_read_blank_self_model_is_all_open(tmp_path: Path) -> None:
    ensure_self_model(tmp_path)
    view = read_self_model(tmp_path)
    assert view["bundle_exists"] is True
    assert view["okf_version"] == OKF_VERSION
    assert view["known"] == []
    assert {q["slug"] for q in view["open_questions"]} == {
        "identity",
        "founder",
        "goals",
        "body",
        "origin",
    }


def test_read_self_model_distinguishes_known_from_open(tmp_path: Path) -> None:
    """Once the brain writes a concept file (learns something), that question is
    KNOWN and drops out of the open set; the rest stay open."""
    bundle = ensure_self_model(tmp_path)
    # the brain learns its name — writes an OKF concept with its receipt.
    (bundle / "identity.md").write_text(
        "---\n"
        "type: self/identity\n"
        "confidence: 0.8\n"
        "provenance: founder-signal\n"
        "---\n\n"
        "My founder calls me Tiny.\n\n"
        "# Citations\n"
        "[1] /founder.md\n",
        encoding="utf-8",
    )
    view = read_self_model(tmp_path)
    known_slugs = {c["slug"] for c in view["known"]}
    open_slugs = {q["slug"] for q in view["open_questions"]}
    assert "identity" in known_slugs
    assert "identity" not in open_slugs
    assert open_slugs == {"founder", "goals", "body", "origin"}


def test_read_missing_self_model_reports_absent(tmp_path: Path) -> None:
    view = read_self_model(tmp_path)
    assert view["bundle_exists"] is False


# ─────────────────────────────────────────────────────────────────────
# Idempotency — re-ensure preserves what the brain has learned
# ─────────────────────────────────────────────────────────────────────


def test_ensure_is_idempotent_and_preserves_learned_concepts(tmp_path: Path) -> None:
    bundle = ensure_self_model(tmp_path)
    (bundle / "founder.md").write_text(
        "---\ntype: self/founder\n---\n\nMy founder is Jonathan.\n",
        encoding="utf-8",
    )
    # re-ensuring must NOT wipe a learned concept or reset the bundle.
    ensure_self_model(tmp_path)
    assert (bundle / "founder.md").is_file()
    assert "Jonathan" in (bundle / "founder.md").read_text(encoding="utf-8")
    view = read_self_model(tmp_path)
    assert "founder" in {c["slug"] for c in view["known"]}


def test_seed_question_is_a_named_tuple_like(tmp_path: Path) -> None:
    q = SEED_QUESTIONS[0]
    assert isinstance(q, SeedQuestion)
    assert q.slug and q.question


# ─────────────────────────────────────────────────────────────────────
# Robustness (Codex review 2026-06-25)
# ─────────────────────────────────────────────────────────────────────


def test_ensure_restores_missing_index_without_clobbering_log(tmp_path: Path) -> None:
    """A partial bundle (interrupted create — log.md present, index.md missing)
    is COMPLETED, not overwritten: index restored, existing log preserved."""
    bundle = ensure_self_model(tmp_path)
    (bundle / "log.md").write_text(
        "# Self-Model Log\n\n## 2026-06-25\n* my own log\n", encoding="utf-8"
    )
    (bundle / "index.md").unlink()
    ensure_self_model(tmp_path)
    assert (bundle / "index.md").is_file()  # restored
    assert "* my own log" in (bundle / "log.md").read_text(encoding="utf-8")  # preserved


def test_read_finds_nested_concepts(tmp_path: Path) -> None:
    """Concepts the brain nests are discovered (OKF concept IDs are path-based)."""
    bundle = ensure_self_model(tmp_path)
    (bundle / "traits").mkdir()
    (bundle / "traits" / "voice.md").write_text(
        "---\ntype: self/trait\n---\n\nI am terse.\n", encoding="utf-8"
    )
    assert "traits/voice" in {c["slug"] for c in read_self_model(tmp_path)["known"]}


def test_read_reports_actual_okf_version_not_constant(tmp_path: Path) -> None:
    """The read view reports the version actually stored in index.md, so a
    preserved/upgraded bundle reports truthfully."""
    bundle = ensure_self_model(tmp_path)
    (bundle / "index.md").write_text(
        '---\nokf_version: "0.2"\n---\n\n# What I Know\n', encoding="utf-8"
    )
    assert read_self_model(tmp_path)["okf_version"] == "0.2"
