"""Structured, non-authorizing failure evidence for retained conversation.

A failed served turn is recorded as FIELDS, and every notice -- the live one
and the one history re-renders -- is composed from them, so a new failure never
needs new copy (founder, 2026-09-24):

* ``code``: the class, from a small closed set derived from transport facts;
* ``stage``: the fixed pipeline position where the turn stopped;
* ``effects``: ``none`` / ``some`` / ``unknown``, read from the turn's own
  effects ledger, never guessed. "Actions may already have occurred" is said
  only when effects are not ``none``;
* ``provider_detail``: the source's own error text, secret- and path-scrubbed
  and bounded -- the owner reading their own universe's failure;
* ``ref``: the turn (or run) id, which the server log line carries too.

Nothing here grants authority or is replayed as an instruction.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

STAGES = ("before_send", "connection", "model_request", "model_reply", "tool", "platform")
EFFECTS = ("none", "some", "unknown")

_STAGE_WORDS = {
    "before_send": "Before anything reached your model",
    "connection": "Connecting to your model's provider",
    "model_request": "Waiting on your model's provider",
    "model_reply": "Reading your model's reply",
    "tool": "Running one of your universe's tools",
    "platform": "Inside TinyAssets",
}
_NO_STAGE = "Your universe's turn stopped"

#: The class in words: one clause per class, composed -- never a whole notice.
_CLASS_WORDS = {
    "provider_idle_timeout": (
        "your model went quiet mid-turn, so the turn was ended and whatever it "
        "finished before that stands; asking it to continue is usually better "
        "than sending the whole request again"
    ),
    "interactive_deadline": (
        "the turn ran past the interactive time limit, so it was ended and "
        "whatever it finished before that stands; asking it to continue is "
        "usually better than sending the whole request again"
    ),
    "provider_rate_limited": (
        "your model provider is rate-limiting it right now; this usually clears "
        "within a few minutes, so send again then"
    ),
    "provider_overloaded": (
        "your model provider is overloaded right now; nothing is wrong with your "
        "setup, so send again in a minute"
    ),
    "auth_invalid": (
        "your model provider reported a sign-in problem; check this universe's "
        "connection and reconnect the provider if needed. This is not evidence "
        "of a usage or billing limit"
    ),
    "endpoint_unreachable": (
        "your universe could not reach its model provider; that is a network or "
        "service problem rather than anything you set up wrong, so send again shortly"
    ),
    "platform_fault": (
        "something broke on our side; this is not a problem with your account, "
        "your credentials or your usage limits, and sending again may well work"
    ),
    "quota_or_cooldown": (
        "model access was in a usage-limit or cooldown window; wait a moment, "
        "then send again"
    ),
    "timed_out": "the model attempt timed out",
    "native_auth_clue": (
        "your model provider reported a sign-in problem; check this universe's "
        "provider connection and reconnect if needed, though we have not "
        "confirmed that was the only cause"
    ),
    "setup_required": (
        "this universe has no model connected yet; connect one from the request "
        "under “Waiting on you”, then send your request again"
    ),
    "provider_protocol_error": (
        "the connected model replied in a format this universe could not read; "
        "try again, or choose another model"
    ),
    "unknown": (
        "we could not identify why; we cannot tell whether this is a connection, "
        "usage, billing, or platform problem, so rather than guess we have "
        "recorded the details"
    ),
}
FAILURE_CODES = frozenset(_CLASS_WORDS)

#: Where each class stops the pipeline -- a transport fact, not a guess.
#: ``unknown`` has no position; the turn's own ledger may still supply one.
STAGE_OF_CLASS = {
    "setup_required": "before_send",
    "auth_invalid": "connection",
    "native_auth_clue": "connection",
    "endpoint_unreachable": "connection",
    "provider_rate_limited": "model_request",
    "provider_overloaded": "model_request",
    "quota_or_cooldown": "model_request",
    "timed_out": "model_request",
    "provider_idle_timeout": "model_reply",
    "interactive_deadline": "model_reply",
    "provider_protocol_error": "model_reply",
    "platform_fault": "platform",
}

_CHECK = "Check progress before sending again; sending again repeats the whole request."
_EFFECT_WORDS = {
    "none": "Nothing ran.",
    "some": "Some actions ran before it stopped. " + _CHECK,
    "unknown": (
        "We can't tell whether actions ran, so actions may already have occurred. " + _CHECK
    ),
}

DETAIL_LIMIT = 200
_REF = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")
_OPTIONAL = frozenset({"stage", "effects", "provider_detail", "ref", "retry_after_s"})
_REQUIRED = frozenset({"version", "kind", "code"})

#: A wait longer than this is not a wait, it is a different answer ("reconnect",
#: "your daily cap resets tomorrow"), so it is dropped rather than rendered as a
#: number nobody will sit through. One day, the longest window any source's
#: Retry-After has meant here.
MAX_WAIT_S = 86_400


def wait_seconds(value: object) -> int | None:
    """A whole positive bounded second count, or None. ``bool`` is not a wait."""
    if type(value) is not int or value <= 0 or value > MAX_WAIT_S:
        return None
    return value


@dataclass(frozen=True, slots=True)
class TurnFailure:
    version: int
    kind: str
    code: str
    stage: str | None = None
    effects: str = "unknown"
    provider_detail: str = ""
    ref: str = ""
    retry_after_s: int | None = None
    """Measured seconds until this source is eligible again -- the source's own
    ``Retry-After`` or the remaining window of our own cooldown gate. Never a
    guess and never a deadline we invent for a class that has no window; absent
    stays absent. Live 2026-09-25 the gate that refused the turn knew it had 120
    seconds left and the founder was told "we could not identify why"."""


def failure_code(value: object) -> str:
    return value if isinstance(value, str) and value in FAILURE_CODES else "unknown"


def clean_detail(value: object) -> str:
    """One bounded, printable line; callers scrub secrets before this."""
    if not isinstance(value, str):
        return ""
    line = " ".join("".join(ch if ch.isprintable() else " " for ch in value).split())
    return line if len(line) <= DETAIL_LIMIT else line[: DETAIL_LIMIT - 3] + "..."


def turn_failure(
    code: object, *, stage: object = None, effects: object = "unknown",
    provider_detail: object = "", ref: object = "", retry_after_s: object = None,
) -> TurnFailure:
    """Build a record; any field outside its closed set degrades, never raises."""
    return TurnFailure(
        version=1, kind="turn_failed", code=failure_code(code),
        stage=stage if stage in STAGES else None,
        # A universe with no model connected cannot have acted.
        effects="none" if failure_code(code) == "setup_required"
        else effects if effects in EFFECTS else "unknown",
        provider_detail=clean_detail(provider_detail),
        ref=ref if isinstance(ref, str) and _REF.fullmatch(ref) else "",
        retry_after_s=wait_seconds(retry_after_s),
    )


def _coerce(value: object) -> TurnFailure:
    if isinstance(value, TurnFailure):
        return value
    normalized = normalize_turn_failure(value) if isinstance(value, dict) else None
    if normalized is not None:
        return turn_failure(**{k: v for k, v in normalized.items()
                               if k not in {"version", "kind"}})
    return turn_failure(value)


def _wait_words(seconds: int) -> str:
    """The measured wait as one sentence. Rounded up: never say "send again now"."""
    if seconds < 60:
        return f"You can send again in about {seconds} seconds."
    minutes = -(-seconds // 60)
    unit = "minute" if minutes == 1 else "minutes"
    return f"You can send again in about {minutes} {unit}."


def failure_notice(value: object) -> str:
    """Compose the notice from the record's fields; no per-failure copy."""
    failure = _coerce(value)
    parts = [
        f"{_STAGE_WORDS.get(failure.stage, _NO_STAGE)} — {_CLASS_WORDS[failure.code]}.",
        _EFFECT_WORDS[failure.effects],
    ]
    if failure.retry_after_s is not None:
        parts.append(_wait_words(failure.retry_after_s))
    if failure.provider_detail:
        parts.append(f'Detail: "{failure.provider_detail}"')
    if failure.ref:
        parts.append(f"Ref: {failure.ref}")
    return " ".join(parts)


def normalize_turn_failure(value: object) -> dict | None:
    """The closed value: required fields exact, optional fields in their sets."""
    if isinstance(value, TurnFailure):
        value = {k: v for k, v in asdict(value).items() if v not in (None, "")}
    if not isinstance(value, dict):
        return None
    keys = set(value)
    if not _REQUIRED <= keys or keys - _REQUIRED - _OPTIONAL:
        return None
    if type(value["version"]) is not int or value["version"] != 1:
        return None
    if value["kind"] != "turn_failed":
        return None
    code = value["code"]
    if not isinstance(code, str) or code not in FAILURE_CODES:
        return None
    result = {"version": 1, "kind": "turn_failed", "code": code}
    if "stage" in value:
        if value["stage"] not in STAGES:
            return None
        result["stage"] = value["stage"]
    if "effects" in value:
        if value["effects"] not in EFFECTS:
            return None
        result["effects"] = value["effects"]
    if "provider_detail" in value:
        detail = value["provider_detail"]
        if not isinstance(detail, str) or clean_detail(detail) != detail:
            return None
        result["provider_detail"] = detail
    if "ref" in value:
        if not isinstance(value["ref"], str) or not _REF.fullmatch(value["ref"]):
            return None
        result["ref"] = value["ref"]
    if "retry_after_s" in value:
        wait = wait_seconds(value["retry_after_s"])
        if wait is None:
            return None
        result["retry_after_s"] = wait
    return result


def read_turn_failure(speaker: str, raw: object) -> TurnFailure | None:
    """Optional metadata is read-only and cannot change a row's speaker."""
    if speaker != "platform" or not isinstance(raw, str) or not 0 < len(raw) <= 4096:
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
