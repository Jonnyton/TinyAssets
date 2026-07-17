"""Legacy plaintext credential-vault migration (S5, one-way, fail-closed).

Retires a universe's ``.credential-vault.json`` + ``.credentials/`` plaintext
surface per the approved design (``docs/design-notes/2026-07-16-provider-
generic-credential-vault.md``, "Legacy migration"):

* legacy VALUES are **never promoted** into live vault refs — provenance,
  expiry, ownership, and scope are not trustworthy;
* each legacy credential becomes a metadata-only ``needs_redeposit``
  :class:`~tinyassets.credentials.SecretBinding` row with the correct
  canonical scope, so the founder sees exactly what must be reconnected and
  every lookup fails closed with ``REAUTHORIZATION_REQUIRED`` until then;
* every legacy artifact is sealed into a non-executable quarantine blob
  (XChaCha20-Poly1305 under the platform KEK), fsynced, and only then is the
  plaintext removed; a non-secret marker records the migration;
* quarantine can NEVER satisfy a credential lookup — this module exposes no
  read path for quarantined bytes.

Fail-closed discipline: unreadable or ambiguous legacy state raises
:class:`CredentialMigrationBlocked` and leaves the plaintext in place —
blocking is honest; assuming "fresh" is not. Treat every legacy value as
exposed: rotate at the provider regardless of migration success.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from tinyassets import credential_broker
from tinyassets.credential_broker import (
    BINDING_STATUS_NEEDS_REDEPOSIT,
    ENGINE_DESTINATION,
    ENGINE_PURPOSE,
    GITHUB_PROVIDER,
    GITHUB_WRITE_PURPOSE,
    LEGACY_ARTIFACT_DIR,
    LEGACY_VAULT_FILENAME,
    MIGRATION_MARKER_FILENAME,
    platform_store,
    record_binding,
    supported_llm_api_key_services,
)
from tinyassets.credentials import (
    KeyProvider,
    SecretBinding,
    SecretKind,
    SecretScope,
    new_secret_ref,
)
from tinyassets.credentials import crypto as vault_crypto
from tinyassets.credentials.paths import platform_vault_dir

QUARANTINE_SUBDIR = "quarantine"
QUARANTINE_AAD_CONTEXT = "legacy-quarantine-v1"

# Founder identity recorded on migrated bindings when the caller cannot supply
# an authenticated founder. Deliberately a sentinel, not an ambient guess: a
# needs_redeposit binding can never resolve, and the re-deposit REPLACES the
# row with the authenticated founder's identity.
UNVERIFIED_FOUNDER = "legacy:unverified"


class CredentialMigrationBlocked(RuntimeError):
    """Legacy state could not be migrated safely — plaintext left in place."""


def _read_legacy_records(vault_file: Path) -> list[dict[str, Any]]:
    """Strict read of the legacy vault file. Any ambiguity BLOCKS."""
    try:
        payload = json.loads(vault_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CredentialMigrationBlocked(
            f"legacy credential vault is unreadable ({exc.__class__.__name__}); "
            "refusing to assume it is empty. Fix or manually quarantine the "
            "file, then re-run."
        ) from exc
    if isinstance(payload, list):
        raw_records = payload
    elif isinstance(payload, dict):
        raw_records = payload.get("credentials", [])
    else:
        raise CredentialMigrationBlocked(
            "legacy credential vault must be a JSON object or list"
        )
    if not isinstance(raw_records, list) or not all(
        isinstance(item, dict) for item in raw_records
    ):
        raise CredentialMigrationBlocked(
            "legacy credential vault 'credentials' must be a list of objects"
        )
    return [dict(item) for item in raw_records]


def _service(record: dict[str, Any]) -> str:
    return str(record.get("service") or record.get("provider") or "").strip().lower()


def _legacy_scope(record: dict[str, Any]) -> tuple[str, str, str, SecretKind]:
    """Map one legacy record to canonical ``(provider, destination, purpose,
    kind)``. Unknown/ambiguous shapes BLOCK — never guessed."""
    credential_type = str(record.get("credential_type") or "").strip()
    service = _service(record)
    if credential_type == "vcs":
        destination = str(record.get("destination") or "").strip()
        if service != "github" or not destination:
            raise CredentialMigrationBlocked(
                "legacy vcs record needs service=github and a destination; "
                f"got service={service!r}"
            )
        # Legacy 'write' purpose becomes the canonical external_write; other
        # explicit purposes are carried verbatim.
        raw_purpose = str(record.get("purpose") or "write").strip()
        purpose = GITHUB_WRITE_PURPOSE if raw_purpose == "write" else raw_purpose
        return GITHUB_PROVIDER, destination, purpose, SecretKind.GITHUB_PAT
    if credential_type == "llm_api_key":
        if service not in supported_llm_api_key_services():
            raise CredentialMigrationBlocked(
                f"legacy llm_api_key record has unknown service {service!r}"
            )
        return service, ENGINE_DESTINATION, ENGINE_PURPOSE, SecretKind.API_KEY
    if credential_type == "llm_subscription":
        if not service:
            raise CredentialMigrationBlocked(
                "legacy llm_subscription record has no service"
            )
        return service, ENGINE_DESTINATION, ENGINE_PURPOSE, SecretKind.OAUTH2_GENERIC
    if credential_type == "social":
        if not service:
            raise CredentialMigrationBlocked("legacy social record has no service")
        destination = str(
            record.get("destination") or record.get("handle") or "account"
        ).strip()
        return service, destination, GITHUB_WRITE_PURPOSE, SecretKind.OAUTH2_GENERIC
    raise CredentialMigrationBlocked(
        f"legacy record has unknown credential_type {credential_type!r}; "
        "refusing to guess a scope"
    )


def _write_durable(path: Path, data: bytes) -> None:
    """Write + fsync through one fd (Windows fsync needs a writable handle)."""
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _quarantine_one(
    keys: KeyProvider,
    source: Path,
    relpath: str,
    universe_id: str,
    stamp: str,
    target_dir: Path,
    index: int,
) -> dict[str, Any]:
    """Seal one legacy artifact into a non-executable quarantine blob."""
    payload = source.read_bytes()
    aad = json.dumps(
        [QUARANTINE_AAD_CONTEXT, universe_id, relpath, stamp],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    envelope = vault_crypto.seal(keys, aad, payload)
    blob = {
        "schema": 1,
        "context": QUARANTINE_AAD_CONTEXT,
        "universe_id": universe_id,
        "relpath": relpath,
        "stamp": stamp,
        "algorithm": "xchacha20poly1305-ietf",
        "key_id": envelope.key_id,
        "wrap_nonce": envelope.wrap_nonce.hex(),
        "wrapped_dek": envelope.wrapped_dek.hex(),
        "data_nonce": envelope.data_nonce.hex(),
        "ciphertext": envelope.ciphertext.hex(),
    }
    blob_path = target_dir / f"{index:04d}.quarantine.json"
    _write_durable(
        blob_path,
        (json.dumps(blob, indent=1, sort_keys=True) + "\n").encode("utf-8"),
    )
    return {"relpath": relpath, "blob": blob_path.name, "bytes": len(payload)}


def migrate_universe_credentials(
    universe_dir: str | Path,
    *,
    founder_id: str = UNVERIFIED_FOUNDER,
    base: str | Path | None = None,
    key_provider: KeyProvider | None = None,
) -> dict[str, Any]:
    """Migrate one universe off the legacy plaintext vault. Idempotent.

    Order is crash-safe by construction: (1) record ``needs_redeposit``
    bindings, (2) durably seal quarantine blobs + manifest, (3) remove
    plaintext, (4) write the marker. A crash between steps leaves either the
    plaintext (re-run migrates again) or the marker-less clean state (re-run
    is a no-op with the bindings already recorded).
    """
    universe = Path(universe_dir)
    universe_id = universe.name
    marker = universe / MIGRATION_MARKER_FILENAME
    if marker.is_file():
        return {"status": "already_migrated", "universe_id": universe_id}
    vault_file = universe / LEGACY_VAULT_FILENAME
    artifact_dir = universe / LEGACY_ARTIFACT_DIR
    if not vault_file.exists() and not artifact_dir.exists():
        return {"status": "clean", "universe_id": universe_id}

    records = _read_legacy_records(vault_file) if vault_file.exists() else []

    # 1) Metadata-only needs_redeposit bindings (values are NOT promoted).
    bindings: list[dict[str, str]] = []
    for record in records:
        provider, destination, purpose, kind = _legacy_scope(record)
        binding = SecretBinding(
            ref=new_secret_ref(),  # unresolvable by construction: no vault row
            kind=kind,
            scope=SecretScope(
                founder_id=founder_id,
                universe_id=universe_id,
                provider=provider,
                destination=destination,
                purpose=purpose,
            ),
            store=platform_store(),
        )
        record_binding(
            binding,
            status=BINDING_STATUS_NEEDS_REDEPOSIT,
            source="legacy_migration",
            base=base,
        )
        bindings.append(
            {"provider": provider, "destination": destination, "purpose": purpose,
             "kind": kind.value}
        )

    # 2) Quarantine every legacy artifact under the platform KEK.
    # Resolved through the module so the test fixture's key-provider seam
    # (monkeypatching credential_broker.platform_key_provider) reaches it.
    keys = (
        key_provider
        if key_provider is not None
        else credential_broker.platform_key_provider()
    )
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    quarantine_dir = (
        platform_vault_dir(base) / QUARANTINE_SUBDIR / universe_id / stamp
    )
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    sources: list[tuple[Path, str]] = []
    if vault_file.exists():
        sources.append((vault_file, LEGACY_VAULT_FILENAME))
    if artifact_dir.exists():
        for child in sorted(artifact_dir.rglob("*")):
            if child.is_file():
                rel = child.relative_to(universe).as_posix()
                sources.append((child, rel))
    manifest_entries = [
        _quarantine_one(keys, src, rel, universe_id, stamp, quarantine_dir, i)
        for i, (src, rel) in enumerate(sources)
    ]
    manifest = quarantine_dir / "manifest.json"
    _write_durable(
        manifest,
        (json.dumps(
            {
                "schema": 1,
                "universe_id": universe_id,
                "stamp": stamp,
                "note": (
                    "Sealed legacy credential artifacts. NEVER a credential "
                    "source: no code path reads these back. Treat every legacy "
                    "value as exposed — rotate at the provider. Delete after "
                    "30 days / founder confirmation."
                ),
                "files": manifest_entries,
            },
            indent=1,
            sort_keys=True,
        ) + "\n").encode("utf-8"),
    )

    # 3) Remove active plaintext only after the sealed copies are durable.
    if vault_file.exists():
        vault_file.unlink()
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)

    # 4) Non-secret marker: the fail-closed record that this universe migrated.
    summary = {
        "status": "migrated",
        "universe_id": universe_id,
        "migrated_at": stamp,
        "bindings_needing_redeposit": bindings,
        "quarantine": str(quarantine_dir),
        "note": (
            "Legacy values were quarantined, not promoted. Re-deposit each "
            "credential through the broker (universe action=set_engine / the "
            "connect flow) to reactivate."
        ),
    }
    marker_tmp = marker.with_name(marker.name + ".tmp")
    _write_durable(
        marker_tmp,
        (
            json.dumps({"schema": 1, **summary}, indent=1, sort_keys=True) + "\n"
        ).encode("utf-8"),
    )
    marker_tmp.replace(marker)
    return summary


def migrate_all_universes(
    base: str | Path | None = None,
    *,
    founder_id: str = UNVERIFIED_FOUNDER,
    key_provider: KeyProvider | None = None,
) -> list[dict[str, Any]]:
    """Sweep every universe directory under the data root. Fails loud on the
    first blocked universe — a partial silent sweep would hide stuck legacy
    plaintext."""
    from tinyassets.storage import data_dir

    root = Path(base) if base is not None else data_dir()
    summaries: list[dict[str, Any]] = []
    if not root.is_dir():
        return summaries
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        summaries.append(
            migrate_universe_credentials(
                child, founder_id=founder_id, base=base, key_provider=key_provider
            )
        )
    return summaries
