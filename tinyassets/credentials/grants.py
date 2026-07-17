"""Opaque, job-scoped broker grants (the S3 executor-boundary primitive).

S3 runs a tenant's job in an ISOLATED worker that must resolve that tenant's
credential WITHOUT holding a raw, forgeable ``universe_id`` or the credential
``ref``. This module is that primitive: the daemon mints an OPAQUE, single
job-scoped grant derived from the AUTHORITATIVE run record; the worker presents
the grant plus its own authoritative ``run_id``/``universe_id`` and the broker
resolves the credential, failing closed for missing / malformed / expired /
wrong-run / cross-universe.

The grant is a bearer capability: an opaque id + a random secret whose hash is
stored. The secret lives in a private, non-observable :class:`SecretBytes` (no
repr/asdict/pickle leak), exactly like the refresh capability.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from typing import NoReturn

from .secret_bytes import SecretBytes

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

    Not a dataclass (so ``asdict``/``vars`` cannot extract the secret); slotted;
    the secret is redacted from repr/str/format and cannot be pickled/copied.
    """

    __slots__ = ("grant_id", "run_id", "universe_id", "_capability")

    def __init__(self, *, grant_id: str, run_id: str, universe_id: str, secret: bytes) -> None:
        self.grant_id = grant_id
        self.run_id = run_id
        self.universe_id = universe_id
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


def revoke_grant(conn: sqlite3.Connection, grant_id: str) -> None:
    conn.execute("DELETE FROM vault_job_grants WHERE grant_id = ?", (grant_id,))
