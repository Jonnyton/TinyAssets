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

#: How strong the evidence behind an outcome claim is. This registry owns the
#: vocabulary; ``tinyassets/handoffs/models.py`` imports it rather than keeping a
#: parallel list, so the Python guard and the SQL CHECK below cannot drift.
#:
#: The values preserve the exact strength of the evidence: transport submission,
#: destination acceptance, and later external verification are deliberately
#: distinct. They do not silently mirror a handoff lifecycle row; each value is
#: appended only from its own authenticated evidence source.
OUTCOME_EVIDENCE_LEVELS = frozenset({
    "user_attested",
    "submitted",
    "accepted",
    "externally_verified",
    "disputed",
    "rejected",
    "orphaned",
    "retracted",
})

_EVIDENCE_LEVEL_SQL_LIST = ", ".join(
    f"'{level}'" for level in sorted(OUTCOME_EVIDENCE_LEVELS)
)

# The CHECK lists are substituted rather than f-string interpolated: this DDL
# contains JSON defaults like '{}' that an f-string would try to parse.
_OUTCOME_EVIDENCE_SCHEMA_TEMPLATE = """
CREATE TABLE IF NOT EXISTS outcome_evidence (
    outcome_id              TEXT PRIMARY KEY
                                REFERENCES outcome_event(outcome_id),
    account_id              TEXT NOT NULL,
    branch_def_id           TEXT NOT NULL DEFAULT '',
    branch_version_id       TEXT NOT NULL DEFAULT '',
    content_hash            TEXT NOT NULL DEFAULT '',
    run_id                  TEXT NOT NULL DEFAULT '',
    output_field            TEXT NOT NULL DEFAULT '',
    output_sha256           TEXT NOT NULL DEFAULT '',
    handoff_id              TEXT NOT NULL DEFAULT '',
    effect_key              TEXT NOT NULL DEFAULT '',
    sink                    TEXT NOT NULL DEFAULT '',
    outcome_kind            TEXT NOT NULL,
    evidence_source         TEXT NOT NULL,
    evidence_level          TEXT NOT NULL
                                CHECK (evidence_level IN (--EVIDENCE-LEVELS--)),
    external_id             TEXT NOT NULL DEFAULT '',
    normalized_external_ref TEXT NOT NULL DEFAULT '',
    attested_by             TEXT NOT NULL DEFAULT '',
    recorded_at             TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_outcome_evidence_account
    ON outcome_evidence(account_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_outcome_evidence_artifact
    ON outcome_evidence(normalized_external_ref);
CREATE INDEX IF NOT EXISTS idx_outcome_evidence_handoff
    ON outcome_evidence(handoff_id);
CREATE INDEX IF NOT EXISTS idx_outcome_evidence_state
    ON outcome_evidence(evidence_level, recorded_at DESC);

CREATE TABLE IF NOT EXISTS outcome_evidence_transition (
    transition_id   TEXT PRIMARY KEY,
    outcome_id      TEXT NOT NULL REFERENCES outcome_evidence(outcome_id),
    seq             INTEGER NOT NULL,
    from_level      TEXT NOT NULL DEFAULT '',
    to_level        TEXT NOT NULL
                        CHECK (to_level IN (--EVIDENCE-LEVELS--)),
    evidence_source TEXT NOT NULL,
    actor_id        TEXT NOT NULL DEFAULT '',
    evidence_json   TEXT NOT NULL DEFAULT '{}',
    recorded_at     TEXT NOT NULL,
    UNIQUE (outcome_id, seq)
);

CREATE TABLE IF NOT EXISTS outcome_artifact (
    artifact_ref  TEXT PRIMARY KEY,
    outcome_kind  TEXT NOT NULL,
    external_id   TEXT NOT NULL,
    first_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outcome_artifact_source (
    artifact_ref   TEXT NOT NULL REFERENCES outcome_artifact(artifact_ref),
    outcome_id     TEXT NOT NULL REFERENCES outcome_evidence(outcome_id),
    contributed_by TEXT NOT NULL DEFAULT '',
    recorded_at    TEXT NOT NULL,
    PRIMARY KEY (artifact_ref, outcome_id)
);
"""

OUTCOME_EVIDENCE_SCHEMA = _OUTCOME_EVIDENCE_SCHEMA_TEMPLATE.replace(
    "--EVIDENCE-LEVELS--", _EVIDENCE_LEVEL_SQL_LIST
)

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
    """Create the outcome registry and its evidence extension. Idempotent.

    Existing rows retain their ids and payloads and gain a ``user_attested``
    evidence head. Their historical schema did not persist the attester, so the
    actor fields stay empty: ``verified_by`` names a verifier and must not be
    repurposed as claimant authority.
    """
    conn.executescript(OUTCOME_SCHEMA + OUTCOME_EVIDENCE_SCHEMA)
    conn.execute(
        """
        INSERT OR IGNORE INTO outcome_evidence (
            outcome_id, account_id, run_id, outcome_kind, evidence_source,
            evidence_level, attested_by, recorded_at, updated_at
        )
        SELECT
            outcome_id, '', run_id, outcome_type, 'legacy_outcome_event',
            'user_attested', '', recorded_at, recorded_at
          FROM outcome_event
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO outcome_evidence_transition (
            transition_id, outcome_id, seq, from_level, to_level,
            evidence_source, actor_id, evidence_json, recorded_at
        )
        SELECT
            'legacy:' || outcome_id || ':user_attested',
            outcome_id, 1, '', 'user_attested', 'legacy_outcome_event',
            '', '{}', recorded_at
          FROM outcome_event
        """
    )
