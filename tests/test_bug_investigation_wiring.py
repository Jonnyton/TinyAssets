"""The file_bug -> investigation auto-trigger is gone, and filing stays ordinary.

The forward-trigger plan was retired at
``docs/exec-plans/completed/2026-04-25-file-bug-wiring.md``; Hard Rule 15 (the
platform has no LLM, 2026-09-24) deleted the compatibility helpers
themselves. These tests prove the helpers are absent and ``file_bug`` touches
no queue or trigger state.
"""

from __future__ import annotations

from unittest.mock import patch

import tinyassets.bug_investigation as bug_investigation

_DELETED_HELPERS = (
    "_maybe_enqueue_investigation",
    "_resolve_investigation_handler",
    "enqueue_investigation_request",
    "format_investigation_comment",
    "is_auto_trigger_enabled",
    "BUG_INVESTIGATION_GOAL_ID",
    "BUG_INVESTIGATION_BRANCH_DEF_ID",
)


def test_investigation_auto_trigger_helpers_are_deleted():
    present = [name for name in _DELETED_HELPERS if hasattr(bug_investigation, name)]
    assert present == []


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
    ) as mark_skipped:
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
