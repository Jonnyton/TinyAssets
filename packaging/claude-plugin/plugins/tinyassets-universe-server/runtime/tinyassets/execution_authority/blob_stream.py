"""Bounded private-body IO using the installed blob store's secure handles.

Not a read/capture authority or a mutable-file snapshot. Callers must journal
both names before writing, hold operation exclusion through binding commit,
and independently freeze any mutable producer. No SQLite transaction or family
fence may span iteration. Only short final publication takes the root lock.
Bodies are deliberately absent from the legacy whole-file JSON blob index.
"""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from pathlib import PurePosixPath

from .blob_proof import (
    BlobProofError,
    BlobRef,
    _canonical_relative_path,
    _validated_ref,
    _windows_create_file,
)

CHUNK_BYTES = 1024 * 1024


class BlobStreamError(BlobProofError):
    """Partial body remains inventoried; these counters are not a quota refund."""

    def __init__(self, message, *, bytes_written=0, bytes_read=0):
        super().__init__(message)
        self.bytes_written = bytes_written
        self.bytes_read = bytes_read


def _cancel(check):
    if check is not None and check():
        raise BlobProofError("blob stream cancelled")


def _sync_parent(parent):
    if parent.parent_fd is not None:
        os.fsync(parent.parent_fd)


def stage_stream(store, relative_path, chunks, max_bytes, should_cancel):
    """Write an exclusive journaled name, leaving partial bytes on any failure."""
    if type(max_bytes) is not int or not 0 <= max_bytes < 2**63:
        raise BlobProofError("invalid blob stream size limit")
    path_key = _canonical_relative_path(relative_path)
    written = consumed = 0
    fd = None
    try:
        _cancel(should_cancel)
        with store._secure_parent(path_key, create_parents=True) as (parent, leaf, path):
            if os.name == "nt":
                fd = _windows_create_file(path)
            else:
                fd = os.open(
                    leaf,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent.parent_fd,
                )
            identity = os.fstat(fd)
            digest = hashlib.sha256()
            iterator = iter(chunks)
            while True:
                _cancel(should_cancel)
                try:
                    chunk = next(iterator)
                except StopIteration:
                    break
                if type(chunk) is not bytes:
                    raise BlobProofError("blob stream requires immutable bytes chunks")
                consumed += len(chunk)
                _cancel(should_cancel)
                if len(chunk) > CHUNK_BYTES:
                    raise BlobProofError("blob stream chunk exceeds limit")
                if written + len(chunk) > max_bytes:
                    raise BlobProofError("blob stream exceeds byte limit")
                view = memoryview(chunk)
                while view:
                    _cancel(should_cancel)
                    amount = os.write(fd, view)
                    if amount <= 0 or amount > len(view):
                        raise BlobProofError("blob stream write made invalid progress")
                    written += amount
                    view = view[amount:]
                digest.update(chunk)
                parent.ensure_stable()
            _cancel(should_cancel)
            os.fsync(fd)
            current = parent.stat_leaf(leaf)
            after = os.fstat(fd)
            if (
                current is None
                or (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino)
                or after.st_size != written
            ):
                raise BlobProofError("blob stream leaf changed during staging")
            parent.ensure_stable()
            _sync_parent(parent)
            return BlobRef(path_key, digest.hexdigest(), written)
    except Exception as exc:
        raise BlobStreamError(str(exc), bytes_written=written, bytes_read=consumed) from exc
    finally:
        if fd is not None:
            os.close(fd)


class HeldBlobStream:
    """One held private immutable body. A caller's operation guard prevents GC."""

    def __init__(self, held, ref, should_cancel):
        self._held = held
        self.ref = ref
        self._should_cancel = should_cancel

    def verify(self):
        self._held.ensure_stable()
        if self._held.snapshot.st_size != self.ref.size:
            raise BlobProofError("blob stream size differs from reference")
        digest = hashlib.sha256()
        count = 0
        os.lseek(self._held.fd, 0, os.SEEK_SET)
        while True:
            _cancel(self._should_cancel)
            chunk = os.read(self._held.fd, CHUNK_BYTES)
            if not chunk:
                break
            count += len(chunk)
            if count > self.ref.size:
                raise BlobProofError("blob stream exceeds reference size")
            digest.update(chunk)
        self._held.ensure_stable()
        if count != self.ref.size or digest.hexdigest() != self.ref.sha256:
            raise BlobProofError("blob stream digest differs from reference")

    def read_range(self, offset, count):
        if (
            type(offset) is not int
            or type(count) is not int
            or offset < 0
            or offset > self.ref.size
            or not 0 <= count <= CHUNK_BYTES
        ):
            raise BlobProofError("invalid blob stream range")
        _cancel(self._should_cancel)
        self._held.ensure_stable()
        os.lseek(self._held.fd, offset, os.SEEK_SET)
        remaining = min(count, self.ref.size - offset)
        parts = []
        while remaining:
            _cancel(self._should_cancel)
            chunk = os.read(self._held.fd, remaining)
            if not chunk:
                raise BlobProofError("blob stream shortened during read")
            parts.append(chunk)
            remaining -= len(chunk)
        self._held.ensure_stable()
        _cancel(self._should_cancel)
        return b"".join(parts)


@contextmanager
def open_held_stream(store, ref, should_cancel):
    ref = _validated_ref(ref)
    with store._secure_parent(ref.relative_path, create_parents=False) as (parent, _, path):
        held = store._read_regular_file(path, parent=parent, hold_open=True, stream_only=True)
        try:
            stream = HeldBlobStream(held, ref, should_cancel)
            stream.verify()
            yield stream
            stream.verify()
        finally:
            held.close()


def publish_staged(store, ref, relative_path, should_cancel):
    """No-clobber same-parent publication. An operation guard must fence GC.

    Link then unlink is crash-recoverable from the caller's two-name inventory.
    Both names may exist after interruption; it must never be reported as two
    allocations. Platforms/filesystems without hard links refuse publication.
    """
    ref = _validated_ref(ref)
    target = _canonical_relative_path(relative_path)
    if PurePosixPath(target).parent != PurePosixPath(ref.relative_path).parent:
        raise BlobProofError("staged publication requires the same secure parent")
    with open_held_stream(store, ref, should_cancel) as stream:
        held = stream._held
        parent = held.parent
        target_path = held.path.with_name(PurePosixPath(target).name)
        _cancel(should_cancel)
        with store.coordinated():
            # No caller callback under the physical coordinator: authority
            # predicates can acquire metadata locks. Verification checks again
            # after release; final custody binding separately rechecks authority.
            # A cancel while waiting may leave an invisible inventoried body,
            # never permission to publish a ready object or run binding.
            held.ensure_stable()
            try:
                if parent.parent_fd is None:
                    os.link(held.path, target_path, follow_symlinks=False)
                else:
                    os.link(
                        held.path.name,
                        target_path.name,
                        src_dir_fd=parent.parent_fd,
                        dst_dir_fd=parent.parent_fd,
                        follow_symlinks=False,
                    )
            except OSError as exc:
                raise BlobProofError("staged publication target exists or is unsupported") from exc
            _sync_parent(parent)
            old_name = held.path.name
            held.path = target_path
            held.ensure_stable()
            parent.unlink_leaf(old_name)
            _sync_parent(parent)
        return BlobRef(target, ref.sha256, ref.size)
