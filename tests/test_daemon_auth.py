from __future__ import annotations

import base64
import hashlib
import importlib
import inspect
import json
import threading
from concurrent.futures import ThreadPoolExecutor

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
    now = [1_800_000_000.0]
    service = daemon_api.DaemonEnrollmentService(
        db_path=tmp_path / "daemon-auth.sqlite3",
        clock=lambda: now[0],
    )
    signer = daemon_auth.DaemonSigner("installation-a", key_store=_MemoryKeyStore())
    enrollment = service.create_enrollment(signer.identity)
    service.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    completed = service.complete_enrollment(enrollment.enrollment_id)
    challenge = service.create_challenge(completed.daemon_id)
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
        "/v1/execution-requests/claim?limit=1",
        body,
        timestamp=int(now),
        nonce=nonce,
    )


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
    assert 6 <= len(enrollment.verification_code) <= 10
    assert enrollment.verification_code.isalnum()
    with pytest.raises(daemon_api.DaemonApiError) as denied:
        service.complete_enrollment(enrollment.enrollment_id)
    assert denied.value.status == 403
    assert set(denied.value.as_dict()["error"]) == {
        "code",
        "message",
        "retryable",
        "request_id",
        "details",
    }

    service.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    complete = service.complete_enrollment(enrollment.enrollment_id)
    assert complete.owner_user_id == "owner-a"
    assert complete.daemon_id
    assert complete.credential_epoch == 1


def test_owner_can_approve_by_short_verification_code(tmp_path):
    daemon_auth, daemon_api = _contracts()
    service = daemon_api.DaemonEnrollmentService(db_path=tmp_path / "auth.sqlite3")
    signer = daemon_auth.DaemonSigner("install-code", key_store=_MemoryKeyStore())
    enrollment = service.create_enrollment(signer.identity)

    service.approve_verification_code(enrollment.verification_code, owner_user_id="owner-a")
    completed = service.complete_enrollment(enrollment.enrollment_id)

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
    completed = service.complete_enrollment(enrollment.enrollment_id)
    challenge = service.create_challenge(completed.daemon_id)

    with pytest.raises(daemon_api.DaemonApiError) as denied:
        service.issue_access_token(
            completed.daemon_id,
            challenge.challenge,
            signer.sign_challenge(completed.daemon_id, challenge.challenge),
            lifetime_seconds=301,
        )

    assert denied.value.status == 422
    assert denied.value.code == "TOKEN_LIFETIME_INVALID"


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


def test_replay_of_previously_valid_nonce_and_timestamp_is_rejected(auth_harness):
    daemon_auth, daemon_api, service, signer, _, token, now = auth_harness
    signed = _signed_request(daemon_auth, signer, token, now=now[0], nonce="replay-me")
    service.verify_request(
        token.value, signed, b"{}", expected_owner_user_id="owner-a"
    )

    with pytest.raises(daemon_api.DaemonApiError) as replay:
        service.verify_request(
            token.value, signed, b"{}", expected_owner_user_id="owner-a"
        )

    assert replay.value.status == 401
    assert replay.value.code == "REPLAY_DETECTED"


def test_replay_is_rejected_after_access_token_renewal(auth_harness):
    daemon_auth, daemon_api, service, signer, completed, token, now = auth_harness
    signed = _signed_request(daemon_auth, signer, token, now=now[0], nonce="cross-token")
    service.verify_request(
        token.value, signed, b"{}", expected_owner_user_id="owner-a"
    )
    challenge = service.create_challenge(completed.daemon_id)
    renewed = service.issue_access_token(
        completed.daemon_id,
        challenge.challenge,
        signer.sign_challenge(completed.daemon_id, challenge.challenge),
    )

    with pytest.raises(daemon_api.DaemonApiError) as replay:
        service.verify_request(
            renewed.value, signed, b"{}", expected_owner_user_id="owner-a"
        )

    assert replay.value.code == "REPLAY_DETECTED"


def test_concurrent_replay_across_service_instances_allows_exactly_one(tmp_path):
    daemon_auth, daemon_api = _contracts()
    now = 1_800_000_000.0
    db_path = tmp_path / "concurrent-replay.sqlite3"
    first = daemon_api.DaemonEnrollmentService(db_path=db_path, clock=lambda: now)
    signer = daemon_auth.DaemonSigner("concurrent-device", key_store=_MemoryKeyStore())
    enrollment = first.create_enrollment(signer.identity)
    first.approve_enrollment(enrollment.enrollment_id, owner_user_id="owner-a")
    completed = first.complete_enrollment(enrollment.enrollment_id)
    challenge = first.create_challenge(completed.daemon_id)
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


def test_key_substitution_is_rejected(auth_harness):
    daemon_auth, daemon_api, service, _, _, token, now = auth_harness
    attacker = daemon_auth.DaemonSigner("attacker", key_store=_MemoryKeyStore())
    body_hash = daemon_auth.request_body_hash(b"{}")
    signature = attacker.sign(
        daemon_auth.canonical_request(
            "POST",
            "/v1/execution-requests/claim?limit=1",
            body_hash,
            int(now[0]),
            "attacker",
        )
    )
    forged = daemon_auth.SignedRequest(
        method="POST",
        path="/v1/execution-requests/claim?limit=1",
        body_hash=body_hash,
        timestamp=int(now[0]),
        nonce="attacker",
        signature=base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii"),
    )

    with pytest.raises(daemon_api.DaemonApiError) as denied:
        service.verify_request(
            token.value, forged, b"{}", expected_owner_user_id="owner-a"
        )

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
        service.verify_request(
            token.value, signed, b"{}", expected_owner_user_id="owner-a"
        )

    assert revoked.value.status == 410
    assert revoked.value.code == "CREDENTIAL_REVOKED"


def test_revoked_daemon_cannot_exchange_fresh_access_token(auth_harness):
    _, daemon_api, service, signer, completed, _, _ = auth_harness
    challenge = service.create_challenge(completed.daemon_id)
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
        service.verify_request(
            token.value, signed, b"{}", expected_owner_user_id="owner-a"
        )

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
        service.verify_request(
            token.value, signed, b"{}", expected_owner_user_id="owner-a"
        )

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
        path="/v1/execution-requests/claim?limit=2",
        body_hash=signed.body_hash,
        timestamp=signed.timestamp,
        nonce="path-bound",
        signature=signed.signature,
    )
    with pytest.raises(daemon_api.DaemonApiError) as altered_path:
        service.verify_request(
            token.value, changed_path, b"{}", expected_owner_user_id="owner-a"
        )
    assert altered_path.value.code == "INVALID_SIGNATURE"


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
            signed_path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            service.verify_headers(
                method,
                signed_path,
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
            expires_at=1_900_000_000,
        )

    session = daemon_auth.DaemonAuthSession(signer, token_supplier=token_supplier)
    headers = session.sign_headers("GET", "/v1/execution-requests", None)
    session.sign_headers("GET", "/v1/execution-requests?cursor=next", None)

    assert len(calls) == 1
    assert headers["Authorization"] == "Bearer token-1"


def test_enrollment_client_posts_start_complete_and_signed_challenge():
    daemon_auth, _ = _contracts()
    registration = importlib.import_module("tinyassets.host_pool.registration")
    signer = daemon_auth.DaemonSigner("client-enroll", key_store=_MemoryKeyStore())

    class FakeHttp:
        def __init__(self) -> None:
            self.calls = []
            self.responses = [
                (201, {"enrollment_id": "enr-1", "verification_code": "AB12CD34"}),
                (
                    200,
                    {
                        "daemon_id": "daemon-1",
                        "owner_user_id": "owner-a",
                        "credential_epoch": 1,
                        "key_thumbprint": signer.identity.key_thumbprint,
                    },
                ),
                (201, {"challenge": "challenge-1", "expires_at": 1_900_000_000}),
                (
                    201,
                    {
                        "access_token": "token-1",
                        "token_type": "Bearer",
                        "daemon_id": "daemon-1",
                        "key_thumbprint": signer.identity.key_thumbprint,
                        "credential_epoch": 1,
                        "expires_at": 1_900_000_000,
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
    completed = client.complete(handoff.enrollment_id)
    token = client.issue_access_token(signer, completed.daemon_id)

    assert handoff.verification_code == "AB12CD34"
    assert completed.owner_user_id == "owner-a"
    assert token.value == "token-1"
    assert [call[0] for call in http.calls] == ["POST", "POST", "POST", "POST"]
    assert http.calls[0][1].endswith("/v1/daemon-enrollments")
    assert http.calls[1][1].endswith("/v1/daemon-enrollments/enr-1:complete")
    assert http.calls[2][1].endswith("/v1/daemon-access-tokens/challenge")
    assert http.calls[3][1].endswith("/v1/daemon-access-tokens")
    token_request = json.loads(http.calls[3][3])
    assert token_request["daemon_id"] == "daemon-1"
    assert base64.urlsafe_b64decode(token_request["signature"] + "==")
    assert hashlib.sha256(signer.identity.ed25519_public_key).digest()


def test_enrollment_client_preserves_standard_error_fields():
    registration = importlib.import_module("tinyassets.host_pool.registration")

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
        client.complete("enrollment-1")

    assert failed.value.retryable is True
    assert failed.value.request_id == "req-503"
    assert failed.value.details == {"region": "west"}


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
    app = FastAPI()
    app.include_router(
        daemon_api.create_router(service, owner_resolver=lambda request: "owner-http")
    )
    client = TestClient(app)

    start = client.post("/v1/daemon-enrollments", json=signer.identity.as_enrollment_payload())
    assert start.status_code == 201
    handoff = start.json()
    approved = client.post(
        "/v1/daemon-enrollments:approve",
        json={"verification_code": handoff["verification_code"]},
    )
    assert approved.status_code == 200
    completed = client.post(
        f"/v1/daemon-enrollments/{handoff['enrollment_id']}:complete",
        json={},
    )
    assert completed.status_code == 200
    daemon_id = completed.json()["daemon_id"]
    challenge = client.post(
        "/v1/daemon-access-tokens/challenge",
        json={"daemon_id": daemon_id},
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
        json={"daemon_id": daemon_id},
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
        json={"verification_code": "ABCDEFGH"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "CONTROL_PLANE_UNAVAILABLE"
    assert response.json()["error"]["retryable"] is True
    assert "secret backend detail" not in response.text
