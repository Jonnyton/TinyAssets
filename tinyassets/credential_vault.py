"""Per-universe credential vault helpers.

The vault stores credentials that are scoped to one universe directory. Public
state and run evidence should reference only summaries; resolver helpers return
secret values only to daemon-side effectors/providers that need them.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VAULT_FILENAME = ".credential-vault.json"
CREDENTIAL_ARTIFACT_DIR = ".credentials"
VALID_CREDENTIAL_TYPES = frozenset(
    # "http" is the general outbound-connection credential (channel-agnostic
    # outbound): a single token/secret for a user-declared HTTP connection,
    # resolved by connection id via `outbound_connections._GeneralVaultCredentialResolver`.
    {"social", "llm_subscription", "llm_api_key", "vcs", "http"}
)

# Map a deposited llm_api_key record's ``service`` to the provider-subprocess
# env var that CLI providers read. Only CLI-subprocess providers are reachable
# via the vault env overlay (claude-code / codex); the in-process HTTP free-tier
# providers build their client from process env at import and are out of scope.
_LLM_API_KEY_ENV_BY_SERVICE: dict[str, str] = {
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

_SUBSCRIPTION_ALIAS_SLOTS_BY_SERVICE: dict[
    str, tuple[frozenset[str], ...]
] = {
    "claude": (
        frozenset({
            "claude_config_dir",
            "config_dir",
            "path",
            "claude_home",
            "home",
            "auth_home",
        }),
        frozenset({
            "oauth_token",
            "claude_code_oauth_token",
            "token_b64",
            "secret_b64",
        }),
    ),
    "codex": (
        frozenset({
            "codex_home",
            "home",
            "auth_home",
            "path",
            "auth_json_path",
        }),
    ),
}


def credential_vault_path(universe_dir: str | Path) -> Path:
    """Return the vault file path for *universe_dir*."""
    return Path(universe_dir) / VAULT_FILENAME


def vault_exists(universe_dir: str | Path | None) -> bool:
    """Return True when a vault file exists for *universe_dir*."""
    return universe_dir is not None and credential_vault_path(universe_dir).is_file()


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _as_path(value: Any, universe_dir: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = universe_dir / candidate
    return candidate


def _secret_artifact_dir(universe_dir: Path, service: str) -> Path:
    service_part = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in service.strip().lower()
    ) or "credential"
    target = universe_dir / CREDENTIAL_ARTIFACT_DIR / service_part
    target.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(target.parent, 0o700)
    _chmod_best_effort(target, 0o700)
    return target


def _decode_codex_auth_json(value: Any) -> bytes:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "credential auth_json_b64 must be a non-empty base64 string"
        )
    normalized = value.translate(str.maketrans("", "", " \t\r\n"))
    try:
        decoded = base64.b64decode(normalized, validate=True)
    except ValueError:
        raise ValueError(
            "credential auth_json_b64 base64 decode failed"
        ) from None
    if not decoded:
        raise ValueError("credential auth_json_b64 decoded content is empty")
    if decoded.startswith(b"\xef\xbb\xbf"):
        raise ValueError("credential auth_json_b64 decoded content has a UTF-8 BOM")
    invalid = False
    try:
        json.loads(decoded)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Not chained: both of these retain the decoded credential blob
        # (`.doc` / `.object`). Raised outside the handler so no context
        # survives either.
        invalid = True
    if invalid:
        raise ValueError("credential auth_json_b64 does not contain valid JSON")
    return decoded


def _normalize_record(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("credential entries must be JSON objects")
    record = dict(raw)
    credential_type = record.get("credential_type")
    if not isinstance(credential_type, str) or not credential_type.strip():
        raise ValueError("credential_type is required")
    normalized_type = credential_type.strip()
    if normalized_type not in VALID_CREDENTIAL_TYPES:
        # The rejected value is NOT echoed. It is attacker- or typo-supplied
        # vault content, and a reviewer put a live token in this field and read
        # it back out of the exception. Naming the allowed set is enough to fix
        # a real mistake.
        allowed = ", ".join(sorted(VALID_CREDENTIAL_TYPES))
        raise ValueError(f"unknown credential_type; expected one of: {allowed}")
    record["credential_type"] = normalized_type
    for key in ("service", "provider", "destination", "purpose"):
        if isinstance(record.get(key), str):
            record[key] = record[key].strip()
    if (
        normalized_type == "llm_subscription"
        and str(record.get("service") or record.get("provider") or "").lower()
        == "codex"
        and "auth_json_b64" in record
    ):
        _decode_codex_auth_json(record["auth_json_b64"])
    return record


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        raw_records = payload
    elif isinstance(payload, dict):
        raw_records = payload.get("credentials", [])
    else:
        raise ValueError("credential vault must be a JSON object or list")
    if not isinstance(raw_records, list):
        raise ValueError("credential vault 'credentials' must be a list")
    return [_normalize_record(item) for item in raw_records]


#: Service names are short lowercase identifiers (slack, github, anthropic...).
#: Anything else is not a name we issued and must not reach a log surface.
_SERVICE_NAME = re.compile(r"\A[a-z][a-z0-9._-]{0,39}\Z")


def _safe_service_name(value: object) -> str:
    """A service name fit to print, or "" — an allow-list, never a scrub."""
    if not isinstance(value, str):
        return ""
    candidate = value.strip().lower()
    return candidate if _SERVICE_NAME.match(candidate) else ""


def _service(record: dict[str, Any]) -> str:
    return str(record.get("service") or record.get("provider") or "").strip().lower()


def _credential_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Return the logical key used for single-record vault upserts."""
    credential_type = str(record["credential_type"])
    service = _service(record)
    if credential_type == "llm_api_key":
        return (
            credential_type,
            _LLM_API_KEY_ENV_BY_SERVICE.get(service, service),
        )
    if credential_type == "vcs":
        destination = str(record.get("destination") or "").strip()
        return credential_type, service, destination
    return credential_type, service


def _vcs_purposes(record: dict[str, Any]) -> frozenset[str]:
    purpose = record.get("purpose")
    if isinstance(purpose, str) and purpose.strip():
        return frozenset({purpose.strip()})
    purposes = record.get("purposes")
    if isinstance(purposes, list):
        return frozenset(
            str(item).strip()
            for item in purposes
            if str(item).strip()
        )
    return frozenset({"write"})


def _credentials_match(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> bool:
    if _credential_key(existing) != _credential_key(incoming):
        return False
    if incoming["credential_type"] != "vcs":
        return True
    return bool(_vcs_purposes(existing) & _vcs_purposes(incoming))


def _merge_subscription_records(
    existing: list[dict[str, Any]],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    replacement: dict[str, Any] = {}
    for record in reversed(existing):
        replacement.update(record)
    for slot in _SUBSCRIPTION_ALIAS_SLOTS_BY_SERVICE.get(
        _service(incoming), ()
    ):
        if not slot.isdisjoint(incoming):
            for field in slot:
                replacement.pop(field, None)
    replacement.update(incoming)
    return replacement


def _merge_single_record(
    existing: list[dict[str, Any]],
    incoming: dict[str, Any],
) -> list[dict[str, Any]]:
    matching_indexes = [
        index
        for index, record in enumerate(existing)
        if _credentials_match(record, incoming)
    ]
    if not matching_indexes:
        return [*existing, incoming]

    replacement = incoming
    if incoming["credential_type"] == "llm_subscription":
        replacement = _merge_subscription_records(
            [existing[index] for index in matching_indexes],
            incoming,
        )

    first_match = matching_indexes[0]
    matching_set = set(matching_indexes)
    return [
        replacement if index == first_match else record
        for index, record in enumerate(existing)
        if index == first_match or index not in matching_set
    ]


def load_credential_vault(universe_dir: str | Path) -> list[dict[str, Any]]:
    """Load and validate the per-universe vault.

    Missing vaults are treated as empty. Malformed vaults raise ValueError so a
    daemon cannot silently grant or lose authority due to a bad secret file.
    """
    path = credential_vault_path(universe_dir)
    if not path.is_file():
        return []
    payload = None
    malformed = ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        # `UnicodeDecodeError.object` is the whole file too — a second channel
        # with the same consequence as JSONDecodeError.doc, found only because
        # a reviewer tried invalid UTF-8 rather than invalid JSON.
        malformed = "an undecodable byte"
    except json.JSONDecodeError as exc:
        # `exc.doc` is the ENTIRE vault file — every token for every service.
        # Chaining it, or interpolating `exc`, hands the whole thing to any
        # traceback, log, or error collector. Keep only the position, and raise
        # after this handler exits so no chain survives (`from None` clears
        # __cause__ but leaves __context__).
        malformed = f"line {exc.lineno} column {exc.colno}"
    if malformed:
        raise ValueError(f"credential vault is not valid JSON at {malformed}")
    return _records_from_payload(payload)


def _prepare_credential_write(
    universe_dir: str | Path,
    credentials: list[dict[str, Any]] | dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate + merge incoming credentials and return ``(records, summary)``
    WITHOUT touching the vault file.

    Against an existing valid vault, a single record is read-modify-write
    upserted into its logical slot and all matching duplicates collapse at their
    first position. Subscription fields merge; other credential types replace
    the whole slot. Two-or-more records replace the stored list exactly, and an
    empty payload clears it. A malformed existing vault blocks a single upsert.

    The returned ``records`` are what the caller persists as the LAST mutation of
    a deposit (after the owner-row DB commit, via ``_persist_credential_vault_file``)
    so the credential file is never visible before its ownership row is committed.
    The only filesystem access here is a read of the existing vault to compute a
    single-record upsert; nothing is written. The summary is non-secret and
    suitable for logs/status surfaces.
    """
    universe = Path(universe_dir)
    records = _records_from_payload(credentials)
    path = credential_vault_path(universe)
    collapsed_credential_count = 0
    dropped_credential_slots: list[dict[str, Any]] = []
    if len(records) == 1 and path.is_file():
        incoming = records[0]
        existing = load_credential_vault(universe)
        matching = [
            record
            for record in existing
            if _credentials_match(record, incoming)
        ]
        collapsed_credential_count = max(0, len(matching) - 1)
        if incoming["credential_type"] == "vcs":
            dropped_purposes = (
                frozenset().union(*(_vcs_purposes(record) for record in matching))
                - _vcs_purposes(incoming)
            )
            if dropped_purposes:
                dropped_credential_slots.append({
                    "credential_type": "vcs",
                    "service": _service(incoming),
                    "destination": str(
                        incoming.get("destination") or ""
                    ).strip(),
                    "purposes": sorted(dropped_purposes),
                })
        records = _merge_single_record(existing, incoming)
    credential_types = sorted({str(r["credential_type"]) for r in records})
    # Sanitised, not echoed. This summary is explicitly "suitable for logs and
    # status surfaces", and `service` is arbitrary vault content — a review put
    # a live token in that field and read it back out of the summary the
    # deposit script prints under the words "nothing above contains a token".
    # Same class as the credential_type echo fixed one round earlier.
    services = sorted(
        {
            name
            for r in records
            if (name := _safe_service_name(r.get("service") or r.get("provider")))
        }
    )
    summary = {
        "path": str(path),
        "credential_count": len(records),
        "credential_types": credential_types,
        "services": services,
        "collapsed_credential_count": collapsed_credential_count,
        "dropped_credential_slots": dropped_credential_slots,
    }
    return records, summary


def _fsync_file(path: Path) -> None:
    """fsync a file's contents to disk. May raise OSError.

    Opened ``r+b`` (writable): Windows' ``os.fsync`` requires a handle open for
    writing and raises ``EBADF`` on a read-only one. No bytes are written.
    """
    with open(path, "r+b") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    """fsync a directory so a rename inside it is persisted. May raise OSError.

    No-op on Windows, which has no portable directory-fsync via ``os.open`` here.
    """
    if os.name == "nt":
        return
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _post_commit_durability(vault_file: Path, universe: Path) -> None:
    """Best-effort durability AFTER the commit point (fsync file + directory).

    Kept as one seam so the caller can treat any failure here as non-fatal — the
    deposit has already taken effect once the vault file is replaced.
    """
    _fsync_file(vault_file)
    _fsync_directory(universe)


def _persist_credential_vault_file(
    universe_dir: str | Path,
    records: list[dict[str, Any]],
) -> None:
    """Atomically replace the vault file with *records*.

    This is the LAST mutation of a deposit — the owner-row DB commit has already
    landed — so a concurrent unlocked reader never observes a credential before
    its ownership row exists.

    The successful ``Path.replace`` is the COMMIT POINT. Everything BEFORE it (the
    temp write, ``handle.flush``, the replace itself) may raise, and such a
    pre-commit failure leaves the prior file intact (``Path.replace`` is atomic)
    so the caller compensates the owner rows. Everything AFTER it — chmod, fsync
    file + directory, the fd close inside them — is best-effort DURABILITY: the
    new credential is already visible, so a failure there MUST NOT raise (a raise
    would wrongly fail an effective deposit and trigger owner-row compensation);
    it is logged loudly and swallowed.
    """
    universe = Path(universe_dir)
    universe.mkdir(parents=True, exist_ok=True)
    path = credential_vault_path(universe)
    tmp = path.with_name(f"{path.name}.tmp")
    data = (
        json.dumps({"schema_version": 1, "credentials": records}, indent=2, sort_keys=True)
        + "\n"
    )
    # Pre-commit: write the temp file. A write/flush failure here is before the
    # commit point and propagates. The temp fsync is durability only — log loudly
    # on failure but do not abort a deposit whose bytes are already written.
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError as exc:
            logger.warning(
                "credential vault temp fsync failed pre-commit (%s)",
                type(exc).__name__,
            )
    _chmod_best_effort(tmp, 0o600)

    # COMMIT POINT: the atomic rename. A failure here leaves the prior file intact.
    tmp.replace(path)

    # Past the commit point: DURABILITY ONLY. Never raise — the deposit already
    # took effect, so a durability failure must not fail it or trigger compensation.
    _chmod_best_effort(path, 0o600)
    try:
        _post_commit_durability(path, universe)
    except Exception as exc:  # noqa: BLE001 - durability is best-effort post-commit
        logger.warning(
            "credential vault durability flush failed after commit (%s); "
            "deposit already took effect",
            type(exc).__name__,
        )


def _restore_owner_rows(
    conn: sqlite3.Connection,
    universe_id: str,
    prior_rows: list[Any],
) -> None:
    """Compensating transaction: restore the owner rows for *universe_id* to
    *prior_rows*.

    Used only when the owner-row DB change already committed but the subsequent
    vault-file replace failed, so no committed-but-ineffective ownership survives.
    """
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        "DELETE FROM llm_credential_deposit_owners WHERE universe_id = ?",
        (universe_id,),
    )
    for row in prior_rows:
        conn.execute(
            """
            INSERT INTO llm_credential_deposit_owners (
                universe_id, service, owner_user_id
            ) VALUES (?, ?, ?)
            """,
            (universe_id, str(row[0]), str(row[1])),
        )
    conn.commit()


def write_credential_vault(
    universe_dir: str | Path,
    credentials: list[dict[str, Any]] | dict[str, Any],
    *,
    owner_user_id: str | None = None,
    universe_id: str | None = None,
) -> dict[str, Any]:
    """Write while excluding launches and optionally record depositor ownership.

    ``owner_user_id`` is trusted transport state, never a vault-record field.
    Omitting it leaves new LLM subscription material unowned and therefore
    ineligible for serving authority.
    """

    from tinyassets.provider_assignment import provider_assignment_admission
    from tinyassets.storage import db_path

    universe = Path(universe_dir).resolve(strict=False)
    owner = (owner_user_id or "").strip()
    uid = (universe_id or universe.name).strip()
    if owner_user_id is not None and not owner:
        raise ValueError("credential owner must be a non-empty server principal")
    if uid != universe.name:
        raise ValueError("credential universe does not match its canonical directory")

    # Validate the payload BEFORE acquiring the exclusive lock. Entering the lock
    # creates the universe directory AND the admission lock file
    # (provider_assignment.py), so validating first means a malformed deposit
    # (e.g. bad Codex base64) mutates NOTHING — no directory, no lock, no schema,
    # no vault file. Pure, side-effect-free; the merge below re-runs it.
    _records_from_payload(credentials)

    with provider_assignment_admission().exclusive(universe):
        conn = sqlite3.connect(db_path(universe.parent), isolation_level=None)
        try:
            _ensure_llm_deposit_owner_schema(conn)
            if owner:
                existing = conn.execute(
                    """
                    SELECT DISTINCT owner_user_id
                      FROM llm_credential_deposit_owners
                     WHERE universe_id = ?
                    """,
                    (uid,),
                ).fetchall()
                if any(str(row[0]) != owner for row in existing):
                    raise PermissionError(
                        "credential ownership transfer requires a dedicated flow"
                    )

            # Compute the final merged records + summary IN MEMORY. The vault file
            # is the LAST mutation (below), never written before the owner-row
            # commit, so a concurrent unlocked reader can never observe a
            # credential before its ownership row exists.
            final_records, summary = _prepare_credential_write(universe, credentials)
            services = {
                _service(record)
                for record in final_records
                if record.get("credential_type") == "llm_subscription"
                and _service(record) in {"claude", "codex"}
            }

            # Snapshot the prior owner rows so a (rare) file-replace failure AFTER
            # the DB commit can be compensated below.
            prior_owner_rows = conn.execute(
                """
                SELECT service, owner_user_id
                  FROM llm_credential_deposit_owners
                 WHERE universe_id = ?
                """,
                (uid,),
            ).fetchall()

            # 1. Owner-row DB transaction FIRST, and commit it.
            conn.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in services)
            if services:
                conn.execute(
                    f"""
                    DELETE FROM llm_credential_deposit_owners
                     WHERE universe_id = ? AND service NOT IN ({placeholders})
                    """,
                    (uid, *sorted(services)),
                )
            else:
                conn.execute(
                    "DELETE FROM llm_credential_deposit_owners WHERE universe_id = ?",
                    (uid,),
                )
            if owner:
                for service_name in services:
                    conn.execute(
                        """
                        INSERT INTO llm_credential_deposit_owners (
                            universe_id, service, owner_user_id
                        ) VALUES (?, ?, ?)
                        ON CONFLICT(universe_id, service) DO UPDATE SET
                            owner_user_id = excluded.owner_user_id
                        """,
                        (uid, service_name, owner),
                    )
            conn.commit()

            # 2. ONLY after the DB commit, atomically replace the vault file.
            #    _persist_credential_vault_file raises ONLY for a pre-commit failure
            #    (the vault file was NOT replaced — Path.replace is atomic — so the
            #    prior file is intact); it never raises once the file is visible.
            try:
                _persist_credential_vault_file(universe, final_records)
            except BaseException as persist_error:
                # 3. Pre-commit failure: the file did not change. Compensate by
                #    restoring the prior owner rows so no committed-but-ineffective
                #    ownership survives, then re-raise.
                try:
                    _restore_owner_rows(conn, uid, prior_owner_rows)
                except Exception as compensation_error:  # noqa: BLE001
                    # Double failure: the file write failed AND the owner-row
                    # commit could not be undone. Fail loud, chaining both — do
                    # not swallow. Residual: a committed owner row with no vault
                    # file is a benign phantom (the owner cannot act — there is no
                    # credential — and a re-deposit reconciles).
                    raise compensation_error from persist_error
                raise
            return summary
        finally:
            conn.close()


@dataclass(frozen=True, slots=True)
class LLMCredentialCustodyReference:
    """Secret-free credential identity issued by the vault custody owner."""

    reference_id: str
    owner_user_id: str
    universe_id: str
    service: str
    generation: int
    reference_digest: str
    _record_digest: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class LLMCredentialSnapshot:
    """One launch's rotation-stable, sandbox-read-only credential copy.

    This blocks source-rotation races and sandbox-interior writes. It does not
    defend against same-UID mutation; those processes remain inside the
    credential-vault trust boundary.
    """

    # At-rest/operator-blind sealing belongs to credential-vault task 1.8.
    directory: Path = field(repr=False)
    service: str
    generation: int
    reference_digest: str
    _directory_identity: tuple[int, int] = field(repr=False)
    _root_directory: Path = field(repr=False)
    _root_identity: tuple[int, int] = field(repr=False)


def _canonical_digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _ensure_llm_deposit_owner_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_credential_deposit_owners (
            universe_id TEXT NOT NULL,
            service TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            PRIMARY KEY (universe_id, service)
        )
        """
    )


def _read_credential_material(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise PermissionError("exactly one usable subscription credential is required")
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise PermissionError("exactly one usable subscription credential is required")
    material = path.read_bytes()
    after = path.stat(follow_symlinks=False)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after:
        raise PermissionError("credential material changed during validation")
    return material


def _subscription_material(
    universe_dir: Path,
    service: str,
    record: dict[str, Any],
) -> bytes:
    if service == "codex":
        encoded = record.get("auth_json_b64")
        if isinstance(encoded, str) and encoded.strip():
            return _decode_codex_auth_json(encoded)
        home = _codex_home_from_record(record, universe_dir)
        if home is None:
            home = universe_dir / CREDENTIAL_ARTIFACT_DIR / "codex"
        auth_file = _contained_path(universe_dir, str(home / "auth.json"))
        if auth_file is None:
            raise PermissionError("exactly one usable subscription credential is required")
        return _read_credential_material(auth_file)
    if service == "claude":
        token = _secret_value(record, "oauth_token", "claude_code_oauth_token")
        if token:
            return token.encode("utf-8")
        config_dir = _claude_config_dir_from_record(record, universe_dir)
        credential_file = (
            _contained_path(universe_dir, str(config_dir / ".credentials.json"))
            if config_dir is not None
            else None
        )
        if credential_file is None:
            raise PermissionError("exactly one usable subscription credential is required")
        return _read_credential_material(credential_file)
    raise PermissionError("exactly one usable subscription credential is required")


def _subscription_material_digest(
    universe_dir: Path,
    service: str,
    record: dict[str, Any],
) -> str:
    material = _subscription_material(universe_dir, service, record)
    return "sha256:" + hashlib.sha256(material).hexdigest()


def _subscription_record_digest(
    universe_dir: Path,
    service: str,
    record: dict[str, Any],
) -> str:
    return _canonical_digest({
        "material_digest": _subscription_material_digest(universe_dir, service, record),
        "record": record,
    })


def _contained_path(universe_dir: Path, raw: object) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    root = universe_dir.resolve(strict=True)
    candidate = Path(raw.strip())
    if not candidate.is_absolute():
        candidate = root / candidate
    lexical = Path(os.path.abspath(candidate))
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        return None
    current = root
    for part in relative.parts:
        current = current / part
        is_junction = getattr(current, "is_junction", None)
        if current.exists() and (
            current.is_symlink()
            or (callable(is_junction) and is_junction())
            or (
                os.name == "nt"
                and os.path.normcase(os.path.realpath(current))
                != os.path.normcase(os.path.abspath(current))
            )
        ):
            return None
    resolved = lexical.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _usable_subscription_record(
    universe_dir: Path,
    service: str,
) -> dict[str, Any]:
    vault_path = credential_vault_path(universe_dir)
    if vault_path.is_symlink() or not vault_path.is_file():
        raise PermissionError("exactly one usable subscription credential is required")
    records = _llm_records(universe_dir, service)
    if len(records) != 1:
        raise PermissionError("exactly one usable subscription credential is required")
    record = records[0]
    path_fields = (
        ("codex_home", "home", "auth_home", "path", "auth_json_path")
        if service == "codex"
        else ("claude_config_dir", "config_dir", "path", "claude_home", "home", "auth_home")
    )
    resolved_paths = [
        _contained_path(universe_dir, record.get(key))
        for key in path_fields
        if isinstance(record.get(key), str) and str(record.get(key)).strip()
    ]
    if any(path is None for path in resolved_paths):
        raise PermissionError("exactly one usable subscription credential is required")
    if service == "codex":
        encoded = record.get("auth_json_b64")
        if isinstance(encoded, str) and encoded.strip():
            _decode_codex_auth_json(encoded)
            return record
        home = _codex_home_from_record(record, universe_dir)
        if home is None:
            home = universe_dir / CREDENTIAL_ARTIFACT_DIR / "codex"
        contained_home = _contained_path(universe_dir, str(home))
        if contained_home is None or not (contained_home / "auth.json").is_file():
            raise PermissionError("exactly one usable subscription credential is required")
        return record
    if service == "claude":
        if _secret_value(record, "oauth_token", "claude_code_oauth_token"):
            return record
        config_dir = _claude_config_dir_from_record(record, universe_dir)
        contained_dir = (
            _contained_path(universe_dir, str(config_dir))
            if config_dir is not None
            else None
        )
        if contained_dir is None or not contained_dir.is_dir():
            raise PermissionError("exactly one usable subscription credential is required")
        return record
    raise PermissionError("exactly one usable subscription credential is required")


def _custody_reference_digest(
    *,
    reference_id: str,
    owner_user_id: str,
    universe_id: str,
    service: str,
    generation: int,
    record_digest: str,
) -> str:
    return _canonical_digest({
        "generation": generation,
        "owner_user_id": owner_user_id,
        "record_digest": record_digest,
        "reference_id": reference_id,
        "schema_version": 1,
        "service": service,
        "universe_id": universe_id,
    })


def adopt_llm_subscription_custody(
    conn: sqlite3.Connection,
    *,
    universe_dir: str | Path,
    owner_user_id: str,
    universe_id: str,
    service: str,
) -> LLMCredentialCustodyReference:
    """Adopt or rotate one current vault record under an existing transaction."""

    if not isinstance(conn, sqlite3.Connection) or not conn.in_transaction:
        raise ValueError("LLM custody adoption requires an active SQLite transaction")
    owner = owner_user_id.strip()
    uid = universe_id.strip()
    canonical_service = service.strip().lower()
    if not owner or not uid or canonical_service not in {"claude", "codex"}:
        raise ValueError("LLM custody root is invalid")
    universe = Path(universe_dir)
    record = _usable_subscription_record(universe, canonical_service)
    record_digest = _subscription_record_digest(universe, canonical_service, record)
    _ensure_llm_deposit_owner_schema(conn)
    depositor = conn.execute(
        """
        SELECT owner_user_id FROM llm_credential_deposit_owners
         WHERE universe_id = ? AND service = ?
        """,
        (uid, canonical_service),
    ).fetchone()
    if depositor is None or str(depositor[0]) != owner:
        raise PermissionError("caller is not the server-recorded credential owner")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_credential_custody (
            reference_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            universe_id TEXT NOT NULL,
            service TEXT NOT NULL,
            generation INTEGER NOT NULL CHECK (generation >= 1),
            record_digest TEXT NOT NULL,
            reference_digest TEXT NOT NULL,
            UNIQUE (owner_user_id, universe_id, service)
        )
        """
    )
    row = conn.execute(
        """
        SELECT reference_id, generation, record_digest, reference_digest
          FROM llm_credential_custody
         WHERE owner_user_id = ? AND universe_id = ? AND service = ?
        """,
        (owner, uid, canonical_service),
    ).fetchone()
    if row is None:
        reference_id = f"llm_credential_{secrets.token_hex(16)}"
        generation = 1
    else:
        reference_id = str(row[0])
        if str(row[2]) == record_digest:
            return LLMCredentialCustodyReference(
                reference_id=reference_id,
                owner_user_id=owner,
                universe_id=uid,
                service=canonical_service,
                generation=int(row[1]),
                reference_digest=str(row[3]),
                _record_digest=record_digest,
            )
        generation = int(row[1]) + 1
    reference_digest = _custody_reference_digest(
        reference_id=reference_id,
        owner_user_id=owner,
        universe_id=uid,
        service=canonical_service,
        generation=generation,
        record_digest=record_digest,
    )
    conn.execute(
        """
        INSERT INTO llm_credential_custody (
            reference_id, owner_user_id, universe_id, service, generation,
            record_digest, reference_digest
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(owner_user_id, universe_id, service) DO UPDATE SET
            generation = excluded.generation,
            record_digest = excluded.record_digest,
            reference_digest = excluded.reference_digest
        """,
        (
            reference_id,
            owner,
            uid,
            canonical_service,
            generation,
            record_digest,
            reference_digest,
        ),
    )
    return LLMCredentialCustodyReference(
        reference_id=reference_id,
        owner_user_id=owner,
        universe_id=uid,
        service=canonical_service,
        generation=generation,
        reference_digest=reference_digest,
        _record_digest=record_digest,
    )


def current_llm_subscription_custody(
    conn: sqlite3.Connection,
    *,
    universe_dir: str | Path,
    owner_user_id: str,
    universe_id: str,
    service: str,
) -> LLMCredentialCustodyReference | None:
    """Reload and verify the current opaque reference without adopting state."""

    _ensure_llm_deposit_owner_schema(conn)
    recorded_owner = conn.execute(
        """
        SELECT owner_user_id FROM llm_credential_deposit_owners
         WHERE universe_id = ? AND service = ?
        """,
        (universe_id.strip(), service.strip().lower()),
    ).fetchone()
    if recorded_owner is None or str(recorded_owner[0]) != owner_user_id.strip():
        return None
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_credential_custody (
            reference_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            universe_id TEXT NOT NULL,
            service TEXT NOT NULL,
            generation INTEGER NOT NULL CHECK (generation >= 1),
            record_digest TEXT NOT NULL,
            reference_digest TEXT NOT NULL,
            UNIQUE (owner_user_id, universe_id, service)
        )
        """
    )
    row = conn.execute(
        """
        SELECT reference_id, generation, record_digest, reference_digest
          FROM llm_credential_custody
         WHERE owner_user_id = ? AND universe_id = ? AND service = ?
        """,
        (owner_user_id.strip(), universe_id.strip(), service.strip().lower()),
    ).fetchone()
    if row is None:
        return None
    try:
        record = _usable_subscription_record(Path(universe_dir), service.strip().lower())
    except (PermissionError, ValueError, OSError):
        return None
    record_digest = _subscription_record_digest(
        Path(universe_dir), service.strip().lower(), record,
    )
    expected = _custody_reference_digest(
        reference_id=str(row[0]),
        owner_user_id=owner_user_id.strip(),
        universe_id=universe_id.strip(),
        service=service.strip().lower(),
        generation=int(row[1]),
        record_digest=record_digest,
    )
    if record_digest != str(row[2]) or expected != str(row[3]):
        return None
    return LLMCredentialCustodyReference(
        reference_id=str(row[0]),
        owner_user_id=owner_user_id.strip(),
        universe_id=universe_id.strip(),
        service=service.strip().lower(),
        generation=int(row[1]),
        reference_digest=str(row[3]),
        _record_digest=record_digest,
    )


def _is_snapshot_reparse_point(file_stat: os.stat_result) -> bool:
    if stat.S_ISLNK(file_stat.st_mode):
        return True
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _snapshot_file_identity(file_stat: os.stat_result) -> tuple[int, int]:
    device = getattr(file_stat, "st_dev", None)
    inode = getattr(file_stat, "st_ino", None)
    if type(device) is not int or type(inode) is not int or inode == 0:
        raise PermissionError("credential snapshot filesystem identity is unavailable")
    return device, inode


def _plain_snapshot_directory(path: Path) -> tuple[int, int]:
    try:
        file_stat = path.lstat()
        resolved = Path(os.path.realpath(path))
        resolved_stat = resolved.stat()
    except OSError as exc:
        raise PermissionError("credential snapshot directory is unavailable") from exc
    if (
        _is_snapshot_reparse_point(file_stat)
        or not stat.S_ISDIR(file_stat.st_mode)
        or os.path.normcase(os.path.abspath(path))
        != os.path.normcase(os.path.abspath(resolved))
    ):
        raise PermissionError("credential snapshot directory must be a plain directory")
    identity = _snapshot_file_identity(file_stat)
    if _snapshot_file_identity(resolved_stat) != identity:
        raise PermissionError("credential snapshot directory identity is unstable")
    get_effective_uid = getattr(os, "geteuid", None)
    if callable(get_effective_uid) and file_stat.st_uid != get_effective_uid():
        raise PermissionError("credential snapshot directory has another owner")
    return identity


def _prepare_snapshot_root(universe: Path) -> tuple[Path, tuple[int, int]]:
    runtime_dir = universe / ".runtime"
    snapshot_root = runtime_dir / "provider-launch-credentials"
    for directory in (runtime_dir, snapshot_root):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise PermissionError("credential snapshot directory cannot be created") from exc
        identity = _plain_snapshot_directory(directory)
        _chmod_best_effort(directory, 0o700)
        if _plain_snapshot_directory(directory) != identity:
            raise PermissionError("credential snapshot directory identity changed")
    return snapshot_root, _plain_snapshot_directory(snapshot_root)


def _create_snapshot_directory(
    snapshot_root: Path,
    root_identity: tuple[int, int],
) -> tuple[Path, tuple[int, int]]:
    for _attempt in range(16):
        if _plain_snapshot_directory(snapshot_root) != root_identity:
            raise PermissionError("credential snapshot root identity changed")
        directory = snapshot_root / f"codex-{secrets.token_hex(16)}"
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            continue
        except OSError as exc:
            raise PermissionError("credential snapshot directory cannot be created") from exc
        identity = _plain_snapshot_directory(directory)
        if _plain_snapshot_directory(snapshot_root) != root_identity:
            raise PermissionError("credential snapshot root identity changed")
        return directory, identity
    raise PermissionError("credential snapshot directory name cannot be reserved")


def _write_exclusive_snapshot_file(path: Path, contents: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise PermissionError("credential snapshot file cannot be created") from exc
    try:
        opened = os.fstat(descriptor)
        current = path.lstat()
        if (
            _is_snapshot_reparse_point(current)
            or not stat.S_ISREG(current.st_mode)
            or getattr(current, "st_nlink", 1) != 1
            or _snapshot_file_identity(opened) != _snapshot_file_identity(current)
        ):
            raise PermissionError("credential snapshot file identity is unstable")
        remaining = memoryview(contents)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("credential snapshot file write made no progress")
            remaining = remaining[written:]
    finally:
        os.close(descriptor)
    _chmod_best_effort(path, 0o400)


def _remove_snapshot_tree(
    path: Path,
    *,
    expected_identity: tuple[int, int] | None = None,
) -> None:
    file_stat = path.lstat()
    if expected_identity is not None and _snapshot_file_identity(file_stat) != expected_identity:
        raise PermissionError("credential snapshot path identity changed")
    if _is_snapshot_reparse_point(file_stat):
        if stat.S_ISDIR(file_stat.st_mode):
            path.rmdir()
        else:
            path.unlink()
        return
    if stat.S_ISDIR(file_stat.st_mode):
        with os.scandir(path) as entries:
            children = [Path(entry.path) for entry in entries]
        for child in children:
            _remove_snapshot_tree(child)
        _chmod_best_effort(path, 0o700)
        path.rmdir()
        return
    _chmod_best_effort(path, 0o600)
    path.unlink()


def _locate_tracked_snapshot(snapshot: LLMCredentialSnapshot) -> Path | None:
    try:
        current = snapshot.directory.lstat()
    except FileNotFoundError:
        current = None
    except OSError:
        current = None
    if (
        current is not None
        and not _is_snapshot_reparse_point(current)
        and stat.S_ISDIR(current.st_mode)
        and _snapshot_file_identity(current) == snapshot._directory_identity
    ):
        return snapshot.directory

    logger.warning(
        "credential snapshot path identity changed; locating tracked directory"
    )
    try:
        if (
            _plain_snapshot_directory(snapshot._root_directory)
            != snapshot._root_identity
        ):
            return None
        with os.scandir(snapshot._root_directory) as entries:
            for entry in entries:
                try:
                    entry_stat = Path(entry.path).lstat()
                    identity = _snapshot_file_identity(entry_stat)
                except (OSError, PermissionError):
                    continue
                if identity != snapshot._directory_identity:
                    continue
                if (
                    _is_snapshot_reparse_point(entry_stat)
                    or not stat.S_ISDIR(entry_stat.st_mode)
                ):
                    return None
                return Path(entry.path)
    except (OSError, PermissionError):
        return None
    return None


def cleanup_llm_credential_snapshot(snapshot: LLMCredentialSnapshot | None) -> None:
    """Best-effort identity-anchored snapshot removal; never raise."""

    if snapshot is None:
        return
    try:
        tracked_directory = _locate_tracked_snapshot(snapshot)
        if tracked_directory is not None:
            _remove_snapshot_tree(
                tracked_directory,
                expected_identity=snapshot._directory_identity,
            )
    except Exception:  # noqa: BLE001 - cleanup must never mask launch outcome
        logger.warning("credential snapshot cleanup could not remove tracked directory")


def snapshot_llm_subscription_credential(
    *,
    universe_dir: str | Path,
    custody: LLMCredentialCustodyReference,
) -> LLMCredentialSnapshot:
    """Copy current credential bytes into one immutable launch directory."""

    universe = Path(universe_dir).resolve(strict=True)
    if custody.universe_id != universe.name or custody.service not in ("codex", "claude"):
        raise PermissionError("credential snapshot root is not current")
    record = _usable_subscription_record(universe, custody.service)
    material = _subscription_material(universe, custody.service, record)
    material_digest = "sha256:" + hashlib.sha256(material).hexdigest()
    snapshot_record_digest = _canonical_digest({
        "material_digest": material_digest,
        "record": record,
    })
    snapshot_reference_digest = _custody_reference_digest(
        reference_id=custody.reference_id,
        owner_user_id=custody.owner_user_id,
        universe_id=custody.universe_id,
        service=custody.service,
        generation=custody.generation,
        record_digest=snapshot_record_digest,
    )
    if (
        snapshot_record_digest != custody._record_digest
        or snapshot_reference_digest != custody.reference_digest
    ):
        raise PermissionError("credential changed before launch snapshot")

    snapshot_root, root_identity = _prepare_snapshot_root(universe)
    directory, directory_identity = _create_snapshot_directory(
        snapshot_root,
        root_identity,
    )
    snapshot = LLMCredentialSnapshot(
        directory=directory,
        service=custody.service,
        generation=custody.generation,
        reference_digest=snapshot_reference_digest,
        _directory_identity=directory_identity,
        _root_directory=snapshot_root,
        _root_identity=root_identity,
    )
    try:
        auth_file = directory / "auth.json"
        if _plain_snapshot_directory(directory) != directory_identity:
            raise PermissionError("credential snapshot directory identity changed")
        _write_exclusive_snapshot_file(auth_file, material)
        config_file = directory / "config.toml"
        _write_exclusive_snapshot_file(
            config_file,
            b'cli_auth_credentials_store = "file"\n',
        )
        lock_file = directory / ".lock"
        _write_exclusive_snapshot_file(lock_file, b"")
        copied_material = _read_credential_material(auth_file)
        copied_record_digest = _canonical_digest({
            "material_digest": (
                "sha256:" + hashlib.sha256(copied_material).hexdigest()
            ),
            "record": record,
        })
        copied_reference_digest = _custody_reference_digest(
            reference_id=custody.reference_id,
            owner_user_id=custody.owner_user_id,
            universe_id=custody.universe_id,
            service=custody.service,
            generation=custody.generation,
            record_digest=copied_record_digest,
        )
        if copied_reference_digest != custody.reference_digest:
            raise PermissionError("credential snapshot custody digest disagrees")
        _chmod_best_effort(directory, 0o700)
        return snapshot
    except BaseException:
        cleanup_llm_credential_snapshot(snapshot)
        raise


def _purpose_matches(record: dict[str, Any], purpose: str) -> bool:
    return purpose.strip() in _vcs_purposes(record)


def _secret_value(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    b64 = record.get("token_b64") or record.get("secret_b64")
    if isinstance(b64, str) and b64.strip():
        decoded = None
        try:
            decoded = base64.b64decode(b64.strip()).decode("utf-8").strip()
        except Exception:  # noqa: BLE001
            # Not chained, and raised outside the handler. A UnicodeDecodeError
            # here carries `.object` — the DECODED credential bytes — so
            # chaining published the very token this was decoding.
            decoded = None
        if decoded is None:
            raise ValueError(f"credential {keys[0]} base64 decode failed")
        return decoded
    return ""


def resolve_github_token(
    universe_dir: str | Path | None,
    destination: str,
    *,
    purpose: str = "write",
) -> str:
    """Return a GitHub token from the per-universe vault, or an empty string."""
    if universe_dir is None:
        return ""
    wanted_destination = destination.strip()
    if not wanted_destination:
        return ""
    for record in load_credential_vault(universe_dir):
        if record.get("credential_type") != "vcs":
            continue
        if _service(record) != "github":
            continue
        if str(record.get("destination") or "").strip() != wanted_destination:
            continue
        if not _purpose_matches(record, purpose):
            continue
        return _secret_value(record, "token", "access_token")
    return ""


def resolve_slack_token(
    universe_dir: str | Path | None,
    connection_id: str,
) -> str:
    """Return a Slack bot token for one connection, or an empty string.

    Mirrors :func:`resolve_github_token`: the record must be a ``social``
    credential for service ``slack`` whose ``destination`` is the exact
    connection id. Scoping to the connection — rather than to the universe —
    keeps one universe's Slack workspaces separable, so a second connection
    cannot be served with the first one's token.

    The caller is responsible for the vault-first / never-fall-through-to-env
    rule; this returns only what the vault holds.
    """
    if universe_dir is None:
        return ""
    wanted = connection_id.strip()
    if not wanted:
        return ""
    for record in load_credential_vault(universe_dir):
        if record.get("credential_type") != "social":
            continue
        if _service(record) != "slack":
            continue
        if str(record.get("destination") or "").strip() != wanted:
            continue
        return _secret_value(record, "bot_token", "token", "access_token")
    return ""


def resolve_slack_app_token(
    universe_dir: str | Path | None,
    connection_id: str,
) -> str:
    """Return a Slack **app-level** token for one connection, or an empty string.

    A Slack connection needs two different credentials, and they are not
    interchangeable: the bot token (``xoxb-``) posts messages, while the
    app-level token (``xapp-``, scope ``connections:write``) is the only one
    that can open a Socket Mode connection. Both live on the same vault record
    because they come from the same app install.

    Deliberately does NOT fall back to ``bot_token``/``token``. Handing a bot
    token to `apps.connections.open` fails with an opaque Slack error, and a
    silent fallback would turn "the app token was never deposited" into a
    mystery instead of the plain answer it is.
    """
    if universe_dir is None:
        return ""
    wanted = connection_id.strip()
    if not wanted:
        return ""
    for record in load_credential_vault(universe_dir):
        if record.get("credential_type") != "social":
            continue
        if _service(record) != "slack":
            continue
        if str(record.get("destination") or "").strip() != wanted:
            continue
        return _secret_value(record, "app_token", "app_level_token")
    return ""


def _llm_records(universe_dir: str | Path | None, service: str) -> list[dict[str, Any]]:
    if universe_dir is None:
        return []
    service_key = service.strip().lower()
    return [
        record
        for record in load_credential_vault(universe_dir)
        if record.get("credential_type") == "llm_subscription"
        and _service(record) == service_key
    ]


def _codex_home_from_record(record: dict[str, Any], universe_dir: Path) -> Path | None:
    for key in ("codex_home", "home", "auth_home", "path"):
        resolved = _as_path(record.get(key), universe_dir)
        if resolved is not None:
            return resolved
    auth_path = _as_path(record.get("auth_json_path"), universe_dir)
    if auth_path is not None:
        return auth_path.parent
    return None


def resolve_codex_home(universe_dir: str | Path | None) -> Path | None:
    """Return the configured CODEX_HOME path for this universe, if any."""
    if universe_dir is None:
        return None
    universe = Path(universe_dir)
    for record in _llm_records(universe, "codex"):
        home = _codex_home_from_record(record, universe)
        if home is not None:
            return home
    materialized = universe / CREDENTIAL_ARTIFACT_DIR / "codex"
    if (materialized / "auth.json").is_file():
        return materialized
    return None


def ensure_codex_home_from_vault(universe_dir: str | Path | None) -> Path | None:
    """Materialize any vault-backed Codex auth bundle and return CODEX_HOME."""
    if universe_dir is None:
        return None
    universe = Path(universe_dir)
    for record in _llm_records(universe, "codex"):
        home = _codex_home_from_record(record, universe) or _secret_artifact_dir(universe, "codex")
        home.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(home, 0o700)
        auth_b64 = record.get("auth_json_b64")
        auth_file = home / "auth.json"
        if isinstance(auth_b64, str) and auth_b64.strip():
            auth_bytes = _decode_codex_auth_json(auth_b64)
            if not auth_file.exists() or auth_file.read_bytes() != auth_bytes:
                tmp = auth_file.with_name("auth.json.tmp")
                tmp.write_bytes(auth_bytes)
                _chmod_best_effort(tmp, 0o600)
                tmp.replace(auth_file)
                _chmod_best_effort(auth_file, 0o600)
        config_file = home / "config.toml"
        if auth_file.exists() and not config_file.exists():
            config_file.write_text(
                'cli_auth_credentials_store = "file"\n',
                encoding="utf-8",
            )
            _chmod_best_effort(config_file, 0o600)
        return home
    return resolve_codex_home(universe)


def codex_subscription_auth_available(universe_dir: str | Path | None) -> bool:
    """Return True when the vault can provide or points at Codex auth."""
    home = ensure_codex_home_from_vault(universe_dir)
    return bool(home and (home / "auth.json").is_file())


def _claude_config_dir_from_record(record: dict[str, Any], universe_dir: Path) -> Path | None:
    for key in ("claude_config_dir", "config_dir", "path"):
        resolved = _as_path(record.get(key), universe_dir)
        if resolved is not None:
            return resolved
    for key in ("claude_home", "home", "auth_home"):
        home = _as_path(record.get(key), universe_dir)
        if home is not None:
            return home / ".claude"
    return None


def resolve_claude_config_dir(universe_dir: str | Path | None) -> Path | None:
    """Return the CLAUDE_CONFIG_DIR path for this universe, if any."""
    if universe_dir is None:
        return None
    universe = Path(universe_dir)
    for record in _llm_records(universe, "claude"):
        config_dir = _claude_config_dir_from_record(record, universe)
        if config_dir is not None:
            return config_dir
    materialized = universe / CREDENTIAL_ARTIFACT_DIR / "claude"
    if materialized.is_dir():
        return materialized
    return None


def ensure_claude_config_dir_from_vault(universe_dir: str | Path | None) -> Path | None:
    """Create the configured Claude config directory and return it."""
    if universe_dir is None:
        return None
    universe = Path(universe_dir)
    for record in _llm_records(universe, "claude"):
        config_dir = _claude_config_dir_from_record(record, universe)
        if config_dir is None:
            config_dir = _secret_artifact_dir(universe, "claude")
        config_dir.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(config_dir, 0o700)
        return config_dir
    return resolve_claude_config_dir(universe)


def resolve_claude_home(universe_dir: str | Path | None) -> Path | None:
    """Deprecated compatibility: return CLAUDE_CONFIG_DIR's parent."""
    config_dir = resolve_claude_config_dir(universe_dir)
    return config_dir.parent if config_dir is not None else None


def ensure_claude_home_from_vault(universe_dir: str | Path | None) -> Path | None:
    """Deprecated compatibility: create CLAUDE_CONFIG_DIR and return parent."""
    config_dir = ensure_claude_config_dir_from_vault(universe_dir)
    return config_dir.parent if config_dir is not None else None


def resolve_claude_oauth_token(universe_dir: str | Path | None) -> str:
    """Return a Claude subscription OAuth token from the vault, if present."""
    for record in _llm_records(universe_dir, "claude"):
        return _secret_value(record, "oauth_token", "claude_code_oauth_token")
    return ""


def claude_subscription_auth_available(universe_dir: str | Path | None) -> bool:
    """Return True when the vault provides a Claude subscription auth route."""
    if resolve_claude_oauth_token(universe_dir):
        return True
    config_dir = ensure_claude_config_dir_from_vault(universe_dir)
    return bool(config_dir and config_dir.is_dir())


def supported_llm_api_key_services() -> frozenset[str]:
    """Services a BYO ``llm_api_key`` deposit may target.

    Only these reach a CLI-subprocess provider via the vault env overlay; a
    deposit for any other service would never inject and the founder's engine
    would silently not run (validate at deposit time — Hard Rule #8)."""
    return frozenset(_LLM_API_KEY_ENV_BY_SERVICE)


def resolve_llm_api_key(
    universe_dir: str | Path | None, env_var: str
) -> str:
    """Return a deposited BYO API key whose ``service`` maps to *env_var*, or ''.

    Scans ``llm_api_key`` vault records; a record matches when its ``service``
    resolves (via ``_LLM_API_KEY_ENV_BY_SERVICE``) to the requested provider env
    var. This is the founder's BYO-engine path — the deposited key is injected
    into the CLI subprocess env so ``claude -p`` / ``codex exec`` authenticate
    with the founder's own key instead of the platform's subscription.
    """
    if universe_dir is None:
        return ""
    for record in load_credential_vault(universe_dir):
        if record.get("credential_type") != "llm_api_key":
            continue
        service = _service(record)
        if _LLM_API_KEY_ENV_BY_SERVICE.get(service) != env_var:
            continue
        return _secret_value(record, "api_key", "key", "token")
    return ""


def provider_auth_env_overrides(
    universe_dir: str | Path | None,
    provider_name: str,
) -> dict[str, str]:
    """Return subprocess env overrides for a CLI-subprocess provider.

    Composes subscription auth (CODEX_HOME / CLAUDE_CONFIG_DIR) with an optional
    founder-deposited BYO API key (OPENAI_API_KEY / ANTHROPIC_API_KEY). The key
    is overlaid here, AFTER ``subprocess_env_without_api_keys`` has stripped the
    process-global keys, so a per-universe key never leaks across universes and
    the platform default is not exposed to a BYO-key universe.
    """
    provider = provider_name.strip()
    if provider == "codex":
        overrides: dict[str, str] = {}
        codex_home = ensure_codex_home_from_vault(universe_dir)
        if codex_home:
            overrides["CODEX_HOME"] = str(codex_home)
        api_key = resolve_llm_api_key(universe_dir, "OPENAI_API_KEY")
        if api_key:
            overrides["OPENAI_API_KEY"] = api_key
        return overrides
    if provider == "claude-code":
        overrides = {}
        claude_config_dir = ensure_claude_config_dir_from_vault(universe_dir)
        if claude_config_dir:
            overrides["CLAUDE_CONFIG_DIR"] = str(claude_config_dir)
        oauth_token = resolve_claude_oauth_token(universe_dir)
        if oauth_token:
            overrides["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
        api_key = resolve_llm_api_key(universe_dir, "ANTHROPIC_API_KEY")
        if api_key:
            overrides["ANTHROPIC_API_KEY"] = api_key
        return overrides
    return {}


def resolve_universe_from_env(env: dict[str, str] | None = None) -> Path | None:
    """Resolve the active universe path from env, if one is explicitly bound."""
    source = os.environ if env is None else env
    value = source.get("TINYASSETS_UNIVERSE", "").strip()
    return Path(value) if value else None


def apply_provider_auth_env(
    env: dict[str, str],
    provider_name: str,
    *,
    universe_dir: str | Path | None = None,
) -> dict[str, str]:
    """Overlay per-universe subscription auth settings onto *env*."""
    resolved_universe = (
        Path(universe_dir)
        if universe_dir is not None
        else resolve_universe_from_env(env)
    )
    if resolved_universe is None:
        return env
    try:
        env.update(provider_auth_env_overrides(resolved_universe, provider_name))
    except ValueError:
        raise
    return env
