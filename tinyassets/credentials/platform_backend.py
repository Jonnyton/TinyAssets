"""Platform custody backend: SQLite (rollback-journal) + XChaCha20-Poly1305-IETF.

For chatbot-only / 24×7 users. Ciphertext rows live in
``data_dir()/private/credential-vault/v1/vault.db``; the KEK is injected via a
:class:`~tinyassets.credentials.crypto.KeyProvider`.

Trust model: the plaintext DB columns (scope, store_id, kind, version, state,
expires_at, ...) are **non-authoritative index hints**. The authoritative record
lives inside the AEAD payload and the immutable identity is bound into the AAD.
Every authorization decision on read/replace/delete is taken from the decrypted
record — tampering a plaintext column has zero effect (a wrong hint just makes
the AAD wrong and the decrypt fail closed).

Guarantees:
  * per-record envelope encryption; immutable store identity bound in the AAD;
  * atomic compare-and-swap ``put(replace=, expected_version=)``;
  * **fenced** exclusive per-ref refresh lease (exactly-one-winner even when a
    holder exceeds its TTL) — the concurrent-refresh CVE class, closed;
  * KEK rotation that verifies every payload + record before committing;
  * fail-closed :class:`CredentialUnavailable` on every abnormal path.

Note (scope): this is the LIBRARY custody layer. The design's separate
vault-broker process / UID+capability drop / signed-capability / socket boundary
is PRODUCTION DEPLOYMENT integration (infra/compose), a named follow-up that
lands with the droplet integration — not provided or claimed by this library.
"""

from __future__ import annotations

import contextlib
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path

from . import crypto, leases, record
from .attestation import AttestationResult, attest_store
from .crypto import Envelope, KeyProvider
from .errors import CredentialUnavailable, VaultErrorCode
from .leases import RefreshLease, RefreshLeaseManager, RefreshTicket
from .paths import platform_vault_db_path
from .secret_bytes import SecretBytes, SecretLease, require_nonempty_bounded
from .types import (
    ROTATING_TOKEN_KINDS,
    XCHACHA20POLY1305_IETF,
    Custody,
    DescriptorState,
    SecretBinding,
    SecretDescriptor,
    SecretKind,
    SecretScope,
    VaultStore,
    is_secret_ref,
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
"""


def _aad(scope: SecretScope, ref: str, kind: str, version: int, store: VaultStore) -> bytes:
    return crypto.identity_aad(
        scope, ref, kind, version, store.store_id, store.custody.value, store.daemon_id
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
        self._leases = RefreshLeaseManager(self._connect)

    # ------------------------------------------------------------------
    # connection + schema
    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path), timeout=30.0, isolation_level=None)
        except OSError:
            # Backend I/O unavailable — never leak the path in a traceback.
            raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
        try:
            conn.row_factory = sqlite3.Row
            # Rollback-journal (NOT WAL) + FULL: version-independent durability.
            # WAL has a documented reset-corruption bug affecting CONCURRENT
            # WRITERS through SQLite 3.51.2 (this env links 3.50.4); the
            # credential workload is low-concurrency so rollback-journal sidesteps
            # the bug entirely while FULL fsyncs every commit for power-loss
            # durability of claims/rows.
            conn.execute("PRAGMA journal_mode = TRUNCATE")
            conn.execute("PRAGMA busy_timeout = 30000")
            # EXTRA (not FULL): rollback-journal FULL can still lose the LAST
            # committed transaction after power loss; EXTRA is the ACID setting
            # that fsyncs the directory after the journal is unlinked. A lost
            # claim would permit a second one-time redemption, so EXTRA it is.
            conn.execute("PRAGMA synchronous = EXTRA")
        except sqlite3.DatabaseError:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
            self._attested = None  # a corrupt DB invalidates the cached gate
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD) from None
        return conn

    def _fetch_row(self, ref: str) -> sqlite3.Row | None:
        """Look up a row by ref, normalizing SQLite corruption to a typed error.

        A DB corrupted AFTER a cached attestation must not leak a raw
        ``sqlite3.DatabaseError``; it becomes ``CORRUPT_RECORD`` and invalidates
        the attestation gate so the next call re-probes instead of serving from a
        stale pass.
        """
        conn = self._connect()
        try:
            return conn.execute(
                "SELECT * FROM vault_secrets WHERE ref = ?", (ref,)
            ).fetchone()
        except sqlite3.DatabaseError:
            self._attested = None
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref) from None
        finally:
            with contextlib.suppress(sqlite3.Error):
                conn.close()

    def initialize(self) -> None:
        if self._initialized:
            return
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.executescript(leases.LEASE_SCHEMA)
        finally:
            conn.close()
        self._initialized = True

    def durability_info(self) -> dict[str, str]:
        """Report the durability posture (for ops verification / the DR gate).

        ``synchronous`` MUST be ``EXTRA`` (the ACID/power-loss setting; FULL can
        still lose the last rollback-journal commit on power loss) and
        ``journal_mode`` MUST be a rollback-journal (``TRUNCATE``/``DELETE``), NOT
        ``WAL`` (WAL's reset-corruption bug, SQLite ≤3.51.2 / this env 3.50.4,
        hits concurrent writers). Full power-cut/VM-reset proof is a deploy
        validation item; EXTRA is the correct pragma.
        """
        self.initialize()
        conn = self._connect()
        try:
            sync = int(conn.execute("PRAGMA synchronous").fetchone()[0])
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        return {
            "sqlite_version": sqlite3.sqlite_version,
            "synchronous": {0: "OFF", 1: "NORMAL", 2: "FULL", 3: "EXTRA"}.get(sync, str(sync)),
            "journal_mode": str(journal),
        }

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
        fence: RefreshLease | None = None,
    ) -> SecretDescriptor:
        self._require_platform_store(store)
        require_nonempty_bounded(value)  # reject empty/oversized before any write
        leases.require_cas_pairing(replace, expected_version)
        self._ensure_attested()
        return self._put(
            store, scope, kind, value, replace, expected_version, expires_at, fence
        )

    def get(self, binding: SecretBinding, expected: SecretScope) -> SecretLease:
        self._require_platform_store(binding.store)
        self._ensure_attested()
        return self._get(binding, expected)

    def delete(self, binding: SecretBinding, expected: SecretScope) -> None:
        self._require_platform_store(binding.store)
        self._ensure_attested()
        self._delete(binding, expected)

    # ------------------------------------------------------------------
    # Internal (ungated) operations
    # ------------------------------------------------------------------
    def _require_platform_store(self, store: VaultStore) -> None:
        if store.custody != Custody.PLATFORM_ENCRYPTED:
            raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN)
        if store.store_id != self._store_id:
            raise CredentialUnavailable(VaultErrorCode.CROSS_STORE_FORBIDDEN)

    @staticmethod
    def _envelope_from_row(row: sqlite3.Row) -> Envelope:
        return Envelope(
            row["key_id"],
            bytes(row["wrap_nonce"]),
            bytes(row["wrapped_dek"]),
            bytes(row["data_nonce"]),
            bytes(row["ciphertext"]),
        )

    def _decrypt_row(
        self,
        row: sqlite3.Row,
        *,
        ref: str,
        kind: SecretKind,
        scope: SecretScope,
        store: VaultStore,
    ) -> tuple[dict, bytes]:
        """Decrypt + authenticate a row. Returns (authoritative_record, value).

        The AAD is built from the caller-provided identity (binding), NOT the
        plaintext columns; the version comes from the plaintext hint but a
        tampered version makes the AAD wrong and the decrypt fail closed.
        """
        try:
            version = int(row["version"])
        except (TypeError, ValueError):
            # Tampered non-integer version hint → typed error, never raw ValueError.
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD, ref) from None
        aad = _aad(scope, ref, kind.value, version, store)
        payload = crypto.open_envelope(self._keys, self._envelope_from_row(row), aad, ref)
        record_json, value = crypto.unframe_record(payload)
        rec = crypto.decode_record(record_json)
        record.verify_record_identity(
            rec, ref=ref, kind=kind, scope=scope, store=store, version=version
        )
        return rec, value

    def _put(
        self,
        store: VaultStore,
        scope: SecretScope,
        kind: SecretKind,
        value: SecretBytes,
        replace: str | None,
        expected_version: int | None,
        expires_at: float | None,
        fence: RefreshLease | None = None,
        ticket: RefreshTicket | None = None,
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
            else:
                ref = replace
                if not is_secret_ref(ref):
                    raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
                row = conn.execute(
                    "SELECT * FROM vault_secrets WHERE ref = ?", (ref,)
                ).fetchone()
                if row is None:
                    raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, ref)
                # Authenticate the FULL existing record against the caller's
                # scope/kind/store before allowing a replace (forged binding must
                # not overwrite a valid credential).
                existing, _existing_val = self._decrypt_row(
                    row, ref=ref, kind=kind, scope=scope, store=store
                )
                if (
                    expected_version is not None
                    and int(existing["version"]) != expected_version
                ):
                    raise CredentialUnavailable(VaultErrorCode.VERSION_CONFLICT, ref)
                if fence is not None:
                    self._require_fence(conn, ref, fence, now)
                if kind in ROTATING_TOKEN_KINDS and ticket is None:
                    # A rotating one-time token can only be advanced via
                    # complete_refresh (with a minted capability) — a bare CAS
                    # would bypass consume-before-mint.
                    raise CredentialUnavailable(VaultErrorCode.LEASE_LOST, ref)
                if ticket is not None and not (
                    ticket.ref == ref
                    and ticket.version == int(existing["version"])
                    and leases.capability_valid(
                        conn, ref, ticket.version, ticket.holder,
                        ticket._reveal_capability(),
                    )
                ):
                    # The completion must present the UNFORGEABLE minted
                    # capability — a reconstructed ticket cannot pass.
                    raise CredentialUnavailable(VaultErrorCode.LEASE_LOST, ref)
                version = int(existing["version"]) + 1
                created = float(existing["created_at"])

            rec = record.build_record(
                ref=ref, kind=kind, scope=scope, store=store, version=version,
                state=DescriptorState.ACTIVE, created_at=created, updated_at=now,
                expires_at=expires_at,
            )
            aad = _aad(scope, ref, kind.value, version, store)
            payload = crypto.frame_record(crypto.encode_record(rec), value.reveal())
            env = crypto.seal(self._keys, aad, payload)

            if replace is None:
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
                        ref, version - 1,
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
            binding=binding, version=version, created_at=created, updated_at=now,
            state=DescriptorState.ACTIVE, expires_at=expires_at,
        )

    @staticmethod
    def _require_fence(
        conn: sqlite3.Connection, ref: str, fence: RefreshLease, now: float
    ) -> None:
        if fence.ref != ref:
            raise CredentialUnavailable(VaultErrorCode.LEASE_LOST, ref)
        if not leases.verify_fence(conn, ref, fence.holder, fence.fence, now):
            raise CredentialUnavailable(VaultErrorCode.LEASE_LOST, ref)

    def _get(self, binding: SecretBinding, expected: SecretScope) -> SecretLease:
        # Validate the canonical ref FIRST — before scope comparison, lookup, or
        # any error echo — so a malformed ref (e.g. embedded newline) can never
        # reach a query or be reflected into a SCOPE_MISMATCH log line.
        if not is_secret_ref(binding.ref):
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)
        if binding.scope != expected:
            raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
        self.initialize()
        row = self._fetch_row(binding.ref)
        if row is None:
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND, binding.ref)
        rec, value = self._decrypt_row(
            row, ref=binding.ref, kind=binding.kind, scope=expected, store=binding.store
        )
        record.check_lifecycle(rec, binding.ref)
        return SecretLease(
            SecretBytes(value), ref=binding.ref, kind=binding.kind.value,
            scope=expected, version=int(rec["version"]),
        )

    def _delete(self, binding: SecretBinding, expected: SecretScope) -> None:
        if not is_secret_ref(binding.ref):
            # Validate before use; never echo a malformed ref (injection defense).
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)
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
            # Authenticate the COMPLETE record (ref/kind/scope/custody/store)
            # before removing — a forged/mismatched binding must not delete.
            self._decrypt_row(
                row, ref=binding.ref, kind=binding.kind, scope=expected,
                store=binding.store,
            )
            conn.execute("DELETE FROM vault_secrets WHERE ref = ?", (binding.ref,))
            leases.retire_claim(conn, binding.ref)  # a one-time ref is never reused
            conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Fenced exclusive per-ref refresh lease
    # ------------------------------------------------------------------
    def refresh_lease(
        self,
        ref: str,
        holder: str,
        *,
        ttl: float = 30.0,
        wait: float = 30.0,
        poll: float = 0.02,
    ) -> Iterator[RefreshLease]:
        """Acquire a fenced exclusive refresh lease for ``ref`` (COARSE coordination).

        The lease reduces thundering-herd contention, but it is NOT the
        exactly-once guarantee — a TTL overrun can still overlap holders. The
        real gate is :meth:`begin_refresh`, which atomically authenticates the
        current record and claims its redemption right. Recommended flow::

            with be.refresh_lease(ref, holder):
                current = be.get(binding, scope).version
                if current == stale:
                    ticket = be.begin_refresh(binding, scope, holder, at_version=current)
                    if ticket is not None:
                        new = provider_refresh(...)      # the ONE redemption
                        be.put(replace=ref, expected_version=ticket.version, value=new)
        """
        self.initialize()
        return self._leases.acquire(ref, holder, ttl=ttl, wait=wait, poll=poll)

    def begin_refresh(
        self, binding: SecretBinding, expected: SecretScope, holder: str, at_version: int
    ) -> RefreshTicket | None:
        """Atomic consume-before-mint gate for a refresh (the ONE broker refresh op).

        In a single transaction: authenticate the CURRENT record, enforce it is
        active + unexpired, confirm its version equals ``at_version`` (the version
        the caller observed), then claim the exclusive redemption right for THAT
        version. Returns a :class:`RefreshTicket` only to the sole winner; ``None``
        if the version already moved or is already claimed.

        Because the claimed version is the authenticated current version, a claim
        for a non-existent version (``at_version=99``) inserts NOTHING and can
        never permanently block it. Complete with
        ``put(replace=binding.ref, expected_version=ticket.version, ...)``.
        """
        self._require_platform_store(binding.store)
        self._ensure_attested()
        if not is_secret_ref(binding.ref):
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)
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
            rec, _value = self._decrypt_row(
                row, ref=binding.ref, kind=binding.kind, scope=expected, store=binding.store
            )
            record.check_lifecycle(rec, binding.ref)
            version = int(rec["version"])
            secret = leases.mint_capability()
            won = version == int(at_version) and leases.claim_refresh(
                conn, binding.ref, version, holder, time.time(),
                leases.capability_hash(secret),
            )
            conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        if not won:
            return None
        return RefreshTicket(
            ref=binding.ref, version=version, holder=holder, secret=secret
        )

    def complete_refresh(
        self,
        binding: SecretBinding,
        expected: SecretScope,
        ticket: RefreshTicket,
        value: SecretBytes,
        *,
        expires_at: float | None = None,
    ) -> SecretDescriptor:
        """Store the refreshed secret, bound to the ticket's durable claim.

        This is the ONLY sanctioned way to complete a refresh: the CAS advance
        succeeds only if ``ticket``'s claim is on record for the current version,
        so a completion cannot bypass consume-before-mint.
        """
        self._require_platform_store(binding.store)
        require_nonempty_bounded(value)  # reject empty/oversized before any write
        self._ensure_attested()
        if not is_secret_ref(binding.ref):
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)
        if binding.scope != expected:
            raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
        if ticket.ref != binding.ref:
            raise CredentialUnavailable(VaultErrorCode.LEASE_LOST, binding.ref)
        return self._put(
            binding.store, expected, binding.kind, value,
            binding.ref, ticket.version, expires_at, None, ticket,
        )

    # ------------------------------------------------------------------
    # KEK rotation (verified)
    # ------------------------------------------------------------------
    def rotate_kek(self, new_key_id: str) -> int:
        """Rewrap every record's DEK under ``new_key_id``; payloads unchanged.

        Requires ``new_key_id`` to be the ACTIVE write key (else future writes
        would keep using the old key while rows moved — a false success). Every
        row is decrypted + its full record authenticated INSIDE the transaction
        before rewrap; after rewrap no row may remain on any other key. Any
        corruption aborts the whole rotation. Attestation gates entry + exit.
        """
        self.initialize()
        if self._keys.active_key_id() != new_key_id:
            raise ValueError(
                "rotate_kek requires new_key_id to be the active write key; "
                "mark it active before rotating"
            )
        gate = self.attest()
        if not gate.ok:
            raise CredentialUnavailable(VaultErrorCode.ATTESTATION_FAILED)
        self._keys.get_key(new_key_id)  # fail loud before touching rows
        rewrapped = 0
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT * FROM vault_secrets").fetchall()
            for row in rows:
                # Reconstruct identity from UNAUTHENTICATED plaintext hints — a
                # forged custody/kind/version must become CORRUPT_RECORD, never a
                # raw ValueError, and must invalidate the cached attestation.
                try:
                    scope = SecretScope(
                        founder_id=row["founder_id"], universe_id=row["universe_id"],
                        provider=row["provider"], destination=row["destination"],
                        purpose=row["purpose"],
                    )
                    store = VaultStore(
                        custody=Custody(row["custody"]), store_id=row["store_id"],
                    )
                    kind = SecretKind(row["kind"])
                    version = int(row["version"])
                except (ValueError, TypeError, KeyError):
                    self._attested = None
                    raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD) from None
                aad = _aad(scope, row["ref"], kind.value, version, store)
                env = self._envelope_from_row(row)
                # Verify payload + record integrity before rewrap.
                payload = crypto.open_envelope(self._keys, env, aad, row["ref"])
                rec_json, _value = crypto.unframe_record(payload)
                rec = crypto.decode_record(rec_json)
                record.verify_record_identity(
                    rec, ref=row["ref"], kind=kind, scope=scope, store=store,
                    version=version,
                )
                if row["key_id"] == new_key_id:
                    continue
                new_env = crypto.rewrap_dek(self._keys, env, aad, new_key_id, row["ref"])
                conn.execute(
                    "UPDATE vault_secrets SET key_id = ?, wrap_nonce = ?, wrapped_dek = ? "
                    "WHERE ref = ?",
                    (new_env.key_id, new_env.wrap_nonce, new_env.wrapped_dek, row["ref"]),
                )
                rewrapped += 1
            # No live row may remain on any key other than the new one.
            stragglers = conn.execute(
                "SELECT COUNT(*) AS n FROM vault_secrets WHERE key_id != ?", (new_key_id,)
            ).fetchone()["n"]
            if stragglers:
                raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
            conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        post = self.attest()
        if not post.ok:
            raise CredentialUnavailable(VaultErrorCode.ATTESTATION_FAILED)
        return rewrapped

    # ------------------------------------------------------------------
    # Attestation-support hooks
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
        """Evidence about the persisted bytes for ``ref`` (attestation)."""
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
