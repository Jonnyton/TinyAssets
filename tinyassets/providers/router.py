"""Exact-authority provider routing with no platform fallback."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from dataclasses import replace

from tinyassets.exceptions import (
    AllProvidersExhaustedError,
    ProviderAuthorityHeldError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from tinyassets.provider_work_authority import ProviderInvocationCarrier
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
)
from tinyassets.providers.diagnostics import (
    ProviderAttemptDiagnostic,
    classify_unavailable,
)
from tinyassets.providers.quota import (
    COOLDOWN_OTHER,
    COOLDOWN_TIMEOUT,
    COOLDOWN_UNAVAILABLE,
    QuotaTracker,
)

logger = logging.getLogger(__name__)

_CONNECT_PROVIDER_MESSAGE = (
    "Connect your provider before running this universe. TinyAssets will not "
    "borrow platform credentials or start a metered trial."
)
_SYNC_CALL_MAX_WORKERS = 8


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
    invocation_operation = (
        carrier.operation
        if universe_context is not None
        and universe_context.assigned_credential is not None
        else operation
    )
    carrier.validate_for_call(role=role, operation=invocation_operation)
    return carrier


def _default_config(context: UniverseContext | None = None) -> ModelConfig:
    try:
        resolved = context.config if context is not None else None
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


class ProviderRouter:
    """Launch exactly the provider named by server-resolved authority."""

    _thread_pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=_SYNC_CALL_MAX_WORKERS,
        thread_name_prefix="tinyassets-provider-sync",
    )

    def __init__(
        self,
        providers: dict[str, BaseProvider] | None = None,
        quota: QuotaTracker | None = None,
        **_retired_options: object,
    ) -> None:
        self._providers = providers or {}
        self._quota = quota or QuotaTracker()

    def register(self, provider: BaseProvider) -> None:
        self._providers[provider.name] = provider

    @property
    def available_providers(self) -> list[str]:
        return list(self._providers)

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
        """Resolve request authority, then launch one exact provider."""

        if (
            universe_context is not None
            and universe_context.provider_invocation is None
            and universe_context.assigned_credential is None
            and universe_context.served_provider is None
        ):
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
                return await self._call_authorized(
                    role,
                    prompt,
                    system,
                    config,
                    operation=operation,
                    universe_context=replace(
                        universe_context,
                        served_provider=authority,
                    ),
                )
        return await self._call_authorized(
            role,
            prompt,
            system,
            config,
            operation=operation,
            universe_context=universe_context,
        )

    async def _call_authorized(
        self,
        role: str,
        prompt: str,
        system: str,
        config: ModelConfig | None,
        *,
        operation: str | None,
        universe_context: UniverseContext | None,
    ) -> ProviderResponse:
        invocation = _provider_invocation_carrier(
            universe_context,
            role=role,
            operation=operation,
        )
        assigned = universe_context.assigned_credential if universe_context else None
        served = universe_context.served_provider if universe_context else None
        universe_dir = universe_context.universe_dir if universe_context else None
        cfg = config or _default_config(universe_context)

        if assigned is not None:
            if universe_dir is None or universe_dir.name != assigned.universe_id:
                raise ProviderAuthorityHeldError(_CONNECT_PROVIDER_MESSAGE)
            if (
                operation not in assigned.allowed_operations
                or role not in assigned.allowed_roles
            ):
                raise ProviderAuthorityHeldError(_CONNECT_PROVIDER_MESSAGE)
            provider_name = assigned.provider
            cfg = replace(
                cfg,
                credential_snapshot_dir=assigned.credential_snapshot_dir,
            )
        elif served is not None:
            if operation != "converse" or role != "writer":
                raise PermissionError("served provider authority is converse/writer only")
            if served.max_tokens < 1 or served.max_cost_microunits < 1:
                raise PermissionError("served provider authority has no positive budget")
            if cfg.max_tokens is None:
                cfg = replace(cfg, max_tokens=served.max_tokens)
            elif (
                isinstance(cfg.max_tokens, bool)
                or not isinstance(cfg.max_tokens, int)
                or cfg.max_tokens < 0
                or cfg.max_tokens > served.max_tokens
            ):
                raise PermissionError("provider call exceeds served token ceiling")
            provider_name = served.provider
            cfg = replace(cfg, credential_snapshot_dir=served.credential_snapshot_dir)
        elif invocation is not None:
            if invocation.max_tokens < 1 or invocation.max_cost_microunits < 1:
                raise PermissionError("armed provider invocation has no positive budget")
            if cfg.max_tokens is None:
                cfg = replace(cfg, max_tokens=invocation.max_tokens)
            elif (
                isinstance(cfg.max_tokens, bool)
                or not isinstance(cfg.max_tokens, int)
                or cfg.max_tokens < 0
                or cfg.max_tokens > invocation.max_tokens
            ):
                raise PermissionError("provider call exceeds armed token ceiling")
            provider_name = invocation.provider
        else:
            raise ProviderAuthorityHeldError(_CONNECT_PROVIDER_MESSAGE)

        provider = self._providers.get(provider_name)
        attempts: list[ProviderAttemptDiagnostic] = []
        if provider is None:
            attempts.append(ProviderAttemptDiagnostic(
                provider=provider_name,
                status="skipped",
                skip_class="not_in_registry",
                detail="assigned provider is not registered with daemon",
            ))
            raise self._exhausted(provider_name, attempts)
        if not self._quota.available(provider_name):
            attempts.append(ProviderAttemptDiagnostic(
                provider=provider_name,
                status="skipped",
                skip_class="quota_or_cooldown",
                detail="assigned provider is rate-limited or cooling down",
                cooldown_remaining_s=(
                    self._quota.cooldown_remaining(provider_name) or None
                ),
            ))
            raise self._exhausted(provider_name, attempts)

        reservation = None
        try:
            if served is not None:
                from tinyassets.auth.middleware import consume_provider_request_invocation
                from tinyassets.provider_assignment import reserve_served_provider_budget

                try:
                    consume_provider_request_invocation(
                        served.request_capability,
                        limit=served.request_max_invocations,
                    )
                except PermissionError as exc:
                    raise ProviderAuthorityHeldError(
                        _CONNECT_PROVIDER_MESSAGE
                    ) from exc
                estimated_input_tokens = max(
                    1,
                    len((f"{system}\n\n{prompt}" if system else prompt).encode()),
                )
                reservation = reserve_served_provider_budget(
                    universe_dir.parent,
                    universe_dir=universe_dir,
                    authority=served,
                    requested_output_tokens=cfg.max_tokens,
                    estimated_input_tokens=estimated_input_tokens,
                )
                cfg = replace(cfg, max_tokens=reservation.output_tokens)
            response = await provider.complete(
                prompt,
                system,
                cfg,
                universe_dir=universe_dir,
            )
            if reservation is not None:
                from tinyassets.provider_assignment import finalize_served_provider_budget

                finalize_served_provider_budget(
                    universe_dir.parent,
                    authority=served,
                    reservation=reservation,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    cost_microunits=response.cost_microunits,
                    fallback_output=response.text,
                )
            self._quota.record_success(provider_name)
            return response
        except ProviderAuthorityHeldError:
            raise
        except BaseException as exc:
            if reservation is not None:
                from tinyassets.provider_assignment import abandon_served_provider_budget

                abandon_served_provider_budget(universe_dir.parent, reservation)
            if isinstance(exc, ProviderUnavailableError):
                self._quota.cooldown(provider_name, COOLDOWN_UNAVAILABLE)
                skip_class = classify_unavailable(exc)
            elif isinstance(exc, ProviderTimeoutError):
                self._quota.cooldown(provider_name, COOLDOWN_TIMEOUT)
                skip_class = "timed_out"
            elif isinstance(exc, ProviderError):
                self._quota.cooldown(provider_name, COOLDOWN_OTHER)
                skip_class = "provider_error"
            else:
                self._quota.cooldown(provider_name, COOLDOWN_OTHER)
                skip_class = "unknown"
            attempts.append(ProviderAttemptDiagnostic(
                provider=provider_name,
                status="failed",
                skip_class=skip_class,
                detail=f"{type(exc).__name__}: {str(exc)[:160]}",
            ))
            raise self._exhausted(provider_name, attempts) from exc

    @staticmethod
    def _exhausted(
        provider_name: str,
        attempts: list[ProviderAttemptDiagnostic],
    ) -> AllProvidersExhaustedError:
        return AllProvidersExhaustedError(
            f"Assigned provider {provider_name!r} exhausted; workflow authority "
            "forbids fallback widening.",
            attempts=attempts,
        )

    @staticmethod
    def _call_meta(response: ProviderResponse, attempts: int) -> dict[str, object]:
        return {
            "model": response.model or "",
            "family": response.family or "",
            "latency_ms": response.latency_ms,
            "degraded": response.degraded,
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
    ) -> tuple[str, str, dict[str, object]]:
        """Apply only non-routing model policy, then use exact authority."""

        del difficulty
        cfg = config or _default_config(universe_context)
        if policy:
            temperature = policy.get("temperature")
            max_tokens = policy.get("max_tokens")
            if isinstance(temperature, (int, float)) and not isinstance(
                temperature, bool
            ):
                cfg = replace(cfg, temperature=float(temperature))
            if isinstance(max_tokens, int) and not isinstance(max_tokens, bool):
                cfg = replace(cfg, max_tokens=max_tokens)
        response = await self.call(
            role,
            prompt,
            system,
            cfg,
            operation=operation,
            universe_context=universe_context,
        )
        return response.text, response.provider, self._call_meta(response, 1)

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
    ) -> tuple[str, str, dict[str, object]]:
        cfg = config or _default_config(universe_context)

        def _run():
            return asyncio.run(self.call_with_policy(
                role,
                prompt,
                system,
                policy,
                cfg,
                difficulty,
                operation=operation,
                universe_context=universe_context,
            ))

        return self._wait(_run, cfg.timeout + 30, role)

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
        cfg = config or _default_config(universe_context)

        def _run():
            return asyncio.run(self.call(
                role,
                prompt,
                system,
                cfg,
                operation=operation,
                universe_context=universe_context,
            ))

        return self._wait(_run, cfg.timeout + 30, role)

    def _wait(self, callback, timeout: int, role: str):
        future = self._thread_pool.submit(callback)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            raise ProviderTimeoutError(
                f"provider call exceeded {timeout}s for role={role}"
            ) from exc

    async def call_judge_ensemble(
        self,
        prompt: str,
        system: str,
        config: ModelConfig | None = None,
        *,
        operation: str | None = None,
        universe_context: UniverseContext | None = None,
    ) -> list[ProviderResponse]:
        """A workflow may model fan-out; the platform launches one credential."""

        return [await self.call(
            "judge",
            prompt,
            system,
            config,
            operation=operation,
            universe_context=universe_context,
        )]


__all__ = ["ProviderRouter"]
