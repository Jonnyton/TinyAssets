"""Exception hierarchy for TinyAssets.

Every exception in the system inherits from FantasyAuthorError so callers
can catch broadly when appropriate.
"""


class FantasyAuthorError(Exception):
    """Base exception for all TinyAssets errors."""


# ---------------------------------------------------------------------------
# Provider errors
# ---------------------------------------------------------------------------

class ProviderError(FantasyAuthorError):
    """A provider call failed for a non-transient reason."""

    #: Structured attempt classification (streamed-attempt taxonomy). ``None``
    #: on the base class; specific subclasses below pin a concrete value so the
    #: router's cooldown map and ``app_ingress._failure_notice`` can branch on
    #: the *class* of failure instead of substring-matching the message.
    failure_class: str | None = None

    #: Streamed-attempt telemetry snapshot attached at raise time by the
    #: streaming reader (Slice 1 blocker K): ``side_effect_state`` /
    #: ``tool_phase`` / ``ttft_ms`` / ``last_progress_age_ms`` / ``exit_code`` /
    #: ``terminal`` / ``provider``. The success path carries these on
    #: :class:`~tinyassets.providers.base.ProviderResponse`; attaching them to the
    #: raised exception lets the router + the honest user notice reason about a
    #: FAILED attempt (e.g. whether a tool may have run) instead of only the
    #: message string. ``None`` on the base class and on non-streaming raises.
    attempt_telemetry: dict | None = None


class ProviderTimeoutError(ProviderError):
    """A provider subprocess exceeded the activity timeout."""


class ProviderIdleTimeoutError(ProviderTimeoutError):
    """A streamed served attempt stopped emitting real protocol events.

    The idle watchdog fired: no assistant text delta, tool event, provider
    retry event, or terminal result arrived within the phase's idle interval.
    A subclass of :class:`ProviderTimeoutError` so legacy ``except
    ProviderTimeoutError`` callers keep working, but the router treats it as a
    transient ATTEMPT outcome and does NOT place the sole served writer on a
    provider-wide cooldown — the next turn stays eligible.
    """

    failure_class = "provider_idle_timeout"


class InteractiveDeadlineError(ProviderTimeoutError):
    """A streamed served attempt reached the absolute interactive safety cap.

    The turn kept making progress but ran past the absolute cap (a fairness /
    resource backstop, not evidence of an unhealthy provider). Like
    :class:`ProviderIdleTimeoutError`, this does NOT cool the provider.
    """

    failure_class = "interactive_deadline"


class ProviderUnavailableError(ProviderError):
    """Provider returned a signal that it is temporarily unreachable
    (e.g. exit code 1 within <5 s, rate-limit header, auth failure).
    Triggers a sticky cooldown on the provider.
    """


class ProviderRateLimitedError(ProviderUnavailableError):
    """The provider reported a genuine rate limit (documented retry event).

    Carries ``retry_after`` (seconds) when the provider supplied one so the
    router can cool the provider for exactly that window instead of a fixed
    default. A subclass of :class:`ProviderUnavailableError` so existing
    unavailable-handling still applies where the precise handler is absent.
    """

    failure_class = "provider_rate_limited"

    def __init__(self, *args, retry_after: float | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry_after = retry_after


class ProviderOverloadedError(ProviderUnavailableError):
    """The provider reported a transient overload (documented retry event)."""

    failure_class = "provider_overloaded"

    def __init__(self, *args, retry_after: float | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry_after = retry_after


class ProviderProtocolError(ProviderError):
    """The provider emitted an unparseable / malformed event stream.

    Raised by the streaming reader when a non-whitespace stdout line is not a
    valid stream-json event object (fail loud per hard rule #8 rather than
    silently discarding garbage).
    """

    failure_class = "provider_protocol_error"


class ProviderAuthorityHeldError(ProviderError):
    """Provider execution has no requester- or platform-owned authority."""

    failure_class = "authority_held"


class AllProvidersExhaustedError(ProviderError):
    """Every provider in the fallback chain failed or is in cooldown.

    FEAT-006: optionally carries a structured ``attempts`` list of
    :class:`tinyassets.providers.diagnostics.ProviderAttemptDiagnostic`
    and a ``chain_state`` dict so callers can diagnose *why* each
    provider was skipped (auth_invalid / quota_or_cooldown /
    endpoint_unreachable / etc) rather than parse the human-readable
    message. Both fields default to ``None`` for backward compatibility
    with pre-FEAT-006 raise sites that pass only a message.
    """

    def __init__(
        self,
        *args,
        attempts=None,
        chain_state=None,
        failure_class=None,
        retry_after=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        # list[ProviderAttemptDiagnostic] | None
        self.attempts = attempts
        # dict | None — typically built via diagnostics.build_chain_state
        self.chain_state = chain_state
        # str | None — the dominant streamed-attempt failure_class of the last
        # failed attempt, so a single-provider (served / pinned / armed) chain
        # can surface an honest, class-specific notice (timeout != capacity).
        self.failure_class = failure_class
        # float | None — provider-supplied retry-after (seconds) for a rate-limit
        # / overload outcome, carried through for the user-facing notice.
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# Graph / checkpoint errors
# ---------------------------------------------------------------------------

class CheckpointError(FantasyAuthorError):
    """Failed to save or load a LangGraph checkpoint."""


class GraphCompilationError(FantasyAuthorError):
    """A StateGraph could not be compiled (topology issue)."""


# ---------------------------------------------------------------------------
# State / validation errors
# ---------------------------------------------------------------------------

class StateValidationError(FantasyAuthorError):
    """State dict is missing required keys or has invalid types."""


class ConstraintViolationError(FantasyAuthorError):
    """ASP solver reported an unsatisfiable model (world rule breach)."""


class ContextBundleOverflowError(FantasyAuthorError):
    """MemoryManager could not trim a ContextBundle under the token budget.

    Raised when iterative trim + string-body truncation both fail to bring
    the bundle under ``MAX_CONTEXT_TOKENS``. Surfaces loudly so callers know
    the bundle is unsafe for LLM dispatch (rather than silently passing
    an over-budget payload that the model will truncate mid-stream).
    """


class StorageCapExceeded(FantasyAuthorError):
    """Per-subsystem storage hard cap reached; new writes refused.

    Raised by ``tinyassets.storage.caps.enforce_write_cap`` when a
    subsystem's on-disk size meets or exceeds its configured hard cap.
    Surfaces loudly (Hard Rule #8) so the 2026-04-23 silent-fill class
    cannot recur under the Phase-3 cap regime: write-site callers must
    either handle the raise (e.g. rotate older artifacts first) or
    propagate it to operator paging.
    """
