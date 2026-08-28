"""Tier resolution and the effect-quota gate.

Sits between the raw ledger (`storage/usage_ledger`) and the effect call sites. The
ledger knows how to reserve and settle; this module knows *how much* a given universe
is allowed and turns a refusal into something a caller can act on.

Two deliberate properties:

* **Free is the absence of a subscription**, not a separate plan record. Fewer states,
  less to drift out of sync.
* **An unresolvable tier falls back to FREE, never to unlimited.** A lookup failure
  must not silently hand out the paid tier.

Sizing is deliberately generous. Cost work on 2026-08-28 measured marginal cost per
user at roughly $0.12/month — the platform supplies no inference, and WorkOS is free
to a million MAU — so cost is not what should constrain the free tier. What should
constrain it is abuse reaching the outside world, which is why *effects* are the tight
dimension and runs are not.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass

TIER_FREE = "free"
TIER_PAID = "paid"

#: Rolling window all quotas are measured over.
_WINDOW_VAR = "TINYASSETS_USAGE_WINDOW_S"
_DEFAULT_WINDOW_S = 86_400.0  # one day

#: Effects. The billable dimension, and the only tight one.
_FREE_EFFECTS_VAR = "TINYASSETS_FREE_EFFECTS_PER_WINDOW"
_PAID_EFFECTS_VAR = "TINYASSETS_PAID_EFFECTS_PER_WINDOW"
_DEFAULT_FREE_EFFECTS = 100
_DEFAULT_PAID_EFFECTS = 5_000

#: Compute. A guard, not a product limit — sized so ordinary iterative debugging
#: never reaches it. The 2026-08-28 outage was caused by a limit tight enough to
#: catch honest work.
_FREE_COMPUTE_VAR = "TINYASSETS_FREE_COMPUTE_MINUTES"
_PAID_COMPUTE_VAR = "TINYASSETS_PAID_COMPUTE_MINUTES"
_DEFAULT_FREE_COMPUTE_MIN = 600.0
_DEFAULT_PAID_COMPUTE_MIN = 12_000.0

#: Storage. Capped, not charged — per-universe attribution is still wrong
#: (docs/concerns/2026-08-28-per-universe-storage-is-515mb-of-duplication.md), and
#: ~99% of the current footprint is our own duplicated provider runtime, which the
#: user did not put there.
_FREE_STORAGE_VAR = "TINYASSETS_FREE_STORAGE_MB"
_PAID_STORAGE_VAR = "TINYASSETS_PAID_STORAGE_MB"
_DEFAULT_FREE_STORAGE_MB = 2_000.0
_DEFAULT_PAID_STORAGE_MB = 20_000.0

#: Longest a single run may be charged for, so a wedged run cannot accrue forever.
_MAX_RUN_VAR = "TINYASSETS_MAX_CHARGEABLE_RUN_S"
_DEFAULT_MAX_RUN_S = 3_600.0


def _positive_number(var: str, default: float) -> float:
    """Read a positive finite number, announcing an unusable override rather than
    swallowing it. A misconfiguration must not silently become the default."""
    raw = os.environ.get(var, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value <= 0:
        print(
            f"{var}={raw!r} is not a positive number; using {default:g}",
            flush=True,
        )
        return default
    return value


@dataclass(frozen=True)
class TierLimits:
    """What one tier permits over the rolling window."""

    name: str
    effects: int
    compute_seconds: float
    storage_bytes: float
    window_seconds: float
    max_chargeable_run_seconds: float

    @property
    def is_paid(self) -> bool:
        return self.name == TIER_PAID


def window_seconds() -> float:
    return _positive_number(_WINDOW_VAR, _DEFAULT_WINDOW_S)


def max_chargeable_run_seconds() -> float:
    return _positive_number(_MAX_RUN_VAR, _DEFAULT_MAX_RUN_S)


def limits_for(tier: str) -> TierLimits:
    """Resolve a tier's limits. An unknown tier resolves to FREE, never unlimited."""
    normalized = (tier or "").strip().lower()
    if normalized != TIER_PAID:
        normalized = TIER_FREE
    paid = normalized == TIER_PAID
    effects = _positive_number(
        _PAID_EFFECTS_VAR if paid else _FREE_EFFECTS_VAR,
        float(_DEFAULT_PAID_EFFECTS if paid else _DEFAULT_FREE_EFFECTS),
    )
    compute_min = _positive_number(
        _PAID_COMPUTE_VAR if paid else _FREE_COMPUTE_VAR,
        _DEFAULT_PAID_COMPUTE_MIN if paid else _DEFAULT_FREE_COMPUTE_MIN,
    )
    storage_mb = _positive_number(
        _PAID_STORAGE_VAR if paid else _FREE_STORAGE_VAR,
        _DEFAULT_PAID_STORAGE_MB if paid else _DEFAULT_FREE_STORAGE_MB,
    )
    return TierLimits(
        name=normalized,
        effects=int(effects),
        compute_seconds=compute_min * 60.0,
        storage_bytes=storage_mb * 1024.0 * 1024.0,
        window_seconds=window_seconds(),
        max_chargeable_run_seconds=max_chargeable_run_seconds(),
    )


def settlement_key(*, sink: str, effect_key: str) -> str:
    """The ledger key for one effect — the receipt's own identity.

    Must match the receipt's `(idempotency_hint, sink)` primary key exactly, or a
    retried effect would reserve a second slot instead of finding its first.

    Hashed over a JSON-encoded PAIR rather than concatenated with a separator.
    Concatenation is not injective when a field can itself contain the separator:
    ``("a", "bc")`` and ``("ab", "c")`` produce the same string, and since
    `reserve_effect` treats an existing row as "same effect, proceed", one tuple
    could ride another's reservation and write with no budget of its own
    (Codex REJECT 2026-08-28 B). JSON encoding is injective over the pair, so the
    digest is too.
    """
    encoded = json.dumps([sink, effect_key], separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class QuotaRefusal:
    """Why a request was refused, and when it can succeed — never just 'try later'."""

    dimension: str
    limit: int | float
    tier: str
    retry_after_seconds: float

    def message(self) -> str:
        when = (
            f"{self.retry_after_seconds / 3600:.1f}h"
            if self.retry_after_seconds >= 3600
            else f"{max(1, round(self.retry_after_seconds / 60))}m"
        )
        return (
            f"{self.dimension} limit reached for the {self.tier} tier "
            f"(max {self.limit:g} per {self.window_label}); "
            f"capacity returns in about {when}."
        )

    @property
    def window_label(self) -> str:
        hours = window_seconds() / 3600
        return "24h" if abs(hours - 24) < 0.01 else f"{hours:g}h"


def _ledger():
    # Imported lazily so this module stays importable in contexts that never
    # touch the ledger (config readers, docs tooling).
    from tinyassets.storage import usage_ledger

    return usage_ledger


_ENFORCE_VAR = "TINYASSETS_USAGE_ENFORCEMENT"


def enforcement_enabled() -> bool:
    """Is usage ENFORCEMENT live? Default OFF — metering still records either way.

    Landing dark. Cross-family review (Codex, 2026-08-28, two rounds) established
    that settlement is not yet exactly-once: receipt finalization and the quota
    write are separate commits, so a crash between them strands a reservation, and
    `wiki_write_back` is a registered sink that writes unmetered. Those are real,
    and closing them properly needs the outbox this change's own spec asks for.

    Enforcing a quota whose accounting can drift means refusing a user's legitimate
    action on a number we do not trust — strictly worse than not enforcing. So the
    meter runs and records from day one (which is how we learn real usage), and the
    gate stays off until the outbox lands and one universe has been proven on it.
    """
    return (os.environ.get(_ENFORCE_VAR, "").strip().lower()) in (
        "1",
        "true",
        "yes",
        "on",
    )


def reserve_effect_quota(
    universe_dir,
    *,
    sink: str,
    effect_key: str,
    tier: str = TIER_FREE,
    now: float | None = None,
) -> QuotaRefusal | None:
    """Reserve effect budget before an outbound write.

    Returns ``None`` when the effect may proceed, or a ``QuotaRefusal`` the caller
    must surface *without* performing the write. This is a pre-flight control: an
    outbound write is irreversible, so a budget checked afterwards is an accounting
    record rather than a limit.
    """
    limits = limits_for(tier)
    admitted = _ledger().reserve_effect(
        universe_dir,
        settlement_key=settlement_key(sink=sink, effect_key=effect_key),
        limit=limits.effects,
        window_seconds=limits.window_seconds,
        now=now,
    )
    if admitted:
        return None
    if not enforcement_enabled():
        # Dark: the reservation was declined, and that is RECORDED, but we do not
        # act on it. Refusing on accounting we know can drift would be worse than
        # letting the action through.
        return None
    return QuotaRefusal(
        dimension="effect",
        limit=limits.effects,
        tier=limits.name,
        retry_after_seconds=limits.window_seconds,
    )


def release_effect_quota(universe_dir, *, sink: str, effect_key: str) -> bool:
    """Return budget after a write that did not reach the world."""
    return _ledger().release_effect(
        universe_dir,
        settlement_key=settlement_key(sink=sink, effect_key=effect_key),
    )


def settle_effect_quota(
    universe_dir, *, sink: str, effect_key: str, now: float | None = None
) -> bool:
    """Commit budget for an effect that reached the world.

    Safe to call from every success path — ordinary finalization, reconciliation,
    and confirmed-hold activation — because the underlying commit only fires on the
    reserved->committed transition. A second call for the same effect settles
    nothing and returns False, which is what stops a replayed finalization from
    double-charging.
    """
    return _ledger().commit_effect(
        universe_dir,
        settlement_key=settlement_key(sink=sink, effect_key=effect_key),
        now=now,
    )
