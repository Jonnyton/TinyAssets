"""Connection-grant custody (serve-open-compute-provider phase 1.2 / custody).

The secret-free custody reference for an open api_key_http provider, reusing the
subscription custody table + reference-digest so the assignment/work-binding/CAS
machinery consumes it unchanged. Covers: adopt creates a reference, idempotency,
rotation on grant-identity change, current read + absence, secret-free record digest,
and reference-digest consistency with the shared helper.
"""

from __future__ import annotations

import sqlite3

import pytest

from tinyassets.credential_vault import (
    LLMCredentialCustodyReference,
    _custody_reference_digest,
    adopt_connection_grant_custody,
    current_connection_grant_custody,
)

_ARGS = dict(
    owner_user_id="founder",
    universe_id="u-x",
    grant_id="http_grant_" + "a" * 32,
    connection_id="http_" + "b" * 32,
    credential_ref="vault://http/webhook:acme",
)


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.execute("BEGIN")
    yield c
    c.rollback()
    c.close()


def test_adopt_creates_reference(conn: sqlite3.Connection) -> None:
    ref = adopt_connection_grant_custody(conn, **_ARGS)
    assert isinstance(ref, LLMCredentialCustodyReference)
    assert ref.reference_id.startswith("llm_credential_")
    assert ref.generation == 1
    assert ref.service == f"connection:{_ARGS['connection_id']}"
    # reference_digest is exactly the shared helper's output over this custody's fields.
    assert ref.reference_digest == _custody_reference_digest(
        reference_id=ref.reference_id, owner_user_id="founder", universe_id="u-x",
        service=ref.service, generation=1, record_digest=ref._record_digest,
    )


def test_adopt_is_idempotent(conn: sqlite3.Connection) -> None:
    a = adopt_connection_grant_custody(conn, **_ARGS)
    b = adopt_connection_grant_custody(conn, **_ARGS)
    assert a.reference_id == b.reference_id
    assert a.generation == b.generation == 1
    assert a.reference_digest == b.reference_digest


def test_adopt_rotates_on_grant_identity_change(conn: sqlite3.Connection) -> None:
    a = adopt_connection_grant_custody(conn, **_ARGS)
    rotated = dict(_ARGS, credential_ref="vault://http/webhook:acme-v2")
    b = adopt_connection_grant_custody(conn, **rotated)
    assert b.reference_id == a.reference_id  # same slot (owner/universe/connection)
    assert b.generation == 2  # rotated
    assert b._record_digest != a._record_digest


def test_current_reads_adopted(conn: sqlite3.Connection) -> None:
    adopted = adopt_connection_grant_custody(conn, **_ARGS)
    got = current_connection_grant_custody(
        conn, owner_user_id="founder", universe_id="u-x",
        connection_id=_ARGS["connection_id"],
    )
    assert got is not None
    assert got.reference_id == adopted.reference_id
    assert got.reference_digest == adopted.reference_digest
    assert got._record_digest == adopted._record_digest


def test_current_absent_is_none(conn: sqlite3.Connection) -> None:
    assert current_connection_grant_custody(
        conn, owner_user_id="founder", universe_id="u-x", connection_id="http_none",
    ) is None


def test_record_digest_is_secret_free(conn: sqlite3.Connection) -> None:
    # The record digest is over grant IDENTITY, never the credential material — pass a
    # would-be secret nowhere; assert the digest depends only on the identity fields.
    ref = adopt_connection_grant_custody(conn, **_ARGS)
    from tinyassets.credential_vault import _connection_grant_record_digest

    assert ref._record_digest == _connection_grant_record_digest(
        grant_id=_ARGS["grant_id"], connection_id=_ARGS["connection_id"],
        credential_ref=_ARGS["credential_ref"], owner_user_id="founder",
        universe_id="u-x",
    )


def test_requires_active_transaction() -> None:
    c = sqlite3.connect(":memory:")
    try:
        with pytest.raises(ValueError):
            adopt_connection_grant_custody(c, **_ARGS)  # not in a transaction
    finally:
        c.close()


def test_invalid_root_rejected(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError):
        adopt_connection_grant_custody(conn, **dict(_ARGS, grant_id=""))
    with pytest.raises(ValueError):
        adopt_connection_grant_custody(conn, **dict(_ARGS, credential_ref=""))
