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

    def to_dict(self) -> dict[str, Any]:
        """Serialize, dropping ``None`` fields for compactness."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


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
