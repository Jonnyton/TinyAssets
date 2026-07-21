"""Raw-DML forge probes for the daemon-enrollment authority surface.

Same threat model as ``tests/test_lease_store.py`` (``_raw_dml_authority_probe``):
forge one durable projection with a direct ``sqlite3`` write and assert the
authority sink fails closed.

The specific invariant under test is that ``enrolled_daemons.key_thumbprint`` is
a *derived* value -- ``device_key_thumbprint(pk) == b64url(sha256(domain + pk))``
-- stored beside the key it is derived from. Because it is derivable, a row whose
two columns disagree is detectable without any new trust root, so the registry
must never treat such a row as a usable credential. Probes 1-4 cover that
binding; probes 5-7 pin the anchors that already hold (the Ed25519 signature and
the revocation epoch fence), so that a regression which drops them shows up here.
"""

from __future__ import annotations

import base64
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from nacl.public import PrivateKey
from nacl.signing import SigningKey

from tinyassets.api.daemon_enrollment import DaemonApiError, DaemonEnrollmentService
from tinyassets.runtime.daemon_auth import (
    DaemonSigner,
    DevicePublicIdentity,
    SignedRequest,
    _b64encode,
    canonical_challenge,
    canonical_challenge_creation,
    canonical_enrollment_completion,
    canonical_request,
    device_key_thumbprint,
    request_body_hash,
)

OWNER = "owner-a"


class _MemoryKeyStore:
    """Test-only key custody; production must use an OS keystore."""

    backend_name = "test-memory"
    hardware_non_exportable = False

    def __init__(self) -> None:
        self._keys: dict[str, tuple[SigningKey, PrivateKey, bytes]] = {}

    def load_or_create(self, installation_id: str) -> DevicePublicIdentity:
        keys = self._keys.get(installation_id)
        if keys is None:
            keys = (SigningKey.generate(), PrivateKey.generate(), PrivateKey.generate().encode())
            self._keys[installation_id] = keys
        signing_key, transfer_key, installation_nonce = keys
        return DevicePublicIdentity(
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


class _Harness:
    """An enrolled daemon holding a live access token."""

    def __init__(self, tmp_path: Path) -> None:
        self.db_path = tmp_path / "daemon-auth.sqlite3"
        self.now = [time.time()]
        self.service = DaemonEnrollmentService(db_path=self.db_path, clock=lambda: self.now[0])
        self.signer = DaemonSigner("installation-a", key_store=_MemoryKeyStore())
        enrollment = self.service.create_enrollment(self.signer.identity)
        self.enrollment_id = enrollment.enrollment_id
        self.service.approve_enrollment(self.enrollment_id, owner_user_id=OWNER)
        self.completed = self.service.complete_enrollment(
            self.enrollment_id,
            **self.signer.enrollment_completion_proof(self.enrollment_id),
        )
        self.daemon_id = self.completed.daemon_id
        self.token = self.issue_token()

    def issue_token(self):
        challenge = self.service.create_challenge(
            self.daemon_id,
            **self.signer.challenge_creation_proof(
                self.daemon_id, timestamp=int(self.service._clock())
            ),
        )
        return self.service.issue_access_token(
            self.daemon_id,
            challenge.challenge,
            self.signer.sign_challenge(self.daemon_id, challenge.challenge),
        )

    def forge(self, mutate: Callable[[sqlite3.Connection], None]) -> None:
        """Apply one raw-DML write directly to the durable projection."""
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            mutate(connection)

    def signed_request(
        self,
        signing_key: SigningKey,
        *,
        nonce: str = "probe-nonce",
        body: bytes = b"{}",
    ) -> tuple[SignedRequest, bytes]:
        body_hash = request_body_hash(body)
        timestamp = int(self.now[0])
        message = canonical_request(
            "POST", "/v1/execution-requests/claim", "limit=1", {}, body_hash, timestamp, nonce
        )
        return (
            SignedRequest(
                method="POST",
                path="/v1/execution-requests/claim",
                query="limit=1",
                signed_headers=(),
                body_hash=body_hash,
                timestamp=timestamp,
                nonce=nonce,
                signature=base64.b64encode(signing_key.sign(message).signature).decode(),
            ),
            body,
        )


@pytest.fixture
def harness(tmp_path: Path) -> _Harness:
    return _Harness(tmp_path)


def _substitute_device_key(
    daemon_id: str, attacker: SigningKey
) -> Callable[[sqlite3.Connection], None]:
    """Forge: repoint a daemon at attacker-held key material.

    Only ``ed25519_public_key`` moves. ``key_thumbprint``, ``credential_epoch``,
    ``revoked_at`` and every access-token row keep their honest values, so each
    existing token-row-vs-daemon-row cross-check still agrees.
    """

    def mutate(connection: sqlite3.Connection) -> None:
        connection.execute(
            "UPDATE enrolled_daemons SET ed25519_public_key = ? WHERE daemon_id = ?",
            (attacker.verify_key.encode(), daemon_id),
        )

    return mutate


# --------------------------------------------------------------------------
# Probes 1-4: key <-> thumbprint binding is not enforced on read.
# --------------------------------------------------------------------------


def test_substituted_device_key_cannot_authenticate_as_enrolled_daemon(
    harness: _Harness,
) -> None:
    """A repointed key must not let an attacker speak as the enrolled daemon."""
    attacker = SigningKey.generate()
    harness.forge(_substitute_device_key(harness.daemon_id, attacker))
    request, body = harness.signed_request(attacker)

    with pytest.raises(DaemonApiError) as rejection:
        harness.service.verify_request(
            harness.token.value, request, body, expected_owner_user_id=OWNER
        )

    assert rejection.value.status in {401, 410}
    print(f"SUBSTITUTED_KEY_REQUEST_REJECTED: {rejection.value.as_dict()}")


def test_substituted_device_key_cannot_mint_an_access_token(harness: _Harness) -> None:
    """Token issuance verifies the challenge with the stored key -- bind it."""
    challenge = harness.service.create_challenge(
        harness.daemon_id,
        **harness.signer.challenge_creation_proof(
            harness.daemon_id, timestamp=int(harness.service._clock())
        ),
    )
    attacker = SigningKey.generate()
    harness.forge(_substitute_device_key(harness.daemon_id, attacker))
    forged_signature = base64.b64encode(
        attacker.sign(canonical_challenge(harness.daemon_id, challenge.challenge)).signature
    ).decode()

    with pytest.raises(DaemonApiError) as rejection:
        harness.service.issue_access_token(
            harness.daemon_id, challenge.challenge, forged_signature
        )

    assert rejection.value.status in {401, 410}
    print(f"SUBSTITUTED_KEY_TOKEN_MINT_REJECTED: {rejection.value.as_dict()}")


def test_substituted_device_key_cannot_create_a_challenge(harness: _Harness) -> None:
    """Challenge creation verifies the stored key too -- bind it there as well."""
    attacker = SigningKey.generate()
    harness.forge(_substitute_device_key(harness.daemon_id, attacker))
    timestamp = int(harness.service._clock())
    nonce = "attacker-challenge-nonce"
    forged_signature = base64.b64encode(
        attacker.sign(
            canonical_challenge_creation(harness.daemon_id, timestamp, nonce)
        ).signature
    ).decode()

    with pytest.raises(DaemonApiError) as rejection:
        harness.service.create_challenge(
            harness.daemon_id, timestamp=timestamp, nonce=nonce, signature=forged_signature
        )

    assert rejection.value.status in {401, 410}
    print(f"SUBSTITUTED_KEY_CHALLENGE_REJECTED: {rejection.value.as_dict()}")


def test_resolve_device_key_refuses_a_row_whose_thumbprint_does_not_bind_its_key(
    harness: _Harness,
) -> None:
    """``resolve_device_key`` must not hand back a mismatched identity/key pair.

    Returning one would let a caller verify against attacker key material while
    attributing the result to the victim's ``device_key_id``.
    """
    attacker = SigningKey.generate()
    harness.forge(_substitute_device_key(harness.daemon_id, attacker))

    resolved = harness.service.resolve_device_key(harness.completed.key_thumbprint)

    assert resolved is None, (
        "resolve_device_key returned a credential whose device_key_id "
        f"{harness.completed.key_thumbprint!r} does not hash-bind its verify key "
        f"{device_key_thumbprint(attacker.verify_key.encode())!r}"
    )


def test_substituted_enrollment_key_cannot_complete_enrollment(tmp_path: Path) -> None:
    """The pending-enrollment row seeds ``enrolled_daemons`` -- bind it at the source."""
    now = [time.time()]
    service = DaemonEnrollmentService(db_path=tmp_path / "auth.sqlite3", clock=lambda: now[0])
    signer = DaemonSigner("installation-a", key_store=_MemoryKeyStore())
    enrollment = service.create_enrollment(signer.identity)
    service.approve_enrollment(enrollment.enrollment_id, owner_user_id=OWNER)

    attacker = SigningKey.generate()
    with sqlite3.connect(tmp_path / "auth.sqlite3") as connection:
        connection.execute(
            "UPDATE daemon_enrollments SET ed25519_public_key = ? WHERE enrollment_id = ?",
            (attacker.verify_key.encode(), enrollment.enrollment_id),
        )
    honest_proof = signer.enrollment_completion_proof(enrollment.enrollment_id)
    nonce = signer.identity.installation_nonce
    forged_signature = _b64encode(
        attacker.sign(
            canonical_enrollment_completion(enrollment.enrollment_id, nonce)
        ).signature
    )

    with pytest.raises(DaemonApiError) as rejection:
        service.complete_enrollment(
            enrollment.enrollment_id,
            installation_nonce=honest_proof["installation_nonce"],
            signature=forged_signature,
        )

    assert rejection.value.status in {401, 410}
    print(f"SUBSTITUTED_ENROLLMENT_KEY_REJECTED: {rejection.value.as_dict()}")


# --------------------------------------------------------------------------
# Probes 5-7: anchors that already hold. These pin existing protections so a
# regression that drops them fails here.
# --------------------------------------------------------------------------


def test_forged_access_token_row_cannot_authenticate_without_the_device_key(
    harness: _Harness,
) -> None:
    """Minting a token row by DML grants nothing: the signature is the anchor.

    The forged row copies the daemon's real thumbprint and epoch, so every
    token-row-vs-daemon-row cross-check agrees -- what stops it is that the
    attacker cannot sign with the enrolled key.
    """
    attacker = SigningKey.generate()
    attacker_token = "attacker-chosen-token-value"
    token_hash = DaemonEnrollmentService._token_hash(attacker_token)

    def mutate(connection: sqlite3.Connection) -> None:
        daemon = connection.execute(
            "SELECT key_thumbprint, credential_epoch FROM enrolled_daemons WHERE daemon_id = ?",
            (harness.daemon_id,),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO daemon_access_tokens (
                token_hash, daemon_id, key_thumbprint, credential_epoch, expires_at, issued_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                token_hash,
                harness.daemon_id,
                daemon["key_thumbprint"],
                daemon["credential_epoch"],
                harness.now[0] + 300,
                harness.now[0],
            ),
        )

    harness.forge(mutate)
    request, body = harness.signed_request(attacker, nonce="forged-token-nonce")

    with pytest.raises(DaemonApiError) as rejection:
        harness.service.verify_request(
            attacker_token, request, body, expected_owner_user_id=OWNER
        )

    assert rejection.value.as_dict()["error"]["code"] == "INVALID_SIGNATURE"
    print(f"FORGED_TOKEN_ROW_REJECTED: {rejection.value.as_dict()}")


def test_clearing_revoked_at_does_not_resurrect_a_revoked_access_token(
    harness: _Harness,
) -> None:
    """Un-revocation by DML is fenced by the epoch bump revocation also applies.

    Mutation note: ``verify_request`` enforces this twice -- once against the
    token/daemon JOIN and once against a re-read inside the transaction (the
    second is TOCTOU cover, not duplication). This probe goes RED only when BOTH
    fences are removed; it pins "revocation is enforced", not either fence alone.
    """
    harness.service.revoke_daemon(OWNER, harness.daemon_id)

    def mutate(connection: sqlite3.Connection) -> None:
        connection.execute(
            "UPDATE enrolled_daemons SET revoked_at = NULL WHERE daemon_id = ?",
            (harness.daemon_id,),
        )

    harness.forge(mutate)
    request, body = harness.signed_request(
        harness.signer._key_store._keys["installation-a"][0], nonce="unrevoke-nonce"
    )

    with pytest.raises(DaemonApiError) as rejection:
        harness.service.verify_request(
            harness.token.value, request, body, expected_owner_user_id=OWNER
        )

    assert rejection.value.as_dict()["error"]["code"] == "CREDENTIAL_REVOKED"
    print(f"UNREVOKED_STALE_TOKEN_REJECTED: {rejection.value.as_dict()}")


def test_reopened_challenge_cannot_mint_a_token_without_the_device_key(
    harness: _Harness,
) -> None:
    """Clearing ``used_at`` re-opens a challenge but still requires the real key."""
    challenge = harness.service.create_challenge(
        harness.daemon_id,
        **harness.signer.challenge_creation_proof(
            harness.daemon_id, timestamp=int(harness.service._clock())
        ),
    )
    harness.service.issue_access_token(
        harness.daemon_id,
        challenge.challenge,
        harness.signer.sign_challenge(harness.daemon_id, challenge.challenge),
    )

    def mutate(connection: sqlite3.Connection) -> None:
        connection.execute("UPDATE daemon_challenges SET used_at = NULL")

    harness.forge(mutate)
    attacker = SigningKey.generate()
    forged_signature = base64.b64encode(
        attacker.sign(canonical_challenge(harness.daemon_id, challenge.challenge)).signature
    ).decode()

    with pytest.raises(DaemonApiError) as rejection:
        harness.service.issue_access_token(
            harness.daemon_id, challenge.challenge, forged_signature
        )

    assert rejection.value.as_dict()["error"]["code"] == "INVALID_SIGNATURE"
    print(f"REOPENED_CHALLENGE_REJECTED: {rejection.value.as_dict()}")


# ---------------------------------------------------------------------------
# Per-fence revocation probes.
#
# `test_clearing_revoked_at_does_not_resurrect_a_revoked_access_token` above
# says so itself: it "goes RED only when BOTH fences are removed; it pins
# 'revocation is enforced', not either fence alone." A mutation run confirmed
# that -- dropping ONE revocation fence left the suite GREEN, i.e. that fence
# was load-bearing in production and unprotected by any test.
#
# Revocation is checked at five independent sinks. A probe that only fails when
# ALL of them are gone lets four regress silently. Each probe below isolates one
# sink so that removing exactly that check turns exactly this test RED.
# ---------------------------------------------------------------------------


def test_revoked_daemon_cannot_create_a_challenge(harness: _Harness) -> None:
    """Isolates the `create_challenge` fence.

    Challenge creation is the entry point of token minting: a revoked daemon that
    can still open a challenge has a live path toward credentials, even if a
    later fence happens to stop it today.
    """
    harness.service.revoke_daemon(OWNER, harness.daemon_id)

    with pytest.raises(DaemonApiError) as rejection:
        harness.service.create_challenge(
            harness.daemon_id,
            **harness.signer.challenge_creation_proof(
                harness.daemon_id, timestamp=int(harness.service._clock())
            ),
        )

    assert rejection.value.as_dict()["error"]["code"] == "CREDENTIAL_REVOKED"


def test_revoked_daemon_cannot_mint_an_access_token(harness: _Harness) -> None:
    """Pins "a revoked daemon cannot mint", NOT a single fence.

    Measured, not assumed: `issue_access_token` guards the mint twice -- once on
    the initial row read and again on a re-read inside the transaction (TOCTOU
    cover). Removing EITHER alone leaves this test green; removing BOTH turns it
    RED. That redundancy is deliberate defense-in-depth, so the honest claim is
    behavioural coverage, not fence isolation.

    Stated explicitly because the first version of this docstring claimed to
    isolate the `issue_access_token` fence, and mutation testing disproved it.
    A probe whose comment overstates what it detects is how the vacuity above
    survived in the first place.
    """
    challenge = harness.service.create_challenge(
        harness.daemon_id,
        **harness.signer.challenge_creation_proof(
            harness.daemon_id, timestamp=int(harness.service._clock())
        ),
    )
    harness.service.revoke_daemon(OWNER, harness.daemon_id)

    with pytest.raises(DaemonApiError) as rejection:
        harness.service.issue_access_token(
            harness.daemon_id,
            challenge.challenge,
            harness.signer.sign_challenge(harness.daemon_id, challenge.challenge),
        )

    assert rejection.value.as_dict()["error"]["code"] == "CREDENTIAL_REVOKED"


def test_resolve_device_key_reports_a_revoked_daemon_as_inactive(
    harness: _Harness,
) -> None:
    """Isolates the `resolve_device_key` active flag.

    This sink does not raise -- it reports. Callers gate on `active`, so a
    revoked daemon surfacing as active is a silent authorization grant rather
    than a visible failure, which is exactly the class that hides from tests
    asserting only on exceptions.
    """
    thumbprint = harness.completed.key_thumbprint
    resolved = harness.service.resolve_device_key(thumbprint)
    assert resolved is not None and resolved.active is True

    harness.service.revoke_daemon(OWNER, harness.daemon_id)

    revoked = harness.service.resolve_device_key(thumbprint)
    assert revoked is not None, "revocation must not make the key unresolvable"
    assert revoked.active is False
