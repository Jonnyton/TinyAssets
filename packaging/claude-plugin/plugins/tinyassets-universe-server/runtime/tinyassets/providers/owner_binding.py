"""The platform has no LLM (AGENTS.md Hard Rule 15) -- the one enforcement point.

Only a powered universe calls an LLM, with the credentials its owner connected,
for that universe alone. The platform never makes, needs or brokers a model call
for its own operation (onboarding, selection, ranking, moderation, investigation,
maintenance, monitoring), and no platform, host, maintainer or shared credential
ever serves one, including as a fallback.

Every provider launch in :class:`tinyassets.providers.router.ProviderRouter`
passes through the two checks below, and the router is the only code that calls
``BaseProvider.complete``. So this module is where the rule is enforced; nothing
else needs to remember it.

* :func:`require_owner_bound_context` runs when a call ENTERS the router. A call
  with no universe, or with a universe but no owner authority (neither a
  server-minted ``ProviderInvocationCarrier`` for that universe nor a live
  ``provider_request`` the router will authorize against the owner's serving
  binding), is refused before any provider is looked at, probed or configured.
* :func:`require_owner_bound_dispatch` runs immediately before a provider is
  launched. The launched provider must be the one the owner's authority names,
  it must resolve credentials from the universe (never the host), and it must
  not be one of the built-in providers whose only credential source is the host
  process: ``gemini-free`` / ``groq-free`` / ``grok-free`` read the host's
  ``*_API_KEY`` environment, and ``ollama-local`` is the host's own model server.
  An owner who wants Gemini, Groq, xAI or their own Ollama connects it as an open
  provider (``api_key_http:<definition>``), which carries their own credential.

A refusal raises :class:`~tinyassets.exceptions.PlatformLLMCallRefusedError`, a
``ProviderAuthorityHeldError``: every caller already propagates that class
instead of swallowing it as a provider fault, so the refusal is loud (Hard
Rule 8) and never degrades into a fallback string.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tinyassets.exceptions import PlatformLLMCallRefusedError

#: Built-in providers whose only credential source is the host process. None of
#: them can carry an owner's connection, so none may ever serve a universe.
HOST_CREDENTIAL_PROVIDERS: frozenset[str] = frozenset({
    "gemini-free",
    "groq-free",
    "grok-free",
    "ollama-local",
})

_NO_UNIVERSE = (
    "The platform has no LLM: a model call must come from a powered universe "
    "using its owner's own connected credentials. This call names no universe, "
    "so it was refused. No platform, host or shared credential serves it."
)
#: The owner-facing refusal. Run-failure taxonomy keys on "connect your
#: provider" (``tinyassets/api/runs.py``), so a universe that has no owner
#: authority reads as the actionable fix, not as a platform fault.
CONNECT_PROVIDER_MESSAGE = (
    "Connect your provider before running this universe. TinyAssets will not "
    "borrow platform credentials or start a metered trial."
)
_NO_OWNER_AUTHORITY = (
    f"{CONNECT_PROVIDER_MESSAGE} (The platform has no LLM: this call names a "
    "universe but carries no owner authority, so it was refused rather than "
    "served from a platform or host credential.)"
)


def _carrier_universe_id(carrier: Any) -> str:
    receipt = getattr(carrier, "_receipt", None)
    return str(getattr(receipt, "universe_id", "") or "")


def require_owner_bound_context(universe_context: Any, *, operation: str | None) -> None:
    """Refuse a router call that is not bound to one universe's owner authority."""
    from tinyassets.provider_work_authority import ProviderInvocationCarrier
    from tinyassets.providers.base import UniverseContext

    if universe_context is None:
        raise PlatformLLMCallRefusedError(_NO_UNIVERSE)
    if not isinstance(universe_context, UniverseContext):
        raise PlatformLLMCallRefusedError(
            "The platform has no LLM: the call's universe context is not a "
            "UniverseContext, so it cannot name an owner."
        )
    universe_dir = universe_context.universe_dir
    if universe_dir is None:
        # A context with no universe directory is the retired single-universe
        # daemon shape: it would resolve config and credentials from process
        # globals. It names no owner, so it gets the owner-facing refusal.
        raise PlatformLLMCallRefusedError(_NO_OWNER_AUTHORITY)
    carrier = universe_context.provider_invocation
    if carrier is not None:
        # A carrier that is not the exact server-minted type is refused by the
        # router's own carrier validation (PermissionError) before any access.
        if (
            type(carrier) is ProviderInvocationCarrier
            and _carrier_universe_id(carrier) != Path(universe_dir).name
        ):
            raise PlatformLLMCallRefusedError(
                "The platform has no LLM: the provider invocation carrier belongs "
                "to a different universe than the one this call names."
            )
        return
    if universe_context.provider_request is None or not operation:
        raise PlatformLLMCallRefusedError(_NO_OWNER_AUTHORITY)


def require_owner_bound_dispatch(
    provider_name: str,
    *,
    universe_dir: Path | None,
    served_authority: Any = None,
    invocation_carrier: Any = None,
) -> None:
    """Refuse a provider launch the owner's authority does not name."""
    if universe_dir is None:
        raise PlatformLLMCallRefusedError(_NO_UNIVERSE)
    authority = served_authority if served_authority is not None else invocation_carrier
    if authority is None:
        raise PlatformLLMCallRefusedError(_NO_OWNER_AUTHORITY)
    if provider_name != getattr(authority, "provider", None):
        raise PlatformLLMCallRefusedError(
            f"The platform has no LLM: provider {provider_name!r} is not the "
            "provider the owner's binding names, so it may not serve this call."
        )
    if provider_name in HOST_CREDENTIAL_PROVIDERS:
        raise PlatformLLMCallRefusedError(
            f"The platform has no LLM: {provider_name!r} can only use the host's "
            "credentials or the host's own model server, never the owner's. "
            "Connect this source to the universe as your own provider instead."
        )


__all__ = [
    "CONNECT_PROVIDER_MESSAGE",
    "HOST_CREDENTIAL_PROVIDERS",
    "require_owner_bound_context",
    "require_owner_bound_dispatch",
]
