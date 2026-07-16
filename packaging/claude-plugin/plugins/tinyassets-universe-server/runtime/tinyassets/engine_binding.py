"""Per-universe engine-capacity binding resolver + the non-ambient-work flag.

The honest "can this universe run?" predicate. A universe executes work only on
capacity **explicitly bound to it** (design note 2026-07-15 gap G7). The
sanctioned founder lanes (per the 2026-07-02 credential-custody research §0/§4 —
the platform may NOT custody a founder's personal subscription tokens) are: a
BYO API key (vault), a self-hosted endpoint, market-rented capacity, or a hosted
daemon (the founder runs their own subscription CLI on their OWN device — tokens
never reach the platform). No ambient, unbound daemon work — a fresh universe
with no bind act is honestly idle-until-bound.

Founder ``llm_subscription`` vault custody is a BLOCKED lane and is NOT counted
as founder capacity here; the platform's own droplet subscription is
process-global first-party auth (Option E) that never flows through the founder
vault.

This module inspects the SAME per-universe primitives the bind acts already
write — the credential vault (:mod:`tinyassets.credential_vault`) and
``config.yaml`` (:mod:`tinyassets.config`) — and never adds a parallel capacity
store.

Two independent surfaces consume it:

* :func:`resolve_engine_binding` — a pure inspection used by ``get_status`` to
  report binding state honestly (additive onboarding surface; always available).
* :func:`non_ambient_work_enabled` — the feature flag the dispatcher/supervisor
  consults before deciding whether an unbound universe may be worked.

**The non-ambient gate is flag-gated and DEFAULT OFF.** With the flag off the
gate is inert and the daemon works universes exactly as it does today (ambient
work) — a byte-for-byte no-op. The production switch-off of the platform-global
daemon is a separate, host-gated decision; flipping this flag on is NOT that
switch.

A DECLARED-but-broken binding raises :class:`EngineMisconfiguredError` so a
bound-but-broken universe fails loud instead of being silently treated as
unbound and skipped (Hard Rule #8).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Engine sources a founder may declare. Anything else in config.yaml is a broken
# declaration (fail loud — Finding 4). ``subscription`` is a RETIRED lane kept
# here only so a legacy value reads as idle rather than "unknown source".
_KNOWN_ENGINE_SOURCES = frozenset({
    "byo_api_key",
    "self_hosted_endpoint",
    "market_rented",
    "host_daemon",
    "subscription",
})

#: Env flag that arms the non-ambient work gate. DEFAULT OFF (unset) = today's
#: behavior. See :func:`non_ambient_work_enabled`.
NON_AMBIENT_WORK_ENV = "TINYASSETS_NON_AMBIENT_WORK"

#: Env flag gating the executable BYO-API-key path. DEFAULT OFF. Hosted BYO keys
#: are stored plaintext-base64 in the per-universe vault; the custody research
#: requires KMS-wrapped / external-secret-manager storage BEFORE the platform may
#: hold + execute founder keys. Until that lands AND is verified, the executable
#: BYO path is DARK: set_engine refuses BYO deposits, resolve_engine_binding
#: never reports a BYO key as bound, and the router does no direct BYO routing.
#: INDEPENDENT of the non-ambient flag (F3) — the non-ambient flag being OFF does
#: not disable BYO deposit/routing, so BYO needs its own gate.
BYO_VAULT_ENCRYPTED_ENV = "TINYASSETS_BYO_VAULT_ENCRYPTED"

_TRUTHY = {"1", "true", "yes", "on"}

# Providers a BYO key can EXECUTE today. Codex BYO needs sandboxing (bwrap +
# attestation) that is unmet, and non-sandboxed `codex exec` runs against the
# host checkout with --dangerously-bypass — so a Codex/OpenAI BYO key is a
# DECLARED-not-executable lane (idle + honest guidance), same as the runtime
# lanes (F1). Only the sandboxed claude-code path is executable.
_EXECUTABLE_BYO_PROVIDERS = frozenset({"claude-code"})


class EngineMisconfiguredError(RuntimeError):
    """A universe DECLARED an engine binding, but its capacity is broken.

    Raised (never swallowed) so a bound-but-broken universe fails loud rather
    than being silently treated as unbound and skipped (Hard Rule #8). Callers
    that consult the gate must surface this loudly, not swallow it into a quiet
    "skip this universe".
    """

    def __init__(self, universe_id: str, engine_source: str, detail: str) -> None:
        self.universe_id = universe_id
        self.engine_source = engine_source
        self.detail = detail
        super().__init__(
            f"universe {universe_id!r} declares engine_source="
            f"{engine_source!r} but its capacity is misconfigured: {detail}"
        )


# A capacity is eligible for a SPECIFIC provider — a universe holding an
# Anthropic key must not satisfy a Codex-pinned worker (which would run on
# global Codex auth). Map each vault service to the writer-provider name it
# feeds (the names in providers.router.FALLBACK_CHAINS).
#
# Only the CLI-subprocess services are per-universe-consumable today (their key
# is overlaid onto the subprocess env by provider_auth_env_overrides). gemini /
# groq / xai keys map only to process-global HTTP providers, so they are NOT
# founder capacity here (Finding 2, round 4) — keep this in lockstep with
# credential_vault.per_universe_byo_services().
_SERVICE_TO_PROVIDER: dict[str, str] = {
    # Anthropic / Claude family → the claude-code CLI writer.
    "anthropic": "claude-code",
    "claude": "claude-code",
    "claude-code": "claude-code",
    # OpenAI / Codex family → the codex CLI writer.
    "openai": "codex",
    "codex": "codex",
}


@dataclass(frozen=True)
class EngineBinding:
    """Resolved engine-capacity binding for one universe.

    ``bound`` is the load-bearing field: True when the universe has real, usable,
    EXECUTABLE capacity bound to it. In S5 the only producible capacity kind is
    ``byo_api_key`` (a validated Anthropic BYO key, and only while the
    vault-encryption gate is on) — the runtime / subscription / codex-BYO lanes
    are declared-not-executable and never bound. ``engine_source`` echoes the
    founder's declared choice from ``config.yaml`` (empty when none was declared).

    ``eligible_providers`` names the writer providers this capacity can actually
    serve — the gate is provider-level, not universe-level, so a Codex-pinned
    worker treats a claude-only universe as idle-until-bound. ``vault_providers``
    is the subset whose auth is per-universe VAULT auth that the child
    materializes at spawn — the pre-spawn global-auth quarantine must be skipped
    for these (they don't need process-global provider auth).
    """

    bound: bool
    engine_source: str
    capacity_kinds: tuple[str, ...]
    reason: str
    eligible_providers: frozenset[str] = frozenset()
    vault_providers: frozenset[str] = frozenset()

    def is_eligible_for(self, provider_name: str) -> bool:
        """Return True iff bound capacity can serve *provider_name*."""
        if not self.bound:
            return False
        return provider_name.strip() in self.eligible_providers

    def serves_via_vault(self, provider_name: str) -> bool:
        """Return True iff *provider_name* is satisfied by per-universe vault auth.

        The child materializes vault auth at spawn, so the caller may skip the
        process-global auth quarantine for these providers.
        """
        return provider_name.strip() in self.vault_providers

    def as_dict(self) -> dict[str, Any]:
        return {
            "bound": self.bound,
            "engine_source": self.engine_source,
            "capacity_kinds": list(self.capacity_kinds),
            "reason": self.reason,
            "eligible_providers": sorted(self.eligible_providers),
            "vault_providers": sorted(self.vault_providers),
        }


def non_ambient_work_enabled() -> bool:
    """Return whether the non-ambient work gate is armed. DEFAULT OFF.

    Reads :data:`NON_AMBIENT_WORK_ENV`.

    * OFF (unset / ``0`` / ``false`` / ``no`` / ``off``): the gate is inert. The
      dispatcher/supervisor works universes exactly as it does today (ambient
      work). This is the production default and a byte-for-byte no-op.
    * ON (``1`` / ``true`` / ``yes`` / ``on``): unbound universes are not worked
      — they are honestly idle-until-bound (see :func:`resolve_engine_binding`).
    """
    return os.environ.get(NON_AMBIENT_WORK_ENV, "").strip().lower() in _TRUTHY


def _vault_encryption_capability_attested() -> bool:
    """Code-backed proof that per-tenant vault encryption is REAL. DEFAULT False.

    The current vault stores keys plaintext-base64 — a truthy env flag alone must
    NEVER unlock deposit+execution of plaintext keys (C4). This returns False
    until real envelope encryption / an external secret manager is implemented
    AND verified in Phase 2; at that point, swap in the actual capability probe
    (e.g. confirm a KMS/secret-manager handle is reachable). Tests that need to
    simulate Phase-2 monkeypatch this to True.
    """
    return False  # Phase 2: implement real envelope encryption + attest it here.


def byo_execution_enabled() -> bool:
    """Return whether the executable BYO-key path is enabled. DEFAULT OFF.

    Requires BOTH the operator opt-in (:data:`BYO_VAULT_ENCRYPTED_ENV`) AND a
    code-backed encryption-capability attestation
    (:func:`_vault_encryption_capability_attested`). Because the attestation is
    False until Phase-2 envelope encryption lands, **the flag alone cannot unlock
    plaintext-key deposit+execution** (C4). OFF (this deploy) → the executable BYO
    path is DARK end-to-end: no deposit, no bound BYO, no direct BYO routing, no
    BYO env injection.
    """
    if os.environ.get(BYO_VAULT_ENCRYPTED_ENV, "").strip().lower() not in _TRUTHY:
        return False
    return _vault_encryption_capability_attested()


def _byo_key_auth_health(provider_name: str, universe_dir: Path) -> str:
    """Return a provider-specific BYO-key FORMAT check: ``ok`` / ``not_logged_in``.

    This is a FORMAT check, not a live auth probe — an Anthropic key must carry
    the ``sk-ant-`` prefix + minimum length, which rejects a decodable-but-junk
    key (e.g. ``"x"``) so it never reads as bound (F4). A real network auth-health
    probe (validate the key against the provider) is Phase-2 work and swaps in
    here; everything downstream already gates ``bound`` on a returned ``ok``.
    Propagates vault I/O errors (ValueError/OSError) to the caller, which
    normalizes them into a loud-but-caught misconfiguration (Fable F6).
    """
    if provider_name.strip() != "claude-code":
        # Non-executable BYO providers have no auth-health here (codex is idle, F1).
        return "not_logged_in"
    from tinyassets.credential_vault import resolve_llm_api_key

    key = resolve_llm_api_key(universe_dir, "ANTHROPIC_API_KEY")
    if key.startswith("sk-ant-") and len(key) >= 24:
        return "ok"
    return "not_logged_in"


def _raw_config(universe_dir: Path, universe_id: str) -> dict[str, Any]:
    """Return the raw ``config.yaml`` mapping.

    Read raw rather than via :func:`tinyassets.config.load_universe_config` so we
    can tell a DECLARED ``engine_source`` (explicit key present) apart from the
    dataclass default — the default ``byo_api_key`` must never read as a bind
    act on a fresh universe.

    A genuinely ABSENT file returns ``{}`` (quiet unbound). A PRESENT but
    unreadable / non-mapping file is a broken declaration → raise
    :class:`EngineMisconfiguredError` (Finding 4: don't let a corrupt config look
    like a fresh universe).
    """
    cfg_file = Path(universe_dir) / "config.yaml"
    if not cfg_file.is_file():
        return {}
    try:
        import yaml

        data = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — surface as a loud misconfiguration
        raise EngineMisconfiguredError(
            universe_id, "", f"config.yaml is unreadable: {exc}",
        ) from exc
    if data is None:
        return {}  # an empty file is a valid "no overrides" config.
    if not isinstance(data, dict):
        raise EngineMisconfiguredError(
            universe_id, "", "config.yaml is not a mapping",
        )
    return data


# Engine sources that persist only a config CHOICE. The executor that would
# consume work — a hosted daemon (device or platform), a matched market runtime,
# or a wired self-hosted endpoint route — DOES NOT EXIST YET in this slice. A
# runtime-instance row cannot prove executable capacity here: its liveness
# discriminator (metadata.worker_id) is forgeable via ``universe
# action=daemon_summon``; its updated_at is refreshed only at registration/control
# (never while a worker runs); and there is no executor lease/routing that ties a
# generic runtime to the SELECTED lane. Building that is a whole subsystem (out of
# scope for S5). So these sources are a DECLARED CHOICE, never executable capacity
# — they read as idle-until-executor-routing-exists (both latest-model gates,
# 2026-07-15). The ONLY genuinely-executable founder capacity in S5 is a validated
# BYO API key (the lane the provider router consumes end-to-end with vault env).
_RUNTIME_BACKED_SOURCES = frozenset(
    {"host_daemon", "market_rented", "self_hosted_endpoint"}
)


def _byo_row_usable(record: dict[str, Any], svc: str) -> bool:
    """Return True iff a BYO ``llm_api_key`` row is per-universe-consumable AND
    carries a non-empty, decodable secret.

    Counting a BYO row by ``credential_type`` alone lets a malformed vault (bad
    base64, missing key, an unknown service, or a gemini/groq/xai service with no
    per-universe consumption wiring) satisfy the gate and then fall through to
    other/global auth. Validate like bind time does: the service must be
    per-universe-consumable (its key is overlaid onto the CLI subprocess) and the
    secret must decode non-empty.
    """
    from tinyassets.credential_vault import _secret_value, per_universe_byo_services

    if svc not in per_universe_byo_services():
        return False
    try:
        secret = _secret_value(record, "api_key", "key", "token")
    except ValueError:
        return False
    return bool(secret)


@dataclass
class _VaultScan:
    """Result of scanning the per-universe vault for executable capacity."""

    capacity_kinds: list[str]
    eligible_providers: set[str]
    vault_providers: set[str]
    has_unusable_vault_source: bool


def _vault_capacity(universe_dir: Path) -> _VaultScan:
    """Scan the vault for USABLE founder BYO-API-key capacity.

    A BYO row counts only when it is per-universe-consumable with a decodable
    secret (:func:`_byo_row_usable`); an unusable-but-declared BYO row sets
    ``has_unusable_vault_source`` so the caller can fail loud instead of silently
    falling through to global auth.

    ``llm_subscription`` vault rows are DELIBERATELY ignored: founder subscription
    custody is a BLOCKED lane (2026-07-02 custody research §0/§4). A legacy
    subscription row therefore reads as NOT founder capacity and never fails loud.
    Propagates :class:`ValueError` (malformed vault) so the caller can fail loud.
    """
    from tinyassets.credential_vault import load_credential_vault

    records = load_credential_vault(universe_dir)  # raises ValueError if malformed
    kinds: list[str] = []
    eligible: set[str] = set()
    vault_providers: set[str] = set()
    has_unusable = False
    for record in records:
        if record.get("credential_type") != "llm_api_key":
            continue  # llm_subscription (blocked lane), vcs, social → not engine capacity
        svc = str(record.get("service") or record.get("provider") or "").strip().lower()
        if _byo_row_usable(record, svc):
            kinds.append("byo_api_key")
            provider = _SERVICE_TO_PROVIDER.get(svc)
            if provider:
                eligible.add(provider)
                vault_providers.add(provider)
        else:
            has_unusable = True
    return _VaultScan(kinds, eligible, vault_providers, has_unusable)


def resolve_engine_binding(universe_dir: str | Path) -> EngineBinding:
    """Inspect a universe's vault + config to resolve its bound engine capacity.

    Reads only the primitives the bind acts already write (the credential vault
    and ``config.yaml``) — no parallel capacity store.

    Returns an :class:`EngineBinding`. ``bound`` is True ONLY for the one
    genuinely-executable founder lane in S5: a vault-backed, per-universe-
    consumable BYO ``llm_api_key`` (its key is overlaid onto the CLI subprocess
    and consumed by the provider router end-to-end).

    The runtime-backed declared sources (``host_daemon`` / ``market_rented`` /
    ``self_hosted_endpoint``) are a DECLARED CHOICE, not executable capacity in
    S5 — no device/market/endpoint executor routing exists yet, and a
    runtime-instance row cannot prove liveness (its worker_id is forgeable and it
    carries no executor lease). They therefore read as ``bound=False``
    (idle-until-executor-routing-exists), never bound. A fresh universe with no
    bind act, and a legacy ``engine_source: subscription`` (a now-blocked lane),
    also read as idle.

    Raises :class:`EngineMisconfiguredError` only when the BYO lane is genuinely
    broken (declared ``byo_api_key`` with no usable key, or a present-but-unusable
    BYO row), a malformed config, or a malformed vault (Hard Rule #8: fail loud,
    never treat a broken binding as merely unbound).
    """
    udir = Path(universe_dir)
    universe_id = udir.name or "default-universe"
    raw = _raw_config(udir, universe_id)
    declared_source = str(raw.get("engine_source") or "").strip()
    if declared_source and declared_source not in _KNOWN_ENGINE_SOURCES:
        raise EngineMisconfiguredError(
            universe_id, declared_source,
            "unknown engine_source — expected one of "
            f"{sorted(_KNOWN_ENGINE_SOURCES)}",
        )

    try:
        scan = _vault_capacity(udir)
    except (ValueError, OSError) as exc:
        # F6: normalize ALL vault I/O failures (JSON ValueError AND
        # OSError/PermissionError reading the vault file) into a loud-but-caught
        # misconfiguration, so get_status + the supervisor (which catch
        # EngineMisconfiguredError) never crash on a bad vault file.
        raise EngineMisconfiguredError(
            universe_id,
            declared_source or "byo_api_key",
            f"credential vault is unreadable: {exc}",
        ) from exc

    # Lane matching: the ONLY executable capacity in S5 is a validated BYO key on
    # the byo_api_key lane (or an undeclared universe). A runtime-backed declared
    # source (host_daemon / market_rented / self_hosted_endpoint) is a declared
    # CHOICE with no executor routing yet — NEVER bound — and a stray BYO key does
    # NOT satisfy it (nor does its broken state fail loud). Subscription is idle.
    byo_lane = declared_source not in _RUNTIME_BACKED_SOURCES and declared_source != "subscription"
    if byo_lane and scan.capacity_kinds:
        # A BYO key exists syntactically. It is EXECUTABLE only when ALL hold:
        #   (F3) the vault-encryption gate is on (else the path is DARK), AND
        #   (F1) the provider is BYO-executable (claude-code; codex BYO is idle), AND
        #   (F4) the key passes provider-specific auth-health (not just non-empty).
        if not byo_execution_enabled():
            reason = (
                "a BYO API key is present but hosted BYO execution is not "
                "enabled — vault encryption (KMS / external secret manager) is "
                "required first; run the daemon on your own device to use your "
                "key now"
            )
        else:
            healthy: set[str] = set()
            try:
                for provider in scan.eligible_providers:
                    if provider not in _EXECUTABLE_BYO_PROVIDERS:
                        continue  # codex BYO is declared-not-executable (F1)
                    if _byo_key_auth_health(provider, udir) == "ok":
                        healthy.add(provider)
            except (ValueError, OSError) as exc:
                # Fable F6: the auth-health hook re-reads the vault; a JSON or I/O
                # error there must be a loud-but-caught misconfiguration too, not
                # a get_status/supervisor crash.
                raise EngineMisconfiguredError(
                    universe_id, declared_source or "byo_api_key",
                    f"credential vault is unreadable: {exc}",
                ) from exc
            if healthy:
                return EngineBinding(
                    bound=True,
                    engine_source=declared_source,
                    capacity_kinds=("byo_api_key",),
                    reason="bound to byo_api_key (" + ", ".join(sorted(healthy)) + ")",
                    eligible_providers=frozenset(healthy),
                    vault_providers=frozenset(healthy),
                )
            # A syntactically-present BYO key that is not executable: codex-only
            # (idle by F1) or a claude key that failed the format check (a real
            # network auth-health probe is Phase 2).
            reason = (
                "a BYO API key is present but not executable: Codex BYO needs "
                "unmet sandboxing, and an Anthropic key must be a well-formed "
                "sk-ant- key (format check; live auth-health is Phase 2) — re-bind"
            )
        return EngineBinding(
            bound=False, engine_source=declared_source,
            capacity_kinds=(), reason=reason,
        )

    # No usable BYO capacity. A present-but-unusable BYO row is genuinely broken
    # → fail loud (Hard Rule #8) so the broken key is re-bound — but ONLY when the
    # BYO lane is the selected one (a runtime-backed universe's stray broken key is
    # irrelevant to its declared lane).
    if byo_lane and scan.has_unusable_vault_source:
        raise EngineMisconfiguredError(
            universe_id,
            declared_source or "byo_api_key",
            "a BYO API key is in the vault but is not usable / not "
            "per-universe-consumable (re-bind via universe action=set_engine)",
        )

    # A DECLARED byo_api_key with no key at all is genuinely broken → fail loud.
    if declared_source == "byo_api_key":
        raise EngineMisconfiguredError(
            universe_id, declared_source,
            "no usable BYO API key in the per-universe vault",
        )

    if declared_source == "subscription":
        reason = (
            "engine_source='subscription' is a retired lane (platform never "
            "custodies subscription tokens) — re-bind via a sanctioned engine"
        )
    elif declared_source in _RUNTIME_BACKED_SOURCES:
        reason = (
            f"engine_source={declared_source!r} is a declared choice — "
            "hosted / market-rented / self-hosted execution routing is not "
            "available yet; bind a BYO API key to run now"
        )
    else:
        reason = "no engine capacity bound to this universe"
    return EngineBinding(
        bound=False,
        engine_source=declared_source,
        capacity_kinds=(),
        reason=reason,
    )
