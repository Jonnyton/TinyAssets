"""Native-platform exact binary streams; no workspace quiescence claim."""

from __future__ import annotations

import errno
import hashlib
import os
import threading
import tracemalloc

import pytest

from tinyassets.execution_authority.blob_proof import BlobProofError, BlobProofStore, BlobRef


def test_large_binary_stream_and_chunk_readback_without_blob_index(tmp_path):
    store = BlobProofStore(tmp_path)
    chunk = bytes(range(256)) * 256
    count = 160  # 10 MiB, greater than the authoring-only whole-file ceiling.
    expected = hashlib.sha256()
    for _ in range(count):
        expected.update(chunk)
    tracemalloc.start()
    try:
        staged = store.stage_stream(
            "item.part", (chunk for _ in range(count)), max_bytes=len(chunk) * count
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 3 * 1024 * 1024
    assert staged.sha256 == expected.hexdigest()
    final = store.publish_staged(staged, "item.body")
    assert not (tmp_path / "item.part").exists()
    assert not (tmp_path / ".blob-index.json").exists()
    actual = hashlib.sha256()
    with store.open_held_stream(final) as held:
        for offset in range(0, final.size, len(chunk)):
            actual.update(held.read_range(offset, len(chunk)))
        assert held.read_range(final.size, 10) == b""
    assert actual.hexdigest() == expected.hexdigest()


def test_zero_byte_body_is_real_and_publish_never_overwrites(tmp_path):
    store = BlobProofStore(tmp_path)
    staged = store.stage_stream("empty.part", iter(()), max_bytes=0)
    final = store.publish_staged(staged, "empty.body")
    with store.open_held_stream(final) as held:
        assert held.read_range(0, 100) == b""
    other = store.stage_stream("other.part", iter([b"other"]), max_bytes=5)
    with pytest.raises(BlobProofError):
        store.publish_staged(other, "empty.body")
    assert (tmp_path / "empty.body").read_bytes() == b""


def test_stream_cancellation_preserves_bounded_inventory_debt(tmp_path):
    store = BlobProofStore(tmp_path)
    calls = []

    def chunks():
        for _ in range(100):
            calls.append(1)
            yield b"x" * 100

    with pytest.raises(BlobProofError, match="cancel") as failure:
        store.stage_stream(
            "cancel.part", chunks(), max_bytes=10000, should_cancel=lambda: len(calls) >= 2
        )
    assert len(calls) == 2
    assert failure.value.bytes_written == 100
    assert (tmp_path / "cancel.part").stat().st_size == 100
    assert not (tmp_path / "cancel.body").exists()


def test_size_bound_and_short_writes_do_not_make_partial_success(tmp_path, monkeypatch):
    store = BlobProofStore(tmp_path)
    write = os.write
    monkeypatch.setattr(os, "write", lambda fd, data: write(fd, data[:3]))
    ref = store.stage_stream("short.part", iter([b"abcdefghij"]), max_bytes=10)
    assert ref.size == 10
    assert (tmp_path / "short.part").read_bytes() == b"abcdefghij"
    with pytest.raises(BlobProofError, match="limit") as failure:
        store.stage_stream("large.part", iter([b"ok", b"too much"]), max_bytes=4)
    assert failure.value.bytes_written == 2
    assert (tmp_path / "large.part").read_bytes() == b"ok"


def test_reader_refuses_tampered_bytes_and_invalid_ranges(tmp_path):
    store = BlobProofStore(tmp_path)
    staged = store.stage_stream("item.part", iter([b"actual"]), max_bytes=6)
    wrong = BlobRef(staged.relative_path, "0" * 64, staged.size)
    with pytest.raises(BlobProofError, match="digest"):
        with store.open_held_stream(wrong):
            pytest.fail("wrong digest opened")
    with store.open_held_stream(staged) as held:
        for offset, size in [(-1, 1), (0, -1), (True, 1), (0, 2 * 1024 * 1024)]:
            with pytest.raises(BlobProofError):
                held.read_range(offset, size)


@pytest.mark.parametrize("unsafe", ["../escape", "/absolute", "a\\b", ".blob-index.json"])
def test_stage_paths_are_constrained(tmp_path, unsafe):
    store = BlobProofStore(tmp_path)
    with pytest.raises(BlobProofError):
        store.stage_stream(unsafe, iter([b"x"]), max_bytes=1)


def test_enospc_preserves_actual_consumed_and_written_counts(tmp_path, monkeypatch):
    store = BlobProofStore(tmp_path)
    original = os.write
    calls = []

    def disk_full(fd, data):
        calls.append(1)
        if len(calls) == 1:
            return original(fd, data[:2])
        raise OSError(errno.ENOSPC, "disposable disk-full simulation")

    monkeypatch.setattr(os, "write", disk_full)
    with pytest.raises(BlobProofError) as failure:
        store.stage_stream("full.part", iter([b"abcdef"]), max_bytes=6)
    assert failure.value.bytes_read == 6
    assert failure.value.bytes_written == 2
    assert (tmp_path / "full.part").read_bytes() == b"ab"


def test_source_error_keeps_inventory_and_accounting(tmp_path):
    store = BlobProofStore(tmp_path)

    def source():
        yield b"first"
        raise RuntimeError("source authorization was revoked")

    with pytest.raises(BlobProofError, match="revoked") as failure:
        store.stage_stream("revoked.part", source(), max_bytes=100)
    assert failure.value.bytes_read == failure.value.bytes_written == 5
    assert (tmp_path / "revoked.part").read_bytes() == b"first"


def test_stream_does_not_hold_root_coordinator_and_close_cancels_promptly(tmp_path):
    store = BlobProofStore(tmp_path)
    started = threading.Event()
    close = threading.Event()
    complete = threading.Event()
    failures = []

    def source():
        yield b"first"
        started.set()
        assert close.wait(2)
        yield b"must not be written"

    def writer():
        try:
            store.stage_stream("cancel.part", source(), max_bytes=1024, should_cancel=close.is_set)
        except BlobProofError as exc:
            failures.append(exc)
        finally:
            complete.set()

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        assert started.wait(2)
        # A close/collector's short root operation is not trapped behind IO.
        with store.coordinated():
            close.set()
        assert complete.wait(2)
    finally:
        close.set()
        thread.join(3)
    assert failures and "cancel" in str(failures[0])
    assert (tmp_path / "cancel.part").read_bytes() == b"first"


def test_ordered_independent_binary_files_are_exact_on_native_platform(tmp_path):
    store = BlobProofStore(tmp_path)
    bodies = [b"\x00\xff\x80", b"", bytes(range(256)) * 6000]
    references = []
    for number, body in enumerate(bodies):
        staged = store.stage_stream(
            f"{number}.part",
            (body[i : i + 65536] for i in range(0, len(body), 65536)),
            max_bytes=len(body),
        )
        references.append(store.publish_staged(staged, f"{number}.body"))
    for body, ref in zip(bodies, references, strict=True):
        with store.open_held_stream(ref) as held:
            observed = b"".join(held.read_range(i, 65536) for i in range(0, ref.size, 65536))
        assert observed == body


def test_reader_checks_cancellation_before_returning_chunk(tmp_path):
    store = BlobProofStore(tmp_path)
    ref = store.stage_stream("item.part", iter([b"private"]), max_bytes=7)
    cancelled = threading.Event()
    with pytest.raises(BlobProofError, match="cancel"):
        with store.open_held_stream(ref, should_cancel=cancelled.is_set) as held:
            cancelled.set()
            held.read_range(0, 7)


def test_publication_does_not_call_authority_predicate_under_physical_coordinator(
    tmp_path, monkeypatch
):
    from contextlib import contextmanager

    store = BlobProofStore(tmp_path)
    staged = store.stage_stream("item.part", iter([b"exact"]), max_bytes=5)
    actual = store.coordinated
    inside = False

    @contextmanager
    def coordinated():
        nonlocal inside
        with actual():
            inside = True
            try:
                yield
            finally:
                inside = False

    def authority_check():
        assert not inside, "metadata authority callback inverted physical-root lock order"
        return False

    monkeypatch.setattr(store, "coordinated", coordinated)
    final = store.publish_staged(staged, "item.body", should_cancel=authority_check)
    assert final.sha256 == staged.sha256


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink/fifo fixture; native Windows above")
def test_stream_rejects_symlink_and_fifo_sources(tmp_path):
    store = BlobProofStore(tmp_path)
    (tmp_path / "real").write_bytes(b"private")
    (tmp_path / "link").symlink_to(tmp_path / "real")
    os.mkfifo(tmp_path / "pipe")
    for name in ["link", "pipe"]:
        ref = BlobRef(name, hashlib.sha256(b"private").hexdigest(), 7)
        with pytest.raises(BlobProofError):
            with store.open_held_stream(ref):
                pytest.fail("unsafe source opened")
