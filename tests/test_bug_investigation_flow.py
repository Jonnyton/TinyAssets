"""Integration tests for the bug_investigation end-to-end flow (Task #25).

Covers:
- enqueue_investigation_request() creates a BranchTask in branch_tasks.json
- BranchTask has correct request_type, inputs (build_run_payload shape), and trigger_source
- format_investigation_comment() with both run_id and request_id paths
- attach_patch_packet_comment() attach + replace flow on a real wiki page file
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_FRONTMATTER = {
    "bug_id": "BUG-099",
    "title": "Frob explodes on edge case",
    "component": "frob",
    "severity": "high",
    "kind": "bug",
    "observed": "explosion",
    "expected": "no explosion",
    "repro": "trigger edge case",
    "workaround": "avoid edge case",
}

_SAMPLE_PACKET = {
    "root_cause": "off-by-one in frob loop",
    "test_plan": "add regression test for edge case",
    "minimal_repro": "frob(edge_value)",
    "implementation_sketch": "fix index in loop",
}


def _make_wiki(tmp_path: Path) -> Path:
    """Create a minimal wiki directory with a bugs page for BUG-099."""
    bugs_dir = tmp_path / "pages" / "bugs"
    bugs_dir.mkdir(parents=True)
    page = bugs_dir / "bug-099-frob-explodes.md"
    page.write_text(
        "---\nbug_id: BUG-099\ntitle: Frob explodes on edge case\n---\n\n"
        "## Description\n\nFrob explodes on edge case.\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# enqueue_investigation_request — dispatcher integration
# ---------------------------------------------------------------------------


class TestEnqueueInvestigationRequest:
    def _enqueue(self, tmp_path: Path, branch_def_id: str = "def-123") -> str:
        from workflow.bug_investigation import enqueue_investigation_request

        with patch("workflow.dispatcher.prefers_request_type", return_value=True):
            request_id = enqueue_investigation_request(
                bug_ref=_SAMPLE_FRONTMATTER,
                canonical_branch_def_id=branch_def_id,
                base_path=tmp_path,
                universe_id="test-universe",
            )
        return request_id

    def test_returns_non_empty_request_id(self, tmp_path):
        request_id = self._enqueue(tmp_path)
        assert request_id and isinstance(request_id, str)

    def test_creates_branch_tasks_json(self, tmp_path):
        self._enqueue(tmp_path)
        queue_file = tmp_path / "branch_tasks.json"
        assert queue_file.exists()

    def test_task_has_correct_request_type(self, tmp_path):
        self._enqueue(tmp_path)
        queue_file = tmp_path / "branch_tasks.json"
        tasks = json.loads(queue_file.read_text(encoding="utf-8"))
        assert len(tasks) == 1
        assert tasks[0]["request_type"] == "bug_investigation"

    def test_task_has_correct_branch_def_id(self, tmp_path):
        self._enqueue(tmp_path, branch_def_id="def-abc-456")
        queue_file = tmp_path / "branch_tasks.json"
        tasks = json.loads(queue_file.read_text(encoding="utf-8"))
        assert tasks[0]["branch_def_id"] == "def-abc-456"

    def test_task_inputs_match_build_run_payload(self, tmp_path):
        self._enqueue(tmp_path)
        queue_file = tmp_path / "branch_tasks.json"
        tasks = json.loads(queue_file.read_text(encoding="utf-8"))
        inputs = tasks[0]["inputs"]
        # All canonical payload keys must be present, including the branch input.
        for key in ("bug_id", "title", "component", "severity", "kind",
                    "observed", "expected", "repro", "workaround", "request_text"):
            assert key in inputs, f"missing key {key!r} in task inputs"
        assert inputs["bug_id"] == "BUG-099"
        assert inputs["title"] == "Frob explodes on edge case"
        assert inputs["request_text"].startswith("bug BUG-099: Frob explodes")
        assert "Observed: explosion" in inputs["request_text"]

    def test_task_trigger_source_is_owner_queued(self, tmp_path):
        self._enqueue(tmp_path)
        queue_file = tmp_path / "branch_tasks.json"
        tasks = json.loads(queue_file.read_text(encoding="utf-8"))
        assert tasks[0]["trigger_source"] == "owner_queued"

    def test_task_universe_id_preserved(self, tmp_path):
        self._enqueue(tmp_path)
        queue_file = tmp_path / "branch_tasks.json"
        tasks = json.loads(queue_file.read_text(encoding="utf-8"))
        assert tasks[0]["universe_id"] == "test-universe"

    def test_task_id_matches_returned_request_id(self, tmp_path):
        request_id = self._enqueue(tmp_path)
        queue_file = tmp_path / "branch_tasks.json"
        tasks = json.loads(queue_file.read_text(encoding="utf-8"))
        assert tasks[0]["branch_task_id"] == request_id

    def test_raises_value_error_when_branch_def_id_empty(self, tmp_path):
        from workflow.bug_investigation import enqueue_investigation_request

        with patch("workflow.dispatcher.prefers_request_type", return_value=True):
            with pytest.raises(ValueError, match="canonical_branch_def_id"):
                enqueue_investigation_request(
                    bug_ref=_SAMPLE_FRONTMATTER,
                    canonical_branch_def_id="",
                    base_path=tmp_path,
                )

    def test_raises_runtime_error_when_request_type_not_accepted(self, tmp_path):
        from workflow.bug_investigation import enqueue_investigation_request

        with patch("workflow.dispatcher.prefers_request_type", return_value=False):
            with pytest.raises(RuntimeError, match="not in"):
                enqueue_investigation_request(
                    bug_ref=_SAMPLE_FRONTMATTER,
                    canonical_branch_def_id="def-123",
                    base_path=tmp_path,
                )

    def test_priority_weight_passed_through(self, tmp_path):
        from workflow.bug_investigation import enqueue_investigation_request

        with patch("workflow.dispatcher.prefers_request_type", return_value=True):
            enqueue_investigation_request(
                bug_ref=_SAMPLE_FRONTMATTER,
                canonical_branch_def_id="def-123",
                base_path=tmp_path,
                priority=5,
            )
        queue_file = tmp_path / "branch_tasks.json"
        tasks = json.loads(queue_file.read_text(encoding="utf-8"))
        assert tasks[0]["priority_weight"] == 5.0

    def test_missing_bug_ref_keys_default_to_empty_string(self, tmp_path):
        from workflow.bug_investigation import enqueue_investigation_request

        sparse_ref = {"bug_id": "BUG-001", "title": "Sparse bug"}
        with patch("workflow.dispatcher.prefers_request_type", return_value=True):
            enqueue_investigation_request(
                bug_ref=sparse_ref,
                canonical_branch_def_id="def-123",
                base_path=tmp_path,
            )
        queue_file = tmp_path / "branch_tasks.json"
        tasks = json.loads(queue_file.read_text(encoding="utf-8"))
        inputs = tasks[0]["inputs"]
        assert inputs["component"] == ""
        assert inputs["severity"] == ""


# ---------------------------------------------------------------------------
# format_investigation_comment — both paths
# ---------------------------------------------------------------------------


class TestFormatInvestigationCommentPaths:
    def test_run_id_path_uses_investigation_run_id_label(self):
        from workflow.bug_investigation import format_investigation_comment

        result = format_investigation_comment(run_id="run-abc", status="queued")
        assert "investigation_run_id=`run-abc`" in result

    def test_request_id_path_uses_dispatcher_request_id_label(self):
        from workflow.bug_investigation import format_investigation_comment

        result = format_investigation_comment(run_id="", request_id="req-xyz", status="queued")
        assert "dispatcher_request_id=`req-xyz`" in result

    def test_request_id_path_does_not_include_run_id_label(self):
        from workflow.bug_investigation import format_investigation_comment

        result = format_investigation_comment(run_id="", request_id="req-xyz")
        assert "investigation_run_id" not in result

    def test_run_id_path_does_not_include_dispatcher_label(self):
        from workflow.bug_investigation import format_investigation_comment

        result = format_investigation_comment(run_id="run-abc")
        assert "dispatcher_request_id" not in result

    def test_status_appears_in_both_paths(self):
        from workflow.bug_investigation import format_investigation_comment

        r1 = format_investigation_comment(run_id="r1", status="running")
        r2 = format_investigation_comment(run_id="", request_id="rq1", status="running")
        assert "status=running" in r1
        assert "status=running" in r2


# ---------------------------------------------------------------------------
# attach_patch_packet_comment — full pipeline: attach, then replace
# ---------------------------------------------------------------------------


class TestAttachPatchPacketPipeline:
    def _call(self, bug_id: str, patch_packet: dict, wiki_root: Path) -> dict:
        from workflow.bug_investigation import attach_patch_packet_comment

        with patch("workflow.storage.wiki_path", return_value=wiki_root):
            return attach_patch_packet_comment(bug_id, patch_packet)

    def _page(self, wiki_root: Path) -> Path:
        return wiki_root / "pages" / "bugs" / "bug-099-frob-explodes.md"

    def test_first_attach_appends_to_page(self, tmp_path):
        wiki_root = _make_wiki(tmp_path)
        result = self._call("BUG-099", _SAMPLE_PACKET, wiki_root)
        assert result["status"] == "attached"
        written = self._page(wiki_root).read_text(encoding="utf-8")
        assert "## Patch Packet" in written
        assert "off-by-one in frob loop" in written

    def test_second_attach_replaces_first(self, tmp_path):
        wiki_root = _make_wiki(tmp_path)
        self._call("BUG-099", {"root_cause": "first cause"}, wiki_root)
        result = self._call("BUG-099", {"root_cause": "second cause"}, wiki_root)
        assert result["status"] == "attached"
        written = self._page(wiki_root).read_text(encoding="utf-8")
        assert written.count("## Patch Packet") == 1
        assert "second cause" in written
        assert "first cause" not in written

    def test_full_packet_all_sections_present(self, tmp_path):
        wiki_root = _make_wiki(tmp_path)
        result = self._call("BUG-099", _SAMPLE_PACKET, wiki_root)
        assert result["status"] == "attached"
        written = self._page(wiki_root).read_text(encoding="utf-8")
        assert "### Root Cause" in written
        assert "### Test Plan" in written
        assert "### Minimal Repro" in written
        assert "### Implementation Sketch" in written

    def test_original_description_preserved_after_attach(self, tmp_path):
        wiki_root = _make_wiki(tmp_path)
        self._call("BUG-099", _SAMPLE_PACKET, wiki_root)
        written = self._page(wiki_root).read_text(encoding="utf-8")
        assert "## Description" in written
        assert "Frob explodes on edge case." in written

    def test_patch_packet_size_bytes_matches_encoded_length(self, tmp_path):
        wiki_root = _make_wiki(tmp_path)
        result = self._call("BUG-099", _SAMPLE_PACKET, wiki_root)
        from workflow.bug_investigation import format_patch_packet_comment

        expected_size = len(format_patch_packet_comment(_SAMPLE_PACKET).encode())
        assert result["patch_packet_size_bytes"] == expected_size
