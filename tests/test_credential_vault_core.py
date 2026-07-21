"""Core unit tests for the provider-generic credential vault.

Covers both custody backends: round-trip put/get/delete, CAS conflict,
wrong-scope fail-closed, backend-absent, KEK rotation, attestation pass/fail,
and the non-observable secret containers. Concurrency and redaction proofs live
in their own modules.
"""

from __future__ import annotations

import copy
import pickle
import sys
import time

import nacl.bindings as sodium
import pytest

import tinyassets.credentials as cv
from tinyassets.credentials import (
    CredentialUnavailable,
    Custody,
    DpapiVaultBackend,
    InMemoryKeyProvider,
    PlatformVaultBackend,
    SecretBinding,
    SecretBytes,
    SecretDescriptor,
    SecretKind,
    SecretScope,
    VaultErrorCode,
    VaultStore,
    is_secret_ref,
    new_secret_ref,
)

WINDOWS_ONLY = pytest.mark.skipif(
    sys.platform != "win32", reason="DPAPI local backend is Windows-only"
)

SCOPE = SecretScope(
    founder_id="founder:abc",
    universe_id="u-123",
    provider="github",
    destination="octo/repo",
    purpose="external_write",
)


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


def _key_provider(*key_ids: str, active: str | None = None) -> InMemoryKeyProvider:
    ids = key_ids or ("k1",)
    keys = {kid: sodium.randombytes(32) for kid in ids}
    return InMemoryKeyProvider(keys, active or ids[0])


@pytest.fixture(autouse=True)
def _isolate_rollback_guard(tmp_path, monkeypatch):
    """Per-test anti-rollback guard OUTSIDE the vault data dir — see the hardening
    suite for the full rationale (home-dir default guard would leak epochs across
    tests as false rollbacks)."""
    monkeypatch.setenv("TINYASSETS_VAULT_ROLLBACK_GUARD", str(tmp_path / "_vault_guard"))


@pytest.fixture()
def platform(tmp_path) -> PlatformVaultBackend:
    return PlatformVaultBackend(
        _key_provider("k1", "k2"),
        store_id="platform:default",
        db_path=tmp_path / "vault.db",
    )


@pytest.fixture()
def platform_store() -> VaultStore:
    return VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:default")


@pytest.fixture()
def dpapi(tmp_path) -> DpapiVaultBackend:
    return DpapiVaultBackend(
        daemon_id="daemon-1", store_id="daemon:default", base=tmp_path / "local"
    )


@pytest.fixture()
def dpapi_store() -> VaultStore:
    return VaultStore(
        custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="daemon-1"
    )


# ---------------------------------------------------------------------------
# SecretRef opacity
# ---------------------------------------------------------------------------


def test_secret_ref_is_opaque_and_unique():
    a, b = new_secret_ref(), new_secret_ref()
    assert a != b
    assert a.startswith("secret:v1:")
    assert is_secret_ref(a)
    # carries no scope / provider / path
    for token in ("github", "octo", "repo", "founder", "external_write"):
        assert token not in a
    assert not is_secret_ref("secret:v1:not-hex")
    assert not is_secret_ref("random")


# ---------------------------------------------------------------------------
# SecretBytes / SecretLease non-observability
# ---------------------------------------------------------------------------


def test_secret_bytes_cannot_disclose_by_accident():
    sb = SecretBytes(b"topsecret-value")
    assert "topsecret-value" not in repr(sb)
    assert "topsecret-value" not in str(sb)
    assert "topsecret-value" not in f"{sb}"
    assert "topsecret-value" not in format(sb)
    with pytest.raises(TypeError):
        pickle.dumps(sb)
    with pytest.raises(TypeError):
        copy.copy(sb)
    with pytest.raises(TypeError):
        copy.deepcopy(sb)
    with pytest.raises(TypeError):
        list(sb)  # not iterable
    with pytest.raises(TypeError):
        hash(sb)  # unhashable → cannot become a dict key
    # explicit disclosure is the only way
    assert sb.reveal() == b"topsecret-value"


def test_secret_bytes_zeroes_buffer():
    sb = SecretBytes(b"abc")
    assert sb.reveal() == b"abc"
    sb.zero()
    assert sb.reveal() == b"\x00\x00\x00"


def test_secret_bytes_context_manager_zeroes_on_exit():
    with SecretBytes(b"xyz") as sb:
        assert sb.reveal() == b"xyz"
    assert sb.reveal() == b"\x00\x00\x00"


def test_secret_lease_non_serializable(platform, platform_store):
    d = platform.put(platform_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"ghp_x"))
    lease = platform.get(d.binding, SCOPE)
    assert "ghp_x" not in repr(lease)
    with pytest.raises(TypeError):
        pickle.dumps(lease)
    lease.zero()


# ---------------------------------------------------------------------------
# Platform backend
# ---------------------------------------------------------------------------


def test_platform_round_trip(platform, platform_store):
    secret = b"ghp_platform_round_trip"
    d = platform.put(platform_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(secret))
    assert isinstance(d, SecretDescriptor)
    assert d.version == 1
    with platform.get(d.binding, SCOPE) as lease:
        assert lease.reveal() == secret
        assert lease.ref == d.binding.ref
    platform.delete(d.binding, SCOPE)
    with pytest.raises(CredentialUnavailable) as exc:
        platform.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.NOT_FOUND


def test_platform_cas_replace_and_conflict(platform, platform_store):
    d1 = platform.put(platform_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"v1"))
    d2 = platform.put(
        platform_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"v2"),
        replace=d1.binding.ref, expected_version=1,
    )
    assert d2.version == 2
    with platform.get(d2.binding, SCOPE) as lease:
        assert lease.reveal() == b"v2"
    # stale expected_version → CAS conflict
    with pytest.raises(CredentialUnavailable) as exc:
        platform.put(
            platform_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"v3"),
            replace=d1.binding.ref, expected_version=1,
        )
    assert exc.value.code == VaultErrorCode.VERSION_CONFLICT


def test_platform_replace_missing_ref_not_found(platform, platform_store):
    with pytest.raises(CredentialUnavailable) as exc:
        platform.put(
            platform_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"v"),
            replace=new_secret_ref(), expected_version=1,
        )
    assert exc.value.code == VaultErrorCode.NOT_FOUND


def test_platform_wrong_scope_get_fails_closed(platform, platform_store):
    d = platform.put(platform_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"s"))
    wrong = SecretScope(
        founder_id=SCOPE.founder_id, universe_id=SCOPE.universe_id,
        provider=SCOPE.provider, destination="attacker/repo", purpose=SCOPE.purpose,
    )
    # guard-level mismatch (binding.scope != expected)
    with pytest.raises(CredentialUnavailable) as exc:
        platform.get(d.binding, wrong)
    assert exc.value.code == VaultErrorCode.SCOPE_MISMATCH
    # crypto-level: a binding carrying the wrong scope decrypts to nothing
    forged = SecretBinding(
        ref=d.binding.ref, kind=SecretKind.GITHUB_PAT, scope=wrong, store=platform_store
    )
    with pytest.raises(CredentialUnavailable) as exc2:
        platform.get(forged, wrong)
    assert exc2.value.code in {VaultErrorCode.CORRUPT_RECORD, VaultErrorCode.SCOPE_MISMATCH}


def test_platform_cross_store_forbidden(platform):
    other = VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:other")
    with pytest.raises(CredentialUnavailable) as exc:
        platform.put(other, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"s"))
    assert exc.value.code == VaultErrorCode.CROSS_STORE_FORBIDDEN
    daemon_store = VaultStore(
        custody=Custody.DAEMON_LOCAL, store_id="platform:default", daemon_id="d"
    )
    with pytest.raises(CredentialUnavailable) as exc2:
        platform.put(daemon_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"s"))
    assert exc2.value.code == VaultErrorCode.CROSS_STORE_FORBIDDEN


def test_platform_expired_and_disabled_states(platform, platform_store):
    d = platform.put(
        platform_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"s"),
        expires_at=time.time() - 1,
    )
    with pytest.raises(CredentialUnavailable) as exc:
        platform.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.EXPIRED


def test_platform_kek_rotation_preserves_readability(platform, platform_store):
    d = platform.put(platform_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"rotate"))
    platform._keys._active = "k2"  # operator marks the new KEK active
    rewrapped = platform.rotate_kek("k2")
    assert rewrapped == 1
    with platform.get(d.binding, SCOPE) as lease:
        assert lease.reveal() == b"rotate"
    # new puts use the new active key
    d2 = platform.put(platform_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"new"))
    ev = platform.inspect_persisted(d2.binding.ref, b"new")
    assert ev["key_id"] == "k2"


def test_platform_ciphertext_has_no_plaintext(platform, platform_store):
    secret = b"CANARY_PLAINTEXT_ABC123"
    d = platform.put(platform_store, SCOPE, SecretKind.API_KEY, SecretBytes(secret))
    ev = platform.inspect_persisted(d.binding.ref, secret)
    assert ev["algorithm_ok"] is True
    assert ev["has_ciphertext"] is True
    assert ev["has_wrapped_dek"] is True
    assert ev["plaintext_absent"] is True


def test_platform_attestation_passes(platform):
    result = platform.attest()
    assert result.ok is True
    assert result.checks["exact_read"] is True
    assert result.checks["wrong_scope_fails"] is True
    assert result.checks["not_found_after_delete"] is True


def test_platform_attestation_fails_when_backend_broken(tmp_path):
    class BrokenKeyProvider:
        def active_key_id(self):
            return "k1"

        def get_key(self, key_id):
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE)

    be = PlatformVaultBackend(
        BrokenKeyProvider(), store_id="platform:default", db_path=tmp_path / "v.db"
    )
    result = be.attest()
    assert result.ok is False
    # a broken store fails closed on the gated surface
    with pytest.raises(CredentialUnavailable) as exc:
        be.put(
            VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:default"),
            SCOPE, SecretKind.API_KEY, SecretBytes(b"x"),
        )
    assert exc.value.code == VaultErrorCode.BACKEND_UNAVAILABLE


def test_refresh_lease_serializes(platform, platform_store):
    d = platform.put(platform_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"s"))
    ref = d.binding.ref
    with platform.refresh_lease(ref, "worker-a", ttl=5.0):
        # a second holder cannot acquire while A holds it
        with pytest.raises(CredentialUnavailable) as exc:
            with platform.refresh_lease(ref, "worker-b", wait=0.2, poll=0.02):
                pass
        assert exc.value.code == VaultErrorCode.LEASE_TIMEOUT
    # once released, another holder can acquire
    with platform.refresh_lease(ref, "worker-b", wait=1.0):
        pass


# ---------------------------------------------------------------------------
# error hygiene
# ---------------------------------------------------------------------------


def test_error_never_contains_secret_value(platform, platform_store):
    secret = b"SUPER_SECRET_TOKEN_XYZ"
    d = platform.put(platform_store, SCOPE, SecretKind.API_KEY, SecretBytes(secret))
    platform.delete(d.binding, SCOPE)
    try:
        platform.get(d.binding, SCOPE)
    except CredentialUnavailable as exc:
        assert "SUPER_SECRET_TOKEN_XYZ" not in str(exc)
        assert exc.code == VaultErrorCode.NOT_FOUND
        assert exc.ref == d.binding.ref  # opaque ref is safe to surface


def test_unknown_error_code_rejected():
    with pytest.raises(ValueError):
        CredentialUnavailable("NOT_A_REAL_CODE")


# ---------------------------------------------------------------------------
# DPAPI local backend (Windows)
# ---------------------------------------------------------------------------


@WINDOWS_ONLY
def test_dpapi_round_trip(dpapi, dpapi_store):
    secret = b"ghp_dpapi_round_trip"
    d = dpapi.put(dpapi_store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(secret))
    with dpapi.get(d.binding, SCOPE) as lease:
        assert lease.reveal() == secret
    dpapi.delete(d.binding, SCOPE)
    with pytest.raises(CredentialUnavailable) as exc:
        dpapi.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.NOT_FOUND


@WINDOWS_ONLY
def test_dpapi_cas_and_conflict(dpapi, dpapi_store):
    d1 = dpapi.put(dpapi_store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v1"))
    d2 = dpapi.put(
        dpapi_store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v2"),
        replace=d1.binding.ref, expected_version=1,
    )
    assert d2.version == 2
    with pytest.raises(CredentialUnavailable) as exc:
        dpapi.put(
            dpapi_store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v3"),
            replace=d1.binding.ref, expected_version=1,
        )
    assert exc.value.code == VaultErrorCode.VERSION_CONFLICT


@WINDOWS_ONLY
def test_dpapi_wrong_scope_fails_closed(dpapi, dpapi_store):
    d = dpapi.put(dpapi_store, SCOPE, SecretKind.API_KEY, SecretBytes(b"s"))
    wrong = SecretScope(
        founder_id=SCOPE.founder_id, universe_id=SCOPE.universe_id,
        provider=SCOPE.provider, destination="attacker/repo", purpose=SCOPE.purpose,
    )
    forged = SecretBinding(
        ref=d.binding.ref, kind=SecretKind.API_KEY, scope=wrong, store=dpapi_store
    )
    with pytest.raises(CredentialUnavailable):
        dpapi.get(forged, wrong)


@WINDOWS_ONLY
def test_dpapi_attestation_passes(dpapi):
    result = dpapi.attest()
    assert result.ok is True
    assert result.checks["current_user_bound"] is True
    assert result.checks["plaintext_absent"] is True


@WINDOWS_ONLY
def test_dpapi_blob_file_has_no_plaintext(dpapi, dpapi_store):
    secret = b"CANARY_DPAPI_PLAINTEXT_9Z"
    d = dpapi.put(dpapi_store, SCOPE, SecretKind.API_KEY, SecretBytes(secret))
    ev = dpapi.inspect_persisted(d.binding.ref, secret)
    assert ev["plaintext_absent"] is True
    assert ev["protection_current_user"] is True


def test_dpapi_backend_absent_fails_loud(dpapi, dpapi_store, monkeypatch):
    # Simulate a non-Windows host: the backend must fail loud, never fall back.
    monkeypatch.setattr(
        "tinyassets.credentials.local_backend.IS_WINDOWS", False, raising=True
    )
    with pytest.raises(CredentialUnavailable) as exc:
        dpapi.put(dpapi_store, SCOPE, SecretKind.API_KEY, SecretBytes(b"s"))
    assert exc.value.code == VaultErrorCode.BACKEND_UNAVAILABLE


# ---------------------------------------------------------------------------
# BYO execution gate
# ---------------------------------------------------------------------------


def test_byo_execution_enabled_requires_all_conditions(platform, platform_store, monkeypatch):
    d = platform.put(platform_store, SCOPE, SecretKind.API_KEY, SecretBytes(b"s"))
    # no opt-in → False
    monkeypatch.delenv("TINYASSETS_BYO_VAULT_ENCRYPTED", raising=False)
    assert cv.byo_execution_enabled(platform, d.binding) is False
    # opt-in but failing auth-health → False
    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    assert cv.byo_execution_enabled(platform, d.binding, auth_health=False) is False
    # all conditions pass → True
    assert cv.byo_execution_enabled(platform, d.binding, auth_health=True) is True
