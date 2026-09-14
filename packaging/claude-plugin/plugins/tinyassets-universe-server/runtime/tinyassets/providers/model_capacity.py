"""Private normalized capacity evidence, separate from authority and model names."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

MAX_RETRY_SECONDS = 2**31 - 1


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
