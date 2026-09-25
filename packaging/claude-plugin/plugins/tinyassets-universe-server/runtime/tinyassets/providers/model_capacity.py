"""Private normalized capacity evidence, separate from authority and model names."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

MAX_RETRY_SECONDS = 2**31 - 1

#: Capacity classes a source itself describes as a passing window. Exhausted
#: credit is deliberately absent: it is about money, not about waiting.
TRANSIENT_CAPACITY = frozenset({"provider_rate_limited", "provider_overloaded"})


def free_sibling_retry(
    *, scope, failure_class, cost_caps, retry_after_s=None, turn_budget_s=None,
) -> bool:
    """POLICY, not evidence: may a zero-cost source try a SIBLING model next?

    ``CapacitySignal.scope`` stays exactly what the source's contract reported.
    When that is ``unknown`` the platform cannot tell a per-model window from an
    account-wide one, so the conservative reading -- exclude the whole account,
    and cool the source -- is the only safe one for a source that can spend.

    On a source whose accepted ceilings are all confirmed zero there is nothing
    to protect: being wrong costs one more refused request. Being conservative,
    however, is what left a freshly connected free universe with no second
    candidate and no answer to its first message (live 2026-09-25).

    A "yes" here also withholds the source's cooldown, because cooling the
    connection would skip the very sibling the turn is about to try. So the
    answer must be **no** once there is no sibling attempt left to protect:

``retry_after_s`` vs ``turn_budget_s`` -- when the source named a window longer
    than a whole turn is allowed to live, waiting is the honest answer and no
    sibling attempt can outlast it. ``None`` or a malformed value for either
    keeps the prior answer.

    Whoever concludes that no sibling attempt remains -- because the budget is
    spent OR because the order has no candidate left on this source -- is
    responsible for cooling it after the fact. That is the turn coordinator, the
    only place that knows both; see ``AgentTurnCoordinator._next_after_capacity``.
    Without it a source at a DAILY free cap, which refuses every model, would
    have every turn pay the full budget of requests again, forever.

    This grants no authority, widens no grant and never admits a paid model: the
    sibling comes from the SAME order under the SAME ceilings.
    """
    if not (
        scope == "unknown"
        and failure_class in TRANSIENT_CAPACITY
        and _confirmed_free_only(cost_caps)
    ):
        return False
    if (
        _finite_positive(retry_after_s)
        and _finite_positive(turn_budget_s)
        and retry_after_s > turn_budget_s
    ):
        return False
    return True


def _finite_positive(value) -> bool:
    return (
        type(value) in (int, float) and not isinstance(value, bool)
        and math.isfinite(value) and value > 0
    )


def _confirmed_free_only(cost_caps) -> bool:
    from tinyassets.providers.model_policy import confirmed_free_only

    return confirmed_free_only(cost_caps)


@dataclass(frozen=True, slots=True)
class CapacitySignal:
    scope: str
    failure_class: str
    retry_after_s: float | None = None

    def __post_init__(self):
        if self.scope not in {"model", "account", "unknown"}:
            raise ValueError("invalid capacity scope")
        if self.failure_class not in {
            "provider_credit_exhausted", "provider_rate_limited", "provider_overloaded",
        }:
            raise ValueError("invalid capacity failure kind")
        delay = self.retry_after_s
        if delay is not None and (
            type(delay) not in (int, float) or not math.isfinite(delay)
            or not 0 <= delay <= MAX_RETRY_SECONDS
        ):
            raise ValueError("invalid capacity retry delay")

    def exhaustion(self, ref):
        from tinyassets.providers.model_policy import Exhaustion

        return Exhaustion("model" if self.scope == "model" else "account", ref)


def retry_after_seconds(headers, *, now=None):
    """Parse only the standard bounded hint; never retain other response headers."""
    if not isinstance(headers, dict):
        return None
    values = [v for k, v in headers.items() if isinstance(k, str) and k.lower() == "retry-after"]
    if len(values) != 1 or not isinstance(values[0], str) or len(values[0]) > 128:
        return None
    value = values[0].strip()
    try:
        if value.isascii() and value.isdecimal() and len(value) <= 10:
            delay = int(value)
        else:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            delay = max(0, (date - (now or datetime.now(UTC))).total_seconds())
        return delay if 0 <= delay <= MAX_RETRY_SECONDS else None
    except (TypeError, ValueError, OverflowError):
        return None
