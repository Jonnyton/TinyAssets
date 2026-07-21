"""Provider router -- fallback chains across six providers.

Hard invariant: every call has a fallback chain that terminates at
``ollama-local``.  The system NEVER stops due to provider
unavailability unless local models are also down.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from tinyassets.exceptions import (
    AllProvidersExhaustedError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from tinyassets.providers.base import (
    DEGRADED_JUDGE_RESPONSE,
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
    api_key_providers_enabled,
    enforce_os_sandbox,
)
from tinyassets.providers.diagnostics import (
    ProviderAttemptDiagnostic,
    build_chain_state,
    classify_unavailable,
)
from tinyassets.providers.quota import (
    COOLDOWN_OTHER,
    COOLDOWN_TIMEOUT,
    COOLDOWN_UNAVAILABLE,
    QuotaTracker,
)

if TYPE_CHECKING:
    from pathlib import Path

    from tinyassets.config import UniverseConfig

logger = logging.getLogger(__name__)


def _universe_provides_provider_auth(
    provider_name: str, universe_dir: "Path | None",
) -> bool:
    """True iff the broker-backed engine binding serves *provider*."""
    try:
        from tinyassets.credential_broker import resolve_universe_from_env
        from tinyassets.engine_binding import resolve_engine_binding

        resolved = (
            universe_dir if universe_dir is not None else resolve_universe_from_env()
        )
        if resolved is None:
            return False
        return resolve_engine_binding(resolved).serves_via_vault(provider_name)
    except Exception:  # noqa: BLE001 — health filtering never breaks routing
        return False


def _enforce_writer_binding(
    chain: list[str],
    *,
    role: str,
    is_pinned_writer: bool,
    pin_writer: str,
    universe_dir: "Path | None",
) -> list[str]:
    """C1: a BYO-BOUND universe's WRITER never falls through to a platform-auth
    provider. The ONE helper applied on EVERY writer route (normal, pinned,
    policy).

    Covers BOTH identity paths — an explicit ``universe_dir`` AND the
    process-global ``TINYASSETS_UNIVERSE`` env fallback (mirrors how the
    auth-health KEEP bypass resolves) — so an external-daemon child with only
    ``TINYASSETS_UNIVERSE`` set is still constrained. **FAILS CLOSED:** any
    binding/resolution error raises ``AllProvidersExhaustedError`` (never
    swallowed → never leaks to a platform-auth provider).

    Inert unless executable BYO is enabled (DARK by default), because only then
    can a universe be bound. The non-ambient guarantee is writer-role only (see
    the custody design note §0.2) — BUT a WRITER route is not just ``role ==
    "writer"``: ``FALLBACK_CHAINS.get(role, writer)`` gives any UNKNOWN role the
    writer chain, and ``model_hint`` is user-authored free-form that becomes the
    role verbatim. So an unknown role is a writer route and MUST be enforced too
    (F1a — else ``model_hint:"novelist"`` silently escapes the constraint).
    """
    is_writer_route = role == "writer" or role not in FALLBACK_CHAINS
    if not is_writer_route:
        return chain
    from tinyassets.credential_broker import resolve_universe_from_env
    from tinyassets.engine_binding import (
        execution_blocked_reason,
        resolve_engine_binding,
    )

    resolved = universe_dir if universe_dir is not None else resolve_universe_from_env()
    if resolved is None:
        return chain  # no bound-universe context.
    try:
        binding = resolve_engine_binding(resolved)
    except AllProvidersExhaustedError:
        raise
    except Exception as exc:  # noqa: BLE001 — FAIL CLOSED, never fall through.
        raise AllProvidersExhaustedError(
            "writer routing refused: could not resolve the universe's engine "
            f"binding ({exc}); refusing to fall through to platform auth."
        ) from exc
    if not binding.bound:
        blocked_reason = execution_blocked_reason(resolved)
        if blocked_reason is not None:
            raise AllProvidersExhaustedError(
                "writer routing refused: external daemon execution is "
                f"quarantined ({blocked_reason})"
            )
        return chain  # legacy unbound local route.
    eligible = set(binding.eligible_providers)
    if is_pinned_writer and pin_writer not in eligible:
        raise AllProvidersExhaustedError(
            f"Pinned writer {pin_writer!r} is not in the BYO-bound universe's "
            f"eligible providers {sorted(eligible)!r}. A bound universe never "
            "borrows platform auth; re-bind or clear the pin."
        )
    constrained = [p for p in chain if p in eligible]
    if not constrained:
        raise AllProvidersExhaustedError(
            "BYO-bound universe has no eligible writer provider "
            f"(eligible={sorted(eligible)!r}); no fallback to platform auth."
        )
    return constrained


def _preflight_retired_universe(universe_dir: "Path | None") -> None:
    """Round-21 #1 / round-22 #1-#2: a RETIRED or UNREADABLE-credential universe must
    NEVER execute on ambient host credentials — through ANY provider, including LOCAL /
    in-process ones (ollama-local) that never raise a retired-lane error at spawn.

    Defense-in-depth mirror of the primary graph-execution chokepoint
    (:func:`tinyassets.runs._invoke_graph`). Enforces the SAME fail-closed invariant
    (:func:`tinyassets.engine_binding.execution_blocked_reason`, strict — a malformed
    vault fails CLOSED) on EVERY router path/fan-out (call, call_with_policy,
    call_judge_ensemble), INDEPENDENT of ``TINYASSETS_NON_AMBIENT_WORK`` and of whether
    a provider raises. Resolves the universe from the explicit dir ELSE the pinned
    execution universe (set at the run boundary) ELSE ``TINYASSETS_UNIVERSE``. On a
    block, raises :class:`RetiredCredentialStateError` — a TERMINAL routing failure.
    """
    from tinyassets.credential_broker import resolve_universe_from_env
    from tinyassets.engine_binding import (
        RetiredCredentialStateError,
        execution_blocked_reason,
    )
    from tinyassets.execution_context import get_execution_universe

    resolved = universe_dir
    if resolved is None:
        resolved = get_execution_universe()
    if resolved is None:
        resolved = resolve_universe_from_env()
    if resolved is None:
        return
    if execution_blocked_reason(resolved) is not None:
        raise RetiredCredentialStateError(
            f"retired credential state for {resolved}; no ambient fallback"
        )


def _resolve_universe_config(
    universe_context: UniverseContext | None,
) -> "UniverseConfig | None":
    """Resolve the effective UniverseConfig for a call.

    An explicit ``universe_context.config`` wins; otherwise fall back to the
    process-global ``runtime.universe_config`` (preserving today's
    single-universe-daemon behavior). Returns ``None`` only when neither is
    available.
    """
    if universe_context is not None and universe_context.config is not None:
        return universe_context.config
    try:
        from tinyassets import runtime_singletons as runtime

        return runtime.universe_config
    except Exception:
        return None


def _default_config(resolved: "UniverseConfig | None" = None) -> ModelConfig:
    """Build default ModelConfig from the resolved universe config if available.

    ``resolved`` is the config produced by :func:`_resolve_universe_config`.
    When omitted, falls back to the process-global ``runtime.universe_config``
    so bare callers keep today's behavior.
    """
    try:
        if resolved is None:
            from tinyassets import runtime_singletons as runtime

            resolved = runtime.universe_config
        return ModelConfig(
            temperature=resolved.temperature,
            timeout=resolved.timeout,
            max_tokens=resolved.max_tokens,
        )
    except Exception:
        return ModelConfig()

# Fallback chains per role (spec Section 8.3).
FALLBACK_CHAINS: dict[str, list[str]] = {
    "writer": ["claude-code", "codex", "gemini-free", "groq-free", "grok-free", "ollama-local"],
    "judge": ["codex", "gemini-free", "groq-free", "grok-free", "ollama-local"],
    "extract": ["codex", "gemini-free", "groq-free", "ollama-local"],
    "embed": ["ollama-local"],
}

# Judge providers to fan out to in parallel.  Every available provider
# gets one call; results are collected and aggregated.  No chains,
# no fallbacks — just "call everyone, return all responses."
_JUDGE_PROVIDERS: list[str] = [
    "codex", "gemini-free", "groq-free", "grok-free", "ollama-local",
]


_LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama-local"})
_API_KEY_PROVIDERS: frozenset[str] = frozenset(
    {"gemini-free", "groq-free", "grok-free"}
)

# BUG-029 Part B: number of consecutive empty-prose responses from a local
# provider (when chain-drained) before raising AllProvidersExhaustedError.
_CHAIN_DRAIN_EMPTY_THRESHOLD: int = 2

# Sync graph nodes call async provider routing through this bounded pool.
# Keep it above 1 so an unrelated slow provider call does not serialize all
# other sync callers behind one shared worker.
_SYNC_CALL_MAX_WORKERS: int = 8


def _pin_byo_snapshot(method):
    """Round-12 #3: pin ONE immutable ``byo_execution_enabled()`` snapshot for the
    whole routing operation. Route selection (``_enforce_writer_binding``) and the
    awaited subprocess spawn (``provider.complete`` → ``subprocess_env_for_provider``)
    both run inside this ``with``, so a mid-call attestation flip can never let
    routing constrain to the BYO writer while the spawn restores platform auth. The
    contextvar is set for the entire awaited coroutine (same task context) and any
    fan-out sub-tasks copy it at creation.

    Round-15 #2: the snapshot carries this call's per-record context — the routing
    universe from ``universe_context`` (else the process-global ``TINYASSETS_UNIVERSE``)
    — so the per-record attestation is not context-free inside the pin."""

    @functools.wraps(method)
    async def _wrapper(self, *args, **kwargs):
        from tinyassets.credential_broker import resolve_universe_from_env
        from tinyassets.engine_binding import pin_byo_execution_snapshot

        uctx = kwargs.get("universe_context")
        udir = getattr(uctx, "universe_dir", None) if uctx is not None else None
        if udir is None:
            udir = resolve_universe_from_env()
        with pin_byo_execution_snapshot(udir):
            return await method(self, *args, **kwargs)

    return _wrapper


class ProviderRouter:
    """Routes LLM calls across providers with fallback and quota tracking.

    Parameters
    ----------
    providers : dict[str, BaseProvider]
        Map from provider name to provider instance.  Only providers
        present in this dict are reachable.
    quota : QuotaTracker | None
        Shared quota tracker.  A default is created if not supplied.
    chain_drain_empty_threshold : int
        Consecutive empty-prose responses from a local provider (when all
        API providers are in cooldown) before raising
        AllProvidersExhaustedError.  Default: 2.
    auth_health : Callable[[str], dict[str, str]] | None
        Subscription-login probe (``tinyassets.providers.base.
        subscription_auth_health``) injected by the daemon. When supplied,
        a provider whose login is definitively ``not_logged_in`` is dropped
        from fallback chains (a pinned writer fails loud instead). Default
        ``None`` disables the gate, so script/test routers that register
        fake providers are unaffected (2026-06-25 loop-wedge follow-up).
    """

    def __init__(
        self,
        providers: dict[str, BaseProvider] | None = None,
        quota: QuotaTracker | None = None,
        chain_drain_empty_threshold: int = _CHAIN_DRAIN_EMPTY_THRESHOLD,
        auth_health: Callable[[str], dict[str, str]] | None = None,
    ) -> None:
        self._providers: dict[str, BaseProvider] = providers or {}
        self._quota = quota or QuotaTracker()
        self._chain_drain_empty_threshold = chain_drain_empty_threshold
        self._auth_health = auth_health
        # {provider_name: consecutive_empty_count} — reset on non-empty response.
        self._consecutive_empty: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def register(self, provider: BaseProvider) -> None:
        """Add or replace a provider in the registry."""
        self._providers[provider.name] = provider

    @property
    def available_providers(self) -> list[str]:
        return list(self._providers)

    def effective_chain(
        self,
        chain: list[str],
    ) -> tuple[list[str], list[ProviderAttemptDiagnostic]]:
        """Return registered providers from *chain* plus explicit exclusions.

        ``FALLBACK_CHAINS`` records preference order, but runtime routing must
        only advertise and iterate providers that were actually registered at
        startup. Missing CLI-backed providers, such as ``claude-code`` in the
        cloud image, are reported as exclusions rather than silent phantom
        entries at the front of the live chain.
        """
        effective: list[str] = []
        excluded: list[ProviderAttemptDiagnostic] = []
        for provider_name in chain:
            if provider_name in self._providers:
                effective.append(provider_name)
                continue
            excluded.append(ProviderAttemptDiagnostic(
                provider=provider_name,
                status="skipped",
                skip_class="not_in_registry",
                detail="provider name not registered with daemon",
            ))
        return effective, excluded

    # ------------------------------------------------------------------
    # Core routing
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_preference(chain: list[str], preferred: str) -> list[str]:
        """Reorder *chain* so *preferred* comes first (if present)."""
        if not preferred or preferred not in chain:
            return chain
        return [preferred] + [p for p in chain if p != preferred]

    @staticmethod
    def _current_allowlist(
        resolved: "UniverseConfig | None" = None,
    ) -> list[str] | None:
        """Read the resolved universe's `allowed_providers` allowlist, or None.

        Q6.3 enforcement primitive — see UniverseConfig.allowed_providers.
        ``resolved`` is the config produced by :func:`_resolve_universe_config`
        (explicit ``universe_context`` wins); when omitted, falls back to the
        process-global ``runtime.universe_config``. Returns None when no universe
        config is bound or the field is unset (full fallback chain preserved,
        backwards-compatible).
        """
        try:
            if resolved is None:
                from tinyassets import runtime_singletons as runtime

                resolved = runtime.universe_config
            return resolved.allowed_providers
        except Exception:
            return None

    @staticmethod
    def _apply_allowlist(
        chain: list[str], allowlist: list[str] | None,
    ) -> list[str]:
        """Filter *chain* down to providers in *allowlist*.

        ``allowlist=None`` is a no-op (returns chain unchanged). An empty list
        filters everything out — the caller is responsible for hard-failing
        with ``AllProvidersExhaustedError`` so the policy block is visible.
        """
        if allowlist is None:
            return chain
        return [p for p in chain if p in allowlist]

    @staticmethod
    def _apply_api_key_provider_policy(chain: list[str]) -> list[str]:
        """Drop API-key-backed providers unless the host opted into them."""
        if api_key_providers_enabled():
            return chain
        return [p for p in chain if p not in _API_KEY_PROVIDERS]

    def _apply_auth_health_policy(
        self, chain: list[str], *, universe_dir: Path | None = None,
    ) -> list[str]:
        """Drop subscription-backed providers whose login is definitively dead.

        Mirrors the worker-level self-quarantine (2026-06-25 loop-wedge): a
        provider with missing subscription credentials fails every call, so
        skipping it routes straight to a healthy provider instead of burning
        an attempt and a misleading cooldown.

        No-op when no auth-health probe was injected (the default), so
        script/test routers that register fake providers are unaffected.

        Conservative — only a definitive ``not_logged_in`` drops a provider.
        ``unknown`` (api-key / local providers the probe cannot assess) and
        ``ok`` are always kept, and a probe that raises is treated as "keep",
        so a probe false-negative can never strand a healthy provider.

        Universe-aware (S5 round 5): the probe reports process-GLOBAL
        subscription health, but a provider whose GLOBAL login is dead is still
        runnable when the call's universe vault supplies usable per-universe auth
        (a BYO key / materialized auth home), which the router applies to the CLI
        subprocess at call time. So a ``not_logged_in`` provider is KEPT when the
        universe vault authenticates it — otherwise the gate would starve bound
        BYO-key capacity that the non-ambient gate just let spawn. Only the
        subscription-health rejection is bypassed; quota/cooldown and hard
        provider errors keep their semantics elsewhere.
        """
        if self._auth_health is None:
            return chain
        alive: list[str] = []
        for provider_name in chain:
            try:
                status = self._auth_health(provider_name).get("status")
            except Exception:
                logger.debug("auth-health probe failed for %s; keeping", provider_name)
                status = None
            if status != "not_logged_in":
                alive.append(provider_name)
            elif _universe_provides_provider_auth(provider_name, universe_dir):
                # This bypass is gated behind the vault-encryption prerequisite
                # (byo_execution_enabled, F3) — DARK by default in this deploy.
                # Within that gate it is NOT further gated on the non-ambient flag:
                # a universe holding a validated BYO key for a globally-dead
                # provider is not starved (latent-bug fix; BYO is the sanctioned
                # lane). The child materializes the vault env at call time.
                logger.info(
                    "Provider %s global login is not_logged_in but the universe "
                    "vault authenticates it — keeping (per-universe auth applied "
                    "at call time).",
                    provider_name,
                )
                alive.append(provider_name)
        return alive

    def _filter_coding_capable(self, chain: list[str]) -> list[str]:
        """Keep only providers that DECLARE AND ENFORCE the coding-sandbox
        contract (``supports_coding_sandbox``).

        Codex latest-model FINDING 4: a sandbox-required call forwards the
        hardened config down the whole writer chain, but a text/HTTP/local
        provider (ollama-local) ignores it and would return a fake 'patched'
        without confining anything. Registered-but-non-capable providers are
        excluded BEFORE dispatch; if the filter empties the chain the caller
        fails loud (never a text-provider fake success — Hard Rule 8).
        """
        return [
            name for name in chain
            if getattr(self._providers.get(name), "supports_coding_sandbox", False)
        ]

    def _filter_closed_tool_surface_capable(self, chain: list[str]) -> list[str]:
        """Keep only providers that HONOR a closed/text-only tool surface
        (``enforces_closed_tool_surface``).

        Codex S3 REJECT r2 (C1b): a ``closed_tool_surface`` call routed to codex
        would silently keep tools (codex ignores tool policy). Filter to enforcing
        providers (claude-code) before dispatch; empty ⇒ caller fails loud.
        """
        return [
            name for name in chain
            if getattr(
                self._providers.get(name), "enforces_closed_tool_surface", False,
            )
        ]

    @_pin_byo_snapshot
    async def call(
        self,
        role: str,
        prompt: str,
        system: str,
        config: ModelConfig | None = None,
        *,
        universe_context: UniverseContext | None = None,
    ) -> ProviderResponse:
        """Route a single call through the fallback chain for *role*.

        Returns a :class:`ProviderResponse` on success.  For judge role,
        returns a degraded sentinel when all providers are exhausted.
        For other roles, raises :class:`AllProvidersExhaustedError`.

        ``universe_context``, when supplied, resolves this call's engine
        preference + allowlist + vault-backed auth from an EXPLICIT argument
        instead of the process globals — the multi-universe seam.
        """
        resolved_config = _resolve_universe_config(universe_context)
        universe_dir = universe_context.universe_dir if universe_context else None
        # Round-21 #1: fail closed BEFORE any provider is tried if the universe is
        # retired and not re-bound — a retired universe must never execute on ambient
        # host creds, even through a local/in-process provider that would not raise.
        _preflight_retired_universe(universe_dir)
        cfg = config or _default_config(resolved_config)
        # Coding-node fail-closed preflight (patch-loop S3): a call requiring an
        # OS sandbox must not be dispatched to ANY provider when none is
        # available — refuse loudly here rather than let a fallback provider (or
        # a local model producing fake text) run the node unconfined (rule #8).
        enforce_os_sandbox(cfg)
        chain = FALLBACK_CHAINS.get(role, FALLBACK_CHAINS["writer"])

        # Hard pin: TINYASSETS_PIN_WRITER narrows the writer chain to a
        # single provider for this call. No fallback — if the pinned
        # provider fails, the call fails loudly (hard rule #8).
        pin_writer = os.environ.get("TINYASSETS_PIN_WRITER", "").strip()
        is_pinned_writer = role == "writer" and bool(pin_writer)
        if is_pinned_writer:
            chain = [pin_writer]
        else:
            # Apply per-universe provider preference from the resolved config.
            try:
                ucfg = resolved_config
                if ucfg is not None:
                    if role == "writer" and ucfg.preferred_writer:
                        chain = self._apply_preference(chain, ucfg.preferred_writer)
                    elif role == "judge" and ucfg.preferred_judge:
                        chain = self._apply_preference(chain, ucfg.preferred_judge)
            except Exception:
                pass

        # C1: a BYO-BOUND universe's WRITER must NEVER fall through to a
        # platform-auth provider. Centralized in ONE helper applied on EVERY
        # writer route (normal, pinned, policy) — see call_with_policy too. It
        # resolves the universe from the explicit dir ELSE TINYASSETS_UNIVERSE,
        # and FAILS CLOSED on any binding/resolution error. Inert in this deploy:
        # bound universes require executable BYO (byo_execution_enabled), DARK by
        # default, so the writer chain is unchanged.
        chain = _enforce_writer_binding(
            chain, role=role, is_pinned_writer=is_pinned_writer,
            pin_writer=pin_writer, universe_dir=universe_dir,
        )

        # Q6.3 — apply per-universe allowlist (privacy primitive). Pin already
        # narrowed chain to [pin_writer] above; the filter then enforces
        # pin × allowlist composition. None = no-op (backwards-compat).
        allowlist = self._current_allowlist(resolved_config)
        if allowlist is not None:
            filtered = self._apply_allowlist(chain, allowlist)
            if not filtered:
                if is_pinned_writer:
                    logger.warning(
                        "Q6.3 allowlist empties chain: pinned writer %r is not "
                        "in allowed_providers=%s; hard-failing.",
                        pin_writer, allowlist,
                    )
                    raise AllProvidersExhaustedError(
                        f"Pinned writer {pin_writer!r} is not in the universe's "
                        f"allowed_providers={allowlist!r}. Either add the "
                        f"provider to the allowlist or clear TINYASSETS_PIN_WRITER."
                    )
                logger.warning(
                    "Q6.3 allowlist empties chain for role=%s: chain=%s "
                    "filtered against allowed_providers=%s; hard-failing.",
                    role, chain, allowlist,
                )
                raise AllProvidersExhaustedError(
                    f"All providers for role={role!r} are blocked by the "
                    f"universe's allowed_providers={allowlist!r}. Daemon will "
                    f"not silently fall back to a disallowed provider."
                )
            chain = filtered

        auth_filtered = self._apply_api_key_provider_policy(chain)
        if not auth_filtered:
            if is_pinned_writer:
                raise AllProvidersExhaustedError(
                    f"Pinned writer provider {pin_writer!r} is API-key-backed "
                    "and disabled by default. Set "
                    "TINYASSETS_ALLOW_API_KEY_PROVIDERS=1 only for an intentional "
                    "API-key daemon, or pin a subscription-backed provider."
                )
            raise AllProvidersExhaustedError(
                f"All providers for role={role!r} are API-key-backed and "
                "disabled by default. TinyAssets daemons are subscription-only "
                "unless TINYASSETS_ALLOW_API_KEY_PROVIDERS=1 is set."
            )
        if auth_filtered != chain:
            logger.info(
                "Ignoring API-key providers by default for role=%s: removed=%s",
                role,
                [p for p in chain if p not in auth_filtered],
            )
            chain = auth_filtered

        # 2026-06-25 loop-wedge: a pinned writer with dead subscription login
        # must fail loud (hard rule #8), not silently route to a different
        # provider. (chain == [pin_writer] here; an empty filter means dead.)
        if is_pinned_writer and not self._apply_auth_health_policy(
            chain, universe_dir=universe_dir,
        ):
            raise AllProvidersExhaustedError(
                f"Pinned writer provider {pin_writer!r} has no subscription "
                "login (auth probe: not_logged_in) and no per-universe vault "
                "auth. Re-seed its credentials, bind a BYO key to the universe, "
                "or clear TINYASSETS_PIN_WRITER to use the fallback chain."
            )

        # FEAT-006 / BUG-025: collect per-provider skip/failure diagnostics so
        # the final AllProvidersExhaustedError can carry structured detail.
        # For normal fallback routing, remove unregistered providers before
        # iteration so the live chain does not advertise phantom first entries.
        attempts: list[ProviderAttemptDiagnostic] = []
        if not is_pinned_writer:
            effective_chain, excluded = self.effective_chain(chain)
            if excluded:
                logger.info(
                    "Excluding unregistered providers from effective role=%s "
                    "chain: %s",
                    role,
                    [attempt.provider for attempt in excluded],
                )
                attempts.extend(excluded)
            chain = effective_chain

            # 2026-06-25 loop-wedge: drop registered providers whose
            # subscription login is definitively dead so fallback routes
            # straight to a healthy provider. No-op without an injected probe.
            # Universe-aware: a provider the universe vault authenticates is kept.
            auth_alive = self._apply_auth_health_policy(
                chain, universe_dir=universe_dir,
            )
            dead_auth = [p for p in chain if p not in auth_alive]
            if dead_auth:
                logger.warning(
                    "Skipping providers with dead subscription login for "
                    "role=%s: %s",
                    role,
                    dead_auth,
                )
                attempts.extend(
                    ProviderAttemptDiagnostic(
                        provider=p,
                        status="skipped",
                        skip_class="auth_invalid",
                        detail="no subscription login (auth probe: not_logged_in)",
                    )
                    for p in dead_auth
                )
                chain = auth_alive

        # Round-18 #3: retired-lane / credential-integrity errors are TERMINAL — a
        # universe holding a retired-lane credential must FAIL the whole routing op,
        # never fall through to another provider on ambient auth. Imported here (lazy)
        # imported lazily to keep provider routing startup lightweight.
        from tinyassets.engine_binding import RetiredCredentialStateError

        # Coding-sandbox capability filter (FINDING 4): a sandbox-required call
        # must reach ONLY providers that enforce the hardened contract — never a
        # text/local provider that would fake a 'patched'. Empty chain ⇒ fail loud.
        if getattr(cfg, "os_sandbox_required", False):
            capable = self._filter_coding_capable(chain)
            dropped = [p for p in chain if p not in capable]
            if dropped:
                logger.warning(
                    "Excluding non-coding-capable providers from sandbox-required "
                    "role=%s chain: %s", role, dropped,
                )
            if not capable:
                raise AllProvidersExhaustedError(
                    f"Sandbox-required (coding) call for role={role!r} has no "
                    "provider that enforces the coding-sandbox contract "
                    "(claude-code / codex). Refusing to run it on a text/local "
                    "provider that would fake success (fail closed)."
                )
            chain = capable

        # Closed-tool-surface filter (C1b): a call requiring an ENFORCED closed
        # surface must reach ONLY providers that honor `--tools ""` (claude-code)
        # — never codex, which ignores tool policy. Empty chain ⇒ fail loud.
        if getattr(cfg, "closed_tool_surface", False):
            surface_ok = self._filter_closed_tool_surface_capable(chain)
            dropped = [p for p in chain if p not in surface_ok]
            if dropped:
                logger.warning(
                    "Excluding non-closed-surface providers from closed-surface "
                    "role=%s chain: %s", role, dropped,
                )
            if not surface_ok:
                raise AllProvidersExhaustedError(
                    f"Closed-tool-surface call for role={role!r} has no provider "
                    "that enforces `--tools \"\"` (claude-code). Refusing to run it "
                    "on a provider that ignores tool policy, e.g. codex (fail "
                    "closed)."
                )
            chain = surface_ok

        for provider_name in chain:
            provider = self._providers.get(provider_name)
            if provider is None:
                logger.info("Provider %s not in registry, skipping", provider_name)
                attempts.append(ProviderAttemptDiagnostic(
                    provider=provider_name, status="skipped",
                    skip_class="not_in_registry",
                    detail="provider name not registered with daemon",
                ))
                continue
            if not self._quota.available(provider_name):
                logger.info("Skipping %s (quota/cooldown)", provider_name)
                cd = self._quota.cooldown_remaining(provider_name)
                attempts.append(ProviderAttemptDiagnostic(
                    provider=provider_name, status="skipped",
                    skip_class="quota_or_cooldown",
                    detail="quota or cooldown gate",
                    cooldown_remaining_s=cd if cd > 0 else None,
                ))
                continue

            logger.info("Trying provider %s for role=%s", provider_name, role)
            try:
                resp = await provider.complete(
                    prompt, system, cfg, universe_dir=universe_dir,
                )
                self._quota.record_success(provider_name)
            except RetiredCredentialStateError:
                # Round-18 #3: TERMINAL. The universe's vault holds a credential from a
                # RETIRED lane the platform must never consume. Do NOT treat this as an
                # ordinary provider failure and continue to the next provider (which
                # would silently route, e.g., a legacy Claude record through ambient
                # Codex). FAIL the whole routing operation closed (Hard Rule #8) — no
                # later provider is tried. Re-raise so the caller surfaces it loudly.
                logger.error(
                    "Retired-lane credential encountered while routing role=%s via "
                    "%s — TERMINAL routing failure (no fallback).",
                    role, provider_name,
                )
                raise
            except ProviderUnavailableError as exc:
                self._quota.cooldown(provider_name, COOLDOWN_UNAVAILABLE)
                logger.warning(
                    "Provider %s unavailable, cooldown %ds",
                    provider_name, COOLDOWN_UNAVAILABLE,
                )
                attempts.append(ProviderAttemptDiagnostic(
                    provider=provider_name, status="failed",
                    skip_class=classify_unavailable(exc),
                    detail=str(exc)[:200],
                ))
                continue
            except ProviderTimeoutError as exc:
                self._quota.cooldown(provider_name, COOLDOWN_TIMEOUT)
                logger.warning(
                    "Provider %s timed out, cooldown %ds",
                    provider_name, COOLDOWN_TIMEOUT,
                )
                attempts.append(ProviderAttemptDiagnostic(
                    provider=provider_name, status="failed",
                    skip_class="timed_out",
                    detail=str(exc)[:200],
                ))
                continue
            except ProviderError as exc:
                self._quota.cooldown(provider_name, COOLDOWN_OTHER)
                logger.warning(
                    "Provider %s error, cooldown %ds: %s",
                    provider_name, COOLDOWN_OTHER, exc,
                )
                attempts.append(ProviderAttemptDiagnostic(
                    provider=provider_name, status="failed",
                    skip_class="provider_error",
                    detail=str(exc)[:200],
                ))
                continue
            except Exception as exc:
                self._quota.cooldown(provider_name, COOLDOWN_OTHER)
                logger.exception("Unexpected error from %s", provider_name)
                attempts.append(ProviderAttemptDiagnostic(
                    provider=provider_name, status="failed",
                    skip_class="unknown",
                    detail=f"{type(exc).__name__}: {str(exc)[:160]}",
                ))
                continue

            # Successful call — apply BUG-029 Part B: track consecutive empty
            # responses from local providers when chain-drained.
            is_local = provider_name in _LOCAL_PROVIDERS
            response_empty = not (resp.text or "").strip()
            if is_local and response_empty:
                count = self._consecutive_empty.get(provider_name, 0) + 1
                self._consecutive_empty[provider_name] = count
                drained = self._quota.all_api_providers_in_cooldown(
                    chain, local_providers=_LOCAL_PROVIDERS
                )
                if drained and count >= self._chain_drain_empty_threshold:
                    logger.warning(
                        "CHAIN_DRAINED + %s empty x%d: raising "
                        "AllProvidersExhaustedError to force backoff (BUG-029)",
                        provider_name, count,
                    )
                    raise AllProvidersExhaustedError(
                        f"Chain drained (all API providers in cooldown) and "
                        f"{provider_name!r} returned empty prose {count} consecutive "
                        f"time(s). Daemon should back off rather than commit empty output."
                    )
            else:
                self._consecutive_empty.pop(provider_name, None)
            return resp

        # All providers exhausted.
        if is_pinned_writer:
            # Hard pin must fail loudly rather than silently falling through
            # to a different provider (hard rule #8).
            raise AllProvidersExhaustedError(
                f"Pinned writer provider {pin_writer!r} exhausted. "
                "TINYASSETS_PIN_WRITER disables fallback — clear the env var "
                "to re-enable the default chain."
            )

        # Chain-drain detection (BUG-029 Part A): when all API providers are
        # in cooldown and the chain fell through to local-only, emit a
        # structured warning so operators can diagnose the condition without
        # reading router logs line-by-line.
        if self._quota.all_api_providers_in_cooldown(chain):
            remaining = self._quota.cooldown_remaining_dict(chain)
            logger.warning(
                "CHAIN_DRAINED: all API providers in cooldown; routing "
                "exclusively to local (ollama-local) for up to %ds. "
                "Per-provider cooldown: %s",
                max(remaining.values(), default=0),
                {k: v for k, v in remaining.items() if v > 0},
            )

        if role == "judge":
            logger.warning("All judge providers exhausted -- returning degraded response")
            return DEGRADED_JUDGE_RESPONSE

        # FEAT-006: attach structured diagnostics so get_run.error_detail
        # can show *why* each provider was skipped without parsing logs.
        chain_state = build_chain_state(
            role=role,
            chain=chain,
            attempts=attempts,
            api_key_providers_enabled=api_key_providers_enabled(),
            pinned_writer=pin_writer if is_pinned_writer else None,
            allowlist=allowlist,
        )
        raise AllProvidersExhaustedError(
            f"All providers exhausted for role={role}. "
            "Daemon should retry with backoff.",
            attempts=attempts,
            chain_state=chain_state,
        )

    # ------------------------------------------------------------------
    # Policy-aware routing (per-node llm_policy override)
    # ------------------------------------------------------------------

    @staticmethod
    def _call_meta(resp, attempts: int) -> dict:
        """Telemetry for one routed call: model identity, latency, attempts.

        Persisted onto run receipts (runs.provider_used/model columns and the
        per-run ``provider_calls`` event) so receipts can answer "which model
        produced this, how long did it take, after how many tries" — spec
        §11.3 model-stamp requirement.
        """
        return {
            "model": getattr(resp, "model", "") or "",
            "family": getattr(resp, "family", "") or "",
            "latency_ms": getattr(resp, "latency_ms", None),
            "degraded": bool(getattr(resp, "degraded", False)),
            "attempts": attempts,
        }

    @_pin_byo_snapshot
    async def call_with_policy(
        self,
        role: str,
        prompt: str,
        system: str,
        policy: dict | None,
        config: ModelConfig | None = None,
        difficulty: str = "",
        *,
        universe_context: UniverseContext | None = None,
    ) -> tuple[str, str, dict]:
        """Route a call honouring an explicit llm_policy dict.

        Returns ``(response_text, provider_name_used, call_meta)`` where
        ``call_meta`` is :meth:`_call_meta` telemetry for the winning call.

        Policy resolution order:
        1. ``preferred`` provider — try first.
        2. ``fallback_chain`` entries — tried in order after preferred fails;
           each entry may declare a ``trigger`` that maps to an exception class:
           "unavailable", "rate_limited", "cost_exceeded", "empty_response".
           An entry with no trigger fires after any failure.
        3. ``difficulty_override`` — checked before attempting preferred; if
           ``difficulty`` matches ``if_difficulty``, the override provider is
           prepended to the attempt order.
        4. If policy is None or all policy-derived providers exhaust, falls
           through to the standard role-based ``call()`` method.

        When ``call()`` is reached it returns a ``ProviderResponse``; this
        method extracts ``.text`` and returns (text, provider_name, meta). For
        the policy path we track the name explicitly.
        """
        resolved_config = _resolve_universe_config(universe_context)
        universe_dir = universe_context.universe_dir if universe_context else None
        # Round-21 #1: retired-universe fail-closed preflight on the policy path too.
        _preflight_retired_universe(universe_dir)
        cfg = config or _default_config(resolved_config)
        # Coding-node fail-closed preflight (patch-loop S3) — see call().
        enforce_os_sandbox(cfg)

        if not policy:
            resp = await self.call(
                role, prompt, system, cfg, universe_context=universe_context,
            )
            return resp.text, resp.provider, self._call_meta(resp, attempts=1)

        # Build ordered attempt list from policy
        attempt_order: list[str] = []

        # difficulty_override check
        if difficulty:
            for override in policy.get("difficulty_override", []):
                if isinstance(override, dict) and override.get("if_difficulty") == difficulty:
                    use = override.get("use", {})
                    p = use.get("provider", "") if isinstance(use, dict) else ""
                    if p:
                        attempt_order.append(p)
                        break

        # preferred provider next
        preferred = policy.get("preferred", {})
        if isinstance(preferred, dict):
            prov = preferred.get("provider", "")
            if prov and prov not in attempt_order:
                attempt_order.append(prov)

        # fallback_chain entries — all get added; trigger filtering happens below
        fallback_chain = policy.get("fallback_chain", [])
        if isinstance(fallback_chain, list):
            for entry in fallback_chain:
                if not isinstance(entry, dict):
                    continue
                p = entry.get("provider", "")
                if p and p not in attempt_order:
                    attempt_order.append(p)

        # Q6.3 — filter policy attempt order by per-universe allowlist.
        # If the universe disallows a provider the policy named, skip it
        # rather than attempt and leak. If everything filters out the
        # method falls through to the role-based ``call()`` below, which
        # applies the same allowlist and hard-fails.
        allowlist = self._current_allowlist(resolved_config)
        if allowlist is not None:
            filtered_order = self._apply_allowlist(attempt_order, allowlist)
            if attempt_order and not filtered_order:
                logger.warning(
                    "Q6.3 allowlist removes all policy providers (%s) for "
                    "role=%s; falling through to role chain.",
                    attempt_order, role,
                )
            attempt_order = filtered_order

        # C1: apply the SAME centralized writer-binding enforcement to the policy
        # attempt-order — a BYO-bound universe's policy must not name a
        # platform-auth provider (e.g. a policy naming codex in a BYO-claude
        # universe is refused, never routed to platform codex). Fails closed.
        attempt_order = _enforce_writer_binding(
            attempt_order, role=role, is_pinned_writer=False, pin_writer="",
            universe_dir=universe_dir,
        )

        auth_filtered_order = self._apply_api_key_provider_policy(attempt_order)
        if attempt_order and not auth_filtered_order:
            logger.warning(
                "Provider auth policy removes all API-key policy providers "
                "(%s) for role=%s; falling through to role chain.",
                attempt_order, role,
            )
        attempt_order = auth_filtered_order

        # 2026-06-25 loop-wedge: drop dead-login subscription providers; if
        # that empties the policy order the method falls through to the role
        # chain below, which re-applies the gate and hard-fails as needed.
        auth_alive_order = self._apply_auth_health_policy(
            attempt_order, universe_dir=universe_dir,
        )
        if attempt_order and not auth_alive_order:
            logger.warning(
                "All policy providers have dead subscription login (%s) for "
                "role=%s; falling through to role chain.",
                attempt_order, role,
            )
        attempt_order = auth_alive_order

        # Round-18 #3 / round-20 #3: retired-lane errors are TERMINAL in EVERY router
        # entry point, not just call(). Imported here (lazy) to match the router's
        # engine-binding import style.
        from tinyassets.engine_binding import RetiredCredentialStateError

        # Coding-sandbox capability filter (FINDING 4) on the policy path: never
        # try a non-coding-capable policy provider (e.g. ollama) for a
        # sandbox-required call — it would fake a 'patched'. If that empties the
        # order, fall through to the role chain, which re-applies the same filter
        # and fails loud when no capable provider remains.
        if getattr(cfg, "os_sandbox_required", False):
            capable_order = self._filter_coding_capable(attempt_order)
            if attempt_order and not capable_order:
                logger.warning(
                    "All policy providers are non-coding-capable for a "
                    "sandbox-required role=%s; falling through to role chain.",
                    role,
                )
            attempt_order = capable_order

        # Closed-tool-surface filter (C1b) on the policy path: never try a
        # non-enforcing policy provider (e.g. codex) for a closed-surface call.
        if getattr(cfg, "closed_tool_surface", False):
            surface_order = self._filter_closed_tool_surface_capable(attempt_order)
            if attempt_order and not surface_order:
                logger.warning(
                    "All policy providers ignore the closed tool surface for "
                    "role=%s; falling through to role chain.", role,
                )
            attempt_order = surface_order

        # Try policy-derived providers
        tried = 0
        for provider_name in attempt_order:
            provider = self._providers.get(provider_name)
            if provider is None:
                logger.info(
                    "Policy provider %s not in registry, skipping", provider_name,
                )
                continue
            if not self._quota.available(provider_name):
                logger.info("Skipping policy provider %s (cooldown)", provider_name)
                continue

            logger.info(
                "Trying policy provider %s for role=%s", provider_name, role,
            )
            tried += 1
            try:
                resp = await provider.complete(
                    prompt, system, cfg, universe_dir=universe_dir,
                )
                self._quota.record_success(provider_name)
                return resp.text, provider_name, self._call_meta(resp, attempts=tried)
            except RetiredCredentialStateError:
                # Round-20 #3: TERMINAL — the universe holds a retired-lane credential.
                # Do NOT fall through to the next policy provider (which would run on
                # ambient host creds — a cross-identity leak). Fail the whole routing
                # operation closed. Rethrow BEFORE the generic handler below.
                logger.error(
                    "Retired-lane credential while routing policy role=%s via %s — "
                    "TERMINAL (no fallback).", role, provider_name,
                )
                raise
            except ProviderUnavailableError:
                self._quota.cooldown(provider_name, COOLDOWN_UNAVAILABLE)
                logger.warning(
                    "Policy provider %s unavailable, cooldown %ds",
                    provider_name, COOLDOWN_UNAVAILABLE,
                )
            except ProviderTimeoutError:
                self._quota.cooldown(provider_name, COOLDOWN_TIMEOUT)
                logger.warning(
                    "Policy provider %s timed out, cooldown %ds",
                    provider_name, COOLDOWN_TIMEOUT,
                )
            except ProviderError as exc:
                self._quota.cooldown(provider_name, COOLDOWN_OTHER)
                logger.warning(
                    "Policy provider %s error, cooldown %ds: %s",
                    provider_name, COOLDOWN_OTHER, exc,
                )
            except Exception:
                self._quota.cooldown(provider_name, COOLDOWN_OTHER)
                logger.exception("Unexpected error from policy provider %s", provider_name)

        # All policy providers exhausted — fall through to role-based chain
        logger.info(
            "Policy providers exhausted for role=%s; falling through to role chain",
            role,
        )
        resp = await self.call(
            role, prompt, system, cfg, universe_context=universe_context,
        )
        return resp.text, resp.provider, self._call_meta(resp, attempts=tried + 1)

    def call_with_policy_sync(
        self,
        role: str,
        prompt: str,
        system: str,
        policy: dict | None,
        config: ModelConfig | None = None,
        difficulty: str = "",
        *,
        universe_context: UniverseContext | None = None,
    ) -> tuple[str, str, dict]:
        """Synchronous wrapper for :meth:`call_with_policy`."""
        cfg = config or _default_config(_resolve_universe_config(universe_context))
        sync_timeout = cfg.timeout + 30

        # Capture universe_context in the closure so it survives the hop into
        # the ThreadPoolExecutor worker thread (no ContextVar — a ContextVar
        # set here would NOT propagate to the pool's worker thread).
        def _run() -> tuple[str, str, dict]:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    self.call_with_policy(
                        role, prompt, system, policy, cfg, difficulty,
                        universe_context=universe_context,
                    )
                )
            finally:
                loop.close()

        future = self._thread_pool.submit(_run)
        try:
            return future.result(timeout=sync_timeout)
        except concurrent.futures.TimeoutError:
            logger.warning(
                "call_with_policy_sync timed out after %ds for role=%s",
                sync_timeout, role,
            )
            raise ProviderTimeoutError(
                f"call_with_policy_sync exceeded {sync_timeout}s for role={role}"
            )

    # ------------------------------------------------------------------
    # Synchronous wrapper (for use from sync graph nodes)
    # ------------------------------------------------------------------

    _thread_pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=_SYNC_CALL_MAX_WORKERS,
        thread_name_prefix="tinyassets-provider-sync",
    )

    def call_sync(
        self,
        role: str,
        prompt: str,
        system: str,
        config: ModelConfig | None = None,
        *,
        universe_context: UniverseContext | None = None,
    ) -> ProviderResponse:
        """Synchronous version of :meth:`call` for use from sync code.

        Runs the async ``call`` in a dedicated thread with its own event
        loop, avoiding the "loop already running" problem that blocks
        ``loop.run_until_complete`` inside LangGraph nodes.

        ``universe_context`` is captured in the submitted closure so it survives
        the hop into the ThreadPoolExecutor worker thread — a ContextVar set in
        the caller's thread would NOT propagate into the pool worker, so the
        per-universe routing state is threaded EXPLICITLY, not via ContextVar.
        """
        cfg = config or _default_config(_resolve_universe_config(universe_context))
        # Allow the subprocess timeout to fire first (+30s margin for
        # async overhead, fallback attempts, etc.)
        sync_timeout = cfg.timeout + 30

        def _run() -> ProviderResponse:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    self.call(
                        role, prompt, system, cfg,
                        universe_context=universe_context,
                    )
                )
            finally:
                loop.close()

        future = self._thread_pool.submit(_run)
        try:
            return future.result(timeout=sync_timeout)
        except concurrent.futures.TimeoutError:
            logger.warning(
                "call_sync timed out after %ds for role=%s",
                sync_timeout, role,
            )
            raise ProviderTimeoutError(
                f"call_sync exceeded {sync_timeout}s hard timeout for role={role}"
            )

    # ------------------------------------------------------------------
    # Judge ensemble (model family diversity)
    # ------------------------------------------------------------------

    @_pin_byo_snapshot
    async def call_judge_ensemble(
        self,
        prompt: str,
        system: str,
        config: ModelConfig | None = None,
        *,
        universe_context: UniverseContext | None = None,
    ) -> list[ProviderResponse]:
        """Fan out to ALL available judge providers in parallel.

        Calls every registered, non-cooldown provider once.  Never
        calls the same provider twice.  Returns 1-N responses
        depending on how many providers are healthy.
        """
        resolved_config = _resolve_universe_config(universe_context)
        universe_dir = universe_context.universe_dir if universe_context else None
        # Round-21 #1: retired-universe fail-closed preflight BEFORE the judge fan-out —
        # a retired universe must never run ANY judge on ambient host creds.
        _preflight_retired_universe(universe_dir)
        cfg = config or _default_config(resolved_config)

        # Q6.3 — filter judge ensemble by per-universe allowlist (privacy
        # primitive). Empty filter => empty list, matching the existing
        # "no judges available" contract at L484-486.
        allowlist = self._current_allowlist(resolved_config)
        ensemble = self._apply_allowlist(list(_JUDGE_PROVIDERS), allowlist)
        if allowlist is not None and not ensemble:
            logger.warning(
                "Q6.3 allowlist empties judge ensemble: allowed_providers=%s "
                "intersected with %s yields no judges.",
                allowlist, _JUDGE_PROVIDERS,
            )
        auth_ensemble = self._apply_api_key_provider_policy(ensemble)
        if ensemble and not auth_ensemble:
            logger.warning(
                "Provider auth policy removes all API-key judge providers "
                "(%s); no judges available without "
                "TINYASSETS_ALLOW_API_KEY_PROVIDERS=1.",
                ensemble,
            )
        ensemble = auth_ensemble

        # 2026-06-25 loop-wedge: drop judge providers with dead subscription
        # login (codex is the only subscription judge; the rest probe unknown
        # and are kept). Empty ensemble returns [] per the contract below.
        auth_alive_ensemble = self._apply_auth_health_policy(
            ensemble, universe_dir=universe_dir,
        )
        if ensemble and not auth_alive_ensemble:
            logger.warning(
                "All judge providers have dead subscription login (%s); no "
                "judges available until credentials are re-seeded.",
                ensemble,
            )
        ensemble = auth_alive_ensemble

        # Find all available judge providers
        available: list[tuple[str, BaseProvider]] = []
        for name in ensemble:
            provider = self._providers.get(name)
            if provider is None:
                continue
            if not self._quota.available(name):
                logger.debug("Judge provider %s in cooldown, skipping", name)
                continue
            available.append((name, provider))

        if not available:
            logger.warning("No judge providers available")
            return []

        # Round-18 #3 / round-20 #3: retired-lane errors are TERMINAL in EVERY router
        # entry point. Lazy import matches the router's credential_vault import style.
        from tinyassets.engine_binding import RetiredCredentialStateError

        # Fan out in parallel
        async def _call_one(
            name: str, provider: BaseProvider,
        ) -> ProviderResponse | None:
            try:
                resp = await provider.complete(
                    prompt, system, cfg, universe_dir=universe_dir,
                )
                self._quota.record_success(name)
                return resp
            except RetiredCredentialStateError:
                # Round-20 #3: TERMINAL — a retired universe must FAIL the whole
                # ensemble, never let other judges return results computed on ambient
                # host creds (a cross-identity leak). Rethrow BEFORE the generic
                # handler; asyncio.gather propagates it out of call_judge_ensemble.
                logger.error(
                    "Retired-lane credential while routing judge ensemble via %s — "
                    "TERMINAL (no fallback).", name,
                )
                raise
            except ProviderUnavailableError:
                self._quota.cooldown(name, COOLDOWN_UNAVAILABLE)
            except ProviderTimeoutError:
                self._quota.cooldown(name, COOLDOWN_TIMEOUT)
            except Exception:
                self._quota.cooldown(name, COOLDOWN_OTHER)
            return None

        tasks = [_call_one(name, prov) for name, prov in available]
        raw_results = await asyncio.gather(*tasks)

        results = [r for r in raw_results if r is not None]
        logger.info(
            "Judge ensemble: %d/%d providers responded",
            len(results), len(available),
        )
        return results
