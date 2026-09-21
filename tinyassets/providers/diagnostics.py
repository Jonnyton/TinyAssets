"""Provider router diagnostic primitives (FEAT-006).

Captures per-provider skip/failure reasons during chain iteration so
``AllProvidersExhaustedError`` can carry structured detail. Operators
and chatbots can then triage *why* the chain exhausted (auth_invalid /
quota_or_cooldown / endpoint_unreachable / etc) instead of parsing the
human-readable error string.

Additive only — no behavior change. ``ProviderAttemptDiagnostic.to_dict``
omits ``None`` fields so the serialized form stays compact when optional
detail isn't available.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

# "skipped" = never tried (registry miss or quota/cooldown gate).
# "failed"  = tried and got an exception.
AttemptStatus = Literal["skipped", "failed"]


def redacted_failure_detail(detail: str, *, limit: int = 200) -> str:
    """Scrub before clipping, retaining the terminal cause within the budget."""
    from tinyassets.workspace_git import scrub_text

    scrubbed = scrub_text(detail)
    if len(scrubbed) <= limit:
        return scrubbed
    head = limit // 2
    tail = limit - head - 5
    return scrubbed[:head] + " ... " + scrubbed[-tail:]

# Operators use this enum to decide the recovery action. Each class maps
# to a distinct fix:
#   not_in_registry     - daemon config / provider registration
#   quota_or_cooldown   - wait, or check quota refresh
#   auth_invalid        - refresh subscription auth bundle / API key
#   endpoint_unreachable- network / service outage
#   timed_out           - subprocess hang / network slow
#   provider_error      - structured provider error (see detail)
#   unknown             - unhandled exception (see detail)
SkipClass = Literal[
    "not_in_registry",
    "quota_or_cooldown",
    "auth_invalid",
    "endpoint_unreachable",
    "timed_out",
    "provider_error",
    "unknown",
]


@dataclass
class ProviderAttemptDiagnostic:
    """One provider's skip/failure record collected during chain iteration.

    Used by ``ProviderRouter.call`` to build an ``attempts`` list that gets
    attached to ``AllProvidersExhaustedError`` (and propagated through
    graph-compiler error serialization to ``get_run.error_detail``).
    """

    provider: str
    status: AttemptStatus
    skip_class: SkipClass
    detail: str = ""
    cooldown_remaining_s: int | None = None
    # Streamed-attempt taxonomy (Slice 1). ``skip_class`` stays the coarse
    # operator-facing bucket for backward-compat; ``failure_class`` carries the
    # precise streamed-attempt class (provider_idle_timeout / interactive_deadline
    # / provider_rate_limited / …). Both optional + dropped from to_dict when None.
    failure_class: str | None = None
    retry_after_s: float | None = None
    # Streamed-attempt side-effect state (Slice 1 blocker K): none|possible|
    # committed — whether a tool may have run before the attempt failed. Lets the
    # sole-writer retry policy avoid re-running a turn that already committed a
    # side effect. Optional + dropped from to_dict when None.
    side_effect_state: str | None = None
    capacity_scope: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize, dropping ``None`` fields for compactness."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


def dominant_capacity_scope(attempts):
    for attempt in reversed(attempts):
        if attempt.status == "failed":
            return attempt.capacity_scope
    return None


def build_chain_state(
    role: str,
    chain: list[str],
    attempts: list[ProviderAttemptDiagnostic],
    *,
    api_key_providers_enabled: bool | None = None,
    pinned_writer: str | None = None,
    allowlist: list[str] | None = None,
) -> dict[str, Any]:
    """Build a structured ``chain_state`` dict for the failure record.

    Suitable for attaching to ``AllProvidersExhaustedError.chain_state``
    and surfacing through ``get_run.error_detail.provider_chain`` /
    ``get_status.provider_chain_health``.
    """
    out: dict[str, Any] = {
        "role": role,
        "chain": list(chain),
        "attempts": [a.to_dict() for a in attempts],
    }
    if api_key_providers_enabled is not None:
        out["api_key_providers_enabled"] = bool(api_key_providers_enabled)
    if pinned_writer:
        out["pinned_writer"] = pinned_writer
    if allowlist is not None:
        out["allowlist"] = list(allowlist)
    return out


def dominant_failure_class(
    attempts: list[ProviderAttemptDiagnostic] | None,
) -> str | None:
    """Return the ``failure_class`` of the last FAILED attempt, or ``None``.

    A single-provider chain (served / pinned / armed) exhausts by looping to
    its one failed attempt and then raising ``AllProvidersExhaustedError``. This
    picks out the precise streamed-attempt class so the honest user notice can
    say *why* (idle timeout != capacity) rather than substring-matching the
    aggregate message. Skips (never-tried providers) carry no failure_class.
    """
    if not attempts:
        return None
    for attempt in reversed(attempts):
        if attempt.status == "failed" and attempt.failure_class:
            return attempt.failure_class
    return None


def dominant_retry_after_s(
    attempts: list[ProviderAttemptDiagnostic] | None,
) -> float | None:
    """Return the ``retry_after_s`` of the last failed attempt that carried one."""
    if not attempts:
        return None
    for attempt in reversed(attempts):
        if attempt.status == "failed" and attempt.retry_after_s is not None:
            return attempt.retry_after_s
    return None


def classify_unavailable(error: BaseException) -> SkipClass:
    """Heuristically classify a ``ProviderUnavailableError`` as auth vs network.

    The base ``ProviderUnavailableError`` covers both auth failures (401/403,
    expired subscription bundle) and network failures (connection refused,
    DNS, timeouts that aren't ``ProviderTimeoutError``). This split is the
    main signal operators need: auth_invalid points at the subscription auth
    bundle / API keys, endpoint_unreachable points at network / service.

    Conservative — defaults to ``endpoint_unreachable`` when the message
    doesn't contain auth-tells, since that's the safer wrong guess (it
    triggers retry/wait rather than premature credential rotation).
    """
    msg = str(error).lower()
    auth_tells = (
        "auth", "credential", "token", "401", "403",
        "unauthor", "forbidden", "expired", "invalid_token", "no_credentials",
    )
    if any(t in msg for t in auth_tells):
        return "auth_invalid"
    return "endpoint_unreachable"


# ---------------------------------------------------------------------------
# Stored-run classification of a held / single-source attempt
# ---------------------------------------------------------------------------
#
# Two surfaces classify the SAME stored run row: ``api.runs`` (get_run /
# run_branch) and ``runs._classify_failure`` (routing evidence, coding-process
# health). They must not report two different causes for one row, and neither
# may take its answer from free text -- the owner's own model id, their
# connection id, or a provider's `detail` all end up inside the stored string,
# so a substring net reads "timeout" off a model called ``fast-timeout-v2``.
# The typed attempt evidence is the only honest source, so it lives here, at the
# layer that produced it, below both readers (``runs`` importing ``api`` would
# be a cycle).

#: The compact JSON evidence suffix ``graph_compiler._wrap_provider_failure``
#: appends to a provider failure. Everything after it is data, never a class.
CHAIN_STATE_MARKER = "[chain_state]:"

#: The attempt's own classified cause -> the run failure class both surfaces
#: report. Streamed ``failure_class`` first, the coarser ``skip_class`` when an
#: attempt carried none. Values are EXISTING run classes (``ACTIONABLE_BY``
#: knows them); this table adds no taxonomy.
HELD_ATTEMPT_RUN_CLASSES: dict[str, str] = {
    "provider_idle_timeout": "timeout",
    "interactive_deadline": "timeout",
    "provider_protocol_error": "provider_error",
    "auth_invalid": "auth_invalid",
    "provider_rate_limited": "quota_exhausted",
    "provider_credit_exhausted": "quota_exhausted",
    "provider_overloaded": "provider_overloaded",
    "timed_out": "timeout",
    "provider_error": "provider_error",
    "endpoint_unreachable": "provider_error",
    "quota_or_cooldown": "quota_exhausted",
}

#: A HELD attempt whose cause this table does not name -- the diagnostics enum's
#: own literal "unknown", or a class a later slice adds. Not an established
#: provider error: asserting one would put a diagnosis in the run record that no
#: evidence supports. "unknown" is still strictly better than the
#: "connect your provider" a substring net produces for a source that was bound.
HELD_ATTEMPT_UNRECOGNISED_CLASS = "unknown"


@dataclass(frozen=True)
class HeldAttemptDiagnosis:
    """What the typed evidence on a stored held/single-source row supports."""

    #: The run failure class BOTH stored-run surfaces must report.
    run_class: str
    #: The attempt's own classified cause, or ``None`` when none was recorded.
    cause: str | None
    #: The attempt's provider/connection id, or ``""``.
    provider: str
    #: True for a held ATTEMPT, False for a single-source no-widening raise.
    held: bool
    #: True when ``cause`` is named by :data:`HELD_ATTEMPT_RUN_CLASSES`.
    recognised: bool
    #: True only when a FAILED attempt record exists. A skipped (never tried)
    #: attempt proves nothing was invoked, so advice must not say it was.
    invoked: bool


def chain_state_from_error(error: str) -> dict[str, Any] | None:
    """Parse the compact ``[chain_state]:`` suffix off a stored error string."""
    import json

    if CHAIN_STATE_MARKER not in (error or ""):
        return None
    suffix = error.rsplit(CHAIN_STATE_MARKER, 1)[1].strip()
    if not suffix:
        return None
    try:
        parsed = json.loads(suffix)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def held_attempt_diagnosis(
    error_text: str, chain_state: dict[str, Any] | None = None,
) -> HeldAttemptDiagnosis | None:
    """Classify a held / single-source stored run error from its typed evidence.

    ``None`` means "not one of these raises, or nothing typed to say" and the
    caller keeps its own classification:

    * a held attempt always gets an answer -- the evidenced class, else
      :data:`HELD_ATTEMPT_UNRECOGNISED_CLASS`;
    * a single-source (``NO_WIDENING_MESSAGE``) raise gets one only when its
      cause is recognised. Without evidence, the existing classifiers already
      say something true about an exhausted chain, and flattening that to
      "unknown" would lose it.

    The marker is looked for BEFORE the evidence suffix, and the class comes
    from the attempt record: a provider ``detail`` that happens to say "timed
    out", a model id containing "timeout", or a connection named "exhausted"
    cannot move the answer.
    """
    from tinyassets.exceptions import AllProvidersExhaustedError, ProviderAuthorityHeldError

    head = (error_text or "").split(CHAIN_STATE_MARKER, 1)[0].lower()
    held = ProviderAuthorityHeldError.ATTEMPT_MESSAGE in head
    if not held and AllProvidersExhaustedError.NO_WIDENING_MESSAGE not in head:
        return None
    if chain_state is None:
        chain_state = chain_state_from_error(error_text)
    attempts = chain_state.get("attempts") if isinstance(chain_state, dict) else None
    failed = [
        item for item in (attempts if isinstance(attempts, list) else [])
        if isinstance(item, dict) and item.get("status") == "failed"
    ]
    cause: str | None = None
    provider = ""
    if failed:
        raw = failed[-1].get("failure_class") or failed[-1].get("skip_class")
        cause = raw if isinstance(raw, str) and raw else None
        provider = str(failed[-1].get("provider") or "")
    recognised = cause is not None and cause in HELD_ATTEMPT_RUN_CLASSES
    if recognised:
        return HeldAttemptDiagnosis(
            run_class=HELD_ATTEMPT_RUN_CLASSES[cause],
            cause=cause, provider=provider, held=held,
            recognised=True, invoked=True,
        )
    if held:
        return HeldAttemptDiagnosis(
            run_class=HELD_ATTEMPT_UNRECOGNISED_CLASS,
            cause=cause, provider=provider, held=True,
            recognised=False, invoked=bool(failed),
        )
    return None
