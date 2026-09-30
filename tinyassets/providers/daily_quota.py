"""Bounded HTTP quota evidence. Wire shapes, never vendor routing branches."""

import json
import math
import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from tinyassets.providers.model_capacity import CapacitySignal

DAILY_QUOTA = "provider_daily_quota"
_DAY = re.compile(r"per[ _-]?day|daily|\b[rt]pd\b", re.I)
_DURATION = re.compile(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?\Z")


def _seconds(value):
    if not isinstance(value, str) or not value or len(value) > 64:
        return None
    try:
        number = float(value)
    except ValueError:
        match = _DURATION.fullmatch(value)
        if not match or not any(match.groups()):
            return None
        number = sum(float(v or 0) * scale for v, scale in zip(match.groups(), (3600, 60, 1)))
    return number if math.isfinite(number) and 0 < number <= 86400 else None


def daily_quota_signal(status, headers, body, *, now=None, daily_request_headers=False,
                       daily_reset_timezone=None):
    """Only explicit daily exhaustion is daily; generic 429/RESOURCE_EXHAUSTED isn't.

    Documented shapes (checked 2026-09-30):
    https://openrouter.ai/docs/api_reference/limits (metadata.headers, epoch ms)
    https://ai.google.dev/gemini-api/docs/troubleshooting (QuotaFailure details)
    https://console.groq.com/docs/rate-limits (RPD and reset duration)
    https://inference-docs.cerebras.ai/support/rate-limits (day header suffixes)
    https://docs.mistral.ai/admin/billing-usage/usage-limits (no daily code promised;
    generic rate_limited/1300 stays unknown unless the message names a day).
    """
    if status != 429:
        return None
    payload = {}
    if isinstance(body, str) and len(body) <= 65536:
        try:
            payload = json.loads(body)
        except (ValueError, RecursionError):
            pass
    error = payload.get("error", payload) if isinstance(payload, dict) else {}
    if not isinstance(error, dict):
        error = {}
    # Scan only error facts, not an echoed request or an arbitrary nested document.
    facts = [error.get("message", ""), error.get("code", "")]
    details = error.get("details", [])
    if isinstance(details, list):
        for detail in details[:32]:
            if isinstance(detail, dict):
                violations = detail.get("violations")
                if not isinstance(violations, list):
                    continue
                for violation in violations[:32]:
                    if isinstance(violation, dict):
                        facts.extend(violation.get(k, "") for k in ("quotaId", "quotaMetric"))
    daily = any(isinstance(f, str) and _DAY.search(f) for f in facts)
    values = {}
    metadata = error.get("metadata")
    nested = metadata.get("headers") if isinstance(metadata, dict) else None
    for source in (nested, headers):
        if isinstance(source, dict):
            values.update({k.lower(): v for k, v in source.items()
                           if isinstance(k, str) and isinstance(v, str)})
    delays = []
    if daily_request_headers and values.get("x-ratelimit-remaining-requests") == "0":
        daily = True
    for unit in ("requests", "tokens"):
        for suffix in ("-day", "-per-day"):
            if values.get(f"x-ratelimit-remaining-{unit}{suffix}") == "0":
                daily = True
                delay = _seconds(values.get(f"x-ratelimit-reset-{unit}{suffix}"))
                if delay is not None:
                    delays.append(delay)
    # A reset-requests duration alone doesn't prove its window is daily. Groq's
    # error names RPD; other OpenAI-compatible APIs use this header for RPM.
    if not daily:
        return None
    if daily_request_headers and values.get("x-ratelimit-remaining-requests") == "0":
        delay = _seconds(values.get("x-ratelimit-reset-requests"))
        if delay is not None:
            delays.append(delay)
    epoch = values.get("x-ratelimit-reset", "")
    if epoch.isascii() and epoch.isdecimal() and len(epoch) in (10, 13):
        reset = int(epoch) / (1000 if len(epoch) == 13 else 1)
        seconds = reset - (now or datetime.now(UTC)).timestamp()
        if 0 < seconds <= 86400:
            delays.append(seconds)
    if not delays and daily_reset_timezone:
        current = now or datetime.now(UTC)
        local = current.astimezone(ZoneInfo(daily_reset_timezone))
        midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        delays.append((midnight.astimezone(UTC) - current).total_seconds())
    # A generic Retry-After can describe a minute bucket even when the daily
    # bucket is empty (Gemini sends both); it is never evidence of a daily reset.
    return CapacitySignal("account", DAILY_QUOTA, max(delays) if delays else None)


def daily_detail(signal, *, billing_url="", now=None):
    words = "Daily quota exhausted."
    if signal.retry_after_s is not None:
        reset = datetime.fromtimestamp(
            (now or datetime.now(UTC)).timestamp() + signal.retry_after_s, UTC,
        )
        words += " Reset: " + reset.strftime("%Y-%m-%d %H:%M UTC") + "."
    else:
        words += " Reset time not supplied."
    if billing_url:
        words += " Add credit: " + billing_url
    return words
