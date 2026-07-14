"""Best execution over standard-size forward offers — exact, pure (Wave 2).

A buyer needs >= N Mtok in one bucket; the book holds discrete offers
of standard sizes (1/10/100 Mtok) at per-Mtok prices. Choosing the
cheapest covering subset is a 0/1 covering knapsack, and the intuitive
greedy (cheapest unit price first) is WRONG: needing 9 Mtok with nine
1-Mtok offers at 5.00 and one 10-Mtok offer at 4.00, greedy pays 45.00
for the small offers while the single big offer covers everything for
40.00. This module solves it exactly.

Guarantees:
  * **Optimal**: minimum total cost among all subsets covering need.
  * **Deterministic**: ties broken by (total cost, total size, offer-id
    tuple lexicographic) so every node computes the identical fill —
    consensus-critical for a distributed book.
  * **Honest failure**: insufficient supply returns None, never a
    partial fill pretending to be an answer (partial-fill policy is a
    caller decision, made explicitly).

Complexity O(n_offers × need_mtok): with standard sizes and realistic
needs (hundreds of Mtok) this is microseconds.
"""

from __future__ import annotations

from dataclasses import dataclass

from tinyassets.paid_market.forwards import ForwardError

__all__ = ["MatchError", "BookOffer", "best_execution"]


class MatchError(ForwardError):
    """Raised on invalid matching inputs."""


@dataclass(frozen=True)
class BookOffer:
    offer_id: str
    size_mtok: int
    price_micros_per_mtok: int

    @property
    def cost_micros(self) -> int:
        return self.size_mtok * self.price_micros_per_mtok

    def validate(self) -> None:
        if not self.offer_id:
            raise MatchError("offer_id must be non-empty")
        if self.size_mtok not in (1, 10, 100):
            raise MatchError("size_mtok must be a standard size (1, 10, 100)")
        if (
            not isinstance(self.price_micros_per_mtok, int)
            or isinstance(self.price_micros_per_mtok, bool)
            or self.price_micros_per_mtok <= 0
        ):
            raise MatchError("price_micros_per_mtok must be a positive int")



def best_execution(
    offers: list[BookOffer],
    need_mtok: int,
) -> tuple[int, list[str]] | None:
    """Cheapest subset of ``offers`` whose sizes sum to >= need_mtok.

    Returns ``(total_cost_micros, [offer_id, ...])`` with ids in the
    deterministic canonical order, or None if total supply < need.

    Exact and deterministic (ties broken by total cost, then total
    size, then lexicographic offer-id tuple) — identical results to
    the reference covering-DP, proven by the differential test in the
    suite. Exploits the standard-size constraint (1/10/100): within a
    size bucket the c cheapest offers (canonical order) are always an
    optimal choice of c, so the search space collapses to counts per
    bucket — O(need^2/1000) candidate combinations with O(1) cost
    lookups via prefix sums, instead of O(n_offers * need) DP cells
    with tuple rebuilds. 100k-offer books clear in milliseconds.
    """
    if not isinstance(need_mtok, int) or isinstance(need_mtok, bool):
        raise MatchError("need_mtok must be int")
    if need_mtok <= 0:
        raise MatchError("need_mtok must be > 0")
    seen: set[str] = set()
    for o in offers:
        o.validate()
        if o.offer_id in seen:
            raise MatchError(f"duplicate offer_id {o.offer_id!r}")
        seen.add(o.offer_id)

    if sum(o.size_mtok for o in offers) < need_mtok:
        return None

    # Bucket by standard size; canonical order inside each bucket.
    # For any fixed count c taken from a bucket, the first c offers in
    # (price, offer_id) order are minimal-cost, and among equal-cost
    # choices have the lexicographically-smallest id tuple (equal-price
    # swaps can only introduce larger ids). So prefixes are sufficient.
    buckets: dict[int, list[BookOffer]] = {1: [], 10: [], 100: []}
    for o in offers:
        buckets[o.size_mtok].append(o)
    for size in buckets:
        buckets[size].sort(key=lambda o: (o.price_micros_per_mtok, o.offer_id))

    # Prefix cost sums: prefix[size][c] = cost of taking the c cheapest.
    prefix: dict[int, list[int]] = {}
    for size, bk in buckets.items():
        acc = [0]
        for o in bk:
            acc.append(acc[-1] + o.cost_micros)
        prefix[size] = acc

    n1, n10, n100 = len(buckets[1]), len(buckets[10]), len(buckets[100])

    best: tuple[int, int, tuple[int, int, int]] | None = None  # (cost, size, counts)
    best_ids: tuple[str, ...] | None = None  # lazy; built only on ties

    def ids_for(counts: tuple[int, int, int]) -> tuple[str, ...]:
        c1, c10, c100 = counts
        picked = (
            [o.offer_id for o in buckets[1][:c1]]
            + [o.offer_id for o in buckets[10][:c10]]
            + [o.offer_id for o in buckets[100][:c100]]
        )
        return tuple(sorted(picked))

    # Taking more of a size than needed for coverage is dominated
    # (prices are strictly positive), so counts are bounded by the
    # residual need at each level.
    max_c100 = min(n100, -(-need_mtok // 100))
    for c100 in range(max_c100 + 1):
        rem_after_100 = max(0, need_mtok - 100 * c100)
        max_c10 = min(n10, -(-rem_after_100 // 10))
        for c10 in range(max_c10 + 1):
            c1 = max(0, rem_after_100 - 10 * c10)
            if c1 > n1:
                continue  # infeasible; a larger c10/c100 covers it
            cost = prefix[100][c100] + prefix[10][c10] + prefix[1][c1]
            size = 100 * c100 + 10 * c10 + c1
            counts = (c1, c10, c100)
            if best is None or cost < best[0] or (
                cost == best[0] and size < best[1]
            ):
                best = (cost, size, counts)
                best_ids = None  # invalidate lazy ids
            elif cost == best[0] and size == best[1]:
                if best_ids is None:
                    best_ids = ids_for(best[2])
                cand_ids = ids_for(counts)
                if cand_ids < best_ids:
                    best = (cost, size, counts)
                    best_ids = cand_ids

    # Supply check above guarantees at least one feasible combination.
    assert best is not None
    cost, _size, counts = best
    if best_ids is None:
        best_ids = ids_for(counts)
    return cost, list(best_ids)
