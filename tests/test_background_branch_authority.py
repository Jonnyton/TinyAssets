from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace

import pytest

from tinyassets.background_branch_authority import (
    BackgroundBranchAttempt,
    BackgroundBranchAttemptLifecycle,
    BackgroundBranchBinding,
    BackgroundBranchBindingStatus,
    BackgroundBranchExecutorClass,
    BackgroundBranchHoldReason,
    BackgroundBranchOperation,
    BackgroundBranchProvenance,
    BackgroundBranchSourceKind,
    BackgroundBranchTargetMode,
)

_BINDING_DIGEST = f"sha256:{'a' * 64}"
_SOURCE_DIGEST = f"sha256:{'b' * 64}"
_BRANCH_CONTENT_DIGEST = f"sha256:{'c' * 64}"


def _binding_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "binding_id": "bnd_01",
        "status": "active",
        "generation": 3,
        "binding_digest": _BINDING_DIGEST,
        "authorizing_principal_id": "acct_jonathan",
        "universe_id": "universe_main",
        "branch_def_id": "branch_spec_drain",
        "operation": "invoke_branch_version",
        "source_kind": "request_admission",
        "source_id": "request_17",
        "source_revision": "4",
        "source_digest": _SOURCE_DIGEST,
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
            "max_depth": 2,
            "max_count": 4,
            "max_cost_microunits": 1_000_000,
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
            "b2_execution_grant_id": None,
            "provider_work_receipt_id": "pwr_01",
            "provider_attempt_receipt_id": "pat_01",
            "payment_receipt_id": None,
            "effect_receipt_id": None,
        },
    }


def _attempt_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "attempt_id": "att_01",
        "logical_attempt_key": "request:17:g4:body-deadbeef",
        "binding_id": "bnd_01",
        "binding_digest": _BINDING_DIGEST,
        "binding_generation": 3,
        "authorizing_principal_id": "acct_jonathan",
        "universe_id": "universe_main",
        "branch_def_id": "branch_spec_drain",
        "branch_version_id": "branch_spec_drain@abc12345",
        "branch_content_digest": _BRANCH_CONTENT_DIGEST,
        "operation": "invoke_branch_version",
        "source_kind": "request_admission",
        "source_id": "request_17",
        "source_generation": 4,
        "executor_audience": {
            "executor_class": "cloud",
            "daemon_id": "daemon_spec_drain",
            "runtime_id": "runtime_cloud_1",
            "worker_id": "worker_codex_1",
        },
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
    assert binding.operation is BackgroundBranchOperation.INVOKE_BRANCH_VERSION
    assert binding.permitted_executor_classes == (BackgroundBranchExecutorClass.CLOUD,)
    assert binding.to_dict() == payload
    assert BackgroundBranchBinding.from_dict(binding.to_dict()) == binding


def test_attempt_round_trip_is_lossless_and_keeps_authorizer_separate() -> None:
    payload = _attempt_payload()

    attempt = BackgroundBranchAttempt.from_dict(payload)

    assert attempt.lifecycle is BackgroundBranchAttemptLifecycle.CLAIMED
    assert attempt.executor_audience.executor_class is (BackgroundBranchExecutorClass.CLOUD)
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
    assert provenance.receipt_refs.provider_work_receipt_id == "pwr_01"
    assert provenance.receipt_refs.provider_attempt_receipt_id == "pat_01"

    unknown = _provenance_payload()
    unknown["credential"] = "secret"
    malformed_receipt = _provenance_payload()
    malformed_receipt["receipt_refs"]["provider_work_receipt_id"] = "Bearer sk-live-secret"

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
    provenance_payload["receipt_refs"]["provider_work_receipt_id"] = "replaced"

    assert binding.to_dict()["child_delegation"]["allowed_branch_def_ids"] == ["branch_review"]
    assert provenance.to_dict()["receipt_refs"]["provider_work_receipt_id"] == "pwr_01"
    with pytest.raises(FrozenInstanceError):
        binding.child_delegation.max_count = 99
    with pytest.raises(FrozenInstanceError):
        provenance.receipt_refs.provider_work_receipt_id = "replaced"


def test_direct_constructors_copy_retained_sequences() -> None:
    binding = BackgroundBranchBinding.from_dict(_binding_payload())
    provenance = BackgroundBranchProvenance.from_dict(_provenance_payload())
    executor_classes = [BackgroundBranchExecutorClass.CLOUD]
    correlation_ids = ["trace:abc"]

    direct_binding = replace(binding, permitted_executor_classes=executor_classes)
    direct_provenance = replace(provenance, audit_correlation_ids=correlation_ids)
    executor_classes.append(BackgroundBranchExecutorClass.HOST)
    correlation_ids.append("trace:evil")

    assert direct_binding.permitted_executor_classes == (BackgroundBranchExecutorClass.CLOUD,)
    assert direct_provenance.audit_correlation_ids == ("trace:abc",)


def test_serialized_sequence_fields_require_json_lists() -> None:
    binding = _binding_payload()
    binding["permitted_executor_classes"] = ("cloud",)
    child = _binding_payload()
    child["child_delegation"]["allowed_operations"] = ("invoke_branch_version",)

    with pytest.raises(ValueError, match="list"):
        BackgroundBranchBinding.from_dict(binding)
    with pytest.raises(ValueError, match="list"):
        BackgroundBranchBinding.from_dict(child)


def test_direct_constructors_reject_string_sequences() -> None:
    binding = BackgroundBranchBinding.from_dict(_binding_payload())
    provenance = BackgroundBranchProvenance.from_dict(_provenance_payload())

    with pytest.raises(ValueError, match="sequence"):
        replace(binding.child_delegation, allowed_branch_def_ids="ab")
    with pytest.raises(ValueError, match="sequence"):
        replace(provenance, audit_correlation_ids="trace")


def test_policy_and_receipt_schemas_reject_secret_shaped_material() -> None:
    binding = _binding_payload()
    binding["child_delegation"]["api_token"] = "sk-live-secret"
    receipt = _provenance_payload()
    receipt["receipt_refs"]["effect_receipt_id"] = "sk-live-secret"

    with pytest.raises(ValueError, match="unknown fields"):
        BackgroundBranchBinding.from_dict(binding)
    with pytest.raises(ValueError, match="reference"):
        BackgroundBranchProvenance.from_dict(receipt)


@pytest.mark.parametrize(
    "field",
    [
        "b2_execution_grant_id",
        "provider_work_receipt_id",
        "provider_attempt_receipt_id",
        "payment_receipt_id",
        "effect_receipt_id",
    ],
)
@pytest.mark.parametrize(
    "bearer",
    [
        "xoxb-123456789-secret",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
    ],
)
def test_receipt_fields_require_kind_specific_nominal_references(
    field: str,
    bearer: str,
) -> None:
    payload = _provenance_payload()
    payload["receipt_refs"][field] = bearer

    with pytest.raises(ValueError, match="reference"):
        BackgroundBranchProvenance.from_dict(payload)


def test_all_receipt_reference_kinds_have_closed_valid_shapes() -> None:
    payload = _provenance_payload()
    payload["receipt_refs"] = {
        "b2_execution_grant_id": "b2g_01",
        "provider_work_receipt_id": "pwr_01",
        "provider_attempt_receipt_id": "pat_01",
        "payment_receipt_id": "pay_01",
        "effect_receipt_id": "eff_01",
    }

    assert BackgroundBranchProvenance.from_dict(payload).to_dict() == payload


@pytest.mark.parametrize(
    ("record", "field"),
    [
        ("binding", "source_id"),
        ("provenance", "source_id"),
        ("provenance", "audit_correlation_ids"),
    ],
)
@pytest.mark.parametrize(
    "bearer",
    [
        "xoxb-123456789-secret",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature",
    ],
)
def test_generic_authority_references_require_nominal_domain_prefixes(
    record: str,
    field: str,
    bearer: str,
) -> None:
    if record == "binding":
        payload = _binding_payload()
        payload[field] = bearer
        parser = BackgroundBranchBinding.from_dict
    else:
        payload = _provenance_payload()
        payload[field] = [bearer] if field == "audit_correlation_ids" else bearer
        parser = BackgroundBranchProvenance.from_dict

    with pytest.raises(ValueError, match="reference"):
        parser(payload)


@pytest.mark.parametrize("revision", ["04", "-1", "latest", "xoxb-123-secret"])
def test_source_revision_is_a_canonical_decimal_generation(revision: str) -> None:
    payload = _binding_payload()
    payload["source_revision"] = revision

    with pytest.raises(ValueError, match="revision"):
        BackgroundBranchBinding.from_dict(payload)


@pytest.mark.parametrize(
    "field",
    [
        "binding_id",
        "binding_digest",
        "authorizing_principal_id",
        "universe_id",
        "branch_def_id",
        "source_id",
        "source_revision",
        "source_digest",
        "pinned_branch_version_id",
        "daemon_id",
        "runtime_id",
    ],
)
def test_binding_ids_digests_and_source_fields_reject_bearer_material(field: str) -> None:
    payload = _binding_payload()
    payload[field] = "Bearer sk-live-secret"

    with pytest.raises(ValueError, match="reference|revision|SHA-256"):
        BackgroundBranchBinding.from_dict(payload)


@pytest.mark.parametrize(
    "field",
    [
        "attempt_id",
        "logical_attempt_key",
        "binding_id",
        "binding_digest",
        "authorizing_principal_id",
        "universe_id",
        "branch_def_id",
        "branch_version_id",
        "branch_content_digest",
        "source_id",
    ],
)
def test_attempt_ids_digests_and_source_fields_reject_bearer_material(field: str) -> None:
    payload = _attempt_payload()
    payload[field] = "Bearer sk-live-secret"
    if field in {"authorizing_principal_id", "source_id"}:
        payload["provenance"][field] = "Bearer sk-live-secret"

    with pytest.raises(ValueError, match="reference|SHA-256"):
        BackgroundBranchAttempt.from_dict(payload)


@pytest.mark.parametrize("field", ["authorizing_principal_id", "source_id"])
def test_provenance_identity_fields_reject_bearer_material(field: str) -> None:
    payload = _provenance_payload()
    payload[field] = "Bearer sk-live-secret"

    with pytest.raises(ValueError, match="reference"):
        BackgroundBranchProvenance.from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation", "admin_everything"),
        ("permitted_executor_classes", ["ambient-maintainer"]),
    ],
)
def test_binding_rejects_open_authority_vocabulary(field: str, value: object) -> None:
    payload = _binding_payload()
    payload[field] = value

    with pytest.raises(ValueError):
        BackgroundBranchBinding.from_dict(payload)


def test_binding_rejects_queue_claim_as_issuance_root() -> None:
    payload = _binding_payload()
    payload["source_kind"] = "claimed_task"

    with pytest.raises(ValueError, match="issuance root"):
        BackgroundBranchBinding.from_dict(payload)


def test_child_delegation_cannot_grant_resume_authority() -> None:
    payload = _binding_payload()
    payload["child_delegation"]["allowed_operations"] = ["resume_run"]

    with pytest.raises(ValueError, match="child delegation"):
        BackgroundBranchBinding.from_dict(payload)


def test_resume_binding_requires_resumed_run_source_and_pinned_target() -> None:
    wrong_source = _binding_payload()
    wrong_source["operation"] = "resume_run"
    live_resume = _binding_payload()
    live_resume["operation"] = "resume_run"
    live_resume["source_kind"] = "resumed_run"
    live_resume["target_mode"] = "live_at_attempt"
    live_resume["pinned_branch_version_id"] = None
    resumed_with_invoke = _binding_payload()
    resumed_with_invoke["source_kind"] = "resumed_run"

    with pytest.raises(ValueError, match="resumed_run source"):
        BackgroundBranchBinding.from_dict(wrong_source)
    with pytest.raises(ValueError, match="pinned"):
        BackgroundBranchBinding.from_dict(live_resume)
    with pytest.raises(ValueError, match="resume_run operation"):
        BackgroundBranchBinding.from_dict(resumed_with_invoke)

    valid = _binding_payload()
    valid["operation"] = "resume_run"
    valid["source_kind"] = "resumed_run"
    assert BackgroundBranchBinding.from_dict(valid).operation is (
        BackgroundBranchOperation.RESUME_RUN
    )


def test_resume_attempt_requires_resumed_run_source() -> None:
    wrong_source = _attempt_payload()
    wrong_source["operation"] = "resume_run"
    wrong_source["provenance"]["source_kind"] = "request_admission"
    resumed_with_invoke = _attempt_payload()
    resumed_with_invoke["source_kind"] = "resumed_run"
    resumed_with_invoke["provenance"]["source_kind"] = "resumed_run"

    with pytest.raises(ValueError, match="resumed_run source"):
        BackgroundBranchAttempt.from_dict(wrong_source)
    with pytest.raises(ValueError, match="resume_run operation"):
        BackgroundBranchAttempt.from_dict(resumed_with_invoke)

    valid = _attempt_payload()
    valid["operation"] = "resume_run"
    valid["source_kind"] = "resumed_run"
    valid["provenance"]["source_kind"] = "resumed_run"
    assert (
        BackgroundBranchAttempt.from_dict(valid).operation is BackgroundBranchOperation.RESUME_RUN
    )


@pytest.mark.parametrize("field", ["binding_digest", "source_digest"])
@pytest.mark.parametrize(
    "value",
    [
        "sha256:not-a-digest",
        "sk_live_raw_secret",
        f"sha256:{'A' * 64}",
        f"sha256:{'0' * 63}",
    ],
)
def test_binding_digest_fields_require_canonical_sha256(field: str, value: str) -> None:
    payload = _binding_payload()
    payload[field] = value

    with pytest.raises(ValueError, match="SHA-256"):
        BackgroundBranchBinding.from_dict(payload)


@pytest.mark.parametrize("field", ["binding_digest", "branch_content_digest"])
def test_attempt_digest_fields_require_canonical_sha256(field: str) -> None:
    payload = _attempt_payload()
    payload[field] = "sk_live_raw_secret"

    with pytest.raises(ValueError, match="SHA-256"):
        BackgroundBranchAttempt.from_dict(payload)


@pytest.mark.parametrize("value", ["never", "2026-07-30", "2026-07-30T08:00:00+00:00"])
def test_binding_expiry_requires_canonical_utc_timestamp(value: str) -> None:
    payload = _binding_payload()
    payload["expires_at"] = value

    with pytest.raises(ValueError, match="UTC timestamp"):
        BackgroundBranchBinding.from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("created_at", "not-a-timestamp"),
        ("updated_at", "2026-07-30T07:01:00+00:00"),
        ("lease_expires_at", "later"),
    ],
)
def test_attempt_timestamps_require_canonical_utc(field: str, value: str) -> None:
    payload = _attempt_payload()
    payload[field] = value

    with pytest.raises(ValueError, match="UTC timestamp"):
        BackgroundBranchAttempt.from_dict(payload)


def test_attempt_timestamps_obey_creation_update_and_lease_order() -> None:
    update_before_creation = _attempt_payload()
    update_before_creation["updated_at"] = "2026-07-30T06:59:59Z"
    expired_lease = _attempt_payload()
    expired_lease["lease_expires_at"] = expired_lease["updated_at"]

    with pytest.raises(ValueError, match="updated_at"):
        BackgroundBranchAttempt.from_dict(update_before_creation)
    with pytest.raises(ValueError, match="lease"):
        BackgroundBranchAttempt.from_dict(expired_lease)


def test_attempt_audience_must_match_provenance_executor() -> None:
    wrong_class = _attempt_payload()
    wrong_class["provenance"]["executor_class"] = "host"
    wrong_worker = _attempt_payload()
    wrong_worker["provenance"]["worker_id"] = "worker_other"

    with pytest.raises(ValueError, match="executor"):
        BackgroundBranchAttempt.from_dict(wrong_class)
    with pytest.raises(ValueError, match="executor"):
        BackgroundBranchAttempt.from_dict(wrong_worker)


def test_lineage_distinguishes_root_and_child_attempts() -> None:
    bad_root = _attempt_payload()
    bad_root["provenance"]["origin_attempt_id"] = "att_unrelated"
    child_without_parent = _attempt_payload()
    child_without_parent["source_kind"] = "direct_child"
    child_without_parent["provenance"]["source_kind"] = "direct_child"

    with pytest.raises(ValueError, match="root"):
        BackgroundBranchAttempt.from_dict(bad_root)
    with pytest.raises(ValueError, match="parent"):
        BackgroundBranchAttempt.from_dict(child_without_parent)

    child = copy.deepcopy(child_without_parent)
    child["provenance"]["parent_attempt_id"] = "att_parent"
    child["provenance"]["origin_attempt_id"] = "att_root"
    assert BackgroundBranchAttempt.from_dict(child).provenance.parent_attempt_id == ("att_parent")


def test_parent_attempt_source_is_bound_to_parent_lineage() -> None:
    child = _attempt_payload()
    child["source_kind"] = "parent_attempt"
    child["source_id"] = "att_unrelated"
    child["provenance"]["source_kind"] = "parent_attempt"
    child["provenance"]["source_id"] = "att_unrelated"
    child["provenance"]["parent_attempt_id"] = "att_parent"
    child["provenance"]["origin_attempt_id"] = "att_root"

    with pytest.raises(ValueError, match="parent source"):
        BackgroundBranchAttempt.from_dict(child)

    child["source_id"] = "att_parent"
    child["provenance"]["source_id"] = "att_parent"
    assert BackgroundBranchAttempt.from_dict(child).provenance.parent_attempt_id == "att_parent"


def test_descendant_count_budget_is_independent_of_max_attempts() -> None:
    payload = _binding_payload()
    payload["max_attempts"] = 1
    payload["remaining_count"] = 100

    binding = BackgroundBranchBinding.from_dict(payload)

    assert binding.max_attempts == 1
    assert binding.remaining_count == 100
