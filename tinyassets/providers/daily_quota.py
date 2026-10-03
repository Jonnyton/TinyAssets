"""Bounded HTTP quota evidence. Wire shapes, never vendor routing branches."""

import json
import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from tinyassets.providers.model_capacity import CapacitySignal

DAILY_QUOTA = "provider_daily_quota"
_SHAPES = json.loads(Path(__file__).with_name("daily_quota_shapes.json").read_text("utf-8"))
_DAY = re.compile(_SHAPES["daily_fact_pattern"], re.I)
#: Daily evidence is judged per SENTENCE of a fact, because providers put the
#: refused window and other windows' balances in one message (gpt-6-astra,
#: 2026-09-30, both directions): "Requests per minute exceeded. Daily quota
#: remaining: 49." is a MINUTE refusal -- read as daily it cooled the whole
#: source and dropped a sibling that works -- while "Daily token limit exceeded.
#: Requests per minute remaining: 49." IS daily. A sentence that also names a
#: shorter window is about that window; a balance that exhausts nothing
#: ("... remaining: 49") is information, not a refusal.
_SHORTER = re.compile(_SHAPES["shorter_window_pattern"], re.I)
_BALANCE = re.compile(_SHAPES["balance_pattern"], re.I)
_EXHAUSTED = re.compile(_SHAPES["exhausted_pattern"], re.I)
_SENTENCES = re.compile(_SHAPES["sentence_split_pattern"])


def _daily_fact(fact) -> bool:
    if not isinstance(fact, str):
        return False
    # Never sliced: a cut can drop the qualifier that makes a sentence a balance
    # (gpt-6-astra round 3). The body is already bounded by the caller.
    for sentence in _SENTENCES.split(fact):
        if _BALANCE.search(sentence) and not _EXHAUSTED.search(sentence):
            continue
        if _DAY.search(sentence) and not _SHORTER.search(sentence):
            return True
    return False
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


def _path_values(value, path):
    """Read installed wire paths, bounding every repeated error-detail array."""
    if not path:
        yield value
    elif path[0] == "*" and isinstance(value, list):
        for item in value[:32]:
            yield from _path_values(item, path[1:])
    elif isinstance(value, dict) and path[0] in value:
        yield from _path_values(value[path[0]], path[1:])


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
    facts = (fact for path in _SHAPES["fact_paths"] for fact in _path_values(error, path))
    daily = any(_daily_fact(f) for f in facts)
    values = {}
    nested = next(_path_values(error, _SHAPES["nested_headers_path"]), None)
    for source in (nested, headers):
        if isinstance(source, dict):
            values.update({k.lower(): v for k, v in source.items()
                           if isinstance(k, str) and isinstance(v, str)})
    delays = []
    windows = list(_SHAPES["daily_windows"])
    if daily_request_headers:
        windows.append(_SHAPES["declared_daily_window"])
    for window in windows:
        if values.get(window["remaining"]) == "0":
            daily = True
            delay = _seconds(values.get(window["reset"]))
            if delay is not None:
                delays.append(delay)
    # A reset duration alone doesn't prove that its window is daily.
    if not daily:
        return None
    epoch = values.get(_SHAPES["epoch_reset_header"], "")
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
