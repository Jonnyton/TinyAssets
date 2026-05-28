"""Tests for the MCP server tool functions.

Each tool is a plain function that reads/writes files in a universe
directory. We test them by pointing WORKFLOW_UNIVERSE at a
temp directory and calling them directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from workflow.mcp_server import (
    add_canon,
    add_note,
    get_activity,
    get_chapter,
    get_premise,
    get_progress,
    get_review_state,
    get_status,
    get_work_targets,
    mcp,
    pause,
    resume,
    set_premise,
    steer,
)


@pytest.fixture(autouse=True)
def universe_dir(tmp_path, monkeypatch):
    """Point the MCP server at a temp directory for every test."""
    monkeypatch.setenv("WORKFLOW_UNIVERSE", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------


class TestMCPServerSetup:
    """MCP server is properly configured."""

    def test_server_name(self):
        assert mcp.name == "workflow"


class TestUniverseDirResolution:
    """_universe_dir() resolves paths without cwd-relative landmines."""

    def test_env_var_is_honored(self, tmp_path, monkeypatch):
        from workflow.mcp_server import _universe_dir

        monkeypatch.setenv("WORKFLOW_UNIVERSE", str(tmp_path / "custom"))
        assert _universe_dir() == Path(str(tmp_path / "custom"))

    def test_default_is_absolute(self, monkeypatch):
        """Default must be absolute so a wrong cwd cannot redirect writes."""
        from workflow.mcp_server import _universe_dir

        monkeypatch.delenv("WORKFLOW_UNIVERSE", raising=False)
        result = _universe_dir()
        assert result.is_absolute()
        assert result.name == "default-universe"

    def test_default_anchored_at_repo_root(self, tmp_path, monkeypatch):
        """Changing cwd must NOT change where the default resolves to."""
        import os

        from workflow.mcp_server import _universe_dir

        monkeypatch.delenv("WORKFLOW_UNIVERSE", raising=False)
        before = _universe_dir()

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            after = _universe_dir()
        finally:
            os.chdir(original_cwd)

        assert before == after

    def test_server_has_tools(self):
        import asyncio

        tools = asyncio.run(mcp.list_tools())
        tool_names = {t.name for t in tools}
        expected = {
            "get_status", "add_note", "get_premise", "set_premise",
            "get_progress", "get_chapter", "get_activity",
            "pause", "resume", "add_canon",
            "get_work_targets", "get_review_state",
        }
        assert expected.issubset(tool_names)
        assert "steer" not in tool_names


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_returns_status_json(self, universe_dir):
        status = {"current_phase": "draft", "word_count": 1200}
        (universe_dir / "status.json").write_text(
            json.dumps(status), encoding="utf-8",
        )
        result = get_status()
        data = json.loads(result)
        assert data["current_phase"] == "draft"
        assert data["word_count"] == 1200

    def test_missing_status(self, universe_dir):
        result = get_status()
        assert "not" in result.lower() or "No" in result


# ---------------------------------------------------------------------------
# steer
# ---------------------------------------------------------------------------


class TestSteer:
    def test_add_note_tool_adds_note(self, universe_dir):
        result = add_note("Focus on dialogue")
        assert "note added" in result.lower() or "Note" in result

        import json
        notes = json.loads(
            (universe_dir / "notes.json").read_text(encoding="utf-8")
        )
        assert len(notes) == 1
        assert notes[0]["text"] == "Focus on dialogue"
        assert notes[0]["source"] == "user"

    def test_adds_note(self, universe_dir):
        result = steer("Focus on dialogue")
        assert "note added" in result.lower() or "Note" in result

        import json
        notes = json.loads(
            (universe_dir / "notes.json").read_text(encoding="utf-8")
        )
        assert len(notes) == 1
        assert notes[0]["text"] == "Focus on dialogue"
        assert notes[0]["source"] == "user"

    def test_adds_multiple(self, universe_dir):
        steer("First note")
        steer("Second note")

        import json
        notes = json.loads(
            (universe_dir / "notes.json").read_text(encoding="utf-8")
        )
        assert len(notes) == 2

    def test_creates_directory_if_needed(self, tmp_path, monkeypatch):
        sub = tmp_path / "nested" / "universe"
        monkeypatch.setenv("WORKFLOW_UNIVERSE", str(sub))
        steer("test")
        assert (sub / "notes.json").exists()


# ---------------------------------------------------------------------------
# get_premise / set_premise
# ---------------------------------------------------------------------------


class TestPremise:
    def test_get_premise_returns_content(self, universe_dir):
        (universe_dir / "PROGRAM.md").write_text(
            "A dark fantasy about dragons.", encoding="utf-8",
        )
        result = get_premise()
        assert "dragons" in result

    def test_get_premise_missing(self, universe_dir):
        result = get_premise()
        assert "No premise found" in result

    def test_set_premise_writes(self, universe_dir):
        result = set_premise("A story about a wandering knight.")
        assert "updated" in result.lower()
        content = (universe_dir / "PROGRAM.md").read_text(encoding="utf-8")
        assert "wandering knight" in content
        soul = (universe_dir / "soul.md").read_text(encoding="utf-8")
        assert "wandering knight" in soul

    def test_set_overwrites_existing(self, universe_dir):
        set_premise("Old premise")
        set_premise("New premise")
        content = (universe_dir / "PROGRAM.md").read_text(encoding="utf-8")
        assert "New premise" in content
        assert "Old premise" not in content

    def test_get_premise_falls_back_to_soul(self, universe_dir):
        from workflow.universe_soul import write_universe_soul

        write_universe_soul(
            universe_dir,
            purpose="A city remembers every repair.",
            lineage="test",
        )

        result = get_premise()
        assert result == "A city remembers every repair."


# ---------------------------------------------------------------------------
# get_progress
# ---------------------------------------------------------------------------


class TestGetProgress:
    def test_returns_progress(self, universe_dir):
        (universe_dir / "progress.md").write_text(
            "# Writing Progress\n\n8,500 words across 7 scenes.",
            encoding="utf-8",
        )
        result = get_progress()
        assert "8,500 words" in result

    def test_missing_progress(self, universe_dir):
        result = get_progress()
        assert "not" in result.lower() or "No" in result


class TestNewReadSurfaces:
    def test_get_work_targets_reads_registry(self, universe_dir):
        (universe_dir / "work_targets.json").write_text(
            json.dumps([{"target_id": "book-1", "title": "Book 1"}]),
            encoding="utf-8",
        )
        result = get_work_targets()
        assert "book-1" in result

    def test_get_review_state_reads_status(self, universe_dir):
        (universe_dir / "status.json").write_text(
            json.dumps({"review_stage": "authorial", "selected_target_id": "book-1"}),
            encoding="utf-8",
        )
        result = get_review_state()
        assert "authorial" in result


# ---------------------------------------------------------------------------
# get_chapter
# ---------------------------------------------------------------------------


class TestGetChapter:
    def test_reads_chapter(self, universe_dir):
        chapter_dir = universe_dir / "output" / "book-1"
        chapter_dir.mkdir(parents=True)
        (chapter_dir / "chapter-03.md").write_text(
            "Ryn entered the forest.", encoding="utf-8",
        )
        result = get_chapter(1, 3)
        assert "Ryn entered the forest" in result

    def test_missing_chapter(self, universe_dir):
        result = get_chapter(1, 99)
        assert "not found" in result.lower()

    def test_chapter_number_zero_padded(self, universe_dir):
        chapter_dir = universe_dir / "output" / "book-2"
        chapter_dir.mkdir(parents=True)
        (chapter_dir / "chapter-05.md").write_text("Prose.", encoding="utf-8")
        result = get_chapter(2, 5)
        assert "Prose." in result


# ---------------------------------------------------------------------------
# get_activity
# ---------------------------------------------------------------------------


class TestGetActivity:
    def test_returns_tail(self, universe_dir):
        lines = [f"[2026-04-01 12:00:{i:02d}] Line {i}" for i in range(30)]
        (universe_dir / "activity.log").write_text(
            "\n".join(lines), encoding="utf-8",
        )
        result = get_activity(5)
        output_lines = result.strip().splitlines()
        assert len(output_lines) == 5
        assert "Line 29" in output_lines[-1]

    def test_default_lines(self, universe_dir):
        lines = [f"Line {i}" for i in range(50)]
        (universe_dir / "activity.log").write_text(
            "\n".join(lines), encoding="utf-8",
        )
        result = get_activity()
        output_lines = result.strip().splitlines()
        assert len(output_lines) == 20

    def test_missing_log(self, universe_dir):
        result = get_activity()
        assert "No activity.log" in result


# ---------------------------------------------------------------------------
# pause / resume
# ---------------------------------------------------------------------------


class TestPauseResume:
    def test_pause_creates_flag(self, universe_dir):
        result = pause()
        assert "pause" in result.lower()
        assert (universe_dir / ".pause").exists()

    def test_resume_removes_flag(self, universe_dir):
        (universe_dir / ".pause").write_text("flagged", encoding="utf-8")
        result = resume()
        assert "resume" in result.lower()
        assert not (universe_dir / ".pause").exists()

    def test_resume_when_not_paused(self, universe_dir):
        result = resume()
        assert "not paused" in result.lower()

    def test_pause_is_idempotent(self, universe_dir):
        pause()
        pause()
        assert (universe_dir / ".pause").exists()


# ---------------------------------------------------------------------------
# add_canon
# ---------------------------------------------------------------------------


class TestAddCanon:
    def test_writes_file(self, universe_dir):
        result = add_canon("characters.md", "# Characters\n\nRyn: a wanderer.")
        assert "characters.md" in result
        content = (universe_dir / "canon" / "characters.md").read_text(
            encoding="utf-8",
        )
        assert "Ryn: a wanderer" in content

    def test_creates_canon_dir(self, universe_dir):
        assert not (universe_dir / "canon").exists()
        add_canon("lore.md", "World lore.")
        assert (universe_dir / "canon").exists()

    def test_overwrites_existing(self, universe_dir):
        add_canon("notes.md", "Old notes")
        add_canon("notes.md", "New notes")
        content = (universe_dir / "canon" / "notes.md").read_text(
            encoding="utf-8",
        )
        assert "New notes" in content
        assert "Old notes" not in content

    def test_path_traversal_sanitized(self, universe_dir):
        add_canon("../../evil.md", "Malicious content")
        # Should be written as "evil.md" inside canon/, not outside
        assert (universe_dir / "canon" / "evil.md").exists()
        assert not (universe_dir.parent / "evil.md").exists()


# ---------------------------------------------------------------------------
# __main__.py --mcp flag
# ---------------------------------------------------------------------------


class TestMCPFlag:
    def test_mcp_flag_exists(self):
        """The --mcp argument should be recognized by the arg parser."""
        # We can't easily test the full main() with --mcp without
        # actually starting a server, but we can verify the import path.
        from workflow.mcp_server import main as mcp_main

        assert callable(mcp_main)


# ---------------------------------------------------------------------------
# .mcp.json config
# ---------------------------------------------------------------------------


class TestMCPConfig:
    def test_example_config_file_exists(self):
        config_path = Path(__file__).parent.parent / ".mcp.example.json"
        assert config_path.exists()

    def test_example_config_is_valid_json(self):
        config_path = Path(__file__).parent.parent / ".mcp.example.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert "mcpServers" in data
        assert "workflow" in data["mcpServers"]
        server = data["mcpServers"]["workflow"]
        assert server["command"] == "python"
        assert "-m" in server["args"]
        assert "workflow.mcp_server" in server["args"]

    def test_local_config_is_ignored(self):
        gitignore_path = Path(__file__).parent.parent / ".gitignore"
        ignored = {
            line.strip()
            for line in gitignore_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        assert ".mcp.json" in ignored
