import sqlite3

from workflow.gates.actions import compute_bonus_payout, release_bonus, unstake_bonus


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
            node_id TEXT,
            bonus_staker_id TEXT
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
    bonus_staker_id: str | None = None,
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
            node_id,
            bonus_staker_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'node', ?, ?)
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
            bonus_staker_id,
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


def test_release_bonus_fail_refunds_recorded_staker_not_caller_supplied():
    """A refund returns to the RECORDED staker (claimed_by), never a
    caller-supplied staker (slice1a review CRITICAL — round 3)."""
    conn = _make_conn()
    _insert_claim(
        conn,
        claim_id="claim-fail",
        claimed_by="real-staker",
        bonus_stake=400,
        bonus_refund_after="2026-06-29T00:00:00+00:00",
    )

    # No staker asserted → trusted in-process call → refund to recorded staker.
    result = release_bonus(
        conn,
        claim_id="claim-fail",
        eval_verdict="fail",
        node_last_claimer="node-winner",
    )
    assert result["status"] == "ok"
    assert result["disposition"] == "refunded"
    assert result["recipient"] == "real-staker"


def test_release_bonus_rejects_mismatched_staker_assertion():
    """A supplied staker that does not match the recorded staker is rejected
    with no disbursement — a caller cannot redirect a refund to themselves."""
    conn = _make_conn()
    _insert_claim(
        conn,
        claim_id="claim-mismatch",
        claimed_by="real-staker",
        bonus_stake=700,
        bonus_refund_after="2026-06-29T00:00:00+00:00",
    )

    result = release_bonus(
        conn,
        claim_id="claim-mismatch",
        eval_verdict="fail",
        node_last_claimer="node-winner",
        staker="attacker",
    )
    assert result["status"] == "rejected"
    assert "recorded staker" in result["error"].lower()

    # Stake untouched.
    row = conn.execute(
        "SELECT bonus_stake FROM gate_claims WHERE claim_id = ?",
        ("claim-mismatch",),
    ).fetchone()
    assert dict(row)["bonus_stake"] == 700


def test_release_bonus_pass_with_matching_staker_assertion_succeeds():
    """Passing the correct recorded staker as an assertion still releases."""
    conn = _make_conn()
    _insert_claim(
        conn,
        claim_id="claim-match",
        claimed_by="real-staker",
        bonus_stake=300,
        bonus_refund_after="2026-06-29T00:00:00+00:00",
    )
    result = release_bonus(
        conn,
        claim_id="claim-match",
        eval_verdict="pass",
        node_last_claimer="node-winner",
        staker="real-staker",
    )
    assert result["status"] == "ok"
    assert result["disposition"] == "released"
    assert result["recipient"] == "node-winner"


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


def test_release_bonus_refuses_double_settle_on_concurrent_release(monkeypatch):
    """Compare-and-swap: if a concurrent release zeroes the stake between this
    call's read and its conditional UPDATE, this call must bail BEFORE recording
    any settlement — no double-settle (slice1a review CRITICAL — round 4)."""
    import workflow.gates.actions as ga

    conn = _make_conn()
    _insert_claim(
        conn,
        claim_id="claim-race",
        claimed_by="staker-1",
        bonus_stake=500,
        bonus_refund_after="2026-06-29T00:00:00+00:00",
    )

    # _now_iso() is the last call before the compare-and-swap UPDATE, so hooking
    # it lets us simulate a concurrent release committing in the read→write
    # window: it zeroes the stake right before our UPDATE runs.
    original_now = ga._now_iso

    def _zero_then_now() -> str:
        conn.execute(
            "UPDATE gate_claims SET bonus_stake = 0 WHERE claim_id = ?",
            ("claim-race",),
        )
        return original_now()

    monkeypatch.setattr(ga, "_now_iso", _zero_then_now)

    result = release_bonus(
        conn,
        claim_id="claim-race",
        eval_verdict="pass",
        node_last_claimer="node-winner",
        staker="staker-1",
    )

    assert result["status"] == "rejected"
    assert "concurrent" in result["error"].lower()
    # No settlement recorded — we bailed before the ledger write.
    assert "settlement_id" not in result
    assert result.get("ledger_recorded") is not True


def test_release_refund_follows_immutable_staker_after_reclaim():
    """A gate re-claim that rewrites claimed_by must NOT redirect the bonus
    refund: a 'fail'/'skip' refund returns to the immutable bonus_staker_id,
    never the (now-attacker) claimed_by (slice1a review CRITICAL — round 5/6)."""
    conn = _make_conn()
    _insert_claim(
        conn,
        claim_id="claim-reclaim",
        claimed_by="alice",
        bonus_stake=600,
        bonus_staker_id="alice",
        bonus_refund_after="2026-06-29T00:00:00+00:00",
    )
    # Attacker re-claims the same (branch, rung): claim_gate overwrites
    # claimed_by but leaves bonus_stake + bonus_staker_id intact.
    conn.execute(
        "UPDATE gate_claims SET claimed_by = ? WHERE claim_id = ?",
        ("mallory", "claim-reclaim"),
    )

    result = release_bonus(
        conn,
        claim_id="claim-reclaim",
        eval_verdict="fail",
        node_last_claimer="node-x",
    )
    assert result["status"] == "ok"
    assert result["disposition"] == "refunded"
    assert result["recipient"] == "alice"  # NOT mallory


def test_release_rejects_reclaimer_staker_assertion():
    """A re-claimer cannot assert themselves as the staker to redirect the
    refund — the assertion is checked against the immutable bonus_staker_id."""
    conn = _make_conn()
    _insert_claim(
        conn,
        claim_id="claim-reclaim2",
        claimed_by="mallory",      # already re-claimed
        bonus_stake=600,
        bonus_staker_id="alice",   # immutable original staker
        bonus_refund_after="2026-06-29T00:00:00+00:00",
    )
    result = release_bonus(
        conn,
        claim_id="claim-reclaim2",
        eval_verdict="fail",
        node_last_claimer="node-x",
        staker="mallory",
    )
    assert result["status"] == "rejected"
    assert "recorded staker" in result["error"].lower()
    # Stake untouched.
    row = conn.execute(
        "SELECT bonus_stake FROM gate_claims WHERE claim_id = ?",
        ("claim-reclaim2",),
    ).fetchone()
    assert dict(row)["bonus_stake"] == 600


def test_unstake_authority_follows_immutable_staker_after_reclaim():
    """After a re-claim, only the immutable original staker may unstake — the
    re-claimer (the new claimed_by) is rejected (slice1a review CRITICAL —
    round 5/6)."""
    conn = _make_conn()
    _insert_claim(
        conn,
        claim_id="claim-unstake",
        claimed_by="mallory",      # re-claimed
        bonus_stake=600,
        bonus_staker_id="alice",   # immutable original staker
        bonus_refund_after="2026-06-29T00:00:00+00:00",
    )
    denied = unstake_bonus(conn, claim_id="claim-unstake", actor="mallory")
    assert denied["status"] == "rejected"
    assert "original staker" in denied["error"].lower()

    ok = unstake_bonus(conn, claim_id="claim-unstake", actor="alice")
    assert ok["status"] == "ok"
    assert ok["refunded"] == 600
    assert ok["refunded_to"] == "alice"
