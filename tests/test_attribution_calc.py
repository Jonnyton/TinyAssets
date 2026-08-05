"""Tests for tinyassets/attribution/calc.py — Task #39."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from tinyassets.attribution.schema import AttributionCredit, AttributionEdge


def _edge(parent: str, child: str, depth: int = 1) -> AttributionEdge:
    return AttributionEdge(
        edge_id=f"{parent}-{child}",
        parent_id=parent,
        child_id=child,
        parent_kind="branch",
        child_kind="branch",
        generation_depth=depth,
        contribution_kind="remix",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _credit(actor: str, artifact: str, gen_depth: int = 0) -> AttributionCredit:
    return AttributionCredit(
        credit_id=f"{actor}-{artifact}",
        artifact_id=artifact,
        artifact_kind="branch",
        actor_id=actor,
        credit_share=1.0,
        royalty_share=0.0,
        generation_depth=gen_depth,
        contribution_kind="original" if gen_depth == 0 else "remix",
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )


def _credit_with_identity(actor: str, artifact: str) -> AttributionCredit:
    return AttributionCredit(
        credit_id=f"{actor}-{artifact}",
        artifact_id=artifact,
        artifact_kind="branch",
        actor_id=actor,
        owner_user_id=f"owner-{actor}",
        daemon_id=f"daemon::{actor}",
        runtime_instance_id=f"runtime-{actor}",
        worker_id=f"worker-{actor}",
        credit_share=1.0,
        royalty_share=0.0,
        generation_depth=0,
        contribution_kind="original",
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )


# ── helper assertions ────────────────────────────────────────────────────────


def _assert_sums_to_one(shares: dict[str, float]) -> None:
    total = sum(shares.values())
    assert math.isclose(total, 1.0, rel_tol=1e-6), (
        f"Shares should sum to 1.0, got {total}: {shares}"
    )


# ── compute_credit_shares (via credits) ──────────────────────────────────────


class TestComputeCreditSharesFromCredits:
    def test_single_author_gets_full_share(self):
        from tinyassets.attribution.calc import compute_credit_shares
        credits = [_credit("alice", "art-1", gen_depth=0)]
        shares = compute_credit_shares(edges=[], credits=credits)
        assert shares == {"alice": pytest.approx(1.0)}

    def test_two_authors_same_generation_split_equally(self):
        from tinyassets.attribution.calc import compute_credit_shares
        credits = [
            _credit("alice", "art-1", gen_depth=0),
            _credit("bob", "art-1", gen_depth=0),
        ]
        shares = compute_credit_shares(edges=[], credits=credits)
        assert shares["alice"] == pytest.approx(0.5)
        assert shares["bob"] == pytest.approx(0.5)
        _assert_sums_to_one(shares)

    def test_identity_fields_do_not_change_credit_split(self):
        from tinyassets.attribution.calc import compute_credit_shares
        credits = [
            _credit_with_identity("alice", "art-1"),
            _credit_with_identity("bob", "art-1"),
        ]
        shares = compute_credit_shares(edges=[], credits=credits)
        assert shares["alice"] == pytest.approx(0.5)
        assert shares["bob"] == pytest.approx(0.5)
        _assert_sums_to_one(shares)

    def test_two_generation_chain_depth_decay(self):
        """Gen 0 gets weight 1.0, gen 1 gets weight 0.5. Normalized: 2/3, 1/3."""
        from tinyassets.attribution.calc import compute_credit_shares
        credits = [
            _credit("alice", "art-leaf", gen_depth=0),
            _credit("bob", "art-parent", gen_depth=1),
        ]
        shares = compute_credit_shares(edges=[], credits=credits)
        # alice: 1.0 / (1.0 + 0.5) = 2/3; bob: 0.5 / 1.5 = 1/3
        assert shares["alice"] == pytest.approx(2 / 3, rel=1e-5)
        assert shares["bob"] == pytest.approx(1 / 3, rel=1e-5)
        _assert_sums_to_one(shares)

    def test_three_generation_chain_decay(self):
        """Weights: gen0=1, gen1=0.5, gen2=0.25. Total=1.75."""
        from tinyassets.attribution.calc import compute_credit_shares
        credits = [
            _credit("a", "art-0", gen_depth=0),
            _credit("b", "art-1", gen_depth=1),
            _credit("c", "art-2", gen_depth=2),
        ]
        shares = compute_credit_shares(edges=[], credits=credits)
        assert shares["a"] == pytest.approx(1.0 / 1.75, rel=1e-5)
        assert shares["b"] == pytest.approx(0.5 / 1.75, rel=1e-5)
        assert shares["c"] == pytest.approx(0.25 / 1.75, rel=1e-5)
        _assert_sums_to_one(shares)

    def test_multi_fork_same_generation_splits_equally(self):
        """Two authors at gen 1 split gen-1 weight equally between themselves.

        Weights: alice (gen0) = 1.0; bob (gen1) = 0.25; carol (gen1) = 0.25.
        Total raw = 1.5. Normalized: alice = 2/3, bob = 1/6, carol = 1/6.
        """
        from tinyassets.attribution.calc import compute_credit_shares
        credits = [
            _credit("alice", "art-leaf", gen_depth=0),
            _credit("bob", "art-p1", gen_depth=1),
            _credit("carol", "art-p2", gen_depth=1),
        ]
        shares = compute_credit_shares(edges=[], credits=credits)
        # bob and carol must have equal shares (symmetric)
        assert shares["bob"] == pytest.approx(shares["carol"])
        # alice at gen 0 gets more than bob or carol individually
        assert shares["alice"] > shares["bob"]
        _assert_sums_to_one(shares)

    def test_depth_cap_truncates_deep_lineage(self):
        """Authors beyond depth_cap contribute nothing (as if lineage ends there)."""
        from tinyassets.attribution.calc import compute_credit_shares
        credits = [
            _credit("alice", "art-0", gen_depth=0),
            _credit("bob", "art-deep", gen_depth=100),
        ]
        shares = compute_credit_shares(edges=[], credits=credits, depth_cap=5)
        # bob's depth 100 is clamped to 5: weight 2^(-5)=0.03125 vs alice's 1.0
        # both still included (just with capped weight)
        assert "alice" in shares
        assert "bob" in shares
        _assert_sums_to_one(shares)

    def test_empty_credits_returns_empty(self):
        from tinyassets.attribution.calc import compute_credit_shares
        assert compute_credit_shares(edges=[], credits=[]) == {}

    def test_shares_sum_to_one(self):
        from tinyassets.attribution.calc import compute_credit_shares
        credits = [
            _credit("a", "x", gen_depth=0),
            _credit("b", "x", gen_depth=1),
            _credit("c", "x", gen_depth=1),
            _credit("d", "x", gen_depth=2),
        ]
        shares = compute_credit_shares(edges=[], credits=credits)
        _assert_sums_to_one(shares)


# ── compute_credit_shares (via edges) ────────────────────────────────────────


class TestComputeCreditSharesFromEdges:
    def test_single_parent_gets_full_share(self):
        """A → B: artifact A is the sole contributor; gets 100%."""
        from tinyassets.attribution.calc import compute_credit_shares
        edges = [_edge("art-a", "art-b", depth=1)]
        shares = compute_credit_shares(edges=edges)
        assert shares == {"art-a": pytest.approx(1.0)}

    def test_two_parents_same_depth_split_equally(self):
        """A → C and B → C at depth 1: A and B each get 50%."""
        from tinyassets.attribution.calc import compute_credit_shares
        edges = [
            _edge("art-a", "art-c", depth=1),
            _edge("art-b", "art-c", depth=1),
        ]
        shares = compute_credit_shares(edges=edges)
        assert shares["art-a"] == pytest.approx(0.5)
        assert shares["art-b"] == pytest.approx(0.5)

    def test_cycle_detection_raises(self):
        """A → B and B → A is a cycle; should raise ValueError."""
        from tinyassets.attribution.calc import compute_credit_shares
        edges = [_edge("art-a", "art-b"), _edge("art-b", "art-a")]
        with pytest.raises(ValueError, match="[Cc]ycle"):
            compute_credit_shares(edges=edges)

    def test_depth_cap_respected(self):
        """Chain longer than depth_cap should not crash; deep ancestors are ignored."""
        from tinyassets.attribution.calc import compute_credit_shares
        # Build linear chain: art-0 → art-1 → ... → art-20 (art-20 is the leaf)
        edges = [_edge(f"art-{i}", f"art-{i+1}", depth=i + 1) for i in range(20)]
        shares = compute_credit_shares(edges=edges, depth_cap=5)
        # art-20 is leaf (depth=0, excluded). art-19..art-15 are depths 1..5 (included).
        # art-14..art-0 are beyond depth_cap=5 and must not appear.
        expected_contributors = {f"art-{19 - i}" for i in range(5)}  # art-19..art-15
        assert set(shares.keys()) == expected_contributors
        _assert_sums_to_one(shares)

    def test_no_edges_no_credits_returns_empty(self):
        from tinyassets.attribution.calc import compute_credit_shares
        assert compute_credit_shares(edges=[]) == {}


# ── compute_payout_shares ─────────────────────────────────────────────────────


class TestComputePayoutShares:
    def test_fee_goes_to_treasury(self):
        """1% of total_payout goes to _treasury."""
        from tinyassets.attribution.calc import compute_payout_shares
        credits = [_credit("alice", "art-1", gen_depth=0)]
        result = compute_payout_shares(
            edges=[], credits=credits, total_payout=100.0, fee_pct=0.01
        )
        assert result["_treasury"] == pytest.approx(1.0)
        assert result["alice"] == pytest.approx(99.0)

    def test_distributable_remainder_after_fee(self):
        """Two equal-weight authors split 99% of payout."""
        from tinyassets.attribution.calc import compute_payout_shares
        credits = [
            _credit("alice", "art-1", gen_depth=0),
            _credit("bob", "art-1", gen_depth=0),
        ]
        result = compute_payout_shares(
            edges=[], credits=credits, total_payout=100.0, fee_pct=0.01
        )
        # Payouts are integer MicroTokens, so 99 cannot split evenly in two.
        # Largest-remainder assigns the odd unit to the alphabetically-first
        # actor on a tie, giving 50/49 rather than 49.5/49.5. The total is
        # still exactly 100 — see test_split_always_conserves_the_total.
        assert result["_treasury"] == 1
        assert result["alice"] == 50
        assert result["bob"] == 49
        assert sum(result.values()) == 100

    def test_zero_payout_returns_zero_treasury(self):
        from tinyassets.attribution.calc import compute_payout_shares
        credits = [_credit("alice", "art-1")]
        result = compute_payout_shares(edges=[], credits=credits, total_payout=0.0)
        assert result == {"_treasury": pytest.approx(0.0)}

    def test_custom_fee_pct(self):
        from tinyassets.attribution.calc import compute_payout_shares
        credits = [_credit("alice", "art-1", gen_depth=0)]
        result = compute_payout_shares(
            edges=[], credits=credits, total_payout=100.0, fee_pct=0.05
        )
        assert result["_treasury"] == pytest.approx(5.0)
        assert result["alice"] == pytest.approx(95.0)

    def test_no_attribution_is_refused_not_absorbed(self):
        """A positive payout with nothing to attribute it to is REFUSED.

        Host decision 2026-08-05. This branch is only reachable when an
        artifact has no credits AND no lineage edges — a data-integrity
        failure, since `depth_cap` clamps a contributor's depth rather than
        filtering them out. Paying the gross to `_treasury` (the previous
        behaviour) would turn a missing-attribution bug into platform revenue
        and hide it; the old expectation of 1.0 was worse still, silently
        losing the other 99.
        """
        from tinyassets.attribution.calc import NoAttributionError, compute_payout_shares

        with pytest.raises(NoAttributionError, match="no attribution"):
            compute_payout_shares(
                edges=[], credits=[], total_payout=100.0, fee_pct=0.01
            )

    def test_split_always_conserves_the_total(self):
        """Nothing is created or destroyed by the split.

        The docstring on `compute_payout_shares` promises the result "sums
        exactly to total_payout" and nothing asserted it, which is how the
        no-attribution branch reached main losing 99 of every 100 units in one
        direction and the old test expectation lost it in the other. Swept
        across actor counts and fee rates so integer-rounding residue cannot
        hide in a single lucky case.
        """
        from tinyassets.attribution.calc import compute_payout_shares

        for n_actors in (1, 2, 3, 7, 11):
            for total in (1, 3, 100, 999, 100_000):
                for fee_pct in (0.0, 0.01, 0.05, 0.5):
                    credits = [
                        _credit(f"actor{i}", "art-1", gen_depth=i % 3)
                        for i in range(n_actors)
                    ]
                    result = compute_payout_shares(
                        edges=[],
                        credits=credits,
                        total_payout=float(total),
                        fee_pct=fee_pct,
                    )
                    assert sum(result.values()) == total, (
                        f"{n_actors} actors, total={total}, fee={fee_pct}: "
                        f"sum={sum(result.values())} != {total} ({result})"
                    )
                    assert all(v >= 0 for v in result.values()), result

    def test_treasury_takes_exactly_the_declared_fee(self):
        """The platform cut is the declared percentage, floored — no more.

        Pins the fee against the conservation invariant above: together they
        say the platform takes exactly its cut and contributors get all the
        rest, so neither can drift without a test going red.
        """
        from tinyassets.attribution.calc import compute_payout_shares

        for total, fee_pct, expected_fee in [
            (100, 0.01, 1),
            (100, 0.05, 5),
            (999, 0.01, 9),
            (1, 0.5, 0),
            (100, 0.0, 0),
        ]:
            result = compute_payout_shares(
                edges=[],
                credits=[_credit("alice", "art-1", gen_depth=0)],
                total_payout=float(total),
                fee_pct=fee_pct,
            )
            assert result["_treasury"] == expected_fee, (
                f"total={total} fee_pct={fee_pct}: "
                f"treasury={result['_treasury']} != {expected_fee}"
            )
