"""Tests for universe render-to-shareable-artifact exports."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

import workflow.api.universe as us


@pytest.fixture
def universe_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    return base


def _make_universe(base: Path, uid: str) -> Path:
    udir = base / uid
    (udir / "canon").mkdir(parents=True)
    (udir / "output" / "book-1").mkdir(parents=True)
    (udir / "PROGRAM.md").write_text("A civic research workflow.", encoding="utf-8")
    (udir / "canon" / "brief.md").write_text("Canon brief.", encoding="utf-8")
    (udir / "output" / "book-1" / "scene-01.md").write_text(
        "Rendered scene text.",
        encoding="utf-8",
    )
    return udir


def test_render_markdown_artifact_writes_export_file(universe_base: Path) -> None:
    udir = _make_universe(universe_base, "alpha")

    result = json.loads(us._action_render_artifact(
        universe_id="alpha",
        artifact_format="markdown",
        filename="packet.md",
    ))

    assert result["universe_id"] == "alpha"
    assert result["format"] == "markdown"
    assert result["path"] == "exports/packet.md"
    assert result["mime_type"] == "text/markdown"
    assert result["sha256"]
    artifact = udir / result["path"]
    assert artifact.is_file()
    text = artifact.read_text(encoding="utf-8")
    assert "# Workflow Universe Export: alpha" in text
    assert "A civic research workflow." in text
    assert "Canon brief." in text
    assert "Rendered scene text." in text


def test_render_docx_artifact_uses_minimal_office_package(
    universe_base: Path,
) -> None:
    udir = _make_universe(universe_base, "alpha")

    result = json.loads(us._action_render_artifact(
        universe_id="alpha",
        artifact_format="docx",
        filename="packet",
    ))

    artifact = udir / result["path"]
    assert result["path"] == "exports/packet.docx"
    assert result["mime_type"].endswith("wordprocessingml.document")
    with zipfile.ZipFile(artifact) as zf:
        names = set(zf.namelist())
        assert "[Content_Types].xml" in names
        document = zf.read("word/document.xml").decode("utf-8")
    assert "Workflow Universe Export: alpha" in document
    assert "Rendered scene text." in document


def test_render_pdf_artifact_starts_with_pdf_header(universe_base: Path) -> None:
    udir = _make_universe(universe_base, "alpha")

    result = json.loads(us._action_render_artifact(
        universe_id="alpha",
        artifact_format="pdf",
        filename="packet.pdf",
    ))

    artifact = udir / result["path"]
    assert result["path"] == "exports/packet.pdf"
    assert result["mime_type"] == "application/pdf"
    assert artifact.read_bytes().startswith(b"%PDF-1.4")


def test_render_artifact_rejects_unknown_format(universe_base: Path) -> None:
    _make_universe(universe_base, "alpha")

    result = json.loads(us._action_render_artifact(
        universe_id="alpha",
        artifact_format="html",
    ))

    assert result["error"] == "Unsupported artifact format."
    assert result["supported_formats"] == ["markdown", "docx", "pdf"]


def test_render_artifact_is_exposed_through_universe_dispatch(
    universe_base: Path,
) -> None:
    udir = _make_universe(universe_base, "alpha")

    result = json.loads(us._universe_impl(
        action="render_artifact",
        universe_id="alpha",
        artifact_format="markdown",
        filename="dispatch.md",
    ))

    assert result["universe_id"] == "alpha"
    assert result["path"] == "exports/dispatch.md"
    assert (udir / "exports" / "dispatch.md").is_file()
