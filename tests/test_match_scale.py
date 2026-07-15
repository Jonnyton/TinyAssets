"""Differential + scale gates for match.best_execution (2026-07-11).

The reference implementation below is the original covering-DP from the
2026-07-08 sprint, kept verbatim as the executable spec. The production
implementation must agree with it exactly (cost AND tie-broken ids) on
randomized tie-heavy books, and must clear large books in bounded time.
"""
import random
import time

from tinyassets.paid_market.match import BookOffer, MatchError, best_execution


def _reference_dp(offers, need_mtok):
    """Original O(n*need) covering DP — executable spec, do not optimize."""
    seen = set()
    for o in offers:
        o.validate()
        if o.offer_id in seen:
            raise MatchError(f"duplicate offer_id {o.offer_id!r}")
        seen.add(o.offer_id)
    if sum(o.size_mtok for o in offers) < need_mtok:
        return None
    ordered = sorted(
        offers, key=lambda o: (o.price_micros_per_mtok, o.size_mtok, o.offer_id)
    )
    dp = [None] * (need_mtok + 1)
    dp[0] = (0, 0, ())

    def better(a, b):
        if a[0] != b[0]:
            return a[0] < b[0]
        if a[1] != b[1]:
            return a[1] < b[1]
        return a[2] < b[2]

    for o in ordered:
        for c in range(need_mtok, -1, -1):
            cur = dp[c]
            if cur is None:
                continue
            nc = min(need_mtok, c + o.size_mtok)
            cand = (
                cur[0] + o.cost_micros,
                cur[1] + o.size_mtok,
                tuple(sorted(cur[2] + (o.offer_id,))),
            )
            if dp[nc] is None or better(cand, dp[nc]):
                dp[nc] = cand
    cost, _size, ids = dp[need_mtok]
    return cost, list(ids)


def test_greedy_trap_from_module_docstring():
    offers = [
        BookOffer(offer_id=f"s{i}", size_mtok=1, price_micros_per_mtok=5_000_000)
        for i in range(9)
    ] + [BookOffer(offer_id="big", size_mtok=10, price_micros_per_mtok=4_000_000)]
    cost, ids = best_execution(offers, 9)
    assert ids == ["big"]
    assert cost == 40_000_000


def test_differential_vs_reference_dp_tie_heavy():
    rng = random.Random(42)
    for _ in range(1000):
        n = rng.randint(0, 14)
        offers = [
            BookOffer(
                offer_id=f"o{i:02d}",
                size_mtok=rng.choice([1, 10, 100]),
                price_micros_per_mtok=rng.choice([3, 3, 5, 5, 7, 40, 100, 101]),
            )
            for i in range(n)
        ]
        total = sum(o.size_mtok for o in offers)
        need = rng.randint(1, max(1, total + rng.choice([0, 0, 0, 5])))
        assert best_execution(offers, need) == _reference_dp(offers, need)


def test_determinism_repeat_calls_identical():
    rng = random.Random(7)
    offers = [
        BookOffer(
            offer_id=f"o{i}",
            size_mtok=rng.choice([1, 10, 100]),
            price_micros_per_mtok=rng.choice([5, 5, 9]),
        )
        for i in range(200)
    ]
    first = best_execution(offers, 333)
    for _ in range(5):
        rng.shuffle(offers)  # input order must not matter
        assert best_execution(offers, 333) == first


def test_scale_gate_100k_offer_book():
    rng = random.Random(2)
    offers = [
        BookOffer(
            offer_id=f"o{i}",
            size_mtok=rng.choice([1, 10, 100]),
            price_micros_per_mtok=rng.randint(1, 10_000),
        )
        for i in range(100_000)
    ]
    t0 = time.time()
    result = best_execution(offers, 5_000)
    elapsed = time.time() - t0
    assert result is not None
    # generous CI bound; measured ~0.3s. The old DP took hours here.
    assert elapsed < 3.0, f"clearing took {elapsed:.1f}s"
