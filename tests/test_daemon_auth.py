from __future__ import annotations

import base64
import hashlib
import importlib
import inspect
import json
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

import pytest
from nacl.public import PrivateKey
from nacl.signing import SigningKey, VerifyKey


def _daemon_auth():
    try:
        return importlib.import_module("tinyassets.runtime.daemon_auth")
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"daemon-auth contract is missing: {exc}")


def _daemon_api():
    try:
        return importlib.import_module("tinyassets.api.daemon_enrollment")
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"daemon-enrollment API contract is missing: {exc}")


def _contracts():
    return _daemon_auth(), _daemon_api()


def _complete_enrollment(service, signer, enrollment_id):
    return service.complete_enrollment(
        enrollment_id,
        **signer.enrollment_completion_proof(enrollment_id),
    )


def _create_challenge(service, signer, daemon_id):
    return service.create_challenge(
        daemon_id,
        **signer.challenge_creation_proof(
            daemon_id,
            timestamp=int(service._clock()),
        ),
    )


class _MemoryKeyStore:
    """Test-only key custody; production must use an OS keystore."""

    backend_name = "test-memory"
    hardware_non_exportable = False

    def __init__(self) -> None:
        self._keys: dict[str, tuple[SigningKey, PrivateKey, bytes]] = {}

    def load_or_create(self, installation_id: str):
        daemon_auth = _daemon_auth()
        keys = self._keys.get(installation_id)
        if keys is None:
            keys = (SigningKey.generate(), PrivateKey.generate(), PrivateKey.generate().encode())
            self._keys[installation_id] = keys
        signing_key, transfer_key, installation_nonce = keys
        return daemon_auth.DevicePublicIdentity(
            installation_id=installation_id,
            ed25519_public_key=signing_key.verify_key.encode(),
            x25519_public_key=transfer_key.public_key.encode(),
            installation_nonce=installation_nonce,
            key_backend=self.backend_name,
            hardware_non_exportable=self.hardware_non_exportable,
        )

    def sign(self, installation_id: str, message: bytes) -> bytes:
        return self._keys[installation_id][0].sign(message).signature

    def exchange(self, installation_id: str, peer_public_key: bytes) -> bytes:
        from nacl.bindings import crypto_scalarmult

        return crypto_scalarmult(self._keys[installation_id][1].encode(), peer_public_key)


@pytest.fixture
def auth_harness(tmp_path):
    daemon_auth, daemon_api = _contracts()
    now = [time.time()]
    service = daemon_api.DaemonEnrollmentService(
        db_path=tmp_path / "daemon-auth.sqlite3",
        clock=lambda: now[0],
    )
    signer = daemon_auth.DaemonSigner("installation-a", key_store=_MemoryKeyStore())
    enrollment = service.create_enrollment(signer.identity)
    service.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    completed = _complete_enrollment(service, signer, enrollment.enrollment_id)
    challenge = _create_challenge(service, signer, completed.daemon_id)
    token = service.issue_access_token(
        completed.daemon_id,
        challenge.challenge,
        signer.sign_challenge(completed.daemon_id, challenge.challenge),
    )
    return daemon_auth, daemon_api, service, signer, completed, token, now


def _signed_request(daemon_auth, signer, token, *, now, nonce="fresh-nonce", body=b"{}"):
    session = daemon_auth.DaemonAuthSession(signer, token_supplier=lambda: token)
    return session.sign_request(
        "POST",
        "/v1/execution-requests/claim",
        "limit=1",
        body,
        timestamp=int(now),
        nonce=nonce,
    )


def test_enrollment_registry_resolves_platform_owned_device_key_and_epoch(
    auth_harness,
):
    _, _, service, signer, completed, _, _ = auth_harness

    registered = service.resolve_device_key(completed.key_thumbprint)

    assert registered is not None
    assert registered.device_key_id == completed.key_thumbprint
    assert registered.credential_epoch == completed.credential_epoch == 1
    assert registered.active is True
    assert bytes(registered.verify_key) == signer.identity.ed25519_public_key

    assert service.resolve_device_key("unregistered-key") is None

    service.revoke_daemon(completed.owner_user_id, completed.daemon_id)
    revoked = service.resolve_device_key(completed.key_thumbprint)

    assert revoked is not None
    assert revoked.credential_epoch == 2
    assert revoked.active is False


def test_device_identity_has_ed25519_x25519_nonce_and_verifiable_signatures():
    daemon_auth = _daemon_auth()
    signer = daemon_auth.DaemonSigner("installation-a", key_store=_MemoryKeyStore())

    identity = signer.identity
    assert len(identity.ed25519_public_key) == 32
    assert len(identity.x25519_public_key) == 32
    assert len(identity.installation_nonce) >= 32
    assert identity.key_backend == "test-memory"
    assert identity.hardware_non_exportable is False

    message = b"request-bound-message"
    VerifyKey(identity.ed25519_public_key).verify(message, signer.sign(message))


def test_unsupported_platform_keystore_fails_loud():
    daemon_auth = _daemon_auth()

    with pytest.raises(daemon_auth.KeystoreUnavailableError, match="unsupported"):
        daemon_auth.default_device_keystore(platform_name="Linux")


def test_windows_keystore_path_uses_credential_manager_without_plaintext_files():
    daemon_auth = _daemon_auth()
    blobs: dict[str, bytes] = {}

    class FakeCredentialApi:
        def read(self, target: str) -> bytes | None:
            return blobs.get(target)

        def write(self, target: str, secret: bytes) -> None:
            blobs[target] = secret

    store = daemon_auth.WindowsCredentialKeyStore(credential_api=FakeCredentialApi())
    public = store.load_or_create("win-install")
    signature = store.sign("win-install", b"proof")

    assert store.backend_name == "windows-credential-manager"
    assert store.hardware_non_exportable is False
    assert blobs
    assert not hasattr(public, "ed25519_private_key")
    VerifyKey(public.ed25519_public_key).verify(b"proof", signature)


def test_enrollment_requires_owner_approval_and_returns_verification_handoff(tmp_path):
    daemon_auth, daemon_api = _contracts()
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "auth.sqlite3")
    signer = daemon_auth.DaemonSigner("install-a", key_store=_MemoryKeyStore())

    enrollment = service.create_enrollment(signer.identity)
    assert enrollment.enrollment_id
    assert len(enrollment.verification_code) == 12
    assert enrollment.verification_code.isalnum()
    with pytest.raises(daemon_api.DaemonApiError) as denied:
        _complete_enrollment(service, signer, enrollment.enrollment_id)
    assert denied.value.status == 403
    assert set(denied.value.as_dict()["error"]) == {
        "code",
        "message",
        "retryable",
        "request_id",
        "details",
    }

    service.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    complete = _complete_enrollment(service, signer, enrollment.enrollment_id)
    assert complete.owner_user_id == "owner-a"
    assert complete.daemon_id
    assert complete.credential_epoch == 1


def test_owner_can_approve_by_short_verification_code(tmp_path):
    daemon_auth, daemon_api = _contracts()
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "auth.sqlite3")
    signer = daemon_auth.DaemonSigner("install-code", key_store=_MemoryKeyStore())
    enrollment = service.create_enrollment(signer.identity)

    service.approve_verification_code(
        enrollment.enrollment_id,
        enrollment.verification_code,
        owner_user_id="owner-a",
    )
    completed = _complete_enrollment(service, signer, enrollment.enrollment_id)

    assert completed.owner_user_id == "owner-a"


def test_expired_verification_code_cannot_be_approved(tmp_path):
    daemon_auth, daemon_api = _contracts()
    now = [time.time()]
    service = daemon_api.DaemonEnrollmentService(
        db_path=tmp_path / "expired-enrollment.sqlite3", clock=lambda: now[0]
    )
    signer = daemon_auth.DaemonSigner("expired-enrollment", key_store=_MemoryKeyStore())
    handoff = service.create_enrollment(signer.identity)
    now[0] += 301

    with pytest.raises(daemon_api.DaemonApiError) as expired:
        service.approve_verification_code(
            handoff.enrollment_id,
            handoff.verification_code,
            owner_user_id="owner-a",
        )

    assert expired.value.status == 410
    assert expired.value.code == "ENROLLMENT_EXPIRED"


def test_enrollment_and_owner_wrong_code_attempts_lock_out(tmp_path):
    daemon_auth, daemon_api = _contracts()
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "attempt-caps.sqlite3")
    signer = daemon_auth.DaemonSigner("attempt-cap-device", key_store=_MemoryKeyStore())
    handoff = service.create_enrollment(signer.identity)

    for attempt in range(5):
        with pytest.raises(daemon_api.DaemonApiError) as rejected:
            service.approve_verification_code(
                handoff.enrollment_id,
                "ZZZZZZZZZZZZ",
                owner_user_id="owner-a",
            )
        assert rejected.value.status == (429 if attempt == 4 else 404)

    with pytest.raises(daemon_api.DaemonApiError) as locked_enrollment:
        service.approve_verification_code(
            handoff.enrollment_id,
            handoff.verification_code,
            owner_user_id="owner-b",
        )
    assert locked_enrollment.value.code == "ENROLLMENT_APPROVAL_LOCKED"

    other_owner_handoffs = []
    for index in range(6):
        other = daemon_auth.DaemonSigner(f"owner-cap-device-{index}", key_store=_MemoryKeyStore())
        other_owner_handoffs.append(service.create_enrollment(other.identity))
    for handoff_for_owner in other_owner_handoffs[:5]:
        with pytest.raises(daemon_api.DaemonApiError):
            service.approve_verification_code(
                handoff_for_owner.enrollment_id,
                "ZZZZZZZZZZZZ",
                owner_user_id="owner-b",
            )
    with pytest.raises(daemon_api.DaemonApiError) as locked_owner:
        service.approve_verification_code(
            other_owner_handoffs[5].enrollment_id,
            other_owner_handoffs[5].verification_code,
            owner_user_id="owner-b",
        )
    assert locked_owner.value.status == 429
    assert locked_owner.value.code == "ENROLLMENT_APPROVAL_LOCKED"


def test_pending_enrollment_capacity_is_per_device_identity(tmp_path):
    daemon_auth, daemon_api = _contracts()
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "enrollment-cap.sqlite3")
    signer = daemon_auth.DaemonSigner("enrollment-cap-device", key_store=_MemoryKeyStore())

    for _ in range(daemon_api._MAX_PENDING_ENROLLMENTS_PER_IDENTITY):
        service.create_enrollment(signer.identity)
    with pytest.raises(daemon_api.DaemonApiError) as capped:
        service.create_enrollment(signer.identity)

    assert capped.value.status == 429
    assert capped.value.code == "DAEMON_ENROLLMENT_CAPACITY"
    assert capped.value.retryable is True
    other = daemon_auth.DaemonSigner("honest-other-device", key_store=_MemoryKeyStore())
    assert service.create_enrollment(other.identity).enrollment_id


def test_enrollment_creation_rate_is_per_device_identity(tmp_path, monkeypatch):
    daemon_auth, daemon_api = _contracts()
    monkeypatch.setattr(daemon_api, "_MAX_PENDING_ENROLLMENTS_PER_IDENTITY", 10, raising=False)
    monkeypatch.setattr(daemon_api, "_ENROLLMENT_CREATION_LIMIT_PER_MINUTE", 2, raising=False)
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "enrollment-rate.sqlite3")
    signer = daemon_auth.DaemonSigner("enrollment-rate-device", key_store=_MemoryKeyStore())

    service.create_enrollment(signer.identity)
    service.create_enrollment(signer.identity)
    with pytest.raises(daemon_api.DaemonApiError) as rate_limited:
        service.create_enrollment(signer.identity)

    assert rate_limited.value.status == 429
    assert rate_limited.value.code == "DAEMON_ENROLLMENT_RATE_LIMITED"
    assert rate_limited.value.retryable is True


def test_concurrent_enrollment_creation_serializes_capacity_across_instances(
    tmp_path, monkeypatch
):
    daemon_auth, daemon_api = _contracts()
    monkeypatch.setattr(daemon_api, "_MAX_PENDING_ENROLLMENTS_PER_IDENTITY", 1, raising=False)
    monkeypatch.setattr(daemon_api, "_ENROLLMENT_CREATION_LIMIT_PER_MINUTE", 10, raising=False)
    db_path = tmp_path / "concurrent-enrollment-cap.sqlite3"
    first = daemon_api.DaemonEnrollmentService(db_path=db_path)
    second = daemon_api.DaemonEnrollmentService(db_path=db_path)
    signer = daemon_auth.DaemonSigner("concurrent-enrollment-device", key_store=_MemoryKeyStore())
    barrier = threading.Barrier(2)

    def create(service):
        barrier.wait()
        try:
            service.create_enrollment(signer.identity)
            return "accepted"
        except daemon_api.DaemonApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, (first, second)))

    assert sorted(results) == ["DAEMON_ENROLLMENT_CAPACITY", "accepted"]


def test_stale_pending_enrollments_are_reaped(tmp_path):
    daemon_auth, daemon_api = _contracts()
    now = [time.time()]
    service = daemon_api.DaemonEnrollmentService(
        db_path=tmp_path / "stale-enrollments.sqlite3", clock=lambda: now[0]
    )
    first = daemon_auth.DaemonSigner("stale-device", key_store=_MemoryKeyStore())
    service.create_enrollment(first.identity)
    now[0] += 301
    second = daemon_auth.DaemonSigner("fresh-device", key_store=_MemoryKeyStore())
    fresh = service.create_enrollment(second.identity)

    rows = service._connection.execute(
        "SELECT enrollment_id FROM daemon_enrollments WHERE status = 'pending'"
    ).fetchall()
    assert [row["enrollment_id"] for row in rows] == [fresh.enrollment_id]


def test_same_device_key_cannot_enroll_under_two_owners(tmp_path):
    daemon_auth, daemon_api = _contracts()
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "unique-device.sqlite3")
    signer = daemon_auth.DaemonSigner("same-device", key_store=_MemoryKeyStore())
    first = service.create_enrollment(signer.identity)
    second = service.create_enrollment(signer.identity)
    service.approve_enrollment(first.enrollment_id, owner_user_id="owner-a")
    service.approve_enrollment(second.enrollment_id, owner_user_id="owner-b")
    proof = signer.enrollment_completion_proof
    service.complete_enrollment(first.enrollment_id, **proof(first.enrollment_id))

    with pytest.raises(daemon_api.DaemonApiError) as duplicate:
        service.complete_enrollment(second.enrollment_id, **proof(second.enrollment_id))

    assert duplicate.value.status == 409
    assert duplicate.value.code == "DEVICE_ALREADY_ENROLLED"


def test_completion_requires_device_proof_of_possession(tmp_path):
    daemon_auth, daemon_api = _contracts()
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "completion-pop.sqlite3")
    signer = daemon_auth.DaemonSigner("completion-device", key_store=_MemoryKeyStore())
    attacker = daemon_auth.DaemonSigner("completion-attacker", key_store=_MemoryKeyStore())
    handoff = service.create_enrollment(signer.identity)
    service.approve_enrollment(handoff.enrollment_id, owner_user_id="owner-a")

    with pytest.raises(daemon_api.DaemonApiError) as rejected:
        service.complete_enrollment(
            handoff.enrollment_id,
            **attacker.enrollment_completion_proof(handoff.enrollment_id),
        )
    assert rejected.value.status == 401
    assert rejected.value.code == "INVALID_DEVICE_PROOF"

    completed = service.complete_enrollment(
        handoff.enrollment_id,
        **signer.enrollment_completion_proof(handoff.enrollment_id),
    )
    assert completed.owner_user_id == "owner-a"


def test_signed_challenge_issues_at_most_five_minute_bound_token(auth_harness):
    _, _, _, signer, completed, token, now = auth_harness

    assert token.daemon_id == completed.daemon_id
    assert token.key_thumbprint == signer.identity.key_thumbprint
    assert token.credential_epoch == 1
    assert 0 < token.expires_at - now[0] <= 300


def test_server_refuses_access_token_lifetime_over_five_minutes(tmp_path):
    daemon_auth, daemon_api = _contracts()
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "auth.sqlite3")
    signer = daemon_auth.DaemonSigner("long-token", key_store=_MemoryKeyStore())
    enrollment = service.create_enrollment(signer.identity)
    service.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    completed = _complete_enrollment(service, signer, enrollment.enrollment_id)
    challenge = _create_challenge(service, signer, completed.daemon_id)

    with pytest.raises(daemon_api.DaemonApiError) as denied:
        service.issue_access_token(
            completed.daemon_id,
            challenge.challenge,
            signer.sign_challenge(completed.daemon_id, challenge.challenge),
            lifetime_seconds=301,
        )

    assert denied.value.status == 422
    assert denied.value.code == "TOKEN_LIFETIME_INVALID"


def test_access_token_issuance_purges_expired_rows_and_caps_outstanding(tmp_path, monkeypatch):
    daemon_auth, daemon_api = _contracts()
    now = [time.time()]
    service = daemon_api.DaemonEnrollmentService(
        db_path=tmp_path / "token-cap.sqlite3", clock=lambda: now[0]
    )
    signer = daemon_auth.DaemonSigner("token-cap-device", key_store=_MemoryKeyStore())
    enrollment = service.create_enrollment(signer.identity)
    service.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    completed = _complete_enrollment(service, signer, enrollment.enrollment_id)

    def issue(lifetime=300):
        challenge = _create_challenge(service, signer, completed.daemon_id)
        return service.issue_access_token(
            completed.daemon_id,
            challenge.challenge,
            signer.sign_challenge(completed.daemon_id, challenge.challenge),
            lifetime_seconds=lifetime,
        )

    expired = issue(lifetime=1)
    now[0] += 2
    current = issue()
    hashes = service._connection.execute(
        "SELECT token_hash FROM daemon_access_tokens WHERE daemon_id = ?",
        (completed.daemon_id,),
    ).fetchall()
    assert [row["token_hash"] for row in hashes] == [service._token_hash(current.value)]
    assert service._token_hash(expired.value) not in {row["token_hash"] for row in hashes}

    monkeypatch.setattr(daemon_api, "_MAX_OUTSTANDING_ACCESS_TOKENS", 2)
    issue()
    with pytest.raises(daemon_api.DaemonApiError) as capped:
        issue()
    assert capped.value.status == 429
    assert capped.value.code == "DAEMON_TOKEN_CAPACITY"


def test_challenge_capacity_bounds_unconsumed_rows_and_allows_honest_flow(auth_harness):
    _, daemon_api, service, signer, completed, _, _ = auth_harness
    first = _create_challenge(service, signer, completed.daemon_id)
    for _ in range(daemon_api._MAX_OUTSTANDING_CHALLENGES_PER_DAEMON - 1):
        _create_challenge(service, signer, completed.daemon_id)

    with pytest.raises(daemon_api.DaemonApiError) as capped:
        _create_challenge(service, signer, completed.daemon_id)

    assert capped.value.status == 429
    assert capped.value.code == "DAEMON_CHALLENGE_CAPACITY"
    assert capped.value.retryable is True
    service.issue_access_token(
        completed.daemon_id,
        first.challenge,
        signer.sign_challenge(completed.daemon_id, first.challenge),
    )
    assert _create_challenge(service, signer, completed.daemon_id).challenge


def test_challenge_creation_rate_is_per_daemon(tmp_path, monkeypatch):
    daemon_auth, daemon_api = _contracts()
    monkeypatch.setattr(daemon_api, "_MAX_OUTSTANDING_CHALLENGES_PER_DAEMON", 10, raising=False)
    monkeypatch.setattr(daemon_api, "_CHALLENGE_CREATION_LIMIT_PER_MINUTE", 2, raising=False)
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "challenge-rate.sqlite3")
    signer = daemon_auth.DaemonSigner("challenge-rate-device", key_store=_MemoryKeyStore())
    enrollment = service.create_enrollment(signer.identity)
    service.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    completed = _complete_enrollment(service, signer, enrollment.enrollment_id)

    _create_challenge(service, signer, completed.daemon_id)
    _create_challenge(service, signer, completed.daemon_id)
    with pytest.raises(daemon_api.DaemonApiError) as rate_limited:
        _create_challenge(service, signer, completed.daemon_id)

    assert rate_limited.value.status == 429
    assert rate_limited.value.code == "DAEMON_CHALLENGE_RATE_LIMITED"
    assert rate_limited.value.retryable is True


def test_concurrent_challenge_creation_serializes_capacity_across_instances(
    tmp_path, monkeypatch
):
    daemon_auth, daemon_api = _contracts()
    monkeypatch.setattr(daemon_api, "_MAX_OUTSTANDING_CHALLENGES_PER_DAEMON", 1, raising=False)
    monkeypatch.setattr(daemon_api, "_CHALLENGE_CREATION_LIMIT_PER_MINUTE", 10, raising=False)
    db_path = tmp_path / "concurrent-challenge-cap.sqlite3"
    first = daemon_api.DaemonEnrollmentService(db_path=db_path)
    signer = daemon_auth.DaemonSigner("concurrent-challenge-device", key_store=_MemoryKeyStore())
    enrollment = first.create_enrollment(signer.identity)
    first.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    completed = _complete_enrollment(first, signer, enrollment.enrollment_id)
    second = daemon_api.DaemonEnrollmentService(db_path=db_path)
    barrier = threading.Barrier(2)

    def create(service):
        barrier.wait()
        try:
            _create_challenge(service, signer, completed.daemon_id)
            return "accepted"
        except daemon_api.DaemonApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, (first, second)))

    assert sorted(results) == ["DAEMON_CHALLENGE_CAPACITY", "accepted"]


@pytest.mark.filterwarnings(
    "ignore:Using `httpx` with `starlette.testclient` is deprecated:UserWarning"
)
def test_wrong_device_cannot_fill_honest_daemon_challenge_capacity(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    daemon_auth, daemon_api = _contracts()
    challenge_capacity = daemon_api._MAX_OUTSTANDING_CHALLENGES_PER_DAEMON
    now = [1_800_000_000.0]
    service = daemon_api.DaemonEnrollmentService(
        db_path=tmp_path / "challenge-pop.sqlite3", clock=lambda: now[0]
    )
    honest = daemon_auth.DaemonSigner("honest-challenge-device", key_store=_MemoryKeyStore())
    attacker = daemon_auth.DaemonSigner("attacker-challenge-device", key_store=_MemoryKeyStore())
    enrollment = service.create_enrollment(honest.identity)
    service.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    completed = _complete_enrollment(service, honest, enrollment.enrollment_id)
    app = FastAPI()
    app.include_router(daemon_api.create_router(service, owner_resolver=lambda request: "owner-a"))
    client = TestClient(app)

    attacker_responses = []
    for index in range(challenge_capacity):
        attacker_responses.append(
            client.post(
                "/v1/daemon-access-tokens/challenge",
                json={
                    "daemon_id": completed.daemon_id,
                    **attacker.challenge_creation_proof(
                        completed.daemon_id,
                        timestamp=int(now[0]),
                        nonce=f"attacker-{index}",
                    ),
                },
            )
        )

    rows_after_attack = service._connection.execute(
        "SELECT COUNT(*) FROM daemon_challenges"
    ).fetchone()[0]
    proof_rows_after_attack = service._connection.execute(
        "SELECT COUNT(*) FROM daemon_challenge_creation_nonces"
    ).fetchone()[0]
    accepted = client.post(
        "/v1/daemon-access-tokens/challenge",
        json={
            "daemon_id": completed.daemon_id,
            **honest.challenge_creation_proof(
                completed.daemon_id,
                timestamp=int(now[0]),
                nonce="honest-after-attack",
            ),
        },
    )
    challenge_rows = service._connection.execute(
        "SELECT COUNT(*) FROM daemon_challenges"
    ).fetchone()[0]

    assert (
        [response.status_code for response in attacker_responses],
        [response.json().get("error", {}).get("code") for response in attacker_responses],
        rows_after_attack,
        proof_rows_after_attack,
        challenge_rows,
        accepted.status_code,
    ) == (
        [401] * challenge_capacity,
        ["INVALID_SIGNATURE"] * challenge_capacity,
        0,
        0,
        1,
        201,
    )


def test_challenge_creation_proof_replay_is_rejected(auth_harness):
    _, daemon_api, service, signer, completed, _, now = auth_harness
    proof = signer.challenge_creation_proof(
        completed.daemon_id,
        timestamp=int(now[0]),
        nonce="challenge-create-replay",
    )

    service.create_challenge(completed.daemon_id, **proof)
    with pytest.raises(daemon_api.DaemonApiError) as replayed:
        service.create_challenge(completed.daemon_id, **proof)

    assert replayed.value.status == 401
    assert replayed.value.code == "REPLAY_DETECTED"


@pytest.mark.parametrize("offset", [-61, 61])
def test_challenge_creation_proof_rejects_clock_skew(auth_harness, offset):
    _, daemon_api, service, signer, completed, _, now = auth_harness
    proof = signer.challenge_creation_proof(
        completed.daemon_id,
        timestamp=int(now[0]) + offset,
        nonce=f"challenge-create-skew-{offset}",
    )

    with pytest.raises(daemon_api.DaemonApiError) as skewed:
        service.create_challenge(completed.daemon_id, **proof)

    assert skewed.value.status == 401
    assert skewed.value.code == "CLOCK_SKEW"


def test_request_rate_and_outstanding_nonce_caps_are_per_daemon(auth_harness, monkeypatch):
    daemon_auth, daemon_api, service, signer, _, token, now = auth_harness
    monkeypatch.setattr(daemon_api, "_REQUEST_RATE_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(daemon_api, "_MAX_OUTSTANDING_NONCES", 10)
    for index in range(2):
        signed = _signed_request(daemon_auth, signer, token, now=now[0], nonce=f"rate-{index}")
        service.verify_request(token.value, signed, b"{}", expected_owner_user_id="owner-a")
    rate_limited = _signed_request(daemon_auth, signer, token, now=now[0], nonce="rate-limited")
    with pytest.raises(daemon_api.DaemonApiError) as rate:
        service.verify_request(
            token.value,
            rate_limited,
            b"{}",
            expected_owner_user_id="owner-a",
        )
    assert rate.value.status == 429
    assert rate.value.code == "DAEMON_RATE_LIMITED"

    now[0] += 61
    monkeypatch.setattr(daemon_api, "_MAX_OUTSTANDING_NONCES", 2)
    nonce_capped = _signed_request(daemon_auth, signer, token, now=now[0], nonce="nonce-capped")
    with pytest.raises(daemon_api.DaemonApiError) as capacity:
        service.verify_request(
            token.value,
            nonce_capped,
            b"{}",
            expected_owner_user_id="owner-a",
        )
    assert capacity.value.status == 429
    assert capacity.value.code == "DAEMON_NONCE_CAPACITY"


def test_request_nonce_capacity_has_five_minute_rate_headroom():
    _, daemon_api = _contracts()

    assert daemon_api._MAX_OUTSTANDING_NONCES >= 660


def test_positive_fresh_signed_request_succeeds(auth_harness):
    daemon_auth, _, service, signer, completed, token, now = auth_harness
    signed = _signed_request(daemon_auth, signer, token, now=now[0])

    principal = service.verify_request(
        token.value,
        signed,
        b"{}",
        expected_owner_user_id="owner-a",
    )

    assert principal.daemon_id == completed.daemon_id
    assert principal.owner_user_id == "owner-a"
    assert principal.credential_epoch == 1


def test_authenticated_request_principal_is_bound_into_platform_lease_grant(
    auth_harness, tmp_path
):
    from uuid import uuid4

    from tinyassets.api.execution_jobs import grant_job_lease
    from tinyassets.branch_tasks import BranchTask
    from tinyassets.runtime.lease_store import LeaseStore, RecordReference

    daemon_auth, _, service, signer, completed, token, now = auth_harness
    signed = _signed_request(
        daemon_auth,
        signer,
        token,
        now=now[0],
        nonce="lease-grant",
    )
    principal = service.verify_request(
        token.value,
        signed,
        b"{}",
        expected_owner_user_id="owner-a",
    )
    grant_key = SigningKey.generate()
    store = LeaseStore(
        tmp_path / "leases.sqlite3",
        key_registry=service,
        grant_signing_key=grant_key,
    )
    task = BranchTask(
        branch_task_id=str(uuid4()),
        branch_def_id="branch-loop",
        universe_id="universe-a",
        queued_at="2026-07-19T12:00:00Z",
    )
    store.add_task(task)

    lease = grant_job_lease(
        store,
        job_id=task.branch_task_id,
        authenticated_daemon=principal,
        bind_capsule=lambda _identity: RecordReference(
            record_id=str(uuid4()),
            content_sha256="a" * 64,
        ),
    )

    with store._connect() as connection:
        grant = store._verified_lease_grant(
            store._task_row(connection, task.branch_task_id)
        )
    assert grant["job_id"] == task.branch_task_id
    assert grant["lease_id"] == lease.lease_id
    assert grant["fence"] == lease.fence
    assert grant["daemon_id"] == completed.daemon_id == principal.daemon_id
    assert grant["owner_user_id"] == completed.owner_user_id
    assert grant["device_key_id"] == completed.key_thumbprint
    assert grant["device_key_epoch"] == completed.credential_epoch
    assert (
        base64.b64decode(grant["device_verify_key"])
        == signer.identity.ed25519_public_key
    )


def test_replay_of_previously_valid_nonce_and_timestamp_is_rejected(auth_harness):
    daemon_auth, daemon_api, service, signer, _, token, now = auth_harness
    signed = _signed_request(daemon_auth, signer, token, now=now[0], nonce="replay-me")
    service.verify_request(token.value, signed, b"{}", expected_owner_user_id="owner-a")

    with pytest.raises(daemon_api.DaemonApiError) as replay:
        service.verify_request(token.value, signed, b"{}", expected_owner_user_id="owner-a")

    assert replay.value.status == 401
    assert replay.value.code == "REPLAY_DETECTED"


def test_replay_is_rejected_after_access_token_renewal(auth_harness):
    daemon_auth, daemon_api, service, signer, completed, token, now = auth_harness
    signed = _signed_request(daemon_auth, signer, token, now=now[0], nonce="cross-token")
    service.verify_request(token.value, signed, b"{}", expected_owner_user_id="owner-a")
    challenge = _create_challenge(service, signer, completed.daemon_id)
    renewed = service.issue_access_token(
        completed.daemon_id,
        challenge.challenge,
        signer.sign_challenge(completed.daemon_id, challenge.challenge),
    )

    with pytest.raises(daemon_api.DaemonApiError) as replay:
        service.verify_request(renewed.value, signed, b"{}", expected_owner_user_id="owner-a")

    assert replay.value.code == "REPLAY_DETECTED"


def test_concurrent_replay_across_service_instances_allows_exactly_one(tmp_path):
    daemon_auth, daemon_api = _contracts()
    now = time.time()
    db_path = tmp_path / "concurrent-replay.sqlite3"
    first = daemon_api.DaemonEnrollmentService(db_path=db_path, clock=lambda: now)
    signer = daemon_auth.DaemonSigner("concurrent-device", key_store=_MemoryKeyStore())
    enrollment = first.create_enrollment(signer.identity)
    first.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    completed = _complete_enrollment(first, signer, enrollment.enrollment_id)
    challenge = _create_challenge(first, signer, completed.daemon_id)
    token = first.issue_access_token(
        completed.daemon_id,
        challenge.challenge,
        signer.sign_challenge(completed.daemon_id, challenge.challenge),
    )
    second = daemon_api.DaemonEnrollmentService(db_path=db_path, clock=lambda: now)
    signed = _signed_request(
        daemon_auth,
        signer,
        token,
        now=now,
        nonce="concurrent-replay",
    )
    barrier = threading.Barrier(2)

    def verify(service):
        barrier.wait()
        try:
            service.verify_request(
                token.value,
                signed,
                b"{}",
                expected_owner_user_id="owner-a",
            )
            return "accepted"
        except daemon_api.DaemonApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(verify, (first, second)))

    assert sorted(results) == ["REPLAY_DETECTED", "accepted"]


def test_revocation_cannot_commit_between_request_validation_and_nonce_consume(
    tmp_path, monkeypatch
):
    daemon_auth, daemon_api = _contracts()
    now = time.time()
    db_path = tmp_path / "request-revocation-race.sqlite3"
    verifier = daemon_api.DaemonEnrollmentService(db_path=db_path, clock=lambda: now)
    revoker = daemon_api.DaemonEnrollmentService(db_path=db_path, clock=lambda: now)
    signer = daemon_auth.DaemonSigner("request-race-device", key_store=_MemoryKeyStore())
    enrollment = verifier.create_enrollment(signer.identity)
    verifier.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    completed = _complete_enrollment(verifier, signer, enrollment.enrollment_id)
    challenge = _create_challenge(verifier, signer, completed.daemon_id)
    token = verifier.issue_access_token(
        completed.daemon_id,
        challenge.challenge,
        signer.sign_challenge(completed.daemon_id, challenge.challenge),
    )
    signed = _signed_request(daemon_auth, signer, token, now=now, nonce="request-revocation-race")
    signature_entered = threading.Event()
    release_signature = threading.Event()
    revoke_started = threading.Event()
    real_verify_key = VerifyKey

    class BlockingVerifyKey:
        def __init__(self, public_key):
            self._delegate = real_verify_key(public_key)

        def verify(self, *args, **kwargs):
            signature_entered.set()
            assert release_signature.wait(2), "signature test gate was not released"
            return self._delegate.verify(*args, **kwargs)

    monkeypatch.setattr(daemon_api, "VerifyKey", BlockingVerifyKey)

    def revoke():
        revoke_started.set()
        return revoker.revoke_daemon("owner-a", completed.daemon_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        verify_future = executor.submit(
            verifier.verify_request,
            token.value,
            signed,
            b"{}",
            expected_owner_user_id="owner-a",
        )
        assert signature_entered.wait(2)
        revoke_future = executor.submit(revoke)
        assert revoke_started.wait(2)
        try:
            with pytest.raises(FutureTimeoutError):
                revoke_future.result(timeout=0.2)
        finally:
            release_signature.set()
        principal = verify_future.result(timeout=2)
        assert revoke_future.result(timeout=2) == 2

    assert principal.credential_epoch == 1
    post_revoke = _signed_request(
        daemon_auth, signer, token, now=now, nonce="request-after-revocation"
    )
    with pytest.raises(daemon_api.DaemonApiError) as rejected:
        verifier.verify_request(
            token.value,
            post_revoke,
            b"{}",
            expected_owner_user_id="owner-a",
        )
    assert rejected.value.code == "CREDENTIAL_REVOKED"


def test_revocation_cannot_commit_between_challenge_validation_and_token_mint(
    tmp_path, monkeypatch
):
    daemon_auth, daemon_api = _contracts()
    now = time.time()
    db_path = tmp_path / "token-revocation-race.sqlite3"
    issuer = daemon_api.DaemonEnrollmentService(db_path=db_path, clock=lambda: now)
    revoker = daemon_api.DaemonEnrollmentService(db_path=db_path, clock=lambda: now)
    signer = daemon_auth.DaemonSigner("token-race-device", key_store=_MemoryKeyStore())
    enrollment = issuer.create_enrollment(signer.identity)
    issuer.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    completed = _complete_enrollment(issuer, signer, enrollment.enrollment_id)
    challenge = _create_challenge(issuer, signer, completed.daemon_id)
    challenge_signature = signer.sign_challenge(completed.daemon_id, challenge.challenge)
    signature_entered = threading.Event()
    release_signature = threading.Event()
    revoke_started = threading.Event()
    real_verify_key = VerifyKey

    class BlockingVerifyKey:
        def __init__(self, public_key):
            self._delegate = real_verify_key(public_key)

        def verify(self, *args, **kwargs):
            signature_entered.set()
            assert release_signature.wait(2), "signature test gate was not released"
            return self._delegate.verify(*args, **kwargs)

    monkeypatch.setattr(daemon_api, "VerifyKey", BlockingVerifyKey)

    def revoke():
        revoke_started.set()
        return revoker.revoke_daemon("owner-a", completed.daemon_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        issue_future = executor.submit(
            issuer.issue_access_token,
            completed.daemon_id,
            challenge.challenge,
            challenge_signature,
        )
        assert signature_entered.wait(2)
        revoke_future = executor.submit(revoke)
        assert revoke_started.wait(2)
        try:
            with pytest.raises(FutureTimeoutError):
                revoke_future.result(timeout=0.2)
        finally:
            release_signature.set()
        token = issue_future.result(timeout=2)
        assert revoke_future.result(timeout=2) == 2

    assert token.credential_epoch == 1
    signed = _signed_request(daemon_auth, signer, token, now=now, nonce="token-after-revocation")
    with pytest.raises(daemon_api.DaemonApiError) as rejected:
        issuer.verify_request(
            token.value,
            signed,
            b"{}",
            expected_owner_user_id="owner-a",
        )
    assert rejected.value.code == "CREDENTIAL_REVOKED"


def test_key_substitution_is_rejected(auth_harness):
    daemon_auth, daemon_api, service, _, _, token, now = auth_harness
    attacker = daemon_auth.DaemonSigner("attacker", key_store=_MemoryKeyStore())
    body_hash = daemon_auth.request_body_hash(b"{}")
    signature = attacker.sign(
        daemon_auth.canonical_request(
            "POST",
            "/v1/execution-requests/claim",
            "limit=1",
            {},
            body_hash,
            int(now[0]),
            "attacker",
        )
    )
    forged = daemon_auth.SignedRequest(
        method="POST",
        path="/v1/execution-requests/claim",
        query="limit=1",
        signed_headers=(),
        body_hash=body_hash,
        timestamp=int(now[0]),
        nonce="attacker",
        signature=base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii"),
    )

    with pytest.raises(daemon_api.DaemonApiError) as denied:
        service.verify_request(token.value, forged, b"{}", expected_owner_user_id="owner-a")

    assert denied.value.status == 401
    assert denied.value.code == "INVALID_SIGNATURE"


def test_owner_crossover_is_rejected(auth_harness):
    daemon_auth, daemon_api, service, signer, _, token, now = auth_harness
    signed = _signed_request(daemon_auth, signer, token, now=now[0], nonce="owner-cross")

    with pytest.raises(daemon_api.DaemonApiError) as denied:
        service.verify_request(
            token.value,
            signed,
            b"{}",
            expected_owner_user_id="owner-b",
        )

    assert denied.value.status == 403
    assert denied.value.code == "OWNER_SCOPE_DENIED"


def test_owner_scope_cannot_be_omitted(auth_harness):
    daemon_auth, _, service, signer, _, token, now = auth_harness
    signed = _signed_request(
        daemon_auth,
        signer,
        token,
        now=now[0],
        nonce="owner-required",
    )

    with pytest.raises(TypeError):
        service.verify_request(token.value, signed, b"{}")


def test_epoch_increment_immediately_rejects_existing_token(auth_harness):
    daemon_auth, daemon_api, service, signer, completed, token, now = auth_harness
    service.revoke_daemon("owner-a", completed.daemon_id)
    signed = _signed_request(daemon_auth, signer, token, now=now[0], nonce="after-revoke")

    with pytest.raises(daemon_api.DaemonApiError) as revoked:
        service.verify_request(token.value, signed, b"{}", expected_owner_user_id="owner-a")

    assert revoked.value.status == 410
    assert revoked.value.code == "CREDENTIAL_REVOKED"


def test_revoked_daemon_cannot_exchange_fresh_access_token(auth_harness):
    _, daemon_api, service, signer, completed, _, _ = auth_harness
    challenge = _create_challenge(service, signer, completed.daemon_id)
    service.revoke_daemon("owner-a", completed.daemon_id)

    with pytest.raises(daemon_api.DaemonApiError) as revoked:
        service.issue_access_token(
            completed.daemon_id,
            challenge.challenge,
            signer.sign_challenge(completed.daemon_id, challenge.challenge),
        )

    assert revoked.value.status == 410
    assert revoked.value.code == "CREDENTIAL_REVOKED"


def test_expired_token_is_rejected(auth_harness):
    daemon_auth, daemon_api, service, signer, _, token, now = auth_harness
    now[0] = token.expires_at + 1
    signed = _signed_request(daemon_auth, signer, token, now=now[0], nonce="expired")

    with pytest.raises(daemon_api.DaemonApiError) as expired:
        service.verify_request(token.value, signed, b"{}", expected_owner_user_id="owner-a")

    assert expired.value.status == 401
    assert expired.value.code == "TOKEN_EXPIRED"


def test_clock_skew_over_sixty_seconds_is_rejected(auth_harness):
    daemon_auth, daemon_api, service, signer, _, token, now = auth_harness
    signed = _signed_request(
        daemon_auth,
        signer,
        token,
        now=now[0] - 61,
        nonce="skewed",
    )

    with pytest.raises(daemon_api.DaemonApiError) as skewed:
        service.verify_request(token.value, signed, b"{}", expected_owner_user_id="owner-a")

    assert skewed.value.status == 401
    assert skewed.value.code == "CLOCK_SKEW"


def test_body_and_query_path_are_covered_by_signature(auth_harness):
    daemon_auth, daemon_api, service, signer, _, token, now = auth_harness
    signed = _signed_request(daemon_auth, signer, token, now=now[0], nonce="body-bound")

    with pytest.raises(daemon_api.DaemonApiError) as altered_body:
        service.verify_request(
            token.value,
            signed,
            b'{"changed":true}',
            expected_owner_user_id="owner-a",
        )
    assert altered_body.value.code == "BODY_HASH_MISMATCH"

    changed_path = daemon_auth.SignedRequest(
        method=signed.method,
        path=signed.path,
        query="limit=2",
        signed_headers=signed.signed_headers,
        body_hash=signed.body_hash,
        timestamp=signed.timestamp,
        nonce="path-bound",
        signature=signed.signature,
    )
    with pytest.raises(daemon_api.DaemonApiError) as altered_path:
        service.verify_request(token.value, changed_path, b"{}", expected_owner_user_id="owner-a")
    assert altered_path.value.code == "INVALID_SIGNATURE"


def test_canonical_request_structurally_binds_query_and_action_headers():
    daemon_auth = _daemon_auth()
    body_hash = daemon_auth.request_body_hash(b"")
    baseline = daemon_auth.canonical_request(
        "POST",
        "/v1/jobs/",
        "item=1&item=2&slash=%2F",
        {"Content-Type": "application/json", "Idempotency-Key": "job-1"},
        body_hash,
        1_800_000_000,
        "nonce-1",
    )

    assert baseline != daemon_auth.canonical_request(
        "POST",
        "/v1/jobs/",
        "item=2&item=1&slash=%2F",
        {"Content-Type": "application/json", "Idempotency-Key": "job-1"},
        body_hash,
        1_800_000_000,
        "nonce-1",
    )
    assert baseline != daemon_auth.canonical_request(
        "POST",
        "/v1/jobs/",
        "item=1&item=2&slash=%2F",
        {"Content-Type": "application/json", "Idempotency-Key": "job-2"},
        body_hash,
        1_800_000_000,
        "nonce-1",
    )
    with pytest.raises(ValueError, match="canonical uppercase"):
        daemon_auth.canonical_request(
            "post", "/v1/jobs/", "", {}, body_hash, 1_800_000_000, "nonce-1"
        )
    with pytest.raises(ValueError, match="query must be separate"):
        daemon_auth.canonical_request(
            "POST", "/v1/jobs/?item=1", "", {}, body_hash, 1_800_000_000, "nonce-1"
        )


def test_real_asgi_dependency_binds_verbatim_target_body_and_headers(tmp_path):
    import time

    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    daemon_auth, daemon_api = _contracts()
    auth_dependency = importlib.import_module("tinyassets.api.daemon_auth")
    now = time.time()
    service = daemon_api.DaemonEnrollmentService(
        db_path=tmp_path / "asgi-auth.sqlite3", clock=lambda: now
    )
    signer = daemon_auth.DaemonSigner("asgi-device", key_store=_MemoryKeyStore())
    enrollment = service.create_enrollment(signer.identity)
    service.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    completed = _complete_enrollment(service, signer, enrollment.enrollment_id)
    challenge = _create_challenge(service, signer, completed.daemon_id)
    token = service.issue_access_token(
        completed.daemon_id,
        challenge.challenge,
        signer.sign_challenge(completed.daemon_id, challenge.challenge),
    )
    session = daemon_auth.DaemonAuthSession(signer, token_supplier=lambda: token)
    app = FastAPI()
    dependency = auth_dependency.install_daemon_request_auth(
        app, service, owner_resolver=lambda request: "owner-a"
    )

    @app.post("/protected/{rest:path}")
    async def protected(principal=Depends(dependency)):
        return {"daemon_id": principal.daemon_id}

    body = b'{"job":1}'
    raw_path = "/protected/%2Ftail/"
    raw_query = "item=1&item=2&slash=%2F"
    action_headers = {
        "Content-Type": "application/json",
        "Prefer": "respond-async",
        "Idempotency-Key": "job-1",
    }
    headers = session.sign_headers(
        "POST",
        raw_path,
        raw_query,
        body,
        action_headers=action_headers,
        timestamp=int(now),
        nonce="asgi-exact-request",
    )
    headers.update(action_headers)

    with TestClient(app) as client:
        accepted = client.post(f"{raw_path}?{raw_query}", content=body, headers=headers)
        query_changed = client.post(
            f"{raw_path}?item=2&item=1&slash=%2F",
            content=body,
            headers=headers,
        )
        header_changed = client.post(
            f"{raw_path}?{raw_query}",
            content=body,
            headers={
                **headers,
                "Idempotency-Key": "job-2",
            },
        )

    assert accepted.status_code == 200
    assert accepted.json() == {"daemon_id": completed.daemon_id}
    assert query_changed.status_code == 401
    assert query_changed.json()["error"]["code"] == "INVALID_SIGNATURE"
    assert header_changed.status_code == 401
    assert header_changed.json()["error"]["code"] == "INVALID_SIGNATURE"


def test_host_pool_client_contains_no_service_role_credential_path():
    client_module = importlib.import_module("tinyassets.host_pool.client")
    source = inspect.getsource(client_module)
    normalized = source.lower().replace("_", "-")

    assert "supabase-service-role-key" not in normalized
    assert "service-role-key" not in normalized
    assert '"apikey"' not in normalized


def test_host_pool_client_signs_exact_control_plane_request(auth_harness):
    import time

    daemon_auth, _, service, signer, _, token, now = auth_harness
    now[0] = time.time()
    client_module = importlib.import_module("tinyassets.host_pool.client")
    auth = daemon_auth.DaemonAuthSession(signer, token_supplier=lambda: token)

    class FakeHttp:
        def __init__(self) -> None:
            self.call = None

        def request(self, method, url, headers, body, timeout):
            self.call = (method, url, headers, body, timeout)
            from urllib.parse import urlsplit

            parsed = urlsplit(url)
            service.verify_headers(
                method,
                parsed.path,
                parsed.query,
                headers,
                body,
                expected_owner_user_id="owner-a",
            )
            return 200, "[]"

    http = FakeHttp()
    client = client_module.HostPoolClient(
        control_plane_url="https://control.example",
        auth=auth,
        http=http,
    )
    client.list_pending_requests("cap-a", limit=1)

    method, url, headers, body, _ = http.call
    assert method == "GET"
    assert url.startswith("https://control.example/v1/execution-requests?")
    assert headers["Authorization"] == f"Bearer {token.value}"
    assert headers["X-TinyAssets-Signature"]
    assert headers["X-TinyAssets-Nonce"]
    assert headers["X-TinyAssets-Timestamp"]
    assert body is None


def test_sign_headers_uses_one_token_snapshot():
    daemon_auth = _daemon_auth()
    signer = daemon_auth.DaemonSigner("single-token", key_store=_MemoryKeyStore())
    calls = []

    def token_supplier():
        calls.append(1)
        return daemon_auth.AccessToken(
            value="token-1",
            daemon_id="daemon-1",
            key_thumbprint=signer.identity.key_thumbprint,
            credential_epoch=1,
            expires_at=time.time() + 299,
        )

    session = daemon_auth.DaemonAuthSession(signer, token_supplier=token_supplier)
    headers = session.sign_headers("GET", "/v1/execution-requests", "", None)
    session.sign_headers("GET", "/v1/execution-requests", "cursor=next", None)

    assert len(calls) == 1
    assert headers["Authorization"] == "Bearer token-1"


def test_auth_session_rejects_supplied_token_over_five_minutes(monkeypatch):
    daemon_auth = _daemon_auth()
    now = 1_800_000_000.0
    monkeypatch.setattr(daemon_auth.time, "time", lambda: now)
    signer = daemon_auth.DaemonSigner("long-session-token", key_store=_MemoryKeyStore())
    token = daemon_auth.AccessToken(
        value="too-long",
        daemon_id="daemon-1",
        key_thumbprint=signer.identity.key_thumbprint,
        credential_epoch=1,
        expires_at=now + 301,
    )
    session = daemon_auth.DaemonAuthSession(signer, token_supplier=lambda: token)

    with pytest.raises(ValueError, match="five-minute"):
        session.sign_headers("GET", "/v1/jobs", "", None)


@pytest.mark.parametrize(
    "expires_at",
    [float("nan"), float("inf"), float("-inf")],
    ids=["nan", "positive-infinity", "negative-infinity"],
)
def test_auth_session_rejects_non_finite_supplied_token_expiry(monkeypatch, expires_at):
    daemon_auth = _daemon_auth()
    now = 1_800_000_000.0
    monkeypatch.setattr(daemon_auth.time, "time", lambda: now)
    signer = daemon_auth.DaemonSigner("non-finite-session-token", key_store=_MemoryKeyStore())
    token = daemon_auth.AccessToken(
        value="non-finite",
        daemon_id="daemon-1",
        key_thumbprint=signer.identity.key_thumbprint,
        credential_epoch=1,
        expires_at=expires_at,
    )
    session = daemon_auth.DaemonAuthSession(signer, token_supplier=lambda: token)

    with pytest.raises(ValueError, match="finite"):
        session.sign_headers("GET", "/v1/jobs", "", None)


def test_enrollment_client_rejects_issued_token_over_five_minutes(monkeypatch):
    daemon_auth = _daemon_auth()
    registration = importlib.import_module("tinyassets.host_pool.registration")
    now = 1_800_000_000.0
    monkeypatch.setattr(registration.time, "time", lambda: now)
    signer = daemon_auth.DaemonSigner("long-issued-token", key_store=_MemoryKeyStore())

    class FakeHttp:
        responses = [
            (201, {"challenge": "challenge-1"}),
            (
                201,
                {
                    "access_token": "too-long",
                    "token_type": "Bearer",
                    "daemon_id": "daemon-1",
                    "key_thumbprint": signer.identity.key_thumbprint,
                    "credential_epoch": 1,
                    "expires_at": now + 301,
                },
            ),
        ]

        def request(self, method, url, headers, body, timeout):
            status, payload = self.responses.pop(0)
            return status, json.dumps(payload)

    client = registration.DaemonEnrollmentClient("https://control.example", http=FakeHttp())
    with pytest.raises(registration.DaemonEnrollmentError) as rejected:
        client.issue_access_token(signer, "daemon-1")

    assert rejected.value.code == "TOKEN_LIFETIME_INVALID"


@pytest.mark.parametrize(
    "expires_at",
    [float("nan"), float("inf"), float("-inf")],
    ids=["nan", "positive-infinity", "negative-infinity"],
)
def test_enrollment_client_rejects_non_finite_issued_token_expiry(monkeypatch, expires_at):
    daemon_auth = _daemon_auth()
    registration = importlib.import_module("tinyassets.host_pool.registration")
    now = 1_800_000_000.0
    monkeypatch.setattr(registration.time, "time", lambda: now)
    signer = daemon_auth.DaemonSigner("non-finite-issued-token", key_store=_MemoryKeyStore())

    class FakeHttp:
        responses = [
            (201, {"challenge": "challenge-1"}),
            (
                201,
                {
                    "access_token": "non-finite",
                    "token_type": "Bearer",
                    "daemon_id": "daemon-1",
                    "key_thumbprint": signer.identity.key_thumbprint,
                    "credential_epoch": 1,
                    "expires_at": expires_at,
                },
            ),
        ]

        def request(self, method, url, headers, body, timeout):
            status, payload = self.responses.pop(0)
            return status, json.dumps(payload)

    client = registration.DaemonEnrollmentClient("https://control.example", http=FakeHttp())
    with pytest.raises(registration.DaemonEnrollmentError) as rejected:
        client.issue_access_token(signer, "daemon-1")

    assert rejected.value.code == "TOKEN_LIFETIME_INVALID"


def test_enrollment_client_posts_start_complete_and_signed_challenge():
    daemon_auth, _ = _contracts()
    registration = importlib.import_module("tinyassets.host_pool.registration")
    signer = daemon_auth.DaemonSigner("client-enroll", key_store=_MemoryKeyStore())

    class FakeHttp:
        def __init__(self) -> None:
            self.calls = []
            self.responses = [
                (201, {"enrollment_id": "enr-1", "verification_code": "AB12CD34EF56"}),
                (
                    200,
                    {
                        "daemon_id": "daemon-1",
                        "credential_epoch": 1,
                        "key_thumbprint": signer.identity.key_thumbprint,
                    },
                ),
                (201, {"challenge": "challenge-1", "expires_at": time.time() + 60}),
                (
                    201,
                    {
                        "access_token": "token-1",
                        "token_type": "Bearer",
                        "daemon_id": "daemon-1",
                        "key_thumbprint": signer.identity.key_thumbprint,
                        "credential_epoch": 1,
                        "expires_at": time.time() + 300,
                    },
                ),
            ]

        def request(self, method, url, headers, body, timeout):
            self.calls.append((method, url, headers, body, timeout))
            status, response = self.responses.pop(0)
            return status, json.dumps(response)

    http = FakeHttp()
    client = registration.DaemonEnrollmentClient(
        "https://control.example",
        http=http,
    )
    handoff = client.begin(signer)
    completed = client.complete(signer, handoff.enrollment_id)
    token = client.issue_access_token(signer, completed.daemon_id)

    assert handoff.verification_code == "AB12CD34EF56"
    assert token.value == "token-1"
    assert [call[0] for call in http.calls] == ["POST", "POST", "POST", "POST"]
    assert http.calls[0][1].endswith("/v1/daemon-enrollments")
    assert http.calls[1][1].endswith("/v1/daemon-enrollments/enr-1:complete")
    assert http.calls[2][1].endswith("/v1/daemon-access-tokens/challenge")
    assert http.calls[3][1].endswith("/v1/daemon-access-tokens")
    challenge_request = json.loads(http.calls[2][3])
    VerifyKey(signer.identity.ed25519_public_key).verify(
        daemon_auth.canonical_challenge_creation(
            challenge_request["daemon_id"],
            challenge_request["timestamp"],
            challenge_request["nonce"],
        ),
        base64.urlsafe_b64decode(challenge_request["signature"] + "=="),
    )
    token_request = json.loads(http.calls[3][3])
    assert token_request["daemon_id"] == "daemon-1"
    assert base64.urlsafe_b64decode(token_request["signature"] + "==")
    assert hashlib.sha256(signer.identity.ed25519_public_key).digest()


def test_enrollment_client_preserves_standard_error_fields():
    daemon_auth = _daemon_auth()
    registration = importlib.import_module("tinyassets.host_pool.registration")
    signer = daemon_auth.DaemonSigner("error-client", key_store=_MemoryKeyStore())

    class FakeHttp:
        def request(self, method, url, headers, body, timeout):
            return 503, json.dumps(
                {
                    "error": {
                        "code": "CONTROL_PLANE_UNAVAILABLE",
                        "message": "Try again later",
                        "retryable": True,
                        "request_id": "req-503",
                        "details": {"region": "west"},
                    }
                }
            )

    client = registration.DaemonEnrollmentClient(
        "https://control.example",
        http=FakeHttp(),
    )

    with pytest.raises(registration.DaemonEnrollmentError) as failed:
        client.complete(signer, "enrollment-1")

    assert failed.value.retryable is True
    assert failed.value.request_id == "req-503"
    assert failed.value.details == {"region": "west"}


def test_enrollment_transport_failure_is_typed_retryable_and_sanitized():
    daemon_auth = _daemon_auth()
    registration = importlib.import_module("tinyassets.host_pool.registration")
    signer = daemon_auth.DaemonSigner("transport-failure", key_store=_MemoryKeyStore())

    class FailingHttp:
        def request(self, method, url, headers, body, timeout):
            raise OSError("TRANSPORT_SECRET_SENTINEL")

    client = registration.DaemonEnrollmentClient("https://control.example", http=FailingHttp())
    with pytest.raises(registration.DaemonEnrollmentError) as failed:
        client.begin(signer)

    assert failed.value.status == 0
    assert failed.value.code == "CONTROL_PLANE_UNAVAILABLE"
    assert failed.value.retryable is True
    assert "TRANSPORT_SECRET_SENTINEL" not in str(failed.value)
    assert failed.value.__cause__ is None
    assert failed.value.__context__ is None
    assert "TRANSPORT_SECRET_SENTINEL" not in "".join(traceback.format_exception(failed.value))


def test_enrollment_malformed_json_body_is_unreachable_from_sanitized_error():
    daemon_auth = _daemon_auth()
    registration = importlib.import_module("tinyassets.host_pool.registration")
    signer = daemon_auth.DaemonSigner("malformed-response", key_store=_MemoryKeyStore())

    class MalformedHttp:
        def request(self, method, url, headers, body, timeout):
            return 200, '{"body":"TRANSPORT_SECRET_SENTINEL"'

    client = registration.DaemonEnrollmentClient("https://control.example", http=MalformedHttp())
    with pytest.raises(registration.DaemonEnrollmentError) as failed:
        client.begin(signer)

    assert "TRANSPORT_SECRET_SENTINEL" not in str(failed.value)
    assert failed.value.__cause__ is None
    assert failed.value.__context__ is None
    assert "TRANSPORT_SECRET_SENTINEL" not in "".join(traceback.format_exception(failed.value))


def test_error_contract_is_typed_and_fail_closed():
    _, daemon_api = _contracts()
    error = daemon_api.DaemonApiError(
        401,
        "INVALID_AUTHENTICATION",
        "Authentication failed",
        retryable=False,
        details={"reason": "invalid"},
        request_id="req-1",
    )

    assert error.as_dict() == {
        "error": {
            "code": "INVALID_AUTHENTICATION",
            "message": "Authentication failed",
            "retryable": False,
            "request_id": "req-1",
            "details": {"reason": "invalid"},
        }
    }


@pytest.mark.filterwarnings(
    "ignore:Using `httpx` with `starlette.testclient` is deprecated:UserWarning"
)
def test_http_enrollment_routes_complete_owner_approved_token_flow(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    daemon_auth, daemon_api = _contracts()
    signer = daemon_auth.DaemonSigner("http-enroll", key_store=_MemoryKeyStore())
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "http-auth.sqlite3")
    owner_resolution_disabled = [False]

    def owner_resolver(request):
        if owner_resolution_disabled[0]:
            raise RuntimeError("owner session is unavailable")
        return "owner-http"

    app = FastAPI()
    app.include_router(daemon_api.create_router(service, owner_resolver=owner_resolver))
    client = TestClient(app)

    start = client.post("/v1/daemon-enrollments", json=signer.identity.as_enrollment_payload())
    assert start.status_code == 201
    handoff = start.json()
    approved = client.post(
        "/v1/daemon-enrollments:approve",
        json={
            "enrollment_id": handoff["enrollment_id"],
            "verification_code": handoff["verification_code"],
        },
    )
    assert approved.status_code == 200
    owner_resolution_disabled[0] = True
    completed = client.post(
        f"/v1/daemon-enrollments/{handoff['enrollment_id']}:complete",
        json=signer.enrollment_completion_proof(handoff["enrollment_id"]),
    )
    assert completed.status_code == 200
    assert "owner_user_id" not in completed.json()
    owner_resolution_disabled[0] = False
    daemon_id = completed.json()["daemon_id"]
    unsigned_challenge = client.post(
        "/v1/daemon-access-tokens/challenge",
        json={"daemon_id": daemon_id},
    )
    assert unsigned_challenge.status_code == 401
    assert unsigned_challenge.json()["error"]["code"] == "INVALID_AUTHENTICATION"
    challenge = client.post(
        "/v1/daemon-access-tokens/challenge",
        json={
            "daemon_id": daemon_id,
            **signer.challenge_creation_proof(daemon_id),
        },
    )
    assert challenge.status_code == 201
    challenge_value = challenge.json()["challenge"]
    issued = client.post(
        "/v1/daemon-access-tokens",
        json={
            "daemon_id": daemon_id,
            "challenge": challenge_value,
            "signature": signer.sign_challenge(daemon_id, challenge_value),
        },
    )
    assert issued.status_code == 201
    assert issued.json()["token_type"] == "Bearer"

    revoked = client.post(f"/v1/daemons/{daemon_id}:revoke", json={})
    assert revoked.status_code == 200
    assert revoked.json() == {"credential_epoch": 2}

    revoked_challenge = client.post(
        "/v1/daemon-access-tokens/challenge",
        json={
            "daemon_id": daemon_id,
            **signer.challenge_creation_proof(
                daemon_id,
                nonce="challenge-after-revocation",
            ),
        },
    )
    assert revoked_challenge.status_code == 410
    assert revoked_challenge.json()["error"]["code"] == "CREDENTIAL_REVOKED"

    malformed = client.post("/v1/daemon-access-tokens", json={})
    assert malformed.status_code == 400
    assert set(malformed.json()["error"]) == {
        "code",
        "message",
        "retryable",
        "request_id",
        "details",
    }


@pytest.mark.filterwarnings(
    "ignore:Using `httpx` with `starlette.testclient` is deprecated:UserWarning"
)
def test_http_enrollment_malformed_identity_uses_standard_error_contract(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    _, daemon_api = _contracts()
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "malformed.sqlite3")
    app = FastAPI()
    app.include_router(daemon_api.create_router(service, owner_resolver=lambda request: "owner"))
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/v1/daemon-enrollments",
        json={
            "installation_id": None,
            "ed25519_public_key": "AA",
            "x25519_public_key": "AA",
            "installation_nonce": "AA",
        },
    )

    assert response.status_code == 400
    assert set(response.json()["error"]) == {
        "code",
        "message",
        "retryable",
        "request_id",
        "details",
    }


@pytest.mark.filterwarnings(
    "ignore:Using `httpx` with `starlette.testclient` is deprecated:UserWarning"
)
def test_http_unexpected_control_plane_failure_is_typed_503(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    _, daemon_api = _contracts()
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "failure.sqlite3")

    def unavailable_owner(request):
        raise RuntimeError("secret backend detail")

    app = FastAPI()
    app.include_router(daemon_api.create_router(service, owner_resolver=unavailable_owner))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/v1/daemon-enrollments:approve",
        json={"enrollment_id": "enrollment-1", "verification_code": "ABCDEFGH1234"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CONTROL_PLANE_UNAVAILABLE"
    assert response.json()["error"]["retryable"] is True
    assert "secret backend detail" not in response.text
