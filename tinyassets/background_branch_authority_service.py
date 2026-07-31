"""Dark server-owned lifecycle transitions for background Branch bindings.

The service resolves canonical authority through a trusted server adapter and
is the only layer that constructs binding IDs, digests, generations, or status
replacements. It does not issue attempts or activate background execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable

from tinyassets.background_branch_authority import (
    BackgroundBranchAuthorityStore,
    BackgroundBranchAuthorityWriteOutcome,
    BackgroundBranchBinding,
    BackgroundBranchBindingFence,
    BackgroundBranchBindingStatus,
    BackgroundBranchBindingWriteResult,
    BackgroundBranchChildDelegation,
    BackgroundBranchExecutorClass,
    BackgroundBranchOperation,
    BackgroundBranchSourceKind,
    BackgroundBranchTargetMode,
)

_BINDING_ROOTS = frozenset({
    BackgroundBranchSourceKind.SCHEDULE,
    BackgroundBranchSourceKind.SUBSCRIPTION,
    BackgroundBranchSourceKind.PINNED_SOUL,
    BackgroundBranchSourceKind.ROOT_RUN,
    BackgroundBranchSourceKind.REQUEST_ADMISSION,
    BackgroundBranchSourceKind.PRODUCER_SUBSCRIPTION,
    BackgroundBranchSourceKind.ACCEPTED_MARKET_CONTRACT,
    BackgroundBranchSourceKind.RESUMED_RUN,
    BackgroundBranchSourceKind.DIRECT_CHILD,
    BackgroundBranchSourceKind.PARENT_ATTEMPT,
})
_PLACEHOLDER_DIGEST = f"sha256:{'0' * 64}"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _digest(value: object) -> str:
    encoded = _canonical_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _required(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty reference")
    return value


@dataclass(frozen=True, slots=True)
class BackgroundBranchBindingRoot:
    """Non-authorizing lookup reference for one closed issuance root."""

    source_kind: BackgroundBranchSourceKind
    source_id: str

    def __post_init__(self) -> None:
        if self.source_kind not in _BINDING_ROOTS:
            raise ValueError("source_kind is not a binding issuance root")
        _required(self.source_id, "source_id")


@dataclass(frozen=True, slots=True)
class BackgroundBranchBindingSeed:
    """Canonical authority facts returned by a trusted server resolver."""

    authorizing_principal_id: str
    universe_id: str
    branch_def_id: str
    operation: BackgroundBranchOperation
    source_kind: BackgroundBranchSourceKind
    source_id: str
    source_revision: str
    source_digest: str
    target_mode: BackgroundBranchTargetMode
    pinned_branch_version_id: str | None
    permitted_executor_classes: tuple[BackgroundBranchExecutorClass, ...]
    daemon_id: str | None
    runtime_id: str | None
    expires_at: str | None
    max_attempts: int
    remaining_depth: int
    remaining_count: int
    remaining_cost_microunits: int
    child_delegation: BackgroundBranchChildDelegation

    def __post_init__(self) -> None:
        _binding_from_seed(
            self,
            binding_id="bnd_validation",
            status=BackgroundBranchBindingStatus.ACTIVE,
            generation=1,
            revocation_generation=0,
        )


@runtime_checkable
class BackgroundBranchBindingResolver(Protocol):
    """Trusted adapter over canonical principal/source/target read models."""

    def resolve(
        self,
        root: BackgroundBranchBindingRoot,
    ) -> BackgroundBranchBindingSeed | None:
        """Return fresh canonical facts, or ``None`` when authority is absent."""


class BackgroundBranchBindingTransitionError(ValueError):
    """Stable fail-closed result for an inadmissible server transition."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _binding_from_seed(
    seed: BackgroundBranchBindingSeed,
    *,
    binding_id: str,
    status: BackgroundBranchBindingStatus,
    generation: int,
    revocation_generation: int,
) -> BackgroundBranchBinding:
    provisional = BackgroundBranchBinding(
        schema_version=1,
        binding_id=binding_id,
        status=status,
        generation=generation,
        binding_digest=_PLACEHOLDER_DIGEST,
        authorizing_principal_id=seed.authorizing_principal_id,
        universe_id=seed.universe_id,
        branch_def_id=seed.branch_def_id,
        operation=seed.operation,
        source_kind=seed.source_kind,
        source_id=seed.source_id,
        source_revision=seed.source_revision,
        source_digest=seed.source_digest,
        revocation_generation=revocation_generation,
        target_mode=seed.target_mode,
        pinned_branch_version_id=seed.pinned_branch_version_id,
        permitted_executor_classes=seed.permitted_executor_classes,
        daemon_id=seed.daemon_id,
        runtime_id=seed.runtime_id,
        expires_at=seed.expires_at,
        max_attempts=seed.max_attempts,
        remaining_depth=seed.remaining_depth,
        remaining_count=seed.remaining_count,
        remaining_cost_microunits=seed.remaining_cost_microunits,
        child_delegation=seed.child_delegation,
    )
    payload = provisional.to_dict()
    del payload["binding_digest"]
    return replace(provisional, binding_digest=_digest(payload))


def _binding_id(root: BackgroundBranchBindingRoot) -> str:
    identity = {
        "schema_version": 1,
        "source_kind": root.source_kind.value,
        "source_id": root.source_id,
    }
    return f"bnd_{_digest(identity).removeprefix('sha256:')[:32]}"


def _with_server_transition(
    current: BackgroundBranchBinding,
    *,
    status: BackgroundBranchBindingStatus,
    revocation_generation: int,
) -> BackgroundBranchBinding:
    provisional = replace(
        current,
        status=status,
        generation=current.generation + 1,
        binding_digest=_PLACEHOLDER_DIGEST,
        revocation_generation=revocation_generation,
    )
    payload = provisional.to_dict()
    del payload["binding_digest"]
    return replace(provisional, binding_digest=_digest(payload))


class BackgroundBranchBindingTransitionService:
    """Construct and persist only server-derived binding transitions."""

    def __init__(
        self,
        store: BackgroundBranchAuthorityStore,
        resolver: BackgroundBranchBindingResolver,
    ) -> None:
        if not isinstance(store, BackgroundBranchAuthorityStore):
            raise ValueError("store must implement BackgroundBranchAuthorityStore")
        if not isinstance(resolver, BackgroundBranchBindingResolver):
            raise ValueError(
                "resolver must implement BackgroundBranchBindingResolver"
            )
        self._store = store
        self._resolver = resolver

    def _resolve(
        self,
        root: BackgroundBranchBindingRoot,
    ) -> BackgroundBranchBindingSeed:
        if not isinstance(root, BackgroundBranchBindingRoot):
            raise ValueError("root must be a BackgroundBranchBindingRoot")
        seed = self._resolver.resolve(root)
        if seed is None:
            raise BackgroundBranchBindingTransitionError(
                "root_resolution_missing",
                "canonical authority is absent",
            )
        if (
            not isinstance(seed, BackgroundBranchBindingSeed)
            or seed.source_kind is not root.source_kind
            or seed.source_id != root.source_id
        ):
            raise BackgroundBranchBindingTransitionError(
                "root_resolution_mismatch",
                "canonical source does not match the requested root",
            )
        return seed

    def create(
        self,
        root: BackgroundBranchBindingRoot,
    ) -> BackgroundBranchBindingWriteResult:
        seed = self._resolve(root)
        binding = _binding_from_seed(
            seed,
            binding_id=_binding_id(root),
            status=BackgroundBranchBindingStatus.ACTIVE,
            generation=1,
            revocation_generation=0,
        )
        with self._store.transaction() as transaction:
            return transaction.insert_binding(binding)

    def rotate(
        self,
        expected: BackgroundBranchBindingFence,
    ) -> BackgroundBranchBindingWriteResult:
        current = self._expected_binding(expected)
        root = BackgroundBranchBindingRoot(
            source_kind=current.source_kind,
            source_id=current.source_id,
        )
        seed = self._resolve(root)
        immutable_identity_matches = (
            seed.authorizing_principal_id
            == current.authorizing_principal_id,
            seed.universe_id == current.universe_id,
            seed.source_kind is current.source_kind,
            seed.source_id == current.source_id,
            _binding_id(root) == current.binding_id,
        )
        if not all(immutable_identity_matches):
            raise BackgroundBranchBindingTransitionError(
                "identity_transfer",
                "rotation cannot replace authorizer, universe, or source",
            )
        replacement = _binding_from_seed(
            seed,
            binding_id=current.binding_id,
            status=BackgroundBranchBindingStatus.ACTIVE,
            generation=current.generation + 1,
            revocation_generation=current.revocation_generation,
        )
        return self._compare_and_swap(expected, replacement)

    def pause(
        self,
        expected: BackgroundBranchBindingFence,
    ) -> BackgroundBranchBindingWriteResult:
        return self._status_transition(
            expected,
            target=BackgroundBranchBindingStatus.PAUSED,
            allowed=frozenset({BackgroundBranchBindingStatus.ACTIVE}),
        )

    def revoke(
        self,
        expected: BackgroundBranchBindingFence,
    ) -> BackgroundBranchBindingWriteResult:
        return self._status_transition(
            expected,
            target=BackgroundBranchBindingStatus.REVOKED,
            allowed=frozenset({
                BackgroundBranchBindingStatus.ACTIVE,
                BackgroundBranchBindingStatus.PAUSED,
                BackgroundBranchBindingStatus.EXHAUSTED,
                BackgroundBranchBindingStatus.EXPIRED,
            }),
            advance_revocation=True,
        )

    def exhaust(
        self,
        expected: BackgroundBranchBindingFence,
    ) -> BackgroundBranchBindingWriteResult:
        return self._status_transition(
            expected,
            target=BackgroundBranchBindingStatus.EXHAUSTED,
            allowed=frozenset({
                BackgroundBranchBindingStatus.ACTIVE,
                BackgroundBranchBindingStatus.PAUSED,
            }),
        )

    @staticmethod
    def _expected_binding(
        expected: BackgroundBranchBindingFence,
    ) -> BackgroundBranchBinding:
        if not isinstance(expected, BackgroundBranchBindingFence):
            raise ValueError("expected must be a BackgroundBranchBindingFence")
        return expected.expected_record

    def _status_transition(
        self,
        expected: BackgroundBranchBindingFence,
        *,
        target: BackgroundBranchBindingStatus,
        allowed: frozenset[BackgroundBranchBindingStatus],
        advance_revocation: bool = False,
    ) -> BackgroundBranchBindingWriteResult:
        current = self._expected_binding(expected)
        if current.status is target:
            replacement = current
        elif current.status in allowed:
            replacement = _with_server_transition(
                current,
                status=target,
                revocation_generation=(
                    current.revocation_generation + 1
                    if advance_revocation
                    else current.revocation_generation
                ),
            )
        else:
            stale = self._preflight(expected)
            if stale is not None:
                return stale
            raise BackgroundBranchBindingTransitionError(
                "invalid_transition",
                f"{current.status.value} cannot transition to {target.value}",
            )
        stale = self._preflight(expected, replay=replacement)
        if stale is not None:
            return stale
        return self._compare_and_swap(expected, replacement)

    def _preflight(
        self,
        expected: BackgroundBranchBindingFence,
        *,
        replay: BackgroundBranchBinding | None = None,
    ) -> BackgroundBranchBindingWriteResult | None:
        current = self._store.get_binding(expected.expected_record.binding_id)
        if current is None:
            return BackgroundBranchBindingWriteResult(
                BackgroundBranchAuthorityWriteOutcome.MISSING,
                None,
            )
        if current == expected.expected_record:
            return None
        if replay is not None and current == replay:
            return BackgroundBranchBindingWriteResult(
                BackgroundBranchAuthorityWriteOutcome.REPLAYED,
                current,
            )
        outcome = (
            BackgroundBranchAuthorityWriteOutcome.GENERATION_MISMATCH
            if current.generation != expected.expected_record.generation
            else BackgroundBranchAuthorityWriteOutcome.CONFLICT
        )
        return BackgroundBranchBindingWriteResult(outcome, current)

    def _compare_and_swap(
        self,
        expected: BackgroundBranchBindingFence,
        replacement: BackgroundBranchBinding,
    ) -> BackgroundBranchBindingWriteResult:
        with self._store.transaction() as transaction:
            return transaction.compare_and_swap_binding(
                binding_id=expected.expected_record.binding_id,
                expected=expected,
                replacement=replacement,
            )


__all__ = [
    "BackgroundBranchBindingResolver",
    "BackgroundBranchBindingRoot",
    "BackgroundBranchBindingSeed",
    "BackgroundBranchBindingTransitionError",
    "BackgroundBranchBindingTransitionService",
]
