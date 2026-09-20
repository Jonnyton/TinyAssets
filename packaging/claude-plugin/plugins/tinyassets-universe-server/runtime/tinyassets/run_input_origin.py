"""Pure immutable origin options; neither an execution grant nor a plugin registry."""

import json


class OriginHeld(ValueError):
    """Unknown or mismatched provenance must stay held, not be terminalized."""


def encode_origin(kind, version, options, *, allow_legacy=False):
    if type(kind) is not str or type(version) is not int or type(options) is not dict:
        raise OriginHeld("run_input_origin_invalid")
    if allow_legacy and (kind, version, options) == ("", 0, {}):
        return "{}"
    if version != 1 or kind not in {"direct", "canonical_consumer"}:
        raise OriginHeld("run_input_origin_unknown")
    if kind == "canonical_consumer":
        if options:
            raise OriginHeld("run_input_origin_options")
    else:
        if set(options) != {"recursion_limit", "concurrency_budget_override"}:
            raise OriginHeld("run_input_origin_options")
        recursion = options["recursion_limit"]
        concurrency = options["concurrency_budget_override"]
        # These are already accepted runtime options, not a second public input
        # parser. Existing public intake owns its narrower 10..1000 rule.
        if type(recursion) is not int or recursion <= 0:
            raise OriginHeld("run_input_origin_options")
        if concurrency is not None and (type(concurrency) is not int or concurrency <= 0):
            raise OriginHeld("run_input_origin_options")
    encoded = json.dumps(options, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > 1024:
        raise OriginHeld("run_input_origin_options_limit")
    return encoded


def decode_origin(envelope):
    try:
        encoded = envelope["origin_options_json"]
        if type(encoded) is not str or len(encoded.encode("utf-8")) > 1024:
            raise OriginHeld("run_input_origin_options_limit")
        options = json.loads(encoded)
        canonical = encode_origin(envelope["origin_kind"], envelope["origin_version"], options)
        if canonical != encoded:
            raise OriginHeld("run_input_origin_options_noncanonical")
        return options
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise OriginHeld("run_input_origin_invalid") from exc


def classify_admission_observation(envelope, status):
    """Pure additive observation, never death evidence or replay permission.

    A queued start marker can also be the small live pre-invocation window.
    Neither a read nor the marker distinguishes that from a lost worker, so
    report the uncertainty rather than claiming the run is safely unstarted.
    Callers must authorize the run before loading this metadata.
    """
    if status not in {"queued", "running"}:
        return {}
    started = (envelope.get("execution_started_at") is not None
               or envelope.get("claim_token") is not None)
    try:
        decode_origin(envelope)
    except (ValueError, TypeError, UnicodeError):
        return {
            "phase": "origin_unavailable", "admission_state": "held",
            "automatic_replay": False, "actions_may_have_occurred": started,
            "suggested_action": (
                "This accepted run's execution origin is unavailable. It remains held; "
                "do not submit a replacement as an automatic retry."
            ),
        }
    if status == "queued" and started:
        return {
            "phase": "recovery_required", "admission_state": "execution_started",
            "automatic_replay": False, "actions_may_have_occurred": True,
            "suggested_action": (
                "Execution was claimed, but a healthy active worker is not confirmed "
                "by this status. Actions may already have occurred. Do not resubmit; "
                "exact execution recovery must resolve this run."
            ),
        }
    return {}
