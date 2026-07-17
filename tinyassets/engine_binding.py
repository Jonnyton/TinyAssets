"""Per-universe engine-capacity binding resolver + the non-ambient-work flag.

The honest "can this universe run?" predicate. A universe executes work only on
capacity **explicitly bound to it** (2026-07-02 credential-custody research §0/§4;
non-ambient work gate). The
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

import contextlib
import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass, field
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
    #: Round-21 #4: TWO distinct retired states with DIFFERENT remediations —
    #: conflating them told operators to re-run an already-completed migration.
    #: * ``needs_record_migration`` — a RAW ``llm_subscription`` record is still
    #:   present; the host must run the record-removal migration to strip it.
    #: * ``retired_needs_rebind`` — the raw record was already removed (a non-secret
    #:   marker remains); the migration is DONE, the founder must RE-BIND a sanctioned
    #:   engine. Both fail closed (never ambient host creds); ``needs_migration`` is the
    #:   umbrella "retired / not workable" derived from either.
    needs_record_migration: bool = False
    retired_needs_rebind: bool = False

    @property
    def needs_migration(self) -> bool:
        """Umbrella "retired / not workable" — True for EITHER retired state. Kept for
        the workable computation + backward compatibility; the specific remediation
        reads the two distinct fields above (round-21 #4)."""
        return self.needs_record_migration or self.retired_needs_rebind

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
            "needs_migration": self.needs_migration,
            "needs_record_migration": self.needs_record_migration,
            "retired_needs_rebind": self.retired_needs_rebind,
        }


def execution_blocked_reason(universe_dir: str | Path | None) -> str | None:
    """THE single fail-closed security gate (round-22 #1/#2): return a block reason if
    *universe_dir* must NOT execute on ambient host credentials, else ``None``.

    This is the invariant enforced at EVERY execution chokepoint — the graph-execution
    entry (:func:`tinyassets.runs._invoke_graph` / ``_invoke_graph_resume``) and the
    provider router (:func:`tinyassets.providers.router._preflight_retired_universe`) —
    so no caller can reach a provider for a blocked universe regardless of feature
    flags, thread hops, or whether a node threaded context.

    Blocks (fail closed) when the universe's credential state is RETIRED or UNREADABLE
    (:func:`credential_vault.credential_state_blocks_ambient_execution`, strict) AND it
    is not re-bound to a sanctioned engine. A retired universe RE-BOUND with a
    sanctioned engine (``resolve_engine_binding().bound``) runs on its OWN identity and
    is allowed. Any error confirming a clean re-bind keeps the universe BLOCKED. A
    ``None`` universe / a clean fresh universe returns ``None`` (may run — the
    single-tenant host-global default)."""
    if universe_dir is None:
        return None
    from tinyassets.credential_vault import (
        credential_state_blocks_ambient_execution,
    )

    if not credential_state_blocks_ambient_execution(universe_dir):
        return None
    # Blocked credential state — allow ONLY a clean, sanctioned re-bind (own identity).
    try:
        if resolve_engine_binding(universe_dir).bound:
            return None
    except Exception:  # noqa: BLE001 — cannot confirm a clean re-bind → stay BLOCKED.
        pass
    return (
        "retired-or-unreadable credential state: this universe's subscription lane was "
        "retired (or its credential vault is unreadable) and it is not re-bound to a "
        "sanctioned engine — refusing to execute on the host's ambient identity. "
        "Re-bind a sanctioned engine via write_graph target=engine."
    )


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


def _vault_encryption_capability_attested(universe_dir: str | Path | None = None) -> bool:
    """Per-record proof that the SELECTED vault secret is REAL-encrypted. DEFAULT False.

    Round-14 #4 (adopt the vault's ``byo_execution_enabled(binding)`` contract): a
    GLOBAL boolean cannot honor a *per-record* promise — it can't verify that THE
    specific secret about to be used is envelope-encrypted + correctly scoped. So
    this now TAKES the record context (``universe_dir``, the binding locus) even
    though Phase-1 returns False unconditionally. The Phase-2 implementation must,
    given the universe/record, verify that record's ciphertext + key reference
    decrypt under a per-tenant DEK — NOT merely that a KMS is globally reachable.

    The current vault stores keys plaintext-base64, so a truthy env flag alone must
    NEVER unlock deposit+execution of plaintext keys (C4). Tests simulate Phase-2
    by monkeypatching this to return True.
    """
    return False  # Phase 2: implement real per-record envelope encryption here.


def _sandbox_execution_attested() -> bool:
    """Proof that OS-level sandbox isolation is READY for BYO execution. DEFAULT False.

    Round-14 #2 + #4: a founder's BYO key must not run until the per-job runner
    (real OS isolation — container/namespace, separate working dir) attests it is
    ready. Until then BYO execution is genuinely DARK, which makes the interim CLI
    file-access surface (``--bare`` still permits Read/Edit) UNREACHABLE. The
    runner build wires this to a live probe; here it is hardcoded False so no flag
    combination can enable BYO execution without sandbox attestation.
    """
    return False  # Phase 2: wire to the per-job runner's sandbox-readiness probe.


@dataclass(frozen=True)
class ByoExecutionSnapshot:
    """The IMMUTABLE binding pinned across ONE routing→spawn operation (round-16 #1).

    Route selection (the router's writer-binding enforcement) and the subprocess
    spawn (:func:`tinyassets.providers.base.subprocess_env_for_provider`) both run
    inside :func:`pin_byo_execution_snapshot`. The pin captures not just the
    boolean attestation but the SELECTED credential's identity+version
    (``credential_digest``) at route time. The spawn recomputes the digest and
    FAILS CLOSED if it changed or disappeared — closing the routing→spawn TOCTOU
    where the ambient platform token could survive if the BYO credential was
    deleted in the interval. ``universe_dir`` is the record locus (round-15 #2).
    """

    enabled: bool
    universe_dir: str | None = None
    credential_digest: str | None = None


#: Round-12 #3 / round-16 #1 (attestation + credential TOCTOU). Route selection and
#: the subprocess spawn BOTH consult the pinned snapshot. The router wraps its
#: chain-selection + the awaited ``provider.complete`` in
#: :func:`pin_byo_execution_snapshot`, so every read inside that one routing
#: operation resolves to the SAME immutable binding. ``None`` = not pinned
#: (standalone callers recompute live).
_BYO_EXECUTION_SNAPSHOT: ContextVar[ByoExecutionSnapshot | None] = ContextVar(
    "byo_execution_snapshot", default=None,
)


def _byo_execution_enabled_uncached(universe_dir: str | Path | None = None) -> bool:
    """Live read of the executable-BYO prerequisite. ALL must hold (round-14 #4):
    operator opt-in flag AND sandbox-readiness attestation (round-14 #2) AND the
    selected record's per-record encryption attestation. Any False → BYO dark."""
    if os.environ.get(BYO_VAULT_ENCRYPTED_ENV, "").strip().lower() not in _TRUTHY:
        return False
    if not _sandbox_execution_attested():
        return False
    return _vault_encryption_capability_attested(universe_dir)


def _compute_byo_snapshot(universe_dir: str | Path | None) -> ByoExecutionSnapshot:
    """Capture the immutable routing-time binding: attestation + the SELECTED BYO
    credential's identity+version (round-16 #1), BOUND TO THE RESOLVED LANE
    (round-17 #4).

    The digest is captured ONLY when the resolved engine lane is the BYO-key lane
    (:func:`byo_lane_selected` — an undeclared universe or explicit
    ``engine_source=byo_api_key``). A RETAINED Anthropic key on a universe switched
    to a NON-BYO lane (``self_hosted_endpoint`` / ``market_rented`` / ``host_daemon``)
    is NOT a selected BYO route, so no digest is pinned — otherwise the spawn
    (:func:`tinyassets.providers.base.subprocess_env_for_provider`) would read the
    pinned digest as a selected BYO route, scrub ambient auth, fail to inject the key
    (the lane-aware overlay declines a non-BYO lane), and crash the spawn (round-17
    #4 reproduction). The digest already encodes the credential's identity+version
    (a content hash of the resolved key); gating its capture on the lane binds the
    snapshot to lane + provider (claude-code / ANTHROPIC_API_KEY) + record.
    """
    enabled = _byo_execution_enabled_uncached(universe_dir)
    udir_str = str(Path(universe_dir)) if universe_dir is not None else None
    digest: str | None = None
    if enabled and universe_dir is not None and byo_lane_selected(universe_dir):
        try:
            from tinyassets.credential_vault import byo_credential_digest

            digest = byo_credential_digest(universe_dir)
        except Exception:  # noqa: BLE001 — no resolvable credential ⇒ no binding
            digest = None
    return ByoExecutionSnapshot(
        enabled=enabled, universe_dir=udir_str, credential_digest=digest,
    )


@contextlib.contextmanager
def pin_byo_execution_snapshot(universe_dir: str | Path | None = None):
    """Pin ONE immutable BYO binding for a routing operation (round-12 #3 +
    round-15 #2 + round-16 #1).

    The router enters this around its chain-selection + the awaited
    ``provider.complete`` so route-time and spawn-time reads can never disagree —
    not on the attestation boolean (round-12), not on the record context
    (round-15), and not on the credential's identity+version (round-16). A nested
    pin reuses the outermost binding — the first decision governs the operation.
    """
    current = _BYO_EXECUTION_SNAPSHOT.get()
    snapshot = _compute_byo_snapshot(universe_dir) if current is None else current
    token = _BYO_EXECUTION_SNAPSHOT.set(snapshot)
    try:
        yield snapshot
    finally:
        _BYO_EXECUTION_SNAPSHOT.reset(token)


def get_pinned_byo_snapshot() -> ByoExecutionSnapshot | None:
    """Return the immutable BYO binding pinned for the current routing operation,
    or ``None`` when not under a pin (standalone/direct callers). The spawn uses it
    to enforce the immutable-credential contract (round-16 #1)."""
    return _BYO_EXECUTION_SNAPSHOT.get()


def byo_execution_enabled(universe_dir: str | Path | None = None) -> bool:
    """Return whether the executable BYO-key path is enabled. DEFAULT OFF.

    Requires ALL of (round-14 #4, the vault's ``byo_execution_enabled(binding)``
    contract): operator opt-in (:data:`BYO_VAULT_ENCRYPTED_ENV`), sandbox-readiness
    attestation (:func:`_sandbox_execution_attested`, round-14 #2), and the SELECTED
    record's per-record encryption attestation
    (:func:`_vault_encryption_capability_attested`). Because sandbox + encryption
    attestation are both False until Phase-2, **the flag alone cannot unlock
    plaintext-key deposit+execution** (C4). OFF (this deploy) → the executable BYO
    path is DARK end-to-end: no deposit, no bound BYO, no direct BYO routing, no
    BYO env injection, no BYO subprocess execution.

    ``universe_dir`` threads the record locus to the per-record attestation. When a
    routing operation has pinned a snapshot (:func:`pin_byo_execution_snapshot`),
    returns that immutable value so route selection and subprocess spawn always
    agree (round-12 #3).
    """
    pinned = _BYO_EXECUTION_SNAPSHOT.get()
    if pinned is not None:
        return pinned.enabled
    return _byo_execution_enabled_uncached(universe_dir)


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


def byo_lane_selected(universe_dir: str | Path) -> bool:
    """Return True iff the universe's DECLARED engine lane is the BYO-key lane.

    Round-13 #2: the spawn-time credential overlay must be LANE-AWARE. The r12
    field-clear on a lane switch was not enough because
    :func:`tinyassets.credential_vault.provider_auth_env_overrides` re-reads the
    vault key INDEPENDENTLY of ``engine_source`` — so a universe switched from
    ``byo_api_key`` to ``market_rented`` (with the old key still in the vault)
    still got ``ANTHROPIC_API_KEY`` injected. A retained vault key is injectable
    ONLY when the selected lane is BYO.

    Round-15 #4 (FAIL CLOSED): the BYO lane is selected ONLY for an undeclared
    universe (``""`` = default lane) or an EXPLICIT ``engine_source=byo_api_key``.
    Every OTHER value — a runtime-backed lane, the retired ``subscription`` lane,
    OR an unknown/typo'd value (``attacker_typo``) — is NOT BYO. An allowlist, not
    a denylist: an unknown ``engine_source`` must never default into the
    credential-injecting path. A config read error also fails closed.
    """
    udir = Path(universe_dir)
    try:
        raw = _raw_config(udir, udir.name or "default-universe")
    except Exception:  # noqa: BLE001 — a broken config must not enable injection
        return False
    declared = str(raw.get("engine_source") or "").strip()
    return declared in ("", "byo_api_key")


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
    #: Round-18 #1: the subset of ``eligible_providers`` whose vault service is in
    #: the sanctioned-custody registry (default-deny at CONSUMPTION). ONLY these may
    #: bind + inject; a usable-but-UNSANCTIONED key is present capacity that can never
    #: become bound or enter a child env — including a legacy/manually-written record.
    sanctioned_eligible_providers: set[str] = field(default_factory=set)


def _vault_capacity(universe_dir: Path) -> _VaultScan:
    """Scan the vault for USABLE founder BYO-API-key capacity + its SANCTIONED subset.

    A BYO row is USABLE capacity when it is per-universe-consumable with a decodable
    secret (:func:`_byo_row_usable`); an unusable-but-declared BYO row sets
    ``has_unusable_vault_source`` so the caller can fail loud. Round-18 #1 tracks the
    SANCTIONED-eligible providers separately (service in
    :func:`credential_vault.sanctioned_custody_services`, default-deny): only these
    may bind + inject, so an attested legacy/manual record for an UNAPPROVED provider
    is present capacity that can never become bound (the caller reports it honestly,
    without a fail-loud "broken" error). Keeping the usable-vs-sanctioned split lets
    the caller report the accurate reason (execution-not-enabled vs custody-not-
    sanctioned) instead of conflating an unsanctioned key with a missing/broken one.

    ``llm_subscription`` vault rows are DELIBERATELY ignored: founder subscription
    custody is a BLOCKED lane (2026-07-02 custody research §0/§4). A legacy
    subscription row therefore reads as NOT founder capacity and never fails loud.
    Propagates :class:`ValueError` (malformed vault) so the caller can fail loud.
    """
    from tinyassets.credential_vault import (
        load_credential_vault,
        sanctioned_custody_services,
    )

    records = load_credential_vault(universe_dir)  # raises ValueError if malformed
    sanctioned = sanctioned_custody_services()
    kinds: list[str] = []
    eligible: set[str] = set()
    vault_providers: set[str] = set()
    sanctioned_eligible: set[str] = set()
    has_unusable = False
    for record in records:
        if record.get("credential_type") != "llm_api_key":
            continue  # llm_subscription (blocked lane), vcs, social → not engine capacity
        svc = str(record.get("service") or record.get("provider") or "").strip().lower()
        if not _byo_row_usable(record, svc):
            has_unusable = True
            continue
        kinds.append("byo_api_key")
        provider = _SERVICE_TO_PROVIDER.get(svc)
        if provider:
            eligible.add(provider)
            vault_providers.add(provider)
            # Round-18 #1: sanctioned-eligible = usable AND custody-approved. Only
            # these may bind/inject (matches the resolve_llm_api_key gate).
            if svc in sanctioned:
                sanctioned_eligible.add(provider)
    return _VaultScan(
        kinds, eligible, vault_providers, has_unusable, sanctioned_eligible,
    )


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

    # Round-14 #3: a PRESENT raw llm_subscription record makes EVERY spawn fail closed
    # (RetiredSubscriptionLaneError at the top of provider_auth_env_overrides), so
    # surface needs_migration here — even a valid BYO key can't be used until the raw
    # record is stripped (the spawn's top-of-function reject fires before BYO). This is
    # the strongest fail-closed state; report it early.
    from tinyassets.credential_vault import (
        _has_retired_subscription_marker,
        has_legacy_subscription_records,
    )

    if has_legacy_subscription_records(udir):
        return EngineBinding(
            bound=False,
            engine_source=declared_source,
            capacity_kinds=(),
            reason=(
                "needs_record_migration: this universe's vault holds a RAW legacy "
                "subscription credential (a RETIRED lane — the platform never custodies "
                "subscription tokens). Every engine spawn will fail closed until it is "
                "removed. Run the host-gated subscription-record migration "
                "(credential_vault.quarantine_legacy_subscription_records) to strip it "
                "(non-secret marker retained), then re-bind a sanctioned engine via "
                "write_graph target=engine."
            ),
            needs_record_migration=True,
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
        if not byo_execution_enabled(udir):  # round-15 #2: per-record context
            reason = (
                "a BYO API key is present but hosted BYO execution is not "
                "enabled — vault encryption (KMS / external secret manager) is "
                "required first; run the daemon on your own device to use your "
                "key now"
            )
        elif not scan.sanctioned_eligible_providers:
            # Round-18 #1: execution is attested, but NO usable key's provider is a
            # sanctioned custody target (default-deny at CONSUMPTION). The key is
            # never bound and never injected (the resolve_llm_api_key gate mirrors
            # this) — even a legacy/manually-written attested record. Honestly
            # not-bound, NOT a fail-loud "broken key" (it may be perfectly valid,
            # just for an unapproved provider).
            reason = (
                "a BYO API key is present but its provider's custody is not a "
                "sanctioned target yet (default-deny) — the platform does not yet "
                "custody and execute this provider's keys; run the daemon on your "
                "own device to use your key now"
            )
        else:
            healthy: set[str] = set()
            try:
                # Only SANCTIONED-eligible providers may bind (round-18 #1); an
                # unsanctioned provider's key never resolves (resolve_llm_api_key
                # gate) so it could never be healthy anyway.
                for provider in scan.sanctioned_eligible_providers:
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
            # Round-12 #4: distinguish "lane DECLARED but BROKEN credential" from
            # "no lane declared" / "declared-not-executable idle". When the founder
            # EXPLICITLY declared engine_source=byo_api_key AND a SANCTIONED
            # executable provider's key (claude-code) is PRESENT but failed
            # auth-health (malformed / not a well-formed sk-ant- key), the declared
            # lane is MISCONFIGURED — fail loud so the router FAILS CLOSED
            # (AllProvidersExhausted) instead of silently borrowing the full
            # platform fallback chain. An UNDECLARED universe with a stray broken
            # key stays idle (ambient) — it never declared a BYO lane to honor.
            if declared_source == "byo_api_key" and (
                scan.sanctioned_eligible_providers & _EXECUTABLE_BYO_PROVIDERS
            ):
                raise EngineMisconfiguredError(
                    universe_id, declared_source,
                    "a BYO API key for an executable provider is present but "
                    "failed auth-health (not a well-formed key) — re-bind via "
                    "write_graph target=engine; refusing to fall through to "
                    "platform auth",
                )
            # A codex-only key, or an undeclared universe with a stray key:
            # declared-not-executable / idle by design (Codex BYO needs unmet
            # sandboxing, F1) — not a fail-closed misconfiguration.
            reason = (
                "a BYO API key is present but not executable: Codex BYO needs "
                "unmet sandboxing (declared-not-executable), or an Anthropic key "
                "must be a well-formed sk-ant- key — bind one or run the daemon "
                "on your own device"
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
            "per-universe-consumable (re-bind via write_graph target=engine)",
        )

    # A DECLARED byo_api_key with no key at all is genuinely broken → fail loud.
    if declared_source == "byo_api_key":
        raise EngineMisconfiguredError(
            universe_id, declared_source,
            "no usable BYO API key in the per-universe vault",
        )

    # Round-20 #1: a RETIRED-MARKED universe (its raw subscription record was removed,
    # a non-secret marker remains) with NO usable per-universe engine reaches here.
    # It must NOT read as idle-ambient (which would run on the HOST's identity — a
    # cross-identity leak). Report it as fail-closed retired until re-bound. Checked
    # AFTER the BYO binding block, so a retired universe RE-BOUND with a healthy
    # sanctioned BYO key still binds to its OWN identity above (not blocked here).
    if _has_retired_subscription_marker(udir):
        return EngineBinding(
            bound=False,
            engine_source=declared_source,
            capacity_kinds=(),
            reason=(
                "retired_needs_rebind: this universe's subscription lane was retired "
                "(the raw token was already removed; a non-secret marker remains). The "
                "migration is DONE — do NOT re-run it. Its spawns FAIL CLOSED (they "
                "will never run on the host's identity) until it is RE-BOUND to a "
                "sanctioned engine via write_graph target=engine."
            ),
            retired_needs_rebind=True,
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
