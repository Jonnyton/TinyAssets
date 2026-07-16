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


@dataclass(frozen=True)
class EngineBinding:
    """Resolved engine-capacity binding for one universe.

    ``bound`` is the load-bearing field: True when the universe has at least one
    real, usable capacity bound to it. ``capacity_kinds`` names each capacity
    found (e.g. ``("byo_api_key",)`` / ``("subscription:claude",)`` /
    ``("self_hosted_endpoint",)``). ``engine_source`` echoes the founder's
    declared choice from ``config.yaml`` (empty when none was declared).
    """

    bound: bool
    engine_source: str
    capacity_kinds: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "bound": self.bound,
            "engine_source": self.engine_source,
            "capacity_kinds": list(self.capacity_kinds),
            "reason": self.reason,
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


def _vault_capacity(universe_dir: Path) -> list[str]:
    """Return capacity kinds present in the per-universe credential vault.

    Recognizes the founder's own engines: a BYO ``llm_api_key`` deposit and a
    subscription-CLI ``llm_subscription`` bundle (claude / codex). These are
    directly executable — provider routing consumes them at call time. Propagates
    :class:`ValueError` (malformed vault) so the caller can fail loud.
    """
    from tinyassets.credential_vault import load_credential_vault

    records = load_credential_vault(universe_dir)  # raises ValueError if malformed
    kinds: list[str] = []
    if any(r.get("credential_type") == "llm_api_key" for r in records):
        kinds.append("byo_api_key")
    for record in records:
        if record.get("credential_type") != "llm_subscription":
            continue
        svc = str(record.get("service") or record.get("provider") or "").strip().lower()
        kinds.append(f"subscription:{svc}" if svc else "subscription")
    return kinds


def _has_live_runtime_instance(universe_dir: Path) -> bool:
    """Return True iff a NON-RETIRED runtime instance is assigned to this universe.

    This is the executable-capacity proof for the config-declared engine sources
    in :data:`_RUNTIME_BACKED_SOURCES`: those persist only a choice, so a live
    ``author_runtime_instances`` row is what proves the worker can actually run
    the universe. A missing / uninitialized registry degrades to ``False`` (no
    runtime yet → idle-until-bound) and never raises — an absent registry is not
    a misconfigured binding.
    """
    try:
        from tinyassets.daemon_server import list_runtime_instances

        instances = list_runtime_instances(
            universe_dir.parent, universe_id=universe_dir.name,
        )
    except Exception:  # noqa: BLE001 — no DB / no table = no assigned runtime
        return False
    return any(
        str(inst.get("status") or "").strip().lower() != "retired"
        for inst in instances
    )


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
        capacity: list[str] = list(_vault_capacity(udir))
    except ValueError as exc:
        raise EngineMisconfiguredError(
            universe_id,
            declared_source or "byo_api_key",
            f"credential vault is unreadable: {exc}",
        ) from exc

    # Config-declared runtime-backed sources are executable ONLY with a live
    # runtime instance assigned to the universe (the config value alone is a
    # choice, not capacity). A missing runtime is idle-until-bound, not an error.
    if declared_source in _RUNTIME_BACKED_SOURCES and _has_live_runtime_instance(udir):
        capacity.append(f"runtime:{declared_source}")

    # Deduplicate while preserving discovery order.
    capacity = list(dict.fromkeys(capacity))

    if capacity:
        return EngineBinding(
            bound=True,
            engine_source=declared_source,
            capacity_kinds=tuple(capacity),
            reason="bound to " + ", ".join(capacity),
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
