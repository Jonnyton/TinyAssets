"""Cross-owner custody copy producing RECEIVER-owned bytes for one delivery.

Not an intake API and not an authority source. The caller supplies the trusted
compiled sender source (persisted running run, never RPC data) and the receiver
owner/universe resolved from receiver-authored link policy. Sender bytes are
copied into receiver-owned custody through the one shared capture journal, so
receiver readability never depends on sender retention and sender erasure never
reaches a receiver copy. No storage row is shared, no receiver-visible value ever
carries a sender file id, path or storage key, and no DB write lock is held while
bytes move.

Source authority is re-resolved ON the publication connections: sender custody,
sender binding and receiver link generation all serialize on the runs database,
and the sender's universe grant on the platform database, so a ``source_fence``
taking either would self-deadlock against the writers opened inside it. Both held
connections are therefore handed to ``_capture_files(publication_check=...)``.

Publication is not the last gate. The copy runs ABOVE every acceptance fence, so
``assert_bound_sources`` is called once more by final acceptance inside its own
transaction -- the last point at which a sender change still costs the receiver
nothing.
"""

from contextlib import contextmanager

from tinyassets import runs
from tinyassets.execution_authority.blob_proof import BlobRef
from tinyassets.execution_authority.blob_stream import CHUNK_BYTES
from tinyassets.run_file_capture import (
    _authority,
    _capture_files,
    _digest,
    _physical_store,
    check_admin_grant,
)
from tinyassets.run_file_contract import public_reference, verify_reference
from tinyassets.storage import receiver_links
from tinyassets.storage import run_files as store

_IDENTITY = ("file_id", "filename", "media_type", "size_bytes", "sha256")


def _trusted_source_run(conn, source):
    """The sender's persisted run must still be the running trusted placement."""
    row = conn.execute(
        "SELECT * FROM runs WHERE run_id=?", (source.run_id,)
    ).fetchone()
    if (
        row is None
        or row["status"] != "running"
        or row["owner_user_id"] != source.owner_user_id
        or row["actor"] != source.actor
        or row["queue_universe_id"] != source.universe_id
        or row["branch_def_id"] != source.branch_def_id
    ):
        raise store.FileCustodyRefused("run_file_access_denied")


def resolve_bound_source(conn, source, reference):
    """Resolve one sender envelope against the trusted source run, read-only.

    Ownership resolution at the sender is the only admitted derivation: envelope
    metadata alone never grants a read. Returns the private row; callers must not
    hand its ``storage_key`` or ``file_id`` to the receiver.
    """
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='run_file_objects'"
    ).fetchone() is None:
        # No custody has ever been created here: a typed refusal, never a raw
        # OperationalError leaking out of an acceptance path.
        raise store.FileCustodyRefused("run_file_not_found")
    row = store.bound_file_in_transaction(
        conn,
        run_id=source.run_id,
        owner_id=source.owner_user_id,
        universe_id=source.universe_id,
        file_id=reference["file_id"],
    )
    verify_reference(reference, row)
    return row


def assert_bound_sources(conn, source, references):
    """Re-resolve sender envelopes against the trusted source run, read-only.

    The ONE definition of "these sender files are still exactly what was read".
    Used by the publication fence and again by final acceptance: the byte copy
    runs above the acceptance fence, so acceptance is the last point at which a
    sender release, rebind or replacement can still be refused before the
    receiver is told yes. Binds nothing and returns the private rows.
    """
    _trusted_source_run(conn, source)
    return [resolve_bound_source(conn, source, reference) for reference in references]


def _resolve_all(base, source, references):
    with _authority(base, source.owner_user_id, source.universe_id):
        with runs._connect(base) as conn:
            conn.execute("BEGIN")
            _trusted_source_run(conn, source)
            return [resolve_bound_source(conn, source, ref) for ref in references]


def operation_id(*, receiver_owner_id, receiver_universe_id, link_id, occurrence_id):
    """Keyed on the receiver occurrence ONLY: a changed replay must re-enter the
    same operation and conflict before any allocation, never allocate afresh."""
    return "file:delivery:" + _digest(
        [receiver_owner_id, receiver_universe_id, link_id, occurrence_id]
    )


def copy_owned_custody_file(
    base,
    *,
    source,
    receiver_owner_id,
    receiver_universe_id,
    link_id,
    occurrence_id,
    references,
    should_cancel=None,
):
    """Copy sender-bound files into receiver custody and return receiver refs.

    ``references`` is the ordered sender envelope list; the result is the ordered
    receiver public reference list. Runs ABOVE any acceptance fence: acceptance
    holds both the platform and runs writers, and this path opens both itself.
    """
    if not isinstance(references, list) or not references:
        raise store.FileCustodyRefused("file_capture_request_invalid")
    operation = operation_id(
        receiver_owner_id=receiver_owner_id, receiver_universe_id=receiver_universe_id,
        link_id=link_id, occurrence_id=occurrence_id,
    )
    request = _digest([
        "cross-owner-delivery-v1", source.owner_user_id, source.universe_id, source.run_id,
        source.branch_def_id, source.node_id,
        [reference["file_id"] for reference in references],
    ])
    expected = []

    def metadata():
        rows = _resolve_all(base, source, references)
        expected.clear()
        expected.extend({key: row[key] for key in _IDENTITY} for row in rows)
        return rows

    @contextmanager
    def opened(index, current, cancelled):
        _, blobs = _physical_store(base, create=False)
        row = _resolve_all(base, source, [references[index]])[0]
        if any(row[key] != current[key] for key in _IDENTITY):
            raise store.FileCustodyRefused("file_source_changed")

        def source_cancelled():
            fresh = _resolve_all(base, source, [references[index]])[0]
            if any(fresh[key] != current[key] for key in _IDENTITY):
                raise store.FileCustodyRefused("file_source_changed")
            return cancelled()

        body = BlobRef(row["storage_key"] + ".body", row["sha256"], row["size_bytes"])
        with blobs.open_held_stream(body, should_cancel=source_cancelled) as held:
            yield _chunks(held, row["size_bytes"], source_cancelled)

    def _chunks(held, size, cancel):
        for offset in range(0, size, CHUNK_BYTES):
            # Sender revocation/release is rechecked between chunks exactly as the
            # authoring adapter does; no DB write lock is held in this loop.
            if cancel():
                raise store.FileCustodyRefused("file_capture_cancelled")
            yield held.read_range(offset, CHUNK_BYTES)

    @contextmanager
    def fence(_current):
        # Deliberately null: a cross-owner source has no third database to order
        # against, and BEGIN IMMEDIATE on the runs database here would deadlock
        # with the publication writer opened inside this context.
        yield

    def publication_check(conn, platform):
        # The sender's grant is revalidated HERE, on the held platform writer: the
        # last source read happened above this fence, so a grant revoked or a
        # principal tombstoned since then must still stop the bytes from becoming
        # receiver-owned. The receiver's own grant is what _capture_files holds.
        check_admin_grant(platform, source.owner_user_id, source.universe_id)
        for row, current in zip(assert_bound_sources(conn, source, references), expected):
            if any(row[key] != current[key] for key in _IDENTITY):
                raise store.FileCustodyRefused("file_source_changed")
        _, receiver = receiver_links.resolve_link_in_transaction(
            conn, link_id=link_id, owner_id=source.owner_user_id,
            universe_id=source.universe_id,
        )
        if (receiver["owner_id"], receiver["universe_id"]) != (
            receiver_owner_id, receiver_universe_id,
        ):
            raise store.FileCustodyRefused("run_file_access_denied")

    return _capture_files(
        base,
        owner_id=receiver_owner_id,
        universe_id=receiver_universe_id,
        operation=operation,
        request=request,
        metadata_provider=metadata,
        open_source=opened,
        source_fence=fence,
        publication_check=publication_check,
        should_cancel=should_cancel,
    )


def receiver_reference(conn, *, run_id, owner_id, universe_id, file_id):
    """Receiver-side readback of its OWN accepted copy; no sender value appears."""
    row = store.bound_file_in_transaction(
        conn, run_id=run_id, owner_id=owner_id, universe_id=universe_id, file_id=file_id
    )
    return public_reference(row)
