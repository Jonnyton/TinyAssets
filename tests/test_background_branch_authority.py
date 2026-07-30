from __future__ import annotations

import copy

import pytest

from tinyassets.background_branch_authority import (
    BackgroundBranchAttempt,
    BackgroundBranchAttemptLifecycle,
    BackgroundBranchBinding,
    BackgroundBranchBindingStatus,
    BackgroundBranchHoldReason,
    BackgroundBranchProvenance,
    BackgroundBranchSourceKind,
    BackgroundBranchTargetMode,
)


def _binding_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "binding_id": "bnd_01",
        "status": "active",
        "generation": 3,
        "binding_digest": "sha256:binding",
        "authorizing_principal_id": "acct_jonathan",
        "universe_id": "universe_main",
        "branch_def_id": "branch_spec_drain",
        "operation": "invoke_branch_version",
        "source_kind": "request_admission",
        "source_id": "request_17",
        "source_revision": "4",
        "source_digest": "sha256:source",
        "revocation_generation": 0,
        "target_mode": "pinned_version",
        "pinned_branch_version_id": "branch_spec_drain@abc12345",
        "permitted_executor_classes": ["cloud"],
        "daemon_id": "daemon_spec_drain",
        "runtime_id": None,
        "expires_at": "2026-08-30T00:00:00Z",
        "max_attempts": 25,
        "remaining_depth": 4,
        "remaining_count": 24,
        "remaining_cost_microunits": 5_000_000,
        "child_delegation": {
            "allowed_branch_def_ids": ["branch_review"],
            "allowed_operations": ["invoke_branch_version"],
        },
    }


def _provenance_payload() -> dict[str, object]:
    return {
        "authorizing_principal_id": "acct_jonathan",
        "source_kind": "request_admission",
        "source_id": "request_17",
        "executor_class": "cloud",
        "daemon_id": "daemon_spec_drain",
        "runtime_id": "runtime_cloud_1",
        "worker_id": "worker_codex_1",
        "parent_attempt_id": None,
        "origin_attempt_id": "att_01",
        "audit_correlation_ids": ["request:17", "trace:abc"],
        "receipt_refs": {
            "provider_work": "pwr_01",
            "provider_attempt": "pat_01",
        },
    }


def _attempt_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "attempt_id": "att_01",
        "logical_attempt_key": "request:17:g4:body-deadbeef",
        "binding_id": "bnd_01",
        "binding_digest": "sha256:binding",
        "binding_generation": 3,
        "authorizing_principal_id": "acct_jonathan",
        "universe_id": "universe_main",
        "branch_def_id": "branch_spec_drain",
        "branch_version_id": "branch_spec_drain@abc12345",
        "branch_content_digest": "sha256:branch",
        "operation": "invoke_branch_version",
        "source_kind": "request_admission",
        "source_id": "request_17",
        "source_generation": 4,
        "executor_audience": "cloud:worker_codex",
        "claim_generation": 2,
        "lease_generation": 5,
        "lease_expires_at": "2026-07-30T08:00:00Z",
        "remaining_depth": 4,
        "remaining_count": 24,
        "remaining_cost_microunits": 5_000_000,
        "lifecycle": "claimed",
        "hold_reason": None,
        "terminal_reason": None,
        "created_at": "2026-07-30T07:00:00Z",
        "updated_at": "2026-07-30T07:01:00Z",
        "provenance": _provenance_payload(),
    }


def test_binding_round_trip_is_lossless_and_typed() -> None:
    payload = _binding_payload()

    binding = BackgroundBranchBinding.from_dict(payload)

    assert binding.status is BackgroundBranchBindingStatus.ACTIVE
    assert binding.source_kind is BackgroundBranchSourceKind.REQUEST_ADMISSION
    assert binding.target_mode is BackgroundBranchTargetMode.PINNED_VERSION
    assert binding.to_dict() == payload
    assert BackgroundBranchBinding.from_dict(binding.to_dict()) == binding


def test_attempt_round_trip_is_lossless_and_keeps_authorizer_separate() -> None:
    payload = _attempt_payload()

    attempt = BackgroundBranchAttempt.from_dict(payload)

    assert attempt.lifecycle is BackgroundBranchAttemptLifecycle.CLAIMED
    assert attempt.provenance.authorizing_principal_id == "acct_jonathan"
    assert attempt.provenance.worker_id == "worker_codex_1"
    assert attempt.to_dict() == payload
    assert BackgroundBranchAttempt.from_dict(attempt.to_dict()) == attempt


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("binding_id", ""),
        ("generation", 0),
        ("status", "invented"),
        ("source_kind", "wiki_filing"),
        ("target_mode", "latest"),
        ("permitted_executor_classes", []),
        ("remaining_cost_microunits", -1),
    ],
)
def test_binding_rejects_malformed_or_open_ended_values(field: str, value: object) -> None:
    payload = _binding_payload()
    payload[field] = value

    with pytest.raises(ValueError):
        BackgroundBranchBinding.from_dict(payload)


def test_binding_rejects_unknown_or_missing_fields() -> None:
    unknown = _binding_payload()
    unknown["owner_actor"] = "ambient-maintainer"
    missing = _binding_payload()
    del missing["authorizing_principal_id"]

    with pytest.raises(ValueError, match="unknown fields"):
        BackgroundBranchBinding.from_dict(unknown)
    with pytest.raises(ValueError, match="missing fields"):
        BackgroundBranchBinding.from_dict(missing)


def test_target_mode_requires_exactly_the_matching_version_shape() -> None:
    live = _binding_payload()
    live["target_mode"] = "live_at_attempt"
    live["pinned_branch_version_id"] = None
    assert BackgroundBranchBinding.from_dict(live).target_mode is (
        BackgroundBranchTargetMode.LIVE_AT_ATTEMPT
    )

    pinned_without_version = _binding_payload()
    pinned_without_version["pinned_branch_version_id"] = None
    live_with_version = copy.deepcopy(live)
    live_with_version["pinned_branch_version_id"] = "branch@abc12345"

    with pytest.raises(ValueError):
        BackgroundBranchBinding.from_dict(pinned_without_version)
    with pytest.raises(ValueError):
        BackgroundBranchBinding.from_dict(live_with_version)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("attempt_id", ""),
        ("logical_attempt_key", ""),
        ("binding_generation", 0),
        ("source_generation", -1),
        ("claim_generation", 0),
        ("lease_generation", 0),
        ("remaining_count", -1),
        ("lifecycle", "invented"),
    ],
)
def test_attempt_rejects_malformed_or_open_ended_values(field: str, value: object) -> None:
    payload = _attempt_payload()
    payload[field] = value

    with pytest.raises(ValueError):
        BackgroundBranchAttempt.from_dict(payload)


def test_hold_lifecycle_requires_typed_reason_and_non_hold_forbids_it() -> None:
    held = _attempt_payload()
    held["lifecycle"] = "target_authority_held"
    held["hold_reason"] = "principal_revoked"
    held["lease_expires_at"] = None
    attempt = BackgroundBranchAttempt.from_dict(held)
    assert attempt.hold_reason is BackgroundBranchHoldReason.PRINCIPAL_REVOKED

    held_without_reason = copy.deepcopy(held)
    held_without_reason["hold_reason"] = None
    active_with_reason = _attempt_payload()
    active_with_reason["hold_reason"] = "target_changed"

    with pytest.raises(ValueError):
        BackgroundBranchAttempt.from_dict(held_without_reason)
    with pytest.raises(ValueError):
        BackgroundBranchAttempt.from_dict(active_with_reason)


def test_terminal_lifecycle_requires_reason_and_active_forbids_it() -> None:
    failed = _attempt_payload()
    failed["lifecycle"] = "failed"
    failed["terminal_reason"] = "branch_validation_failed"
    failed["lease_expires_at"] = None
    assert BackgroundBranchAttempt.from_dict(failed).terminal_reason == ("branch_validation_failed")

    failed_without_reason = copy.deepcopy(failed)
    failed_without_reason["terminal_reason"] = None
    active_with_reason = _attempt_payload()
    active_with_reason["terminal_reason"] = "not-terminal"

    with pytest.raises(ValueError):
        BackgroundBranchAttempt.from_dict(failed_without_reason)
    with pytest.raises(ValueError):
        BackgroundBranchAttempt.from_dict(active_with_reason)


def test_provenance_is_strict_and_receipts_are_non_bearer_references() -> None:
    provenance = BackgroundBranchProvenance.from_dict(_provenance_payload())
    assert provenance.receipt_refs == {
        "provider_work": "pwr_01",
        "provider_attempt": "pat_01",
    }

    unknown = _provenance_payload()
    unknown["credential"] = "secret"
    malformed_receipt = _provenance_payload()
    malformed_receipt["receipt_refs"] = {"provider_work": ""}

    with pytest.raises(ValueError, match="unknown fields"):
        BackgroundBranchProvenance.from_dict(unknown)
    with pytest.raises(ValueError):
        BackgroundBranchProvenance.from_dict(malformed_receipt)


def test_nested_policy_and_receipt_data_cannot_mutate_records() -> None:
    binding_payload = _binding_payload()
    binding = BackgroundBranchBinding.from_dict(binding_payload)
    provenance_payload = _provenance_payload()
    provenance = BackgroundBranchProvenance.from_dict(provenance_payload)

    binding_payload["child_delegation"]["allowed_branch_def_ids"].append("evil")
    provenance_payload["receipt_refs"]["provider_work"] = "replaced"

    assert binding.to_dict()["child_delegation"]["allowed_branch_def_ids"] == ["branch_review"]
    assert provenance.to_dict()["receipt_refs"]["provider_work"] == "pwr_01"
    with pytest.raises(TypeError):
        binding.child_delegation["new_policy"] = True
    with pytest.raises(TypeError):
        provenance.receipt_refs["provider_work"] = "replaced"
