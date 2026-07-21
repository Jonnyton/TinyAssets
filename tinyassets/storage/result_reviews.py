"""Immutable, result-bound reviews for separately authorized effects."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tinyassets.runtime.effect_authorization import ResultReview


class ResultReviewStore:
    """SQLite authority for reviews that exist before a GitHub PR."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS result_reviews (
                    review_record_id TEXT PRIMARY KEY,
                    reviewer_id TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    accepted_result_sha256 TEXT NOT NULL,
                    patch_blob_sha256 TEXT NOT NULL,
                    base_commit TEXT NOT NULL,
                    base_tree TEXT NOT NULL,
                    resulting_tree TEXT NOT NULL,
                    expected_repository_head_sha TEXT NOT NULL,
                    verifier_policy_sha256 TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    revoked_at TEXT,
                    superseded_by TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS result_reviews_one_binding
                ON result_reviews(
                    accepted_result_sha256, patch_blob_sha256,
                    expected_repository_head_sha, verifier_policy_sha256
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @staticmethod
    def _time(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("review timestamps must be timezone-aware")
        return value.isoformat()

    def record(self, review: ResultReview) -> ResultReview:
        from tinyassets.runtime.effect_authorization import ResultReview

        if not isinstance(review, ResultReview):
            raise TypeError("review must be a ResultReview")
        values = (
            review.review_record_id,
            review.reviewer_id,
            review.verdict,
            review.accepted_result_sha256,
            review.patch_blob_sha256,
            review.base_commit,
            review.base_tree,
            review.resulting_tree,
            review.expected_repository_head_sha,
            review.verifier_policy_sha256,
            self._time(review.reviewed_at),
            self._time(review.revoked_at),
            review.superseded_by,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO result_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_record_id) DO NOTHING
                """,
                values,
            )
            row = connection.execute(
                "SELECT * FROM result_reviews WHERE review_record_id = ?",
                (review.review_record_id,),
            ).fetchone()
        stored = self._from_row(row)
        if stored != review:
            raise ValueError("review_record_id already names different immutable content")
        return stored

    def get(self, review_record_id: str) -> ResultReview | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM result_reviews WHERE review_record_id = ?",
                (review_record_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def revoke(self, review_record_id: str, *, revoked_at: datetime) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE result_reviews SET revoked_at = ?
                WHERE review_record_id = ? AND revoked_at IS NULL
                """,
                (self._time(revoked_at), review_record_id),
            )
        if cursor.rowcount != 1:
            raise KeyError(review_record_id)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ResultReview:
        from tinyassets.runtime.effect_authorization import ResultReview

        values: dict[str, Any] = dict(row)
        for key in ("reviewed_at", "revoked_at"):
            if values[key] is not None:
                values[key] = datetime.fromisoformat(values[key])
        return ResultReview(**values)


__all__ = ["ResultReviewStore"]
