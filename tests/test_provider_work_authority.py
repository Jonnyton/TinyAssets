from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from tinyassets.provider_work_authority import (
    ProviderInvocationReservationRequest,
    ProviderUniverseWorkAuthority,
    ProviderUniverseWorkRoot,
    ProviderWorkAuthorityWriteOutcome,
    ProviderWorkBindingFence,
    ProviderWorkBindingSeed,
    ProviderWorkBindingService,
    ProviderWorkBindingState,
    ProviderWorkExecutionClaimRequest,
    ProviderWorkReceiptService,
    ProviderWorkReceiptState,
)
from tinyassets.storage import db_path
from tinyassets.storage.provider_work_authority import (
    SQLiteProviderWorkAuthorityStore,
)

NOW = datetime(2026, 8, 1, 6, 0, tzinfo=timezone.utc)


def _seed(**overrides: object) -> ProviderWorkBindingSeed:
    values: dict[str, object] = {
        "owner_user_id": "acct_alice",
        "universe_id": "universe_alice",
        "provider": "codex",
        "credential_reference_digest": f"sha256:{'a' * 64}",
        "allowed_operations": ("repository_spec_delivery",),
        "allowed_roles": ("writer", "reviewer"),
        "assignment_generation": 3,
        "assignment_digest": f"sha256:{'b' * 64}",
        "max_invocations": 4,
        "max_tokens": 100_000,
        "max_cost_microunits": 5_000_000,
        "expires_at": "2026-08-02T00:00:00Z",
    }
    values.update(overrides)
    return ProviderWorkBindingSeed(**values)  # type: ignore[arg-type]


def _install(
    tmp_path,
    seed: ProviderWorkBindingSeed | None = None,
) -> tuple[SQLiteProviderWorkAuthorityStore, object]:
    store = SQLiteProviderWorkAuthorityStore(
        tmp_path,
        allow_test_fixtures=True,
    )
    result = store.install_test_binding(_seed() if seed is None else seed)
    return store, result


def test_binding_is_secret_free_immutable_and_content_addressed(tmp_path) -> None:
    _store, created = _install(tmp_path)

    assert created.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED
    binding = created.record
    assert binding is not None
    assert binding.binding_id.startswith("pwb_")
    assert binding.binding_digest.startswith("sha256:")
    assert binding.state is ProviderWorkBindingState.ACTIVE
    assert "credential" not in binding.to_dict()
    assert binding.to_dict()["credential_reference_digest"] == f"sha256:{'a' * 64}"
    with pytest.raises(FrozenInstanceError):
        binding.provider = "claude"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("credential_reference_digest", "secret-token"),
        ("assignment_digest", "not-a-digest"),
        ("allowed_operations", ()),
        ("allowed_roles", ()),
        ("assignment_generation", 0),
        ("max_invocations", 0),
        ("max_tokens", -1),
        ("max_cost_microunits", -1),
    ],
)
def test_binding_seed_rejects_unbounded_or_noncanonical_authority(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        _seed(**{field: value})


def test_same_fixture_binding_replays_across_restart(tmp_path) -> None:
    first = _install(tmp_path)[1]
    second = _install(tmp_path)[1]

    assert first.record is not None
    assert second.outcome is ProviderWorkAuthorityWriteOutcome.REPLAYED
    assert second.record == first.record


def test_changed_assignment_conflicts_instead_of_silently_rebinding(tmp_path) -> None:
    original = _install(tmp_path)[1]

    changed = _install(
        tmp_path,
        _seed(
            assignment_generation=4,
            assignment_digest=f"sha256:{'c' * 64}",
        ),
    )[1]

    assert original.record is not None
    assert changed.outcome is ProviderWorkAuthorityWriteOutcome.CONFLICT
    assert changed.record == original.record


def test_concurrent_create_has_one_record_and_only_replays(tmp_path) -> None:
    def create_once(_index: int):
        return _install(tmp_path)[1]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(create_once, range(16)))

    assert (
        sum(result.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED for result in results) == 1
    )
    assert all(
        result.outcome
        in {
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            ProviderWorkAuthorityWriteOutcome.REPLAYED,
        }
        for result in results
    )
    assert len({result.record.binding_digest for result in results if result.record}) == 1


def test_exact_current_binding_validation_fails_closed_after_revoke(tmp_path) -> None:
    store, created = _install(tmp_path)
    service = ProviderWorkBindingService(store)
    binding = created.record
    assert binding is not None

    with store.connection() as conn:
        assert store.validate_in_transaction(
            conn,
            binding_id=binding.binding_id,
            binding_generation=binding.generation,
            binding_digest=binding.binding_digest,
            owner_user_id="acct_alice",
            universe_id="universe_alice",
            provider="codex",
            operation="repository_spec_delivery",
            role="writer",
        )
        assert not store.validate_in_transaction(
            conn,
            binding_id=binding.binding_id,
            binding_generation=binding.generation,
            binding_digest=binding.binding_digest,
            owner_user_id="acct_other",
            universe_id="universe_alice",
            provider="codex",
            operation="repository_spec_delivery",
            role="writer",
        )

    revoked = service.revoke(ProviderWorkBindingFence(binding))
    assert revoked.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED
    assert revoked.record is not None
    assert revoked.record.state is ProviderWorkBindingState.REVOKED
    assert revoked.record.generation == binding.generation + 1
    assert revoked.record.revocation_generation == binding.revocation_generation + 1

    with store.connection() as conn:
        assert not store.validate_in_transaction(
            conn,
            binding_id=binding.binding_id,
            binding_generation=binding.generation,
            binding_digest=binding.binding_digest,
            owner_user_id="acct_alice",
            universe_id="universe_alice",
            provider="codex",
            operation="repository_spec_delivery",
            role="writer",
        )


def test_revoke_cas_has_one_winner(tmp_path) -> None:
    store, created = _install(tmp_path)
    binding = created.record
    assert binding is not None

    def revoke_once(_index: int):
        return ProviderWorkBindingService(
            SQLiteProviderWorkAuthorityStore(tmp_path),
        ).revoke(ProviderWorkBindingFence(binding))

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(revoke_once, range(8)))

    assert (
        sum(result.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED for result in results) == 1
    )
    assert all(result.record is not None for result in results)
    assert all(
        result.record.state is ProviderWorkBindingState.REVOKED
        for result in results
        if result.record
    )


def test_tampered_persisted_record_is_rejected_on_read(tmp_path) -> None:
    store, created = _install(tmp_path)
    binding = created.record
    assert binding is not None

    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            "UPDATE provider_work_bindings SET record_json = ? WHERE binding_id = ?",
            ("{}", binding.binding_id),
        )

    with pytest.raises(ValueError, match="persisted provider binding"):
        store.get(binding.binding_id)


def test_binding_state_cannot_be_forged_by_replace(tmp_path) -> None:
    _store, created = _install(tmp_path)
    binding = created.record
    assert binding is not None

    with pytest.raises(ValueError, match="revoked binding"):
        replace(binding, state=ProviderWorkBindingState.REVOKED)


def test_production_store_has_no_binding_installation_path(tmp_path) -> None:
    store = SQLiteProviderWorkAuthorityStore(tmp_path)

    with pytest.raises(PermissionError, match="test fixtures are disabled"):
        store.install_test_binding(_seed())
    assert not hasattr(ProviderWorkBindingService(store), "create")
    assert not hasattr(store, "issue_universe_receipt")
    with store.transaction() as transaction:
        assert not hasattr(transaction, "issue_universe_receipt")
        assert not hasattr(transaction, "claim_receipt")
        assert not hasattr(transaction, "reserve_invocation")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("owner_user_id", "acct_mallory"),
        ("allowed_roles", ("writer", "admin")),
    ],
)
def test_store_rejects_each_coherent_identity_or_scope_transfer(
    tmp_path,
    field: str,
    value: object,
) -> None:
    store, created = _install(tmp_path)
    binding = created.record
    assert binding is not None
    forged = replace(
        binding,
        generation=binding.generation + 1,
        binding_digest=f"sha256:{'0' * 64}",
        state=ProviderWorkBindingState.REVOKED,
        revocation_generation=binding.revocation_generation + 1,
        updated_at="2026-08-01T00:00:00Z",
        **{field: value},
    )
    forged = replace(forged, binding_digest=forged.expected_digest())

    with pytest.raises(ValueError, match="immutable|transition"):
        with store.transaction() as transaction:
            transaction.compare_and_swap(
                ProviderWorkBindingFence(binding),
                forged,
            )


class _UniverseWorkResolver:
    def __init__(self, authority: ProviderUniverseWorkAuthority | None) -> None:
        self.authority = authority

    def resolve(
        self,
        root: ProviderUniverseWorkRoot,
    ) -> ProviderUniverseWorkAuthority | None:
        if self.authority is None or self.authority.root != root:
            return None
        return self.authority


def _ledger_fixture(tmp_path):
    store = SQLiteProviderWorkAuthorityStore(
        tmp_path,
        clock=lambda: NOW,
        allow_test_fixtures=True,
    )
    binding = store.install_test_binding(_seed()).record
    assert binding is not None
    root = ProviderUniverseWorkRoot(
        work_item_kind="background_attempt",
        work_item_id="attempt_cloud_drain_1",
    )
    authority = ProviderUniverseWorkAuthority(
        root=root,
        binding=binding,
        actor_id="daemon_cloud_drain",
        branch_def_id="branch_cloud_drain",
        branch_version_id="branch_cloud_drain@abc12345",
        operation="repository_spec_delivery",
        role="writer",
        executor_class="cloud",
        max_invocations=2,
        max_tokens=80_000,
        max_cost_microunits=4_000_000,
        expires_at="2026-08-01T07:00:00.000000Z",
    )
    service = ProviderWorkReceiptService(
        store,
        _UniverseWorkResolver(authority),
    )
    return store, binding, root, authority, service


def test_universe_receipt_is_dark_bounded_and_restart_safe(tmp_path) -> None:
    store, binding, root, authority, service = _ledger_fixture(tmp_path)

    first = service.issue(root)
    replay = ProviderWorkReceiptService(
        SQLiteProviderWorkAuthorityStore(tmp_path, clock=lambda: NOW),
        _UniverseWorkResolver(authority),
    ).issue(root)

    assert first.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED
    assert replay.outcome is ProviderWorkAuthorityWriteOutcome.REPLAYED
    assert replay.record == first.record
    receipt = first.record
    assert receipt is not None
    assert receipt.state is ProviderWorkReceiptState.ACTIVE
    assert receipt.binding_id == binding.binding_id
    assert receipt.binding_generation == binding.generation
    assert receipt.work_item_id == root.work_item_id
    assert receipt.executor_class == "cloud"
    assert receipt.max_invocations == 2
    payload = receipt.to_dict()
    assert not {"credential", "credential_reference", "token"} & set(payload)
    assert payload["credential_reference_digest"] == (binding.credential_reference_digest)
    assert store.list_reservations(receipt.receipt_id) == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation", "unapproved_operation"),
        ("role", "admin"),
        ("max_invocations", 5),
        ("max_tokens", 100_001),
        ("max_cost_microunits", 5_000_001),
    ],
)
def test_universe_receipt_rejects_widened_authority(
    tmp_path,
    field: str,
    value: object,
) -> None:
    store, _binding, root, authority, _service = _ledger_fixture(tmp_path)
    widened = replace(authority, **{field: value})

    with pytest.raises(PermissionError, match="authority"):
        ProviderWorkReceiptService(
            store,
            _UniverseWorkResolver(widened),
        ).issue(root)


def test_universe_receipt_rejects_non_cloud_executor(tmp_path) -> None:
    _store, _binding, _root, authority, _service = _ledger_fixture(tmp_path)

    with pytest.raises(ValueError, match="executor_class must be cloud"):
        replace(authority, executor_class="host")


def test_concurrent_receipt_issue_has_one_record(tmp_path) -> None:
    _store, _binding, root, authority, _service = _ledger_fixture(tmp_path)

    def issue_once(_index: int):
        return ProviderWorkReceiptService(
            SQLiteProviderWorkAuthorityStore(tmp_path, clock=lambda: NOW),
            _UniverseWorkResolver(authority),
        ).issue(root)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(issue_once, range(12)))

    assert (
        sum(result.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED for result in results) == 1
    )
    assert all(
        result.outcome
        in {
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            ProviderWorkAuthorityWriteOutcome.REPLAYED,
        }
        for result in results
    )
    assert len({result.record for result in results}) == 1


def test_revoked_binding_cannot_issue_or_reserve(tmp_path) -> None:
    store, binding, root, _authority, service = _ledger_fixture(tmp_path)
    receipt = service.issue(root).record
    assert receipt is not None
    claim = store.claim(
        ProviderWorkExecutionClaimRequest(
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
            worker_id="worker_cloud_1",
            runtime_id="runtime_cloud_1",
            claim_nonce_digest=f"sha256:{'d' * 64}",
            lease_seconds=60,
        )
    ).record
    assert claim is not None
    ProviderWorkBindingService(store).revoke(ProviderWorkBindingFence(binding))

    with pytest.raises(PermissionError, match="binding"):
        service.issue(root)
    reserved = store.reserve(
        ProviderInvocationReservationRequest(
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
            claim_id=claim.claim_id,
            claim_digest=claim.claim_digest,
            claim_generation=claim.generation,
            invocation_key="attempt-1",
            operation="repository_spec_delivery",
            role="writer",
            max_tokens=20_000,
            max_cost_microunits=1_000_000,
        )
    )
    assert reserved.outcome is ProviderWorkAuthorityWriteOutcome.STALE
    assert reserved.record is None


def test_concurrent_claim_has_one_owner_and_same_request_replays(tmp_path) -> None:
    store, _binding, root, _authority, service = _ledger_fixture(tmp_path)
    receipt = service.issue(root).record
    assert receipt is not None

    def claim_once(index: int):
        return SQLiteProviderWorkAuthorityStore(
            tmp_path,
            clock=lambda: NOW,
        ).claim(
            ProviderWorkExecutionClaimRequest(
                receipt_id=receipt.receipt_id,
                receipt_digest=receipt.receipt_digest,
                worker_id=f"worker_cloud_{index}",
                runtime_id="runtime_cloud_1",
                claim_nonce_digest=f"sha256:{index:064x}",
                lease_seconds=60,
            )
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim_once, range(8)))

    assert (
        sum(result.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED for result in results) == 1
    )
    assert (
        sum(result.outcome is ProviderWorkAuthorityWriteOutcome.CONFLICT for result in results) == 7
    )
    winner = next(result.record for result in results if result.record)
    assert winner is not None
    replay = store.claim(
        ProviderWorkExecutionClaimRequest(
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
            worker_id=winner.worker_id,
            runtime_id=winner.runtime_id,
            claim_nonce_digest=winner.claim_nonce_digest,
            lease_seconds=60,
        )
    )
    assert replay.outcome is ProviderWorkAuthorityWriteOutcome.REPLAYED
    assert replay.record == winner


def test_reservations_conserve_invocation_token_and_cost_budgets(tmp_path) -> None:
    store, _binding, root, _authority, service = _ledger_fixture(tmp_path)
    receipt = service.issue(root).record
    assert receipt is not None
    claim = store.claim(
        ProviderWorkExecutionClaimRequest(
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
            worker_id="worker_cloud_1",
            runtime_id="runtime_cloud_1",
            claim_nonce_digest=f"sha256:{'e' * 64}",
            lease_seconds=60,
        )
    ).record
    assert claim is not None

    def reserve_once(index: int):
        return SQLiteProviderWorkAuthorityStore(
            tmp_path,
            clock=lambda: NOW,
        ).reserve(
            ProviderInvocationReservationRequest(
                receipt_id=receipt.receipt_id,
                receipt_digest=receipt.receipt_digest,
                claim_id=claim.claim_id,
                claim_digest=claim.claim_digest,
                claim_generation=claim.generation,
                invocation_key=f"attempt-{index}",
                operation="repository_spec_delivery",
                role="writer",
                max_tokens=40_000,
                max_cost_microunits=2_000_000,
            )
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve_once, range(8)))

    assert (
        sum(result.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED for result in results) == 2
    )
    assert (
        sum(result.outcome is ProviderWorkAuthorityWriteOutcome.EXHAUSTED for result in results)
        == 6
    )
    reservations = store.list_reservations(receipt.receipt_id)
    assert tuple(item.ordinal for item in reservations) == (1, 2)
    assert all(item.claim_digest == claim.claim_digest for item in reservations)
    assert sum(item.max_tokens for item in reservations) == receipt.max_tokens
    assert sum(item.max_cost_microunits for item in reservations) == (receipt.max_cost_microunits)
    replay = store.reserve(
        ProviderInvocationReservationRequest(
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
            claim_id=claim.claim_id,
            claim_digest=claim.claim_digest,
            claim_generation=claim.generation,
            invocation_key=reservations[0].invocation_key,
            operation="repository_spec_delivery",
            role="writer",
            max_tokens=40_000,
            max_cost_microunits=2_000_000,
        )
    )
    assert replay.outcome is ProviderWorkAuthorityWriteOutcome.REPLAYED


def test_expired_claim_cannot_replay_or_reserve(tmp_path) -> None:
    store, _binding, root, _authority, service = _ledger_fixture(tmp_path)
    receipt = service.issue(root).record
    assert receipt is not None
    request = ProviderWorkExecutionClaimRequest(
        receipt_id=receipt.receipt_id,
        receipt_digest=receipt.receipt_digest,
        worker_id="worker_cloud_1",
        runtime_id="runtime_cloud_1",
        claim_nonce_digest=f"sha256:{'f' * 64}",
        lease_seconds=60,
    )
    claim = store.claim(request).record
    assert claim is not None
    later = SQLiteProviderWorkAuthorityStore(
        tmp_path,
        clock=lambda: NOW + timedelta(minutes=2),
    )

    replay = later.claim(request)
    reserved = later.reserve(
        ProviderInvocationReservationRequest(
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
            claim_id=claim.claim_id,
            claim_digest=claim.claim_digest,
            claim_generation=claim.generation,
            invocation_key="attempt-expired",
            operation="repository_spec_delivery",
            role="writer",
            max_tokens=1,
            max_cost_microunits=1,
        )
    )

    assert replay.outcome is ProviderWorkAuthorityWriteOutcome.STALE
    assert reserved.outcome is ProviderWorkAuthorityWriteOutcome.STALE
    assert later.list_reservations(receipt.receipt_id) == ()


@pytest.mark.parametrize("record_kind", ["receipt", "claim", "reservation"])
def test_tampered_ledger_record_fails_closed(
    tmp_path,
    record_kind: str,
) -> None:
    store, _binding, root, _authority, service = _ledger_fixture(tmp_path)
    receipt = service.issue(root).record
    assert receipt is not None
    claim = store.claim(
        ProviderWorkExecutionClaimRequest(
            receipt_id=receipt.receipt_id,
            receipt_digest=receipt.receipt_digest,
            worker_id="worker_cloud_1",
            runtime_id="runtime_cloud_1",
            claim_nonce_digest=f"sha256:{'1' * 64}",
            lease_seconds=60,
        )
    ).record
    assert claim is not None
    reservation_request = ProviderInvocationReservationRequest(
        receipt_id=receipt.receipt_id,
        receipt_digest=receipt.receipt_digest,
        claim_id=claim.claim_id,
        claim_digest=claim.claim_digest,
        claim_generation=claim.generation,
        invocation_key="attempt-tamper",
        operation="repository_spec_delivery",
        role="writer",
        max_tokens=1,
        max_cost_microunits=1,
    )
    reservation = store.reserve(reservation_request).record
    assert reservation is not None
    table, identifier_column, identifier = {
        "receipt": (
            "provider_work_receipts",
            "receipt_id",
            receipt.receipt_id,
        ),
        "claim": (
            "provider_work_execution_claims",
            "claim_id",
            claim.claim_id,
        ),
        "reservation": (
            "provider_invocation_reservations",
            "reservation_id",
            reservation.reservation_id,
        ),
    }[record_kind]
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            f"UPDATE {table} SET record_json = ? WHERE {identifier_column} = ?",
            ("{}", identifier),
        )

    with pytest.raises(ValueError, match="persisted provider"):
        if record_kind == "receipt":
            store.get_receipt(receipt.receipt_id)
        elif record_kind == "claim":
            store.reserve(reservation_request)
        else:
            store.list_reservations(receipt.receipt_id)
