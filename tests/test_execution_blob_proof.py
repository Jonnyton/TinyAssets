from __future__ import annotations

import dataclasses
import hashlib
import json
import multiprocessing
import os
import sqlite3
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest


def _blob_api():
    try:
        from tinyassets.execution_authority.blob_proof import (
            BlobProofError,
            BlobProofStore,
            BlobRef,
            physical_root_identity,
        )
    except ImportError as exc:
        pytest.fail(f"D0 blob-proof API is missing: {exc}")
    return BlobProofError, BlobProofStore, BlobRef, physical_root_identity


def _put_blob_in_process(
    root: str,
    started: multiprocessing.synchronize.Event,
    finished: multiprocessing.synchronize.Event,
) -> None:
    from tinyassets.execution_authority.blob_proof import BlobProofStore

    started.set()
    BlobProofStore(Path(root)).put_blob("child.bin", b"child")
    finished.set()


def _make_directory_alias(alias: Path, root: Path) -> None:
    try:
        alias.symlink_to(root, target_is_directory=True)
        return
    except OSError as symlink_error:
        if os.name != "nt":
            pytest.skip(f"directory symlink proof NOT-RUN on this host: {symlink_error}")
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(alias), str(root)],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        pytest.skip(
            "directory alias proof NOT-RUN: Windows symlink privilege is absent "
            f"and junction creation failed ({result.stderr.strip()})"
        )


def test_verify_blob_rereads_exact_bytes_and_mints_m2_evidence(tmp_path: Path) -> None:
    _, BlobProofStore, _, _ = _blob_api()
    store = BlobProofStore(tmp_path)
    ref = store.put_blob("results/output.bin", b"verified bytes")

    verified = store.verify_blob(ref, verified_at=123)

    assert verified.value == ref
    assert verified.mechanism == "m2"
    assert verified.domain == "tinyassets.blob-ref.v1"
    assert verified.evidence_digest == hashlib.sha256(b"verified bytes").hexdigest()
    assert verified.verified_at == 123


def test_blob_store_exposes_no_raw_m2_mint_method(tmp_path: Path) -> None:
    _, BlobProofStore, _, _ = _blob_api()

    assert not hasattr(BlobProofStore(tmp_path), "_mint_verified")


def test_signed_metadata_or_raw_reference_cannot_replace_fresh_blob_proof(
    tmp_path: Path,
) -> None:
    BlobProofError, BlobProofStore, BlobRef, _ = _blob_api()
    store = BlobProofStore(tmp_path)
    ref = store.put_blob("result.bin", b"first")
    (tmp_path / "result.bin").write_bytes(b"other")

    with pytest.raises(BlobProofError, match="digest|size"):
        store.verify_blob(ref, verified_at=124)

    forged = BlobRef(relative_path="result.bin", sha256="0" * 64, size=5)
    with pytest.raises(BlobProofError, match="index|digest"):
        store.verify_blob(forged, verified_at=125)


def test_wrong_byte_mutation_is_forced_between_index_load_and_exact_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    BlobProofError, BlobProofStore, _, _ = _blob_api()
    store = BlobProofStore(tmp_path)
    ref = store.put_blob("result.bin", b"right")
    target = tmp_path / "result.bin"
    mutate = threading.Event()
    mutated = threading.Event()

    def writer() -> None:
        assert mutate.wait(5)
        target.write_bytes(b"wrong")
        mutated.set()

    worker = threading.Thread(target=writer)
    worker.start()
    original_read = store._read_regular_file

    def interleaved_read(path: Path, **kwargs: Any) -> bytes:
        if path == target:
            mutate.set()
            assert mutated.wait(5)
        return original_read(path, **kwargs)

    monkeypatch.setattr(store, "_read_regular_file", interleaved_read)
    with pytest.raises(BlobProofError, match="digest|size|changed"):
        store.verify_blob(ref, verified_at=125)
    worker.join(5)
    assert not worker.is_alive()


def test_in_place_mutation_after_read_before_mint_cannot_escape_as_m2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    BlobProofError, BlobProofStore, _, _ = _blob_api()
    store = BlobProofStore(tmp_path)
    ref = store.put_blob("result.bin", b"right")
    target = tmp_path / "result.bin"
    original_read = store._read_regular_file

    def mutate_after_read(path: Path, **kwargs: Any) -> Any:
        result = original_read(path, **kwargs)
        if path == target:
            target.write_bytes(b"wrong")
        return result

    monkeypatch.setattr(store, "_read_regular_file", mutate_after_read)
    with pytest.raises(BlobProofError, match="changed|digest|size"):
        store.verify_blob(ref, verified_at=125)


def test_in_place_mutation_with_restored_mtime_cannot_escape_as_m2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    BlobProofError, BlobProofStore, _, _ = _blob_api()
    store = BlobProofStore(tmp_path)
    ref = store.put_blob("result.bin", b"right")
    target = tmp_path / "result.bin"
    original_read = store._read_regular_file

    def mutate_after_read(path: Path, **kwargs: Any) -> Any:
        result = original_read(path, **kwargs)
        if path == target:
            snapshot = result.snapshot
            target.write_bytes(b"wrong")
            os.utime(
                target,
                ns=(snapshot.st_atime_ns, snapshot.st_mtime_ns),
            )
        return result

    monkeypatch.setattr(store, "_read_regular_file", mutate_after_read)
    with pytest.raises(BlobProofError, match="changed|digest|size"):
        store.verify_blob(ref, verified_at=125)


def test_store_reloads_index_for_each_operation_across_instances(tmp_path: Path) -> None:
    _, BlobProofStore, _, _ = _blob_api()
    first = BlobProofStore(tmp_path)
    second = BlobProofStore(tmp_path)

    alpha = first.put_blob("alpha.bin", b"alpha")
    beta = second.put_blob("beta.bin", b"beta")

    assert first.list_refs() == (alpha, beta)
    assert second.list_refs() == (alpha, beta)


def test_collected_binding_cannot_be_resurrected_by_stale_instance(
    tmp_path: Path,
) -> None:
    BlobProofError, BlobProofStore, _, _ = _blob_api()
    first = BlobProofStore(tmp_path)
    stale = BlobProofStore(tmp_path)
    ref = first.put_blob("collected.bin", b"ephemeral")

    first.collect_blob(ref)

    with pytest.raises(BlobProofError, match="index|collected|missing"):
        stale.verify_blob(ref, verified_at=126)


def test_forced_stale_index_interleaving_cannot_overtake_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    BlobProofError, BlobProofStore, _, _ = _blob_api()
    verifier = BlobProofStore(tmp_path)
    collector = BlobProofStore(tmp_path)
    ref = verifier.put_blob("collected.bin", b"ephemeral")
    index_loaded = threading.Event()
    release_verifier = threading.Event()
    collection_finished = threading.Event()
    original_load = verifier._load_index

    def paused_load():
        index = original_load()
        index_loaded.set()
        assert release_verifier.wait(5)
        return index

    monkeypatch.setattr(verifier, "_load_index", paused_load)
    verified: list[Any] = []
    verify_thread = threading.Thread(
        target=lambda: verified.append(verifier.verify_blob(ref, verified_at=126))
    )
    collect_thread = threading.Thread(
        target=lambda: (
            collector.collect_blob(ref),
            collection_finished.set(),
        )
    )
    verify_thread.start()
    assert index_loaded.wait(5)
    collect_thread.start()
    assert not collection_finished.wait(0.25)
    release_verifier.set()
    verify_thread.join(5)
    collect_thread.join(5)

    assert verified[0].value == ref
    assert collection_finished.is_set()
    with pytest.raises(BlobProofError, match="index|collected|missing"):
        BlobProofStore(tmp_path).verify_blob(ref, verified_at=127)


def test_replaced_binding_rejects_the_old_reference(tmp_path: Path) -> None:
    BlobProofError, BlobProofStore, _, _ = _blob_api()
    store = BlobProofStore(tmp_path)
    stale = store.put_blob("result.bin", b"old")
    current = store.put_blob("result.bin", b"new")

    with pytest.raises(BlobProofError, match="index|stale"):
        store.verify_blob(stale, verified_at=126)

    assert store.verify_blob(current, verified_at=127).value == current


def test_blob_refs_are_immutable_and_validate_their_contract() -> None:
    _, _, BlobRef, _ = _blob_api()
    ref = BlobRef(relative_path="result.bin", sha256="0" * 64, size=0)

    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.size = 1
    with pytest.raises((TypeError, ValueError)):
        BlobRef(relative_path="../result.bin", sha256="0" * 64, size=0)
    with pytest.raises((TypeError, ValueError)):
        BlobRef(relative_path="result.bin", sha256="not-a-digest", size=0)


def test_malformed_index_fails_closed_instead_of_being_repaired(tmp_path: Path) -> None:
    BlobProofError, BlobProofStore, _, _ = _blob_api()
    (tmp_path / ".blob-index.json").write_text(
        json.dumps({"version": 1, "blobs": [], "unexpected": True}),
        encoding="utf-8",
    )

    with pytest.raises(BlobProofError, match="index"):
        BlobProofStore(tmp_path).list_refs()

    assert "unexpected" in (tmp_path / ".blob-index.json").read_text(encoding="utf-8")


def test_paths_cannot_escape_the_physical_blob_root(tmp_path: Path) -> None:
    BlobProofError, BlobProofStore, BlobRef, _ = _blob_api()
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    store = BlobProofStore(root)

    with pytest.raises(BlobProofError, match="relative|escape|root"):
        store.put_blob("../outside.bin", b"replace")

    ref = object.__new__(BlobRef)
    object.__setattr__(ref, "relative_path", "../outside.bin")
    object.__setattr__(ref, "sha256", hashlib.sha256(b"outside").hexdigest())
    object.__setattr__(ref, "size", 7)
    with pytest.raises(BlobProofError, match="relative|escape|root"):
        store.verify_blob(ref, verified_at=127)


def test_symlinked_blob_path_cannot_escape_the_physical_root(tmp_path: Path) -> None:
    BlobProofError, BlobProofStore, _, _ = _blob_api()
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "link"
    _make_directory_alias(link, outside)

    with pytest.raises(BlobProofError, match="symlink|reparse|escape|root"):
        BlobProofStore(root).put_blob("link/escaped.bin", b"escaped")

    assert not (outside / "escaped.bin").exists()


def test_dot_alias_shares_one_physical_identity(tmp_path: Path) -> None:
    _, _, _, physical_root_identity = _blob_api()
    root = tmp_path / "root"
    root.mkdir()

    assert physical_root_identity(root) == physical_root_identity(root / ".")


def test_supported_root_aliases_share_one_physical_identity(tmp_path: Path) -> None:
    _, BlobProofStore, _, physical_root_identity = _blob_api()
    root = tmp_path / "root"
    root.mkdir()
    alias = tmp_path / "alias"
    _make_directory_alias(alias, root)

    assert physical_root_identity(alias) == physical_root_identity(root)
    first = BlobProofStore(root)
    second = BlobProofStore(alias)
    alpha = first.put_blob("alpha.bin", b"alpha")
    beta = second.put_blob("beta.bin", b"beta")
    assert first.list_refs() == (alpha, beta)


def test_windows_case_and_extended_path_aliases_converge(tmp_path: Path) -> None:
    if os.name != "nt":
        pytest.skip("Windows case/extended-path alias proof NOT-RUN on this non-Windows host")
    _, BlobProofStore, _, physical_root_identity = _blob_api()
    root = (tmp_path / "Root").resolve()
    root.mkdir()
    case_alias = Path(str(root).swapcase())
    extended_alias = Path("\\\\?\\" + str(root))

    assert physical_root_identity(case_alias) == physical_root_identity(root)
    assert physical_root_identity(extended_alias) == physical_root_identity(root)
    first = BlobProofStore(case_alias)
    second = BlobProofStore(extended_alias)
    alpha = first.put_blob("alpha.bin", b"alpha")
    beta = second.put_blob("beta.bin", b"beta")
    assert first.list_refs() == (alpha, beta)


def test_concurrent_instances_do_not_lose_index_updates(tmp_path: Path) -> None:
    _, BlobProofStore, _, _ = _blob_api()
    first = BlobProofStore(tmp_path)
    second = BlobProofStore(tmp_path)

    def write(i: int):
        store = first if i % 2 else second
        return store.put_blob(f"{i:02}.bin", str(i).encode())

    with ThreadPoolExecutor(max_workers=8) as pool:
        expected = tuple(pool.map(write, range(32)))

    assert first.list_refs() == tuple(sorted(expected, key=lambda ref: ref.relative_path))


def test_coordinated_context_serializes_a_separate_process(tmp_path: Path) -> None:
    _, BlobProofStore, _, _ = _blob_api()
    context = multiprocessing.get_context("spawn")
    started = context.Event()
    finished = context.Event()
    process = context.Process(
        target=_put_blob_in_process,
        args=(str(tmp_path), started, finished),
    )

    store = BlobProofStore(tmp_path)
    with store.coordinated():
        process.start()
        assert started.wait(5)
        assert not finished.wait(0.25)

    assert finished.wait(5)
    process.join(5)
    assert process.exitcode == 0
    assert store.list_refs()[0].relative_path == "child.bin"


@pytest.mark.parametrize("first_store_index", [0, 1])
def test_coordinated_transaction_enforces_blob_then_sqlite_in_both_orders(
    tmp_path: Path,
    first_store_index: int,
) -> None:
    _, BlobProofStore, _, _ = _blob_api()
    root = tmp_path / "blobs"
    root.mkdir()
    stores = (BlobProofStore(root), BlobProofStore(root / "."))
    database = tmp_path / "authority.sqlite"
    seed = sqlite3.connect(database)
    seed.execute("CREATE TABLE decisions (name TEXT PRIMARY KEY)")
    seed.commit()
    seed.close()

    first_factory_called = threading.Event()
    first_sqlite_entered = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_factory_called = threading.Event()
    errors: list[BaseException] = []

    def transaction(
        name: str,
        *,
        factory_called: threading.Event,
        hold: bool,
    ) -> Iterator[sqlite3.Connection]:
        factory_called.set()
        connection = sqlite3.connect(database, timeout=0.1, isolation_level=None)
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute("INSERT INTO decisions VALUES (?)", (name,))
            if hold:
                first_sqlite_entered.set()
                assert release_first.wait(5)
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def run_first() -> None:
        try:
            with stores[first_store_index].coordinated_transaction(
                lambda: contextmanager(transaction)(
                    "first",
                    factory_called=first_factory_called,
                    hold=True,
                )
            ):
                pass
        except BaseException as exc:
            errors.append(exc)

    def run_second() -> None:
        second_started.set()
        try:
            with stores[1 - first_store_index].coordinated_transaction(
                lambda: contextmanager(transaction)(
                    "second",
                    factory_called=second_factory_called,
                    hold=False,
                )
            ):
                pass
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=run_first)
    second = threading.Thread(target=run_second)
    first.start()
    assert first_factory_called.wait(5)
    assert first_sqlite_entered.wait(5)
    second.start()
    assert second_started.wait(5)
    assert not second_factory_called.wait(0.25)
    release_first.set()
    first.join(5)
    second.join(5)

    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    check = sqlite3.connect(database)
    try:
        assert check.execute("SELECT name FROM decisions ORDER BY name").fetchall() == [
            ("first",),
            ("second",),
        ]
    finally:
        check.close()


def test_parent_swap_cannot_redirect_an_atomic_blob_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    BlobProofError, BlobProofStore, _, _ = _blob_api()
    root = tmp_path / "root"
    parent = root / "nested"
    parent.mkdir(parents=True)
    moved = root / "moved"
    store = BlobProofStore(root)
    swap_now = threading.Event()
    swap_done = threading.Event()
    swap_succeeded = threading.Event()

    def swap_parent() -> None:
        assert swap_now.wait(5)
        try:
            parent.rename(moved)
            parent.mkdir()
            swap_succeeded.set()
        except OSError:
            pass
        finally:
            swap_done.set()

    worker = threading.Thread(target=swap_parent)
    worker.start()
    original_replace = store._atomic_replace
    first_call = True

    def interleaved_replace(*args: Any, **kwargs: Any) -> None:
        nonlocal first_call
        if first_call:
            first_call = False
            swap_now.set()
            assert swap_done.wait(5)
        original_replace(*args, **kwargs)

    monkeypatch.setattr(store, "_atomic_replace", interleaved_replace)
    error: BlobProofError | None = None
    try:
        store.put_blob("nested/result.bin", b"verified")
    except BlobProofError as exc:
        error = exc
    worker.join(5)

    if swap_succeeded.is_set():
        assert error is not None
        assert not (parent / "result.bin").exists()
    else:
        assert error is None
        assert (parent / "result.bin").read_bytes() == b"verified"


def test_parent_swap_cannot_redirect_an_exact_blob_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    BlobProofError, BlobProofStore, _, _ = _blob_api()
    root = tmp_path / "root"
    parent = root / "nested"
    parent.mkdir(parents=True)
    moved = root / "moved"
    store = BlobProofStore(root)
    ref = store.put_blob("nested/result.bin", b"verified")
    target = parent / "result.bin"
    swap_now = threading.Event()
    swap_done = threading.Event()
    swap_succeeded = threading.Event()

    def swap_parent() -> None:
        assert swap_now.wait(5)
        try:
            parent.rename(moved)
            parent.mkdir()
            (parent / "result.bin").write_bytes(b"verified")
            swap_succeeded.set()
        except OSError:
            pass
        finally:
            swap_done.set()

    worker = threading.Thread(target=swap_parent)
    worker.start()
    original_read = store._read_regular_file

    def interleaved_read(path: Path, **kwargs: Any) -> bytes:
        if path == target:
            swap_now.set()
            assert swap_done.wait(5)
        return original_read(path, **kwargs)

    monkeypatch.setattr(store, "_read_regular_file", interleaved_read)
    error: BlobProofError | None = None
    try:
        store.verify_blob(ref, verified_at=128)
    except BlobProofError as exc:
        error = exc
    worker.join(5)

    if swap_succeeded.is_set():
        assert error is not None
    else:
        assert error is None


def test_leaf_swap_during_exact_read_cannot_mint_from_unlinked_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    BlobProofError, BlobProofStore, _, _ = _blob_api()
    store = BlobProofStore(tmp_path)
    ref = store.put_blob("result.bin", b"verified")
    target = tmp_path / "result.bin"
    moved = tmp_path / "moved.bin"
    original_inode = target.stat().st_ino
    original_read = os.read
    swap_succeeded = False

    def swapping_read(fd: int, size: int) -> bytes:
        nonlocal swap_succeeded
        if not swap_succeeded and os.fstat(fd).st_ino == original_inode:
            try:
                target.rename(moved)
                target.write_bytes(b"verified")
                swap_succeeded = True
            except OSError:
                pass
        return original_read(fd, size)

    monkeypatch.setattr(os, "read", swapping_read)
    error: BlobProofError | None = None
    try:
        store.verify_blob(ref, verified_at=129)
    except BlobProofError as exc:
        error = exc

    if swap_succeeded:
        assert error is not None
    else:
        assert error is None


def test_windows_lock_retries_beyond_msvcrt_internal_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows LK_NBLCK retry proof NOT-RUN on this non-Windows host")
    import msvcrt

    from tinyassets.execution_authority import blob_proof

    path = tmp_path / "lock"
    path.write_bytes(b"\0")
    fd = os.open(path, os.O_RDWR)
    calls = 0
    sleeps: list[float] = []

    def contended_then_acquired(lock_fd: int, mode: int, size: int) -> None:
        nonlocal calls
        calls += 1
        if calls <= 12:
            raise OSError(13, "simulated contention")

    monkeypatch.setattr(msvcrt, "locking", contended_then_acquired)
    monkeypatch.setattr(blob_proof.time, "sleep", sleeps.append)
    try:
        blob_proof._lock_fd(fd)
    finally:
        os.close(fd)

    assert calls == 13
    assert len(sleeps) == 12
    assert all(0 < delay <= 0.1 for delay in sleeps)


def test_lock_file_descriptor_closes_when_acquisition_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tinyassets.execution_authority import blob_proof

    coordinator = blob_proof._PhysicalRootCoordinator(
        tmp_path,
        blob_proof.physical_root_identity(tmp_path),
    )
    path = tmp_path / "failing-lock"
    path.write_bytes(b"\0")
    fd = os.open(path, os.O_RDWR)
    monkeypatch.setattr(coordinator, "_open_lock_file", lambda: fd)
    monkeypatch.setattr(
        blob_proof,
        "_lock_fd",
        lambda _fd: (_ for _ in ()).throw(RuntimeError("lock failed")),
    )

    with pytest.raises(RuntimeError, match="lock failed"):
        coordinator.acquire()
    with pytest.raises(OSError):
        os.fstat(fd)
