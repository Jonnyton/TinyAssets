"""Capability-scoped bounded authoring source reads for generic file custody.

An internal source adapter, not authentication or acceptance. Its caller must
provide the authenticated owner and independently check universe/tombstone
authority. Periodic reads refuse revocation/expiry; final binding ALSO requires
the short authoring-source authority fence so revoke cannot race commit. This
module does not publish a run object, hold a writer during IO, or claim a mutable
workspace snapshot. Authoring bodies are server-private immutable handle files.
"""

from contextlib import contextmanager
from types import MappingProxyType

from tinyassets.authoring.models import access_denied
from tinyassets.execution_authority.blob_proof import BlobProofStore, BlobRef
from tinyassets.execution_authority.blob_stream import CHUNK_BYTES

_IDENTITY = (
    "handle_id",
    "session_id",
    "owner_id",
    "filename",
    "media_type",
    "size_bytes",
    "sha256",
)


class AuthoringFileSource:
    def __init__(self, store, owner_id, session_id, handle_id, metadata, should_cancel):
        self._store = store
        self._owner = owner_id
        self._session = session_id
        self._handle = handle_id
        self._cancel = should_cancel
        self.metadata = MappingProxyType(dict(metadata))
        self._held = None

    def recheck(self):
        self._store.get_session(self._session, actor_id=self._owner)
        current = self._store.get_file_handle(
            self._handle,
            actor_id=self._owner,
            session_id=self._session,
        )
        if any(current[key] != self.metadata[key] for key in _IDENTITY):
            raise access_denied()
        return current

    def _should_cancel(self):
        self.recheck()
        return self._cancel is not None and self._cancel()

    @contextmanager
    def commit_fence(self, *, timeout_seconds=2.0):
        """After bytes publish: caller owns canonical author fence, then runs commit.

        No stream/hash/physical coordinator work is allowed inside this context.
        Its sole purpose is to serialize handle revocation with final acceptance.
        """
        if self._held is None:
            raise RuntimeError("authoring file source is not held")
        with self._store.file_handle_commit_fence(
            handle_id=self._handle,
            actor_id=self._owner,
            session_id=self._session,
            timeout_seconds=timeout_seconds,
        ) as current:
            if any(current[key] != self.metadata[key] for key in _IDENTITY):
                raise access_denied()
            yield current

    def iter_chunks(self):
        if self._held is None:
            raise RuntimeError("authoring file source is not held")
        for offset in range(0, self.metadata["size_bytes"], CHUNK_BYTES):
            self.recheck()
            chunk = self._held.read_range(offset, CHUNK_BYTES)
            self.recheck()
            yield chunk
        self.recheck()


@contextmanager
def open_authoring_source(store, *, owner_id, session_id, handle_id, should_cancel=None):
    """Resolve actual owned handle; no caller filesystem path is ever accepted."""
    if any(type(value) is not str or not value for value in (owner_id, session_id, handle_id)):
        raise access_denied()
    store.get_session(session_id, actor_id=owner_id)
    metadata = store.get_file_handle(handle_id, actor_id=owner_id, session_id=session_id)
    source = AuthoringFileSource(store, owner_id, session_id, handle_id, metadata, should_cancel)
    # IDs come from the current authorized row and the blob primitive validates
    # canonical traversal, secure parents, regular leaf and exact digest/size.
    reference = BlobRef(
        f"{metadata['session_id']}/{metadata['handle_id']}",
        metadata["sha256"],
        metadata["size_bytes"],
    )
    blobs = BlobProofStore(store.blob_root)
    with blobs.open_held_stream(reference, should_cancel=source._should_cancel) as held:
        source._held = held
        try:
            yield source
            source.recheck()
        finally:
            source._held = None
