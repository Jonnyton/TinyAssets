"""Spot price index — pure computation, no transport.

Track E Waves 3a/3b (spec: docs/exec-plans/active/
2026-07-08-track-e-price-index-and-capacity-forwards.md §2).

Computes the per-capability composite spot quote from settled trades.
All money is integer micros-per-Mtok; all intermediate arithmetic is
exact (int / fractions.Fraction). No floats anywhere in the money path.

Manipulation posture implemented here:
  * VWAP over *settled* trades only (caller must pass settled trades).
  * Per-counterparty-pair weight cap (water-filling): no single
    (buyer, seller) pair's volume may exceed ``pair_share_cap_ppm`` of
    the capped total. Direction-insensitive, so A→B and B→A wash pairs
    share one cap bucket.
  * Ceiling clamp: the published VWAP never exceeds the hosted-API
    ceiling; the raw value is retained and the quote is flagged.

Fail-loud per AGENTS.md Hard Rule 8: invalid inputs raise IndexError_
(never silently skipped/coerced).
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

__all__ = [
    "IndexError_",
    "SettledTrade",
    "SpotQuote",
    "capped_pair_weights",
    "compute_vwap",
    "compute_spot_quote",
    "MICROS_PER_UNIT",
    "PPM",
    "DEFAULT_MIN_TRADES",
    "DEFAULT_PAIR_SHARE_CAP_PPM",
    "WINDOW_PRIMARY_SECONDS",
    "WINDOW_WIDENED_SECONDS",
]

MICROS_PER_UNIT = 1_000_000
PPM = 1_000_000

DEFAULT_MIN_TRADES = 3
DEFAULT_PAIR_SHARE_CAP_PPM = 250_000  # 25% — one pair can't be >1/4 of weight
WINDOW_PRIMARY_SECONDS = 24 * 3600  # '24h'
WINDOW_WIDENED_SECONDS = 7 * 24 * 3600  # '7d'


class IndexError_(ValueError):
    """Raised on invalid index inputs. Trailing underscore avoids
    shadowing the builtin ``IndexError``."""


@dataclass(frozen=True)
class SettledTrade:
    """One settled, dispute-window-cleared trade (a price observation)."""

    capability_id: str
    price_micros_per_mtok: int  # unit price actually settled at
    tokens_out: int  # completion tokens delivered (VWAP weight)
    buyer_id: str
    seller_id: str
    settled_at: int  # unix seconds, UTC

    def validate(self) -> None:
        if not self.capability_id:
            raise IndexError_("trade missing capability_id")
        if not isinstance(self.price_micros_per_mtok, int) or isinstance(
            self.price_micros_per_mtok, bool
        ):
            raise IndexError_("price_micros_per_mtok must be int")
        if self.price_micros_per_mtok <= 0:
            raise IndexError_("price_micros_per_mtok must be > 0")
        if not isinstance(self.tokens_out, int) or isinstance(self.tokens_out, bool):
            raise IndexError_("tokens_out must be int")
        if self.tokens_out <= 0:
            raise IndexError_("tokens_out must be > 0")
        if not self.buyer_id or not self.seller_id:
            raise IndexError_("trade missing buyer_id/seller_id")
        if not isinstance(self.settled_at, int) or isinstance(self.settled_at, bool):
            raise IndexError_("settled_at must be int unix seconds")

    @property
    def pair_key(self) -> tuple[str, str]:
        """Direction-insensitive counterparty pair key."""
        a, b = sorted((self.buyer_id, self.seller_id))
        return (a, b)


@dataclass(frozen=True)
class SpotQuote:
    """Composite spot quote for one capability (spec §2)."""

    capability_id: str
    vwap_micros: int | None  # published (post-clamp) VWAP, None if too thin
    raw_vwap_micros: int | None  # pre-clamp VWAP (== vwap unless clamped)
    vwap_window: str | None  # '24h' | '7d' | None
    n_trades: int
    n_pairs: int  # distinct counterparty pairs in the window (diversity)
    best_ask_micros: int | None
    ceiling_micros: int | None
    above_ceiling: bool  # True → raw VWAP exceeded ceiling; vwap clamped
    as_of: int  # unix seconds the quote was computed at


def capped_pair_weights(
    pair_volumes: dict[tuple[str, str], int],
    share_cap_ppm: int,
) -> dict[tuple[str, str], Fraction]:
    """Water-filling weight cap.

    Returns per-pair weights such that no pair's weight exceeds
    ``share_cap_ppm`` of the *capped* total, solving the fixed point

        T = sum_i min(v_i, c * T),   c = share_cap_ppm / PPM

    exactly with Fractions. Uncapped pairs keep their raw volume;
    capped pairs contribute exactly c*T.

    If the cap is infeasible (n_pairs * c <= 1, e.g. 4 pairs at 25% —
    everyone would be capped and T collapses toward 0), pairs get EQUAL
    weight instead. Returning raw volumes here would let a single whale
    pair print the price in any thin (<= 1/c pairs) market — confirmed
    exploit, review pass A finding A-2. Equal weighting removes the
    volume lever entirely: in an n-pair market no pair exceeds 1/n
    influence regardless of wash volume. Callers surface ``n_pairs`` so
    consumers can judge diversity.
    """
    if not (0 < share_cap_ppm <= PPM):
        raise IndexError_("share_cap_ppm must be in (0, PPM]")
    for v in pair_volumes.values():
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            raise IndexError_("pair volumes must be positive ints")

    n = len(pair_volumes)
    c = Fraction(share_cap_ppm, PPM)
    if n == 0:
        return {}
    if n * c <= 1:
        # Infeasible cap — every pair would bind; degenerate fixed point.
        # Equal weights (A-2): volume cannot buy influence in thin markets.
        return {k: Fraction(1) for k in pair_volumes}

    # Sort descending; determine the binding set greedily. With pairs
    # sorted v_1 >= v_2 >= ..., if the top-k are capped:
    #   T_k = S_rest / (1 - k*c),  S_rest = sum of the uncapped volumes.
    # The correct k is the largest one where v_k > c * T_k (cap binds)
    # and v_{k+1} <= c * T_k (next one doesn't). k = 0 (nobody capped)
    # is checked first.
    items = sorted(pair_volumes.items(), key=lambda kv: (-kv[1], kv[0]))
    volumes = [Fraction(v) for _, v in items]
    total_raw = sum(volumes)

    chosen_T: Fraction | None = None
    chosen_k = 0
    for k in range(0, n):
        s_rest = sum(volumes[k:], Fraction(0))
        denom = 1 - k * c
        if denom <= 0:
            break  # larger k only more infeasible
        T = s_rest / denom if k > 0 else total_raw
        cap_value = c * T
        top_ok = k == 0 or volumes[k - 1] > cap_value  # all top-k truly bind
        rest_ok = volumes[k] <= cap_value if k < n else True
        if top_ok and rest_ok:
            chosen_T = T
            chosen_k = k
            break
    if chosen_T is None:
        # Should be unreachable when n*c > 1; fail loud rather than guess.
        raise IndexError_("weight-cap fixed point not found")

    cap_value = c * chosen_T
    out: dict[tuple[str, str], Fraction] = {}
    for i, (key, _) in enumerate(items):
        out[key] = cap_value if i < chosen_k else volumes[i]
    return out


def compute_vwap(
    trades: list[SettledTrade],
    *,
    share_cap_ppm: int = DEFAULT_PAIR_SHARE_CAP_PPM,
) -> tuple[int, int]:
    """Volume-weighted average price over ``trades`` with pair caps.

    Returns ``(vwap_micros, n_pairs)``. VWAP is floored to int micros.
    Raises IndexError_ on empty input (callers gate on min_trades first).
    """
    if not trades:
        raise IndexError_("compute_vwap requires at least one trade")
    cap_id = trades[0].capability_id
    pair_volumes: dict[tuple[str, str], int] = {}
    pair_value: dict[tuple[str, str], int] = {}  # sum(price * tokens) per pair
    for t in trades:
        t.validate()
        if t.capability_id != cap_id:
            raise IndexError_("compute_vwap trades must share one capability_id")
        pair_volumes[t.pair_key] = pair_volumes.get(t.pair_key, 0) + t.tokens_out
        pair_value[t.pair_key] = (
            pair_value.get(t.pair_key, 0) + t.price_micros_per_mtok * t.tokens_out
        )

    weights = capped_pair_weights(pair_volumes, share_cap_ppm)
    num = Fraction(0)
    den = Fraction(0)
    for key, w in weights.items():
        # Pair's average price (exact), weighted by capped weight. Using
        # the pair-internal average keeps a capped pair from choosing
        # *which* of its own trades count.
        pair_avg = Fraction(pair_value[key], pair_volumes[key])
        num += pair_avg * w
        den += w
    if den == 0:
        raise IndexError_("zero total weight")  # unreachable with validation
    vwap = num / den
    return (int(vwap), len(pair_volumes))  # int() floors positive Fractions


def compute_spot_quote(
    *,
    capability_id: str,
    trades: list[SettledTrade],
    now: int,
    best_ask_micros: int | None,
    ceiling_micros: int | None,
    min_trades: int = DEFAULT_MIN_TRADES,
    share_cap_ppm: int = DEFAULT_PAIR_SHARE_CAP_PPM,
) -> SpotQuote:
    """Assemble the composite quote (spec §2 table).

    Window logic: trailing 24h; if fewer than ``min_trades`` settled
    trades, widen to 7d; if still thin, VWAP is None (no fabricated
    liveness). ``trades`` may contain any history; filtering happens
    here. Trades newer than ``now`` are rejected (clock discipline —
    a future-dated settlement is a bug upstream, not data).
    """
    if min_trades < 1:
        raise IndexError_("min_trades must be >= 1")
    if best_ask_micros is not None and best_ask_micros <= 0:
        raise IndexError_("best_ask_micros must be > 0 or None")
    if ceiling_micros is not None and ceiling_micros <= 0:
        raise IndexError_("ceiling_micros must be > 0 or None")

    for t in trades:
        t.validate()
        if t.capability_id != capability_id:
            raise IndexError_("trade capability_id mismatch")
        if t.settled_at > now:
            raise IndexError_("trade settled in the future")

    def _window(cutoff: int) -> list[SettledTrade]:
        return [t for t in trades if t.settled_at >= cutoff]

    selected: list[SettledTrade] = []
    window_label: str | None = None
    primary = _window(now - WINDOW_PRIMARY_SECONDS)
    if len(primary) >= min_trades:
        selected, window_label = primary, "24h"
    else:
        widened = _window(now - WINDOW_WIDENED_SECONDS)
        if len(widened) >= min_trades:
            selected, window_label = widened, "7d"

    raw_vwap: int | None = None
    vwap: int | None = None
    n_pairs = 0
    above_ceiling = False
    if window_label is not None:
        raw_vwap, n_pairs = compute_vwap(selected, share_cap_ppm=share_cap_ppm)
        vwap = raw_vwap
        if ceiling_micros is not None and raw_vwap > ceiling_micros:
            vwap = ceiling_micros  # clamp; never publish above ceiling
            above_ceiling = True

    return SpotQuote(
        capability_id=capability_id,
        vwap_micros=vwap,
        raw_vwap_micros=raw_vwap,
        vwap_window=window_label,
        n_trades=len(selected),
        n_pairs=n_pairs,
        best_ask_micros=best_ask_micros,
        ceiling_micros=ceiling_micros,
        above_ceiling=above_ceiling,
        as_of=now,
    )
