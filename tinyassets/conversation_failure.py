"""Closed, non-authorizing failure evidence for retained conversation.

Only platform-authored sentences enter this sink. Provider diagnostics, names,
attempts and exception strings are deliberately not fields of this value.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

_NOTICES = {
    "provider_idle_timeout": "The turn ended after the model stopped responding.",
    "interactive_deadline": "The turn reached its interactive time limit.",
    "provider_rate_limited": "The model provider reported a rate limit during this turn.",
    "provider_overloaded": "The model provider reported being overloaded during this turn.",
    "auth_invalid": "The model provider reported a sign-in problem during this turn.",
    "endpoint_unreachable": "The turn could not complete its connection to the model provider.",
    "platform_fault": "A platform problem interrupted this turn.",
    "quota_or_cooldown": "Model access was in a usage-limit or cooldown window during this turn.",
    "timed_out": "The model attempt timed out during this turn.",
    "native_auth_clue": (
        "The turn did not complete. The model provider reported a sign-in problem, "
        "but we have not confirmed that was the only cause."
    ),
    "setup_required": "The turn needs this universe's model connection to be set up or recovered.",
    "unknown": "The turn did not complete, and its cause has not been established.",
}
FAILURE_CODES = frozenset(_NOTICES)
_RETRY_CAUTION = (
    " Actions may already have occurred. Check progress before sending again; "
    "sending again repeats the whole request."
)


@dataclass(frozen=True, slots=True)
class TurnFailure:
    version: int
    kind: str
    code: str


def failure_code(value: object) -> str:
    return value if isinstance(value, str) and value in FAILURE_CODES else "unknown"


def failure_notice(code: object) -> str:
    """Render a fixed sentence, never interpolate diagnostic data."""
    return _NOTICES[failure_code(code)] + _RETRY_CAUTION


def turn_failure(code: object) -> TurnFailure:
    return TurnFailure(version=1, kind="turn_failed", code=failure_code(code))


def normalize_turn_failure(value: object) -> dict | None:
    if isinstance(value, TurnFailure):
        value = asdict(value)
    if not isinstance(value, dict) or set(value) != {"version", "kind", "code"}:
        return None
    if type(value["version"]) is not int or value["version"] != 1:
        return None
    if value["kind"] != "turn_failed":
        return None
    code = value["code"]
    if not isinstance(code, str) or code not in FAILURE_CODES:
        return None
    return {"version": 1, "kind": "turn_failed", "code": code}


def read_turn_failure(speaker: str, raw: object) -> TurnFailure | None:
    """Optional metadata is read-only and cannot change a row's speaker."""
    if speaker != "platform" or not isinstance(raw, str) or not 0 < len(raw) <= 512:
        return None
    try:
        value = normalize_turn_failure(json.loads(raw))
    except (ValueError, RecursionError):
        return None
    return TurnFailure(**value) if value is not None else None


def failure_column_sql(conn) -> str:
    """Fixed optional-column expression for pure readers; no schema writes."""
    columns = conn.execute("PRAGMA table_info(conversation_turns)")
    return "failure_json" if any(row[1] == "failure_json" for row in columns) else "''"


def project_failure_row(row) -> dict:
    """Drop storage representation; expose only validated platform-owned detail."""
    value = dict(row)
    raw = value.pop("failure_json", "")
    failure = normalize_turn_failure(read_turn_failure(value.get("speaker", ""), raw))
    if failure is not None:
        value["failure"] = failure
    return value
