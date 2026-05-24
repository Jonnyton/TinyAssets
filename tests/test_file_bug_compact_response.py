"""Tests for FEAT-008-adjacent — compact ``file_bug`` response shape.

After 2026-05-03 chatbot-side timeout finding (see ``.agents/activity.log``
2026-05-03T02:50Z), the default ``wiki action=file_bug`` response is
trimmed to drop the ``investigation.branch_task`` BranchTask mirror —
which dumped 23 fields including the full ``inputs.request_text`` echo
and pushed responses to ~3.7 KB even for tiny filings, exhausting
ChatGPT connector-wrapper response budgets.

Default response is now compact (~600 bytes). Operators / canaries that
need the full BranchTask mirror pass ``verbose=True``.
"""

from __future__ import annotations

import json

import pytest

from workflow.api.wiki import _wiki_file_bug, wiki


@pytest.fixture
def wired_wiki(tmp_path, monkeypatch):
    """Tmp wiki + canonical investigation branch wired so file_bug enqueues."""
    wiki_root = tmp_path / "Wiki"
    (wiki_root / "pages" / "bugs").mkdir(parents=True)
    (wiki_root / "pages" / "feature-requests").mkdir(parents=True)
    (wiki_root / "drafts" / "bugs").mkdir(parents=True)
    (wiki_root / "drafts" / "feature-requests").mkdir(parents=True)
    monkeypatch.setenv("WORKFLOW_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID",
        "branch-canonical-test",
    )
    monkeypatch.delenv("WORKFLOW_REQUEST_TYPE_PRIORITIES", raising=False)
    return wiki_root


def _file_one(verbose: bool, wired_wiki) -> dict:
    """Helper — file a tiny bug and return the parsed response."""
    raw = _wiki_file_bug(
        component="probe",
        severity="cosmetic",
        title=f"compact-response-test-{verbose}",
        observed="x",
        expected="y",
        kind="feature",
        verbose=verbose,
    )
    return json.loads(raw)


# ── Default response (compact) ─────────────────────────────────────────────


class TestDefaultCompact:
    def test_default_response_omits_branch_task_mirror(self, wired_wiki):
        resp = _file_one(verbose=False, wired_wiki=wired_wiki)
        assert resp["status"] == "filed"
        # investigation block exists with the IDs callers need…
        assert "investigation" in resp
        inv = resp["investigation"]
        assert inv.get("status") == "queued"
        assert "dispatcher_request_id" in inv
        # …but NOT the bulky branch_task mirror
        assert "branch_task" not in inv

    def test_default_response_size_under_one_kb(self, wired_wiki):
        resp = _file_one(verbose=False, wired_wiki=wired_wiki)
        size = len(json.dumps(resp))
        assert size < 1024, (
            f"compact response should fit under 1KB; was {size} bytes. "
            f"Keys: {sorted(resp.keys())}, "
            f"investigation keys: {sorted(resp.get('investigation', {}).keys())}"
        )

    def test_default_response_preserves_top_level_fields(self, wired_wiki):
        resp = _file_one(verbose=False, wired_wiki=wired_wiki)
        for key in ("path", "bug_id", "status", "kind", "severity", "component", "note"):
            assert key in resp, f"compact response dropped {key}"


# ── Verbose response (legacy shape) ────────────────────────────────────────


class TestVerboseRestoresMirror:
    def test_verbose_includes_branch_task_mirror(self, wired_wiki):
        resp = _file_one(verbose=True, wired_wiki=wired_wiki)
        inv = resp["investigation"]
        assert inv.get("status") == "queued"
        assert "branch_task" in inv, (
            "verbose=True must restore the legacy branch_task mirror"
        )
        bt = inv["branch_task"]
        # spot-check a few of the 23 BranchTask fields
        assert "branch_task_id" in bt
        assert "branch_def_id" in bt
        assert "inputs" in bt
        assert bt.get("status") == "pending"

    def test_verbose_branch_task_id_matches_dispatcher_request_id(self, wired_wiki):
        resp = _file_one(verbose=True, wired_wiki=wired_wiki)
        inv = resp["investigation"]
        assert inv["branch_task"]["branch_task_id"] == inv["dispatcher_request_id"]


# ── Wiki dispatch threading ────────────────────────────────────────────────


class TestWikiDispatchThreadsVerbose:
    def test_wiki_dispatch_default_omits_branch_task(self, wired_wiki):
        raw = wiki(
            action="file_bug",
            component="probe",
            severity="cosmetic",
            title="dispatch-default-compact",
            kind="feature",
            observed="x",
        )
        resp = json.loads(raw)
        inv = resp.get("investigation", {})
        assert "branch_task" not in inv

    def test_wiki_dispatch_verbose_includes_branch_task(self, wired_wiki):
        raw = wiki(
            action="file_bug",
            component="probe",
            severity="cosmetic",
            title="dispatch-verbose-restored",
            kind="feature",
            observed="x",
            verbose=True,
        )
        resp = json.loads(raw)
        inv = resp.get("investigation", {})
        assert "branch_task" in inv


# ── Trigger receipt block (FEAT-004) is unaffected by verbose flag ────────


class TestTriggerReceiptUnchanged:
    def test_compact_response_still_emits_trigger_block(self, wired_wiki):
        resp = _file_one(verbose=False, wired_wiki=wired_wiki)
        assert "trigger" in resp, (
            "compact response must still surface FEAT-004 trigger receipt"
        )
        trig = resp["trigger"]
        assert trig.get("attempted") is True
        assert "trigger_attempt_id" in trig
        assert trig.get("status") == "queued"
        assert "dispatcher_request_id" in trig

    def test_trigger_block_present_in_verbose_too(self, wired_wiki):
        resp = _file_one(verbose=True, wired_wiki=wired_wiki)
        assert "trigger" in resp
        assert resp["trigger"].get("attempted") is True
