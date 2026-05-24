"""Tests for workflow/bug_investigation.py — Task #33 Phase 1 + Phase 2 helpers."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch


def _reload_module(goal_id: str):
    """Reload bug_investigation with a patched env var so the module-level
    constant re-evaluates.
    """
    with patch.dict("os.environ", {"WORKFLOW_BUG_INVESTIGATION_GOAL_ID": goal_id}):
        if "workflow.bug_investigation" in sys.modules:
            del sys.modules["workflow.bug_investigation"]
        mod = importlib.import_module("workflow.bug_investigation")
    return mod


class TestIsAutoTriggerEnabled:
    def test_disabled_when_env_unset(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("WORKFLOW_BUG_INVESTIGATION_GOAL_ID", None)
            # Reimport to pick up missing env
            mod = _reload_module("")
            assert mod.is_auto_trigger_enabled() is False

    def test_enabled_when_env_set(self):
        mod = _reload_module("goal-abc-123")
        assert mod.is_auto_trigger_enabled() is True

    def test_disabled_when_env_empty_string(self):
        mod = _reload_module("")
        assert mod.is_auto_trigger_enabled() is False


class TestBuildRunPayload:
    def _call(self, frontmatter: dict) -> dict:
        mod = _reload_module("")
        return mod.build_run_payload(frontmatter)

    def test_extracts_all_expected_keys(self):
        fm = {
            "bug_id": "BUG-042",
            "title": "Widget explodes",
            "component": "widget",
            "severity": "critical",
            "kind": "bug",
            "observed": "boom",
            "expected": "no boom",
            "repro": "click widget",
            "workaround": "don't click",
        }
        payload = self._call(fm)
        for key, value in fm.items():
            assert payload[key] == value
        assert payload["request_text"].startswith("bug BUG-042: Widget explodes")
        assert "Observed: boom" in payload["request_text"]
        assert "Expected: no boom" in payload["request_text"]

    def test_missing_keys_default_to_empty_string(self):
        payload = self._call({"bug_id": "BUG-001", "title": "Oops"})
        for key in ("component", "severity", "kind", "observed", "expected",
                    "repro", "workaround"):
            assert payload[key] == "", f"expected empty string for missing {key!r}"
        assert payload["request_text"] == "bug BUG-001: Oops"

    def test_extra_keys_are_excluded(self):
        fm = {
            "bug_id": "BUG-002",
            "title": "X",
            "reporter": "alice",   # extra key
            "filed_at": "2026-04-24",  # extra key
        }
        payload = self._call(fm)
        assert "reporter" not in payload
        assert "filed_at" not in payload

    def test_existing_request_text_is_preserved(self):
        payload = self._call({
            "bug_id": "BUG-003",
            "title": "X",
            "request_text": "custom request body",
        })
        assert payload["request_text"] == "custom request body"

    def test_payload_keys_are_stable(self):
        """The 9 canonical fields plus request_text are always present."""
        payload = self._call({})
        assert set(payload.keys()) == {
            "bug_id", "title", "component", "severity", "kind",
            "observed", "expected", "repro", "workaround", "request_text",
        }


class TestFormatInvestigationComment:
    def _call(self, run_id: str, **kwargs) -> str:
        from workflow.bug_investigation import format_investigation_comment
        return format_investigation_comment(run_id, **kwargs)

    def test_contains_run_id(self):
        result = self._call("run-abc-123")
        assert "run-abc-123" in result

    def test_default_status_is_queued(self):
        result = self._call("run-xyz")
        assert "status=queued" in result

    def test_custom_status(self):
        result = self._call("run-xyz", status="running")
        assert "status=running" in result

    def test_has_investigation_heading(self):
        result = self._call("run-xyz")
        assert "## Investigation" in result

    def test_starts_with_double_newline(self):
        result = self._call("run-xyz")
        assert result.startswith("\n\n")


class TestFormatPatchPacketComment:
    def _call(self, patch_packet: dict) -> str:
        from workflow.bug_investigation import format_patch_packet_comment
        return format_patch_packet_comment(patch_packet)

    def test_empty_dict_returns_empty_string(self):
        assert self._call({}) == ""

    def test_all_none_values_returns_empty_string(self):
        assert self._call({
            "minimal_repro": None,
            "root_cause": None,
            "test_plan": None,
            "implementation_sketch": None,
        }) == ""

    def test_has_patch_packet_heading_when_nonempty(self):
        result = self._call({"root_cause": "off-by-one"})
        assert "## Patch Packet" in result

    def test_includes_present_sections(self):
        result = self._call({
            "root_cause": "bad index",
            "test_plan": "add regression test",
        })
        assert "### Root Cause" in result
        assert "bad index" in result
        assert "### Test Plan" in result
        assert "add regression test" in result

    def test_omits_missing_sections(self):
        result = self._call({"root_cause": "x"})
        assert "Minimal Repro" not in result
        assert "Implementation Sketch" not in result

    def test_all_four_sections_present(self):
        pp = {
            "minimal_repro": "a",
            "root_cause": "b",
            "test_plan": "c",
            "implementation_sketch": "d",
        }
        result = self._call(pp)
        assert "### Minimal Repro" in result
        assert "### Root Cause" in result
        assert "### Test Plan" in result
        assert "### Implementation Sketch" in result


# ---------------------------------------------------------------------------
# Task #37: attach_patch_packet_comment
# ---------------------------------------------------------------------------

_SAMPLE_PACKET = {
    "root_cause": "off-by-one in loop",
    "test_plan": "add regression test",
}

_SAMPLE_PAGE = """\
---
bug_id: BUG-042
title: Widget explodes
---

## Description

Widget explodes on click.

## Steps

1. Click widget
"""


def _make_bugs_dir(tmp_path: Path) -> Path:
    bugs_dir = tmp_path / "pages" / "bugs"
    bugs_dir.mkdir(parents=True)
    return bugs_dir


def _write_bug_page(bugs_dir: Path, filename: str, content: str = _SAMPLE_PAGE) -> Path:
    p = bugs_dir / filename
    p.write_text(content, encoding="utf-8")
    return p


class TestAttachPatchPacketComment:
    def _call(self, bug_id: str, patch_packet: dict, wiki_root: Path) -> dict:
        from workflow.bug_investigation import attach_patch_packet_comment
        with patch("workflow.storage.wiki_path", return_value=wiki_root):
            return attach_patch_packet_comment(bug_id, patch_packet)

    def test_successful_attach(self, tmp_path):
        """Bug page exists → attach succeeds and written content includes packet."""
        bugs_dir = _make_bugs_dir(tmp_path)
        page = _write_bug_page(bugs_dir, "bug-042-widget-explodes.md")

        result = self._call("BUG-042", _SAMPLE_PACKET, tmp_path)

        assert result["status"] == "attached"
        assert result["bug_id"] == "BUG-042"
        assert result["patch_packet_size_bytes"] > 0
        written = page.read_text(encoding="utf-8")
        assert "## Patch Packet" in written
        assert "off-by-one in loop" in written

    def test_nonexistent_bug_returns_error(self, tmp_path):
        """Bug page does not exist → structured error, no crash."""
        _make_bugs_dir(tmp_path)

        result = self._call("BUG-999", _SAMPLE_PACKET, tmp_path)

        assert result["status"] == "error"
        assert result["bug_id"] == "BUG-999"
        assert "not found" in result["error"]

    def test_reattach_replaces_not_duplicates(self, tmp_path):
        """Second attach replaces the existing Patch Packet section."""
        bugs_dir = _make_bugs_dir(tmp_path)
        initial_page = _SAMPLE_PAGE + "\n\n## Patch Packet\n\n### Root Cause\n\nold cause\n"
        page = _write_bug_page(bugs_dir, "bug-042-widget-explodes.md", initial_page)

        result = self._call("BUG-042", {"root_cause": "new cause"}, tmp_path)

        assert result["status"] == "attached"
        written = page.read_text(encoding="utf-8")
        assert written.count("## Patch Packet") == 1
        assert "new cause" in written
        assert "old cause" not in written

    def test_reattach_preserves_following_heading(self, tmp_path):
        bugs_dir = _make_bugs_dir(tmp_path)
        initial_page = (
            _SAMPLE_PAGE
            + "\n\n## Patch Packet\n\n### Root Cause\n\nold cause\n\n"
            + "## Related\n\n- BUG-041\n"
        )
        page = _write_bug_page(bugs_dir, "bug-042-widget-explodes.md", initial_page)

        result = self._call("BUG-042", {"root_cause": "new cause"}, tmp_path)

        assert result["status"] == "attached"
        written = page.read_text(encoding="utf-8")
        assert "## Related\n\n- BUG-041" in written
        assert "\nRelated\n" not in written
        assert "old cause" not in written

    def test_empty_patch_packet_returns_error(self, tmp_path):
        """Empty patch_packet → error returned, no write attempted."""
        bugs_dir = _make_bugs_dir(tmp_path)
        page = _write_bug_page(bugs_dir, "bug-042-widget-explodes.md")
        mtime_before = page.stat().st_mtime

        result = self._call("BUG-042", {}, tmp_path)

        assert result["status"] == "error"
        assert page.stat().st_mtime == mtime_before  # file untouched

    def test_slug_case_alias_resolution(self, tmp_path):
        """File named BUG-042-*.md (uppercase) resolves via lowercase slug match."""
        bugs_dir = _make_bugs_dir(tmp_path)
        # Filename uses uppercase BUG prefix — simulates pre-BUG-028-fix files
        page = _write_bug_page(bugs_dir, "BUG-042-widget-explodes.md")

        result = self._call("BUG-042", _SAMPLE_PACKET, tmp_path)

        assert result["status"] == "attached"
        written = page.read_text(encoding="utf-8")
        assert "## Patch Packet" in written

    def test_lowercase_bug_id_also_resolves(self, tmp_path):
        """bug-042 (lowercase) finds file named bug-042-*.md."""
        bugs_dir = _make_bugs_dir(tmp_path)
        page = _write_bug_page(bugs_dir, "bug-042-widget-explodes.md")

        result = self._call("bug-042", _SAMPLE_PACKET, tmp_path)

        assert result["status"] == "attached"
        written = page.read_text(encoding="utf-8")
        assert "## Patch Packet" in written
