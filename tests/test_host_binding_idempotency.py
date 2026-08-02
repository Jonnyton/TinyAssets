from __future__ import annotations

import base64
import copy
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from tinyassets.auth.host_enrollment import (
    HostEnrollmentCoordinator,
    HostEnrollmentIdempotencyConflict,
    HostEnrollmentRefused,
    HostEnrollmentTransactionOutcome,
    HostEnrollmentTransactionRequest,
    HostEnrollmentWritersDisabled,
    HostPrincipalResultV1,
)
from tinyassets.auth.host_proof import (
    HostProofBindingV1,
    HostProofRefused,
    host_proof_signing_bytes,
    jwk_thumbprint,
    operation_policy,
)

NOW = 1_800_000_000
DAY = 24 * 60 * 60
HMAC_KEY = b"k" * 32


def _b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _key(seed: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([seed]) * 32)


def _jwk(key: Ed25519PrivateKey) -> dict[str, str]:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return {"kty": "OKP", "crv": "Ed25519", "x": _b64u(raw)}


def _binding(
    key: Ed25519PrivateKey,
    *,
    subject: str = "user_owner",
    challenge_seed: int = 1,
    body_sha256: str,
    now: int = NOW,
) -> HostProofBindingV1:
    policy = operation_policy("enroll")
    return HostProofBindingV1(
        schema_version="host-binding-v1",
        policy_version="host-binding-v1",
        operation="enroll",
        permission="host:enroll",
        issuer="https://example.authkit.app",
        subject=subject,
        audience="https://tinyassets.io/host-binding",
        method=policy.method,
        path=policy.path,
        body_sha256=body_sha256,
        key_thumbprints={"new": jwk_thumbprint(_jwk(key))},
        host_principal_id=None,
        expected_generation=None,
        challenge_id_b64u=_b64u(bytes([challenge_seed]) * 32),
        issued_at=now - 30,
        expires_at=now + 270,
    )


def _submission(binding: HostProofBindingV1, key: Ed25519PrivateKey) -> bytes:
    signing_input = host_proof_signing_bytes(binding)
    return rfc8785.dumps(
        {
            "schema_version": "host-binding-v1",
            "challenge_id_b64u": binding.challenge_id_b64u,
            "signatures": {"new": _b64u(key.sign(signing_input))},
        }
    )


class _ResponseLost(RuntimeError):
    pass


class _TransactionalContractStore:
    """Shared atomic contract model; production PostgreSQL remains task 3.2."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._consumed_challenges: set[str] = set()
        self._receipts: dict[str, tuple[str, HostPrincipalResultV1, int]] = {}
        self._principals: dict[tuple[str, str, str], HostPrincipalResultV1] = {}
        self._key_owners: dict[tuple[str, str], str] = {}
        self.mutation_count = 0
        self.requests: list[HostEnrollmentTransactionRequest] = []
        self.fail_before_commit_once = False
        self.lose_response_after_commit_once = False

    def commit_enrollment(
        self, request: HostEnrollmentTransactionRequest
    ) -> HostEnrollmentTransactionOutcome:
        lose_response = False
        with self._lock:
            self.requests.append(request)
            if request.challenge_id_b64u in self._consumed_challenges:
                return HostEnrollmentTransactionOutcome("replayed")

            consumed = set(self._consumed_challenges)
            receipts = copy.copy(self._receipts)
            principals = copy.copy(self._principals)
            key_owners = copy.copy(self._key_owners)
            mutation_count = self.mutation_count

            # Fixed transaction order: challenge CAS, idempotency, uniqueness,
            # then principal + receipt write.
            consumed.add(request.challenge_id_b64u)
            receipt = receipts.get(request.idempotency_lookup_hash)
            if receipt is not None and receipt[2] > request.transaction_time:
                binding_hash, result, _expires_at = receipt
                if binding_hash != request.idempotency_binding_hash:
                    self._consumed_challenges = consumed
                    return HostEnrollmentTransactionOutcome("idempotency_conflict")
                self._consumed_challenges = consumed
                return HostEnrollmentTransactionOutcome("committed", result)
            receipts.pop(request.idempotency_lookup_hash, None)

            key_owner = key_owners.get((request.issuer, request.key_thumbprint))
            if key_owner is not None and key_owner != request.subject:
                self._consumed_challenges = consumed
                return HostEnrollmentTransactionOutcome("refused")

            principal_key = (request.issuer, request.subject, request.key_thumbprint)
            result = principals.get(principal_key)
            if result is None:
                result = request.candidate_result
                principals[principal_key] = result
                key_owners[(request.issuer, request.key_thumbprint)] = request.subject
                mutation_count += 1

            receipts[request.idempotency_lookup_hash] = (
                request.idempotency_binding_hash,
                result,
                request.idempotency_expires_at,
            )
            if self.fail_before_commit_once:
                self.fail_before_commit_once = False
                raise RuntimeError("injected pre-commit crash")

            self._consumed_challenges = consumed
            self._receipts = receipts
            self._principals = principals
            self._key_owners = key_owners
            self.mutation_count = mutation_count
            if self.lose_response_after_commit_once:
                self.lose_response_after_commit_once = False
                lose_response = True

        if lose_response:
            raise _ResponseLost("injected response loss after commit")
        return HostEnrollmentTransactionOutcome("committed", result)


def _coordinator(
    store: _TransactionalContractStore,
    principal_id: str = "hp_winner",
    *,
    enabled: bool = True,
) -> HostEnrollmentCoordinator:
    return HostEnrollmentCoordinator(
        store=store,
        idempotency_hmac_key=HMAC_KEY,
        writers_enabled=enabled,
        new_principal_id=lambda: principal_id,
    )


def _complete(
    coordinator: HostEnrollmentCoordinator,
    key: Ed25519PrivateKey,
    *,
    subject: str = "user_owner",
    challenge_seed: int = 1,
    idempotency_seed: int = 9,
    device_label: str | None = None,
    now: int = NOW,
) -> HostPrincipalResultV1:
    intent: dict[str, object] = {
        "idempotency_key_b64u": _b64u(bytes([idempotency_seed]) * 32),
        "public_jwk": _jwk(key),
    }
    if device_label is not None:
        intent["device_label"] = device_label
    canonical_intent = rfc8785.dumps(intent)
    binding = _binding(
        key,
        subject=subject,
        challenge_seed=challenge_seed,
        body_sha256="sha256:" + hashlib.sha256(canonical_intent).hexdigest(),
        now=now,
    )
    return coordinator.complete_enrollment(
        submission_json=_submission(binding, key),
        binding=binding,
        enroll_intent=intent,
        signing_input_b64u=_b64u(host_proof_signing_bytes(binding)),
        now=now,
    )


def test_writers_are_disabled_by_default_and_raw_idempotency_key_is_not_stored() -> None:
    store = _TransactionalContractStore()
    key = _key(1)
    disabled = HostEnrollmentCoordinator(
        store=store,
        idempotency_hmac_key=HMAC_KEY,
        new_principal_id=lambda: "hp_disabled",
    )

    with pytest.raises(HostEnrollmentWritersDisabled):
        _complete(disabled, key)
    assert store.requests == []

    _complete(_coordinator(store), key)
    request_text = repr(store.requests[-1])
    assert _b64u(bytes([9]) * 32) not in request_text
    assert repr(HMAC_KEY) not in request_text


def test_precommit_crash_rolls_back_authority_and_postcommit_loss_recovers_fresh() -> None:
    store = _TransactionalContractStore()
    coordinator = _coordinator(store)
    key = _key(1)
    store.fail_before_commit_once = True

    with pytest.raises(RuntimeError, match="pre-commit"):
        _complete(coordinator, key, challenge_seed=1)
    assert store.mutation_count == 0

    # A pre-commit crash did not consume the exact challenge. The next commit
    # succeeds even when its response is lost.
    store.lose_response_after_commit_once = True
    with pytest.raises(_ResponseLost):
        _complete(coordinator, key, challenge_seed=1)
    assert store.mutation_count == 1

    # Exact replay is never upgraded by the receipt.
    with pytest.raises(HostProofRefused):
        _complete(coordinator, key, challenge_seed=1)

    recovered = _complete(coordinator, key, challenge_seed=2)
    assert recovered.host_principal_id == "hp_winner"
    assert store.mutation_count == 1


def test_same_idempotency_key_with_changed_body_conflicts_after_fresh_proof() -> None:
    store = _TransactionalContractStore()
    coordinator = _coordinator(store)
    key = _key(1)
    _complete(coordinator, key, challenge_seed=1)

    with pytest.raises(HostEnrollmentIdempotencyConflict):
        _complete(
            coordinator,
            key,
            challenge_seed=2,
            device_label="changed intent",
        )
    assert store.mutation_count == 1
    with pytest.raises(HostProofRefused):
        _complete(
            coordinator,
            key,
            challenge_seed=2,
            device_label="changed intent",
        )


def test_idempotency_receipt_expires_at_exactly_24_hours_but_uniqueness_remains() -> None:
    store = _TransactionalContractStore()
    coordinator = _coordinator(store)
    key = _key(1)
    original = _complete(coordinator, key, challenge_seed=1)

    with pytest.raises(HostEnrollmentIdempotencyConflict):
        _complete(
            coordinator,
            key,
            challenge_seed=2,
            device_label="changed intent",
            now=NOW + DAY - 1,
        )

    after_expiry = _complete(
        coordinator,
        key,
        challenge_seed=3,
        device_label="changed intent",
        now=NOW + DAY,
    )
    assert after_expiry == original
    assert store.mutation_count == 1


def test_concurrent_server_instances_converge_on_one_subject_key_winner() -> None:
    store = _TransactionalContractStore()
    key = _key(1)
    server_a = _coordinator(store, "hp_a")
    server_b = _coordinator(store, "hp_b")
    barrier = threading.Barrier(24)

    def enroll(index: int) -> HostPrincipalResultV1:
        barrier.wait()
        server = server_a if index % 2 == 0 else server_b
        return _complete(
            server,
            key,
            challenge_seed=index + 1,
            idempotency_seed=index + 1,
        )

    with ThreadPoolExecutor(max_workers=24) as pool:
        results = list(pool.map(enroll, range(24)))

    assert len({result.host_principal_id for result in results}) == 1
    assert {result.generation for result in results} == {1}
    assert store.mutation_count == 1


def test_distinct_device_keys_for_one_subject_create_distinct_principals() -> None:
    store = _TransactionalContractStore()
    first = _complete(_coordinator(store, "hp_first"), _key(1), challenge_seed=1)
    second = _complete(
        _coordinator(store, "hp_second"),
        _key(2),
        challenge_seed=2,
        idempotency_seed=2,
    )

    assert first.host_principal_id != second.host_principal_id
    assert store.mutation_count == 2


def test_cross_subject_key_reuse_has_one_non_enumerating_refusal_class() -> None:
    store = _TransactionalContractStore()
    key = _key(1)
    first = _complete(_coordinator(store, "hp_private"), key, subject="user_first")

    with pytest.raises(HostEnrollmentRefused) as refusal:
        _complete(
            _coordinator(store, "hp_attacker"),
            key,
            subject="user_second",
            challenge_seed=2,
            idempotency_seed=2,
        )

    assert refusal.value.public_error["error"] == "host_binding_refused"
    assert first.host_principal_id not in repr(refusal.value)
    assert "user_first" not in repr(refusal.value)
