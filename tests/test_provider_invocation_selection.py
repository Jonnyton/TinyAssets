"""Selected work records are exact, immutable and still non-authorizing."""

import json
from dataclasses import FrozenInstanceError, replace

import pytest

from tests.test_provider_work_authority import NOW, _armed_carrier_result
from tinyassets.provider_work_authority import (
    ProviderInvocationReservation,
    ProviderInvocationReservationRequest,
    ProviderInvocationReservationState,
    ProviderInvocationSelection,
    ProviderInvocationSettlementOwner,
    _canonical_json,
    _mint_provider_invocation_carrier,
    _reservation_from_request,
)
from tinyassets.storage.provider_work_authority import (
    SQLiteProviderWorkAuthorityStore,
    _provider_invocation_store_mint_proof,
)

DIGEST = "sha256:" + "a" * 64


def selection(**overrides):
    fields = dict(
        provider="native_source", binding_id="binding_source", binding_generation=2,
        binding_digest=DIGEST, binding_revocation_generation=0,
        credential_reference_id="credential_source", credential_reference_generation=3,
        credential_reference_digest=DIGEST, assignment_generation=4,
        assignment_digest=DIGEST, manifest_digest=DIGEST, member_digest=DIGEST,
        model_id="", executor_id="native_executor",
    )
    fields.update(overrides)
    return ProviderInvocationSelection(**fields)


def request(**overrides):
    fields = dict(
        receipt_id="receipt", receipt_digest=DIGEST, claim_id="claim",
        claim_digest=DIGEST, claim_generation=1, invocation_key="node1:attempt1",
        operation="run_graph", role="writer", max_tokens=100, max_cost_microunits=50,
    )
    fields.update(overrides)
    return ProviderInvocationReservationRequest(**fields)


def reservation(**overrides):
    return _reservation_from_request(
        request(**overrides), ordinal=1, created_at="2026-08-01T06:00:00Z",
    )


def http_selection():
    from tinyassets.providers.discovery_protocols import discovery_protocol

    contract = discovery_protocol("openrouter_user_models_v1")
    evidence = dict(
        discovery_protocol="openrouter_user_models_v1", source_digest="b" * 64,
        context_tokens=32000,
        supports_tools=True, cost_caps=dict.fromkeys(contract.price_components, 0),
        execution_contract={"kind": "installed", "value": "openrouter_user_models_v1"},
        observed_at="2026-08-01T06:00:00Z", completed_at="2026-08-01T06:00:01Z",
    )
    return selection(
        provider="api_key_http:source", model_id="vendor/new-model",
        executor_id=contract.inference_protocol, model_evidence_json=_canonical_json(evidence),
    )


@pytest.mark.parametrize("make_selection", [selection, http_selection])
def test_selected_reservation_roundtrip_and_immutable_evidence(make_selection):
    chosen = make_selection()
    record = reservation(selection=chosen)
    assert record.schema_version == 3
    restored = ProviderInvocationReservation.from_dict(json.loads(json.dumps(record.to_dict())))
    assert restored == record
    assert record.reservation_digest == record.expected_digest()
    changed = replace(record, selection=replace(chosen, model_id="another-model"))
    assert changed.expected_digest() != record.expected_digest()
    with pytest.raises(FrozenInstanceError):
        chosen.model_id = "mutated"
    document = chosen.to_dict()
    document["model_id"] = "mutated"
    if document["model_evidence"] is not None:
        document["model_evidence"]["cost_caps"].clear()
        assert chosen.model_evidence()["cost_caps"]
    assert chosen.model_id != "mutated"


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_reservation_wire_stays_exact(version):
    record = replace(reservation(), schema_version=version)
    document = record.to_dict()
    assert "selection" not in document
    assert ("actual_total_tokens" in document) == (version == 2)
    assert ProviderInvocationReservation.from_dict(document) == record
    with pytest.raises(ValueError, match="legacy reservation"):
        replace(record, selection=selection())
    document["selection"] = None
    with pytest.raises(ValueError, match="fields"):
        ProviderInvocationReservation.from_dict(document)


@pytest.mark.parametrize("version", [True, 1.0, 3.0, "3", None, 4])
def test_reservation_version_is_strict(version):
    document = reservation(selection=selection()).to_dict()
    document["schema_version"] = version
    with pytest.raises(ValueError, match="schema_version"):
        ProviderInvocationReservation.from_dict(document)


@pytest.mark.parametrize("overrides", [
    {"selection": None}, {"selection": {}}, {"selection": "source"},
])
def test_version3_requires_typed_selection(overrides):
    with pytest.raises(ValueError, match="selected-member"):
        replace(reservation(selection=selection()), **overrides)


@pytest.mark.parametrize("overrides", [
    {"binding_generation": True}, {"binding_generation": 0},
    {"credential_reference_generation": 0}, {"assignment_generation": 1.0},
    {"binding_digest": "fake"}, {"member_digest": "fake"},
    {"model_id": " spaced "}, {"model_id": "line\nbreak"}, {"model_id": 1},
    {"executor_id": ""}, {"binding_revocation_generation": -1},
])
def test_selected_member_rejects_malformed_facts(overrides):
    with pytest.raises(ValueError):
        selection(**overrides)


@pytest.mark.parametrize("field,value", [
    ("supports_tools", 1), ("context_tokens", True), ("cost_caps", {}),
    ("source_digest", "not-a-digest"), ("completed_at", "2026-08-01T05:00:00Z"),
    ("execution_contract", {"kind": "callback", "value": "eval"}),
    ("execution_contract", {"kind": "installed", "value": "invented-source"}),
])
def test_selected_model_evidence_is_strict(field, value):
    chosen = http_selection()
    evidence = chosen.model_evidence()
    evidence[field] = value
    with pytest.raises(ValueError):
        replace(chosen, model_evidence_json=_canonical_json(evidence))


def test_selected_model_rejects_unrecognized_or_noncanonical_evidence():
    chosen = http_selection()
    document = chosen.to_dict()
    document["model_evidence"]["credential"] = "not-permitted"
    with pytest.raises(ValueError, match="fields"):
        ProviderInvocationSelection.from_dict(document)
    with pytest.raises(ValueError, match="fields"):
        replace(chosen, model_evidence_json=json.dumps(chosen.model_evidence(), indent=2))
    with pytest.raises(ValueError, match="executor"):
        replace(chosen, executor_id="different_executor")


def test_selection_cannot_activate_through_legacy_reservation(tmp_path):
    receipt, claim, _armed = _armed_carrier_result(tmp_path)
    store = SQLiteProviderWorkAuthorityStore(tmp_path, clock=lambda: NOW, allow_test_fixtures=True)
    before = store.list_reservations(receipt.receipt_id)
    with pytest.raises(PermissionError, match="manifest invocation admission"):
        store.reserve(request(
            receipt_id=receipt.receipt_id, receipt_digest=receipt.receipt_digest,
            claim_id=claim.claim_id, claim_digest=claim.claim_digest,
            claim_generation=claim.generation, selection=selection(),
        ))
    assert store.list_reservations(receipt.receipt_id) == before


def test_selection_cannot_mint_a_carrier_without_manifest_admission(tmp_path):
    receipt, claim, armed = _armed_carrier_result(tmp_path)
    selected = replace(armed.record, schema_version=3, selection=selection())
    selected = replace(selected, reservation_digest=selected.expected_digest())
    with pytest.raises(PermissionError, match="stale or inconsistent"):
        _mint_provider_invocation_carrier(
            receipt, claim, selected, _provider_invocation_store_mint_proof(selected),
            settlement_owner=ProviderInvocationSettlementOwner.CONSUMER,
        )


@pytest.mark.parametrize("state", [
    ProviderInvocationReservationState.SUCCEEDED,
    ProviderInvocationReservationState.FAILED,
    ProviderInvocationReservationState.INDETERMINATE,
])
def test_version3_settlement_preserves_exact_selection(tmp_path, state):
    _receipt, _claim, armed = _armed_carrier_result(tmp_path)
    store = SQLiteProviderWorkAuthorityStore(tmp_path, clock=lambda: NOW, allow_test_fixtures=True)
    record = replace(armed.record, schema_version=3, selection=http_selection())
    record = replace(record, reservation_digest=record.expected_digest())
    # A fixture substitutes a version3 record solely to exercise durable terminal
    # accounting. Neither this write nor the inert document can admit a launch.
    with store.connection() as conn:
        conn.execute(
            "UPDATE provider_invocation_reservations SET reservation_digest=?, record_json=? "
            "WHERE reservation_id=?",
            (record.reservation_digest, json.dumps(record.to_dict()), record.reservation_id),
        )
        conn.commit()
    usage = (None, None, None) if state.value == "indeterminate" else (3, 4, 5)
    store._settle_carrier(record, state, *usage)
    settled = store.get_reservation(record.reservation_id)
    assert settled.schema_version == 3
    assert settled.selection == record.selection
    assert settled.state is state
    assert settled.reservation_digest == settled.expected_digest()
    with pytest.raises(PermissionError, match="settlement conflicted"):
        store._settle_carrier(record, state, *usage)
    assert store.get_reservation(record.reservation_id) == settled
