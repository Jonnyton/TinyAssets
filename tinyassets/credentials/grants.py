"""Opaque, job-scoped broker grants (the S3 executor-boundary primitive).

S3 runs a tenant's job in an ISOLATED worker that must resolve that tenant's
credential WITHOUT holding a raw, forgeable ``universe_id`` or the credential
``ref``. This module is that primitive: the daemon mints an OPAQUE, single
job-scoped grant derived from the AUTHORITATIVE run record; the worker presents
ONLY the opaque grant and the broker resolves the credential against the grant's
OWN authoritative run/universe (recorded at mint from the run record) — NEVER
against caller-supplied identifiers, which a bearer could forge.

The grant is a bearer capability: an opaque id + a random secret whose hash is
stored. The secret lives in a private, non-observable :class:`SecretBytes` (no
repr/asdict/pickle leak), exactly like the refresh capability. The grant object
deliberately exposes NO ``run_id``/``universe_id`` — those live only in the
broker-side row, so there is nothing for a bearer to replay.

The public resolver keeps ``verify_context=None`` in its signature for consumer
compatibility, but verification is mandatory in effect: omission, a falsey
result, or a raised callback fails closed. The broker hands the verifier the
grant's authoritative :class:`JobContext`. The TTL is validated finite,
positive, and bounded at mint time so a grant can never be non-expiring.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import sqlite3
from dataclasses import dataclass
from typing import NoReturn

from .errors import CredentialUnavailable, VaultErrorCode
from .secret_bytes import SecretBytes
from .types import SecretKind, is_secret_ref

# A job grant is short-lived by construction: it exists only for the lifetime of
# one isolated worker job. Reject a TTL beyond this upper bound (and any
# non-finite / non-positive TTL) so a grant can never become effectively
# permanent — the exact ``ttl=inf`` hole Codex r10 flagged.
MAX_JOB_GRANT_TTL = 86_400.0  # 24h hard ceiling


def validate_ttl(ttl: float) -> float:
    """Return a finite, positive, bounded TTL or raise ``INVALID_ARGUMENT``.

    Rejects ``inf``/``nan`` (non-expiring or nonsensical), ``<= 0`` (already
    expired / negative), and anything above :data:`MAX_JOB_GRANT_TTL`.
    """
    try:
        ttl = float(ttl)
    except (TypeError, ValueError):
        raise CredentialUnavailable(VaultErrorCode.INVALID_ARGUMENT) from None
    if not math.isfinite(ttl) or ttl <= 0.0 or ttl > MAX_JOB_GRANT_TTL:
        raise CredentialUnavailable(VaultErrorCode.INVALID_ARGUMENT)
    return ttl


@dataclass(frozen=True)
class JobContext:
    """The AUTHORITATIVE execution context a grant was minted from.

    Broker-trusted: reconstructed from the stored grant row (which the daemon
    wrote from the run record at mint time), NEVER from caller input. Handed to
    a mandatory-in-effect ``verify_context`` callback so S3 confirms the LIVE
    executor identity matches the grant. Carries only non-secret identifiers.
    """

    run_id: str
    universe_id: str
    founder_id: str


@dataclass(frozen=True)
class ParsedGrant:
    grant_id: str
    capability_hash: str
    ref: str
    founder_id: str
    universe_id: str
    provider: str
    destination: str
    purpose: str
    kind: SecretKind
    run_id: str
    expires_at: float


GRANTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_job_grants (
    grant_id        TEXT PRIMARY KEY,
    capability_hash TEXT NOT NULL,
    ref             TEXT NOT NULL,
    founder_id      TEXT NOT NULL,
    universe_id     TEXT NOT NULL,
    provider        TEXT NOT NULL,
    destination     TEXT NOT NULL,
    purpose         TEXT NOT NULL,
    kind            TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    expires_at      REAL NOT NULL
);
"""

_GRANT_ID_PREFIX = "grant:v1:"
_GRANT_ID_BYTES = 16
_CAPABILITY_BYTES = 32


def new_grant_id() -> str:
    return _GRANT_ID_PREFIX + secrets.token_hex(_GRANT_ID_BYTES)


def is_grant_id(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith(_GRANT_ID_PREFIX):
        return False
    body = value[len(_GRANT_ID_PREFIX) :]
    if len(body) != _GRANT_ID_BYTES * 2:
        return False
    try:
        int(body, 16)
    except ValueError:
        return False
    return True


def mint_capability() -> bytes:
    return secrets.token_bytes(_CAPABILITY_BYTES)


def capability_hash(secret: bytes) -> str:
    return hashlib.sha256(secret).hexdigest()


def capability_matches(stored_hash: str, secret: bytes) -> bool:
    return hmac.compare_digest(stored_hash, capability_hash(secret))


def _refuse(*_a: object, **_k: object) -> NoReturn:
    raise TypeError("JobGrant carries a bearer capability and cannot be copied/serialized")


class JobGrant:
    """Opaque job-scoped grant: an id + a private, non-observable capability.

    Deliberately exposes NO ``run_id``/``universe_id`` — the authoritative
    identifiers live only in the broker-side row, so a bearer has nothing to
    replay. Not a dataclass (so ``asdict``/``vars`` cannot extract the secret);
    slotted; the secret is redacted from repr/str/format and cannot be
    pickled/copied.
    """

    __slots__ = ("grant_id", "_capability")

    def __init__(self, *, grant_id: str, secret: bytes) -> None:
        self.grant_id = grant_id
        self._capability = SecretBytes(secret)

    def _reveal_capability(self) -> bytes:
        return self._capability.reveal()

    def __repr__(self) -> str:
        return f"JobGrant(grant_id={self.grant_id!r}, capability=<redacted>)"

    __str__ = __repr__

    def __format__(self, _spec: str) -> str:
        return self.__repr__()

    __reduce__ = _refuse
    __reduce_ex__ = _refuse
    __getstate__ = _refuse
    __copy__ = _refuse
    __deepcopy__ = _refuse


def store_grant(
    conn: sqlite3.Connection,
    *,
    grant_id: str,
    cap_hash: str,
    ref: str,
    founder_id: str,
    universe_id: str,
    provider: str,
    destination: str,
    purpose: str,
    kind: str,
    run_id: str,
    expires_at: float,
) -> None:
    conn.execute(
        "INSERT INTO vault_job_grants(grant_id, capability_hash, ref, founder_id, "
        "universe_id, provider, destination, purpose, kind, run_id, expires_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            grant_id, cap_hash, ref, founder_id, universe_id, provider,
            destination, purpose, kind, run_id, expires_at,
        ),
    )


def read_grant(conn: sqlite3.Connection, grant_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM vault_job_grants WHERE grant_id = ?", (grant_id,)
    ).fetchone()


def parse_grant(row: sqlite3.Row) -> ParsedGrant:
    """Normalize every persisted field before capability or context use."""
    try:
        grant_id = row["grant_id"]
        capability = row["capability_hash"]
        ref = row["ref"]
        text = {
            name: row[name]
            for name in (
                "founder_id", "universe_id", "provider", "destination",
                "purpose", "run_id",
            )
        }
        kind = SecretKind(row["kind"])
        expires_at = float(row["expires_at"])
        if not is_grant_id(grant_id) or not is_secret_ref(ref):
            raise ValueError
        if not isinstance(capability, str) or len(capability) != 64:
            raise ValueError
        int(capability, 16)
        if any(
            not isinstance(value, str)
            or not value
            or len(value) > 4096
            or any(ch in value for ch in ("\x00", "\r", "\n"))
            for value in text.values()
        ):
            raise ValueError
        if not math.isfinite(expires_at):
            raise ValueError
    except (KeyError, IndexError, TypeError, ValueError):
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD) from None
    return ParsedGrant(
        grant_id=grant_id,
        capability_hash=capability,
        ref=ref,
        founder_id=text["founder_id"],
        universe_id=text["universe_id"],
        provider=text["provider"],
        destination=text["destination"],
        purpose=text["purpose"],
        kind=kind,
        run_id=text["run_id"],
        expires_at=expires_at,
    )


def revoke_grant(conn: sqlite3.Connection, grant_id: str) -> None:
    conn.execute("DELETE FROM vault_job_grants WHERE grant_id = ?", (grant_id,))
