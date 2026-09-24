"""Integration tests for the bug_investigation end-to-end flow (Task #25).

Covers attach_patch_packet_comment() attach + replace on a real wiki page
file. The enqueue and investigation-comment halves were deleted under Hard
Rule 15 (the platform has no LLM): nothing queues an investigation any more.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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
# format_investigation_comment — both paths
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# attach_patch_packet_comment — full pipeline: attach, then replace
# ---------------------------------------------------------------------------


class TestAttachPatchPacketPipeline:
    def _call(self, bug_id: str, patch_packet: dict, wiki_root: Path) -> dict:
        from tinyassets.bug_investigation import attach_patch_packet_comment

        with patch("tinyassets.storage.wiki_path", return_value=wiki_root):
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
        from tinyassets.bug_investigation import format_patch_packet_comment

        expected_size = len(format_patch_packet_comment(_SAMPLE_PACKET).encode())
        assert result["patch_packet_size_bytes"] == expected_size
