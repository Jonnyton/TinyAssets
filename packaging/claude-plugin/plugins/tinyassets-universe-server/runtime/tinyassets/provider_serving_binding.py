"""Server-owned serving bindings for authenticated universe turns."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tinyassets.config import write_provider_assignment_projection
from tinyassets.credential_vault import (
    LLMCredentialCustodyReference,
    adopt_llm_subscription_custody,
    current_llm_subscription_custody,
)
from tinyassets.custom_agents import (
    get_binding,
    list_bindings,
    set_binding_provider_ref_in_transaction,
    set_binding_serving_in_transaction,
)
from tinyassets.provider_assignment import (
    ProviderAssignment,
    load_provider_assignment,
    load_provider_assignment_in_transaction,
    provider_assignment_admission,
    provider_assignment_digest,
    store_provider_assignment_in_transaction,
)
from tinyassets.provider_work_authority import (
    ProviderWorkAuthorityWriteOutcome,
    ProviderWorkBindingFence,
    ProviderWorkBindingRoot,
    ProviderWorkBindingSeed,
    ProviderWorkBindingService,
    provider_work_binding_id,
)
from tinyassets.storage.provider_work_authority import (
    SQLiteProviderWorkAuthorityStore,
)

_PROVIDER_SERVICE = {
    "claude-code": "claude",
    "codex": "codex",
}
_SERVING_OPERATIONS = ("converse",)
_SERVING_ROLES = ("writer",)
_MAX_BINDING_INVOCATIONS = 10_000
_MAX_TOKENS = 32_768
_MAX_COST_MICROUNITS = 10_000_000
_BINDING_TTL = timedelta(days=30)
_PLACEHOLDER_DIGEST = f"sha256:{'0' * 64}"


@dataclass(frozen=True, slots=True)
class _ServingResolver:
    seed: ProviderWorkBindingSeed

    def resolve(self, root: ProviderWorkBindingRoot) -> ProviderWorkBindingSeed | None:
        return self.seed if self._matches(root) else None

    def resolve_current_in_transaction(
        self,
        _connection: object,
        root: ProviderWorkBindingRoot,
    ) -> ProviderWorkBindingSeed | None:
        return self.resolve(root)

    def _matches(self, root: ProviderWorkBindingRoot) -> bool:
        return (
            root.owner_user_id == self.seed.owner_user_id
            and root.universe_id == self.seed.universe_id
            and root.provider == self.seed.provider
        )


def _expiry(now: datetime) -> str:
    return (now + _BINDING_TTL).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_universe(base: Path, universe_dir: str | Path, universe_id: str) -> Path:
    canonical_base = base.resolve(strict=False)
    expected = (canonical_base / universe_id).resolve(strict=False)
    supplied = Path(universe_dir).resolve(strict=False)
    if supplied != expected or expected.parent != canonical_base:
        raise ValueError("universe directory does not match the canonical universe id")
    return supplied


def _projection(binding) -> dict[str, object]:
    return {
        "binding_id": binding.binding_id,
        "generation": binding.generation,
        "binding_digest": binding.binding_digest,
        "state": binding.state.value,
        "owner_user_id": binding.owner_user_id,
        "universe_id": binding.universe_id,
        "provider": binding.provider,
        "allowed_operations": list(binding.allowed_operations),
        "allowed_roles": list(binding.allowed_roles),
        "assignment_generation": binding.assignment_generation,
        "assignment_digest": binding.assignment_digest,
        "max_invocations": binding.max_invocations,
        "max_tokens": binding.max_tokens,
        "max_cost_microunits": binding.max_cost_microunits,
        "expires_at": binding.expires_at,
    }


def _assignment(
    *,
    owner_user_id: str,
    universe_id: str,
    state: str,
    generation: int,
    provider: str,
    binding_id: str,
    binding_generation: int,
    binding_digest: str,
    custody: LLMCredentialCustodyReference,
    updated_at: str,
) -> ProviderAssignment:
    digest = provider_assignment_digest(
        owner_user_id=owner_user_id,
        universe_id=universe_id,
        provider=provider,
        generation=generation,
        binding_id=binding_id,
        credential_reference_id=custody.reference_id,
        credential_reference_generation=custody.generation,
        credential_reference_digest=custody.reference_digest,
    )
    return ProviderAssignment(
        universe_id=universe_id,
        owner_user_id=owner_user_id,
        state=state,
        generation=generation,
        provider=provider,
        binding_id=binding_id,
        binding_generation=binding_generation,
        binding_digest=binding_digest,
        credential_reference_id=custody.reference_id,
        credential_reference_generation=custody.generation,
        credential_reference_digest=custody.reference_digest,
        assignment_digest=digest,
        updated_at=updated_at,
    )


def _write_failed_assignment(
    store: SQLiteProviderWorkAuthorityStore,
    pending: ProviderAssignment,
    universe_dir: Path,
) -> None:
    try:
        with store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            failed = replace(
                pending,
                state="failed",
                updated_at=store.timestamp(),
            )
            store_provider_assignment_in_transaction(conn, failed)
            conn.commit()
        write_provider_assignment_projection(
            universe_dir,
            state="failed",
            generation=pending.generation,
        )
    except Exception:
        # The already-published pending assignment is deny-all. Preserve it
        # rather than masking the original exception with recovery diagnostics.
        pass


def _assert_provider_serving_coverage(selected: str) -> None:
    """Validate provider identity + present-day serving-role coverage.

    Shared live-policy gate so re-affirming serving (the switch replay path) can
    NEVER skip the coverage check that the initial bind enforced — coverage is a
    COMPUTED fact against today's FALLBACK_CHAINS, not a one-time bind check
    (Codex review 2026-08-12). A serving binding grants exactly `_SERVING_ROLES`;
    claude-code may serve iff it heads every one of those role chains. Today
    `_SERVING_ROLES == ("writer",)` and claude-code heads the writer chain, so
    converse serving is covered; if the serving scope later widens to a role
    claude-code cannot cover (judge/extract), this re-blocks it automatically
    rather than silently serving a role it cannot fulfil.
    """
    if selected not in _PROVIDER_SERVICE:
        raise ValueError("provider must be claude-code or codex")
    if selected == "claude-code":
        from tinyassets.providers.router import FALLBACK_CHAINS

        uncovered = [
            role
            for role in _SERVING_ROLES
            if selected not in FALLBACK_CHAINS.get(role, ())
        ]
        if uncovered:
            raise PermissionError(
                "claude-code serving is held until every live role is covered; "
                f"uncovered role(s): {', '.join(uncovered)}"
            )


def bind_serving_provider(
    *,
    base_path: str | Path,
    universe_dir: str | Path,
    owner_user_id: str,
    universe_id: str,
    agent_binding_id: str,
    expected_revision: int,
    provider: str,
) -> dict[str, object]:
    """Mint/rebind serving authority and wire one exact agent binding."""

    base = Path(base_path)
    owner = owner_user_id.strip()
    uid = universe_id.strip()
    binding_id = agent_binding_id.strip()
    selected = provider.strip()
    _assert_provider_serving_coverage(selected)
    if not owner or not uid or not binding_id:
        raise ValueError("owner, universe, and agent binding are required")
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision < 1
    ):
        raise ValueError("expected_revision must be a positive integer")
    universe = _canonical_universe(base, universe_dir, uid)

    # Ensures the custom-agent schema (including the serving migration) exists.
    agent = get_binding(base, universe_id=uid, binding_id=binding_id)
    if agent is None:
        raise LookupError("agent binding was not found")
    if agent["created_by"] != owner:
        raise PermissionError("only the binding creator may assign its provider")
    if int(agent["revision"]) != expected_revision:
        raise ValueError("agent binding revision is stale")

    admission = provider_assignment_admission()
    store = SQLiteProviderWorkAuthorityStore(base)
    serving_binding_id = provider_work_binding_id(
        owner_user_id=owner,
        universe_id=uid,
        provider=selected,
        binding_class="serving",
    )
    with admission.exclusive(universe):
        agent = get_binding(base, universe_id=uid, binding_id=binding_id)
        if agent is None:
            raise LookupError("agent binding was not found")
        if agent["created_by"] != owner:
            raise PermissionError("only the binding creator may assign its provider")
        if int(agent["revision"]) != expected_revision:
            raise ValueError("agent binding revision is stale")
        current_assignment = load_provider_assignment(base, universe_id=uid)
        current_binding = store.get(serving_binding_id)
        if (
            current_assignment is not None
            and current_assignment.state == "ready"
            and current_assignment.owner_user_id == owner
            and current_assignment.provider == selected
            and current_binding is not None
            and current_binding.binding_digest == current_assignment.binding_digest
            and agent["configuration"].get("provider_ref") == serving_binding_id
        ):
            try:
                with store.connection() as replay_conn:
                    replay_conn.execute("BEGIN")
                    _current_serving_authority(
                        replay_conn,
                        store=store,
                        universe_dir=universe,
                        owner_user_id=owner,
                        universe_id=uid,
                        agent=agent,
                    )
                    replay_conn.rollback()
            except PermissionError:
                pass
            else:
                return {
                    "status": "ready",
                    "replayed": True,
                    "provider_binding": _projection(current_binding),
                    "agent_binding": agent,
                    "assignment_generation": current_assignment.generation,
                }

        generation = (current_assignment.generation + 1) if current_assignment else 1
        predicted_binding_generation = (
            current_binding.generation + 1 if current_binding is not None else 1
        )
        pending: ProviderAssignment | None = None
        try:
            # Durable deny-all quarantine first. A process crash after this
            # point cannot resurrect the previous assignment.
            with store.connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                custody = adopt_llm_subscription_custody(
                    conn,
                    universe_dir=universe,
                    owner_user_id=owner,
                    universe_id=uid,
                    service=_PROVIDER_SERVICE[selected],
                )
                pending = _assignment(
                    owner_user_id=owner,
                    universe_id=uid,
                    state="pending",
                    generation=generation,
                    provider=selected,
                    binding_id=serving_binding_id,
                    binding_generation=predicted_binding_generation,
                    binding_digest=_PLACEHOLDER_DIGEST,
                    custody=custody,
                    updated_at=store.timestamp(),
                )
                store_provider_assignment_in_transaction(conn, pending)
                conn.commit()
            write_provider_assignment_projection(
                universe,
                state="pending",
                generation=generation,
            )

            with store.connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                custody = current_llm_subscription_custody(
                    conn,
                    universe_dir=universe,
                    owner_user_id=owner,
                    universe_id=uid,
                    service=_PROVIDER_SERVICE[selected],
                )
                if custody is None:
                    raise PermissionError("credential custody changed during assignment")
                seed = ProviderWorkBindingSeed(
                    owner_user_id=owner,
                    universe_id=uid,
                    provider=selected,
                    credential_reference_digest=custody.reference_digest,
                    allowed_operations=_SERVING_OPERATIONS,
                    allowed_roles=_SERVING_ROLES,
                    assignment_generation=generation,
                    assignment_digest=pending.assignment_digest,
                    max_invocations=_MAX_BINDING_INVOCATIONS,
                    max_tokens=_MAX_TOKENS,
                    max_cost_microunits=_MAX_COST_MICROUNITS,
                    expires_at=_expiry(datetime.now(timezone.utc)),
                )
                service = ProviderWorkBindingService(store, _ServingResolver(seed))
                if current_binding is None:
                    issued = service.issue_in_transaction(
                        conn,
                        ProviderWorkBindingRoot(owner, uid, selected),
                    )
                else:
                    issued = service.rebind_in_transaction(
                        conn,
                        ProviderWorkBindingFence(current_binding),
                        ProviderWorkBindingRoot(owner, uid, selected),
                    )
                if issued.outcome not in {
                    ProviderWorkAuthorityWriteOutcome.APPLIED,
                    ProviderWorkAuthorityWriteOutcome.REPLAYED,
                } or issued.record is None:
                    raise PermissionError("serving provider binding could not be issued")
                provider_binding = issued.record
                updated_agent = set_binding_provider_ref_in_transaction(
                    conn,
                    universe_id=uid,
                    binding_id=binding_id,
                    expected_revision=expected_revision,
                    owner_user_id=owner,
                    provider_ref=provider_binding.binding_id,
                )
                ready = _assignment(
                    owner_user_id=owner,
                    universe_id=uid,
                    state="ready",
                    generation=generation,
                    provider=selected,
                    binding_id=provider_binding.binding_id,
                    binding_generation=provider_binding.generation,
                    binding_digest=provider_binding.binding_digest,
                    custody=custody,
                    updated_at=store.timestamp(),
                )
                if ready.assignment_digest != provider_binding.assignment_digest:
                    raise RuntimeError("binding and assignment digests disagree")
                store_provider_assignment_in_transaction(conn, ready)
                binding_projection = {
                    "binding_id": provider_binding.binding_id,
                    "generation": provider_binding.generation,
                    "binding_digest": provider_binding.binding_digest,
                    "assignment_digest": provider_binding.assignment_digest,
                }
                write_provider_assignment_projection(
                    universe,
                    state="ready",
                    generation=generation,
                    provider=selected,
                    binding=binding_projection,
                )
                conn.commit()
        except Exception:
            if pending is not None:
                _write_failed_assignment(store, pending, universe)
            raise

    return {
        "status": "ready",
        "replayed": False,
        "provider_binding": _projection(provider_binding),
        "agent_binding": updated_agent,
        "assignment_generation": ready.generation,
        "next_action": "set_serving",
    }


def _current_serving_authority(
    conn,
    *,
    store: SQLiteProviderWorkAuthorityStore,
    universe_dir: Path,
    owner_user_id: str,
    universe_id: str,
    agent: dict[str, object],
) -> tuple[ProviderAssignment, object, LLMCredentialCustodyReference]:
    """Re-read the complete server-owned serving chain in one SQLite fence."""

    assignment = load_provider_assignment_in_transaction(
        conn,
        universe_id=universe_id,
    )
    provider_ref = agent["configuration"].get("provider_ref")
    if (
        assignment is None
        or assignment.state != "ready"
        or assignment.owner_user_id != owner_user_id
        or not isinstance(provider_ref, str)
        or provider_ref != assignment.binding_id
    ):
        raise PermissionError("connect your provider before enabling serving")
    provider_binding = store.get_binding_in_transaction(
        conn,
        binding_id=assignment.binding_id,
    )
    if provider_binding is None or not store.validate_in_transaction(
        conn,
        binding_id=assignment.binding_id,
        binding_generation=assignment.binding_generation,
        binding_digest=assignment.binding_digest,
        owner_user_id=owner_user_id,
        universe_id=universe_id,
        provider=assignment.provider,
        operation="converse",
        role="writer",
    ):
        raise PermissionError("connect your provider before enabling serving")
    custody = current_llm_subscription_custody(
        conn,
        universe_dir=universe_dir,
        owner_user_id=owner_user_id,
        universe_id=universe_id,
        service=_PROVIDER_SERVICE[assignment.provider],
    )
    if custody is None or (
        custody.reference_id != assignment.credential_reference_id
        or custody.generation != assignment.credential_reference_generation
        or custody.reference_digest != assignment.credential_reference_digest
        or provider_binding.credential_reference_digest != custody.reference_digest
        or provider_binding.assignment_generation != assignment.generation
        or provider_binding.assignment_digest != assignment.assignment_digest
    ):
        raise PermissionError("connect your provider before enabling serving")
    return assignment, provider_binding, custody


def set_serving(
    *,
    base_path: str | Path,
    universe_dir: str | Path,
    owner_user_id: str,
    universe_id: str,
    agent_binding_id: str,
    expected_revision: int,
    enabled: bool,
) -> dict[str, object]:
    """Enable/disable an exact founder-owned binding for served turns."""

    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    owner = owner_user_id.strip()
    uid = universe_id.strip()
    binding_id = agent_binding_id.strip()
    if not owner or not uid or not binding_id:
        raise ValueError("owner, universe, and agent binding are required")
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision < 1
    ):
        raise ValueError("expected_revision must be a positive integer")

    universe = _canonical_universe(Path(base_path), universe_dir, uid)
    # Initialize/migrate the custom-agent schema before opening the composed
    # authority transaction below.
    existing = get_binding(base_path, universe_id=uid, binding_id=binding_id)
    if existing is None:
        raise LookupError("agent binding was not found")
    store = SQLiteProviderWorkAuthorityStore(base_path)
    with provider_assignment_admission().exclusive(universe):
        current = get_binding(base_path, universe_id=uid, binding_id=binding_id)
        if current is None:
            raise LookupError("agent binding was not found")
        if current["created_by"] != owner:
            raise PermissionError("only the binding creator may change serving state")
        if int(current["revision"]) != expected_revision:
            raise ValueError("agent binding revision is stale")
        with store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if enabled:
                assignment, _provider_binding, _custody = _current_serving_authority(
                    conn,
                    store=store,
                    universe_dir=universe,
                    owner_user_id=owner,
                    universe_id=uid,
                    agent=current,
                )
            updated = set_binding_serving_in_transaction(
                conn,
                universe_id=uid,
                binding_id=binding_id,
                expected_revision=expected_revision,
                owner_user_id=owner,
                enabled=enabled,
            )
            conn.commit()
    response: dict[str, object] = {
        "status": "serving" if enabled else "configured",
        "agent_binding": updated,
    }
    if enabled:
        response["provider"] = assignment.provider
        response["assignment_generation"] = assignment.generation
    return response


def switch_serving_provider(
    *,
    base_path: str | Path,
    universe_dir: str | Path,
    owner_user_id: str,
    universe_id: str,
    agent_binding_id: str,
    expected_revision: int,
    provider: str,
) -> dict[str, object]:
    """One call: bind ``provider`` as serving authority AND enable serving.

    This COMPOSES the existing revision-gated ``bind_serving_provider`` +
    ``set_serving`` and resolves the intermediate revision internally, so a
    caller (or a chatbot) makes ONE call instead of the two-step handshake —
    bind bumps the revision, then set_serving must use the new one — which
    forced stale-revision retries in the live chatbot flow. It adds NO new
    authority: each composed call keeps its own owner + revision +
    provider-coverage checks, so this can only do what the caller could already
    do by hand.

    Concurrency (Codex TOCTOU review 2026-08-12): bind releases its exclusive
    lock before set_serving re-acquires it, so a concurrent owner-authorized
    switch could intervene in that gap. Guarded two ways: set_serving is threaded
    with the revision ``bind`` itself left the binding at (an intervening switch
    bumps it, so set_serving fails STALE rather than silently enabling the other
    provider), and the enabled provider is verified against the requested one
    before success is reported. An "already serving the requested provider"
    call short-circuits to a no-op success so a retry is idempotent.
    """
    uid = universe_id.strip()
    binding_id = agent_binding_id.strip()
    selected = provider.strip()
    # Present-day provider + coverage gate BEFORE either path, so the replay
    # (re-affirm) path can never enable serving on a provider that no longer
    # covers every serving role — the check bind runs but set_serving does not
    # (Codex review 2026-08-12).
    _assert_provider_serving_coverage(selected)

    from tinyassets.provider_assignment import load_provider_assignment

    # Idempotency / retry-safety: if already serving the requested provider,
    # RE-AFFIRM through set_serving — NOT a bare read-return. set_serving re-runs
    # the owner (created_by == owner) + custody + serving-authority checks under
    # its own admission lock, and we thread the CURRENT revision so a
    # stale-revision retry is idempotent. (Codex review 2026-08-12: a bare
    # read-return skipped the primitives' owner/coverage/lock checks, so a
    # collaborator could get a success envelope for a binding they don't own.)
    # A concurrent change between this read and set_serving makes it fail stale
    # (fail-loud), and the enabled provider is verified below regardless.
    _current = get_binding(base_path, universe_id=uid, binding_id=binding_id)
    if _current is not None and str(_current.get("status")) == "serving":
        _assignment = load_provider_assignment(base_path, universe_id=uid)
        if (
            _assignment is not None
            and _assignment.provider == selected
            and _assignment.state == "ready"
        ):
            served = set_serving(
                base_path=base_path,
                universe_dir=universe_dir,
                owner_user_id=owner_user_id,
                universe_id=universe_id,
                agent_binding_id=agent_binding_id,
                expected_revision=int(_current["revision"]),
                enabled=True,
            )
            served_provider = served.get("provider")
            if served_provider != selected:
                raise PermissionError(
                    f"serving provider mismatch: requested {selected!r}, "
                    f"enabled {served_provider!r}"
                )
            return {
                "status": served.get("status", "serving"),
                "provider": selected,
                "agent_binding": served.get("agent_binding"),
                "served": served,
                "replayed": True,
            }

    bound = bind_serving_provider(
        base_path=base_path,
        universe_dir=universe_dir,
        owner_user_id=owner_user_id,
        universe_id=universe_id,
        agent_binding_id=agent_binding_id,
        expected_revision=expected_revision,
        provider=selected,
    )
    # Thread the revision bind ITSELF left the binding at (its returned
    # projection), NOT a fresh re-read. In the post-bind gap a concurrent switch
    # would bump the revision; using bind's revision makes set_serving fail stale
    # on that race instead of enabling the intervening provider.
    agent = bound.get("agent_binding") or {}
    try:
        bound_revision = int(agent["revision"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LookupError("could not resolve the post-bind agent revision") from exc

    served = set_serving(
        base_path=base_path,
        universe_dir=universe_dir,
        owner_user_id=owner_user_id,
        universe_id=universe_id,
        agent_binding_id=agent_binding_id,
        expected_revision=bound_revision,
        enabled=True,
    )
    # Defense in depth: never report success on a provider other than requested.
    served_provider = served.get("provider")
    if served_provider != selected:
        raise PermissionError(
            f"serving provider mismatch: requested {selected!r}, "
            f"enabled {served_provider!r}"
        )
    return {
        "status": served.get("status", "serving"),
        "provider": selected,
        "agent_binding": served.get("agent_binding"),
        "bound": bound,
        "served": served,
    }


def resolve_serving_agent_binding(
    base_path: str | Path,
    *,
    universe_id: str,
    owner_user_id: str,
) -> dict[str, object]:
    """Select exactly one current serving binding for a founder turn."""

    matches = [
        binding
        for binding in list_bindings(base_path, universe_id=universe_id, limit=100)
        if binding["status"] == "serving"
        and binding["created_by"] == owner_user_id
    ]
    if len(matches) != 1:
        raise PermissionError(
            "connect your provider: exactly one founder serving binding is required"
        )
    return matches[0]


def list_serving_universes(base_path: str | Path) -> list[str]:
    """Return universes with exactly one fully-current serving enrollment."""

    from collections import defaultdict

    from tinyassets.storage import db_path

    base = Path(base_path)
    conn = sqlite3.connect(db_path(base))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT universe_id, agent_binding_id, created_by
              FROM agent_bindings
             WHERE status = 'serving'
             ORDER BY universe_id, agent_binding_id
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[str(row["universe_id"])].append(row)

    valid: list[str] = []
    store = SQLiteProviderWorkAuthorityStore(base)
    for uid, candidates in grouped.items():
        universe = base / uid
        for row in candidates:
            agent = get_binding(
                base,
                universe_id=uid,
                binding_id=str(row["agent_binding_id"]),
            )
            if agent is None or agent["status"] != "serving":
                continue
            try:
                with provider_assignment_admission().shared(universe):
                    with store.connection() as authority_conn:
                        authority_conn.execute("BEGIN")
                        _current_serving_authority(
                            authority_conn,
                            store=store,
                            universe_dir=universe,
                            owner_user_id=str(row["created_by"]),
                            universe_id=uid,
                            agent=agent,
                        )
                        authority_conn.rollback()
            except (PermissionError, RuntimeError, ValueError, sqlite3.Error):
                continue
            valid.append(uid)
            break
    return sorted(valid)


__all__ = [
    "bind_serving_provider",
    "list_serving_universes",
    "resolve_serving_agent_binding",
    "set_serving",
]
