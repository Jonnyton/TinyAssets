from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace

import pytest

from tinyassets.provider_work_authority import (
    ProviderWorkAuthorityWriteOutcome,
    ProviderWorkBindingFence,
    ProviderWorkBindingSeed,
    ProviderWorkBindingService,
    ProviderWorkBindingState,
)
from tinyassets.storage import db_path
from tinyassets.storage.provider_work_authority import (
    SQLiteProviderWorkAuthorityStore,
)


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

    changed = _install(tmp_path, _seed(
        assignment_generation=4,
        assignment_digest=f"sha256:{'c' * 64}",
    ))[1]

    assert original.record is not None
    assert changed.outcome is ProviderWorkAuthorityWriteOutcome.CONFLICT
    assert changed.record == original.record


def test_concurrent_create_has_one_record_and_only_replays(tmp_path) -> None:
    def create_once(_index: int):
        return _install(tmp_path)[1]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(create_once, range(16)))

    assert sum(
        result.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED
        for result in results
    ) == 1
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

    assert sum(
        result.outcome is ProviderWorkAuthorityWriteOutcome.APPLIED
        for result in results
    ) == 1
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

    import sqlite3

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
