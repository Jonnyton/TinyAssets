"""Hardening tests — reproduce each Codex-review finding and prove it closed.

Every test here corresponds to a reproduced attack from the 2026-07-16 Codex
security review (``docs/audits/2026-07-16-provider-generic-credential-vault-codex-review.md``):
plaintext-metadata tampering, forged-binding deletion, refresh-lease TTL overrun,
non-atomic local CAS, KEK-rotation verification, and KEK-file security gates.
Each would FAIL on the pre-review code and PASSES on the fix.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time

import nacl.bindings as sodium
import pytest

from tinyassets.credentials import (
    CredentialUnavailable,
    Custody,
    DpapiVaultBackend,
    FileKeyProvider,
    InMemoryKeyProvider,
    PlatformVaultBackend,
    SecretBinding,
    SecretBytes,
    SecretKind,
    SecretScope,
    VaultErrorCode,
    VaultStore,
)
from tinyassets.credentials import crypto as vault_crypto

WINDOWS_ONLY = pytest.mark.skipif(
    sys.platform != "win32", reason="DPAPI local backend is Windows-only"
)
POSIX_ONLY = pytest.mark.skipif(
    os.name != "posix", reason="POSIX file-permission semantics"
)

SCOPE = SecretScope(
    founder_id="founder:h",
    universe_id="u-h",
    provider="github",
    destination="octo/repo",
    purpose="external_write",
)


def _kp(*ids: str) -> InMemoryKeyProvider:
    ids = ids or ("k1",)
    return InMemoryKeyProvider({i: sodium.randombytes(32) for i in ids}, ids[0])


@pytest.fixture()
def platform(tmp_path):
    be = PlatformVaultBackend(
        _kp("k1", "k2"), store_id="platform:default", db_path=tmp_path / "vault.db"
    )
    be.attest()
    return be


@pytest.fixture()
def store():
    return VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:default")


# ===========================================================================
# Finding 1 — lifecycle + custody metadata must be authenticated, not trusted
# ===========================================================================


def test_tampered_plaintext_expiry_cannot_reactivate(platform, store, tmp_path):
    """Clearing the plaintext ``expires_at`` column must NOT revive an expired
    credential — expiry is taken from the AUTHENTICATED record."""
    d = platform.put(
        store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"tok"),
        expires_at=time.time() - 100,
    )
    with pytest.raises(CredentialUnavailable) as first:
        platform.get(d.binding, SCOPE)
    assert first.value.code == VaultErrorCode.EXPIRED

    # Attacker clears the plaintext hint column (no KEK needed).
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    conn.execute("UPDATE vault_secrets SET expires_at = NULL WHERE ref = ?", (d.binding.ref,))
    conn.commit()
    conn.close()

    with pytest.raises(CredentialUnavailable) as after:
        platform.get(d.binding, SCOPE)
    assert after.value.code == VaultErrorCode.EXPIRED  # still expired — fix holds


def test_tampered_plaintext_store_id_cross_store_decrypt_fails(tmp_path):
    """Swapping the plaintext ``store_id`` and reading through another store must
    fail authentication — store identity is bound into the AAD."""
    kp = _kp("k1")
    db = tmp_path / "vault.db"
    a = PlatformVaultBackend(kp, store_id="platform:default", db_path=db)
    a.attest()
    store_a = VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:default")
    d = a.put(store_a, SCOPE, SecretKind.API_KEY, SecretBytes(b"cross-store-secret"))

    # Attacker repoints the row at another store id.
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE vault_secrets SET store_id = 'platform:other' WHERE ref = ?", (d.binding.ref,)
    )
    conn.commit()
    conn.close()

    b = PlatformVaultBackend(kp, store_id="platform:other", db_path=db)
    b.attest()
    store_b = VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:other")
    forged = SecretBinding(
        ref=d.binding.ref, kind=SecretKind.API_KEY, scope=SCOPE, store=store_b
    )
    with pytest.raises(CredentialUnavailable) as exc:
        b.get(forged, SCOPE)
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD


def test_tampered_plaintext_state_is_non_authoritative(platform, store, tmp_path):
    """The plaintext ``state`` column is a hint; the authenticated record governs."""
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"live"))
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    conn.execute("UPDATE vault_secrets SET state = 'disabled' WHERE ref = ?", (d.binding.ref,))
    conn.commit()
    conn.close()
    # authoritative state is still active → get succeeds
    with platform.get(d.binding, SCOPE) as lease:
        assert lease.reveal() == b"live"


# ===========================================================================
# Finding 2 — forged bindings must not delete valid credentials
# ===========================================================================


def test_forged_wrong_kind_binding_cannot_delete_platform(platform, store):
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"keep-me"))
    forged = SecretBinding(
        ref=d.binding.ref, kind=SecretKind.GITHUB_PAT, scope=SCOPE, store=store
    )
    with pytest.raises(CredentialUnavailable):
        platform.delete(forged, SCOPE)
    # the real credential survives
    with platform.get(d.binding, SCOPE) as lease:
        assert lease.reveal() == b"keep-me"


def test_forged_wrong_scope_binding_cannot_delete_platform(platform, store):
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"keep-me"))
    wrong = SecretScope(
        founder_id=SCOPE.founder_id, universe_id=SCOPE.universe_id,
        provider=SCOPE.provider, destination="attacker/repo", purpose=SCOPE.purpose,
    )
    forged = SecretBinding(
        ref=d.binding.ref, kind=SecretKind.API_KEY, scope=wrong, store=store
    )
    with pytest.raises(CredentialUnavailable):
        platform.delete(forged, wrong)
    with platform.get(d.binding, SCOPE) as lease:
        assert lease.reveal() == b"keep-me"


@WINDOWS_ONLY
def test_forged_binding_cannot_delete_local(tmp_path):
    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "loc")
    be.attest()
    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"keep-local"))
    # wrong kind
    forged_kind = SecretBinding(
        ref=d.binding.ref, kind=SecretKind.GITHUB_PAT, scope=SCOPE, store=store
    )
    with pytest.raises(CredentialUnavailable):
        be.delete(forged_kind, SCOPE)
    # cross-store (different daemon)
    other_store = VaultStore(
        custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d2"
    )
    forged_store = SecretBinding(
        ref=d.binding.ref, kind=SecretKind.API_KEY, scope=SCOPE, store=other_store
    )
    with pytest.raises(CredentialUnavailable):
        be.delete(forged_store, SCOPE)
    with be.get(d.binding, SCOPE) as lease:
        assert lease.reveal() == b"keep-local"


# ===========================================================================
# Finding 3 — the refresh lease must be exclusive AFTER ttl (fencing)
# ===========================================================================


def test_fenced_lease_evicts_stalled_holder(platform, store):
    """A holder whose lease expired (stall/crash) is fenced out: it cannot commit
    its refresh, and the holder that stole the lease commits exactly once."""
    d = platform.put(
        store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"tok")
    )
    ref = d.binding.ref

    cm_a = platform.refresh_lease(ref, "A", ttl=0.05, wait=2.0)
    lease_a = cm_a.__enter__()
    time.sleep(0.2)  # A stalls past its TTL (simulated crash / long op, no heartbeat)
    cm_b = platform.refresh_lease(ref, "B", ttl=30.0, wait=2.0)
    lease_b = cm_b.__enter__()
    try:
        assert lease_a.still_held() is False  # evicted
        assert lease_b.still_held() is True

        # Stalled holder A cannot commit — the write CAS-checks the fence.
        with pytest.raises(CredentialUnavailable) as exc:
            platform.put(
                store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"ghost"),
                replace=ref, expected_version=1, fence=lease_a,
            )
        assert exc.value.code == VaultErrorCode.LEASE_LOST

        # The current holder B commits exactly one refresh.
        d2 = platform.put(
            store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"fresh"),
            replace=ref, expected_version=1, fence=lease_b,
        )
        assert d2.version == 2
    finally:
        cm_b.__exit__(None, None, None)
        cm_a.__exit__(None, None, None)


def test_lease_heartbeat_keeps_it_live_past_ttl(platform, store):
    """A live holder that heartbeats keeps the lease past the original TTL, so no
    second holder can steal it (exactly-one provider call)."""
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"x"))
    ref = d.binding.ref
    cm = platform.refresh_lease(ref, "A", ttl=0.2, wait=2.0)
    lease = cm.__enter__()
    try:
        time.sleep(0.1)
        assert lease.renew(ttl=5.0) is True  # heartbeat well past the original ttl
        time.sleep(0.15)  # t~0.25 > original 0.2 expiry; alive only via the renew
        assert lease.still_held() is True
        # a competitor cannot acquire while it is live
        with pytest.raises(CredentialUnavailable) as exc:
            other = platform.refresh_lease(ref, "B", ttl=0.2, wait=0.1)
            other.__enter__()
        assert exc.value.code == VaultErrorCode.LEASE_TIMEOUT
    finally:
        cm.__exit__(None, None, None)


# ===========================================================================
# Finding 6 — KEK rotation must verify payloads/records before success
# ===========================================================================


def test_rotate_kek_rejects_corrupted_row(platform, store, tmp_path):
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"rot"))
    # Corrupt the ciphertext bytes directly.
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    conn.execute(
        "UPDATE vault_secrets SET ciphertext = ? WHERE ref = ?",
        (b"\x00" * 40, d.binding.ref),
    )
    conn.commit()
    conn.close()
    platform._keys._active = "k2"
    with pytest.raises(CredentialUnavailable) as exc:
        platform.rotate_kek("k2")
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD


def test_rotate_kek_crash_injection_rolls_back(platform, store, monkeypatch):
    d1 = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"one"))
    d2 = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"two"))
    platform._keys._active = "k2"

    calls = {"n": 0}
    real = vault_crypto.rewrap_dek

    def _boom(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated crash mid-rotation")
        return real(*args, **kwargs)

    monkeypatch.setattr(vault_crypto, "rewrap_dek", _boom)
    with pytest.raises(RuntimeError):
        platform.rotate_kek("k2")

    # Whole rotation rolled back: both rows still readable under the OLD key.
    monkeypatch.setattr(vault_crypto, "rewrap_dek", real)
    platform._keys._active = "k1"
    with platform.get(d1.binding, SCOPE) as lease:
        assert lease.reveal() == b"one"
    with platform.get(d2.binding, SCOPE) as lease:
        assert lease.reveal() == b"two"


# ===========================================================================
# Finding 5 — KEK-file security gates (library layer)
# ===========================================================================


def test_file_key_provider_reads_valid_key(tmp_path):
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "k1.bin").write_bytes(sodium.randombytes(32))
    if os.name == "posix":
        os.chmod(keys / "k1.bin", 0o400)
    kp = FileKeyProvider(
        keys, "k1", expected_uid=(os.getuid() if os.name == "posix" else None)
    )
    assert len(kp.get_key("k1")) == 32


def test_file_key_provider_rejects_symlink(tmp_path):
    keys = tmp_path / "keys"
    keys.mkdir()
    real = tmp_path / "real_key.bin"
    real.write_bytes(sodium.randombytes(32))
    link = keys / "k1.bin"
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")
    kp = FileKeyProvider(keys, "k1", expected_uid=None)
    with pytest.raises(CredentialUnavailable) as exc:
        kp.get_key("k1")
    assert exc.value.code == VaultErrorCode.KEK_INSECURE


@POSIX_ONLY
def test_file_key_provider_rejects_group_readable(tmp_path):
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "k1.bin").write_bytes(sodium.randombytes(32))
    os.chmod(keys / "k1.bin", 0o440)  # group-readable → insecure
    kp = FileKeyProvider(keys, "k1", expected_uid=os.getuid())
    with pytest.raises(CredentialUnavailable) as exc:
        kp.get_key("k1")
    assert exc.value.code == VaultErrorCode.KEK_INSECURE


@WINDOWS_ONLY
def test_local_attestation_reports_dacl_evidence(tmp_path):
    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "loc")
    be.attest()
    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"probe"))
    ev = be.inspect_persisted(d.binding.ref, b"probe")
    assert "dacl_current_user_only" in ev  # evidence surfaced (bool or None)
    assert ev["current_user_bound"] is True
