"""Tests for gate bonus MCP actions: stake_bonus, unstake_bonus, release_bonus.

Spec: docs/vetted-specs.md §Gate bonuses — staked payouts attached to gate milestones.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

# ── helpers ───────────────────────────────────────────────────────────────────

def _seed_goal_and_claim(
    base_path: Path,
    *,
    claimed_by: str = "test_user",
    goal_owner: str | None = None,
) -> tuple[str, str, str]:
    """Insert a gate claim directly into the DB.

    Returns (goal_id, branch_def_id, claim_id).
    The bonus handlers only need the gate_claims table row, plus the Goal
    record when ``goal_owner`` is supplied so release-authority checks resolve
    the Goal owner.
    """
    from workflow.daemon_server import initialize_author_server, save_goal
    from workflow.gates.schema import migrate_gate_bonus_columns
    from workflow.storage import _connect

    initialize_author_server(base_path)

    goal_id = f"goal-{uuid.uuid4().hex[:8]}"
    bid = f"branch-{uuid.uuid4().hex[:8]}"
    claim_id = f"claim-{uuid.uuid4().hex[:8]}"
    now_iso = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

    if goal_owner is not None:
        save_goal(
            base_path,
            goal={
                "goal_id": goal_id,
                "name": f"Goal {goal_id}",
                "description": "seed goal for gate-bonus release authority tests",
                "author": goal_owner,
            },
        )

    with _connect(base_path) as conn:
        migrate_gate_bonus_columns(conn)
        conn.execute(
            """
            INSERT INTO gate_claims
                (claim_id, branch_def_id, goal_id, rung_key,
                 evidence_url, evidence_note, claimed_by, claimed_at,
                 retracted_at, retracted_reason)
            VALUES (?, ?, ?, 'rung1', 'https://example.com/ev', '', ?, ?, NULL, '')
            """,
            (claim_id, bid, goal_id, claimed_by, now_iso),
        )
    return goal_id, bid, claim_id


def _gates(monkeypatch, tmp_path, *, user: str = "test_user", host_user: str | None = None,
           **kwargs):
    """Call gates() with GATES_ENABLED + WORKFLOW_PAID_MARKET set.

    ``user`` sets the authenticated caller (UNIVERSE_SERVER_USER). ``host_user``
    optionally overrides the configured host identity used for release authority.
    """
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GATES_ENABLED", "1")
    monkeypatch.setenv("WORKFLOW_PAID_MARKET", "on")
    monkeypatch.setenv("UNIVERSE_SERVER_USER", user)
    if host_user is not None:
        monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", host_user)
    from workflow.universe_server import gates
    return json.loads(gates(**kwargs))


# ── stake_bonus ───────────────────────────────────────────────────────────────

class TestStakeBonus:
    def test_stake_bonus_success(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path)
        result = _gates(monkeypatch, tmp_path,
                        action="stake_bonus",
                        claim_id=claim_id,
                        bonus_stake=1000,
                        node_id="n1")
        assert result["status"] == "ok"
        assert result["bonus_stake"] == 1000
        assert result["claim_id"] == claim_id

    def test_stake_bonus_requires_paid_market(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("GATES_ENABLED", "1")
        monkeypatch.setenv("WORKFLOW_PAID_MARKET", "off")
        from workflow.universe_server import gates
        result = json.loads(gates(action="stake_bonus", claim_id="x", bonus_stake=100))
        assert result["status"] == "not_available"

    def test_stake_bonus_rejects_zero_stake(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path)
        result = _gates(monkeypatch, tmp_path,
                        action="stake_bonus",
                        claim_id=claim_id,
                        bonus_stake=0)
        assert result["status"] == "rejected"

    def test_stake_bonus_rejects_negative_stake(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path)
        result = _gates(monkeypatch, tmp_path,
                        action="stake_bonus",
                        claim_id=claim_id,
                        bonus_stake=-50,
                        node_id="n1")
        assert result["status"] == "rejected"

    def test_stake_bonus_rejects_missing_claim_id(self, tmp_path, monkeypatch):
        _seed_goal_and_claim(tmp_path)
        result = _gates(monkeypatch, tmp_path,
                        action="stake_bonus",
                        bonus_stake=100)
        assert result["status"] == "rejected"
        assert "claim_id" in result["error"].lower()

    def test_stake_bonus_rejects_missing_node_id(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path)
        result = _gates(monkeypatch, tmp_path,
                        action="stake_bonus",
                        claim_id=claim_id,
                        bonus_stake=100)
        assert result["status"] == "rejected"
        assert "node_id" in result["error"].lower()

    def test_stake_bonus_rejects_unknown_claim(self, tmp_path, monkeypatch):
        _seed_goal_and_claim(tmp_path)
        result = _gates(monkeypatch, tmp_path,
                        action="stake_bonus",
                        claim_id="does-not-exist",
                        bonus_stake=100,
                        node_id="n1")
        assert result["status"] == "rejected"
        assert "not found" in result["error"].lower()

    def test_stake_bonus_rejects_branch_scope(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path)
        result = _gates(monkeypatch, tmp_path,
                        action="stake_bonus",
                        claim_id=claim_id,
                        bonus_stake=100,
                        node_id="n1",
                        attachment_scope="branch")
        assert result["status"] == "rejected"
        assert "not yet implemented" in result["error"].lower()

    def test_stake_bonus_rejects_double_stake(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path)
        _gates(monkeypatch, tmp_path,
               action="stake_bonus",
               claim_id=claim_id,
               bonus_stake=500,
               node_id="n1")
        result = _gates(monkeypatch, tmp_path,
                        action="stake_bonus",
                        claim_id=claim_id,
                        bonus_stake=200,
                        node_id="n1")
        assert result["status"] == "rejected"
        assert "already" in result["error"].lower()

    def test_stake_bonus_rejects_cross_actor(self, tmp_path, monkeypatch):
        """Only the claim owner (or host) may stake a bonus on a claim — a
        write-scoped caller who knows a claim_id cannot attach a stake to
        another actor's claim (slice1a review CRITICAL — round 4)."""
        _, _, claim_id = _seed_goal_and_claim(tmp_path, claimed_by="alice")
        result = _gates(monkeypatch, tmp_path,
                        user="mallory",
                        action="stake_bonus",
                        claim_id=claim_id,
                        bonus_stake=1000,
                        node_id="n1")
        assert result["status"] == "rejected"
        assert "cross-actor" in result["error"].lower()
        # Stake must not have been attached to alice's claim.
        replay = _gates(monkeypatch, tmp_path,
                        user="alice",
                        action="stake_bonus",
                        claim_id=claim_id,
                        bonus_stake=1000,
                        node_id="n1")
        assert replay["status"] == "ok"  # owner can still stake → mallory's was a no-op

    def test_stake_bonus_owner_succeeds(self, tmp_path, monkeypatch):
        """The recorded claim owner may stake a bonus on their own claim."""
        _, _, claim_id = _seed_goal_and_claim(tmp_path, claimed_by="alice")
        result = _gates(monkeypatch, tmp_path,
                        user="alice",
                        action="stake_bonus",
                        claim_id=claim_id,
                        bonus_stake=1000,
                        node_id="n1")
        assert result["status"] == "ok"
        assert result["bonus_stake"] == 1000
        # Immutable owner-of-record is recorded at stake time.
        assert result["bonus_staker_id"] == "alice"

    def test_stake_bonus_host_may_stake_for_any_claim(self, tmp_path, monkeypatch):
        """The configured host identity may stake on any claim."""
        _, _, claim_id = _seed_goal_and_claim(tmp_path, claimed_by="alice")
        result = _gates(monkeypatch, tmp_path,
                        user="hostbox",
                        host_user="hostbox",
                        action="stake_bonus",
                        claim_id=claim_id,
                        bonus_stake=750,
                        node_id="n1")
        assert result["status"] == "ok"
        assert result["bonus_stake"] == 750


# ── unstake_bonus ─────────────────────────────────────────────────────────────

class TestUnstakeBonus:
    def test_unstake_after_stake(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path)
        _gates(monkeypatch, tmp_path,
               action="stake_bonus",
               claim_id=claim_id,
               bonus_stake=1000,
               node_id="n1")
        result = _gates(monkeypatch, tmp_path,
                        action="unstake_bonus",
                        claim_id=claim_id)
        assert result["status"] == "ok"
        assert result["refunded"] == 1000
        assert result["refunded_to"] == "test_user"

    def test_unstake_rejects_wrong_actor(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path)
        _gates(monkeypatch, tmp_path,
               action="stake_bonus",
               claim_id=claim_id,
               bonus_stake=500,
               node_id="n1")
        monkeypatch.setenv("UNIVERSE_SERVER_USER", "other_user")
        from workflow.universe_server import gates
        result = json.loads(gates(action="unstake_bonus", claim_id=claim_id))
        assert result["status"] == "rejected"
        assert "not authorized" in result["error"].lower()

    def test_unstake_rejects_no_stake(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path)
        result = _gates(monkeypatch, tmp_path,
                        action="unstake_bonus",
                        claim_id=claim_id)
        assert result["status"] == "rejected"

    def test_unstake_rejects_unknown_claim(self, tmp_path, monkeypatch):
        _seed_goal_and_claim(tmp_path)
        result = _gates(monkeypatch, tmp_path,
                        action="unstake_bonus",
                        claim_id="no-such-claim")
        assert result["status"] == "rejected"


# ── release_bonus ─────────────────────────────────────────────────────────────

class TestReleaseBonus:
    """Release/refund a gate bonus. Authority is the Goal owner / host /
    gate-claim-capability holder — NOT the staker, NOT an arbitrary caller.

    These tests seed a Goal owned by ``goal_owner`` and stake the bonus as the
    staker (``test_user``); the release is performed by the legitimate authority.
    """

    def test_release_on_pass_goes_to_node_last_claimer(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path, goal_owner="goal_owner")
        _gates(monkeypatch, tmp_path,
               action="stake_bonus",
               claim_id=claim_id,
               bonus_stake=1000,
               node_id="n1")
        result = _gates(monkeypatch, tmp_path,
                        user="goal_owner",
                        action="release_bonus",
                        claim_id=claim_id,
                        eval_verdict="pass",
                        node_last_claimer="daemon_holder")
        assert result["status"] == "ok"
        assert result["disposition"] == "released"
        assert result["recipient"] == "daemon_holder"
        assert result["net_disbursed"] + result["treasury_take"] == 1000

    def test_release_on_fail_refunds_to_recorded_staker(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path, goal_owner="goal_owner")
        _gates(monkeypatch, tmp_path,
               action="stake_bonus",
               claim_id=claim_id,
               bonus_stake=800,
               node_id="n1")
        result = _gates(monkeypatch, tmp_path,
                        user="goal_owner",
                        action="release_bonus",
                        claim_id=claim_id,
                        eval_verdict="fail",
                        node_last_claimer="daemon_holder")
        assert result["status"] == "ok"
        assert result["disposition"] == "refunded"
        # Refund returns to the RECORDED staker (claimed_by), never the caller.
        assert result["recipient"] == "test_user"

    def test_release_after_reclaim_refunds_immutable_staker(self, tmp_path, monkeypatch):
        """A gate re-claim rewrites claimed_by, but the legitimate owner/host
        release must still succeed and refund the IMMUTABLE original staker —
        a re-claimer can neither strand nor redirect the bonus (round-6)."""
        from workflow.storage import _connect
        _, _, claim_id = _seed_goal_and_claim(
            tmp_path, claimed_by="alice", goal_owner="goal_owner"
        )
        staked = _gates(monkeypatch, tmp_path, user="alice",
                        action="stake_bonus", claim_id=claim_id,
                        bonus_stake=900, node_id="n1")
        assert staked["status"] == "ok"
        assert staked["bonus_staker_id"] == "alice"

        # Mallory re-claims the same (branch, rung): claim_gate overwrites
        # claimed_by while preserving bonus_stake + the immutable bonus_staker_id.
        with _connect(tmp_path) as conn:
            conn.execute(
                "UPDATE gate_claims SET claimed_by = ? WHERE claim_id = ?",
                ("mallory", claim_id),
            )

        # The goal owner releases on fail: must succeed and refund ALICE, not
        # mallory, and must NOT be stranded by a stale claimed_by assertion.
        result = _gates(monkeypatch, tmp_path, user="goal_owner",
                        action="release_bonus", claim_id=claim_id,
                        eval_verdict="fail", node_last_claimer="daemon_holder")
        assert result["status"] == "ok"
        assert result["disposition"] == "refunded"
        assert result["recipient"] == "alice"

    def test_release_by_host_succeeds(self, tmp_path, monkeypatch):
        """The configured host is a legitimate gate-outcome authority."""
        _, _, claim_id = _seed_goal_and_claim(tmp_path, goal_owner="goal_owner")
        _gates(monkeypatch, tmp_path,
               action="stake_bonus",
               claim_id=claim_id,
               bonus_stake=600,
               node_id="n1")
        result = _gates(monkeypatch, tmp_path,
                        user="ops_host", host_user="ops_host",
                        action="release_bonus",
                        claim_id=claim_id,
                        eval_verdict="pass",
                        node_last_claimer="daemon_holder")
        assert result["status"] == "ok"
        assert result["disposition"] == "released"
        assert result["recipient"] == "daemon_holder"

    # ── Cross-actor authorization (slice1a review CRITICAL — round 3) ───────────

    def test_release_rejected_for_arbitrary_caller_no_balance_moves(
        self, tmp_path, monkeypatch,
    ):
        """A write-scoped caller who is neither owner/host/cap cannot release.

        Proves fail-without: the bonus stake stays on the claim, no settlement
        is recorded, and the treasury take is not credited.
        """
        from workflow.storage import _connect

        _, _, claim_id = _seed_goal_and_claim(tmp_path, goal_owner="goal_owner")
        _gates(monkeypatch, tmp_path,
               action="stake_bonus",
               claim_id=claim_id,
               bonus_stake=1000,
               node_id="n1")
        result = _gates(monkeypatch, tmp_path,
                        user="random_attacker",
                        action="release_bonus",
                        claim_id=claim_id,
                        eval_verdict="pass",
                        node_last_claimer="random_attacker")
        assert result["status"] == "rejected"
        assert "not permitted" in result["error"].lower()

        # No money moved: stake intact, no settlement, no treasury credit. The
        # settlement/treasury tables are created lazily on first disbursement,
        # so their absence is itself proof that no value moved; a present-but-
        # empty table is equally valid.
        def _count_or_zero(conn, table: str) -> int:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if exists is None:
                return 0
            return conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]

        with _connect(tmp_path) as conn:
            row = conn.execute(
                "SELECT bonus_stake FROM gate_claims WHERE claim_id = ?",
                (claim_id,),
            ).fetchone()
            assert row["bonus_stake"] == 1000
            assert _count_or_zero(conn, "pending_settlement") == 0
            assert _count_or_zero(conn, "treasury_balance") == 0

    def test_release_rejected_for_staker_self_adjudication(self, tmp_path, monkeypatch):
        """The staker cannot adjudicate their own gate outcome (self-payout)."""
        _, _, claim_id = _seed_goal_and_claim(
            tmp_path, claimed_by="staker_self", goal_owner="goal_owner",
        )
        _gates(monkeypatch, tmp_path,
               user="staker_self",
               action="stake_bonus",
               claim_id=claim_id,
               bonus_stake=500,
               node_id="n1")
        result = _gates(monkeypatch, tmp_path,
                        user="staker_self",
                        action="release_bonus",
                        claim_id=claim_id,
                        eval_verdict="pass",
                        node_last_claimer="staker_self")
        assert result["status"] == "rejected"
        assert "not permitted" in result["error"].lower()

    def test_release_rejected_for_unknown_claim(self, tmp_path, monkeypatch):
        _seed_goal_and_claim(tmp_path, goal_owner="goal_owner")
        result = _gates(monkeypatch, tmp_path,
                        user="goal_owner",
                        action="release_bonus",
                        claim_id="no-such-claim",
                        eval_verdict="pass",
                        node_last_claimer="daemon_holder")
        assert result["status"] == "rejected"
        assert "not found" in result["error"].lower()

    def test_release_rejects_missing_verdict(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path, goal_owner="goal_owner")
        _gates(monkeypatch, tmp_path,
               action="stake_bonus",
               claim_id=claim_id,
               bonus_stake=500,
               node_id="n1")
        result = _gates(monkeypatch, tmp_path,
                        user="goal_owner",
                        action="release_bonus",
                        claim_id=claim_id,
                        node_last_claimer="daemon_holder")
        assert result["status"] == "rejected"
        assert "eval_verdict" in result["error"].lower()

    def test_release_rejects_invalid_verdict(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path, goal_owner="goal_owner")
        _gates(monkeypatch, tmp_path,
               action="stake_bonus",
               claim_id=claim_id,
               bonus_stake=500,
               node_id="n1")
        result = _gates(monkeypatch, tmp_path,
                        user="goal_owner",
                        action="release_bonus",
                        claim_id=claim_id,
                        eval_verdict="maybe",
                        node_last_claimer="daemon_holder")
        assert result["status"] == "rejected"

    def test_release_rejects_no_stake(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path, goal_owner="goal_owner")
        result = _gates(monkeypatch, tmp_path,
                        user="goal_owner",
                        action="release_bonus",
                        claim_id=claim_id,
                        eval_verdict="pass",
                        node_last_claimer="daemon_holder")
        assert result["status"] == "rejected"
        assert "no bonus" in result["error"].lower()

    def test_release_rejects_missing_node_last_claimer(self, tmp_path, monkeypatch):
        _, _, claim_id = _seed_goal_and_claim(tmp_path, goal_owner="goal_owner")
        _gates(monkeypatch, tmp_path,
               action="stake_bonus",
               claim_id=claim_id,
               bonus_stake=500,
               node_id="n1")
        result = _gates(monkeypatch, tmp_path,
                        user="goal_owner",
                        action="release_bonus",
                        claim_id=claim_id,
                        eval_verdict="pass")
        assert result["status"] == "rejected"

    def test_payout_invariant_net_plus_treasury_equals_stake(self, tmp_path, monkeypatch):
        """net + treasury == original stake for any verdict."""
        _, _, claim_id = _seed_goal_and_claim(tmp_path, goal_owner="goal_owner")
        stake = 9999
        _gates(monkeypatch, tmp_path,
               action="stake_bonus",
               claim_id=claim_id,
               bonus_stake=stake,
               node_id="n1")
        result = _gates(monkeypatch, tmp_path,
                        user="goal_owner",
                        action="release_bonus",
                        claim_id=claim_id,
                        eval_verdict="pass",
                        node_last_claimer="daemon_holder")
        assert result["net_disbursed"] + result["treasury_take"] == stake


# ── Pure business logic unit tests ────────────────────────────────────────────

class TestGatesActionsUnit:
    """Unit tests for workflow/gates/actions.py business logic (no MCP layer)."""

    def test_validate_stake_amount_valid(self):
        from workflow.gates.actions import validate_stake_amount
        stake, err = validate_stake_amount(500)
        assert stake == 500
        assert err is None

    def test_validate_stake_amount_zero(self):
        from workflow.gates.actions import validate_stake_amount
        stake, err = validate_stake_amount(0)
        assert stake == 0
        assert err is None

    def test_validate_stake_amount_negative_rejected(self):
        from workflow.gates.actions import validate_stake_amount
        stake, err = validate_stake_amount(-1)
        assert err is not None

    def test_validate_stake_amount_non_numeric_rejected(self):
        from workflow.gates.actions import validate_stake_amount
        _, err = validate_stake_amount("abc")
        assert err is not None

    def test_compute_bonus_payout_invariant(self):
        from workflow.gates.actions import compute_bonus_payout
        for stake in range(0, 10_001, 100):
            net, treasury = compute_bonus_payout(stake)
            assert net + treasury == stake, f"invariant broken at stake={stake}"

    def test_compute_bonus_payout_1pct_take(self):
        from workflow.gates.actions import compute_bonus_payout
        net, treasury = compute_bonus_payout(10_000)
        assert treasury == 100
        assert net == 9_900
