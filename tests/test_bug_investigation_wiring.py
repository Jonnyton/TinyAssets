"""Historical helper tests plus the filing-only retirement contract.

The former forward-trigger plan is retired at
``docs/exec-plans/completed/2026-04-25-file-bug-wiring.md``. Helper-level tests
remain until the locked migration removes the compatibility module; integration
tests below now prove ``file_bug`` does not invoke it.
"""

from __future__ import annotations

from unittest.mock import patch

from tinyassets.branch_tasks import read_queue
from tinyassets.bug_investigation import (
    REQUEST_TYPE_BUG_INVESTIGATION,
    _maybe_enqueue_investigation,
)

# ── _maybe_enqueue_investigation: env-gate ────────────────────────────────────


class TestEnvGate:
    def test_returns_none_when_env_unset(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", raising=False)
        result = _maybe_enqueue_investigation(
            bug_id="BUG-100",
            frontmatter={"title": "x"},
            base_path=tmp_path,
        )
        assert result is None
        assert read_queue(tmp_path) == []

    def test_returns_none_when_env_empty_string(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "")
        result = _maybe_enqueue_investigation(
            bug_id="BUG-101",
            frontmatter={"title": "x"},
            base_path=tmp_path,
        )
        assert result is None
        assert read_queue(tmp_path) == []

    def test_returns_none_when_env_whitespace(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "   ")
        result = _maybe_enqueue_investigation(
            bug_id="BUG-102",
            frontmatter={"title": "x"},
            base_path=tmp_path,
        )
        assert result is None
        assert read_queue(tmp_path) == []


# ── _maybe_enqueue_investigation: happy path ──────────────────────────────────


class TestEnqueuesWhenBound:
    def test_enqueues_when_canonical_bound(self, tmp_path, monkeypatch):
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)
        request_id = _maybe_enqueue_investigation(
            bug_id="BUG-200",
            frontmatter={
                "title": "crash on load",
                "severity": "high",
                "component": "engine",
            },
            base_path=tmp_path,
        )
        assert request_id is not None
        assert len(request_id) == 36

        queue = read_queue(tmp_path)
        assert len(queue) == 1
        task = queue[0]
        assert task.branch_task_id == request_id
        assert task.request_type == REQUEST_TYPE_BUG_INVESTIGATION
        assert task.branch_def_id == "branch-canonical-abc"
        assert task.inputs["bug_id"] == "BUG-200"
        assert task.inputs["title"] == "crash on load"
        assert task.inputs["severity"] == "high"

    def test_passes_universe_id_through(self, tmp_path, monkeypatch):
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)
        _maybe_enqueue_investigation(
            bug_id="BUG-201",
            frontmatter={"title": "x"},
            base_path=tmp_path,
            universe_id="custom-universe",
        )
        queue = read_queue(tmp_path)
        assert queue[0].universe_id == "custom-universe"

    def test_frontmatter_bug_id_overridden_by_arg(self, tmp_path, monkeypatch):
        """Even if frontmatter has a stale bug_id, the explicit arg wins."""
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)
        _maybe_enqueue_investigation(
            bug_id="BUG-202",
            frontmatter={"bug_id": "BUG-WRONG", "title": "x"},
            base_path=tmp_path,
        )
        queue = read_queue(tmp_path)
        assert queue[0].inputs["bug_id"] == "BUG-202"


# ── _maybe_enqueue_investigation: graceful failure ────────────────────────────


class TestGracefulFailure:
    def test_returns_none_on_dispatcher_rejection(self, tmp_path, monkeypatch):
        """When `TINYASSETS_REQUEST_TYPE_PRIORITIES` excludes bug_investigation,
        enqueue raises RuntimeError. Filing must NOT break — caller gets None."""
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.setenv(
            "TINYASSETS_REQUEST_TYPE_PRIORITIES", "paid_market,branch_run"
        )
        result = _maybe_enqueue_investigation(
            bug_id="BUG-300",
            frontmatter={"title": "x"},
            base_path=tmp_path,
        )
        assert result is None
        assert read_queue(tmp_path) == []

    def test_returns_none_on_missing_bug_id(self, tmp_path, monkeypatch):
        """Empty bug_id is a malformed input — log and return None, do not crash."""
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)
        result = _maybe_enqueue_investigation(
            bug_id="",
            frontmatter={"title": "x"},
            base_path=tmp_path,
        )
        assert result is None
        assert read_queue(tmp_path) == []

    def test_returns_none_on_value_error_from_enqueue(self, tmp_path, monkeypatch):
        """If `enqueue_investigation_request` raises ValueError, we recover."""
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)
        with patch(
            "tinyassets.bug_investigation.enqueue_investigation_request",
            side_effect=ValueError("boom"),
        ):
            result = _maybe_enqueue_investigation(
                bug_id="BUG-301",
                frontmatter={"title": "x"},
                base_path=tmp_path,
            )
        assert result is None

    def test_none_frontmatter_does_not_crash(self, tmp_path, monkeypatch):
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)
        request_id = _maybe_enqueue_investigation(
            bug_id="BUG-302",
            frontmatter=None,  # type: ignore[arg-type]
            base_path=tmp_path,
        )
        assert request_id is not None
        queue = read_queue(tmp_path)
        assert queue[0].inputs["bug_id"] == "BUG-302"


# ── Integration: _wiki_file_bug call site ─────────────────────────────────────


def test_wiki_file_bug_never_invokes_retired_investigation_helpers(
    tmp_path, monkeypatch,
):
    """Filing remains ordinary even while the retired module is retained."""
    from tinyassets.api import wiki as wiki_api

    wiki_root = tmp_path / "wiki"
    data_root = tmp_path / "data"
    wiki_api._ensure_wiki_scaffold(wiki_root)
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_root))

    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_GOAL_ID", "goal-canonical-abc"
    )
    monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)

    with patch(
        "tinyassets.bug_investigation._maybe_enqueue_investigation",
        side_effect=AssertionError("file_bug must not enqueue"),
    ) as enqueue, patch(
        "tinyassets.bug_investigation.format_investigation_comment",
        side_effect=AssertionError("file_bug must not format an investigation"),
    ) as formatter, patch(
        "tinyassets.branch_tasks.read_queue",
        side_effect=AssertionError("file_bug must not read task state"),
    ) as queue_reader:
        result_json = wiki_api._wiki_file_bug(
            component="engine",
            severity="minor",
            title="example bug",
            observed="boom",
            verbose=True,
        )

    import json as _json
    result = _json.loads(result_json)
    assert result["status"] == "filed"
    assert "investigation" not in result
    assert "trigger" not in result
    page = (wiki_root / result["path"]).read_text(encoding="utf-8")
    assert "## Investigation" not in page
    assert "## Patch Packet" not in page
    enqueue.assert_not_called()
    formatter.assert_not_called()
    queue_reader.assert_not_called()
    assert not (data_root / "wiki_trigger_attempts.db").exists()


def test_wiki_file_bug_preserves_historical_receipt_without_writing(
    tmp_path, monkeypatch,
):
    """The stop-writer leaves pre-existing task-2.5 evidence byte-for-byte."""
    from tinyassets.api import wiki as wiki_api
    from tinyassets.wiki import trigger_receipts

    wiki_root = tmp_path / "wiki"
    data_root = tmp_path / "data"
    receipt_db = data_root / "wiki_trigger_attempts.db"
    wiki_api._ensure_wiki_scaffold(wiki_root)
    data_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_root))
    monkeypatch.setenv("TINYASSETS_TRIGGER_RECEIPTS_DB", str(receipt_db))
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc",
    )
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_GOAL_ID", "goal-canonical-abc",
    )

    historical = trigger_receipts.create_pending(
        request_id="BUG-HISTORICAL",
        request_kind="bug",
        request_page="pages/bugs/bug-historical.md",
        branch_def_id="branch-canonical-abc",
    )
    before_bytes = receipt_db.read_bytes()

    with patch(
        "tinyassets.wiki.trigger_receipts.create_pending",
        side_effect=AssertionError("file_bug must not create a receipt"),
    ) as create_pending, patch(
        "tinyassets.wiki.trigger_receipts.mark_queued",
        side_effect=AssertionError("file_bug must not update a receipt"),
    ) as mark_queued, patch(
        "tinyassets.wiki.trigger_receipts.mark_failed",
        side_effect=AssertionError("file_bug must not update a receipt"),
    ) as mark_failed, patch(
        "tinyassets.wiki.trigger_receipts.mark_skipped",
        side_effect=AssertionError("file_bug must not update a receipt"),
    ) as mark_skipped, patch(
        "tinyassets.bug_investigation._maybe_enqueue_investigation",
        side_effect=AssertionError("file_bug must not enqueue"),
    ):
        result_json = wiki_api._wiki_file_bug(
            component="engine",
            severity="minor",
            title="new ordinary filing",
            observed="boom",
        )

    import json as _json
    result = _json.loads(result_json)
    assert result["status"] == "filed"
    assert "investigation" not in result
    assert "trigger" not in result
    create_pending.assert_not_called()
    mark_queued.assert_not_called()
    mark_failed.assert_not_called()
    mark_skipped.assert_not_called()
    assert receipt_db.read_bytes() == before_bytes
    assert (
        trigger_receipts.get_receipt(historical.trigger_attempt_id).to_row()
        == historical.to_row()
    )
