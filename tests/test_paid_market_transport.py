from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest


def _transport_contract():
    try:
        from tinyassets.payments import market_transport
    except ImportError:
        pytest.fail("tinyassets.payments.market_transport is missing")
    return market_transport


class RecordingRpc:
    def __init__(self):
        self.commands = []

    def apply_settlement(self, command):
        self.commands.append(command)
        return {"status": "applied", "tx_id": 41}


class RecordingAuthorityVerifier:
    def __init__(self):
        self.authorities = []

    def verify(self, authority, *, now):
        self.authorities.append((authority, now))
        return authority


def _enabled_transport(contract, rpc):
    return contract.MarketTransport(
        rpc,
        enabled=True,
        authority_verifier=RecordingAuthorityVerifier(),
    )


def _authority_and_grant():
    contract = _transport_contract()
    now = datetime.now(UTC)
    grant = contract.VerifiedOnBehalfGrant(
        grant_id="grant-1",
        host_actor_id="host-actor",
        target_actor_id="buyer",
        target_tenant_id="tenant-a",
        account="escrow:req-1",
        allowed_actions=frozenset({"settle"}),
        max_amount_micros=10_000,
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=5),
        revocation_generation=3,
        verified_signature_sha256="a" * 64,
    )
    authority = contract.VerifiedMarketAuthority(
        subject_id="host-actor",
        tenant_id="tenant-a",
        requester_user_id="buyer",
        host_owner_user_id="seller",
        grant=grant,
    )
    return contract, authority, now


def _command(contract, authority):
    return contract.SettlementCommand(
        idempotency_key="settle:req-1:v2",
        business_reference="request:req-1",
        expected_state_version=2,
        authority=authority,
        action="settle",
        amount_micros=10_000,
        escrow_account="escrow:req-1",
        postings=(
            ("escrow:req-1", -10_000),
            ("user:seller", 9_900),
            ("treasury", 100),
        ),
        memo="accepted result",
    )


def test_transport_defaults_off_and_never_calls_rpc():
    contract, authority, now = _authority_and_grant()
    rpc = RecordingRpc()
    result = contract.MarketTransport(rpc).settle(
        _command(contract, authority), now=now
    )
    assert result.status == "not_available"
    assert result.tx_id is None
    assert rpc.commands == []


def test_transport_serializes_pure_entries_unchanged_and_recomputes_hash():
    contract, authority, now = _authority_and_grant()
    rpc = RecordingRpc()
    command = _command(contract, authority)
    transport = _enabled_transport(contract, rpc)
    result = transport.settle(command, now=now)
    assert result.status == "applied"
    assert result.tx_id == 41
    assert len(rpc.commands) == 1
    serialized = rpc.commands[0]
    assert serialized.postings == command.postings
    assert serialized.request_sha256 == hashlib.sha256(
        serialized.canonical_body
    ).hexdigest()
    assert serialized.authority.grant.grant_id == "grant-1"
    assert serialized.authority.subject_id == "host-actor"
    assert serialized.authority.requester_user_id == "buyer"
    assert len(transport._authority_verifier.authorities) == 1


def test_enabled_transport_requires_a_trusted_authority_verifier():
    contract, authority, now = _authority_and_grant()
    with pytest.raises(contract.MarketTransportError, match="authority verifier"):
        contract.MarketTransport(RecordingRpc(), enabled=True).settle(
            _command(contract, authority), now=now
        )


def test_transport_rejects_applied_or_replayed_result_without_tx_id():
    contract, authority, now = _authority_and_grant()

    class MissingIdentityRpc:
        def apply_settlement(self, command):
            return {"status": "replayed", "tx_id": None}

    with pytest.raises(contract.MarketTransportError, match="transaction identity"):
        _enabled_transport(contract, MissingIdentityRpc()).settle(
            _command(contract, authority), now=now
        )


@pytest.mark.parametrize(
    "mutation, message",
    [
        ({"tenant_id": "tenant-b"}, "tenant"),
        ({"subject_id": "ungranted-host"}, "grant"),
    ],
)
def test_transport_rejects_caller_selected_authority(mutation, message):
    contract, authority, now = _authority_and_grant()
    changed = replace(authority, **mutation)
    with pytest.raises(contract.MarketTransportError, match=message):
        _enabled_transport(contract, RecordingRpc()).settle(
            _command(contract, changed), now=now
        )


@pytest.mark.parametrize(
    "grant_change, message",
    [
        ({"expires_at": datetime(2020, 1, 1, tzinfo=UTC)}, "expired"),
        ({"allowed_actions": frozenset({"refund"})}, "action"),
        ({"account": "escrow:other"}, "account"),
        ({"max_amount_micros": 9_999}, "amount"),
        ({"target_actor_id": "other"}, "target"),
        ({"target_tenant_id": "tenant-b"}, "tenant"),
        ({"verified_signature_sha256": "not-verified"}, "signature"),
    ],
)
def test_transport_enforces_every_signed_grant_bound(grant_change, message):
    contract, authority, now = _authority_and_grant()
    grant = replace(authority.grant, **grant_change)
    changed = replace(authority, grant=grant)
    with pytest.raises(contract.MarketTransportError, match=message):
        _enabled_transport(contract, RecordingRpc()).settle(
            _command(contract, changed), now=now
        )


def test_transport_rejects_non_integer_or_unbalanced_postings():
    contract, authority, now = _authority_and_grant()
    base = _command(contract, authority)
    for postings in (
        (("escrow:req-1", -10_000), ("user:seller", 10_001)),
        (("escrow:req-1", -10_000.0), ("user:seller", 10_000.0)),
    ):
        with pytest.raises(contract.MarketTransportError):
            _enabled_transport(contract, RecordingRpc()).settle(
                replace(base, postings=postings), now=now
            )


def test_transport_rejects_postings_not_emitted_by_the_spot_adapter():
    contract, authority, now = _authority_and_grant()
    command = replace(
        _command(contract, authority),
        postings=(
            ("escrow:req-1", -10_000),
            ("user:seller", 9_800),
            ("treasury", 200),
        ),
    )
    with pytest.raises(contract.MarketTransportError, match="canonical adapter"):
        _enabled_transport(contract, RecordingRpc()).settle(command, now=now)


def test_transport_exposes_no_direct_balance_or_table_writer():
    contract = _transport_contract()
    public_methods = {
        name
        for name, member in inspect.getmembers(
            contract.MarketTransport, inspect.isfunction
        )
        if not name.startswith("_")
    }
    assert public_methods == {"settle"}
