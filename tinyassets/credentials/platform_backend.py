"""Platform custody backend: SQLite (WAL) + XChaCha20-Poly1305-IETF envelopes.

For chatbot-only / 24×7 users. Ciphertext rows live in
``data_dir()/private/credential-vault/v1/vault.db``; the KEK is injected via a
:class:`~tinyassets.credentials.crypto.KeyProvider` (a root-only file mount in
production, an in-memory key in tests). A backup of the DB reveals nothing
without the KEK.

Guarantees implemented here:
  * per-record envelope encryption with canonical scope/ref/version AAD;
  * atomic compare-and-swap ``put(replace=, expected_version=)``;
  * a DB-backed **exclusive per-ref lease** that serializes one-time refresh
    exchanges (closes the concurrent-refresh CVE class);
  * KEK rotation that rewraps DEKs without touching payload ciphertext;
  * fail-closed :class:`CredentialUnavailable` on every abnormal path.
"""

from __future__ import annotations

import contextlib
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path

from . import crypto
from .attestation import AttestationResult, attest_store
from .crypto import Envelope, KeyProvider
from .errors import CredentialUnavailable, VaultErrorCode
from .paths import platform_vault_db_path
from .secret_bytes import SecretBytes, SecretLease
from .types import (
    XCHACHA20POLY1305_IETF,
    Custody,
    DescriptorState,
    SecretBinding,
    SecretDescriptor,
    SecretKind,
    SecretScope,
    VaultStore,
    new_secret_ref,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_secrets (
    ref          TEXT PRIMARY KEY,
    store_id     TEXT NOT NULL,
    custody      TEXT NOT NULL,
    kind         TEXT NOT NULL,
    founder_id   TEXT NOT NULL,
    universe_id  TEXT NOT NULL,
    provider     TEXT NOT NULL,
    destination  TEXT NOT NULL,
    purpose      TEXT NOT NULL,
    version      INTEGER NOT NULL,
    state        TEXT NOT NULL,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    expires_at   REAL,
    algorithm    TEXT NOT NULL,
    key_id       TEXT NOT NULL,
    wrap_nonce   BLOB NOT NULL,
    wrapped_dek  BLOB NOT NULL,
    data_nonce   BLOB NOT NULL,
    ciphertext   BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS vault_refresh_leases (
    ref         TEXT PRIMARY KEY,
    holder      TEXT NOT NULL,
    acquired_at REAL NOT NULL,
    expires_at  REAL NOT NULL
);
"""


def _scope_from_row(row: sqlite3.Row) -> SecretScope:
    return SecretScope(
        founder_id=row["founder_id"],
        universe_id=row["universe_id"],
        provider=row["provider"],
        destination=row["destination"],
        purpose=row["purpose"],
    )


class PlatformVaultBackend:
    """XChaCha AEAD envelope store behind the :class:`VaultBroker` seam."""

    def __init__(
        self,
        key_provider: KeyProvider,
        *,
        store_id: str = "platform:default",
        db_path: str | Path | None = None,
        base: str | Path | None = None,
    ) -> None:
        self._keys = key_provider
        self._store_id = store_id
        self._db_path = (
            Path(db_path) if db_path is not None else platform_vault_db_path(base)
        )
        self._attested: bool | None = None
        self._initialized = False

    # ------------------------------------------------------------------
    # connection + schema
    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def initialize(self) -> None:
        if self._initialized:
            return
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
        finally:
            conn.close()
        self._initialized = True

    # ------------------------------------------------------------------
    # attestation gate
    # ------------------------------------------------------------------
    @property
    def store_id(self) -> str:
        return self._store_id

    @property
    def custody(self) -> Custody:
        return Custody.PLATFORM_ENCRYPTED

    def _ensure_attested(self) -> None:
        if self._attested is True:
            return
        if self._attested is False:
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE)
        result: AttestationResult = attest_store(self)
        self._attested = result.ok
        if not result.ok:
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE)

    def attest(self) -> AttestationResult:
        """Run (and cache) the per-store probe; return the structured result."""
        result = attest_store(self)
        self._attested = result.ok
        return result

    # ------------------------------------------------------------------
    # VaultBroker surface (attestation-gated)
    # ------------------------------------------------------------------
    def put(
        self,
        store: VaultStore,
        scope: SecretScope,
        kind: SecretKind,
        value: SecretBytes,
        *,
        replace: str | None = None,
        expected_version: int | None = None,
        expires_at: float | None = None,
    ) -> SecretDescriptor:
        self._require_platform_store(store)
        self._ensure_attested()
        return self._put(store, scope, kind, value, replace, expected_version, expires_at)

    def get(self, binding: SecretBinding, expected: SecretScope) -> SecretLease:
        self._require_platform_store(binding.store)
        self._ensure_attested()
        return self._get(binding, expected)

    def delete(self, binding: SecretBinding, expected: SecretScope) -> None:
        self._require_platform_store(binding.store)
        self._ensure_attested()
        self._delete(binding, expected)

    # ------------------------------------------------------------------
    # Internal (ungated) operations — used by attestation + gated surface
    # ------------------------------------------------------------------
    def _require_platform_store(self, store: VaultStore) -> None:
        if store.custody != Custody.PLATFORM_ENCRYPTED:
            raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN)
        if store.store_id != self._store_id:
            raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN)

    def _put(
        self,
        store: VaultStore,
        scope: SecretScope,
        kind: SecretKind,
        value: SecretBytes,
        replace: str | None,
        expected_version: int | None,
        expires_at: float | None,
    ) -> SecretDescriptor:
        self.initialize()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            now = time.time()
            if replace is None:
                ref = new_secret_ref()
                version = 1
                created = now
                env = crypto.seal(self._keys, scope, ref, kind.value, version, value.reveal())
                conn.execute(
                    """INSERT INTO vault_secrets(
                        ref, store_id, custody, kind, founder_id, universe_id,
                        provider, destination, purpose, version, state,
                        created_at, updated_at, expires_at, algorithm, key_id,
                        wrap_nonce, wrapped_dek, data_nonce, ciphertext)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ref, store.store_id, store.custody.value, kind.value,
                        scope.founder_id, scope.universe_id, scope.provider,
                        scope.destination, scope.purpose, version,
                        DescriptorState.ACTIVE.value, created, now, expires_at,
                        XCHACHA20POLY1305_IETF, env.key_id, env.wrap_nonce,
                        env.wrapped_dek, env.data_nonce, env.ciphertext,
                    ),
                )
            else:
                ref = replace
                row = conn.execute(
                    "SELECT * FROM vault_secrets WHERE ref = ?", (ref,)
                ).fetchone()
                if row is None:
                    raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, ref)
                if _scope_from_row(row) != scope:
                    raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, ref)
                if row["kind"] != kind.value:
                    raise CredentialUnavailable(VaultErrorCode.KIND_MISMATCH, ref)
                if row["store_id"] != store.store_id:
                    raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN, ref)
                if expected_version is not None and row["version"] != expected_version:
                    raise CredentialUnavailable(VaultErrorCode.VERSION_CONFLICT, ref)
                version = int(row["version"]) + 1
                created = float(row["created_at"])
                env = crypto.seal(self._keys, scope, ref, kind.value, version, value.reveal())
                cur = conn.execute(
                    """UPDATE vault_secrets SET
                        version = ?, state = ?, updated_at = ?, expires_at = ?,
                        algorithm = ?, key_id = ?, wrap_nonce = ?, wrapped_dek = ?,
                        data_nonce = ?, ciphertext = ?
                       WHERE ref = ? AND version = ?""",
                    (
                        version, DescriptorState.ACTIVE.value, now, expires_at,
                        XCHACHA20POLY1305_IETF, env.key_id, env.wrap_nonce,
                        env.wrapped_dek, env.data_nonce, env.ciphertext,
                        ref, int(row["version"]),
                    ),
                )
                if cur.rowcount != 1:
                    raise CredentialUnavailable(VaultErrorCode.VERSION_CONFLICT, ref)
            conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

        binding = SecretBinding(ref=ref, kind=kind, scope=scope, store=store)
        return SecretDescriptor(
            binding=binding,
            version=version,
            created_at=created,
            updated_at=now,
            state=DescriptorState.ACTIVE,
            expires_at=expires_at,
        )

    def _get(self, binding: SecretBinding, expected: SecretScope) -> SecretLease:
        if binding.scope != expected:
            raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
        self.initialize()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM vault_secrets WHERE ref = ?", (binding.ref,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, binding.ref)
        if (
            row["store_id"] != binding.store.store_id
            or row["custody"] != binding.store.custody.value
        ):
            raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN, binding.ref)
        if row["kind"] != binding.kind.value:
            raise CredentialUnavailable(VaultErrorCode.KIND_MISMATCH, binding.ref)

        self._check_state(row, binding.ref)

        version = int(row["version"])
        envelope = Envelope(
            row["key_id"],
            bytes(row["wrap_nonce"]),
            bytes(row["wrapped_dek"]),
            bytes(row["data_nonce"]),
            bytes(row["ciphertext"]),
        )
        value = crypto.open_envelope(
            self._keys, envelope, expected, binding.ref, binding.kind.value, version
        )
        return SecretLease(
            SecretBytes(value),
            ref=binding.ref,
            kind=binding.kind.value,
            scope=expected,
            version=version,
        )

    @staticmethod
    def _check_state(row: sqlite3.Row, ref: str) -> None:
        state = row["state"]
        if state == DescriptorState.DISABLED.value:
            raise CredentialUnavailable(VaultErrorCode.DISABLED, ref)
        if state == DescriptorState.REVOCATION_PENDING.value:
            raise CredentialUnavailable(VaultErrorCode.REVOKED, ref)
        expires_at = row["expires_at"]
        if expires_at is not None and float(expires_at) <= time.time():
            raise CredentialUnavailable(VaultErrorCode.EXPIRED, ref)

    def _delete(self, binding: SecretBinding, expected: SecretScope) -> None:
        if binding.scope != expected:
            raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
        self.initialize()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM vault_secrets WHERE ref = ?", (binding.ref,)
            ).fetchone()
            if row is None:
                raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, binding.ref)
            if _scope_from_row(row) != expected:
                raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
            if row["store_id"] != binding.store.store_id:
                raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN, binding.ref)
            conn.execute("DELETE FROM vault_secrets WHERE ref = ?", (binding.ref,))
            conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Exclusive per-ref refresh lease (serializes one-time refresh exchange)
    # ------------------------------------------------------------------
    @contextlib.contextmanager
    def refresh_lease(
        self,
        ref: str,
        holder: str,
        *,
        ttl: float = 30.0,
        wait: float = 30.0,
        poll: float = 0.02,
    ) -> Iterator[None]:
        """Block until this process exclusively holds the refresh lease for ``ref``.

        Two workers cannot both hold the lease; the loser blocks until the holder
        releases, then re-checks stored state and skips a redundant refresh. This
        is the mandatory serialization for rotating-refresh providers.
        """
        self.initialize()
        deadline = time.monotonic() + wait
        acquired = False
        while True:
            if self._try_acquire_lease(ref, holder, ttl):
                acquired = True
                break
            if time.monotonic() >= deadline:
                raise CredentialUnavailable(VaultErrorCode.LEASE_TIMEOUT, ref)
            time.sleep(poll)
        try:
            yield
        finally:
            if acquired:
                self._release_lease(ref, holder)

    def _try_acquire_lease(self, ref: str, holder: str, ttl: float) -> bool:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            now = time.time()
            conn.execute(
                "DELETE FROM vault_refresh_leases WHERE ref = ? AND expires_at < ?",
                (ref, now),
            )
            try:
                conn.execute(
                    "INSERT INTO vault_refresh_leases(ref, holder, acquired_at, expires_at) "
                    "VALUES(?,?,?,?)",
                    (ref, holder, now, now + ttl),
                )
            except sqlite3.IntegrityError:
                conn.execute("ROLLBACK")
                return False
            conn.execute("COMMIT")
            return True
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _release_lease(self, ref: str, holder: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM vault_refresh_leases WHERE ref = ? AND holder = ?",
                (ref, holder),
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # KEK rotation
    # ------------------------------------------------------------------
    def rotate_kek(self, new_key_id: str) -> int:
        """Rewrap every record's DEK under ``new_key_id``; payloads unchanged.

        The :class:`KeyProvider` must still expose both the old and new KEKs.
        Returns the number of rows rewrapped. Rows already on ``new_key_id`` are
        skipped.
        """
        self.initialize()
        # Validate the new key is available before touching any row.
        self._keys.get_key(new_key_id)
        rewrapped = 0
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT * FROM vault_secrets").fetchall()
            for row in rows:
                if row["key_id"] == new_key_id:
                    continue
                scope = _scope_from_row(row)
                version = int(row["version"])
                envelope = Envelope(
                    row["key_id"],
                    bytes(row["wrap_nonce"]),
                    bytes(row["wrapped_dek"]),
                    bytes(row["data_nonce"]),
                    bytes(row["ciphertext"]),
                )
                new_env = crypto.rewrap_dek(
                    self._keys, envelope, scope, row["ref"], row["kind"], version, new_key_id
                )
                conn.execute(
                    "UPDATE vault_secrets SET key_id = ?, wrap_nonce = ?, wrapped_dek = ? "
                    "WHERE ref = ?",
                    (new_env.key_id, new_env.wrap_nonce, new_env.wrapped_dek, row["ref"]),
                )
                rewrapped += 1
            conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return rewrapped

    # ------------------------------------------------------------------
    # Attestation-support hooks (duck-typed by attestation.attest_store)
    # ------------------------------------------------------------------
    def _probe_store(self) -> VaultStore:
        return VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id=self._store_id)

    def _probe_put(self, scope: SecretScope, value: bytes) -> SecretDescriptor:
        return self._put(
            self._probe_store(), scope, SecretKind.API_KEY, SecretBytes(value),
            None, None, None,
        )

    def _probe_get(self, binding: SecretBinding, expected: SecretScope) -> bytes:
        with self._get(binding, expected) as lease:
            return lease.reveal()

    def _probe_delete(self, binding: SecretBinding, expected: SecretScope) -> None:
        self._delete(binding, expected)

    def inspect_persisted(self, ref: str, probe_value: bytes) -> dict[str, object]:
        """Return evidence about the persisted bytes for ``ref`` (attestation).

        Confirms AEAD algorithm + ciphertext + wrapped DEK + active key_id are
        present and that the probe plaintext appears in NO stored column.
        """
        self.initialize()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM vault_secrets WHERE ref = ?", (ref,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return {"present": False}
        blob_columns = (
            bytes(row["wrap_nonce"]) + bytes(row["wrapped_dek"])
            + bytes(row["data_nonce"]) + bytes(row["ciphertext"])
        )
        return {
            "present": True,
            "algorithm": row["algorithm"],
            "algorithm_ok": row["algorithm"] == XCHACHA20POLY1305_IETF,
            "has_ciphertext": len(bytes(row["ciphertext"])) > 0,
            "has_wrapped_dek": len(bytes(row["wrapped_dek"])) > 0,
            "key_id": row["key_id"],
            "key_id_active": row["key_id"] == self._keys.active_key_id(),
            "plaintext_absent": probe_value not in blob_columns,
        }
