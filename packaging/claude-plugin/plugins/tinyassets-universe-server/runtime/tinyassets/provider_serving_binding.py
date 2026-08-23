"""Server-owned serving bindings for authenticated universe turns."""

from __future__ import annotations

import os
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
# In-flight token / cost ceilings for a serving binding. These bound only
# UNSETTLED (concurrent) reserved spend — a settled turn RELEASES (see
# provider_assignment.reserve_served_provider_budget), so this is a CONCURRENCY
# runaway guard, NOT a cumulative spend limit (the user's own deposited
# subscription meters real spend upstream). The prior 32_768 was sized like a
# spend cap and bricked at ~2 concurrent codex turns: a served turn reserves
# `len(system+prompt bytes)` (a rebuilt persona/brain system prompt is ~15-30 KB)
# plus its output, so the SECOND simultaneous turn across ANY surface got
# `output_tokens < 1` -> "budget exhausted". That violated the core requirement
# that one user drive their universe from many surfaces at once alongside
# concurrent LangGraph automations (and many users doing the same, each on their
# OWN per-binding ceiling). Sized now for realistic single-user concurrency
# (~90 simultaneous worst-case ~45 KB turns); the true runaway backstops remain
# the rolling per-hour invocation cap (_MAX_BINDING_INVOCATIONS) + the engine-run
# rate limit (20/hr) + the user's metered subscription.
_MAX_TOKENS = 4_000_000
_MAX_COST_MICROUNITS = 400_000_000  # affordable = _MAX_COST/100 tokens, kept >= _MAX_TOKENS
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
    if selected not in _PROVIDER_SERVICE:
        raise ValueError("provider must be claude-code or codex")
    if selected == "claude-code":
        # claude-code serving is HELD BY DEFAULT. The OpenSpec design
        # (byo-llm-connect-flow/design.md §"Claude requester-local readiness")
        # requires that Slice 1 "must not silently bypass" the role-completeness
        # invariant "merely because `converse` currently asks only for `writer`".
        # So enabling it requires BOTH, and neither alone is enough:
        #
        #   (a) an EXPLICIT operator opt-in (`TINYASSETS_ALLOW_CLAUDE_SERVING`).
        #       Off by default, so no deployment silently gains claude serving;
        #       the vetted single-founder host sets it deliberately (host
        #       directive: the founder's universe serves on their own deposited
        #       Claude subscription). This is the documented ratification of the
        #       decision the founder drove — it is NOT computed away silently.
        #   (b) a COMPUTED proof that claude-code covers every role THIS binding
        #       actually grants (`_SERVING_ROLES`). Today that is `("writer",)`
        #       and claude-code heads the writer chain, so converse serving is
        #       covered. If the serving scope ever widens to a role claude-code
        #       cannot cover (judge/extract), (b) re-blocks automatically — the
        #       invariant is enforced, not bypassed.
        #
        # Cross-family review 2026-08-19 (Codex reject #2) flagged the earlier
        # (b)-only form as a silent bypass. Gate (a) restores the spec DEFAULT
        # (claude-code serving held) and makes any relaxation an explicit host
        # deployment decision, not a computed no-op. Formal OpenSpec sync of this
        # host exception (byo-llm-connect-flow/design.md §"Claude requester-local
        # readiness") is owed and pending founder ratification — tracked in
        # STATUS.md; the code fails safe (held) until the host opts in.
        from tinyassets.providers.router import FALLBACK_CHAINS

        opt_in = os.environ.get(
            "TINYASSETS_ALLOW_CLAUDE_SERVING", ""
        ).strip().lower() in ("1", "true", "yes", "on")
        uncovered = [
            role
            for role in _SERVING_ROLES
            if selected not in FALLBACK_CHAINS.get(role, ())
        ]
        if not opt_in:
            raise PermissionError(
                "claude-code serving is held by default; set "
                "TINYASSETS_ALLOW_CLAUDE_SERVING for the vetted host to enable it"
            )
        if uncovered:
            raise PermissionError(
                "claude-code serving is held until every live role is covered; "
                f"uncovered role(s): {', '.join(uncovered)}"
            )
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
            # Replay ONLY when the signed ceilings EXACTLY match current policy.
            # Any drift — a stale-low binding (bound before the ceiling was raised)
            # OR a stale-high binding (policy since tightened) — must fall through
            # to the transactional rebind, which advances the generation/digest and
            # re-signs at the current ceiling. Exact equality (not >=) so a policy
            # tightening actually reflows down, and a raise actually heals up, both
            # via a re-signed authority — never an admission-time override that
            # would bypass the digest-covered contract (Codex 2026-08-22).
            and current_binding.max_tokens == _MAX_TOKENS
            and current_binding.max_cost_microunits == _MAX_COST_MICROUNITS
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
