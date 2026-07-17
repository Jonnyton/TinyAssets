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
    # replace without expected_version → rejected (would permit lost updates)
    with pytest.raises(ValueError):
        platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"y"), replace=d.binding.ref)
    # expected_version without replace → rejected (inverse pairing)
    with pytest.raises(ValueError):
        platform.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(b"y"), expected_version=1)


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
    # k1 is still the active write key → rotating to k2 must be refused loudly.
    with pytest.raises(ValueError):
        platform.rotate_kek("k2")


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

    blob = str(be._blob_path(d.binding.ref))
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


def test_claim_table_bounded_and_retired_on_delete(platform, store, tmp_path):
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
    # delete retires the claim
    platform.delete(b, SCOPE)
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    try:
        n2 = conn.execute(
            "SELECT COUNT(*) FROM vault_refresh_claims WHERE ref = ?", (b.ref,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert n2 == 0


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
    be._blob_path(d.binding.ref).write_text("[]", encoding="utf-8")
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
    blob = be._blob_path(d.binding.ref)
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
