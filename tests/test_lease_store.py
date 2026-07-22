from __future__ import annotations

import base64
import copy
import hashlib
import inspect
import json
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import tinyassets.runtime.lease_store as lease_store_module
from tinyassets.branch_tasks import BranchTask
from tinyassets.runtime.lease_store import (
    AlreadyClaimedError,
    CandidateValidationError,
    InvalidLeaseHolderError,
    Lease,
    LeaseGrantCapsule,
    LeaseGrantIssuer,
    LeaseStore,
    LeaseStoreError,
    RecordReference,
    ResultConflictError,
    StaleFenceError,
    StaleLeaseError,
    StoredStateCorruptError,
    TaskConflictError,
)
from tinyassets.runtime.signed_records import PlatformSigner, RecordVerifier


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class StaticDeviceKeyRegistry:
    def __init__(self, key, *, credential_epoch: int = 1, active: bool = True) -> None:
        self.device_key_id = "device-key:builder-1"
        self.verify_key = key.verify_key
        self.credential_epoch = credential_epoch
        self.active = active

    def resolve_device_key(self, device_key_id: str):
        if device_key_id != self.device_key_id:
            return None
        return SimpleNamespace(
            device_key_id=self.device_key_id,
            verify_key=self.verify_key,
            credential_epoch=self.credential_epoch,
            active=self.active,
        )


def _capsule_key(signing_key, *, active: bool = True):
    return SimpleNamespace(
        signing_key_id="platform-capsule:1",
        verify_key=signing_key.verify_key,
        active=active,
    )


def _authenticated_daemon(*, owner_user_id: str = "user:owner-1"):
    return SimpleNamespace(
        daemon_id="daemon:builder-1",
        owner_user_id=owner_user_id,
        key_thumbprint="device-key:builder-1",
        credential_epoch=1,
    )


class SignalingLeaseStore(LeaseStore):
    def __init__(
        self,
        *args,
        transaction_boundary: threading.Event,
        completion_signer: PlatformSigner | None = None,
        **kwargs,
    ) -> None:
        self._transaction_boundary = transaction_boundary
        self._test_completion_signer = completion_signer
        super().__init__(*args, **kwargs)

    @contextmanager
    def _transaction(self):
        self._transaction_boundary.set()
        with super()._transaction() as connection:
            yield connection

    def complete_validated_result(self, job_id, **kwargs):
        if self._test_completion_signer is not None:
            kwargs.setdefault("completion_signer", self._test_completion_signer)
        return super().complete_validated_result(job_id, **kwargs)


class SigningLeaseStore(LeaseStore):
    """Test harness that supplies the non-retained signer per completion call."""

    def __init__(self, *args, completion_signer: PlatformSigner, **kwargs) -> None:
        self._test_completion_signer = completion_signer
        super().__init__(*args, **kwargs)

    def complete_validated_result(self, job_id, **kwargs):
        kwargs.setdefault("completion_signer", self._test_completion_signer)
        return super().complete_validated_result(job_id, **kwargs)


def _raw_dml_authority_probe(
    store: LeaseStore,
    mutate: Callable[[sqlite3.Connection], None],
    decide: Callable[[], object],
    *,
    match: str,
) -> StoredStateCorruptError:
    """Forge one durable projection and assert the authority sink fails closed."""
    with sqlite3.connect(store.db_path) as connection:
        mutate(connection)
    with pytest.raises(StoredStateCorruptError, match=match) as rejection:
        decide()
    return rejection.value


@contextmanager
def _legacy_attestation_insert(connection: sqlite3.Connection):
    """Install a pre-v7 duplicate row outside the current schema contract."""
    name = "lease_completion_attestations_append_only_insert"
    connection.execute(f"DROP TRIGGER {name}")
    connection.execute(
        "DROP INDEX lease_completion_attestations_task_id_uq"
    )
    try:
        yield
    finally:
        connection.execute(
            lease_store_module._COMPLETION_ATTESTATION_TRIGGERS[name]
        )


def _replace_attestation_table(
    connection: sqlite3.Connection,
    definition: str,
) -> None:
    for name in lease_store_module._COMPLETION_ATTESTATION_TRIGGERS:
        connection.execute(f"DROP TRIGGER IF EXISTS {name}")
    connection.execute("DROP TABLE main.lease_completion_attestations")
    connection.execute(definition)
    connection.execute(
        lease_store_module._COMPLETION_ATTESTATION_TASK_INDEX
    )
    for trigger in lease_store_module._COMPLETION_ATTESTATION_TRIGGERS.values():
        connection.execute(trigger)


def _spoof_canonical_attestation_table_sql(
    connection: sqlite3.Connection,
) -> None:
    connection.execute("PRAGMA writable_schema = ON")
    connection.execute(
        "UPDATE main.sqlite_schema SET sql = ? "
        "WHERE type = 'table' AND name = 'lease_completion_attestations'",
        (lease_store_module._COMPLETION_ATTESTATION_TABLE,),
    )
    connection.execute("PRAGMA writable_schema = OFF")


def test_time_text_is_fixed_width_for_sqlite_expiry_ordering() -> None:
    whole_second = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    next_microsecond = whole_second + timedelta(microseconds=1)

    assert LeaseStore._time_text(whole_second).endswith(".000000Z")
    assert LeaseStore._time_text(next_microsecond).endswith(".000001Z")
    assert LeaseStore._time_text(whole_second) < LeaseStore._time_text(next_microsecond)


def test_completion_store_role_cannot_retain_a_grant_signing_key(tmp_path: Path) -> None:
    from nacl.signing import SigningKey

    assert "grant_signing_key" not in inspect.signature(LeaseStore).parameters
    with pytest.raises(TypeError, match="grant_signing_key"):
        LeaseStore(
            tmp_path / "leases.sqlite3",
            grant_signing_key=SigningKey.generate(),
        )
    signing_key = SigningKey.generate()
    completion_store = LeaseStore(
        tmp_path / "verify-only.sqlite3",
        record_verifier=RecordVerifier(signing_key.verify_key),
    )
    issuer = LeaseGrantIssuer(
        platform_signer=PlatformSigner(signing_key),
        capsule_key=_capsule_key(signing_key),
        supported_request_schema_versions={3},
    )
    assert not hasattr(issuer, "complete_validated_result")
    assert all(not isinstance(value, LeaseStore) for value in vars(issuer).values())
    assert all("signing_key" not in name for name in vars(completion_store))


def _task() -> BranchTask:
    task_id = str(uuid4())
    return BranchTask(
        branch_task_id=task_id,
        branch_def_id="branch-loop",
        universe_id="universe-a",
        queued_at="2026-07-19T12:00:00Z",
    )


def _capsule(seed: str):
    def bind(_lease) -> RecordReference:
        return RecordReference(record_id=str(uuid4()), content_sha256=seed * 64)

    return bind


def _grant_capsule(seed: str, signing_key):
    def bind(lease) -> LeaseGrantCapsule:
        from tests.test_execution_capsule import _payload
        from tinyassets.runtime.execution_capsule import create_execution_capsule

        payload = _payload()
        payload["job_id"] = lease.task_id
        payload["audience_daemon_id"] = lease.daemon_id
        payload["lease"] = {
            "lease_id": lease.lease_id,
            "fence": lease.fence,
            "issued_at": lease.issued_at,
            "expires_at": lease.expires_at,
        }
        payload["issued_at"] = lease.issued_at
        payload["not_before"] = lease.issued_at
        payload["expires_at"] = lease.expires_at
        payload["model_broker_route"]["expires_at"] = lease.expires_at
        payload["allowed_capability"].update(
            runner_policy_sha256="c" * 64,
            image_digest=f"sha256:{'d' * 64}",
        )
        capsule = create_execution_capsule(
            payload,
            signing_key=signing_key,
            signing_key_id="platform-capsule:1",
        )
        raw_capsule = json.dumps(capsule, separators=(",", ":")).encode()
        return LeaseGrantCapsule(
            raw_capsule=raw_capsule,
        )

    return bind


@dataclass(frozen=True)
class ResultLeaseFixture:
    values: tuple
    issuer: LeaseGrantIssuer
    capsule_signing_key: object

    def __iter__(self):
        return iter(self.values)


def _claim(store: LeaseStore, task_id: str, daemon_id: str, seed: str = "a"):
    return store.claim(
        task_id,
        daemon_id=daemon_id,
        bind_capsule=_capsule(seed),
        lease_seconds=120,
    )


def test_authenticated_claim_requires_signed_capsule_and_active_capsule_key(
    tmp_path: Path,
) -> None:
    from nacl.signing import SigningKey

    device_key = SigningKey.generate()
    grant_key = SigningKey.generate()
    registry = StaticDeviceKeyRegistry(device_key)
    store = LeaseStore(
        tmp_path / "leases.sqlite3",
        key_registry=registry,
        record_verifier=RecordVerifier(grant_key.verify_key),
    )
    issuer = LeaseGrantIssuer(
        platform_signer=PlatformSigner(grant_key),
        capsule_key=_capsule_key(grant_key),
        supported_request_schema_versions={3},
    )
    task = _task()
    store.add_task(task)
    signed_binder = _grant_capsule("a", grant_key)

    def tampered_binder(identity):
        bound = signed_binder(identity)
        capsule = json.loads(bound.raw_capsule)
        capsule["payload"]["allowed_capability"]["repo_mode"] = "repo_exec"
        return replace(
            bound,
            raw_capsule=json.dumps(capsule, separators=(",", ":")).encode(),
        )

    with pytest.raises(LeaseStoreError, match="capsule authentication failed"):
        issuer.claim(
            store,
            task.branch_task_id,
            daemon_id="daemon:builder-1",
            authenticated_daemon=SimpleNamespace(
                daemon_id="daemon:builder-1",
                owner_user_id="user:owner-1",
                key_thumbprint=registry.device_key_id,
                credential_epoch=registry.credential_epoch,
            ),
            bind_capsule=tampered_binder,
        )

    revoked_issuer = LeaseGrantIssuer(
        platform_signer=PlatformSigner(grant_key),
        capsule_key=_capsule_key(grant_key, active=False),
        supported_request_schema_versions={3},
    )
    with pytest.raises(LeaseStoreError, match="capsule authentication failed"):
        revoked_issuer.claim(
            store,
            task.branch_task_id,
            daemon_id="daemon:builder-1",
            authenticated_daemon=SimpleNamespace(
                daemon_id="daemon:builder-1",
                owner_user_id="user:owner-1",
                key_thumbprint=registry.device_key_id,
                credential_epoch=registry.credential_epoch,
            ),
            bind_capsule=signed_binder,
        )


def _result_lease(tmp_path: Path, *, clock: MutableClock | None = None):
    from nacl.signing import SigningKey

    from tests.test_execution_jobs_result import blob_store_with_result_blobs
    from tests.test_execution_result import result_body
    from tinyassets.runtime.execution_result import create_execution_result

    active_clock = clock or MutableClock()
    key = SigningKey.generate()
    grant_key = SigningKey.generate()
    platform_signer = PlatformSigner(grant_key)
    registry = StaticDeviceKeyRegistry(key)
    store = SigningLeaseStore(
        tmp_path / "leases.sqlite3",
        clock=active_clock,
        key_registry=registry,
        record_verifier=RecordVerifier(grant_key.verify_key),
        completion_signer=platform_signer,
    )
    issuer = LeaseGrantIssuer(
        platform_signer=platform_signer,
        capsule_key=_capsule_key(grant_key),
        supported_request_schema_versions={3},
    )
    task = _task()
    store.add_task(
        task,
        result_state={
            "owner_user_id": "user:owner-1",
            "device_key_id": registry.device_key_id,
            "device_key_epoch": registry.credential_epoch,
            "capability_class": "repo",
            "repo_mode": "coding",
            "runner_policy_sha256": "c" * 64,
            "image_digest": f"sha256:{'d' * 64}",
            "candidate_result": None,
            "candidate_receipt": None,
            "completion_receipt": None,
        },
    )
    lease = issuer.claim(
        store,
        task.branch_task_id,
        daemon_id="daemon:builder-1",
        authenticated_daemon=SimpleNamespace(
            daemon_id="daemon:builder-1",
            owner_user_id="user:owner-1",
            key_thumbprint=registry.device_key_id,
            credential_epoch=registry.credential_epoch,
        ),
        bind_capsule=_grant_capsule("a", grant_key),
        lease_seconds=120,
    )
    body = result_body()
    body.update(
        job_id=task.branch_task_id,
        capsule_id=lease.capsule.record_id,
        capsule_sha256=lease.capsule.content_sha256,
        lease_id=lease.lease_id,
        fence=lease.fence,
    )
    body["executor"]["device_key_id"] = registry.device_key_id
    blob_store, body = blob_store_with_result_blobs(
        tmp_path / "result-blobs",
        body=body,
        job_id=task.branch_task_id,
        lease_id=lease.lease_id,
        fence=lease.fence,
    )
    result = create_execution_result(
        body,
        signing_key=key,
        device_key_id=registry.device_key_id,
        repo_mode="coding",
    )
    raw_result = json.dumps(result, separators=(",", ":")).encode()
    expected = {
        "lease_id": lease.lease_id,
        "lease_fence": lease.fence,
        "daemon_id": lease.daemon_id,
        "capsule_sha256": lease.capsule.content_sha256,
        "result_sha256": result["signature"]["result_sha256"],
    }
    return ResultLeaseFixture(
        (
            store,
            task,
            lease,
            blob_store,
            key,
            result,
            raw_result,
            expected,
            active_clock,
        ),
        issuer,
        grant_key,
    )


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("schema_version", "lease-grant/v999"),
        ("device_key_id", "device-key:missing"),
        ("device_verify_key", "bm90LWEta2V5"),
        ("device_key_epoch", 2),
        ("capability_class", "unknown"),
        ("repo_mode", "unknown"),
        ("runner_policy_sha256", "not-a-sha256"),
        ("image_digest", "not-an-image-digest"),
    ],
)
def test_lease_specialized_fields_reject_valid_signatures_before_verified(
    tmp_path: Path,
    field: str,
    invalid_value: object,
) -> None:
    fixture = _result_lease(tmp_path)
    store, task, *_ = fixture
    with sqlite3.connect(store.db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(row["lease_grant_json"])
        payload[field] = invalid_value
        signed_json, signature = PlatformSigner(fixture.capsule_signing_key).sign(
            lease_store_module._LEASE_GRANT_DOMAIN_SEPARATOR,
            payload,
        )
        connection.execute(
            "UPDATE lease_tasks SET lease_grant_json = ?, lease_grant_signature = ? "
            "WHERE task_id = ?",
            (signed_json, signature, task.branch_task_id),
        )
        row = connection.execute(
            "SELECT * FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        assert row is not None

    with pytest.raises(StoredStateCorruptError) as rejection:
        store._verified_lease_grant(row)
    assert isinstance(rejection.value.__cause__, StoredStateCorruptError)
    assert "specialized validation" in str(rejection.value.__cause__)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("schema_version", "completion-attestation/v999"),
        ("receipt_id", "completion:forged"),
        ("status", "running"),
        ("completed_at", "not-a-timestamp"),
    ],
)
def test_completion_specialized_fields_reject_valid_signatures_before_verified(
    tmp_path: Path,
    field: str,
    invalid_value: str,
) -> None:
    fixture = _result_lease(tmp_path)
    store, task, _, blobs, key, _, raw, expected, clock = fixture
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, blobs, expected, clock.now)

    with sqlite3.connect(store.db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        attestation = connection.execute(
            "SELECT signed_json FROM lease_completion_attestations "
            "WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        assert row is not None and attestation is not None
        payload = json.loads(attestation["signed_json"])
        payload[field] = invalid_value
        signed_json, signature = store._test_completion_signer.sign(
            lease_store_module._COMPLETION_ATTESTATION_DOMAIN_SEPARATOR,
            payload,
        )

    with pytest.raises(StoredStateCorruptError, match="specialized validation"):
        store._record_verifier.verify(
            lease_store_module._COMPLETION_ATTESTATION_DOMAIN_SEPARATOR,
            signed_json,
            signature,
            store._completion_row_bindings(row),
            validation_context=store._completion_validation_context(row),
        )


def test_completion_owner_user_id_is_inert_audit_metadata(tmp_path: Path) -> None:
    fixture = _result_lease(tmp_path)
    store, task, _, blobs, key, _, raw, expected, clock = fixture
    _record_candidate(store, task, blobs, key, raw, clock.now)
    receipt = _complete(store, task, blobs, expected, clock.now)

    with sqlite3.connect(store.db_path) as connection:
        signed_json = connection.execute(
            "SELECT signed_json FROM lease_completion_attestations "
            "WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()[0]
        payload = json.loads(signed_json)
        payload["owner_user_id"] = "user:changed-audit-metadata"
        changed_json, changed_signature = store._test_completion_signer.sign(
            lease_store_module._COMPLETION_ATTESTATION_DOMAIN_SEPARATOR,
            payload,
        )
        with _legacy_attestation_insert(connection):
            connection.execute(
                "INSERT INTO lease_completion_attestations("
                "attestation_id, task_id, signed_json, signature, created_at"
                ") VALUES (?, ?, ?, ?, ?)",
                (
                    "changed-inert-owner",
                    task.branch_task_id,
                    changed_json,
                    changed_signature,
                    LeaseStore._time_text(clock.now),
                ),
            )

    assert _complete(store, task, blobs, expected, clock.now) == receipt


def test_resigned_lease_owner_is_rejected_against_durable_owner(
    tmp_path: Path,
) -> None:
    fixture = _result_lease(tmp_path)
    store, task, *_ = fixture
    with sqlite3.connect(store.db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
      …35763 tokens truncated…ame = ?",
                (name,),
            ).fetchone()[0]
            for name in old_insert_guards
        }
    assert version == 7
    assert all(
        LeaseStore._normalized_schema_sql(actual[name])
        == LeaseStore._normalized_schema_sql(definition)
        for name, definition in (
            lease_store_module._COMPLETION_ATTESTATION_TRIGGERS
            | lease_store_module._EVENT_TRIGGERS
        ).items()
        if name in old_insert_guards
    )


@pytest.mark.parametrize(
    ("table", "trigger_name"),
    [
        (
            "lease_completion_attestations",
            "lease_completion_attestations_append_only_insert",
        ),
        ("lease_events", "lease_events_append_only_insert"),
    ],
)
def test_schema_v5_rejects_malformed_insert_guard_instead_of_repairing(
    tmp_path: Path,
    table: str,
    trigger_name: str,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    LeaseStore(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.execute(
            f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON {table} "
            "BEGIN SELECT 1; END"
        )
        connection.execute("PRAGMA user_version = 5")

    with pytest.raises(StoredStateCorruptError, match="trigger"):
        LeaseStore(db_path)


@pytest.mark.parametrize(
    "corruption",
    [
        "table_columns",
        "missing_update_trigger",
        "malformed_update_trigger",
        "missing_delete_trigger",
        "malformed_delete_trigger",
    ],
)
def test_schema_v4_rejects_malformed_completion_attestation_defenses(
    tmp_path: Path,
    corruption: str,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    LeaseStore(db_path)
    trigger_suffix = "update" if "update" in corruption else "delete"
    trigger_name = (
        f"lease_completion_attestations_append_only_{trigger_suffix}"
    )
    with sqlite3.connect(db_path) as connection:
        if corruption == "table_columns":
            connection.execute(
                "DROP TRIGGER lease_completion_attestations_append_only_update"
            )
            connection.execute(
                "DROP TRIGGER lease_completion_attestations_append_only_delete"
            )
            connection.execute("DROP TABLE lease_completion_attestations")
            connection.execute(
                "CREATE TABLE lease_completion_attestations("
                "attestation_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
                "signed_json TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
        else:
            connection.execute(f"DROP TRIGGER {trigger_name}")
            if corruption.startswith("malformed"):
                operation = trigger_suffix.upper()
                connection.execute(
                    f"CREATE TRIGGER {trigger_name} BEFORE {operation} "
                    "ON lease_completion_attestations BEGIN SELECT 1; END"
                )

    with pytest.raises(
        StoredStateCorruptError,
        match="completion attestation",
    ) as rejection:
        LeaseStore(db_path)
    if corruption == "malformed_update_trigger":
        print(f"MIGRATION_MALFORMED_TRIGGER_REJECTED: {rejection.value}")


def test_schema_v4_rejects_attestation_primary_key_on_conflict_replace(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    LeaseStore(db_path)
    with sqlite3.connect(db_path) as connection:
        for trigger_name in lease_store_module._COMPLETION_ATTESTATION_TRIGGERS:
            connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.execute("DROP TABLE lease_completion_attestations")
        connection.execute(
            "CREATE TABLE lease_completion_attestations("
            "attestation_id TEXT PRIMARY KEY ON CONFLICT REPLACE, "
            "task_id TEXT NOT NULL REFERENCES lease_tasks(task_id), "
            "signed_json TEXT NOT NULL, signature TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        connection.execute(
            lease_store_module._COMPLETION_ATTESTATION_TASK_INDEX
        )
        for definition in lease_store_module._COMPLETION_ATTESTATION_TRIGGERS.values():
            connection.execute(definition)

    with pytest.raises(
        StoredStateCorruptError,
        match="completion attestation table",
    ):
        LeaseStore(db_path)


def test_operational_connections_enable_required_sqlite_defenses(
    tmp_path: Path,
) -> None:
    store = LeaseStore(tmp_path / "leases.sqlite3")

    with store._connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 1


@pytest.mark.parametrize(
    "table_suffix",
    [
        "STRICT",
        (
            ", shadow TEXT GENERATED ALWAYS AS (attestation_id) VIRTUAL"
        ),
    ],
    ids=["strict-table-list", "hidden-table-xinfo"],
)
def test_attestation_validation_rejects_metadata_hidden_by_spoofed_table_sql(
    tmp_path: Path,
    table_suffix: str,
) -> None:
    store = LeaseStore(tmp_path / "leases.sqlite3")
    if table_suffix == "STRICT":
        definition = lease_store_module._COMPLETION_ATTESTATION_TABLE.strip() + " STRICT"
    else:
        canonical = lease_store_module._COMPLETION_ATTESTATION_TABLE.strip()
        definition = canonical[:-1] + table_suffix + ")"

    with store._connect() as connection:
        _replace_attestation_table(connection, definition)
        _spoof_canonical_attestation_table_sql(connection)
        with pytest.raises(StoredStateCorruptError, match="completion attestation"):
            LeaseStore._migrate_schema(connection)


def test_attestation_validation_rejects_spoofed_foreign_key_contract(
    tmp_path: Path,
) -> None:
    store = LeaseStore(tmp_path / "leases.sqlite3")
    altered_definition = """
        CREATE TABLE lease_completion_attestations (
            attestation_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES lease_tasks(task_id) ON DELETE CASCADE,
            signed_json TEXT NOT NULL,
            signature TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """

    with store._connect() as connection:
        _replace_attestation_table(connection, altered_definition)
        _spoof_canonical_attestation_table_sql(connection)
        with pytest.raises(StoredStateCorruptError, match="foreign key"):
            LeaseStore._migrate_schema(connection)


def test_attestation_validation_rejects_existing_foreign_key_violation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    LeaseStore(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO main.lease_completion_attestations("
            "attestation_id, task_id, signed_json, signature, created_at"
            ") VALUES ('orphan', 'missing-task', '{}', 'signature', 'now')"
        )

    with pytest.raises(StoredStateCorruptError, match="foreign key violation"):
        LeaseStore(db_path)


@pytest.mark.parametrize(
    "index_corruption",
    ["missing", "malformed", "extra"],
)
def test_attestation_validation_rejects_noncanonical_index_set(
    tmp_path: Path,
    index_corruption: str,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    LeaseStore(db_path)
    index_name = "lease_completion_attestations_task_id_uq"
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"DROP INDEX IF EXISTS {index_name}")
        if index_corruption == "malformed":
            connection.execute(
                f"CREATE UNIQUE INDEX {index_name} "
                "ON lease_completion_attestations(task_id COLLATE NOCASE)"
            )
        elif index_corruption == "extra":
            connection.execute(
                f"CREATE UNIQUE INDEX {index_name} "
                "ON lease_completion_attestations(task_id)"
            )
            connection.execute(
                "CREATE INDEX lease_completion_attestations_created_at "
                "ON lease_completion_attestations(created_at)"
            )

    with pytest.raises(StoredStateCorruptError, match="index"):
        LeaseStore(db_path)


def test_v6_migration_rejects_duplicate_task_attestations(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    _complete(store, task, blobs, expected, clock.now)
    insert_trigger = "lease_completion_attestations_append_only_insert"
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(f"DROP TRIGGER {insert_trigger}")
        connection.execute(
            "DROP INDEX IF EXISTS lease_completion_attestations_task_id_uq"
        )
        connection.execute(
            "INSERT INTO lease_completion_attestations("
            "attestation_id, task_id, signed_json, signature, created_at) "
            "SELECT 'duplicate-task', task_id, signed_json, signature, created_at "
            "FROM lease_completion_attestations WHERE task_id = ?",
            (task.branch_task_id,),
        )
        connection.execute(
            lease_store_module._COMPLETION_ATTESTATION_TRIGGERS[insert_trigger]
        )
        connection.execute("PRAGMA user_version = 6")

    with pytest.raises(StoredStateCorruptError, match="duplicate task"):
        LeaseStore(store.db_path)


@pytest.mark.parametrize("trigger_corruption", ["altered_when", "extra"])
def test_attestation_validation_rejects_noncanonical_trigger_set(
    tmp_path: Path,
    trigger_corruption: str,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    LeaseStore(db_path)
    with sqlite3.connect(db_path) as connection:
        if trigger_corruption == "altered_when":
            name = "lease_completion_attestations_append_only_insert"
            connection.execute(f"DROP TRIGGER {name}")
            connection.execute(
                f"CREATE TRIGGER {name} "
                "BEFORE INSERT ON lease_completion_attestations "
                "WHEN EXISTS (SELECT 1 FROM lease_completion_attestations "
                "WHERE attestation_id = NEW.attestation_id) "
                "BEGIN SELECT RAISE(ABORT, "
                "'lease_completion_attestations is append-only'); END"
            )
        else:
            connection.execute(
                "CREATE TRIGGER lease_completion_attestations_unexpected "
                "AFTER INSERT ON lease_completion_attestations BEGIN SELECT 1; END"
            )

    with pytest.raises(StoredStateCorruptError, match="trigger"):
        LeaseStore(db_path)


def test_attestation_validation_rejects_temp_namespace_shadow(
    tmp_path: Path,
) -> None:
    store = LeaseStore(tmp_path / "leases.sqlite3")
    with store._connect() as connection:
        connection.execute(
            "CREATE TEMP TABLE lease_completion_attestations("
            "attestation_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
            "signed_json TEXT NOT NULL, signature TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        with pytest.raises(StoredStateCorruptError, match="temp"):
            LeaseStore._migrate_schema(connection)


def test_attestation_replay_reads_main_table_despite_temp_shadow(
    tmp_path: Path,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    receipt = _complete(store, task, blobs, expected, clock.now)

    with store._connect() as connection:
        connection.execute(
            "CREATE TEMP TABLE lease_completion_attestations("
            "attestation_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
            "signed_json TEXT NOT NULL, signature TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO temp.lease_completion_attestations VALUES "
            "('shadow', ?, '{}', 'bad-signature', 'now')",
            (task.branch_task_id,),
        )
        row = connection.execute(
            "SELECT * FROM main.lease_tasks WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()
        assert row is not None
        assert store._verified_completion_replay(
            connection,
            row=row,
            expected=expected,
        ) == dict(receipt)


def test_completion_writes_main_attestation_despite_temp_shadow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, task, _, blobs, key, _, raw, expected, clock = _result_lease(tmp_path)
    _record_candidate(store, task, blobs, key, raw, clock.now)
    real_connect = store._connect

    def shadowed_connect() -> sqlite3.Connection:
        connection = real_connect()
        connection.execute(
            "CREATE TEMP TABLE lease_completion_attestations("
            "attestation_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, "
            "signed_json TEXT NOT NULL, signature TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        return connection

    monkeypatch.setattr(store, "_connect", shadowed_connect)
    _complete(store, task, blobs, expected, clock.now)

    with sqlite3.connect(store.db_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM main.lease_completion_attestations "
            "WHERE task_id = ?",
            (task.branch_task_id,),
        ).fetchone()[0] == 1


@pytest.mark.parametrize("operation", ["update", "delete", "insert"])
def test_schema_rejects_malformed_lease_event_append_only_trigger(
    tmp_path: Path,
    operation: str,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    LeaseStore(db_path)
    trigger_name = f"lease_events_append_only_{operation}"
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
        connection.execute(
            f"CREATE TRIGGER {trigger_name} BEFORE {operation.upper()} "
            "ON lease_events BEGIN SELECT 1; END"
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="lease event trigger",
    ):
        LeaseStore(db_path)


def test_wrong_same_name_index_is_replaced_with_required_definition(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    LeaseStore(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP INDEX lease_events_one_shot_generation_uq")
        connection.execute(
            "CREATE INDEX lease_events_one_shot_generation_uq "
            "ON lease_events(task_id)"
        )

    LeaseStore(db_path)

    with sqlite3.connect(db_path) as connection:
        definition = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE type = 'index' AND name = ?",
            ("lease_events_one_shot_generation_uq",),
        ).fetchone()[0]
        index_row = next(
            row
            for row in connection.execute("PRAGMA index_list(lease_events)")
            if row[1] == "lease_events_one_shot_generation_uq"
        )
    assert definition.startswith("CREATE UNIQUE INDEX")
    assert "result_submitted" in definition
    assert index_row[2] == 1
    assert index_row[4] == 1


def test_v0_duplicate_events_roll_back_entire_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "leases.sqlite3"
    _create_v0_lease_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO lease_tasks(task_id) VALUES ('task-1')")
        connection.executemany(
            "INSERT INTO lease_events("
            "task_id, kind, lease_id, fence, occurred_at"
            ") VALUES ('task-1', 'claimed', 'lease-1', 1, ?)",
            [("2026-07-19T12:00:00Z",), ("2026-07-19T12:00:01Z",)],
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="lease event ledger contains duplicate one-shot events",
    ):
        LeaseStore(db_path)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert "content_sha256" not in {
            row[1] for row in connection.execute("PRAGMA table_info(lease_events)")
        }
        assert not {
            row[1]
            for row in connection.execute("PRAGMA index_list(lease_events)")
        } & {
            "lease_events_one_shot_generation_uq",
            "lease_events_added_uq",
        }


def test_exception_after_anchor_alter_rolls_back_schema_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    _create_v0_lease_database(db_path)
    real_connect = sqlite3.connect

    class FailingConnection:
        def __init__(self, inner: sqlite3.Connection) -> None:
            object.__setattr__(self, "inner", inner)
            object.__setattr__(self, "altered", False)

        def __setattr__(self, name, value):
            if name in {"inner", "altered"}:
                object.__setattr__(self, name, value)
            else:
                setattr(self.inner, name, value)

        def __getattr__(self, name):
            return getattr(self.inner, name)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.close()

        def execute(self, sql, parameters=()):
            normalized = " ".join(sql.split()).upper()
            if self.altered and normalized.startswith("DROP INDEX"):
                raise sqlite3.OperationalError("injected migration failure")
            result = self.inner.execute(sql, parameters)
            if normalized.startswith("ALTER TABLE LEASE_EVENTS ADD COLUMN"):
                object.__setattr__(self, "altered", True)
            return result

    def failing_connect(self):
        inner = real_connect(str(self.db_path), timeout=30.0, isolation_level=None)
        inner.row_factory = sqlite3.Row
        inner.execute("PRAGMA busy_timeout = 30000")
        inner.execute("PRAGMA foreign_keys = ON")
        inner.execute("PRAGMA synchronous = FULL")
        return FailingConnection(inner)

    monkeypatch.setattr(LeaseStore, "_connect", failing_connect)
    with pytest.raises(sqlite3.OperationalError, match="injected migration failure"):
        LeaseStore(db_path)

    with real_connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert "content_sha256" not in {
            row[1] for row in connection.execute("PRAGMA table_info(lease_events)")
        }


def test_legacy_unanchored_result_event_fails_at_initialization(tmp_path: Path) -> None:
    db_path = tmp_path / "leases.sqlite3"
    _create_v0_lease_database(db_path, with_content_column=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO lease_tasks(task_id) VALUES ('task-1')")
        connection.execute(
            "INSERT INTO lease_events("
            "task_id, kind, lease_id, fence, occurred_at, content_sha256"
            ") VALUES ('task-1', 'result_submitted', 'lease-1', 1, "
            "'2026-07-19T12:00:00Z', NULL)"
        )

    with pytest.raises(
        StoredStateCorruptError,
        match="pre-anchor ledger events require migration decision",
    ):
        LeaseStore(db_path)


def test_concurrent_schema_initializers_serialize(tmp_path: Path) -> None:
    db_path = tmp_path / "leases.sqlite3"
    start = threading.Barrier(2)

    def initialize() -> None:
        start.wait()
        LeaseStore(db_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(initialize) for _ in range(2)]
        for future in futures:
            future.result(timeout=30)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
