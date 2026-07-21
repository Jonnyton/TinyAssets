"""Content-addressed blob upload and ownership-bound reference attacks."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

JOB_ID = "123e4567-e89b-42d3-a456-426614174001"
LEASE_ID = "123e4567-e89b-42d3-a456-426614174002"


def declaration(content: bytes = b"candidate patch", **overrides: Any) -> dict[str, Any]:
    value = {
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "media_type": "application/vnd.tinyassets.git-diff.v1",
        "confidentiality": "public",
        "job_id": JOB_ID,
        "lease_id": LEASE_ID,
        "fence": 17,
    }
    value.update(overrides)
    return value


def store(tmp_path: Path, **overrides: Any):
    from tinyassets.runtime.blob_refs import BlobStore

    options = {
        "max_blob_bytes": 64,
        "owner_quota_bytes": 128,
        "daemon_quota_bytes": 96,
        "unreferenced_ttl_seconds": 60,
    }
    options.update(overrides)
    return BlobStore(tmp_path / "blob-store", **options)


def init_write(blob_store: Any, decl: dict[str, Any], content: bytes):
    upload = blob_store.init_blob(
        decl,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    blob_store.write_upload(upload.upload_id, content)
    return upload


def test_truncated_upload_is_rejected_at_size_commit(tmp_path: Path) -> None:
    from tinyassets.runtime.blob_refs import BlobSizeMismatchError

    blob_store = store(tmp_path)
    upload = init_write(blob_store, declaration(b"abcdef"), b"abc")
    with pytest.raises(BlobSizeMismatchError):
        blob_store.commit_blob(
            upload.upload_id,
            owner_user_id="user:owner-1",
            daemon_id="daemon:builder-1",
        )


def test_same_size_hash_substitution_is_rejected(tmp_path: Path) -> None:
    from tinyassets.runtime.blob_refs import BlobHashMismatchError

    blob_store = store(tmp_path)
    upload = init_write(blob_store, declaration(b"good"), b"evil")
    with pytest.raises(BlobHashMismatchError):
        blob_store.commit_blob(
            upload.upload_id,
            owner_user_id="user:owner-1",
            daemon_id="daemon:builder-1",
        )


def test_blob_and_per_owner_quota_reject_oversized_artifact(tmp_path: Path) -> None:
    from tinyassets.runtime.blob_refs import BlobQuotaError

    blob_store = store(tmp_path, max_blob_bytes=8, owner_quota_bytes=12)
    with pytest.raises(BlobQuotaError):
        blob_store.init_blob(
            declaration(b"x" * 9),
            owner_user_id="user:owner-1",
            daemon_id="daemon:builder-1",
        )

    first = init_write(blob_store, declaration(b"a" * 7), b"a" * 7)
    blob_store.commit_blob(
        first.upload_id,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    with pytest.raises(BlobQuotaError):
        blob_store.init_blob(
            declaration(b"b" * 6),
            owner_user_id="user:owner-1",
            daemon_id="daemon:other-device",
        )


def test_per_daemon_quota_counts_pending_reservations(tmp_path: Path) -> None:
    from tinyassets.runtime.blob_refs import BlobQuotaError

    blob_store = store(
        tmp_path,
        max_blob_bytes=20,
        owner_quota_bytes=100,
        daemon_quota_bytes=10,
    )
    blob_store.init_blob(
        declaration(b"a" * 6),
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    with pytest.raises(BlobQuotaError, match="per-daemon"):
        blob_store.init_blob(
            declaration(
                b"b" * 5,
                job_id="123e4567-e89b-42d3-a456-426614174099",
            ),
            owner_user_id="user:owner-1",
            daemon_id="daemon:builder-1",
        )


@pytest.mark.parametrize(
    ("owner_quota_bytes", "daemon_quota_bytes", "message"),
    [(10, 100, "per-owner"), (100, 10, "per-daemon")],
)
def test_same_hash_pending_uploads_each_consume_quota(
    tmp_path: Path,
    owner_quota_bytes: int,
    daemon_quota_bytes: int,
    message: str,
) -> None:
    from tinyassets.runtime.blob_refs import BlobQuotaError

    blob_store = store(
        tmp_path,
        max_blob_bytes=20,
        owner_quota_bytes=owner_quota_bytes,
        daemon_quota_bytes=daemon_quota_bytes,
    )
    content = b"a" * 6
    init_write(blob_store, declaration(content), content)
    with pytest.raises(BlobQuotaError, match=message):
        blob_store.init_blob(
            declaration(
                content,
                job_id="123e4567-e89b-42d3-a456-426614174099",
            ),
            owner_user_id="user:owner-1",
            daemon_id="daemon:builder-1",
        )


def test_daemon_quota_aggregates_pending_uploads_across_owners(tmp_path: Path) -> None:
    from tinyassets.runtime.blob_refs import BlobQuotaError

    blob_store = store(
        tmp_path,
        max_blob_bytes=20,
        owner_quota_bytes=100,
        daemon_quota_bytes=10,
    )
    first_content = b"a" * 6
    first = blob_store.init_blob(
        declaration(first_content),
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    blob_store.write_upload(first.upload_id, first_content)
    with pytest.raises(BlobQuotaError, match="per-daemon"):
        blob_store.init_blob(
            declaration(b"b" * 5),
            owner_user_id="user:owner-2",
            daemon_id="daemon:builder-1",
        )


def test_duplicate_commit_is_idempotent_and_does_not_rewrite_object(
    tmp_path: Path,
) -> None:
    blob_store = store(tmp_path)
    content = b"one immutable object"
    upload = init_write(blob_store, declaration(content), content)
    first = blob_store.commit_blob(
        upload.upload_id,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    object_stat = next((tmp_path / "blob-store" / "objects").rglob(first.sha256)).stat()

    second = blob_store.commit_blob(
        upload.upload_id,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    assert second == first
    assert next((tmp_path / "blob-store" / "objects").rglob(first.sha256)).stat() == object_stat


def test_duplicate_init_reuses_one_pending_upload(tmp_path: Path) -> None:
    blob_store = store(tmp_path)
    declared = declaration(b"same declaration")
    first = blob_store.init_blob(
        declared,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    second = blob_store.init_blob(
        declared,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    assert second == first


def test_corrupted_platform_object_is_never_referenceable(tmp_path: Path) -> None:
    from tinyassets.runtime.blob_refs import BlobHashMismatchError

    blob_store = store(tmp_path)
    content = b"integrity guarded"
    upload = init_write(blob_store, declaration(content), content)
    ref = blob_store.commit_blob(
        upload.upload_id,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    object_path = next((tmp_path / "blob-store" / "objects").rglob(ref.sha256))
    object_path.write_bytes(b"x" * len(content))
    with pytest.raises(BlobHashMismatchError):
        blob_store.validate_reference(
            ref.ref,
            owner_user_id="user:owner-1",
            job_id=JOB_ID,
            lease_id=LEASE_ID,
            fence=17,
            expected_sha256=ref.sha256,
            expected_size_bytes=ref.size_bytes,
        )


def test_commit_rejects_same_size_corrupt_existing_object_and_preserves_staging(
    tmp_path: Path,
) -> None:
    from tinyassets.runtime.blob_refs import BlobHashMismatchError

    blob_store = store(tmp_path)
    content = b"verified staging bytes"
    declared = declaration(content)
    upload = init_write(blob_store, declared, content)
    object_path = (
        tmp_path
        / "blob-store"
        / "objects"
        / declared["sha256"][:2]
        / declared["sha256"]
    )
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(b"x" * len(content))
    staging_path = tmp_path / "blob-store" / "uploads" / f"{upload.upload_id}.part"

    with pytest.raises(BlobHashMismatchError):
        blob_store.commit_blob(
            upload.upload_id,
            owner_user_id="user:owner-1",
            daemon_id="daemon:builder-1",
        )
    assert staging_path.read_bytes() == content

    object_path.unlink()
    ref = blob_store.commit_blob(
        upload.upload_id,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    assert ref.sha256 == declared["sha256"]


@pytest.mark.parametrize(
    "binding_override",
    [
        {"job_id": "123e4567-e89b-42d3-a456-426614174099"},
        {"lease_id": "123e4567-e89b-42d3-a456-426614174099"},
        {"fence": 18},
        {"owner_user_id": "user:owner-2"},
    ],
)
def test_cross_job_owner_lease_or_fence_blob_reference_is_rejected(
    tmp_path: Path, binding_override: dict[str, Any]
) -> None:
    from tinyassets.runtime.blob_refs import BlobBindingError

    blob_store = store(tmp_path)
    content = b"bound candidate"
    upload = init_write(blob_store, declaration(content), content)
    ref = blob_store.commit_blob(
        upload.upload_id,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    expected = {
        "blob_ref": ref.ref,
        "owner_user_id": "user:owner-1",
        "job_id": JOB_ID,
        "lease_id": LEASE_ID,
        "fence": 17,
        "expected_sha256": ref.sha256,
        "expected_size_bytes": ref.size_bytes,
    }
    expected.update(binding_override)
    with pytest.raises(BlobBindingError):
        blob_store.validate_reference(**expected)


def test_blob_declaration_and_owner_ref_reject_path_material(tmp_path: Path) -> None:
    from tinyassets.runtime.blob_refs import BlobPolicyError, BlobSchemaError

    blob_store = store(tmp_path)
    with pytest.raises((BlobPolicyError, BlobSchemaError)):
        blob_store.init_blob(
            declaration(path="C:\\host\\secret"),
            owner_user_id="user:owner-1",
            daemon_id="daemon:builder-1",
        )

    private = declaration(confidentiality="owner_private")
    with pytest.raises(BlobPolicyError):
        blob_store.register_owner_blob(
            private,
            owner_user_id="user:owner-1",
            daemon_id="daemon:builder-1",
            owner_blob_ref="file:///host/private.bin",
            possession_proof=b"proof",
            verify_possession=lambda *_: True,
        )


def test_owner_private_ref_is_registered_without_platform_plaintext(tmp_path: Path) -> None:
    blob_store = store(tmp_path)
    content = b"owner private bytes"
    ref = blob_store.register_owner_blob(
        declaration(content, confidentiality="owner_private"),
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
        owner_blob_ref="owner-cas:opaque-private-object",
        possession_proof=b"signed-range-proof",
        verify_possession=lambda decl, ref, proof: (
            decl["sha256"] == hashlib.sha256(content).hexdigest()
            and ref.startswith("owner-cas:")
            and proof == b"signed-range-proof"
        ),
    )
    assert ref.owner_controlled is True
    assert not any((tmp_path / "blob-store" / "objects").rglob(ref.sha256))
    assert "path" not in vars(ref)


def test_pending_upload_reservation_expires_and_frees_quota(tmp_path: Path) -> None:
    blob_store = store(
        tmp_path,
        max_blob_bytes=10,
        owner_quota_bytes=10,
        daemon_quota_bytes=10,
    )
    pending_content = b"a" * 10
    init_write(blob_store, declaration(pending_content), pending_content)
    collected = blob_store.collect_garbage(now=datetime.now(UTC) + timedelta(seconds=61))
    assert collected == (f"blob:sha256:{hashlib.sha256(pending_content).hexdigest()}",)
    blob_store.init_blob(
        declaration(b"b" * 10),
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )


def test_failed_unreferenced_blob_is_collected_after_ttl_and_index_survives_restart(
    tmp_path: Path,
) -> None:
    from tinyassets.runtime.blob_refs import BlobBindingError, BlobStore

    blob_store = store(tmp_path)
    content = b"failed job output"
    upload = init_write(blob_store, declaration(content), content)
    ref = blob_store.commit_blob(
        upload.upload_id,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    restarted = BlobStore(
        tmp_path / "blob-store",
        max_blob_bytes=64,
        owner_quota_bytes=128,
        daemon_quota_bytes=96,
        unreferenced_ttl_seconds=60,
    )
    restarted.validate_reference(
        ref.ref,
        owner_user_id="user:owner-1",
        job_id=JOB_ID,
        lease_id=LEASE_ID,
        fence=17,
        expected_sha256=ref.sha256,
        expected_size_bytes=ref.size_bytes,
    )
    failed_at = datetime(2026, 7, 19, tzinfo=UTC)
    restarted.mark_job_failed(owner_user_id="user:owner-1", job_id=JOB_ID, failed_at=failed_at)
    assert restarted.collect_garbage(now=failed_at + timedelta(seconds=59)) == ()
    assert restarted.collect_garbage(now=failed_at + timedelta(seconds=61)) == (ref.ref,)
    with pytest.raises(BlobBindingError):
        restarted.validate_reference(
            ref.ref,
            owner_user_id="user:owner-1",
            job_id=JOB_ID,
            lease_id=LEASE_ID,
            fence=17,
            expected_sha256=ref.sha256,
            expected_size_bytes=ref.size_bytes,
        )


def test_blob_store_lock_identity_collapses_windows_extended_path_alias(
    tmp_path: Path,
) -> None:
    from tinyassets.runtime.blob_refs import BlobStore

    root = (tmp_path / "blob-store").resolve()
    ordinary = BlobStore(root)
    extended = BlobStore(f"\\\\?\\{root}")

    assert ordinary._lock is extended._lock


def test_two_live_blob_stores_do_not_lose_each_others_committed_bindings(
    tmp_path: Path,
) -> None:
    from tinyassets.runtime.blob_refs import BlobStore

    root = tmp_path / "blob-store"
    first = BlobStore(root)
    second = BlobStore(root)
    first_content = b"first concurrent binding"
    first_decl = declaration(first_content)
    first_upload = init_write(first, first_decl, first_content)
    first_ref = first.commit_blob(
        first_upload.upload_id,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )
    second_content = b"second concurrent binding"
    second_decl = declaration(
        second_content,
        job_id="123e4567-e89b-42d3-a456-426614174099",
    )
    second_upload = init_write(second, second_decl, second_content)
    second_ref = second.commit_blob(
        second_upload.upload_id,
        owner_user_id="user:owner-1",
        daemon_id="daemon:builder-1",
    )

    restarted = BlobStore(root)
    for ref, declared in ((first_ref, first_decl), (second_ref, second_decl)):
        restarted.validate_reference(
            ref.ref,
            owner_user_id="user:owner-1",
            job_id=declared["job_id"],
            lease_id=declared["lease_id"],
            fence=declared["fence"],
            expected_sha256=ref.sha256,
            expected_size_bytes=ref.size_bytes,
        )
