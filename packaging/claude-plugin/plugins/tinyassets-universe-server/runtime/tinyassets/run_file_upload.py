"""Bounded raw-byte app upload into the SAME immutable run-file custody.

No new store, queue, job, schema or provider. A trusted authenticated adapter
supplies owner/home; this module reuses the capture journal, reservation,
staging, publication, commit fence and cleanup debt of ``run_file_capture``.
Bytes arrive through an explicitly bounded two-slot bridge between the ASGI
producer and one worker thread that owns the operation guard throughout.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import threading
import time
from collections import deque
from contextlib import contextmanager

from tinyassets.authoring.io import MAX_FILE_BYTES
from tinyassets.execution_authority.blob_stream import CHUNK_BYTES
from tinyassets.run_file_capture import _capture_files, _digest
from tinyassets.storage import run_files as store

UPLOAD_SOURCE_KIND = "app-upload-v1"
MAX_UPLOAD_BYTES = MAX_FILE_BYTES
MAX_HEADER_BYTES = 8192
LABEL_MIN, LABEL_MAX = 16, 128
BRIDGE_SLOTS = 2
IDLE_SECONDS = 10.0
TOTAL_SECONDS = 120.0
_METADATA_KEYS = frozenset(
    {"version", "label", "expected_universe_id", "filename", "media_type", "size_bytes", "sha256"}
)
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_B64URL = re.compile(r"[A-Za-z0-9_-]*={0,2}\Z")


def parse_upload_metadata(header):
    """Exact metadata header -> dict; refuse rather than truncate or coerce."""
    if type(header) is not str or not header.isascii():
        raise store.FileCustodyRefused("upload_metadata_invalid")
    if len(header) > MAX_HEADER_BYTES:
        raise store.FileCustodyRefused("upload_header_limit")
    if not header or not _B64URL.fullmatch(header):
        raise store.FileCustodyRefused("upload_metadata_invalid")
    padded = header.rstrip("=")
    padded += "=" * (-len(padded) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded)
        data = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise store.FileCustodyRefused("upload_metadata_invalid") from exc
    if not isinstance(data, dict) or set(data) != _METADATA_KEYS:
        raise store.FileCustodyRefused("upload_metadata_invalid")
    if type(data["version"]) is not int or data["version"] != 1:
        raise store.FileCustodyRefused("upload_metadata_invalid")
    for key in ("label", "expected_universe_id", "filename", "media_type", "sha256"):
        if type(data[key]) is not str:
            raise store.FileCustodyRefused("upload_metadata_invalid")
    if not LABEL_MIN <= len(data["label"]) <= LABEL_MAX:
        raise store.FileCustodyRefused("upload_metadata_invalid")
    if not data["expected_universe_id"] or not data["filename"]:
        raise store.FileCustodyRefused("upload_metadata_invalid")
    if len(data["filename"]) > 4096 or len(data["media_type"]) > 256:
        raise store.FileCustodyRefused("upload_metadata_limit")
    if not _SHA.fullmatch(data["sha256"]):
        raise store.FileCustodyRefused("upload_metadata_invalid")
    size = data["size_bytes"]
    if type(size) is not int or size < 0:
        raise store.FileCustodyRefused("upload_metadata_invalid")
    if size > MAX_UPLOAD_BYTES:
        raise store.FileCustodyRefused("upload_too_large")
    return dict(data)


class UploadAborted(Exception):
    """The bridge was failed by either side; ``reason`` is a stable safe token."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class StreamBridge:
    """Two-slot handoff: async ASGI producer -> one synchronous worker thread.

    Chunks are at most CHUNK_BYTES each and at most BRIDGE_SLOTS are buffered;
    the producer waits for space and the worker waits for data or EOF. Either
    side may ``fail`` it; both sides wake. Nothing here is durable.
    """

    def __init__(self, loop, *, slots=BRIDGE_SLOTS, idle_seconds=None, total_seconds=None):
        import asyncio

        self._loop = loop
        self._slots = slots
        self._idle = IDLE_SECONDS if idle_seconds is None else idle_seconds
        self._total = TOTAL_SECONDS if total_seconds is None else total_seconds
        self._cond = threading.Condition()
        self._chunks = deque()
        self._eof = False
        self._reason = None
        self._started = None
        self._space = asyncio.Event()
        self._ready = asyncio.Event()
        self._done = asyncio.Event()
        self.high_water = 0
        self.consumed = 0

    # ---- shared -----------------------------------------------------------
    @property
    def reason(self):
        return self._reason

    def _wake_loop(self, event):
        try:
            self._loop.call_soon_threadsafe(event.set)
        except RuntimeError:  # loop already closed: nothing left to wake
            pass

    def fail(self, reason):
        with self._cond:
            if self._reason is None:
                self._reason = reason
            self._cond.notify_all()
        self._wake_loop(self._space)
        self._wake_loop(self._ready)
        self._wake_loop(self._done)

    def remaining(self):
        if self._started is None:
            return self._total
        return self._total - (time.monotonic() - self._started)

    # ---- worker side (thread) --------------------------------------------
    def ready_to_copy(self):
        """Reservation done: the producer may start reading body bytes now."""
        with self._cond:
            if self._reason is not None:
                raise UploadAborted(self._reason)
            self._started = time.monotonic()
        self._wake_loop(self._ready)

    def finished(self):
        self._wake_loop(self._done)

    def cancelled(self):
        return self._reason is not None

    def chunks(self):
        while True:
            with self._cond:
                waited = 0.0
                while not self._chunks and not self._eof and self._reason is None:
                    step = min(self._idle - waited, max(self.remaining(), 0.0), 1.0)
                    if step <= 0:
                        self.fail("upload_timeout")
                        break
                    before = time.monotonic()
                    self._cond.wait(timeout=step)
                    waited += time.monotonic() - before
                    if waited >= self._idle and not self._chunks and not self._eof:
                        self.fail("upload_timeout")
                        break
                if self._reason is not None:
                    raise UploadAborted(self._reason)
                if not self._chunks:
                    return
                chunk = self._chunks.popleft()
            self.consumed += len(chunk)
            self._wake_loop(self._space)
            yield chunk

    # ---- producer side (event loop) --------------------------------------
    async def wait_ready(self):
        """True when the worker reached the copy phase; False when it finished first."""
        import asyncio

        ready = asyncio.ensure_future(self._ready.wait())
        done = asyncio.ensure_future(self._done.wait())
        try:
            await asyncio.wait({ready, done}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (ready, done):
                task.cancel()
        return self._ready.is_set() and self._reason is None

    async def push(self, data):
        import asyncio

        view = memoryview(data)
        while view:
            piece = bytes(view[:CHUNK_BYTES])
            view = view[CHUNK_BYTES:]
            while True:
                with self._cond:
                    if self._reason is not None:
                        raise UploadAborted(self._reason)
                    if len(self._chunks) < self._slots:
                        self._chunks.append(piece)
                        self.high_water = max(self.high_water, len(self._chunks))
                        self._cond.notify_all()
                        break
                    self._space.clear()
                remaining = self.remaining()
                if remaining <= 0:
                    self.fail("upload_timeout")
                    raise UploadAborted("upload_timeout")
                try:
                    await asyncio.wait_for(self._space.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    self.fail("upload_timeout")
                    raise UploadAborted("upload_timeout") from None

    def close(self):
        with self._cond:
            self._eof = True
            self._cond.notify_all()


def _wrap_result(conn, operation, refs):
    """Wrapper metadata beside the immutable references, from the operation row."""
    row = conn.execute(
        "SELECT unbound_expires_at FROM run_file_operations WHERE operation_id=?", (operation,)
    ).fetchone()
    if row is None:
        raise store.FileCustodyRefused("run_file_not_found")
    bound = all(
        conn.execute(
            "SELECT 1 FROM run_file_bindings WHERE file_id=?", (ref["file_id"],)
        ).fetchone()
        is not None
        for ref in refs
    )
    expires = float(row[0])
    if not bound and expires <= time.time():
        raise store.FileCustodyRefused("upload_expired")
    return {
        "files": refs,
        "unbound_retention_seconds": store.UNBOUND_LIFETIME_SECONDS,
        "unbound_expires_at": None if bound else expires,
    }


def upload_app_file(base, *, owner_id, universe_id, metadata, chunks, should_cancel,
                    ready_to_copy, declared_length=None):
    """One exact owned file from a bounded chunk iterator into shared custody.

    ``metadata`` is the parsed header. Owner/home come from the trusted adapter
    only; ``expected_universe_id`` equality is checked by the caller. Same label
    with identical request digest replays committed references (no body read);
    changed metadata conflicts; an unfinished prior copy is held recovery debt.
    """
    if type(owner_id) is not str or not owner_id or type(universe_id) is not str or not universe_id:
        raise store.FileCustodyRefused("file_capture_request_invalid")
    fields = {key: metadata[key] for key in ("filename", "media_type", "size_bytes", "sha256")}
    operation = "file:upload:" + _digest([owner_id, universe_id, metadata["label"]])
    request = _digest([UPLOAD_SOURCE_KIND, owner_id, universe_id, fields])

    def provide_metadata():
        # Only a NEW copy reaches here (committed replay returned earlier), so
        # Content-Length equality applies exactly to the copy it describes.
        if declared_length is not None and declared_length != fields["size_bytes"]:
            raise store.FileCustodyRefused("upload_length_mismatch")
        return [dict(fields)]

    @contextmanager
    def opened(index, expected, cancelled):
        yield chunks()

    @contextmanager
    def fence(expected):
        # No source handle to re-read; current-home/admin/tombstone are checked
        # by the surrounding authority fence (require_current_home=True).
        yield

    return _capture_files(
        base,
        owner_id=owner_id,
        universe_id=universe_id,
        operation=operation,
        request=request,
        metadata_provider=provide_metadata,
        open_source=opened,
        source_fence=fence,
        should_cancel=should_cancel,
        require_current_home=True,
        ready_to_copy=ready_to_copy,
        replay_result=_wrap_result,
    )
