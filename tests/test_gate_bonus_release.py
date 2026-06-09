import sqlite3

from workflow.gates.actions import compute_bonus_payout, release_bonus


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE gate_claims (
            claim_id TEXT PRIMARY KEY,
            branch_def_id TEXT NOT NULL,
            goal_id TEXT NOT NULL,
            rung_key TEXT NOT NULL,
            evidence_url TEXT NOT NULL,
            evidence_note TEXT NOT NULL DEFAULT '',
            claimed_by TEXT NOT NULL,
            claimed_at TEXT NOT NULL,
            retracted_at TEXT,
            retracted_reason TEXT NOT NULL DEFAULT '',
            bonus_stake INTEGER NOT NULL DEFAULT 0,
            bonus_refund_after TEXT,
            attachment_scope TEXT NOT NULL DEFAULT 'node',
            node_id TEXT
        )
        """
    )
    return conn


def _insert_claim(
    conn: sqlite3.Connection,
    *,
    claim_id: str,
    claimed_by: str = "staker-1",
    bonus_stake: int = 0,
    bonus_refund_after: str | None = None,
    retracted_at: str | None = None,
    retracted_reason: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO gate_claims (
            claim_id,
            branch_def_id,
            goal_id,
            rung_key,
            evidence_url,
            evidence_note,
            claimed_by,
            claimed_at,
            retracted_at,
            retracted_reason,
            bonus_stake,
            bonus_refund_after,
            attachment_scope,
            node_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'node', ?)
        """,
        (
            claim_id,
            "branch-1",
            "goal-1",
            f"rung-{claim_id}",
            "https://example.test/evidence",
            "",
            claimed_by,
            "2026-05-30T00:00:00+00:00",
            retracted_at,
            retracted_reason,
            bonus_stake,
            bonus_refund_after,
            "node-1",
        ),
    )


def test_release_bonus_pass_disburses_to_node_last_claimer():
    conn = _make_conn()
    _insert_claim(
        conn,
        claim_id="claim-pass",
        bonus_stake=500,
        bonus_refund_after="2026-06-29T00:00:00+00:00",
    )

    result = release_bonus(
        conn,
        claim_id="claim-pass",
        eval_verdict="pass",
        node_last_claimer="node-winner",
        staker="staker-1",
    )

    net, treasury = compute_bonus_payout(500)
    assert result["status"] == "ok"
    assert result["disposition"] == "released"
    assert result["recipient"] == "node-winner"
    assert result["gross_stake"] == 500
    assert result["net_disbursed"] == net
    assert result["treasury_take"] == treasury

    row = conn.execute(
        "SELECT bonus_stake, bonus_refund_after FROM gate_claims WHERE claim_id = ?",
        ("claim-pass",),
    ).fetchone()
    assert dict(row) == {"bonus_stake": 0, "bonus_refund_after": None}


def test_release_bonus_retracted_claim_is_rejected_before_disbursement():
    conn = _make_conn()
    _insert_claim(
        conn,
        claim_id="claim-retracted",
        bonus_stake=500,
        bonus_refund_after="2026-06-29T00:00:00+00:00",
        retracted_at="2026-05-30T01:00:00+00:00",
        retracted_reason="invalid evidence",
    )

    result = release_bonus(
        conn,
        claim_id="claim-retracted",
        eval_verdict="pass",
        node_last_claimer="node-winner",
        staker="staker-1",
    )

    assert result == {
        "status": "rejected",
        "error": "Cannot release bonus on a retracted claim.",
    }

    row = conn.execute(
        "SELECT bonus_stake, bonus_refund_after FROM gate_claims WHERE claim_id = ?",
        ("claim-retracted",),
    ).fetchone()
    assert dict(row) == {
        "bonus_stake": 500,
        "bonus_refund_after": "2026-06-29T00:00:00+00:00",
    }
