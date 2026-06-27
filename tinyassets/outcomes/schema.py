"""Outcome event schema — DDL and dataclass for real-world outcome tracking.

Spec: project_real_world_effect_engine.

One table:
  outcome_event — records a verified real-world outcome tied to a branch run

Outcome types: published_paper, merged_pr, deployed_app, won_competition, custom.
Verification may be automated (evaluator probe) or manual (verified_by actor).
"""

from __future__ import annotations

from dataclasses import dataclass

# ── DDL ───────────────────────────────────────────────────────────────────────

OUTCOME_SCHEMA = """
CREATE TABLE IF NOT EXISTS outcome_event (
    outcome_id      TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    outcome_type    TEXT NOT NULL
                        CHECK (outcome_type IN (
                            'published_paper', 'merged_pr',
                            'deployed_app', 'won_competition', 'custom'
                        )),
    evidence_url    TEXT,
    verified_at     TEXT,
    verified_by     TEXT,
    claim_run_id    TEXT,
    payload         TEXT NOT NULL DEFAULT '{}',
    recorded_at     TEXT NOT NULL,
    note            TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_outcome_run
    ON outcome_event(run_id);

CREATE INDEX IF NOT EXISTS idx_outcome_type
    ON outcome_event(outcome_type);
"""

OUTCOME_TYPES = frozenset({
    "published_paper",
    "merged_pr",
    "deployed_app",
    "won_competition",
    "custom",
})

# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class OutcomeEvent:
    """One verified real-world outcome record."""

    outcome_id: str
    run_id: str
    outcome_type: str
    recorded_at: str
    evidence_url: str | None = None
    verified_at: str | None = None
    verified_by: str | None = None
    claim_run_id: str | None = None
    payload: str = "{}"
    note: str = ""

    def __post_init__(self) -> None:
        if self.outcome_type not in OUTCOME_TYPES:
            raise ValueError(
                f"outcome_type must be one of {sorted(OUTCOME_TYPES)}, "
                f"got {self.outcome_type!r}"
            )

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None

    @classmethod
    def from_row(cls, row: dict) -> OutcomeEvent:
        return cls(
            outcome_id=row["outcome_id"],
            run_id=row["run_id"],
            outcome_type=row["outcome_type"],
            recorded_at=row["recorded_at"],
            evidence_url=row.get("evidence_url"),
            verified_at=row.get("verified_at"),
            verified_by=row.get("verified_by"),
            claim_run_id=row.get("claim_run_id"),
            payload=row.get("payload") or "{}",
            note=row.get("note") or "",
        )


# ── Migration ─────────────────────────────────────────────────────────────────

def migrate_outcome_schema(conn) -> None:  # type: ignore[no-untyped-def]
    """Create outcome tables if absent. Idempotent."""
    conn.executescript(OUTCOME_SCHEMA)
