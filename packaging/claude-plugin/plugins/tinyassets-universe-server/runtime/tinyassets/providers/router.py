"""Provider router -- fallback chains across six providers.

Hard invariant: every call has a fallback chain that terminates at
``ollama-local``.  The system NEVER stops due to provider
unavailability unless local models are also down.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import math
import os
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from tinyassets.exceptions import (
    AllProvidersExhaustedError,
    InteractiveDeadlineError,
    ProviderAuthorityHeldError,
    ProviderError,
    ProviderIdleTimeoutError,
    ProviderOverloadedError,
    ProviderProtocolError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from tinyassets.provider_admission import ProviderBusy as _ProviderBusy
from tinyassets.provider_admission import provider_slot_async as _provider_slot
from tinyassets.provider_work_authority import (
    ProviderInvocationCarrier,
    ProviderInvocationReservationState,
    ProviderInvocationSettlementOwner,
)
from tinyassets.providers.base import (
    DEGRADED_JUDGE_RESPONSE,
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
    api_key_providers_enabled,
)
from tinyassets.providers.diagnostics import (
    ProviderAttemptDiagnostic,
    build_chain_state,
    classify_unavailable,
    dominant_failure_class,
    dominant_retry_after_s,
)
from tinyassets.providers.quota import (
    COOLDOWN_OTHER,
    COOLDOWN_TIMEOUT,
    COOLDOWN_UNAVAILABLE,
    QuotaTracker,
)

if TYPE_CHECKING:
    from tinyassets.config import UniverseConfig

logger = logging.getLogger(__name__)

_CONNECT_PROVIDER_MESSAGE = (
    "Connect your provider before running this universe. TinyAssets will not "
    "borrow platform credentials or start a metered trial."
)

# Per-call served output reservation when the caller sets no explicit max_tokens
# (the production `_sandboxed_config` converse path leaves it None). This MUST be
# decoupled from the binding's aggregate in-flight ceiling
# (ServedProviderAuthority.max_tokens): substituting the whole ceiling made each
# turn reserve the ENTIRE budget, so the second concurrent turn always bricked
# regardless of how high the ceiling was raised (Codex 2026-08-22). A bounded
# per-call reservation lets many concurrent turns share the ceiling. It is a
# reservation estimate, not a hard generation cap (the CLI subprocess is not
# passed a token limit — see finalize_served_provider_budget), so it only needs
# to be generous for one reply while small relative to the aggregate ceiling.
_SERVED_PER_CALL_MAX_TOKENS = 65_536


def _provider_invocation_carrier(
    universe_context: UniverseContext | None,
    *,
    role: str,
    operation: str | None,
) -> ProviderInvocationCarrier | None:
    carrier = universe_context.provider_invocation if universe_context else None
    if carrier is None:
        return None
    if operation is None:
        raise PermissionError("armed provider invocation requires an operation")
    if type(carrier) is not ProviderInvocationCarrier:
        raise PermissionError("provider invocation carrier is not server-owned")
    carrier.validate_for_call(role=role, operation=operation)
    return carrier

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


def _effective_universe_provider_ceiling(
    universe_context: UniverseContext | None,
    resolved_config: "UniverseConfig | None",
    *,
    carrier_armed: bool,
) -> list[str] | None:
    """Return the requester's provider ceiling, or legacy/platform ``None``.

    A server-minted invocation carrier is already pinned to one provider and
    remains subject to any explicit assignment allowlist. An unarmed explicit
    universe context is requester work: legacy ``allowed_providers=None`` may
    use only providers the universe itself selected, never the process-global
    fallback chain. Missing/empty selection holds before provider access.
    """
    if carrier_armed or universe_context is None:
        return (
            resolved_config.allowed_providers
            if resolved_config is not None
            else None
        )
    # An unarmed explicit context is requester authority. Its config must be
    # carried on the request; ``resolved_config`` may be the ambient runtime
    # fallback and therefore cannot establish requester authority here.
    requester_config = universe_context.config
    if requester_config is None:
        raise ProviderAuthorityHeldError(_CONNECT_PROVIDER_MESSAGE)
    if requester_config.allowed_providers is not None:
        ceiling = [
            str(provider).strip()
            for provider in requester_config.allowed_providers
            if str(provider).strip()
        ]
    else:
        ceiling = list(dict.fromkeys(
            provider
            for provider in (
                str(requester_config.preferred_writer or "").strip(),
                str(requester_config.preferred_judge or "").strip(),
            )
            if provider
        ))
    if not ceiling:
        raise ProviderAuthorityHeldError(_CONNECT_PROVIDER_MESSAGE)
    return ceiling


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


def _rate_limit_cooldown_s(exc: BaseException) -> int:
    """Cooldown seconds for a genuine rate-limit / overload outcome.

    Honors the provider's own ``retry_after`` (+1s margin) when present; else
    falls back to the fixed unavailable cooldown.
    """
    retry_after = getattr(exc, "retry_after", None)
    if (
        isinstance(retry_after, (int, float))
        and math.isfinite(retry_after)
        and retry_after > 0
    ):
        return int(retry_after) + 1
    return COOLDOWN_UNAVAILABLE


def _sync_call_timeout_s(cfg: ModelConfig) -> float:
    """Timeout for a sync-wrapper call: at least the stream absolute cap.

    The streaming served path is judged by its idle watchdog + absolute cap
    (``stream_timeout_profile().absolute_cap_s``, default 600s), NOT the legacy
    ``timeout`` scalar. A sync wrapper firing at ``timeout + 30`` (330s by
    default) would return failure while the subprocess kept streaming up to the
    600s cap (blocker L). Take the larger of the legacy timeout and the absolute
    cap, plus a margin for async overhead + the in-band reap.
    """
    try:
        absolute_cap = cfg.stream_timeout_profile().absolute_cap_s
    except Exception:  # noqa: BLE001 - a malformed cfg falls back to the legacy path
        absolute_cap = 0.0
    legacy = float(getattr(cfg, "timeout", 0) or 0)
    return max(legacy, absolute_cap) + 30.0


def _side_effect_from(exc: BaseException) -> str | None:
    """Read the streamed-attempt ``side_effect_state`` off a raised exception.

    The streaming reader attaches an ``attempt_telemetry`` snapshot (blocker K);
    surfacing ``side_effect_state`` into the ProviderAttemptDiagnostic lets the
    sole-writer retry policy know whether a tool may have run before the attempt
    failed. ``None`` for non-streaming raises (dropped from the diagnostic dict).
    """
    tele = getattr(exc, "attempt_telemetry", None)
    if isinstance(tele, dict):
        state = tele.get("side_effect_state")
        if isinstance(state, str):
            return state
    return None


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
#
# It also acts as a second ceiling on concurrent provider subprocesses, which is a
# property worth knowing about rather than relying on: admission
# (`TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS`, default 6) is the bound sized against
# memory and observable through `get_status.provider_admission`. Raising THIS number to
# unlock concurrency would raise memory pressure with nothing reporting it — I proposed
# exactly that and the arithmetic behind it was wrong, so it stays where it is until a
# real turn's high-water is measured.
_SYNC_CALL_MAX_WORKERS: int = 16

# NOTE: `_provider_slot` (imported above) bounds concurrent provider SUBPROCESSES.
# _SYNC_CALL_MAX_WORKERS bounds threads, which are cheap; a subprocess is ~77 MB.


def _is_nested(universe_context) -> bool:
    """Is this call spawned BY a turn that already holds a slot?

    `run_graph` child calls carry a typed `provider_invocation` carrier, so the answer
    is available exactly where it is needed. Nested work draws on the reserve, because
    otherwise a served turn holding a slot starves the children it created and both
    fail (Codex round 3).
    """
    return bool(getattr(universe_context, "provider_invocation", None))


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

    def _apply_open_preference(self, chain: list[str], preferred: str) -> list[str]:
        """Preference that also admits an OPEN, registered provider not in the
        static role chain (compute-agnostic).

        The static ``FALLBACK_CHAINS`` only name the built-in providers, so a
        universe that selected an open provider (``api_key_http:<def-id>``, set as
        ``preferred_writer`` by the ``open_provider`` engine mode) is not in the
        chain — plain ``_apply_preference`` would be a no-op. If the preferred
        provider is REGISTERED (the per-universe registration bridge ran) but not in
        the chain, prepend it so it is tried first, keeping the built-in chain as
        fallback. If it is not registered, behave exactly as before (no phantom
        entry). Only the non-served path reaches here; the interactive served turn
        uses ``served_authority.provider`` directly and never consults this."""
        reordered = self._apply_preference(chain, preferred)
        if preferred and preferred not in reordered and preferred in self._providers:
            return [preferred, *reordered]
        return reordered

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

    def _apply_auth_health_policy(self, chain: list[str]) -> list[str]:
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
        return alive

    async def call(
        self,
        role: str,
        prompt: str,
        system: str,
        config: ModelConfig | None = None,
        *,
        operation: str | None = None,
        universe_context: UniverseContext | None = None,
    ) -> ProviderResponse:
        """Route a call, fencing founder-facing served turns before launch."""

        # A context that ALREADY carries an authorized ServedProviderAuthority (the
        # daemon-owned background consumer fences its own authority per call in
        # background_served_provider._authorize_launch and injects it here) must
        # NOT be re-authorized as a founder-facing served turn: that path demands a
        # live provider_request the background has none of, so it raised
        # ProviderAuthorityHeldError and the real background path could never
        # launch (Codex REJECT #1, PR #2528). Only an UN-authorized context is
        # fenced here.
        # REVERTED (Codex REJECT #4 on #2531): an earlier head honoured a pre-set
        # ``served_provider`` on the context so the background consumer could inject
        # its authority. ServedProviderAuthority is a plain dataclass, and no
        # in-process provenance scheme (registry, sentinel fence) survived review:
        # 'if arbitrary in-process Python is the adversary, no underscore, sentinel,
        # or same-process secret suffices'. The correct route for background is the
        # server-minted, pid-bound, ONE-USE ProviderInvocationCarrier (the
        # ``provider_invocation`` branch below) - the next lane. Until then a context
        # without a carrier is re-fenced as a served turn: fail closed.
        if universe_context is not None and universe_context.provider_invocation is None:
            from tinyassets.provider_assignment import authorize_served_provider_call

            if (
                universe_context.universe_dir is None
                or universe_context.provider_request is None
                or not operation
            ):
                raise ProviderAuthorityHeldError(_CONNECT_PROVIDER_MESSAGE)
            universe_dir = universe_context.universe_dir
            with authorize_served_provider_call(
                universe_dir.parent,
                universe_dir=universe_dir,
                request_carrier=universe_context.provider_request,
                role=role,
                operation=operation,
            ) as authority:
                authorized_context = replace(
                    universe_context,
                    served_provider=authority,
                )
                return await self._call_routed(
                    role,
                    prompt,
                    system,
                    config,
                    operation=operation,
                    universe_context=authorized_context,
                )
        return await self._call_routed(
            role,
            prompt,
            system,
            config,
            operation=operation,
            universe_context=universe_context,
        )

    async def _call_routed(
        self,
        role: str,
        prompt: str,
        system: str,
        config: ModelConfig | None = None,
        *,
        operation: str | None = None,
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
        invocation_carrier = _provider_invocation_carrier(
            universe_context,
            role=role,
            operation=operation,
        )
        carrier_settled = False
        router_settles_carrier = (
            invocation_carrier is not None
            and invocation_carrier.settlement_owner
            is ProviderInvocationSettlementOwner.ROUTER
        )

        def settle_carrier(
            state: ProviderInvocationReservationState,
            *,
            input_tokens: int | None = None,
            output_tokens: int | None = None,
            cost_microunits: int | None = None,
        ) -> None:
            nonlocal carrier_settled
            if not router_settles_carrier or carrier_settled:
                return
            try:
                invocation_carrier.settle(
                    state,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_microunits=cost_microunits,
                )
            except Exception as exc:
                # Name the CAUSE. The bare message sent a founder in circles for
                # two days on 2026-08-27: every prompt-template run failed with
                # "provider invocation usage could not be settled" and neither
                # the universe nor its founder could tell a budget exhaustion
                # from a carrier-lifecycle error from a storage failure. The
                # `settle()` path alone has four distinct PermissionError exits.
                #
                # `__cause__` was always attached; nothing surfaced it, because
                # the message the user sees is built from this string. Keeping
                # the wrapper type (callers branch on it) and appending the
                # cause costs nothing and makes the failure actionable.
                raise ProviderAuthorityHeldError(
                    "provider invocation usage could not be settled: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            carrier_settled = True
        served_authority = universe_context.served_provider if universe_context else None
        resolved_config = _resolve_universe_config(universe_context)
        universe_dir = universe_context.universe_dir if universe_context else None
        cfg = config or _default_config(resolved_config)
        if served_authority is not None:
            if (
                operation != served_authority.operation
                or role not in served_authority.allowed_roles
            ):
                raise PermissionError("provider role or operation is outside authority")
            if served_authority.max_tokens < 1:
                raise PermissionError("served provider authority has no token budget")
            if served_authority.max_cost_microunits < 1:
                raise PermissionError("served provider authority has no cost budget")
            if cfg.max_tokens is None:
                # Reserve a BOUNDED per-call output, not the whole aggregate
                # ceiling — otherwise the first turn reserves the entire budget
                # and the second concurrent turn bricks (Codex 2026-08-22). Cap
                # to the ceiling so a small binding still validates.
                cfg = replace(
                    cfg,
                    max_tokens=min(
                        served_authority.max_tokens, _SERVED_PER_CALL_MAX_TOKENS
                    ),
                )
            elif (
                isinstance(cfg.max_tokens, bool)
                or not isinstance(cfg.max_tokens, int)
                or cfg.max_tokens < 0
                or cfg.max_tokens > served_authority.max_tokens
            ):
                raise PermissionError("provider call exceeds served token ceiling")
            cfg = replace(
                cfg,
                credential_snapshot_dir=served_authority.credential_snapshot_dir,
            )
            chain = [served_authority.provider]
        elif invocation_carrier is not None:
            if invocation_carrier.max_tokens < 1:
                raise PermissionError("armed provider invocation has no positive token budget")
            if invocation_carrier.max_cost_microunits < 1:
                raise PermissionError("armed provider invocation has no positive cost budget")
            if cfg.max_tokens is None:
                cfg = replace(cfg, max_tokens=invocation_carrier.max_tokens)
            elif (
                isinstance(cfg.max_tokens, bool)
                or not isinstance(cfg.max_tokens, int)
                or cfg.max_tokens < 0
                or cfg.max_tokens > invocation_carrier.max_tokens
            ):
                raise PermissionError("provider call exceeds armed token ceiling")
            chain = [invocation_carrier.provider]
        else:
            chain = FALLBACK_CHAINS.get(role, FALLBACK_CHAINS["writer"])

        # Hard pin: TINYASSETS_PIN_WRITER narrows the writer chain to a
        # single provider for this call. No fallback — if the pinned
        # provider fails, the call fails loudly (hard rule #8).
        pin_writer = os.environ.get("TINYASSETS_PIN_WRITER", "").strip()
        is_pinned_writer = role == "writer" and bool(pin_writer)
        if served_authority is not None:
            if is_pinned_writer and pin_writer != served_authority.provider:
                raise PermissionError("writer pin conflicts with served provider")
        elif invocation_carrier is not None:
            if is_pinned_writer and pin_writer != invocation_carrier.provider:
                raise PermissionError("writer pin conflicts with armed provider")
        elif is_pinned_writer:
            chain = [pin_writer]
        else:
            # Apply per-universe provider preference from the resolved config.
            try:
                ucfg = resolved_config
                if ucfg is not None:
                    if role == "writer" and ucfg.preferred_writer:
                        chain = self._apply_open_preference(chain, ucfg.preferred_writer)
                    elif role == "judge" and ucfg.preferred_judge:
                        chain = self._apply_open_preference(chain, ucfg.preferred_judge)
            except Exception:
                pass

        # Q6.3 — apply per-universe allowlist (privacy primitive). Pin already
        # narrowed chain to [pin_writer] above; the filter then enforces
        # pin × allowlist composition. None = no-op (backwards-compat).
        if served_authority is not None:
            # The served authority is the explicitly-bound provider, but it must ALSO
            # sit within the universe's privacy allowlist — a minted served authority
            # must NOT bypass allowed_providers (Codex serve-open-compute review #2).
            # No ceiling set = allow (backwards-compatible); a ceiling that excludes the
            # served provider empties the chain -> fail closed below.
            _served_ceiling = _effective_universe_provider_ceiling(
                universe_context,
                resolved_config,
                carrier_armed=False,
            )
            allowlist = (
                [served_authority.provider]
                if _served_ceiling is None
                or served_authority.provider in _served_ceiling
                else []
            )
        else:
            allowlist = _effective_universe_provider_ceiling(
                universe_context,
                resolved_config,
                carrier_armed=invocation_carrier is not None,
            )
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
        if is_pinned_writer and not self._apply_auth_health_policy(chain):
            raise AllProvidersExhaustedError(
                f"Pinned writer provider {pin_writer!r} has no subscription "
                "login (auth probe: not_logged_in). Re-seed its credentials, "
                "or clear TINYASSETS_PIN_WRITER to use the fallback chain."
            )

        # FEAT-006 / BUG-025: collect per-provider skip/failure diagnostics so
        # the final AllProvidersExhaustedError can carry structured detail.
        # For normal fallback routing, remove unregistered providers before
        # iteration so the live chain does not advertise phantom first entries.
        attempts: list[ProviderAttemptDiagnostic] = []
        if (
            invocation_carrier is None
            and served_authority is None
            and not is_pinned_writer
        ):
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
            auth_alive = self._apply_auth_health_policy(chain)
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

        for provider_name in chain:
            provider = self._providers.get(provider_name)
            if (
                served_authority is not None
                and provider_name == served_authority.provider
                and provider_name.startswith("api_key_http:")
            ):
                # Do NOT trust the mutable registry for an OPEN served provider (Codex
                # serve-open-compute re-review #4): a substituted same-name registry
                # object could advertise the content-addressed name while backing a
                # different endpoint/grant/credential. Resolve the executor FRESH from
                # the integrity-checked ProviderDefinition (get_definition verifies the
                # id content-addresses its fields), so the dispatched instance is
                # authenticated by construction, not by a name comparison.
                try:
                    from tinyassets.providers.definition import get_definition
                    from tinyassets.providers.provider_resolver import (
                        provider_for_definition,
                    )

                    _uid = (
                        universe_dir.name
                        if universe_dir is not None
                        else served_authority.universe_id
                    )
                    _def_id = provider_name.split("api_key_http:", 1)[-1]
                    _definition = get_definition(_uid, _def_id)
                    if _definition is None:
                        raise PermissionError(
                            "open served provider definition is absent"
                        )
                    provider = provider_for_definition(_definition)
                except PermissionError:
                    raise
                except Exception as exc:  # noqa: BLE001 - fail closed, secret-free
                    raise PermissionError(
                        "open served provider could not be authenticated"
                    ) from exc
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
                budget_reservation = None
                # EVERY served authority — founder-facing served turns
                # ("served_request") AND daemon-owned background attempts
                # ("background_attempt") — goes THROUGH this reserve-before-launch /
                # finalize-actuals-after machinery. It used to admit only
                # "served_request", so background calls reserved nothing and
                # created no actual-usage row, which made the consumer's rolling
                # cap blind to real spend (Codex REJECT #2/#6, PR #2528). The one
                # genuinely served-ONLY step is consuming a live request
                # capability, which background does not carry — skipped below when
                # absent; reservation + finalization are common to both.
                if served_authority is not None and served_authority.budget_owner not in (
                    "served_request",
                    "background_attempt",
                ):
                    # An authority with an UNKNOWN budget owner must never reach a
                    # provider: it would skip the reservation block below and launch
                    # with no budget at all (Codex REJECT #3 reproduced exactly this
                    # with a forged authority). Fail closed before routing.
                    raise ProviderAuthorityHeldError(_CONNECT_PROVIDER_MESSAGE)
                if served_authority is not None and served_authority.budget_owner in (
                    "served_request",
                    "background_attempt",
                ):
                    from tinyassets.auth.middleware import (
                        consume_provider_request_invocation,
                    )
                    from tinyassets.provider_assignment import (
                        abandon_served_provider_budget,
                        finalize_served_provider_budget,
                        release_served_provider_budget,
                        reserve_served_provider_budget,
                    )

                    try:
                        if served_authority.request_capability is not None:
                            consume_provider_request_invocation(
                                served_authority.request_capability,
                                limit=served_authority.request_max_invocations,
                            )
                    except PermissionError as exc:
                        raise ProviderAuthorityHeldError(
                            _CONNECT_PROVIDER_MESSAGE
                        ) from exc
                    estimated_input_tokens = max(
                        1,
                        len(
                            (f"{system}\n\n{prompt}" if system else prompt).encode(
                                "utf-8"
                            )
                        ),
                    )
                    budget_reservation = reserve_served_provider_budget(
                        universe_dir.parent,
                        universe_dir=universe_dir,
                        authority=served_authority,
                        role=role,
                        requested_output_tokens=cfg.max_tokens,
                        estimated_input_tokens=estimated_input_tokens,
                        call_timeout_s=getattr(cfg, "timeout", None),
                    )
                    cfg = replace(cfg, max_tokens=budget_reservation.output_tokens)
                try:
                    # Bound concurrent provider SUBPROCESSES (~77 MB PSS each,
                    # measured). ASYNC form: a blocking acquire here stalls the event
                    # loop, and `call_judge_ensemble` gathers admission-taking tasks on
                    # one loop, so the bound would refuse work it was itself holding up.
                    #
                    # Acquired BEFORE `before_provider_launch` on purpose. With the
                    # order reversed, a busy refusal charged the launch, abandoned the
                    # budget reservation as INDETERMINATE and cooled a provider that had
                    # never started — the caller then saw AllProvidersExhaustedError
                    # instead of "busy, retry" (Codex reproduced this).
                    async with _provider_slot(nested=_is_nested(universe_context)):
                        before_launch = getattr(
                            served_authority, "before_provider_launch", None
                        ) if served_authority is not None else None
                        if callable(before_launch):
                            before_launch()
                        resp = await provider.complete(
                            prompt, system, cfg, universe_dir=universe_dir,
                        )
                except _ProviderBusy:
                    # Not a provider failure: nothing launched, so the reservation is
                    # released untouched, no cooldown is applied, and the actionable
                    # message reaches the caller instead of being flattened into
                    # "all providers exhausted".
                    if budget_reservation is not None:
                        # RELEASED, not abandoned: nothing launched, so no tokens were
                        # spent and charging the binding would exhaust a budget that
                        # still has capacity — the same reasoning the
                        # ProviderUnavailableError branch below applies.
                        try:
                            release_served_provider_budget(
                                universe_dir.parent, budget_reservation,
                            )
                        except Exception:
                            # Logged, not suppressed silently: a failed release leaves a
                            # binding charged for a turn that never ran, and swallowing
                            # it is how that becomes an unexplained "budget exhausted".
                            logger.exception(
                                "failed to release reservation after admission refusal"
                            )
                    raise
                except BaseException as exc:
                    if budget_reservation is not None:
                        # A provider that never became available produced no
                        # tokens, so its reservation must be RELEASED, not
                        # conservatively consumed forever. Abandoning it
                        # (`indeterminate`) permanently charges the binding for a
                        # turn that spent nothing — so a flaky provider exhausts
                        # its own budget one failed turn at a time and then reads
                        # as "budget exhausted" while actually having capacity.
                        # Only a failure AFTER the call began (genuinely unknown
                        # usage) is conservatively consumed.
                        if isinstance(exc, ProviderUnavailableError):
                            release_served_provider_budget(
                                universe_dir.parent,
                                budget_reservation,
                            )
                        else:
                            abandon_served_provider_budget(
                                universe_dir.parent,
                                budget_reservation,
                            )
                    if invocation_carrier is not None:
                        if isinstance(
                            exc,
                            (
                                ProviderRateLimitedError,
                                ProviderOverloadedError,
                                ProviderUnavailableError,
                            ),
                        ):
                            settle_carrier(
                                ProviderInvocationReservationState.FAILED,
                                input_tokens=0,
                                output_tokens=0,
                                cost_microunits=0,
                            )
                        else:
                            settle_carrier(
                                ProviderInvocationReservationState.INDETERMINATE
                            )
                    raise
                if budget_reservation is not None:
                    finalize_served_provider_budget(
                        universe_dir.parent,
                        authority=served_authority,
                        reservation=budget_reservation,
                        input_tokens=resp.input_tokens,
                        output_tokens=resp.output_tokens,
                        cost_microunits=resp.cost_microunits,
                        fallback_output=resp.text,
                    )
                # A SUCCEEDED settlement must carry KNOWN usage: settle_invocation
                # rejects anything that is not an int. But usage is optional on
                # ProviderResponse by design -- "every existing construction site
                # and non-streaming provider stays a valid terminal
                # ProviderResponse" (providers/base.py) -- and codex_provider only
                # populates it when machine accounting is on
                # (`machine_accounting = bool(config.sandbox_workspace)`,
                # codex_provider.py:350). A plain prompt-template node has no
                # sandbox workspace, so a perfectly successful call arrived here
                # with all three fields None and the settlement destroyed it:
                # every prompt-template run in the founder's universe failed with
                # "provider invocation usage could not be settled" on 2026-08-27
                # while effect-only branches, which take no carrier, kept working.
                #
                # INDETERMINATE is the state that already means exactly this, and
                # its budget treatment is the conservative one (consume the
                # reservation rather than report a free call). Settling zeros
                # instead would report the call as free and leave the budget
                # undrainable.
                if (
                    resp.input_tokens is None
                    or resp.output_tokens is None
                    or resp.cost_microunits is None
                ):
                    settle_carrier(ProviderInvocationReservationState.INDETERMINATE)
                else:
                    settle_carrier(
                        ProviderInvocationReservationState.SUCCEEDED,
                        input_tokens=resp.input_tokens,
                        output_tokens=resp.output_tokens,
                        cost_microunits=resp.cost_microunits,
                    )
                self._quota.record_success(provider_name)
            except _ProviderBusy:
                # Nothing launched: not a provider failure, so no cooldown and no
                # "exhausted" verdict about a provider that was never asked. Codex
                # reproduced the alternative — `provider_calls=0`, cooldown 29s,
                # AllProvidersExhaustedError — where the inner re-raise was swallowed by
                # this outer classifier.
                raise
            except ProviderAuthorityHeldError:
                raise
            except (ProviderRateLimitedError, ProviderOverloadedError) as exc:
                # A genuine rate-limit / overload IS real capacity: cool the
                # provider until its own retry-after (+margin), keeping fallback
                # forbidden for the sole served writer.
                cd = _rate_limit_cooldown_s(exc)
                self._quota.cooldown(provider_name, cd)
                logger.warning(
                    "Provider %s rate-limited/overloaded (%s), cooldown %ds",
                    provider_name, exc.failure_class, cd,
                )
                attempts.append(ProviderAttemptDiagnostic(
                    provider=provider_name, status="failed",
                    skip_class=classify_unavailable(exc),
                    detail=str(exc)[:200],
                    failure_class=exc.failure_class,
                    retry_after_s=getattr(exc, "retry_after", None),
                    side_effect_state=_side_effect_from(exc),
                ))
                continue
            except (ProviderIdleTimeoutError, InteractiveDeadlineError) as exc:
                # A transient attempt timeout is NOT proof the credential is
                # down. Do NOT cool the sole served writer — the next turn stays
                # eligible. The process was already killed by the provider.
                logger.warning(
                    "Provider %s ended on %s (no provider cooldown)",
                    provider_name, exc.failure_class,
                )
                attempts.append(ProviderAttemptDiagnostic(
                    provider=provider_name, status="failed",
                    skip_class="timed_out",
                    detail=str(exc)[:200],
                    failure_class=exc.failure_class,
                    side_effect_state=_side_effect_from(exc),
                ))
                continue
            except ProviderProtocolError as exc:
                self._quota.cooldown(provider_name, COOLDOWN_OTHER)
                logger.warning(
                    "Provider %s protocol error, cooldown %ds",
                    provider_name, COOLDOWN_OTHER,
                )
                attempts.append(ProviderAttemptDiagnostic(
                    provider=provider_name, status="failed",
                    skip_class="provider_error",
                    detail=str(exc)[:200],
                    failure_class=exc.failure_class,
                    side_effect_state=_side_effect_from(exc),
                ))
                continue
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
            except _ProviderBusy:
                # Nothing launched: not a provider failure, so no cooldown and no
                # "exhausted" verdict about a provider that was never asked. Codex
                # reproduced the alternative — `provider_calls=0`, cooldown 29s,
                # AllProvidersExhaustedError — where the inner re-raise was swallowed by
                # this outer classifier.
                raise
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
        if served_authority is not None:
            raise AllProvidersExhaustedError(
                f"Served provider {served_authority.provider!r} exhausted; "
                "universe authority forbids fallback widening.",
                attempts=attempts,
                failure_class=dominant_failure_class(attempts),
                retry_after=dominant_retry_after_s(attempts),
            )
        if invocation_carrier is not None:
            settle_carrier(
                ProviderInvocationReservationState.CANCELLED_BEFORE_LAUNCH,
                input_tokens=0,
                output_tokens=0,
                cost_microunits=0,
            )
            raise AllProvidersExhaustedError(
                f"Armed provider {invocation_carrier.provider!r} exhausted; "
                "provider authority forbids fallback widening.",
                attempts=attempts,
                failure_class=dominant_failure_class(attempts),
                retry_after=dominant_retry_after_s(attempts),
            )
        if is_pinned_writer:
            # Hard pin must fail loudly rather than silently falling through
            # to a different provider (hard rule #8).
            raise AllProvidersExhaustedError(
                f"Pinned writer provider {pin_writer!r} exhausted. "
                "TINYASSETS_PIN_WRITER disables fallback — clear the env var "
                "to re-enable the default chain.",
                attempts=attempts,
                failure_class=dominant_failure_class(attempts),
                retry_after=dominant_retry_after_s(attempts),
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
            failure_class=dominant_failure_class(attempts),
            retry_after=dominant_retry_after_s(attempts),
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

    async def call_with_policy(
        self,
        role: str,
        prompt: str,
        system: str,
        policy: dict | None,
        config: ModelConfig | None = None,
        difficulty: str = "",
        *,
        operation: str | None = None,
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
        if universe_context is not None:
            response = await self.call(
                role,
                prompt,
                system,
                config,
                operation=operation,
                universe_context=universe_context,
            )
            return response.text, response.provider, self._call_meta(response, attempts=1)

        resolved_config = _resolve_universe_config(universe_context)
        universe_dir = universe_context.universe_dir if universe_context else None
        cfg = config or _default_config(resolved_config)

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
        allowlist = _effective_universe_provider_ceiling(
            universe_context,
            resolved_config,
            carrier_armed=False,
        )
        if allowlist is not None:
            filtered_order = self._apply_allowlist(attempt_order, allowlist)
            if attempt_order and not filtered_order:
                logger.warning(
                    "Q6.3 allowlist removes all policy providers (%s) for "
                    "role=%s; falling through to role chain.",
                    attempt_order, role,
                )
            attempt_order = filtered_order

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
        auth_alive_order = self._apply_auth_health_policy(attempt_order)
        if attempt_order and not auth_alive_order:
            logger.warning(
                "All policy providers have dead subscription login (%s) for "
                "role=%s; falling through to role chain.",
                attempt_order, role,
            )
        attempt_order = auth_alive_order

        # Try policy-derived providers
        tried = 0
        # Track the classifed failure of the last executed policy provider so the
        # aggregate we raise below carries an honest failure_class/retry_after
        # (Codex re-review blockers F/I/K): the notice must never fall back to a
        # substring "capacity" guess.
        last_fc: str | None = None
        last_ra: float | None = None
        # Full attempt telemetry of the last executed provider, carried onto the
        # aggregate so terminal/TTFT/progress-age/exit are not lost when the
        # original classified exception is replaced (Codex re-review blocker K).
        last_tele: dict | None = None
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
                # Bound concurrent provider SUBPROCESSES (~77 MB PSS each,
                # measured). ASYNC form — a blocking acquire stalls the event loop, and
                # this method gathers admission-taking tasks onto one loop.
                async with _provider_slot(nested=_is_nested(universe_context)):
                    resp = await provider.complete(
                        prompt, system, cfg, universe_dir=universe_dir,
                    )
                self._quota.record_success(provider_name)
                return resp.text, provider_name, self._call_meta(resp, attempts=tried)
            except ProviderAuthorityHeldError:
                # Serving authority unavailable/revoked is NOT a provider fault to
                # swallow as generic error + cooldown; preserve it on the policy
                # path exactly like the role chain (blocker F) so the caller gets
                # the honest "connect your provider" outcome, not a fallthrough.
                raise
            except (ProviderRateLimitedError, ProviderOverloadedError) as exc:
                # New failure-class cooldown semantics on the policy path too
                # (blocker F): a genuine rate-limit/overload cools until the
                # provider's own retry-after (+margin), NOT a fixed unavailable
                # window — otherwise a documented 30s wait is over/under-cooled.
                cd = _rate_limit_cooldown_s(exc)
                self._quota.cooldown(provider_name, cd)
                last_fc = exc.failure_class
                last_ra = getattr(exc, "retry_after", None)
                last_tele = getattr(exc, "attempt_telemetry", None)
                logger.warning(
                    "Policy provider %s rate-limited/overloaded (%s), cooldown %ds",
                    provider_name, exc.failure_class, cd,
                )
            except (ProviderIdleTimeoutError, InteractiveDeadlineError) as exc:
                # A transient attempt timeout is NOT proof the credential is down.
                # Do NOT cool the provider on the policy path either (blocker F);
                # the next turn stays eligible. The process was already killed.
                last_fc = exc.failure_class
                last_tele = getattr(exc, "attempt_telemetry", None)
                logger.warning(
                    "Policy provider %s ended on %s (no provider cooldown)",
                    provider_name, exc.failure_class,
                )
            except ProviderProtocolError:
                self._quota.cooldown(provider_name, COOLDOWN_OTHER)
                last_fc = "provider_protocol_error"
                logger.warning(
                    "Policy provider %s protocol error, cooldown %ds",
                    provider_name, COOLDOWN_OTHER,
                )
            except _ProviderBusy:
                # Nothing launched: not a provider failure, so no cooldown and no
                # "exhausted" verdict about a provider that was never asked. Codex
                # reproduced the alternative — `provider_calls=0`, cooldown 29s,
                # AllProvidersExhaustedError — where the inner re-raise was swallowed by
                # this outer classifier.
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

        # Fall-through-to-self.call() is the DOCUMENTED policy fallback (e.g. a
        # preferred Claude that is unavailable should still let a healthy Codex
        # role-chain provider answer). We must preserve it (Codex re-review #2
        # caught an over-broad `if tried > 0: raise` that suppressed Codex
        # fallback entirely). The ONE case where re-executing is dangerous is a
        # possible SIDE EFFECT: an idle/deadline attempt that had already started
        # a tool did NOT cool the provider, so the role chain would re-run the
        # SAME provider and could duplicate that effect (Codex re-review #1
        # blocker F). Suppress the fall-through ONLY then; otherwise fall through
        # so genuine cross-provider fallback still works.
        last_side_effect = (
            last_tele.get("side_effect_state")
            if isinstance(last_tele, dict) else None
        )
        if tried > 0 and last_side_effect in ("possible", "committed"):
            agg = AllProvidersExhaustedError(
                f"All policy providers exhausted for role={role}.",
                failure_class=last_fc,
                retry_after=last_ra,
            )
            if last_tele is not None:
                agg.attempt_telemetry = last_tele
            raise agg
        # Fall through to the role chain (a preferred provider that failed cleanly
        # — e.g. rate-limited/unavailable, no possible side effect — must still let
        # a healthy role-chain provider answer). If the role chain ALSO exhausts,
        # preserve THIS policy attempt's classification on the aggregate (Codex
        # re-review #3 regression: a real rate-limit was otherwise downgraded to a
        # generic "error" notice after fallthrough because the role-chain aggregate
        # carried failure_class=None).
        logger.info(
            "Policy providers exhausted for role=%s; falling through to role chain",
            role,
        )
        try:
            resp = await self.call(
                role, prompt, system, cfg, universe_context=universe_context,
            )
        except AllProvidersExhaustedError as chain_exc:
            if last_fc is not None and chain_exc.failure_class is None:
                chain_exc.failure_class = last_fc
                chain_exc.retry_after = last_ra
                if last_tele is not None and getattr(
                    chain_exc, "attempt_telemetry", None,
                ) is None:
                    chain_exc.attempt_telemetry = last_tele
            raise
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
        operation: str | None = None,
        universe_context: UniverseContext | None = None,
    ) -> tuple[str, str, dict]:
        """Synchronous wrapper for :meth:`call_with_policy`."""
        cfg = config or _default_config(_resolve_universe_config(universe_context))
        # See call_sync (blocker L): enforce the timeout INSIDE the async task so
        # a timeout cancels the coroutine and kills the streaming subprocess, and
        # never fire below the stream absolute cap.
        inner_timeout = _sync_call_timeout_s(cfg)

        # Capture universe_context in the closure so it survives the hop into
        # the ThreadPoolExecutor worker thread (no ContextVar — a ContextVar
        # set here would NOT propagate to the pool's worker thread).
        def _run() -> tuple[str, str, dict]:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    asyncio.wait_for(
                        self.call_with_policy(
                            role, prompt, system, policy, cfg, difficulty,
                            operation=operation,
                            universe_context=universe_context,
                        ),
                        timeout=inner_timeout,
                    )
                )
            except asyncio.TimeoutError:
                raise ProviderTimeoutError(
                    f"call_with_policy_sync exceeded {inner_timeout:.0f}s for "
                    f"role={role} (subprocess cancelled/killed)"
                )
            finally:
                loop.close()

        future = self._thread_pool.submit(_run)
        try:
            return future.result(timeout=inner_timeout + 30)
        except concurrent.futures.TimeoutError:
            logger.warning(
                "call_with_policy_sync backstop fired after %.0fs for role=%s",
                inner_timeout + 30, role,
            )
            raise ProviderTimeoutError(
                f"call_with_policy_sync exceeded {inner_timeout + 30:.0f}s "
                f"backstop for role={role}"
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
        operation: str | None = None,
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
        # The streaming served path has its OWN absolute cap (default 600s); the
        # sync wrapper MUST NOT fire below it (blocker L) or it would return
        # failure while the subprocess keeps streaming (possible side effects).
        # Enforce the cap INSIDE the async task via ``asyncio.wait_for`` so a
        # timeout CANCELS ``call`` → ``complete`` → ``_read_stream``'s finally,
        # which kills the subprocess. ``future.result`` keeps a slightly larger
        # backstop only for a wedged event loop.
        inner_timeout = _sync_call_timeout_s(cfg)

        def _run() -> ProviderResponse:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    asyncio.wait_for(
                        self.call(
                            role, prompt, system, cfg,
                            operation=operation,
                            universe_context=universe_context,
                        ),
                        timeout=inner_timeout,
                    )
                )
            except asyncio.TimeoutError:
                # wait_for already cancelled the coroutine (subprocess killed).
                raise ProviderTimeoutError(
                    f"call_sync exceeded {inner_timeout:.0f}s for role={role} "
                    "(subprocess cancelled/killed)"
                )
            finally:
                loop.close()

        future = self._thread_pool.submit(_run)
        try:
            return future.result(timeout=inner_timeout + 30)
        except concurrent.futures.TimeoutError:
            logger.warning(
                "call_sync backstop fired after %.0fs for role=%s (event loop "
                "wedged)", inner_timeout + 30, role,
            )
            raise ProviderTimeoutError(
                f"call_sync exceeded {inner_timeout + 30:.0f}s hard backstop "
                f"for role={role}"
            )

    # ------------------------------------------------------------------
    # Judge ensemble (model family diversity)
    # ------------------------------------------------------------------

    async def call_judge_ensemble(
        self,
        prompt: str,
        system: str,
        config: ModelConfig | None = None,
        *,
        operation: str | None = None,
        universe_context: UniverseContext | None = None,
    ) -> list[ProviderResponse]:
        """Fan out to ALL available judge providers in parallel.

        Calls every registered, non-cooldown provider once.  Never
        calls the same provider twice.  Returns 1-N responses
        depending on how many providers are healthy.
        """
        if universe_context is not None and universe_context.provider_invocation is not None:
            return [
                await self.call(
                    "judge",
                    prompt,
                    system,
                    config,
                    operation=operation,
                    universe_context=universe_context,
                )
            ]

        resolved_config = _resolve_universe_config(universe_context)
        universe_dir = universe_context.universe_dir if universe_context else None
        cfg = config or _default_config(resolved_config)

        # Q6.3 — filter judge ensemble by per-universe allowlist (privacy
        # primitive). Empty filter => empty list, matching the existing
        # "no judges available" contract at L484-486.
        allowlist = _effective_universe_provider_ceiling(
            universe_context,
            resolved_config,
            carrier_armed=False,
        )
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
        auth_alive_ensemble = self._apply_auth_health_policy(ensemble)
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

        # Fan out in parallel
        async def _call_one(
            name: str, provider: BaseProvider,
        ) -> ProviderResponse | None:
            try:
                # Bound concurrent provider SUBPROCESSES (~77 MB PSS each,
                # measured). ASYNC form — a blocking acquire stalls the event loop, and
                # this method gathers admission-taking tasks onto one loop.
                async with _provider_slot(nested=_is_nested(universe_context)):
                    resp = await provider.complete(
                        prompt, system, cfg, universe_dir=universe_dir,
                    )
                self._quota.record_success(name)
                return resp
            except _ProviderBusy:
                # The judge fan-out had no busy guard, so saturation returned an empty
                # ensemble AND cooled a provider that never ran: `result=[]`,
                # `provider_calls=0`, `cooldown=29s` (Codex round 3). Re-raised so the
                # gather surfaces it rather than silently degrading the ensemble.
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
