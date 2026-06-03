from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from workflow.api.helpers import _scoped_wiki_root
from workflow.api.wiki import _wiki_file_bug


class WikiFileBugValidationTests(unittest.TestCase):
    def test_rejects_truthy_content_and_body_kwargs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wiki_root = Path(tmp) / "wiki"
            wiki_root.mkdir(parents=True, exist_ok=True)

            with _scoped_wiki_root(wiki_root):
                response = json.loads(_wiki_file_bug(
                    title="Unsupported body field should fail",
                    component="workflow.api.wiki",
                    severity="major",
                    content="this should not be accepted",
                    body="nor should this",
                ))

            self.assertEqual(
                response["error"],
                "Unsupported file_bug field(s): body, content",
            )
            self.assertEqual(response["rejected_fields"], ["body", "content"])
            self.assertIn("repro, observed, expected, and workaround", response["hint"])
            self.assertIn("content/body belong to wiki write/patch actions", response["hint"])
            self.assertFalse((wiki_root / "pages").exists())
            self.assertFalse((wiki_root / "log.md").exists())

    def test_tolerates_falsey_and_default_passthrough_kwargs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wiki_root = Path(tmp) / "wiki"
            wiki_root.mkdir(parents=True, exist_ok=True)

            with _scoped_wiki_root(wiki_root):
                response = json.loads(_wiki_file_bug(
                    title="Falsy kwargs still file",
                    component="workflow.api.wiki",
                    severity="minor",
                    observed="Observed behavior",
                    dry_run=True,
                    similarity_threshold=0.25,
                    max_results=10,
                    offset=0,
                    max_chars=128_000,
                    content="",
                    body="",
                ))

            self.assertEqual(response["status"], "filed")
            self.assertEqual(response["bug_id"], "BUG-001")
            self.assertNotIn("warning", response)
            self.assertTrue((wiki_root / "pages" / "bugs" / "bug-001-falsy-kwargs-still-file.md").exists())

    def test_successful_supported_file_bug_path_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wiki_root = Path(tmp) / "wiki"
            wiki_root.mkdir(parents=True, exist_ok=True)

            with _scoped_wiki_root(wiki_root):
                response = json.loads(_wiki_file_bug(
                    title="Successful filing",
                    component="workflow.api.wiki",
                    severity="critical",
                    repro="1. Run the failing command",
                    observed="The command crashes",
                    expected="The command completes",
                    workaround="Retry with a safe flag",
                    tags="regression, api",
                ))

            self.assertEqual(response["status"], "filed")
            self.assertEqual(response["kind"], "bug")
            self.assertEqual(response["severity"], "critical")
            self.assertEqual(response["component"], "workflow.api.wiki")
            self.assertEqual(response["bug_id"], "BUG-001")
            self.assertIn("navigator triage pipeline", response["note"])

            bug_page = wiki_root / "pages" / "bugs" / "bug-001-successful-filing.md"
            self.assertTrue(bug_page.exists())
            bug_text = bug_page.read_text(encoding="utf-8")
            self.assertIn("# BUG-001: Successful filing", bug_text)
            self.assertIn("## What happened", bug_text)
            self.assertIn("The command crashes", bug_text)
            self.assertIn("## Workaround", bug_text)


if __name__ == "__main__":
    unittest.main()
