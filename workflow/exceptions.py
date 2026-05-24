"""Exception hierarchy for Workflow.

Every exception in the system inherits from FantasyAuthorError so callers
can catch broadly when appropriate.
"""


class FantasyAuthorError(Exception):
    """Base exception for all Workflow errors."""


# ---------------------------------------------------------------------------
# Provider errors
# ---------------------------------------------------------------------------

class ProviderError(FantasyAuthorError):
    """A provider call failed for a non-transient reason."""


class ProviderTimeoutError(ProviderError):
    """A provider subprocess exceeded the activity timeout."""


class ProviderUnavailableError(ProviderError):
    """Provider returned a signal that it is temporarily unreachable
    (e.g. exit code 1 within <5 s, rate-limit header, auth failure).
    Triggers a sticky cooldown on the provider.
    """


class AllProvidersExhaustedError(ProviderError):
    """Every provider in the fallback chain failed or is in cooldown.

    FEAT-006: optionally carries a structured ``attempts`` list of
    :class:`workflow.providers.diagnostics.ProviderAttemptDiagnostic`
    and a ``chain_state`` dict so callers can diagnose *why* each
    provider was skipped (auth_invalid / quota_or_cooldown /
    endpoint_unreachable / etc) rather than parse the human-readable
    message. Both fields default to ``None`` for backward compatibility
    with pre-FEAT-006 raise sites that pass only a message.
    """

    def __init__(self, *args, attempts=None, chain_state=None, **kwargs):
        super().__init__(*args, **kwargs)
        # list[ProviderAttemptDiagnostic] | None
        self.attempts = attempts
        # dict | None — typically built via diagnostics.build_chain_state
        self.chain_state = chain_state


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

    Raised by ``workflow.storage.caps.enforce_write_cap`` when a
    subsystem's on-disk size meets or exceeds its configured hard cap.
    Surfaces loudly (Hard Rule #8) so the 2026-04-23 silent-fill class
    cannot recur under the Phase-3 cap regime: write-site callers must
    either handle the raise (e.g. rotate older artifacts first) or
    propagate it to operator paging.
    """
