"""Broker-backed engine binding and non-ambient execution gates.

The encrypted credential broker is the sole credential source.  This module
projects its non-secret bindings into the S5 routing contract and pins the
selected binding's ref/version across one routing-to-spawn operation.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tinyassets.credential_broker import (
    BINDING_STATUS_ACTIVE,
    BINDING_STATUS_NEEDS_REDEPOSIT,
    BINDING_STATUS_REVOKED,
    ENGINE_DESTINATION,
    ENGINE_PURPOSE,
    MIGRATION_MARKER_FILENAME,
    LegacyCredentialVaultError,
    list_bindings,
    platform_backend,
    require_no_legacy_vault,
)
from tinyassets.credentials import (
    CredentialUnavailable,
    SecretBinding,
    SecretKind,
)
from tinyassets.credentials import byo_execution_enabled as core_byo_execution_enabled

NON_AMBIENT_WORK_ENV = "TINYASSETS_NON_AMBIENT_WORK"
BYO_VAULT_ENCRYPTED_ENV = "TINYASSETS_BYO_VAULT_ENCRYPTED"
EXTERNAL_CAPACITY_PENDING_REASON = "no_eligible_external_daemon"

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_KNOWN_ENGINE_SOURCES = frozenset(
    {
        "byo_api_key",
        "self_hosted_endpoint",
        "market_rented",
        "host_daemon",
        "subscription",
    }
)
_RUNTIME_BACKED_SOURCES = frozenset(
    {"host_daemon", "market_rented", "self_hosted_endpoint"}
)
_SERVICE_TO_PROVIDER = {
    "anthropic": "claude-code",
    "claude": "claude-code",
    "claude-code": "claude-code",
    "openai": "codex",
    "codex": "codex",
}
# The approved S5 slice keeps Codex BYO dark until its sandbox path exists.
_EXECUTABLE_BYO_PROVIDERS = frozenset({"claude-code"})


class EngineMisconfiguredError(RuntimeError):
    """A declared engine cannot be resolved safely."""

    def __init__(self, universe_id: str, engine_source: str, detail: str) -> None:
        self.universe_id = universe_id
        self.engine_source = engine_source
        self.detail = detail
        super().__init__(
            f"universe {universe_id!r} declares engine_source={engine_source!r} "
            f"but its capacity is misconfigured: {detail}"
        )


class RetiredCredentialStateError(RuntimeError):
    """Terminal: a retired/unreadable credential state must not fall back."""


@dataclass(frozen=True)
class EngineBinding:
    bound: bool
    engine_source: str
    capacity_kinds: tuple[str, ...]
    reason: str
    eligible_providers: frozenset[str] = frozenset()
    vault_providers: frozenset[str] = frozenset()
    needs_record_migration: bool = False
    retired_needs_rebind: bool = False

    @property
    def needs_migration(self) -> bool:
        return self.needs_record_migration or self.retired_needs_rebind

    @property
    def external_route_declared(self) -> bool:
        return self.engine_source in _RUNTIME_BACKED_SOURCES

    def is_eligible_for(self, provider_name: str) -> bool:
        return self.bound and provider_name.strip() in self.eligible_providers

    def serves_via_vault(self, provider_name: str) -> bool:
        return provider_name.strip() in self.vault_providers

    def as_dict(self) -> dict[str, Any]:
        return {
            "bound": self.bound,
            "engine_source": self.engine_source,
            "capacity_kinds": list(self.capacity_kinds),
            "reason": self.reason,
            "eligible_providers": sorted(self.eligible_providers),
            "vault_providers": sorted(self.vault_providers),
            "needs_migration": self.needs_migration,
            "needs_record_migration": self.needs_record_migration,
            "retired_needs_rebind": self.retired_needs_rebind,
        }


def non_ambient_work_enabled() -> bool:
    return os.environ.get(NON_AMBIENT_WORK_ENV, "").strip().lower() in _TRUTHY


def _raw_config(universe_dir: Path, universe_id: str) -> dict[str, Any]:
    config_path = universe_dir / "config.yaml"
    if not config_path.is_file():
        return {}
    try:
        import yaml

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise EngineMisconfiguredError(
            universe_id, "", f"config.yaml is unreadable: {exc}"
        ) from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise EngineMisconfiguredError(
            universe_id, "", "config.yaml is not a mapping"
        )
    return raw


def byo_lane_selected(universe_dir: str | Path) -> bool:
    udir = Path(universe_dir)
    try:
        source = str(
            _raw_config(udir, udir.name or "default-universe").get(
                "engine_source", ""
            )
            or ""
        ).strip()
    except EngineMisconfiguredError:
        return False
    return source in ("", "byo_api_key")


def _engine_rows(universe_dir: Path) -> list[tuple[SecretBinding, str]]:
    rows = list_bindings(universe_dir.name, purpose=ENGINE_PURPOSE)
    return [
        (binding, status)
        for binding, status in rows
        if binding.scope.destination == ENGINE_DESTINATION
    ]


def _active_byo_bindings(universe_dir: Path) -> list[SecretBinding]:
    return [
        binding
        for binding, status in _engine_rows(universe_dir)
        if status == BINDING_STATUS_ACTIVE
        and binding.kind == SecretKind.API_KEY
        and binding.scope.provider in _SERVICE_TO_PROVIDER
    ]


def _sandbox_execution_attested() -> bool:
    """Phase-1 default: no hosted BYO execution before the isolated runner."""
    return False


def _vault_encryption_capability_attested(
    universe_dir: str | Path | None = None,
) -> bool:
    """Attest the exact broker record, never a global storage capability."""
    if universe_dir is None:
        return False
    try:
        backend = platform_backend()
        return any(
            core_byo_execution_enabled(backend, binding, auth_health=True)
            for binding in _active_byo_bindings(Path(universe_dir))
        )
    except (CredentialUnavailable, LegacyCredentialVaultError, OSError):
        return False


def _byo_execution_enabled_uncached(
    universe_dir: str | Path | None = None,
) -> bool:
    if os.environ.get(BYO_VAULT_ENCRYPTED_ENV, "").strip().lower() not in _TRUTHY:
        return False
    if not _sandbox_execution_attested():
        return False
    return _vault_encryption_capability_attested(universe_dir)


def _binding_digest(universe_dir: Path, provider_name: str | None = None) -> str | None:
    """Hash the selected opaque ref + authenticated record version.

    No credential bytes enter the digest or logs. A replacement increments the
    backend version; deletion makes the lookup fail, so either change is visible
    to the routing-to-spawn TOCTOU check.
    """
    candidates = []
    for binding in _active_byo_bindings(universe_dir):
        provider = _SERVICE_TO_PROVIDER[binding.scope.provider]
        if provider_name is None or provider == provider_name.strip():
            candidates.append(binding)
    if not candidates:
        return None
    candidates.sort(key=lambda binding: binding.ref)
    backend = platform_backend()
    parts: list[str] = []
    for binding in candidates:
        with backend.get(binding, binding.scope) as lease:
            parts.append(f"{binding.ref}:{lease.version}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def byo_credential_digest(
    universe_dir: str | Path,
    provider_name: str | None = None,
) -> str | None:
    return _binding_digest(Path(universe_dir), provider_name)


@dataclass(frozen=True)
class ByoExecutionSnapshot:
    enabled: bool
    universe_dir: str | None = None
    credential_digest: str | None = None


_BYO_EXECUTION_SNAPSHOT: ContextVar[ByoExecutionSnapshot | None] = ContextVar(
    "byo_execution_snapshot", default=None
)


def _compute_byo_snapshot(
    universe_dir: str | Path | None,
) -> ByoExecutionSnapshot:
    enabled = _byo_execution_enabled_uncached(universe_dir)
    universe_text = str(Path(universe_dir)) if universe_dir is not None else None
    digest = None
    if enabled and universe_dir is not None and byo_lane_selected(universe_dir):
        try:
            digest = _binding_digest(Path(universe_dir))
        except (CredentialUnavailable, LegacyCredentialVaultError, OSError):
            digest = None
    return ByoExecutionSnapshot(enabled, universe_text, digest)


@contextlib.contextmanager
def pin_byo_execution_snapshot(universe_dir: str | Path | None = None):
    current = _BYO_EXECUTION_SNAPSHOT.get()
    snapshot = _compute_byo_snapshot(universe_dir) if current is None else current
    token = _BYO_EXECUTION_SNAPSHOT.set(snapshot)
    try:
        yield snapshot
    finally:
        _BYO_EXECUTION_SNAPSHOT.reset(token)


def get_pinned_byo_snapshot() -> ByoExecutionSnapshot | None:
    return _BYO_EXECUTION_SNAPSHOT.get()


def byo_execution_enabled(universe_dir: str | Path | None = None) -> bool:
    pinned = _BYO_EXECUTION_SNAPSHOT.get()
    if pinned is not None:
        return pinned.enabled
    return _byo_execution_enabled_uncached(universe_dir)


def _retired_binding(rows: list[tuple[SecretBinding, str]]) -> bool:
    return any(
        status in {BINDING_STATUS_NEEDS_REDEPOSIT, BINDING_STATUS_REVOKED}
        for _binding, status in rows
    )


def resolve_engine_binding(universe_dir: str | Path) -> EngineBinding:
    udir = Path(universe_dir)
    universe_id = udir.name or "default-universe"
    raw = _raw_config(udir, universe_id)
    source = str(raw.get("engine_source") or "").strip()
    if source and source not in _KNOWN_ENGINE_SOURCES:
        raise EngineMisconfiguredError(
            universe_id,
            source,
            f"unknown engine_source — expected one of {sorted(_KNOWN_ENGINE_SOURCES)}",
        )

    marker = (udir / MIGRATION_MARKER_FILENAME).is_file()
    try:
        require_no_legacy_vault(udir)
    except LegacyCredentialVaultError as exc:
        return EngineBinding(
            False,
            source,
            (),
            f"needs_record_migration: {exc}",
            needs_record_migration=True,
        )

    try:
        rows = _engine_rows(udir)
    except CredentialUnavailable as exc:
        raise EngineMisconfiguredError(
            universe_id,
            source or "byo_api_key",
            f"credential binding registry is unreadable [{exc.code}]",
        ) from exc

    if source in _RUNTIME_BACKED_SOURCES or source == "subscription":
        reason = (
            f"engine_source={source!r} is declared but its executor route is not "
            "available in this slice"
        )
        return EngineBinding(False, source, (), reason)

    active = _active_byo_bindings(udir)
    providers = {
        _SERVICE_TO_PROVIDER[binding.scope.provider] for binding in active
    }
    executable = providers & _EXECUTABLE_BYO_PROVIDERS

    if active:
        if not byo_execution_enabled(udir):
            binding = EngineBinding(
                False,
                source,
                (),
                "a broker-backed BYO credential is present but executable BYO "
                "is not fully attested (operator opt-in, encrypted record, and "
                "sandbox must all pass)",
            )
        elif not executable:
            binding = EngineBinding(
                False,
                source,
                (),
                "the deposited credential has no executable BYO provider in this slice",
            )
        else:
            binding = EngineBinding(
                True,
                source,
                ("byo_api_key",),
                "bound to broker-backed byo_api_key ("
                + ", ".join(sorted(executable))
                + ")",
                frozenset(executable),
                frozenset(executable),
            )
        if marker and not binding.bound:
            return EngineBinding(
                False,
                source,
                (),
                "retired_needs_rebind: migrated credentials cannot execute until "
                "a sanctioned replacement binding is fully attested",
                retired_needs_rebind=True,
            )
        return binding

    if source == "byo_api_key":
        if _retired_binding(rows) or marker:
            return EngineBinding(
                False,
                source,
                (),
                "retired_needs_rebind: the legacy value was removed; deposit a "
                "new sanctioned credential",
                retired_needs_rebind=True,
            )
        raise EngineMisconfiguredError(
            universe_id, source, "no active broker-backed BYO credential"
        )

    if marker or _retired_binding(rows):
        return EngineBinding(
            False,
            source,
            (),
            "retired_needs_rebind: migration is complete; bind a sanctioned engine",
            retired_needs_rebind=True,
        )
    return EngineBinding(False, source, (), "no engine capacity bound to this universe")


def execution_blocked_reason(universe_dir: str | Path | None) -> str | None:
    if universe_dir is None:
        return None
    binding = resolve_engine_binding(universe_dir)
    if binding.bound:
        return None
    if binding.external_route_declared:
        return (
            f"{EXTERNAL_CAPACITY_PENDING_REASON}: the declared external daemon "
            "route has no owner-authorized or market lease; job remains pending"
        )
    if binding.needs_migration:
        return (
            "retired or unmigrated credential state is not rebound to a sanctioned "
            "engine; refusing ambient host credentials"
        )
    return None
