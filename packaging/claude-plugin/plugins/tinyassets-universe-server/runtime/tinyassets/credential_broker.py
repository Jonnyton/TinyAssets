"""S5 credential seam: daemon-side wiring for the provider-generic vault.

This module is the single production route between TinyAssets callers and the
FROZEN vault CORE (:mod:`tinyassets.credentials`). It never re-implements
custody; it CONSUMES the broker contract:

* **Construction point** — :func:`platform_backend` builds the daemon's
  :class:`~tinyassets.credentials.PlatformVaultBackend` with
  ``run_context_lookup`` wired to the AUTHORITATIVE run store
  (:mod:`tinyassets.runs` + the daemon registry), so ``mint_job_grant`` can
  cross-check a run's real founder/universe. Without that lookup every mint
  fails closed (``CROSS_STORE_FORBIDDEN``) by vault design.
* **Binding registry** — the non-secret control-plane map
  ``(universe_id, provider, destination, purpose) -> SecretBinding`` in
  ``bindings.db`` next to the vault ciphertext DB. A
  :class:`~tinyassets.credentials.SecretBinding` is the ONLY credential shape
  allowed in control-plane rows (opaque ref + custody metadata, no value).
* **Deposit / resolution surfaces** — engine (BYO API key, Claude OAuth
  token, Codex auth bundle) and GitHub write credentials. Every miss is a
  typed :class:`~tinyassets.credentials.CredentialUnavailable`, never ``""``,
  ``None``, env, or ambient fallback. A ``needs_redeposit`` binding (created
  by the legacy migration) raises ``REAUTHORIZATION_REQUIRED``: legacy values
  are never promoted, the founder must re-deposit (design note
  ``docs/design-notes/2026-07-16-provider-generic-credential-vault.md``,
  "Legacy migration").

Scope vocabulary (canonical; S4's GitHub client and the Phase-2 runner mint
consume these exact strings):

* GitHub write credential: ``provider="github"``, ``destination="owner/repo"``,
  ``purpose="external_write"``.
* Engine credential: ``provider=<service>`` (``anthropic``/``openai``/...),
  ``destination="cli_subprocess"``, ``purpose="engine_auth"``.

Production KEK config: ``TINYASSETS_VAULT_KEK_DIR`` names the root-only key
directory for :class:`~tinyassets.credentials.FileKeyProvider` (outside
``/data``). Unset means platform custody is unavailable — fail closed.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

from tinyassets.credentials import (
    CredentialUnavailable,
    Custody,
    FileKeyProvider,
    JobContext,
    KeyProvider,
    PlatformVaultBackend,
    SecretBinding,
    SecretBytes,
    SecretKind,
    SecretLease,
    SecretScope,
    VaultErrorCode,
    VaultStore,
    is_secret_ref,
)
from tinyassets.credentials.paths import platform_vault_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical scope vocabulary
# ---------------------------------------------------------------------------

GITHUB_PROVIDER = "github"
GITHUB_WRITE_PURPOSE = "external_write"
ENGINE_DESTINATION = "cli_subprocess"
ENGINE_PURPOSE = "engine_auth"

PLATFORM_STORE_ID = "platform:default"

# Map a deposited BYO API key's service to the provider-subprocess env var the
# CLI providers read (moved verbatim from the retired legacy vault module).
LLM_API_KEY_ENV_BY_SERVICE: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "claude-code": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "codex": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "xai": "XAI_API_KEY",
    "grok": "XAI_API_KEY",
}

# Which deposited engine services feed which CLI-subprocess provider. Keys are
# ProviderRouter provider names; values are normalized deposit ``provider``
# (service) strings. Exact-match — no cross-provider bleed.
ENGINE_SERVICES_BY_CLI_PROVIDER: dict[str, tuple[str, ...]] = {
    "codex": ("openai", "codex"),
    "claude-code": ("anthropic", "claude", "claude-code"),
}

# New-world engine-auth materialization dir (Codex auth bundle). Deliberately
# NOT the legacy ``.credentials/`` name: that path is a legacy-remnant signal
# (see require_no_legacy_vault) and must never be recreated by the new route.
ENGINE_AUTH_DIR = ".engine-auth"

# Legacy plaintext artifacts (owned by the retired tinyassets.credential_vault).
LEGACY_VAULT_FILENAME = ".credential-vault.json"
LEGACY_ARTIFACT_DIR = ".credentials"
MIGRATION_MARKER_FILENAME = ".credential-vault.retired.json"


def supported_llm_api_key_services() -> frozenset[str]:
    """Services a BYO ``llm_api_key`` deposit may target (validated at deposit)."""
    return frozenset(LLM_API_KEY_ENV_BY_SERVICE)


class LegacyCredentialVaultError(RuntimeError):
    """Unmigrated legacy plaintext credential state detected — fail closed.

    The legacy ``.credential-vault.json`` / ``.credentials/`` surface is
    retired (Hard Rule 11: no fallback reader). Any read through the new
    broker while legacy artifacts are still present must BLOCK until
    ``scripts/migrate_legacy_credential_vaults.py`` has quarantined them —
    never silently ignore them, never read them.
    """


def require_no_legacy_vault(universe_dir: str | Path) -> None:
    """Raise :class:`LegacyCredentialVaultError` on unmigrated legacy state.

    Post-migration universes carry ``.credential-vault.retired.json`` (the
    non-secret marker) and may legitimately have neither legacy artifact. An
    orphaned ``.credentials/`` dir WITHOUT the marker is ambiguous legacy
    state and blocks too — ambiguity must never read as "fresh".
    """
    universe = Path(universe_dir)
    legacy_file = universe / LEGACY_VAULT_FILENAME
    legacy_dir = universe / LEGACY_ARTIFACT_DIR
    if (universe / MIGRATION_MARKER_FILENAME).is_file():
        if legacy_file.exists() or legacy_dir.exists():
            raise LegacyCredentialVaultError(
                f"universe {universe.name!r} has legacy credential plaintext "
                "that reappeared after retirement. Refusing to trust either "
                "state; quarantine the restored artifacts before continuing."
            )
        return
    if legacy_file.exists() or legacy_dir.exists():
        raise LegacyCredentialVaultError(
            f"universe {universe.name!r} has unmigrated legacy credential "
            "artifacts (.credential-vault.json / .credentials). The legacy "
            "plaintext vault is retired and has no reader. Run "
            "`python scripts/migrate_legacy_credential_vaults.py` to "
            "quarantine it, then re-deposit credentials through the broker."
        )


# ---------------------------------------------------------------------------
# Construction point: key provider + backend + run-context lookup
# ---------------------------------------------------------------------------

VAULT_KEK_DIR_ENV = "TINYASSETS_VAULT_KEK_DIR"

_PRELOADED_KEY_PROVIDER: KeyProvider | None = None


class _PreloadedPlatformKeyProvider:
    """Process-local KEKs captured at the root custody boundary."""

    def __init__(self, keys: dict[str, bytes], active_key_id: str) -> None:
        self._keys = dict(keys)
        self._active_key_id = active_key_id

    def active_key_id(self) -> str:
        return self._active_key_id

    def get_key(self, key_id: str) -> bytes:
        try:
            return self._keys[key_id]
        except KeyError:
            raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE) from None


def preload_platform_keys() -> KeyProvider:
    """Validate and preload every root-owned KEK before privilege drop.

    The container starts as root solely for this custody boundary.  The daemon
    process then keeps only opaque key bytes in memory and drops to UID 1001;
    it never gains filesystem access to the root-only KEK mount.
    """
    global _PRELOADED_KEY_PROVIDER

    kek_dir = os.environ.get(VAULT_KEK_DIR_ENV, "").strip()
    if not kek_dir:
        raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE)
    file_provider = FileKeyProvider(kek_dir)
    active_key_id = file_provider.active_key_id()
    key_ids = {
        path.name.removesuffix(".bin")
        for path in Path(kek_dir).glob("*.bin")
        if path.name.endswith(".bin")
    }
    key_ids.add(active_key_id)
    keys = {key_id: file_provider.get_key(key_id) for key_id in sorted(key_ids)}
    _PRELOADED_KEY_PROVIDER = _PreloadedPlatformKeyProvider(keys, active_key_id)
    return _PRELOADED_KEY_PROVIDER


def platform_key_provider() -> KeyProvider:
    """The production KEK source. ``TINYASSETS_VAULT_KEK_DIR`` is required."""
    if _PRELOADED_KEY_PROVIDER is not None:
        return _PRELOADED_KEY_PROVIDER
    kek_dir = os.environ.get(VAULT_KEK_DIR_ENV, "").strip()
    if not kek_dir:
        # No KEK directory -> platform custody cannot decrypt anything. Typed
        # fail-closed; never a silent empty vault.
        raise CredentialUnavailable(VaultErrorCode.KEY_UNAVAILABLE)
    return FileKeyProvider(kek_dir)


def platform_store() -> VaultStore:
    return VaultStore(custody=Custody.PLATFORM_ENCRYPTED, store_id=PLATFORM_STORE_ID)


def run_context_lookup(base_path: str | Path) -> Callable[[str], JobContext]:
    """Build the AUTHORITATIVE ``run_id -> JobContext`` lookup for grant minting.

    Identity fields, verified against the run store schema
    (``tinyassets/runs.py``):

    * ``founder_id`` <- ``runs.owner_user_id`` — resolved at ``create_run``
      from the daemon registry's ``owner_user_id`` (or passed explicitly by
      the API layer). This is the run record's founder-identity column.
    * ``universe_id`` <- the run's ``runtime_instance_id`` joined through
      ``daemon_server.get_runtime_instance`` — runs carry no universe column;
      the runtime-instance registry is the authoritative universe binding.

    A run without an owner or without a runtime instance CANNOT anchor a
    credential grant: the lookup raises (fail loud), which the vault maps to
    ``CROSS_STORE_FORBIDDEN`` at mint time.
    """
    base = Path(base_path)

    def _lookup(run_id: str) -> JobContext:
        from tinyassets.daemon_server import get_runtime_instance
        from tinyassets.runs import runs_db_path

        db = runs_db_path(base)
        if not db.is_file():
            raise LookupError(f"no run store at base {base.name!r}")
        conn = sqlite3.connect(db, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT owner_user_id, runtime_instance_id FROM runs "
                "WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        finally:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        if row is None:
            raise LookupError(f"run {run_id!r} not found in the run store")
        founder_id = str(row["owner_user_id"] or "").strip()
        if not founder_id:
            raise LookupError(
                f"run {run_id!r} has no owner_user_id; an ownerless run "
                "cannot anchor a credential grant"
            )
        runtime_instance_id = str(row["runtime_instance_id"] or "").strip()
        if not runtime_instance_id:
            raise LookupError(
                f"run {run_id!r} has no runtime_instance_id; a run without a "
                "runtime identity cannot anchor a credential grant"
            )
        runtime = get_runtime_instance(base, instance_id=runtime_instance_id)
        universe_id = str(runtime.get("universe_id") or "").strip()
        if not universe_id:
            raise LookupError(
                f"runtime instance for run {run_id!r} has no universe_id"
            )
        return JobContext(
            run_id=run_id, universe_id=universe_id, founder_id=founder_id
        )

    return _lookup


_BACKENDS: dict[tuple[str, str], PlatformVaultBackend] = {}


def platform_backend(
    base: str | Path | None = None,
    *,
    key_provider: KeyProvider | None = None,
) -> PlatformVaultBackend:
    """The daemon's single :class:`PlatformVaultBackend` construction point.

    ``base`` overrides the data root (tests); production resolves through
    ``data_dir()``. The backend is cached per data root so the attestation
    gate does not re-probe on every call. ``run_context_lookup`` is always
    wired — a backend built here can mint job grants against the real run
    store.
    """
    from tinyassets.storage import data_dir

    root = Path(base) if base is not None else data_dir()
    cache_key = (str(root), os.environ.get(VAULT_KEK_DIR_ENV, "").strip())
    cached = _BACKENDS.get(cache_key)
    if cached is not None and key_provider is None:
        return cached
    backend = PlatformVaultBackend(
        key_provider if key_provider is not None else platform_key_provider(),
        store_id=PLATFORM_STORE_ID,
        base=root,
        run_context_lookup=run_context_lookup(root),
    )
    if key_provider is None:
        _BACKENDS[cache_key] = backend
    return backend


def _reset_backend_cache() -> None:
    """Test seam: drop cached backends (per-test tmp roots must not leak)."""
    _BACKENDS.clear()


# ---------------------------------------------------------------------------
# Binding registry (non-secret control plane)
# ---------------------------------------------------------------------------

BINDINGS_DB_FILENAME = "bindings.db"

BINDING_STATUS_ACTIVE = "active"
BINDING_STATUS_NEEDS_REDEPOSIT = "needs_redeposit"
BINDING_STATUS_REVOKED = "revoked"
_VALID_BINDING_STATUS = frozenset(
    {BINDING_STATUS_ACTIVE, BINDING_STATUS_NEEDS_REDEPOSIT, BINDING_STATUS_REVOKED}
)

_BINDINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS credential_bindings (
    universe_id  TEXT NOT NULL,
    provider     TEXT NOT NULL,
    destination  TEXT NOT NULL,
    purpose      TEXT NOT NULL,
    founder_id   TEXT NOT NULL,
    ref          TEXT NOT NULL,
    kind         TEXT NOT NULL,
    custody      TEXT NOT NULL,
    store_id     TEXT NOT NULL,
    daemon_id    TEXT,
    status       TEXT NOT NULL,
    source       TEXT NOT NULL,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    PRIMARY KEY (universe_id, provider, destination, purpose)
);

CREATE TABLE IF NOT EXISTS github_connection_metadata (
    universe_id     TEXT NOT NULL,
    destination     TEXT NOT NULL,
    app_id          TEXT NOT NULL DEFAULT '',
    installation_id TEXT NOT NULL DEFAULT '',
    app_actor_id    TEXT NOT NULL DEFAULT '',
    account_login   TEXT NOT NULL DEFAULT '',
    client_id       TEXT NOT NULL DEFAULT '',
    updated_at      REAL NOT NULL,
    PRIMARY KEY (universe_id, destination)
);
"""


def bindings_db_path(base: str | Path | None = None) -> Path:
    """Registry location: beside the vault ciphertext DB (same /data volume,
    same backup/restore recovery domain)."""
    return platform_vault_dir(base) / BINDINGS_DB_FILENAME


def registry_exists(base: str | Path | None = None) -> bool:
    return bindings_db_path(base).is_file()


def _registry_connect(base: str | Path | None, *, create: bool) -> sqlite3.Connection:
    db = bindings_db_path(base)
    if not create and not db.is_file():
        raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)
    try:
        if create:
            db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.executescript(_BINDINGS_SCHEMA)
    except (OSError, sqlite3.Error):
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
    return conn


def _clean_field(value: object, field: str, *, max_len: int = 4096) -> str:
    """Symmetric boundary validation — applied on BOTH write and read."""
    if not isinstance(value, str):
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > max_len
        or any(ch in cleaned for ch in ("\x00", "\r", "\n"))
    ):
        logger.error("credential binding field %s failed validation", field)
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
    return cleaned


def _clean_optional_metadata(value: object, field: str) -> str:
    if value in (None, ""):
        return ""
    return _clean_field(value, field, max_len=512)


def set_github_connection_metadata(
    universe_id: str,
    destination: str,
    *,
    app_id: str = "",
    installation_id: str = "",
    app_actor_id: str = "",
    account_login: str = "",
    client_id: str = "",
    base: str | Path | None = None,
) -> None:
    """Persist GitHub's non-secret connection identifiers beside bindings.

    The fixed columns deliberately exclude tokens, refresh tokens, private keys,
    and client secrets; those values belong only in the encrypted vault record.
    """
    values = {
        "universe_id": _clean_field(universe_id, "universe_id"),
        "destination": _clean_field(destination, "destination"),
        "app_id": _clean_optional_metadata(app_id, "app_id"),
        "installation_id": _clean_optional_metadata(
            installation_id, "installation_id"
        ),
        "app_actor_id": _clean_optional_metadata(app_actor_id, "app_actor_id"),
        "account_login": _clean_optional_metadata(
            account_login, "account_login"
        ).lstrip("@").lower(),
        "client_id": _clean_optional_metadata(client_id, "client_id"),
    }
    conn = _registry_connect(base, create=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO github_connection_metadata(
                universe_id, destination, app_id, installation_id,
                app_actor_id, account_login, client_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(universe_id, destination) DO UPDATE SET
                app_id = excluded.app_id,
                installation_id = excluded.installation_id,
                app_actor_id = excluded.app_actor_id,
                account_login = excluded.account_login,
                client_id = excluded.client_id,
                updated_at = excluded.updated_at
            """,
            (
                values["universe_id"],
                values["destination"],
                values["app_id"],
                values["installation_id"],
                values["app_actor_id"],
                values["account_login"],
                values["client_id"],
                time.time(),
            ),
        )
        conn.execute("COMMIT")
    except sqlite3.Error:
        with contextlib.suppress(sqlite3.Error):
            conn.execute("ROLLBACK")
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
    finally:
        with contextlib.suppress(sqlite3.Error):
            conn.close()


def github_connection_metadata(
    universe_id: str,
    destination: str,
    *,
    base: str | Path | None = None,
) -> dict[str, str]:
    """Return only the allowlisted, non-secret GitHub connection metadata."""
    if not registry_exists(base):
        return {}
    universe = _clean_field(universe_id, "universe_id")
    dest = _clean_field(destination, "destination")
    conn = _registry_connect(base, create=False)
    try:
        row = conn.execute(
            "SELECT app_id, installation_id, app_actor_id, account_login, client_id "
            "FROM github_connection_metadata WHERE universe_id = ? AND destination = ?",
            (universe, dest),
        ).fetchone()
    except sqlite3.Error:
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
    finally:
        with contextlib.suppress(sqlite3.Error):
            conn.close()
    if row is None:
        return {}
    return {
        "app_id": _clean_optional_metadata(row["app_id"], "app_id"),
        "installation_id": _clean_optional_metadata(
            row["installation_id"], "installation_id"
        ),
        "app_actor_id": _clean_optional_metadata(row["app_actor_id"], "app_actor_id"),
        "account_login": _clean_optional_metadata(
            row["account_login"], "account_login"
        ).lstrip("@").lower(),
        "client_id": _clean_optional_metadata(row["client_id"], "client_id"),
    }


def github_account_login(
    universe_id: str, *, base: str | Path | None = None
) -> str:
    """Return the universe's one unambiguous connected GitHub account login."""
    if not registry_exists(base):
        return ""
    universe = _clean_field(universe_id, "universe_id")
    conn = _registry_connect(base, create=False)
    try:
        rows = conn.execute(
            "SELECT DISTINCT lower(account_login) AS account_login "
            "FROM github_connection_metadata "
            "WHERE universe_id = ? AND account_login != ''",
            (universe,),
        ).fetchall()
    except sqlite3.Error:
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
    finally:
        with contextlib.suppress(sqlite3.Error):
            conn.close()
    if len(rows) != 1:
        return ""
    return _clean_optional_metadata(rows[0]["account_login"], "account_login")


def _binding_from_row(row: sqlite3.Row) -> tuple[SecretBinding, str]:
    """Validate a registry row and rebuild ``(SecretBinding, status)``.

    A corrupt/tampered row is a typed ``CORRUPT_RECORD`` — and even a row that
    validates here cannot leak a value: the vault re-authenticates the full
    scope in the AEAD AAD at ``get`` time, so a rewritten scope fails decrypt.
    """
    try:
        scope = SecretScope(
            founder_id=_clean_field(row["founder_id"], "founder_id"),
            universe_id=_clean_field(row["universe_id"], "universe_id"),
            provider=_clean_field(row["provider"], "provider"),
            destination=_clean_field(row["destination"], "destination"),
            purpose=_clean_field(row["purpose"], "purpose"),
        )
        ref = row["ref"]
        if not is_secret_ref(ref):
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
        kind = SecretKind(row["kind"])
        custody = Custody(row["custody"])
        store_id = _clean_field(row["store_id"], "store_id")
        raw_daemon = row["daemon_id"]
        daemon_id = (
            _clean_field(raw_daemon, "daemon_id") if raw_daemon is not None else None
        )
        store = VaultStore(custody=custody, store_id=store_id, daemon_id=daemon_id)
        status = row["status"]
        if status not in _VALID_BINDING_STATUS:
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
    except CredentialUnavailable:
        raise
    except (KeyError, IndexError, TypeError, ValueError):
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD) from None
    return SecretBinding(ref=ref, kind=kind, scope=scope, store=store), status


def record_binding(
    binding: SecretBinding,
    *,
    status: str = BINDING_STATUS_ACTIVE,
    source: str = "deposit",
    base: str | Path | None = None,
) -> None:
    """Upsert one control-plane binding row (validated before write)."""
    if status not in _VALID_BINDING_STATUS:
        raise CredentialUnavailable(VaultErrorCode.INVALID_ARGUMENT)
    if not is_secret_ref(binding.ref):
        raise CredentialUnavailable(VaultErrorCode.INVALID_ARGUMENT)
    scope = binding.scope
    fields = {
        "founder_id": _clean_field(scope.founder_id, "founder_id"),
        "universe_id": _clean_field(scope.universe_id, "universe_id"),
        "provider": _clean_field(scope.provider, "provider").lower(),
        "destination": _clean_field(scope.destination, "destination"),
        "purpose": _clean_field(scope.purpose, "purpose"),
    }
    source = _clean_field(source, "source")
    now = time.time()
    conn = _registry_connect(base, create=True)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO credential_bindings(
                universe_id, provider, destination, purpose, founder_id,
                ref, kind, custody, store_id, daemon_id, status, source,
                created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(universe_id, provider, destination, purpose)
            DO UPDATE SET
                founder_id = excluded.founder_id,
                ref = excluded.ref,
                kind = excluded.kind,
                custody = excluded.custody,
                store_id = excluded.store_id,
                daemon_id = excluded.daemon_id,
                status = excluded.status,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                fields["universe_id"], fields["provider"], fields["destination"],
                fields["purpose"], fields["founder_id"], binding.ref,
                binding.kind.value, binding.store.custody.value,
                binding.store.store_id, binding.store.daemon_id, status, source,
                now, now,
            ),
        )
        conn.execute("COMMIT")
    except sqlite3.Error:
        with contextlib.suppress(sqlite3.Error):
            conn.execute("ROLLBACK")
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
    finally:
        with contextlib.suppress(sqlite3.Error):
            conn.close()


def find_binding(
    universe_id: str,
    provider: str,
    purpose: str,
    destination: str,
    *,
    base: str | Path | None = None,
) -> SecretBinding:
    """Exact-match binding lookup. Typed miss — never ``None``.

    * ``NOT_FOUND`` — no row for the exact (universe, provider, destination,
      purpose) key.
    * ``REAUTHORIZATION_REQUIRED`` — a ``needs_redeposit`` row (legacy
      migration created the binding but the value was never promoted; the
      founder must re-deposit).
    * ``REVOKED`` — a disconnected credential; effectors must not use it.
    """
    universe_id = _clean_field(universe_id, "universe_id")
    provider = _clean_field(provider, "provider").lower()
    purpose = _clean_field(purpose, "purpose")
    destination = _clean_field(destination, "destination")
    conn = _registry_connect(base, create=False)
    try:
        row = conn.execute(
            "SELECT * FROM credential_bindings WHERE universe_id = ? AND "
            "provider = ? AND destination = ? AND purpose = ?",
            (universe_id, provider, destination, purpose),
        ).fetchone()
    except sqlite3.Error:
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
    finally:
        with contextlib.suppress(sqlite3.Error):
            conn.close()
    if row is None:
        raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)
    binding, status = _binding_from_row(row)
    if status == BINDING_STATUS_NEEDS_REDEPOSIT:
        raise CredentialUnavailable(
            VaultErrorCode.REAUTHORIZATION_REQUIRED, binding.ref
        )
    if status == BINDING_STATUS_REVOKED:
        raise CredentialUnavailable(VaultErrorCode.REVOKED, binding.ref)
    return binding


def list_bindings(
    universe_id: str,
    *,
    provider: str | None = None,
    purpose: str | None = None,
    base: str | Path | None = None,
) -> list[tuple[SecretBinding, str]]:
    """All validated ``(binding, status)`` rows for a universe (optionally
    filtered). Returns ``[]`` when the registry has never been created."""
    if not registry_exists(base):
        return []
    universe_id = _clean_field(universe_id, "universe_id")
    query = "SELECT * FROM credential_bindings WHERE universe_id = ?"
    params: list[str] = [universe_id]
    if provider is not None:
        query += " AND provider = ?"
        params.append(_clean_field(provider, "provider").lower())
    if purpose is not None:
        query += " AND purpose = ?"
        params.append(_clean_field(purpose, "purpose"))
    conn = _registry_connect(base, create=False)
    try:
        rows = conn.execute(query, params).fetchall()
    except sqlite3.Error:
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
    finally:
        with contextlib.suppress(sqlite3.Error):
            conn.close()
    return [_binding_from_row(row) for row in rows]


def universe_has_bindings(
    universe_id: str,
    *,
    provider: str | None = None,
    base: str | Path | None = None,
) -> bool:
    """True when the universe is vault-routed (ANY row, any status).

    This is the two-tier gate the GitHub effectors use: a vault-routed
    universe never falls through to the host env tier — including when its
    rows are ``needs_redeposit`` or ``revoked`` (falling back would run the
    universe on the HOST's credentials: the ambient identity leak)."""
    if not registry_exists(base):
        return False
    universe_id = _clean_field(universe_id, "universe_id")
    query = "SELECT COUNT(*) FROM credential_bindings WHERE universe_id = ?"
    params: list[str] = [universe_id]
    if provider is not None:
        query += " AND provider = ?"
        params.append(_clean_field(provider, "provider").lower())
    conn = _registry_connect(base, create=False)
    try:
        count = int(conn.execute(query, params).fetchone()[0])
    except sqlite3.Error:
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE) from None
    finally:
        with contextlib.suppress(sqlite3.Error):
            conn.close()
    return count > 0


# ---------------------------------------------------------------------------
# Deposit
# ---------------------------------------------------------------------------


def deposit_credential(
    *,
    universe_id: str,
    founder_id: str,
    provider: str,
    destination: str,
    purpose: str,
    kind: SecretKind,
    value: bytes,
    expires_at: float | None = None,
    base: str | Path | None = None,
    backend: PlatformVaultBackend | None = None,
) -> dict[str, object]:
    """Deposit one credential value into platform custody + record the binding.

    Returns the descriptor's non-secret public projection (ref/kind/scope/
    timestamps) — safe for logs and MCP responses. The value itself never
    appears in any return, log, or registry row.
    """
    scope = SecretScope(
        founder_id=_clean_field(founder_id, "founder_id"),
        universe_id=_clean_field(universe_id, "universe_id"),
        provider=_clean_field(provider, "provider").lower(),
        destination=_clean_field(destination, "destination"),
        purpose=_clean_field(purpose, "purpose"),
    )
    be = backend if backend is not None else platform_backend(base)
    existing = [
        (binding, status)
        for binding, status in list_bindings(
            scope.universe_id, provider=scope.provider, purpose=scope.purpose, base=base
        )
        if binding.scope.destination == scope.destination
    ]
    if existing and existing[0][1] == BINDING_STATUS_ACTIVE:
        binding = existing[0][0]
        if binding.scope != scope:
            raise CredentialUnavailable(VaultErrorCode.SCOPE_MISMATCH, binding.ref)
        if binding.kind != kind:
            raise CredentialUnavailable(VaultErrorCode.INVALID_ARGUMENT, binding.ref)
        with be.get(binding, scope) as lease:
            version = lease.version
        _revoke_job_grants(be, binding.ref)
        descriptor = be.put(
            binding.store,
            scope,
            kind,
            SecretBytes(value),
            replace=binding.ref,
            expected_version=version,
            expires_at=expires_at,
        )
        return descriptor.public_projection()

    descriptor = be.put(
        platform_store(), scope, kind, SecretBytes(value), expires_at=expires_at
    )
    try:
        record_binding(descriptor.binding, status=BINDING_STATUS_ACTIVE, base=base)
    except Exception:
        try:
            be.delete(descriptor.binding, descriptor.binding.scope)
        except Exception as cleanup_error:
            raise CredentialUnavailable(
                VaultErrorCode.BACKEND_UNAVAILABLE, descriptor.binding.ref
            ) from cleanup_error
        raise
    return descriptor.public_projection()


def _revoke_job_grants(backend: PlatformVaultBackend, ref: str) -> None:
    """Invalidate every outstanding job capability before credential CAS."""
    from tinyassets.credentials.grants import revoke_grant

    backend.initialize()
    conn = backend._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        grant_ids = [
            str(row[0])
            for row in conn.execute(
                "SELECT grant_id FROM vault_job_grants WHERE ref = ?", (ref,)
            ).fetchall()
        ]
        for grant_id in grant_ids:
            revoke_grant(conn, grant_id)
        if grant_ids:
            backend._reserve_epoch(conn)
        conn.execute("COMMIT")
    except sqlite3.Error:
        with contextlib.suppress(sqlite3.Error):
            conn.execute("ROLLBACK")
        raise CredentialUnavailable(VaultErrorCode.BACKEND_UNAVAILABLE, ref) from None
    finally:
        with contextlib.suppress(sqlite3.Error):
            conn.close()


def deposit_engine_api_key(
    *,
    universe_id: str,
    founder_id: str,
    service: str,
    api_key: str,
    base: str | Path | None = None,
    backend: PlatformVaultBackend | None = None,
) -> dict[str, object]:
    """Deposit a founder's BYO LLM API key (validated against the service map)."""
    service = _clean_field(service, "service").lower()
    if service not in supported_llm_api_key_services():
        raise CredentialUnavailable(VaultErrorCode.INVALID_ARGUMENT)
    return deposit_credential(
        universe_id=universe_id,
        founder_id=founder_id,
        provider=service,
        destination=ENGINE_DESTINATION,
        purpose=ENGINE_PURPOSE,
        kind=SecretKind.API_KEY,
        value=api_key.encode("utf-8"),
        base=base,
        backend=backend,
    )


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_credential(
    universe_id: str,
    provider: str,
    purpose: str,
    destination: str,
    *,
    base: str | Path | None = None,
    backend: PlatformVaultBackend | None = None,
) -> SecretLease:
    """Binding lookup + authenticated vault read. Every failure is typed."""
    binding = find_binding(universe_id, provider, purpose, destination, base=base)
    be = backend if backend is not None else platform_backend(base)
    return be.get(binding, binding.scope)


def github_token(
    universe_dir: str | Path,
    destination: str,
    *,
    purpose: str = GITHUB_WRITE_PURPOSE,
    base: str | Path | None = None,
    backend: PlatformVaultBackend | None = None,
) -> str | None:
    """GitHub write-token resolution for the effector two-tier contract.

    Explicit tri-state (documented, not ambient):

    * ``None``  — this universe is not vault-routed at all (no registry rows).
      The CALLER may consult its own env-vended capability tier; that is the
      pre-vault host-capability route, not a credential fallback.
    * ``""``    — vault-authoritative "not authorized for this destination".
      The caller MUST NOT fall through to env.
    * ``str``   — the resolved token.

    ``needs_redeposit`` / ``revoked`` / corrupt rows RAISE (typed) — a
    universe whose credential was quarantined or disconnected must fail
    loudly, never silently push with the host's token.
    """
    universe = Path(universe_dir)
    require_no_legacy_vault(universe)
    universe_id = universe.name
    if not universe_has_bindings(universe_id, base=base):
        return None
    try:
        lease = resolve_credential(
            universe_id, GITHUB_PROVIDER, purpose, destination,
            base=base, backend=backend,
        )
    except CredentialUnavailable as exc:
        if exc.code == VaultErrorCode.NOT_FOUND:
            # Vault-routed universe, no credential for this destination:
            # "not authorized" — block the env tier.
            return ""
        raise
    with lease:
        return lease.reveal().decode("utf-8")


def resolve_universe_from_env(env: dict[str, str] | None = None) -> Path | None:
    """Resolve the active universe path from env, if one is explicitly bound."""
    source = os.environ if env is None else env
    value = source.get("TINYASSETS_UNIVERSE", "").strip()
    return Path(value) if value else None


def _materialize_codex_home(universe_dir: Path, auth_json: bytes) -> Path:
    """Write the vault-held Codex auth bundle to the CLI-consumable home.

    ``codex exec`` reads auth from a file — materialization at point of use
    (0700 dir / 0600 file, atomic replace) is the CLI's contract, mirroring
    the retired legacy behavior but sourced from platform custody."""
    home = universe_dir / ENGINE_AUTH_DIR / "codex"
    home.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(home.parent, 0o700)
    _chmod_best_effort(home, 0o700)
    auth_file = home / "auth.json"
    tmp = auth_file.with_name("auth.json.tmp")
    tmp.write_bytes(auth_json)
    _chmod_best_effort(tmp, 0o600)
    tmp.replace(auth_file)
    _chmod_best_effort(auth_file, 0o600)
    config_file = home / "config.toml"
    if not config_file.exists():
        config_file.write_text(
            'cli_auth_credentials_store = "file"\n', encoding="utf-8"
        )
        _chmod_best_effort(config_file, 0o600)
    return home


def _chmod_best_effort(path: Path, mode: int) -> None:
    with contextlib.suppress(OSError):
        os.chmod(path, mode)


def provider_auth_env_overrides(
    provider_name: str,
    universe_dir: str | Path,
    *,
    base: str | Path | None = None,
    backend: PlatformVaultBackend | None = None,
    require_binding: bool = False,
) -> dict[str, str]:
    """Subprocess env overrides for a CLI provider, from platform custody.

    Composes the universe's deposited engine credentials (BYO API key, Claude
    OAuth token, Codex auth bundle) for exactly one CLI provider — no
    cross-provider bleed. A universe with no engine deposits returns ``{}``
    (the host_daemon default engine, which never reads the vault).

    Fail-closed rules:

    * unmigrated legacy artifacts -> :class:`LegacyCredentialVaultError`;
    * any relevant ``needs_redeposit`` / ``revoked`` binding raises
      ``REAUTHORIZATION_REQUIRED`` / ``REVOKED`` — the engine STOPS until the
      founder reconnects; it never silently runs on the host's credentials.
    """
    universe = Path(universe_dir)
    require_no_legacy_vault(universe)
    services = ENGINE_SERVICES_BY_CLI_PROVIDER.get(provider_name.strip())
    if not services:
        if require_binding:
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)
        return {}
    universe_id = universe.name
    rows = [
        (binding, status)
        for binding, status in list_bindings(
            universe_id, purpose=ENGINE_PURPOSE, base=base
        )
        if binding.scope.provider in services
        and binding.scope.destination == ENGINE_DESTINATION
    ]
    if not rows:
        if require_binding:
            raise CredentialUnavailable(VaultErrorCode.NOT_FOUND)
        return {}
    for binding, status in rows:
        if status == BINDING_STATUS_NEEDS_REDEPOSIT:
            raise CredentialUnavailable(
                VaultErrorCode.REAUTHORIZATION_REQUIRED, binding.ref
            )
        if status == BINDING_STATUS_REVOKED:
            raise CredentialUnavailable(VaultErrorCode.REVOKED, binding.ref)
    be = backend if backend is not None else platform_backend(base)
    overrides: dict[str, str] = {}
    for binding, _status in rows:
        with be.get(binding, binding.scope) as lease:
            value = lease.reveal()
            if binding.kind == SecretKind.API_KEY:
                env_var = LLM_API_KEY_ENV_BY_SERVICE.get(binding.scope.provider)
                if env_var is None:
                    raise CredentialUnavailable(
                        VaultErrorCode.CORRUPT_RECORD, binding.ref
                    )
                overrides[env_var] = value.decode("utf-8")
            elif binding.kind == SecretKind.OAUTH2_GENERIC:
                if provider_name.strip() == "codex":
                    home = _materialize_codex_home(universe, bytes(value))
                    overrides["CODEX_HOME"] = str(home)
                else:
                    overrides["CLAUDE_CODE_OAUTH_TOKEN"] = value.decode("utf-8")
            else:
                # An engine row holding a non-engine kind is registry
                # corruption — typed, never skipped.
                raise CredentialUnavailable(
                    VaultErrorCode.CORRUPT_RECORD, binding.ref
                )
    return overrides
