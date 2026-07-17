"""Hardening tests — reproduce each Codex-review finding and prove it closed.

Every test here corresponds to a reproduced attack from the 2026-07-16 Codex
security review (``docs/audits/2026-07-16-provider-generic-credential-vault-codex-review.md``):
plaintext-metadata tampering, forged-binding deletion, refresh-lease TTL overrun,
non-atomic local CAS, KEK-rotation verification, and KEK-file security gates.
Each would FAIL on the pre-review code and PASSES on the fix.
"""

from __future__ import annotations

import os
import shutil
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
    RefreshTicket,
    SecretBinding,
    SecretBytes,
    SecretKind,
    SecretScope,
    VaultBroker,
    VaultErrorCode,
    VaultStore,
)
from tinyassets.credentials import crypto as vault_crypto
from tinyassets.credentials import record as vault_record

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


@pytest.fixture(autouse=True)
def _isolate_rollback_guard(tmp_path, monkeypatch):
    """Point the anti-rollback guard at a per-test domain OUTSIDE the vault data
    dir. Without this, backends fall back to the home-dir default guard and its
    epoch bumps leak across tests (false rollbacks); an independent per-test guard
    also lets a full-volume-restore test model 'the guard survives a /data restore'.
    """
    monkeypatch.setenv("TINYASSETS_VAULT_ROLLBACK_GUARD", str(tmp_path / "_vault_guard"))


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


def _authorize_run(platform, run_id: str, scope: SecretScope) -> None:
    """Install the broker-side authoritative run lookup used by grant tests."""
    from tinyassets.credentials import JobContext

    platform._run_context_lookup = lambda candidate: (
        JobContext(run_id=run_id, universe_id=scope.universe_id, founder_id=scope.founder_id)
        if candidate == run_id
        else None
    )


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
    # Non-rotating kind: exercises the fence primitive directly (rotating-token
    # kinds must go through begin/complete_refresh, tested separately).
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"tok"))
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
                store, SCOPE, SecretKind.API_KEY, SecretBytes(b"ghost"),
                replace=ref, expected_version=1, fence=lease_a,
            )
        assert exc.value.code == VaultErrorCode.LEASE_LOST

        # The current holder B commits exactly one refresh.
        d2 = platform.put(
            store, SCOPE, SecretKind.API_KEY, SecretBytes(b"fresh"),
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


# ===========================================================================
# Review r2 finding 1 — atomic consume-before-mint (single-process semantics)
# ===========================================================================


def test_begin_refresh_is_exclusive_and_dos_safe(platform, store):
    """begin_refresh gives exactly one redeemer per version, ties the claim to the
    authenticated current version (no version-99 DoS), and refuses a stale view."""
    d = platform.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"t1"))
    b = d.binding
    t_a = platform.begin_refresh(b, SCOPE, "A", at_version=1)
    assert t_a is not None and t_a.version == 1
    assert platform.begin_refresh(b, SCOPE, "B", at_version=1) is None  # already claimed

    # a claim for a NON-EXISTENT version inserts nothing and cannot block it
    assert platform.begin_refresh(b, SCOPE, "X", at_version=99) is None

    # complete A's refresh: v1 -> v2 (via the sanctioned capability-bound path)
    platform.complete_refresh(b, SCOPE, t_a, SecretBytes(b"t2"))
    # a straggler still holding the old view (v1) is refused — cannot re-redeem
    assert platform.begin_refresh(b, SCOPE, "C", at_version=1) is None
    # the NEW current version is independently redeemable exactly once
    assert platform.begin_refresh(b, SCOPE, "C", at_version=2) is not None
    assert platform.begin_refresh(b, SCOPE, "D", at_version=2) is None


def test_put_requires_cas_pairing(platform, store):
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"x"))
    # replace without expected_version → typed rejection (would permit lost updates)
    with pytest.raises(CredentialUnavailable) as exc:
        platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"y"), replace=d.binding.ref)
    assert exc.value.code == VaultErrorCode.INVALID_ARGUMENT
    # expected_version without replace → typed rejection (inverse pairing)
    with pytest.raises(CredentialUnavailable) as exc2:
        platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"y"), expected_version=1)
    assert exc2.value.code == VaultErrorCode.INVALID_ARGUMENT


def test_platform_store_forbids_daemon_id():
    with pytest.raises(ValueError):
        VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:default", daemon_id="d")


def test_tampered_noninteger_version_hint_is_typed(platform, store, tmp_path):
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"x"))
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    conn.execute("UPDATE vault_secrets SET version = 'not-an-int' WHERE ref = ?", (d.binding.ref,))
    conn.commit()
    conn.close()
    with pytest.raises(CredentialUnavailable) as exc:  # never a raw ValueError
        platform.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD


# ===========================================================================
# Review r2 finding 2 — non-finite (NaN/Inf) numeric metadata bypasses lifecycle
# ===========================================================================


def test_nan_expiry_rejected_at_put(platform, store):
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(CredentialUnavailable) as exc:
            platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"x"), expires_at=bad)
        assert exc.value.code == VaultErrorCode.CORRUPT_RECORD


def test_check_lifecycle_rejects_nan_expiry():
    with pytest.raises(CredentialUnavailable) as exc:
        vault_record.check_lifecycle(
            {"state": "active", "expires_at": float("nan")}, "secret:v1:x"
        )
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD


def test_decode_record_rejects_nan_json():
    import json

    raw = json.dumps({"state": "active", "expires_at": float("nan")}).encode("utf-8")
    with pytest.raises(CredentialUnavailable) as exc:
        vault_crypto.decode_record(raw)
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD


# ===========================================================================
# Review r2 finding 4 — KEK rotation false success
# ===========================================================================


def test_rotate_kek_requires_new_key_to_be_active(platform, store):
    platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"x"))
    # k1 is still the active write key → rotating to k2 must be refused (typed).
    with pytest.raises(CredentialUnavailable) as exc:
        platform.rotate_kek("k2")
    assert exc.value.code == VaultErrorCode.INVALID_ARGUMENT


def test_rotate_kek_leaves_no_row_on_old_key(platform, store):
    d1 = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"a"))
    d2 = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"b"))
    platform._keys._active = "k2"
    platform.rotate_kek("k2")
    for d in (d1, d2):
        ev = platform.inspect_persisted(d.binding.ref, b"")
        assert ev["key_id"] == "k2"
        assert ev["key_id_active"] is True


# ===========================================================================
# Review r2 finding 6 — attestation must fail with typed errors
# ===========================================================================


def test_attestation_rejects_untyped_wrong_scope_failure(tmp_path):
    """If the wrong-scope probe fails with an UNEXPECTED (non-typed) error, that
    is NOT accepted as proof of scope isolation — attestation fails."""

    class WrongScopeRaisesRuntime(PlatformVaultBackend):
        def _probe_get(self, binding, expected):
            if expected.destination == "__wrong_destination__":
                raise RuntimeError("unexpected backend fault")  # wrong failure mode
            return super()._probe_get(binding, expected)

    be = WrongScopeRaisesRuntime(
        _kp("k1"), store_id="platform:default", db_path=tmp_path / "v.db"
    )
    result = be.attest()
    assert result.ok is False
    assert result.checks.get("wrong_scope_fails") is False


def test_attestation_converts_probe_read_fault_to_failed_result(tmp_path):
    """A backend read fault after probe creation must become a failed result, not
    escape as a raw exception."""

    class ReadAlwaysFaults(PlatformVaultBackend):
        def _probe_get(self, binding, expected):
            raise RuntimeError("read fault")

    be = ReadAlwaysFaults(_kp("k1"), store_id="platform:default", db_path=tmp_path / "v.db")
    result = be.attest()  # must NOT raise
    assert result.ok is False
    # and the gated surface fails closed
    with pytest.raises(CredentialUnavailable) as exc:
        be.get(
            SecretBinding(
                ref="secret:v1:" + "0" * 64, kind=SecretKind.API_KEY, scope=SCOPE,
                store=VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:default"),
            ),
            SCOPE,
        )
    assert exc.value.code == VaultErrorCode.BACKEND_UNAVAILABLE


# ===========================================================================
# Review r4 finding 2 — per-record DACL verified at ACCESS (not cached probe)
# ===========================================================================


@WINDOWS_ONLY
def test_broadened_dacl_fails_get_closed(tmp_path):
    """A credential whose DACL is broadened AFTER the boot probe must fail get()
    closed — never return the secret from a world-readable blob."""
    import ntsecuritycon
    import win32security

    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "loc")
    be.attest()
    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"localsecret"))
    with be.get(d.binding, SCOPE) as lease:  # fine while narrow
        assert lease.reveal() == b"localsecret"

    blob = str(be._blob_path(d.binding.ref, d.version))
    everyone = win32security.ConvertStringSidToSid("S-1-1-0")
    sd = win32security.GetFileSecurity(blob, win32security.DACL_SECURITY_INFORMATION)
    dacl = sd.GetSecurityDescriptorDacl()
    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_GENERIC_READ, everyone)
    win32security.SetNamedSecurityInfo(
        blob, win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, dacl, None,
    )
    with pytest.raises(CredentialUnavailable) as exc:
        be.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.BACKEND_UNAVAILABLE


# ===========================================================================
# Review r4 finding 3 — refresh is a first-class broker op, completion bound
# ===========================================================================


def test_broker_protocol_includes_refresh(platform):
    assert isinstance(platform, VaultBroker)  # begin/complete present + typed
    assert hasattr(VaultBroker, "begin_refresh")
    assert hasattr(VaultBroker, "complete_refresh")


# ===========================================================================
# Review r9 finding 1 — rollback (full-snapshot restore) forces reauthorization
# ===========================================================================


def test_full_db_rollback_forces_reauthorization(platform, store, tmp_path):
    """Restoring the WHOLE pre-refresh DB rolls back the consumed claim — the
    external epoch mirror (outside the snapshot) detects it and forces reauth."""
    d = platform.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"tok"))
    db = tmp_path / "vault.db"
    snap = tmp_path / "vault.db.snap"
    shutil.copy(db, snap)  # snapshot pre-refresh
    tk = platform.begin_refresh(d.binding, SCOPE, "A", at_version=1)
    platform.complete_refresh(d.binding, SCOPE, tk, SecretBytes(b"tok2"))
    shutil.copy(snap, db)  # restore the WHOLE pre-refresh DB (rollback)

    fresh = PlatformVaultBackend(platform._keys, store_id="platform:default", db_path=db)
    with pytest.raises(CredentialUnavailable) as exc:
        fresh.begin_refresh(d.binding, SCOPE, "B", at_version=1)  # would reopen v1
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED
    with pytest.raises(CredentialUnavailable) as exc2:
        fresh.get(d.binding, SCOPE)
    assert exc2.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


def test_full_db_rollback_after_delete_refuses_restored_value(platform, store, tmp_path):
    d = platform.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"val"))
    db = tmp_path / "vault.db"
    snap = tmp_path / "vault.db.snap"
    shutil.copy(db, snap)  # snapshot pre-delete
    platform.delete(d.binding, SCOPE)
    shutil.copy(snap, db)  # restore the pre-delete DB (deleted value reappears)
    fresh = PlatformVaultBackend(platform._keys, store_id="platform:default", db_path=db)
    with pytest.raises(CredentialUnavailable) as exc:
        fresh.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


@WINDOWS_ONLY
def test_full_local_directory_rollback_forces_reauth(tmp_path):
    base = tmp_path / "loc"
    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=base)
    be.attest()
    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"tok"))
    store_dir = be._dir
    snap = tmp_path / "v1-snap"
    shutil.copytree(store_dir, snap)  # snapshot the WHOLE store directory
    tk = be.begin_refresh(d.binding, SCOPE, "A", at_version=1)
    be.complete_refresh(d.binding, SCOPE, tk, SecretBytes(b"tok2"))
    shutil.rmtree(store_dir)
    shutil.copytree(snap, store_dir)  # restore the whole dir; mirror is OUTSIDE it

    fresh = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=base)
    with pytest.raises(CredentialUnavailable) as exc:
        fresh.begin_refresh(d.binding, SCOPE, "B", at_version=1)
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED
    with pytest.raises(CredentialUnavailable) as exc2:
        fresh.get(d.binding, SCOPE)
    assert exc2.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


# ===========================================================================
# S3 cross-slice — opaque job-scoped grant, fail-closed
# ===========================================================================


def test_job_grant_resolves_and_fails_closed(platform, store):
    import inspect

    from tinyassets.credentials import JobContext, JobGrant

    universe_scope = SecretScope(
        founder_id="founder1", universe_id="universe-A", provider="github",
        destination="octo/repo", purpose="external_write",
    )
    d = platform.put(store, universe_scope, SecretKind.GITHUB_PAT, SecretBytes(b"ghp_worker"))
    _authorize_run(platform, "run-1", universe_scope)
    grant = platform.mint_job_grant(d.binding, universe_scope, run_id="run-1", ttl=3600)

    signature = inspect.signature(PlatformVaultBackend.resolve_job_grant)
    assert list(signature.parameters) == ["self", "grant", "verify_context"]
    assert signature.parameters["verify_context"].default is None
    assert signature.parameters["verify_context"].kind is inspect.Parameter.KEYWORD_ONLY

    # Opaque + non-observable: the grant exposes NO run_id/universe_id (nothing to
    # replay) and the capability cannot be extracted.
    assert not hasattr(grant, "run_id")
    assert not hasattr(grant, "universe_id")
    with pytest.raises(TypeError):
        import dataclasses
        dataclasses.asdict(grant)

    # The live executor check is mandatory-in-effect while the callable signature
    # remains stable: omitting it fails closed.
    with pytest.raises(CredentialUnavailable) as exc_missing_verifier:
        platform.resolve_job_grant(grant)
    assert exc_missing_verifier.value.code == VaultErrorCode.CROSS_STORE_FORBIDDEN

    # The broker hands the AUTHORITATIVE context (from the stored row, not caller
    # input) to verify_context so S3 can bind to the live executor identity.
    seen: dict[str, object] = {}

    def _capture(ctx: JobContext) -> bool:
        seen.update(run_id=ctx.run_id, universe_id=ctx.universe_id, founder_id=ctx.founder_id)
        return True

    with platform.resolve_job_grant(grant, verify_context=_capture) as lease:
        assert lease.reveal() == b"ghp_worker"
    assert seen == {"run_id": "run-1", "universe_id": "universe-A", "founder_id": "founder1"}

    # A rejecting executor-identity check fails CLOSED (typed).
    with pytest.raises(CredentialUnavailable) as exc:
        platform.resolve_job_grant(grant, verify_context=lambda _ctx: False)
    assert exc.value.code == VaultErrorCode.CROSS_STORE_FORBIDDEN

    # A RAISING verify_context also fails closed (never leaks the exception).
    def _raise(_ctx):
        raise RuntimeError("executor identity service down")

    with pytest.raises(CredentialUnavailable) as exc_raise:
        platform.resolve_job_grant(grant, verify_context=_raise)
    assert exc_raise.value.code == VaultErrorCode.CROSS_STORE_FORBIDDEN

    # Forged capability → fail closed.
    forged = JobGrant(grant_id=grant.grant_id, secret=b"\x00" * 32)
    with pytest.raises(CredentialUnavailable) as exc3:
        platform.resolve_job_grant(forged, verify_context=lambda _ctx: True)
    assert exc3.value.code == VaultErrorCode.LEASE_LOST


def test_mint_job_grant_requires_authoritative_run_lookup(platform, store):
    """The caller's raw run_id/scope assertion is never mint authority."""
    from tinyassets.credentials import JobContext

    d = platform.put(store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"tok"))
    with pytest.raises(CredentialUnavailable) as missing:
        platform.mint_job_grant(d.binding, SCOPE, run_id="run-1")
    assert missing.value.code == VaultErrorCode.CROSS_STORE_FORBIDDEN

    platform._run_context_lookup = lambda _run_id: JobContext(
        run_id="run-1", universe_id="other-universe", founder_id=SCOPE.founder_id
    )
    with pytest.raises(CredentialUnavailable) as mismatch:
        platform.mint_job_grant(d.binding, SCOPE, run_id="run-1")
    assert mismatch.value.code == VaultErrorCode.CROSS_STORE_FORBIDDEN


def test_job_grant_rejects_malformed_grant_object(platform, store):
    """r10 #4: a non-JobGrant object is a TYPED INVALID_ARGUMENT, never a raw
    AttributeError leaking from ``grant.grant_id``."""
    d = platform.put(store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"tok"))
    _authorize_run(platform, "run-x", SCOPE)
    platform.mint_job_grant(d.binding, SCOPE, run_id="run-x")
    for bad in (None, "grant:v1:deadbeef", object(), 42, {"grant_id": "x"}):
        with pytest.raises(CredentialUnavailable) as exc:
            platform.resolve_job_grant(bad)
        assert exc.value.code == VaultErrorCode.INVALID_ARGUMENT


def test_job_grant_rejects_non_finite_and_unbounded_ttl(platform, store):
    """r10 #4: a grant can never be non-expiring — inf/nan/<=0/over-cap TTLs are
    rejected at mint; a finite, positive, bounded TTL is accepted."""
    from tinyassets.credentials.grants import MAX_JOB_GRANT_TTL

    d = platform.put(store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"tok"))
    _authorize_run(platform, "run-1", SCOPE)
    for bad in (float("inf"), float("nan"), float("-inf"), 0.0, -1.0, MAX_JOB_GRANT_TTL + 1):
        with pytest.raises(CredentialUnavailable) as exc:
            platform.mint_job_grant(d.binding, SCOPE, run_id="run-1", ttl=bad)
        assert exc.value.code == VaultErrorCode.INVALID_ARGUMENT
    grant = platform.mint_job_grant(d.binding, SCOPE, run_id="run-1", ttl=60.0)
    with platform.resolve_job_grant(grant, verify_context=lambda _ctx: True) as lease:
        assert lease.reveal() == b"tok"


def test_job_grant_expired_fails_closed(platform, store, tmp_path):
    """An expired grant resolves to a typed EXPIRED, never a stale credential."""
    d = platform.put(store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"tok"))
    _authorize_run(platform, "run-1", SCOPE)
    grant = platform.mint_job_grant(d.binding, SCOPE, run_id="run-1", ttl=60.0)
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    conn.execute(
        "UPDATE vault_job_grants SET expires_at = 0 WHERE grant_id = ?", (grant.grant_id,)
    )
    conn.commit()
    conn.close()
    with pytest.raises(CredentialUnavailable) as exc:
        platform.resolve_job_grant(grant, verify_context=lambda _ctx: True)
    assert exc.value.code == VaultErrorCode.EXPIRED


@pytest.mark.parametrize(
    ("column", "bad_value"),
    [
        ("capability_hash", "bad"),
        ("ref", "not-a-secret-ref"),
        ("founder_id", ""),
        ("universe_id", ""),
        ("provider", ""),
        ("destination", ""),
        ("purpose", ""),
        ("kind", "not-a-kind"),
        ("run_id", ""),
        ("expires_at", "nan"),
    ],
)
def test_corrupt_grant_rows_are_typed(platform, store, tmp_path, column, bad_value):
    """Every persisted grant field is normalized before capability/context use."""
    d = platform.put(store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(b"tok"))
    _authorize_run(platform, "run-1", SCOPE)
    grant = platform.mint_job_grant(d.binding, SCOPE, run_id="run-1", ttl=60.0)
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    conn.execute(
        f"UPDATE vault_job_grants SET {column} = ? WHERE grant_id = ?",
        (bad_value, grant.grant_id),
    )
    conn.commit()
    conn.close()
    with pytest.raises(CredentialUnavailable) as exc:
        platform.resolve_job_grant(grant, verify_context=lambda _ctx: True)
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD


# ===========================================================================
# Review r9 finding 2 — durable GC removes every old on-disk version
# ===========================================================================


@WINDOWS_ONLY
def test_rotation_and_delete_gc_all_versions(tmp_path):
    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "loc")
    be.attest()
    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v1"))
    be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v2"),
           replace=d.binding.ref, expected_version=1)
    be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v3"),
           replace=d.binding.ref, expected_version=2)
    tail = d.binding.ref.rsplit(":", 1)[-1]
    assert len(list(be._dir.glob(f"{tail}.v*.json"))) == 1  # only the live version
    be.delete(d.binding, SCOPE)
    assert len(list(be._dir.glob(f"{tail}.v*.json"))) == 0  # every version gone


# ===========================================================================
# Review r9 finding 4 — a tampered record is QUARANTINED, not backend corruption
# ===========================================================================


def test_tampered_record_is_quarantined_not_backend_corruption(platform, store, tmp_path):
    d1 = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"one"))
    d2 = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"two"))
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    conn.execute(
        "UPDATE vault_secrets SET ciphertext = ? WHERE ref = ?", (b"\x00" * 40, d1.binding.ref)
    )
    conn.commit()
    conn.close()
    with pytest.raises(CredentialUnavailable) as exc:
        platform.get(d1.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD
    # a single bad record is QUARANTINED — attestation stays valid, other records work
    assert platform._attested is True
    with platform.get(d2.binding, SCOPE) as lease:
        assert lease.reveal() == b"two"


# ===========================================================================
# Review r8 finding 1 — local CAS: SQLite commit is authoritative
# ===========================================================================


@WINDOWS_ONLY
def test_local_commit_failure_preserves_old_value(tmp_path, monkeypatch):
    from tinyassets.credentials import leases as vault_leases

    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "loc")
    be.attest()
    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v1"))
    d2 = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v2"),
                replace=d.binding.ref, expected_version=1)

    def _boom(_conn, _ref, _version):
        raise sqlite3.OperationalError("injected control-DB commit failure")

    monkeypatch.setattr(vault_leases, "set_live_version", _boom)
    with pytest.raises(CredentialUnavailable) as exc:
        be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v3-must-not-persist"),
               replace=d.binding.ref, expected_version=2)
    assert exc.value.code == VaultErrorCode.BACKEND_UNAVAILABLE
    monkeypatch.undo()
    # the control-DB live-version pointer never advanced → OLD value is live
    with be.get(d2.binding, SCOPE) as lease:
        assert lease.reveal() == b"v2"
        assert lease.version == 2


# ===========================================================================
# Review r8 finding 2 — crash mid-refresh → reauthorization_required
# ===========================================================================


def test_wedged_refresh_surfaces_reauthorization(platform, store, tmp_path):
    """A refresh claimed at the current version but never completed (a crash at
    ANY of the three boundaries — before the provider call, after provider
    success before persist, before completion — all converge to this same
    persisted state) surfaces REAUTHORIZATION_REQUIRED once past the wedge
    timeout: never a silent-None wedge, never an unsafe retry."""
    d = platform.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"tok"))
    b = d.binding
    tk = platform.begin_refresh(b, SCOPE, "A", at_version=1)  # claimed, never completed
    assert tk is not None
    # recent claim = in-flight → None (let the holder finish), NOT reauth
    assert platform.begin_refresh(b, SCOPE, "B", at_version=1, wedge_timeout=300) is None
    # backdate the claim → wedged past timeout → reauthorization_required
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    conn.execute("UPDATE vault_refresh_claims SET claimed_at = 0 WHERE ref = ?", (b.ref,))
    conn.commit()
    conn.close()
    with pytest.raises(CredentialUnavailable) as exc:
        platform.begin_refresh(b, SCOPE, "C", at_version=1, wedge_timeout=1.0)
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


def test_completed_refresh_is_not_wedged(platform, store):
    d = platform.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"t1"))
    b = d.binding
    tk = platform.begin_refresh(b, SCOPE, "A", at_version=1)
    platform.complete_refresh(b, SCOPE, tk, SecretBytes(b"t2"))  # advances to v2
    # a normal next refresh at the NEW version is fine — not a wedge
    tk2 = platform.begin_refresh(b, SCOPE, "A", at_version=2, wedge_timeout=1.0)
    assert tk2 is not None


# ===========================================================================
# Review r8 finding 3 — sqlite connect failure normalized (db_path is a dir)
# ===========================================================================


def test_db_path_directory_is_typed(tmp_path):
    d = tmp_path / "not-a-db"
    d.mkdir()
    be = PlatformVaultBackend(_kp("k1"), store_id="platform:default", db_path=d)
    with pytest.raises(CredentialUnavailable) as exc:  # never a raw OperationalError
        be.put(
            VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:default"),
            SCOPE, SecretKind.API_KEY, SecretBytes(b"x"),
        )
    assert exc.value.code == VaultErrorCode.BACKEND_UNAVAILABLE


# ===========================================================================
# Review r8 finding 4 — attestation probes must not leak permanent tombstones
# ===========================================================================


def test_byo_checks_do_not_leak_tombstones(platform, store, tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    from tinyassets.credentials import byo_execution_enabled

    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"x"))
    for _ in range(5):
        assert byo_execution_enabled(platform, d.binding) is True
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    try:
        rows = conn.execute("SELECT COUNT(*) FROM vault_refresh_claims").fetchone()[0]
    finally:
        conn.close()
    assert rows == 0  # cached per-boot probe + non-tombstoning probe delete = no leak


# ===========================================================================
# Review r7 finding 2 — deletion is an irreversible tombstone (restored data refused)
# ===========================================================================


def test_deleted_platform_restored_row_refused(platform, store, tmp_path):
    d = platform.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"tok"))
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    row = conn.execute(
        "SELECT * FROM vault_secrets WHERE ref = ?", (d.binding.ref,)
    ).fetchone()
    cols = [c[1] for c in conn.execute("PRAGMA table_info(vault_secrets)")]
    conn.close()
    platform.delete(d.binding, SCOPE)  # irreversible tombstone
    # restore the deleted row (partial backup restore)
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    placeholders = ",".join(["?"] * len(cols))
    conn.execute(
        f"INSERT INTO vault_secrets ({','.join(cols)}) VALUES ({placeholders})", row
    )
    conn.commit()
    conn.close()
    with pytest.raises(CredentialUnavailable) as exc:
        platform.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.NOT_FOUND  # tombstone refuses the restore


@WINDOWS_ONLY
def test_deleted_local_sidecar_reappears_refused(tmp_path):
    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "loc")
    be.attest()
    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"tok"))
    blob = be._blob_path(d.binding.ref, d.version)
    saved = blob.read_bytes()
    be.delete(d.binding, SCOPE)  # tombstone (control DB) + remove sidecar
    # the sidecar reappears / is restored WITHOUT touching the control-DB tombstone
    blob.write_bytes(saved)
    with pytest.raises(CredentialUnavailable) as exc:
        be.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.NOT_FOUND
    with pytest.raises(CredentialUnavailable) as exc2:
        be.begin_refresh(d.binding, SCOPE, "A", at_version=1)
    assert exc2.value.code == VaultErrorCode.NOT_FOUND


# ===========================================================================
# Review r7 finding 3 — remaining typed-error escapes normalized
# ===========================================================================


def test_blob_column_wrong_storage_type_is_typed(platform, store, tmp_path):
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"x"))
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    conn.execute(
        "UPDATE vault_secrets SET ciphertext = ? WHERE ref = ?",
        ("now-a-text-column", d.binding.ref),
    )
    conn.commit()
    conn.close()
    with pytest.raises(CredentialUnavailable) as exc:  # never a raw TypeError
        platform.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD
    assert platform._attested is None  # structural corruption invalidates the gate


def test_begin_refresh_malformed_at_version_is_typed(platform, store):
    d = platform.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"tok"))
    with pytest.raises(CredentialUnavailable) as exc:  # never a raw ValueError
        platform.begin_refresh(d.binding, SCOPE, "A", at_version="not-an-int")
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD


# ===========================================================================
# Review r6 finding 1 — short writes must not destroy the existing credential
# ===========================================================================


@WINDOWS_ONLY
def test_short_write_no_progress_preserves_old_credential(tmp_path, monkeypatch):
    from tinyassets.credentials import local_backend as lb

    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "loc")
    be.attest()
    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"original"))

    def _no_progress(_fd, _data):
        return 0  # os.write makes no progress → must raise, never truncate

    monkeypatch.setattr(lb.os, "write", _no_progress)
    with pytest.raises(CredentialUnavailable):
        be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"replacement"),
               replace=d.binding.ref, expected_version=1)
    monkeypatch.undo()
    with be.get(d.binding, SCOPE) as lease:
        assert lease.reveal() == b"original"  # OLD credential survived, no CORRUPT


@WINDOWS_ONLY
def test_partial_write_completes_without_truncation(tmp_path, monkeypatch):
    from tinyassets.credentials import local_backend as lb

    real_write = os.write
    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "loc")
    be.attest()
    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v1"))

    def _partial(fd, data):
        half = max(1, len(bytes(data)) // 2)
        return real_write(fd, bytes(data)[:half])  # write at most half per call

    monkeypatch.setattr(lb.os, "write", _partial)
    d2 = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v2-full-new-value"),
                replace=d.binding.ref, expected_version=1)
    monkeypatch.undo()
    with be.get(d2.binding, SCOPE) as lease:
        assert lease.reveal() == b"v2-full-new-value"  # complete, not truncated


# ===========================================================================
# Review r6 finding 3 — corrupt rotation metadata → typed CORRUPT_RECORD
# ===========================================================================


@pytest.mark.parametrize(
    "column,badval",
    [("custody", "forged"), ("kind", "not-a-kind"), ("version", "not-an-int")],
)
def test_rotate_kek_typed_on_corrupt_hint(platform, store, tmp_path, column, badval):
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"x"))
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    conn.execute(
        f"UPDATE vault_secrets SET {column} = ? WHERE ref = ?", (badval, d.binding.ref)
    )
    conn.commit()
    conn.close()
    platform._keys._active = "k2"
    with pytest.raises(CredentialUnavailable) as exc:  # never a raw ValueError
        platform.rotate_kek("k2")
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD
    assert platform._attested is None  # cached gate invalidated


# ===========================================================================
# Review r6 finding 4 — reject empty (and oversized) payloads, preserve prior
# ===========================================================================


def test_empty_and_oversized_payloads_rejected(platform, store):
    # empty on a fresh put → typed INVALID_ARGUMENT
    with pytest.raises(CredentialUnavailable) as exc:
        platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b""))
    assert exc.value.code == VaultErrorCode.INVALID_ARGUMENT
    # oversized on a fresh put
    with pytest.raises(CredentialUnavailable) as exc2:
        platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"x" * (1024 * 1024 + 1)))
    assert exc2.value.code == VaultErrorCode.INVALID_ARGUMENT
    # a rejected CAS preserves the prior value
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"keep"))
    with pytest.raises(CredentialUnavailable):
        platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b""),
                     replace=d.binding.ref, expected_version=1)
    with platform.get(d.binding, SCOPE) as lease:
        assert lease.reveal() == b"keep"


def test_put_replace_refused_for_rotating_kind(platform, store):
    """A rotating one-time-token kind cannot be advanced by a bare CAS — only
    complete_refresh (with a minted capability) may."""
    for kind in (SecretKind.GITHUB_APP_USER_TOKEN, SecretKind.OAUTH2_GENERIC):
        d = platform.put(store, SCOPE, kind, SecretBytes(b"v1"))
        with pytest.raises(CredentialUnavailable) as exc:
            platform.put(
                store, SCOPE, kind, SecretBytes(b"v2"), replace=d.binding.ref, expected_version=1
            )
        assert exc.value.code == VaultErrorCode.LEASE_LOST
    # non-rotating kinds still CAS-replace freely
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"a1"))
    d2 = platform.put(
        store, SCOPE, SecretKind.API_KEY, SecretBytes(b"a2"),
        replace=d.binding.ref, expected_version=1,
    )
    assert d2.version == 2


def test_claim_table_bounded_and_tombstoned_on_delete(platform, store, tmp_path):
    d = platform.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"t1"))
    b = d.binding
    for i in range(3):  # three refresh cycles
        tk = platform.begin_refresh(b, SCOPE, "A", at_version=i + 1)
        platform.complete_refresh(b, SCOPE, tk, SecretBytes(f"t{i + 2}".encode()))
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM vault_refresh_claims WHERE ref = ?", (b.ref,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert n == 1  # high-water: one row per ref, never unbounded
    # delete leaves an IRREVERSIBLE tombstone (deleted=1), never removes the row
    platform.delete(b, SCOPE)
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    try:
        row = conn.execute(
            "SELECT deleted FROM vault_refresh_claims WHERE ref = ?", (b.ref,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None and int(row[0]) == 1  # tombstone retained, consumed forever


def test_attestation_fails_when_wrong_scope_returns_wrong_code(tmp_path):
    """Wrong-scope probe must fail with SCOPE_MISMATCH — a fake backend returning
    NOT_FOUND is NOT accepted as scope-isolation proof."""

    class WrongScopeNotFound(PlatformVaultBackend):
        def _probe_get(self, binding, expected):
            if expected.destination == "__wrong_destination__":
                raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)  # wrong code
            return super()._probe_get(binding, expected)

    be = WrongScopeNotFound(_kp("k1"), store_id="platform:default", db_path=tmp_path / "v.db")
    result = be.attest()
    assert result.ok is False
    assert result.checks.get("wrong_scope_fails") is False


@WINDOWS_ONLY
def test_dacl_failure_on_write_preserves_old_credential(tmp_path, monkeypatch):
    """A failed CAS (DACL can't be applied) must leave the OLD credential intact —
    never destroy the existing blob."""
    from tinyassets.credentials import local_backend as lb

    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "loc")
    be.attest()
    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"original"))

    def _boom(_path):
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE)

    monkeypatch.setattr(lb, "set_restrictive_dacl", _boom)
    with pytest.raises(CredentialUnavailable):
        be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"replacement"),
               replace=d.binding.ref, expected_version=1)
    monkeypatch.undo()
    with be.get(d.binding, SCOPE) as lease:
        assert lease.reveal() == b"original"  # OLD credential survived


@WINDOWS_ONLY
def test_local_sidecar_non_object_is_typed(tmp_path):
    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "loc")
    be.attest()
    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"x"))
    # overwrite with valid JSON that is NOT an object → must not leak AttributeError
    be._blob_path(d.binding.ref, d.version).write_text("[]", encoding="utf-8")
    with pytest.raises(CredentialUnavailable) as exc:
        be.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.CORRUPT_RECORD


def test_complete_refresh_requires_valid_ticket(platform, store):
    d = platform.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"t1"))
    ticket = platform.begin_refresh(d.binding, SCOPE, "A", at_version=1)
    d2 = platform.complete_refresh(d.binding, SCOPE, ticket, SecretBytes(b"t2"))
    assert d2.version == 2
    with platform.get(d2.binding, SCOPE) as lease:
        assert lease.reveal() == b"t2"
    # a forged ticket whose minted capability does not match cannot complete a
    # refresh even with the correct ref/version/holder fields
    bogus = RefreshTicket(ref=d.binding.ref, version=2, holder="A", secret=b"\x00" * 32)
    with pytest.raises(CredentialUnavailable) as exc:
        platform.complete_refresh(d2.binding, SCOPE, bogus, SecretBytes(b"evil"))
    assert exc.value.code == VaultErrorCode.LEASE_LOST
    for malformed in (None, object(), "ticket"):
        with pytest.raises(CredentialUnavailable) as malformed_exc:
            platform.complete_refresh(d2.binding, SCOPE, malformed, SecretBytes(b"evil"))
        assert malformed_exc.value.code == VaultErrorCode.INVALID_ARGUMENT


@WINDOWS_ONLY
def test_local_complete_refresh_rejects_malformed_ticket(tmp_path):
    local = DpapiVaultBackend(
        daemon_id="daemon-ticket", store_id="daemon:default", base=tmp_path / "local"
    )
    local.attest()
    local_store = VaultStore(
        custody=Custody.DAEMON_LOCAL,
        store_id="daemon:default",
        daemon_id="daemon-ticket",
    )
    descriptor = local.put(
        local_store,
        SCOPE,
        SecretKind.GITHUB_APP_USER_TOKEN,
        SecretBytes(b"token"),
    )
    with pytest.raises(CredentialUnavailable) as exc:
        local.complete_refresh(
            descriptor.binding, SCOPE, object(), SecretBytes(b"replacement")
        )
    assert exc.value.code == VaultErrorCode.INVALID_ARGUMENT


# ===========================================================================
# Review r4 finding 5 — typed errors after cached attestation + ref validation
# ===========================================================================


def test_corrupt_db_after_attestation_is_typed_and_invalidates_gate(platform, store, tmp_path):
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"x"))
    with open(tmp_path / "vault.db", "r+b") as fh:
        fh.seek(0)
        fh.write(b"NOT A SQLITE DATABASE HEADER" * 20)
    with pytest.raises(CredentialUnavailable) as exc:  # never a raw sqlite3 error
        platform.get(d.binding, SCOPE)
    assert exc.value.code in {VaultErrorCode.CORRUPT_RECORD, VaultErrorCode.BACKEND_UNAVAILABLE}
    assert platform._attested is None  # cached gate invalidated → re-probes next time


def test_malformed_ref_is_not_echoed(platform, store):
    injected = SecretBinding(
        ref="secret:v1:zz\ninjected-log-line", kind=SecretKind.API_KEY, scope=SCOPE, store=store
    )
    with pytest.raises(CredentialUnavailable) as exc:
        platform.get(injected, SCOPE)
    assert exc.value.code == VaultErrorCode.NOT_FOUND
    assert exc.value.ref is None  # malformed ref never echoed into the error
    assert "injected" not in str(exc.value)


@WINDOWS_ONLY
def test_local_attestation_verifies_dacl_honestly(tmp_path):
    """Local attestation is HONEST: it passes only when the file DACL is verified
    to be current-user + SYSTEM only, and fails when the DACL is broadened."""
    from tinyassets.credentials import local_backend as lb

    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "loc")
    result = be.attest()
    assert result.ok is True
    assert result.checks["dacl_current_user_only"] is True  # actually verified

    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"probe"))
    blob = be._blob_path(d.binding.ref, d.version)
    assert lb.dacl_is_current_user_and_system_only(blob) is True

    # Broaden the DACL (grant Everyone) → the verifier must report False.
    import ntsecuritycon
    import win32security

    everyone = win32security.ConvertStringSidToSid("S-1-1-0")
    sd = win32security.GetFileSecurity(str(blob), win32security.DACL_SECURITY_INFORMATION)
    dacl = sd.GetSecurityDescriptorDacl()
    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_GENERIC_READ, everyone)
    win32security.SetNamedSecurityInfo(
        str(blob), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, dacl, None,
    )
    assert lb.dacl_is_current_user_and_system_only(blob) is False
    ev = be.inspect_persisted(d.binding.ref, b"probe")
    assert ev["dacl_current_user_only"] is False


# ===========================================================================
# Review r10 finding 1 — anti-rollback vs FULL-VOLUME restore
# (guard is an INDEPENDENT recovery domain OUTSIDE /data)
# ===========================================================================


def test_full_volume_restore_forces_reauthorization(tmp_path):
    """Restoring the ENTIRE data volume rolls the DB epoch back; the guard lives
    in an INDEPENDENT recovery domain OUTSIDE the volume, so the restore does not
    carry it and every op forces reauthorization — the real backup/restore path."""
    data = tmp_path / "data"
    data.mkdir()
    guard = tmp_path / "guard-domain"  # independent recovery domain, NOT under /data
    kp = _kp("k1")
    be = PlatformVaultBackend(
        kp, store_id="platform:default", db_path=data / "vault.db", guard_dir=guard
    )
    be.attest()
    store = VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:default")
    d = be.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"tok"))
    snap = tmp_path / "data-snapshot"
    shutil.copytree(data, snap)  # snapshot the WHOLE volume
    tk = be.begin_refresh(d.binding, SCOPE, "A", at_version=1)
    be.complete_refresh(d.binding, SCOPE, tk, SecretBytes(b"tok2"))
    # restore the WHOLE volume; the guard-domain is untouched (outside /data)
    shutil.rmtree(data)
    shutil.copytree(snap, data)
    fresh = PlatformVaultBackend(
        kp, store_id="platform:default", db_path=data / "vault.db", guard_dir=guard
    )
    with pytest.raises(CredentialUnavailable) as exc:
        fresh.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED
    with pytest.raises(CredentialUnavailable) as exc2:
        fresh.begin_refresh(d.binding, SCOPE, "B", at_version=1)
    assert exc2.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


def test_bump_for_restore_forces_reauth(tmp_path):
    """``backup-restore.sh`` explicitly advances the guard so a restore ALWAYS
    forces reauthorization — belt-and-suspenders even if the guard were co-located
    and carried by a restore."""
    guard = tmp_path / "guard"
    kp = _kp("k1")
    be = PlatformVaultBackend(
        kp, store_id="platform:default", db_path=tmp_path / "vault.db", guard_dir=guard
    )
    be.attest()
    store = VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:default")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v"))
    with be.get(d.binding, SCOPE) as lease:
        assert lease.reveal() == b"v"  # fine before the restore signal
    be._epoch.bump_for_restore()
    with pytest.raises(CredentialUnavailable) as exc:
        be.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


# ===========================================================================
# Review r10 finding 2 — rollback detection is fail-OPEN unless EVERY mutation
# checks it; the guard must be durable, fail-closed, and concurrency-safe
# ===========================================================================


def test_put_and_delete_check_rollback_first(platform, store, tmp_path):
    """A rolled-back store must be refused by put() AND delete(), not only reads —
    else one unrelated put catches the DB epoch up and re-exposes the credential."""
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v1"))
    db = tmp_path / "vault.db"
    snap = tmp_path / "snap.db"
    shutil.copy(db, snap)  # snapshot at epoch N
    platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v2"))  # advance epoch
    shutil.copy(snap, db)  # roll the DB back to epoch N (guard stays ahead)
    fresh = PlatformVaultBackend(platform._keys, store_id="platform:default", db_path=db)
    with pytest.raises(CredentialUnavailable) as exc_put:
        fresh.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"attack"))
    assert exc_put.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED
    with pytest.raises(CredentialUnavailable) as exc_del:
        fresh.delete(d.binding, SCOPE)
    assert exc_del.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


def test_epoch_guard_never_regresses_under_concurrent_advance(tmp_path):
    """The guard's high-water is monotonic: concurrent advances (including
    out-of-order lower values) never regress it below the max — the deterministic
    race Codex reproduced (epoch 1 left after epoch 2) cannot happen."""
    import threading

    from tinyassets.credentials.rollback import EpochGuard

    guard = EpochGuard("s", guard_dir=tmp_path / "g")
    guard.advance(1)
    errors: list[Exception] = []

    def _adv(v: int) -> None:
        try:
            guard.advance(v)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_adv, args=(v,)) for v in (5, 2, 4, 3, 5, 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert guard.read() == 5  # high-water preserved, never regressed


def test_rollback_guard_unavailable_fails_closed(platform, store, monkeypatch):
    """If the guard cannot be consulted, a mutation FAILS CLOSED
    (BACKEND_UNAVAILABLE) — never silently proceeds as if not rolled back."""
    from tinyassets.credentials.rollback import EpochGuard, GuardUnavailable

    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v"))

    def _boom(self):
        raise GuardUnavailable("guard volume offline")

    monkeypatch.setattr(EpochGuard, "read", _boom)
    with pytest.raises(CredentialUnavailable) as exc:
        platform.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.BACKEND_UNAVAILABLE


# ===========================================================================
# Review r11 findings 1-4 — reserve-before-commit, guard identity, stable reads
# ===========================================================================


def test_guard_reservation_failure_aborts_delete(platform, store, monkeypatch):
    """A vault commit can never outrun a failed external epoch reservation."""
    from tinyassets.credentials.rollback import EpochGuard, GuardUnavailable

    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"must-survive"))

    def _fail_reservation(self, expected_epoch):
        raise GuardUnavailable("injected guard write failure")

    monkeypatch.setattr(EpochGuard, "reserve", _fail_reservation, raising=False)
    with pytest.raises(CredentialUnavailable) as exc:
        platform.delete(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.BACKEND_UNAVAILABLE
    with platform.get(d.binding, SCOPE) as lease:
        assert lease.reveal() == b"must-survive"


def test_missing_guard_after_mutation_forces_reauthorization(platform, store, tmp_path):
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"must-not-recover"))
    guard_dir = tmp_path / "_vault_guard"
    shutil.rmtree(guard_dir)
    guard_dir.mkdir()  # recreated but empty recovery domain
    fresh = PlatformVaultBackend(
        platform._keys, store_id="platform:default", db_path=tmp_path / "vault.db"
    )
    with pytest.raises(CredentialUnavailable) as exc:
        fresh.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


def test_mismatched_guard_identity_forces_reauthorization(platform, store, tmp_path):
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"must-not-recover"))
    guard_db = tmp_path / "_vault_guard" / "rollback_guard.db"
    conn = sqlite3.connect(str(guard_db))
    conn.execute("UPDATE guard_epoch SET store_id = 'different-store-generation'")
    conn.commit()
    conn.close()
    fresh = PlatformVaultBackend(
        platform._keys, store_id="platform:default", db_path=tmp_path / "vault.db"
    )
    with pytest.raises(CredentialUnavailable) as exc:
        fresh.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.REAUTHORIZATION_REQUIRED


def test_corrupt_guard_fails_closed(platform, store, tmp_path):
    d = platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"must-not-recover"))
    guard_db = tmp_path / "_vault_guard" / "rollback_guard.db"
    guard_db.write_bytes(b"not a sqlite database")
    fresh = PlatformVaultBackend(
        platform._keys, store_id="platform:default", db_path=tmp_path / "vault.db"
    )
    with pytest.raises(CredentialUnavailable) as exc:
        fresh.get(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.BACKEND_UNAVAILABLE


@WINDOWS_ONLY
def test_independent_local_daemons_do_not_share_guard_identity(tmp_path):
    first = DpapiVaultBackend(daemon_id="daemon-a", store_id="daemon:default", base=tmp_path / "a")
    second = DpapiVaultBackend(daemon_id="daemon-b", store_id="daemon:default", base=tmp_path / "b")
    first.attest()
    second.attest()
    store_a = VaultStore(
        custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="daemon-a"
    )
    store_b = VaultStore(
        custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="daemon-b"
    )
    a = first.put(store_a, SCOPE, SecretKind.API_KEY, SecretBytes(b"a"))
    b = second.put(store_b, SCOPE, SecretKind.API_KEY, SecretBytes(b"b"))
    with first.get(a.binding, SCOPE) as lease_a, second.get(b.binding, SCOPE) as lease_b:
        assert lease_a.reveal() == b"a"
        assert lease_b.reveal() == b"b"


# ===========================================================================
# Review r10 finding 3 — local delete never claims success while bytes remain
# ===========================================================================


@WINDOWS_ONLY
def test_delete_with_locked_sidecar_reports_pending_then_sweeps(tmp_path, monkeypatch):
    """A locked sidecar during delete: the credential is already unreadable
    (tombstone committed) but delete() must NOT claim a full delete — it surfaces
    DELETE_PENDING, durably records the leftover, and a later op sweeps it."""
    from tinyassets.credentials import local_backend as lb

    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "loc")
    be.attest()
    store = VaultStore(custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"v1"))
    tail = d.binding.ref.rsplit(":", 1)[-1]

    real_remove = os.remove
    lock = {"on": True}

    def _locked_remove(path):
        if lock["on"] and str(path).endswith(".json"):
            raise PermissionError("sidecar locked by another handle")
        return real_remove(path)

    monkeypatch.setattr(lb.os, "remove", _locked_remove)

    with pytest.raises(CredentialUnavailable) as exc:
        be.delete(d.binding, SCOPE)
    assert exc.value.code == VaultErrorCode.DELETE_PENDING
    # already unreadable (tombstone committed), but bytes still on disk while locked
    with pytest.raises(CredentialUnavailable) as g:
        be.get(d.binding, SCOPE)
    assert g.value.code == VaultErrorCode.NOT_FOUND
    assert len(list(be._dir.glob(f"{tail}.v*.json"))) == 1  # leftover recorded pending

    # unlock: the NEXT op's sweep removes the leftover (no read path skips GC)
    lock["on"] = False
    with pytest.raises(CredentialUnavailable):
        be.get(d.binding, SCOPE)  # still NOT_FOUND, but sweeps the pending GC first
    assert len(list(be._dir.glob(f"{tail}.v*.json"))) == 0  # bytes now gone
