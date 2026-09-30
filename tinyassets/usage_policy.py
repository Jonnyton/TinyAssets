"""What one account tier permits: THE table, and the only one.

Founder directive 2026-09-30, verbatim: *"usage limits for accounts should really
only be based on 2 things, total gibs thier universe takes up in the cloud. and how
many agent calls thier universe can simoltaniously run ... free users have less cloud
storage space and less simaltaniouse agent runs."*

So a tier is two numbers:

* ``seats`` — concurrent agent calls (`tinyassets.universe_seats`). Over the limit,
  work QUEUES; it is never refused and never dropped.
* ``storage_bytes`` — the universe's whole cloud footprint
  (`tinyassets.universe_storage`). At the quota, byte-adding writes are refused;
  reads never break.

Both live here because a second definition of the same fact is the defect class
behind the longest review loops in this repo. This module already owned
``storage_bytes`` and already resolved the tier; ``seats`` joins it rather than
starting a rival table.

Three deliberate properties, two of them inherited and still right:

* **Free is the absence of a subscription**, not a separate plan record. Fewer
  states, less to drift out of sync.
* **An unresolvable tier falls back to FREE, never to unlimited.** A lookup failure
  must not silently hand out the paid tier.
* **Seats queue, storage refuses.** That asymmetry is the directive's: asking for
  more concurrency than fits is not a user error, so it waits. Asking to store
  bytes that do not fit cannot wait for anything, so it is refused — with the
  numbers and an upgrade link, never a bare failure.

Sizing note, still accurate: cost work on 2026-08-28 measured marginal cost per user
at roughly $0.12/month — the platform supplies no inference, and WorkOS is free to a
million MAU — so cost is not what constrains the free tier. Seats constrain
concurrency on shared hardware; storage constrains the box.

`effects` and `compute_seconds` below are the retired rolling-window meters. They are
deleted with their call sites in the second half of this change; nothing new should
read them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from dataclasses import dataclass
from urllib.parse import quote

_log = logging.getLogger(__name__)

TIER_FREE = "free"
TIER_PAID = "paid"

#: Weakest first. `upgrade_url` returns None for the last entry, so a future middle
#: tier needs no change at the call sites -- "is there a tier above this one" is a
#: question about the table, never a `tier != "free"` test at a message site.
TIER_ORDER = (TIER_FREE, TIER_PAID)

#: Seats: concurrent agent calls per universe.
#:
#: Free is 3 rather than the directive's "e.g. 2" (approved 2026-09-30). It is a
#: PRODUCT choice -- two simultaneous background agents on free -- and not a
#: necessity. The necessity argument was refuted: 2 seats with 1 reserved gives one
#: running background agent and three waiting, which is a queue, and does
#: demonstrate what the founder asked to see (astra round 1, finding 19). Keeping
#: the honest version because an argument that does not hold is worse than none.
#:
#: What IS load-bearing is the reserve, not the total. The owner's chat must never
#: wait on background work, and guaranteeing that needs a RESERVED seat rather than
#: a priority ordering: a background run may legitimately last
#: `automations.DEFAULT_RUN_TIMEOUT_SECONDS` (3 hours), so an ordering alone bounds
#: the chat's wait by three hours.
_FREE_SEATS_VAR = "TINYASSETS_FREE_SEATS"
_PAID_SEATS_VAR = "TINYASSETS_PAID_SEATS"
_DEFAULT_FREE_SEATS = 3
_DEFAULT_PAID_SEATS = 8

#: Seats background work may never take, so interactive work always has one.
#: Clamped below the seat count in `limits_for`: a reserve at or above it would
#: refuse every background run to protect a chat that is not asking.
_RESERVE_VAR = "TINYASSETS_INTERACTIVE_SEAT_RESERVE"
_DEFAULT_RESERVE = 1

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

#: Storage: the universe's whole cloud footprint, one of the directive's two numbers.
#:
#: These defaults predate the directive and are kept: 2,000 MB free / 20,000 MB paid
#: is already "free users have less cloud storage space", and a number that has
#: already been through review is worth more than a rounder one.
#:
#: What changes is that it is now MEASURED and ENFORCED
#: (`tinyassets.universe_storage`) rather than declared. The old comment said
#: per-universe attribution was wrong because ~99% of the footprint was our own
#: duplicated provider runtime, which the user did not put there -- so the
#: measurement excludes shared provider runtime and scratch-lease bytes, and counts
#: only what the universe itself holds. That is what makes the number chargeable.
_FREE_STORAGE_VAR = "TINYASSETS_FREE_STORAGE_MB"
_PAID_STORAGE_VAR = "TINYASSETS_PAID_STORAGE_MB"
_DEFAULT_FREE_STORAGE_MB = 2_000.0
_DEFAULT_PAID_STORAGE_MB = 20_000.0

#: Where an owner goes to buy more of either number.
#:
#: There is no GET upgrade route: the app's own control (`app.html` `btn-plan` ->
#: `startSubscribe`) POSTs `/app/billing/checkout`, which is identity-gated. A
#: link inside a message cannot POST, and inventing a route is forbidden -- so the
#: link is the app's EXISTING route plus a query parameter wired to that same
#: `startSubscribe()`. One builder, so there is exactly one string to test -- and
#: that paid off: when the app's public URL moved (#4112) this was the one-line
#: default change below.
_UPGRADE_ORIGIN = "https://tinyassets.io"
_APP_PATH_VAR = "TINYASSETS_APP_PATH"
_DEFAULT_APP_PATH = "/app"
_UPGRADE_QUERY = "upgrade=1"

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


def _positive_int(var: str, default: int) -> int:
    """Read a positive integer, announcing an unusable override rather than
    swallowing it. Shares `_positive_number`'s contract so a misconfigured seat
    count is as loud as a misconfigured quota."""
    value = _positive_number(var, float(default))
    return max(1, int(value))


@dataclass(frozen=True)
class TierLimits:
    """What one tier permits: two numbers, plus the retired window meters.

    ``seats`` and ``storage_bytes`` are the directive's two dimensions.
    ``background_seats`` is derived rather than stored, so the reserve can never
    disagree with the seat count it is subtracted from.
    """

    name: str
    seats: int
    interactive_reserve: int
    storage_bytes: float
    # Retired rolling-window meters; deleted with their call sites.
    effects: int
    compute_seconds: float
    window_seconds: float
    max_chargeable_run_seconds: float

    @property
    def is_paid(self) -> bool:
        return self.name == TIER_PAID

    @property
    def background_seats(self) -> int:
        """Seats background work may occupy. At least 1: a reserve that consumed
        every seat would refuse all automation to protect a chat nobody is having."""
        return max(1, self.seats - self.interactive_reserve)

    def seats_for(self, seat_class: str) -> int:
        """The ceiling this class of work may reach. Interactive work may take
        every seat; background work stops one short, which is the whole of the
        fairness guarantee."""
        from tinyassets.universe_seats import CLASS_INTERACTIVE

        return self.seats if seat_class == CLASS_INTERACTIVE else self.background_seats

    @property
    def storage_gib(self) -> float:
        return self.storage_bytes / float(1024**3)


def app_path() -> str:
    """The app's served path. One reader, which is why moving the app's public
    URL (#4112) was a single default change here and nothing else."""
    raw = (os.environ.get(_APP_PATH_VAR) or "").strip()
    path = raw or _DEFAULT_APP_PATH
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") or _DEFAULT_APP_PATH


def upgrade_url(tier: str) -> str | None:
    """Where this tier's owner goes to buy more, or None on the top tier.

    None rather than a link on the highest tier because there is nothing to sell
    them, and derived from `TIER_ORDER` rather than compared against `"free"` so a
    future middle tier needs no change at any message site.
    """
    normalized = normalize_tier(tier)
    if normalized == TIER_ORDER[-1]:
        return None
    return f"{_UPGRADE_ORIGIN}{quote(app_path())}?{_UPGRADE_QUERY}"


def upgrade_sentence(tier: str, *, what: str = "seats") -> str:
    """The upgrade half of a waiting or full message: one clickable link inline,
    never a banner, button, card or modal (founder, 2026-09-30). Empty on the top
    tier, so a caller concatenates unconditionally and the top tier simply gets the
    fact."""
    url = upgrade_url(tier)
    if url is None:
        return ""
    return f"[Upgrade]({url}) for more {what}."


def normalize_tier(tier: str) -> str:
    """Resolve a tier string. Anything unrecognized is the WEAKEST tier and says
    so, because the alternative to "unknown means free" is "unknown means
    unlimited"."""
    normalized = (tier or "").strip().lower()
    if normalized in TIER_ORDER:
        return normalized
    if normalized:
        _log.warning(
            "unrecognized account tier %r; applying the %s tier's limits",
            tier,
            TIER_ORDER[0],
        )
    return TIER_ORDER[0]


def window_seconds() -> float:
    return _positive_number(_WINDOW_VAR, _DEFAULT_WINDOW_S)


def max_chargeable_run_seconds() -> float:
    return _positive_number(_MAX_RUN_VAR, _DEFAULT_MAX_RUN_S)


def limits_for(tier: str) -> TierLimits:
    """Resolve a tier's limits. An unknown tier resolves to FREE, never unlimited."""
    normalized = normalize_tier(tier)
    paid = normalized == TIER_PAID
    seats = _positive_int(
        _PAID_SEATS_VAR if paid else _FREE_SEATS_VAR,
        _DEFAULT_PAID_SEATS if paid else _DEFAULT_FREE_SEATS,
    )
    # Clamped INSIDE the resolver, not at the call sites: a reserve at or above the
    # seat count would refuse every background run, and a reserve read
    # independently at two call sites is two chances to forget the clamp.
    reserve = min(_positive_int(_RESERVE_VAR, _DEFAULT_RESERVE), max(0, seats - 1))
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
        seats=seats,
        interactive_reserve=reserve,
        storage_bytes=storage_mb * 1024.0 * 1024.0,
        effects=int(effects),
        compute_seconds=compute_min * 60.0,
        window_seconds=window_seconds(),
        max_chargeable_run_seconds=max_chargeable_run_seconds(),
    )


def limits_for_universe(universe_dir) -> TierLimits:
    """This universe's limits, resolved from its stored tier.

    The single place the two halves meet, so no caller pairs `get_tier` with
    `limits_for` itself and no caller can pass a tier it chose. `get_tier` already
    returns FREE for an absent or unreadable record, and it never raises.
    """
    from tinyassets.storage.subscription_state import get_tier

    return limits_for(get_tier(universe_dir))


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
    enforcing = enforcement_enabled()
    try:
        admitted = _ledger().reserve_effect(
            universe_dir,
            settlement_key=settlement_key(sink=sink, effect_key=effect_key),
            limit=limits.effects,
            window_seconds=limits.window_seconds,
            now=now,
        )
    except Exception:
        # While dark, metering must not be able to decide whether an effect
        # happens. A locked or unwritable ledger would otherwise block a real
        # outbound write — a failure mode created purely by merging this, which is
        # exactly what landing dark is supposed to avoid (Codex round 3, 1 and 4).
        if not enforcing:
            return None
        # Enforcing: a ledger we cannot read must fail closed, or the cap is
        # trivially defeated by making the ledger unavailable.
        return QuotaRefusal(
            dimension="effect",
            limit=limits.effects,
            tier=limits.name,
            retry_after_seconds=limits.window_seconds,
        )
    if admitted:
        return None
    if not enforcing:
        # Dark: the decline is RECORDED but not acted on. Refusing on accounting we
        # know can drift would be worse than letting the action through.
        return None
    return QuotaRefusal(
        dimension="effect",
        limit=limits.effects,
        tier=limits.name,
        retry_after_seconds=limits.window_seconds,
    )


def release_effect_quota(universe_dir, *, sink: str, effect_key: str) -> bool:
    """Return budget after a write that did not reach the world.

    Never raises. Both this and `settle_effect_quota` run AFTER the destination has
    been contacted, so an exception here would turn a completed outbound write into a
    crash -- strictly worse than any accounting error it could prevent, and a failure
    mode created purely by merging metering at all.

    Failing to refund leaves the effect charged, which is unfair but not dangerous.
    """
    try:
        return _ledger().release_effect(
            universe_dir,
            settlement_key=settlement_key(sink=sink, effect_key=effect_key),
        )
    except Exception:
        _log.warning("could not refund effect quota", exc_info=True)
        return False


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
    try:
        return _ledger().commit_effect(
            universe_dir,
            settlement_key=settlement_key(sink=sink, effect_key=effect_key),
            now=now,
        )
    except Exception:
        # The write already happened. A meter that cannot record it is an accounting
        # gap; raising here would be a crash after an irreversible action. The
        # reservation stays reserved and still counts against the window, so this
        # cannot under-charge.
        _log.warning("could not settle effect quota", exc_info=True)
        return False
