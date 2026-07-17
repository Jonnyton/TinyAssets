"""Defense-in-depth redaction proof.

Seeds canary token + PEM values, then scans every place a secret could leak —
persisted DB/blob bytes, temp files, exception text, ``repr``/``str``/``format``
of every vault type, public projections, and captured log output — asserting the
canary NEVER appears. Regex redaction is explicitly NOT the guarantee; this test
is (per the design's Redaction section).
"""

from __future__ import annotations

import logging
import sqlite3
import sys

import nacl.bindings as sodium
import pytest

from tinyassets.credentials import (
    CredentialUnavailable,
    Custody,
    DpapiBlob,
    DpapiVaultBackend,
    EncryptedRow,
    InMemoryKeyProvider,
    PlatformVaultBackend,
    SecretBinding,
    SecretBytes,
    SecretKind,
    SecretScope,
    VaultStore,
    new_secret_ref,
)

WINDOWS_ONLY = pytest.mark.skipif(
    sys.platform != "win32", reason="DPAPI local backend is Windows-only"
)

# Distinctive canary material — if any of these appears in a scanned surface the
# test fails loud.
CANARY_TOKEN = b"ghp_CANARYtoken0000000000000000000000AAA"
CANARY_PEM = (
    b"-----BEGIN RSA PRIVATE KEY-----\n"
    b"CANARY_PRIVATE_KEY_MATERIAL_ZZZ9\n"
    b"-----END RSA PRIVATE KEY-----\n"
)

SCOPE = SecretScope(
    founder_id="founder:red",
    universe_id="u-red",
    provider="github",
    destination="octo/repo",
    purpose="external_write",
)


def _collect_all_bytes(root) -> bytes:
    chunks: list[bytes] = []
    for path in root.rglob("*"):
        if path.is_file():
            chunks.append(path.read_bytes())
    return b"".join(chunks)


def _assert_absent(canary: bytes, blob: bytes, where: str) -> None:
    assert canary not in blob, f"canary leaked in {where}"
    # also guard the text projections
    assert canary.decode("latin-1") not in blob.decode("latin-1", "ignore"), where


@pytest.fixture()
def caplog_root():
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    prev_level = root.level
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    try:
        yield records
    finally:
        root.removeHandler(handler)
        root.setLevel(prev_level)


def test_platform_never_leaks_canary(tmp_path, caplog_root):
    kek = sodium.randombytes(32)
    be = PlatformVaultBackend(
        InMemoryKeyProvider({"k1": kek}, "k1"),
        store_id="platform:default",
        db_path=tmp_path / "vault.db",
    )
    store = VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:default")

    d_token = be.put(store, SCOPE, SecretKind.GITHUB_PAT, SecretBytes(CANARY_TOKEN))
    pem_scope = SecretScope(
        founder_id=SCOPE.founder_id, universe_id=SCOPE.universe_id,
        provider=SCOPE.provider, destination=SCOPE.destination, purpose="engine",
    )
    d_pem = be.put(store, pem_scope, SecretKind.GITHUB_APP_PRIVATE_KEY, SecretBytes(CANARY_PEM))

    # 0. sanity: the scanner CAN detect the canary when explicitly revealed
    with be.get(d_token.binding, SCOPE) as lease:
        assert CANARY_TOKEN in lease.reveal()

    # 1. persisted bytes (DB + WAL + any temp) contain no plaintext
    disk = _collect_all_bytes(tmp_path)
    assert len(disk) > 0
    _assert_absent(CANARY_TOKEN, disk, "platform disk")
    _assert_absent(CANARY_PEM, disk, "platform disk")

    # 2. raw sqlite column values contain no plaintext
    conn = sqlite3.connect(str(tmp_path / "vault.db"))
    try:
        rows = conn.execute("SELECT * FROM vault_secrets").fetchall()
        raw = repr(rows).encode("latin-1", "ignore")
    finally:
        conn.close()
    _assert_absent(CANARY_TOKEN, raw, "sqlite rows repr")
    _assert_absent(CANARY_PEM, raw, "sqlite rows repr")

    # 3. repr / str / format of every vault type
    with be.get(d_token.binding, SCOPE) as lease:
        surfaces = [
            repr(lease), str(lease), format(lease), format(lease, "x"),
            repr(SecretBytes(CANARY_TOKEN)), str(SecretBytes(CANARY_TOKEN)),
            format(SecretBytes(CANARY_TOKEN)),
            repr(d_token), repr(d_token.binding), repr(d_token.public_projection()),
            repr(d_pem.public_projection()),
        ]
    for surface in surfaces:
        _assert_absent(CANARY_TOKEN, surface.encode("latin-1", "ignore"), f"repr:{surface[:40]}")

    # 4. EncryptedRow / DpapiBlob type reprs (carry ciphertext only, never value)
    enc = EncryptedRow(
        descriptor=d_token, algorithm="xchacha20poly1305-ietf", key_id="k1",
        wrap_nonce=b"\x00" * 24, wrapped_dek=b"\x01" * 48, data_nonce=b"\x02" * 24,
        ciphertext=b"\x03" * 64,
    )
    _assert_absent(CANARY_TOKEN, repr(enc).encode("latin-1", "ignore"), "EncryptedRow repr")
    blob_meta = DpapiBlob(descriptor=d_token, blob_path="C:/x/y.json")
    _assert_absent(CANARY_TOKEN, repr(blob_meta).encode("latin-1", "ignore"), "DpapiBlob repr")

    # 5. exception text (not-found + wrong-scope) never carries the value
    be.delete(d_token.binding, SCOPE)
    try:
        be.get(d_token.binding, SCOPE)
    except CredentialUnavailable as exc:
        _assert_absent(CANARY_TOKEN, str(exc).encode("latin-1", "ignore"), "not-found exc")
    forged = SecretBinding(
        ref=new_secret_ref(), kind=SecretKind.GITHUB_PAT, scope=SCOPE, store=store
    )
    try:
        be.get(forged, SCOPE)
    except CredentialUnavailable as exc:
        _assert_absent(CANARY_TOKEN, str(exc).encode("latin-1", "ignore"), "forged exc")

    # 6. captured log output carries no canary
    log_blob = "\n".join(r.getMessage() for r in caplog_root).encode("latin-1", "ignore")
    _assert_absent(CANARY_TOKEN, log_blob, "logs")
    _assert_absent(CANARY_PEM, log_blob, "logs")


def test_reprs_hide_internal_metadata(tmp_path):
    """No repr/str of any vault type may leak custody/store/daemon ids, version,
    ciphertext, wrapped DEKs, or filesystem paths (design forbids them in logs)."""
    from tinyassets.credentials import DpapiBlob, EncryptedRow, SecretBinding
    from tinyassets.credentials.types import DescriptorState, SecretDescriptor

    kek = sodium.randombytes(32)
    be = PlatformVaultBackend(
        InMemoryKeyProvider({"STOREKEY-CANARY": kek}, "STOREKEY-CANARY"),
        store_id="STOREID-CANARY", db_path=tmp_path / "vault.db",
    )
    store = VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="STOREID-CANARY")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(CANARY_TOKEN))
    lease = be.get(d.binding, SCOPE)

    daemon_store = VaultStore(
        custody=Custody.DAEMON_LOCAL, store_id="STOREID-CANARY", daemon_id="DAEMON-CANARY"
    )
    binding = SecretBinding(
        ref=d.binding.ref, kind=SecretKind.API_KEY, scope=SCOPE, store=daemon_store
    )
    descriptor = SecretDescriptor(
        binding=binding, version=7770001, created_at=1.0, updated_at=2.0,
        state=DescriptorState.REVOCATION_PENDING,
    )
    enc = EncryptedRow(
        descriptor=descriptor, algorithm="xchacha20poly1305-ietf", key_id="STOREKEY-CANARY",
        wrap_nonce=b"WRAPCANARY", wrapped_dek=b"DEKCANARY", data_nonce=b"NONCECANARY",
        ciphertext=b"CIPHERTEXT-CANARY",
    )
    blob_meta = DpapiBlob(descriptor=descriptor, blob_path="C:/secret/PATH-CANARY.json")

    forbidden = (
        "STOREID-CANARY", "DAEMON-CANARY", "STOREKEY-CANARY", "7770001",
        "REVOCATION_PENDING", "revocation_pending", "CIPHERTEXT-CANARY",
        "DEKCANARY", "WRAPCANARY", "PATH-CANARY",
    )
    surfaces = [
        repr(store), str(store), repr(daemon_store), repr(binding), str(binding),
        repr(descriptor), str(descriptor), repr(lease), str(lease), format(lease),
        repr(enc), str(enc), repr(blob_meta), str(blob_meta),
    ]
    lease.zero()
    for surface in surfaces:
        for token in forbidden:
            assert token not in surface, f"internal metadata {token!r} leaked in {surface[:60]!r}"


def test_refresh_and_attestation_reprs_are_redacted(tmp_path):
    """AttestationResult / RefreshTicket / RefreshLease reprs must not leak
    store/custody/boot/holder/version/fence or the minted capability."""
    kek = sodium.randombytes(32)
    be = PlatformVaultBackend(
        InMemoryKeyProvider({"KEK-CANARY": kek}, "KEK-CANARY"),
        store_id="STOREID-CANARY", db_path=tmp_path / "vault.db",
    )
    store = VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="STOREID-CANARY")
    d = be.put(store, SCOPE, SecretKind.GITHUB_APP_USER_TOKEN, SecretBytes(b"tok"))
    result = be.attest()
    ticket = be.begin_refresh(d.binding, SCOPE, "HOLDER-CANARY", at_version=1)

    with be.refresh_lease(d.binding.ref, "HOLDER-CANARY", ttl=5.0) as lease:
        surfaces = [
            repr(result), str(result), repr(ticket), str(ticket),
            repr(lease), str(lease),
        ]
        forbidden = ["STOREID-CANARY", "HOLDER-CANARY", result.boot_id, result.custody]
        cap_hex = ticket.secret.hex()
        for surface in surfaces:
            for token in forbidden:
                assert token not in surface, f"leaked {token!r} in {surface!r}"
            assert cap_hex not in surface  # minted capability never in a repr


def test_public_projection_is_allowlist_only(tmp_path):
    kek = sodium.randombytes(32)
    be = PlatformVaultBackend(
        InMemoryKeyProvider({"k1": kek}, "k1"),
        store_id="platform:default",
        db_path=tmp_path / "vault.db",
    )
    store = VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id="platform:default")
    d = be.put(store, SCOPE, SecretKind.API_KEY, SecretBytes(CANARY_TOKEN))
    proj = d.public_projection()
    # Design allowlist = ref / kind / scope / timestamps ONLY (no version/state).
    assert set(proj) == {
        "ref", "kind", "scope", "created_at", "updated_at", "expires_at",
    }
    # no custody internals, key ids, ciphertext, wrapped DEKs, backend paths, lifecycle counters
    text = repr(proj)
    for forbidden in (
        "ciphertext", "wrapped_dek", "key_id", "wrap_nonce", "blob_path", "version", "state",
    ):
        assert forbidden not in text


@WINDOWS_ONLY
def test_dpapi_blob_never_leaks_canary(tmp_path):
    be = DpapiVaultBackend(daemon_id="d1", store_id="daemon:default", base=tmp_path / "local")
    store = VaultStore(
        custody=Custody.DAEMON_LOCAL, store_id="daemon:default", daemon_id="d1"
    )
    d = be.put(store, SCOPE, SecretKind.GITHUB_APP_PRIVATE_KEY, SecretBytes(CANARY_PEM))
    # sanity: revealing works
    with be.get(d.binding, SCOPE) as lease:
        assert CANARY_PEM in lease.reveal()
    # DPAPI blob file + sidecar contain no plaintext
    disk = _collect_all_bytes(tmp_path)
    _assert_absent(CANARY_PEM, disk, "dpapi disk")
    _assert_absent(CANARY_TOKEN, disk, "dpapi disk")
