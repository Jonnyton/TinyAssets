"""General LLM-call bridge for the engine.

Routes all provider calls through the shared :class:`ProviderRouter`
(synchronous ``call_sync``), with a deterministic mock path for tests and an
explicit fallback when providers are exhausted. This is the engine's single,
domain-agnostic LLM-call primitive — engine code must reach the LLM only
through this module, never through a domain package. (It was previously hosted
inside the fantasy domain; the relocation is the de-fantasy audit's Tier A:
``docs/audits/2026-06-24-fantasy-architecture-residue-audit.md``.)

The router is injectable: a long-running host (e.g. a daemon) builds its own
fully-configured :class:`ProviderRouter` and installs it via
:func:`set_provider_router`. A bare import builds a best-effort fallback router
from whatever provider binaries/keys are present, so scripts and tests work
without a daemon.

Use the accessors (:func:`get_last_provider`, :func:`is_force_mock`) rather than
``from ... import last_provider`` / ``_FORCE_MOCK``: the import-the-name pattern
binds an import-time snapshot that never reflects later reassignment (the latent
bug at ``ingestion/extractors.py``, where ``model=last_provider`` always wrote
an empty string).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

if TYPE_CHECKING:
    from tinyassets.providers.router import ProviderRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mutable module state (use the accessors below; do not import these names)
# ---------------------------------------------------------------------------

# Skip real provider calls and return mock/fallback output. Tests set this via
# set_force_mock() in conftest.
_force_mock = False

# The router call_provider() routes through. None until a router is built or
# injected. A daemon overwrites it via set_provider_router().
_real_router: "Optional[ProviderRouter]" = None

# Provider name used by the most recent call. Read via get_last_provider().
_last_provider: str = ""


def set_force_mock(value: bool) -> None:
    """Enable/disable the mock path (tests)."""
    global _force_mock
    _force_mock = bool(value)


def is_force_mock() -> bool:
    """Whether call_provider() short-circuits to mock/fallback output."""
    return _force_mock


def set_provider_router(router: "Optional[ProviderRouter]") -> None:
    """Install the router call_provider() routes through.

    This is the daemon-injection seam: ``DaemonController`` builds a fully
    configured router and installs it here so the engine's LLM calls use the
    host's provider configuration instead of the import-time fallback.
    """
    global _real_router
    _real_router = router


def get_provider_router() -> "Optional[ProviderRouter]":
    """The router currently installed (fallback or daemon-injected)."""
    return _real_router


def get_last_provider() -> str:
    """Provider name used by the most recent call_provider() — live, not a snapshot."""
    return _last_provider


# ---------------------------------------------------------------------------
# Fallback router for standalone / script / test usage
# ---------------------------------------------------------------------------


def _build_fallback_router() -> "Optional[ProviderRouter]":
    """Best-effort router registering whatever providers are available.

    A daemon overwrites this via :func:`set_provider_router`, so these
    registrations only serve standalone/script/test usage. Each provider import
    is independently guarded so a missing optional dependency never breaks the
    bridge.
    """
    try:
        from tinyassets.providers.base import subscription_auth_health
        from tinyassets.providers.router import ProviderRouter
    except ImportError:
        logger.info("Real ProviderRouter not available; using mock-only provider")
        return None

    router = ProviderRouter(auth_health=subscription_auth_health)

    try:
        from tinyassets.providers.claude_provider import ClaudeProvider
        if ClaudeProvider.is_available():
            router.register(ClaudeProvider())
            logger.info("Registered ClaudeProvider")
        else:
            logger.debug("claude binary not found - ClaudeProvider skipped")
    except Exception:
        logger.debug("ClaudeProvider not available")

    try:
        from tinyassets.providers.codex_provider import CodexProvider
        if CodexProvider.is_available():
            router.register(CodexProvider())
            logger.info("Registered CodexProvider")
        else:
            logger.debug("codex binary not found - CodexProvider skipped")
    except Exception:
        logger.debug("CodexProvider not available")

    try:
        from tinyassets.providers.ollama_provider import OllamaProvider
        router.register(OllamaProvider())
        logger.info("Registered OllamaProvider")
    except Exception:
        logger.debug("OllamaProvider not available")

    try:
        from tinyassets.providers.gemini_provider import GeminiProvider
        router.register(GeminiProvider())
        logger.info("Registered GeminiProvider")
    except Exception:
        logger.debug("GeminiProvider not available")

    try:
        from tinyassets.providers.groq_provider import GroqProvider
        router.register(GroqProvider())
        logger.info("Registered GroqProvider")
    except Exception:
        logger.debug("GroqProvider not available")

    try:
        from tinyassets.providers.grok_provider import GrokProvider
        router.register(GrokProvider())
        logger.info("Registered GrokProvider")
    except Exception:
        logger.debug("GrokProvider not available")

    logger.info(
        "ProviderRouter ready with providers: %s",
        router.available_providers,
    )
    return router


_real_router = _build_fallback_router()


# ---------------------------------------------------------------------------
# Public call primitive
# ---------------------------------------------------------------------------


def _call_router_with_retry(
    role: str,
    prompt: str,
    system: str,
    config: Any = None,
    universe_context: Any = None,
) -> str:
    """Call the installed router with exception-type exhaustion retries.

    Every ``AllProvidersExhaustedError`` is eligible for up to three total
    attempts, regardless of whether its cause is transient or permanent.  The
    configured exponential wait yields two-second waits after failures one and
    two when all three attempts are needed, with no wait after terminal failure.
    """
    from tinyassets.exceptions import AllProvidersExhaustedError

    @retry(
        retry=retry_if_exception_type(AllProvidersExhaustedError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    def _attempt() -> str:
        global _last_provider
        # Only forward config / universe_context when set, so existing
        # routers/stubs with the 3-arg call_sync signature keep working
        # (backward-compat).
        kwargs: dict[str, Any] = {}
        if universe_context is not None:
            kwargs["universe_context"] = universe_context
        if config is not None:
            result = _real_router.call_sync(role, prompt, system, config, **kwargs)
        else:
            result = _real_router.call_sync(role, prompt, system, **kwargs)
        _last_provider = result.provider
        return result.text

    return _attempt()


def call_provider(
    prompt: str,
    system: str = "",
    *,
    role: str = "writer",
    fallback_response: str | None = None,
    config: Any = None,
    universe_context: Any = None,
) -> str:
    """Call an LLM provider with automatic fallback.

    Routes through the installed :class:`ProviderRouter`'s synchronous
    ``call_sync`` (which runs the async fallback chain in a dedicated thread).
    On transient exhaustion, retries up to 3 times with exponential backoff.
    Falls back to mock/``fallback_response`` only when forced or exhausted.

    Parameters
    ----------
    prompt:
        The user prompt.
    system:
        System prompt.
    role:
        Routing role (writer, judge, extract).
    fallback_response:
        Returned if all providers fail. If ``None`` in production, provider
        exhaustion surfaces as the real error rather than masquerading as an
        empty LLM response downstream.
    universe_context:
        Optional per-universe routing context (:class:`~tinyassets.providers.
        base.UniverseContext`) threaded through to ``call_sync`` so engine
        preference + vault auth resolve for the given universe instead of the
        process globals.
    """
    if _force_mock:
        if fallback_response is not None:
            return fallback_response
        # Preserve the exact legacy string (callers/tests may assert on it).
        return "[Mock response -- _FORCE_MOCK is True]"

    provider_error: Exception | None = None

    if _real_router is not None:
        try:
            return _call_router_with_retry(
                role, prompt, system, config, universe_context,
            )
        except Exception as e:
            provider_error = e
            logger.error(
                "All providers exhausted for role=%s after retries: %s", role, e,
            )

    if fallback_response is not None:
        logger.warning(
            "Using fallback response for role=%s (%d chars)",
            role, len(fallback_response),
        )
        return fallback_response
    if provider_error is not None:
        raise provider_error

    from tinyassets.exceptions import AllProvidersExhaustedError

    raise AllProvidersExhaustedError(
        f"No provider router available for role={role!r} and no fallback_response "
        "was provided."
    )
