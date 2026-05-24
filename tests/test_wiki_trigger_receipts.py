"""Tests for FEAT-004 — wiki trigger receipt / outbox primitive.

Covers the lifecycle (pending -> queued | failed | skipped), read API
(get_receipt, recent_attempts, orphan_attempts, health_summary), and
response shape (TriggerReceipt.to_response).

Each test uses an isolated tempfile sqlite db via the ``WORKFLOW_TRIGGER
_RECEIPTS_DB`` env override so tests don't touch real WORKFLOW_DATA_DIR.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from workflow.wiki import trigger_receipts as tr


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "wiki_trigger_attempts.db"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestCreatePending:
    def test_creates_row_with_minted_id(self, db_path: Path) -> None:
        r = tr.create_pending(
            request_id="BUG-047",
            request_kind="bug",
            request_page="pages/bugs/bug-047-x.md",
            db_path=db_path,
        )
        assert r.status == "pending"
        assert r.request_id == "BUG-047"
        assert r.request_kind == "bug"
        assert r.attempted_at  # non-empty ISO-8601 string
        assert len(r.trigger_attempt_id) == 36  # uuid4 string

    def test_optional_fields_persisted(self, db_path: Path) -> None:
        r = tr.create_pending(
            request_id="FEAT-007",
            request_kind="feature",
            request_page="pages/feature-requests/feat-007.md",
            goal_id="c4f481e65b13",
            branch_def_id="fd5c66b1d87d",
            db_path=db_path,
        )
        fetched = tr.get_receipt(r.trigger_attempt_id, db_path=db_path)
        assert fetched is not None
        assert fetched.goal_id == "c4f481e65b13"
        assert fetched.branch_def_id == "fd5c66b1d87d"


class TestMarkQueued:
    def test_pending_to_queued(self, db_path: Path) -> None:
        r = tr.create_pending(
            request_id="BUG-048", request_kind="bug",
            request_page="pages/bugs/bug-048-x.md", db_path=db_path,
        )
        tr.mark_queued(
            r,
            dispatcher_request_id="02b0874d-d5c6-4732-902b-c67888e0093b",
            db_path=db_path,
        )
        fetched = tr.get_receipt(r.trigger_attempt_id, db_path=db_path)
        assert fetched is not None
        assert fetched.status == "queued"
        assert fetched.dispatcher_request_id == "02b0874d-d5c6-4732-902b-c67888e0093b"
        assert fetched.queued_at is not None

    def test_queued_with_run_id(self, db_path: Path) -> None:
        r = tr.create_pending(
            request_id="FEAT-007", request_kind="feature",
            request_page="pages/feature-requests/feat-007.md", db_path=db_path,
        )
        tr.mark_queued(
            r, dispatcher_request_id="d-id", run_id="r-id", db_path=db_path,
        )
        fetched = tr.get_receipt(r.trigger_attempt_id, db_path=db_path)
        assert fetched.run_id == "r-id"


class TestMarkFailed:
    def test_with_exception(self, db_path: Path) -> None:
        r = tr.create_pending(
            request_id="BUG-049", request_kind="bug",
            request_page="pages/bugs/bug-049-x.md", db_path=db_path,
        )
        tr.mark_failed(r, error=RuntimeError("dispatcher rejected"), db_path=db_path)
        fetched = tr.get_receipt(r.trigger_attempt_id, db_path=db_path)
        assert fetched.status == "failed"
        assert fetched.error_class == "RuntimeError"
        assert "dispatcher rejected" in fetched.error_message

    def test_with_explicit_class_and_message(self, db_path: Path) -> None:
        r = tr.create_pending(
            request_id="FEAT-008", request_kind="feature",
            request_page="pages/feature-requests/feat-008.md", db_path=db_path,
        )
        tr.mark_failed(
            r, error_class="EnqueueRejected", error_message="not in priorities",
            db_path=db_path,
        )
        fetched = tr.get_receipt(r.trigger_attempt_id, db_path=db_path)
        assert fetched.error_class == "EnqueueRejected"
        assert fetched.error_message == "not in priorities"

    def test_message_truncated_at_500(self, db_path: Path) -> None:
        r = tr.create_pending(
            request_id="BUG-050", request_kind="bug",
            request_page="pages/bugs/bug-050-x.md", db_path=db_path,
        )
        big = "x" * 1000
        tr.mark_failed(r, error_message=big, db_path=db_path)
        fetched = tr.get_receipt(r.trigger_attempt_id, db_path=db_path)
        assert len(fetched.error_message) == 500


class TestMarkSkipped:
    def test_default_reason(self, db_path: Path) -> None:
        r = tr.create_pending(
            request_id="BUG-051", request_kind="bug",
            request_page="pages/bugs/bug-051-x.md", db_path=db_path,
        )
        tr.mark_skipped(r, db_path=db_path)
        fetched = tr.get_receipt(r.trigger_attempt_id, db_path=db_path)
        assert fetched.status == "skipped"
        assert fetched.error_message == "no_canonical_branch"


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


class TestToResponse:
    def test_pending_minimal(self) -> None:
        r = tr.TriggerReceipt(
            trigger_attempt_id="trg-1", request_id="BUG-047", request_kind="bug",
            request_page="pages/bugs/bug-047-x.md", status="pending",
            attempted_at="2026-05-02T20:00:00+00:00",
        )
        d = r.to_response()
        assert d == {
            "attempted": True, "trigger_attempt_id": "trg-1", "status": "pending",
        }

    def test_queued_includes_dispatcher_id(self) -> None:
        r = tr.TriggerReceipt(
            trigger_attempt_id="trg-2", request_id="FEAT-007", request_kind="feature",
            request_page="pages/feature-requests/feat-007.md", status="queued",
            attempted_at="2026-05-02T20:00:00+00:00",
            queued_at="2026-05-02T20:00:01+00:00",
            dispatcher_request_id="d-id",
            goal_id="c4f481e65b13", branch_def_id="fd5c66b1d87d",
        )
        d = r.to_response()
        assert d["status"] == "queued"
        assert d["dispatcher_request_id"] == "d-id"
        assert d["goal_id"] == "c4f481e65b13"
        assert d["branch_def_id"] == "fd5c66b1d87d"
        assert "error" not in d

    def test_failed_includes_error_block(self) -> None:
        r = tr.TriggerReceipt(
            trigger_attempt_id="trg-3", request_id="BUG-049", request_kind="bug",
            request_page="pages/bugs/bug-049-x.md", status="failed",
            attempted_at="2026-05-02T20:00:00+00:00",
            error_class="RuntimeError", error_message="dispatcher rejected",
        )
        d = r.to_response()
        assert d["status"] == "failed"
        assert d["error"] == {"class": "RuntimeError", "message": "dispatcher rejected"}


# ---------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------


class TestReadAPI:
    def test_receipts_for_request_returns_chronological(self, db_path: Path) -> None:
        for _ in range(3):
            tr.create_pending(
                request_id="BUG-100", request_kind="bug",
                request_page="pages/bugs/bug-100-x.md", db_path=db_path,
            )
        all_rows = tr.receipts_for_request("BUG-100", db_path=db_path)
        assert len(all_rows) == 3
        # attempted_at strings should be non-decreasing
        ats = [r.attempted_at for r in all_rows]
        assert ats == sorted(ats)

    def test_recent_attempts_descending(self, db_path: Path) -> None:
        ids = []
        for i in range(5):
            r = tr.create_pending(
                request_id=f"BUG-{200+i}", request_kind="bug",
                request_page=f"pages/bugs/bug-{200+i}.md", db_path=db_path,
            )
            ids.append(r.trigger_attempt_id)
        recent = tr.recent_attempts(limit=3, db_path=db_path)
        assert len(recent) == 3

    def test_orphan_attempts_empty_when_fresh(self, db_path: Path) -> None:
        tr.create_pending(
            request_id="BUG-300", request_kind="bug",
            request_page="pages/bugs/bug-300.md", db_path=db_path,
        )
        # Just-created records aren't orphans for default 30min cutoff.
        orphans = tr.orphan_attempts(stale_minutes=30, db_path=db_path)
        assert orphans == []

    def test_orphan_attempts_finds_stale_pending(self, db_path: Path) -> None:
        # Manually insert a row with a stale attempted_at to bypass utc_now().
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(tr._TABLE_DDL)
            conn.execute(
                """INSERT INTO wiki_trigger_attempts (
                    trigger_attempt_id, request_id, request_kind, request_page,
                    status, attempted_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                ("stale-trg", "BUG-999", "bug", "pages/bugs/bug-999.md",
                 "pending", old_ts),
            )
            conn.commit()
        orphans = tr.orphan_attempts(stale_minutes=30, db_path=db_path)
        assert len(orphans) == 1
        assert orphans[0].trigger_attempt_id == "stale-trg"

    def test_health_summary_counts_by_status(self, db_path: Path) -> None:
        # Mix: 2 pending, 1 queued, 1 failed.
        tr.create_pending(
            request_id="X-1", request_kind="bug",
            request_page="p1.md", db_path=db_path,
        )
        tr.create_pending(
            request_id="X-2", request_kind="bug",
            request_page="p2.md", db_path=db_path,
        )
        c = tr.create_pending(
            request_id="X-3", request_kind="bug",
            request_page="p3.md", db_path=db_path,
        )
        d = tr.create_pending(
            request_id="X-4", request_kind="bug",
            request_page="p4.md", db_path=db_path,
        )
        tr.mark_queued(c, dispatcher_request_id="d", db_path=db_path)
        tr.mark_failed(d, error=RuntimeError("nope"), db_path=db_path)

        summary = tr.health_summary(db_path=db_path)
        assert summary["window_size"] == 4
        assert summary["by_status"]["pending"] == 2
        assert summary["by_status"]["queued"] == 1
        assert summary["by_status"]["failed"] == 1
