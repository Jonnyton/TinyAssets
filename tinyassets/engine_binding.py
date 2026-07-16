"""Per-universe engine-capacity binding resolver + the non-ambient-work flag.

The honest "can this universe run?" predicate. A universe executes work only on
capacity **explicitly bound to it** (design note 2026-07-15 gap G7): the owner's
own engine (BYO API key or subscription CLI), a self-hosted endpoint,
market-rented / offered cloud capacity, or a hosted daemon the founder chose. No
ambient, unbound daemon work — a fresh universe with no bind act is honestly
idle-until-bound.

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

#: Env flag that arms the non-ambient work gate. DEFAULT OFF (unset) = today's
#: behavior. See :func:`non_ambient_work_enabled`.
NON_AMBIENT_WORK_ENV = "TINYASSETS_NON_AMBIENT_WORK"

_TRUTHY = {"1", "true", "yes", "on"}


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
# feeds (the names in providers.router.FALLBACK_CHAINS). ``ANY_PROVIDER`` is the
# wildcard for a generic runtime that declares no specific provider.
ANY_PROVIDER = "*"

_SERVICE_TO_PROVIDER: dict[str, str] = {
    # Anthropic / Claude family → the claude-code CLI writer.
    "anthropic": "claude-code",
    "claude": "claude-code",
    "claude-code": "claude-code",
    # OpenAI / Codex family → the codex CLI writer.
    "openai": "codex",
    "codex": "codex",
    # API-key HTTP free-tier providers (writer-chain names).
    "gemini": "gemini-free",
    "google": "gemini-free",
    "groq": "groq-free",
    "xai": "grok-free",
    "grok": "grok-free",
}


@dataclass(frozen=True)
class EngineBinding:
    """Resolved engine-capacity binding for one universe.

    ``bound`` is the load-bearing field: True when the universe has at least one
    real, usable capacity bound to it. ``capacity_kinds`` names each capacity
    found (e.g. ``("byo_api_key",)`` / ``("subscription:claude",)`` /
    ``("runtime:host_daemon",)``). ``engine_source`` echoes the founder's declared
    choice from ``config.yaml`` (empty when none was declared).

    ``eligible_providers`` names the writer providers this capacity can actually
    serve — the gate is provider-level, not universe-level, so a Codex-pinned
    worker treats a claude-only universe as idle-until-bound. ``ANY_PROVIDER``
    (``"*"``) in the set means a generic runtime that can serve any provider.
    ``vault_providers`` is the subset whose auth is per-universe VAULT auth that
    the child materializes at spawn — the pre-spawn global-auth quarantine must
    be skipped for these (they don't need process-global provider auth).
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
        if ANY_PROVIDER in self.eligible_providers:
            return True
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


def _raw_config(universe_dir: Path) -> dict[str, Any]:
    """Return the raw ``config.yaml`` mapping (or ``{}``), best-effort.

    Read raw rather than via :func:`tinyassets.config.load_universe_config` so we
    can tell a DECLARED ``engine_source`` (explicit key present) apart from the
    dataclass default — the default ``byo_api_key`` must never read as a bind
    act on a fresh universe.
    """
    cfg_file = Path(universe_dir) / "config.yaml"
    if not cfg_file.is_file():
        return {}
    try:
        import yaml

        data = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a bad config.yaml is not a vault secret
        logger.warning("engine_binding: config.yaml unreadable at %s", cfg_file)
        return {}
    return data if isinstance(data, dict) else {}


# Engine sources that persist only a config CHOICE — the runtime that actually
# consumes work is provisioned separately (``universe action=daemon_summon`` for
# host_daemon, a matched market runtime for market_rented, a wired endpoint route
# for self_hosted_endpoint; the deeper routing is post-M1 per PLAN §config.py).
# A choice with no live runtime is NOT executable capacity — it reads as
# idle-until-bound, never bound.
_RUNTIME_BACKED_SOURCES = frozenset(
    {"host_daemon", "market_rented", "self_hosted_endpoint"}
)

# The ONLY runtime-instance status that proves the worker can execute work now.
# `paused` and `restart_requested` are control states (daemon_registry
# RUNTIME_CONTROL_STATUSES) with no active-execution contract, so a universe
# whose only runtime is paused/restart_requested must read as idle-until-bound —
# the gate must not spawn for it. `resume` writes `provisioned`, so recovery is
# automatic once a paused daemon is resumed.
_EXECUTABLE_RUNTIME_STATUSES = frozenset({"provisioned"})


def _codex_auth_b64_valid(auth_json_b64: str) -> bool:
    """Return True iff *auth_json_b64* strictly decodes to a JSON Codex auth.json.

    Strict base64 (``validate=True`` rejects non-alphabet chars like ``!``) +
    a JSON parse of the decoded bytes. A lenient decode would silently accept
    garbage like ``"not-base64!"`` and materialize a broken auth.json, so the
    subscription would fall through to platform/global provider auth.
    """
    import base64
    import binascii
    import json as _json

    try:
        raw = base64.b64decode(auth_json_b64, validate=True)
    except (binascii.Error, ValueError):
        return False
    try:
        _json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False
    return True


def _subscription_row_usable(universe_dir: Path, record: dict[str, Any], svc: str) -> bool:
    """Return True iff a subscription vault row carries usable, materializable auth.

    A row's mere presence is NOT capacity — the credential must be consumable by
    the CLI-subprocess provider, else provider routing silently falls back to
    platform/global auth (the exact failure Codex flagged). Claude needs an OAuth
    token or a resolvable config dir; Codex needs a strictly-valid ``auth_json_b64``
    or a resolvable CODEX_HOME with an ``auth.json``.
    """
    from tinyassets.credential_vault import (
        resolve_claude_config_dir,
        resolve_codex_home,
    )

    if svc in {"claude", "anthropic", "claude-code"}:
        token = str(
            record.get("oauth_token") or record.get("claude_code_oauth_token") or ""
        ).strip()
        if token:
            return True
        # A configured config-dir path is NOT enough — credential_vault returns
        # configured paths without checking they exist. Require an EXISTING,
        # populated dir (holds the auth artifact) so a dangling pointer never
        # reads as usable and falls through to global auth.
        cfg = resolve_claude_config_dir(universe_dir)
        try:
            return bool(cfg and cfg.is_dir() and any(cfg.iterdir()))
        except OSError:
            return False
    if svc in {"codex", "openai"}:
        b64 = str(record.get("auth_json_b64") or "").strip()
        if b64 and _codex_auth_b64_valid(b64):
            return True
        home = resolve_codex_home(universe_dir)
        return bool(home and (home / "auth.json").is_file())
    # Unknown subscription service — we cannot prove it is materializable.
    return False


def _byo_row_usable(record: dict[str, Any], svc: str) -> bool:
    """Return True iff a BYO ``llm_api_key`` row maps to a known provider AND
    carries a non-empty, decodable secret.

    Counting a BYO row by ``credential_type`` alone lets a malformed vault (bad
    base64, missing key, or an unknown service that never reaches any provider)
    satisfy the gate and then fall through to other/global auth. Validate like
    bind time does.
    """
    from tinyassets.credential_vault import (
        _secret_value,
        supported_llm_api_key_services,
    )

    if svc not in supported_llm_api_key_services():
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
    """Scan the vault for USABLE BYO + subscription capacity.

    A row counts only when its credential is actually usable — a BYO key must map
    to a known provider with a decodable secret (:func:`_byo_row_usable`); a
    subscription row must carry materializable auth (:func:`_subscription_row_usable`).
    Unusable-but-declared vault sources set ``has_unusable_vault_source`` so the
    caller can fail loud instead of silently falling through to platform auth.
    Propagates :class:`ValueError` (malformed vault) so the caller can fail loud.
    """
    from tinyassets.credential_vault import load_credential_vault

    records = load_credential_vault(universe_dir)  # raises ValueError if malformed
    kinds: list[str] = []
    eligible: set[str] = set()
    vault_providers: set[str] = set()
    has_unusable = False
    for record in records:
        ctype = record.get("credential_type")
        svc = str(record.get("service") or record.get("provider") or "").strip().lower()
        if ctype == "llm_api_key":
            if _byo_row_usable(record, svc):
                kinds.append("byo_api_key")
                provider = _SERVICE_TO_PROVIDER.get(svc)
                if provider:
                    eligible.add(provider)
                    vault_providers.add(provider)
            else:
                has_unusable = True
        elif ctype == "llm_subscription":
            if _subscription_row_usable(universe_dir, record, svc):
                kinds.append(f"subscription:{svc}" if svc else "subscription")
                provider = _SERVICE_TO_PROVIDER.get(svc)
                if provider:
                    eligible.add(provider)
                    vault_providers.add(provider)
            else:
                has_unusable = True
    return _VaultScan(kinds, eligible, vault_providers, has_unusable)


def _live_runtime_providers(universe_dir: Path) -> set[str]:
    """Return the providers served by PROVISIONED runtime instances (or empty).

    Only :data:`_EXECUTABLE_RUNTIME_STATUSES` count — `paused` / `restart_requested`
    / retired runtimes are not executable. Each provisioned instance contributes
    its declared ``provider_name``; a runtime with no declared provider is a
    generic daemon and contributes :data:`ANY_PROVIDER`. A missing / uninitialized
    registry degrades to an empty set (idle-until-bound) and never raises.
    """
    try:
        from tinyassets.daemon_server import list_runtime_instances

        instances = list_runtime_instances(
            universe_dir.parent, universe_id=universe_dir.name,
        )
    except Exception:  # noqa: BLE001 — no DB / no table = no assigned runtime
        return set()
    providers: set[str] = set()
    for inst in instances:
        if str(inst.get("status") or "").strip().lower() not in _EXECUTABLE_RUNTIME_STATUSES:
            continue
        provider = str(inst.get("provider_name") or "").strip()
        providers.add(provider or ANY_PROVIDER)
    return providers


def resolve_engine_binding(universe_dir: str | Path) -> EngineBinding:
    """Inspect a universe's vault + config to resolve its bound engine capacity.

    Reads only the primitives the bind acts already write (the credential vault
    and ``config.yaml``) — no parallel capacity store.

    Returns an :class:`EngineBinding`. ``bound`` is True ONLY when the worker can
    actually execute the universe:

    * a vault-backed BYO ``llm_api_key`` or ``llm_subscription`` (provider
      routing consumes these directly), or
    * a config-declared runtime-backed source (``host_daemon`` /
      ``market_rented`` / ``self_hosted_endpoint``) that has a live, non-retired
      runtime instance assigned to the universe.

    A config CHOICE with no runtime yet, and a fresh universe with no bind act,
    both return ``bound=False`` (idle-until-bound) — quietly. This split matters:
    a bare ``engine_source: host_daemon`` value with no summoned daemon is NOT
    executable capacity, so the non-ambient gate must not spawn for it.

    Raises :class:`EngineMisconfiguredError` only when a **vault-backed** source
    (``byo_api_key`` / ``subscription``) was declared but its credential is
    absent — those bind acts deposit the credential atomically, so a declared
    vault source with no credential is genuinely broken (Hard Rule #8: fail loud,
    never treat a broken binding as merely unbound). A malformed vault is
    likewise loud.
    """
    udir = Path(universe_dir)
    universe_id = udir.name or "default-universe"
    raw = _raw_config(udir)
    declared_source = str(raw.get("engine_source") or "").strip()

    try:
        scan = _vault_capacity(udir)
    except ValueError as exc:
        raise EngineMisconfiguredError(
            universe_id,
            declared_source or "byo_api_key",
            f"credential vault is unreadable: {exc}",
        ) from exc
    capacity: list[str] = list(scan.capacity_kinds)
    eligible: set[str] = set(scan.eligible_providers)
    vault_providers: set[str] = set(scan.vault_providers)

    # Config-declared runtime-backed sources are executable ONLY with a live
    # runtime instance assigned to the universe (the config value alone is a
    # choice, not capacity). A missing runtime is idle-until-bound, not an error.
    # Each provisioned runtime contributes the provider it declares to eligibility
    # (a generic daemon contributes ANY_PROVIDER).
    if declared_source in _RUNTIME_BACKED_SOURCES:
        runtime_providers = _live_runtime_providers(udir)
        if runtime_providers:
            capacity.append(f"runtime:{declared_source}")
            eligible |= runtime_providers

    # Deduplicate while preserving discovery order.
    capacity = list(dict.fromkeys(capacity))

    if capacity:
        return EngineBinding(
            bound=True,
            engine_source=declared_source,
            capacity_kinds=tuple(capacity),
            reason="bound to " + ", ".join(capacity),
            eligible_providers=frozenset(eligible),
            vault_providers=frozenset(vault_providers),
        )

    # A vault source (BYO or subscription) is present but not usable, and nothing
    # else backs this universe. Counting it as bound would let the daemon spawn
    # and silently fall through to platform/global provider auth — fail loud
    # instead (Hard Rule #8) so the broken credential is re-bound.
    if scan.has_unusable_vault_source:
        raise EngineMisconfiguredError(
            universe_id,
            declared_source or "vault",
            "a BYO/subscription credential is in the vault but is not "
            "usable/materializable (re-bind via universe action=set_engine)",
        )

    # No executable capacity. A DECLARED vault-backed source with no credential
    # is genuinely broken → fail loud. A declared runtime-backed source with no
    # runtime yet is a legitimate not-yet-provisioned state → idle-until-bound.
    if declared_source in {"byo_api_key", "subscription"}:
        detail = {
            "byo_api_key": (
                "no BYO API key or subscription credential in the per-universe "
                "vault"
            ),
            "subscription": "no subscription credential in the per-universe vault",
        }[declared_source]
        raise EngineMisconfiguredError(universe_id, declared_source, detail)

    reason = (
        f"engine_source={declared_source!r} chosen but no runtime instance is "
        "assigned yet"
        if declared_source
        else "no engine capacity bound to this universe"
    )
    return EngineBinding(
        bound=False,
        engine_source=declared_source,
        capacity_kinds=(),
        reason=reason,
    )
