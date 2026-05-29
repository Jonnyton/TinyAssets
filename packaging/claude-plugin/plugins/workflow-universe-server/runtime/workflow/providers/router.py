"""Provider router -- fallback chains across six providers.

Hard invariant: every call has a fallback chain that terminates at
``ollama-local``.  The system NEVER stops due to provider
unavailability unless local models are also down.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os

from workflow.exceptions import (
    AllProvidersExhaustedError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from workflow.providers.base import (
    DEGRADED_JUDGE_RESPONSE,
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    api_key_providers_enabled,
)
from workflow.providers.diagnostics import (
    ProviderAttemptDiagnostic,
    build_chain_state,
    classify_unavailable,
)
from workflow.providers.quota import (
    COOLDOWN_OTHER,
    COOLDOWN_TIMEOUT,
    COOLDOWN_UNAVAILABLE,
    QuotaTracker,
)

logger = logging.getLogger(__name__)

def _default_config() -> ModelConfig:
    """Build default ModelConfig from universe config if available."""
    try:
        from workflow import runtime_singletons as runtime

        cfg = runtime.universe_config
        return ModelConfig(
            temperature=cfg.temperature,
            timeout=cfg.timeout,
            max_tokens=cfg.max_tokens,
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
    """

    def __init__(
        self,
        providers: dict[str, BaseProvider] | None = None,
        quota: QuotaTracker | None = None,
        chain_drain_empty_threshold: int = _CHAIN_DRAIN_EMPTY_THRESHOLD,
    ) -> None:
        self._providers: dict[str, BaseProvider] = providers or {}
        self._quota = quota or QuotaTracker()
        self._chain_drain_empty_threshold = chain_drain_empty_threshold
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
    def _current_allowlist() -> list[str] | None:
        """Read the active universe's `allowed_providers` allowlist, or None.

        Q6.3 enforcement primitive — see UniverseConfig.allowed_providers.
        Returns None when no universe config is bound or the field is unset
        (full fallback chain preserved, backwards-compatible).
        """
        try:
            from workflow import runtime_singletons as runtime

            return runtime.universe_config.allowed_providers
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

    async def call(
        self,
        role: str,
        prompt: str,
        system: str,
        config: ModelConfig | None = None,
    ) -> ProviderResponse:
        """Route a single call through the fallback chain for *role*.

        Returns a :class:`ProviderResponse` on success.  For judge role,
        returns a degraded sentinel when all providers are exhausted.
        For other roles, raises :class:`AllProvidersExhaustedError`.
        """
        cfg = config or _default_config()
        chain = FALLBACK_CHAINS.get(role, FALLBACK_CHAINS["writer"])

        # Hard pin: WORKFLOW_PIN_WRITER narrows the writer chain to a
        # single provider for this call. No fallback — if the pinned
        # provider fails, the call fails loudly (hard rule #8).
        pin_writer = os.environ.get("WORKFLOW_PIN_WRITER", "").strip()
        is_pinned_writer = role == "writer" and bool(pin_writer)
        if is_pinned_writer:
            chain = [pin_writer]
        else:
            # Apply per-universe provider preference from config.yaml
            try:
                from workflow import runtime_singletons as runtime
                ucfg = runtime.universe_config
                if role == "writer" and ucfg.preferred_writer:
                    chain = self._apply_preference(chain, ucfg.preferred_writer)
                elif role == "judge" and ucfg.preferred_judge:
                    chain = self._apply_preference(chain, ucfg.preferred_judge)
            except Exception:
                pass

        # Q6.3 — apply per-universe allowlist (privacy primitive). Pin already
        # narrowed chain to [pin_writer] above; the filter then enforces
        # pin × allowlist composition. None = no-op (backwards-compat).
        allowlist = self._current_allowlist()
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
                        f"provider to the allowlist or clear WORKFLOW_PIN_WRITER."
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
                    "WORKFLOW_ALLOW_API_KEY_PROVIDERS=1 only for an intentional "
                    "API-key daemon, or pin a subscription-backed provider."
                )
            raise AllProvidersExhaustedError(
                f"All providers for role={role!r} are API-key-backed and "
                "disabled by default. Workflow daemons are subscription-only "
                "unless WORKFLOW_ALLOW_API_KEY_PROVIDERS=1 is set."
            )
        if auth_filtered != chain:
            logger.info(
                "Ignoring API-key providers by default for role=%s: removed=%s",
                role,
                [p for p in chain if p not in auth_filtered],
            )
            chain = auth_filtered

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
                resp = await provider.complete(prompt, system, cfg)
                self._quota.record_success(provider_name)
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
                "WORKFLOW_PIN_WRITER disables fallback — clear the env var "
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

    async def call_with_policy(
        self,
        role: str,
        prompt: str,
        system: str,
        policy: dict | None,
        config: ModelConfig | None = None,
        difficulty: str = "",
    ) -> tuple[str, str]:
        """Route a call honouring an explicit llm_policy dict.

        Returns ``(response_text, provider_name_used)``.

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
        method extracts ``.text`` and returns (text, provider_name). For
        the policy path we track the name explicitly.
        """
        cfg = config or _default_config()

        if not policy:
            resp = await self.call(role, prompt, system, cfg)
            return resp.text, resp.provider

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
        allowlist = self._current_allowlist()
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

        # Try policy-derived providers
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
            try:
                resp = await provider.complete(prompt, system, cfg)
                self._quota.record_success(provider_name)
                return resp.text, provider_name
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
        resp = await self.call(role, prompt, system, cfg)
        return resp.text, resp.provider

    def call_with_policy_sync(
        self,
        role: str,
        prompt: str,
        system: str,
        policy: dict | None,
        config: ModelConfig | None = None,
        difficulty: str = "",
    ) -> tuple[str, str]:
        """Synchronous wrapper for :meth:`call_with_policy`."""
        cfg = config or _default_config()
        sync_timeout = cfg.timeout + 30

        def _run() -> tuple[str, str]:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    self.call_with_policy(
                        role, prompt, system, policy, cfg, difficulty,
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
        thread_name_prefix="workflow-provider-sync",
    )

    def call_sync(
        self,
        role: str,
        prompt: str,
        system: str,
        config: ModelConfig | None = None,
    ) -> ProviderResponse:
        """Synchronous version of :meth:`call` for use from sync code.

        Runs the async ``call`` in a dedicated thread with its own event
        loop, avoiding the "loop already running" problem that blocks
        ``loop.run_until_complete`` inside LangGraph nodes.
        """
        cfg = config or _default_config()
        # Allow the subprocess timeout to fire first (+30s margin for
        # async overhead, fallback attempts, etc.)
        sync_timeout = cfg.timeout + 30

        def _run() -> ProviderResponse:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    self.call(role, prompt, system, cfg)
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

    async def call_judge_ensemble(
        self,
        prompt: str,
        system: str,
        config: ModelConfig | None = None,
    ) -> list[ProviderResponse]:
        """Fan out to ALL available judge providers in parallel.

        Calls every registered, non-cooldown provider once.  Never
        calls the same provider twice.  Returns 1-N responses
        depending on how many providers are healthy.
        """
        cfg = config or _default_config()

        # Q6.3 — filter judge ensemble by per-universe allowlist (privacy
        # primitive). Empty filter => empty list, matching the existing
        # "no judges available" contract at L484-486.
        allowlist = self._current_allowlist()
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
                "WORKFLOW_ALLOW_API_KEY_PROVIDERS=1.",
                ensemble,
            )
        ensemble = auth_ensemble

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
                resp = await provider.complete(prompt, system, cfg)
                self._quota.record_success(name)
                return resp
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
