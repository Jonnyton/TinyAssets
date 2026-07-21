from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from nacl.public import PrivateKey
from nacl.signing import SigningKey

from tinyassets.api.daemon_enrollment import DaemonEnrollmentService
from tinyassets.api.execution_jobs import (
    complete_job,
    grant_job_lease,
    submit_candidate_result,
)
from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import DevAuthProvider, OAuthProvider
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.config import write_universe_config_fields
from tinyassets.daemon_server import (
    ensure_universe_registered,
    ensure_universe_rules,
    grant_universe_access,
    save_branch_definition,
)
from tinyassets.runs import get_run, wait_for
from tinyassets.runtime.blob_refs import BlobStore
from tinyassets.runtime.daemon_auth import (
    DevicePublicIdentity,
    SignedRequest,
    canonical_challenge,
    canonical_challenge_creation,
    canonical_enrollment_completion,
    canonical_request,
    request_body_hash,
)
from tinyassets.runtime.execution_capsule import (
    canonicalize_jcs,
    create_execution_capsule,
)
from tinyassets.runtime.execution_result import create_execution_result
from tinyassets.runtime.lease_store import (
    CapsuleVerificationKeyRecord,
    LeaseGrantCapsule,
    LeaseGrantIssuer,
    LeaseStore,
)
from tinyassets.runtime.signed_records import PlatformSigner, RecordVerifier
from tinyassets.universe_server import run_graph


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _capsule_payload(
    lease,
    *,
    owner_user_id: str,
    device_key_id: str,
    device_signing_key: SigningKey,
) -> dict:
    inline_request = {
        "kind": "isolated_execution_request",
        "schema_version": 3,
        "prompt": "write one executed artifact",
    }
    request_bytes = canonicalize_jcs(inline_request)
    source_bytes = b"tinyassets B2 source bundle"
    return {
        "schema_version": "execution-capsule/v1",
        "capsule_id": str(uuid4()),
        "job_id": lease.task_id,
        "attempt": lease.fence,
        "audience_daemon_id": lease.daemon_id,
        "owner_user_id": owner_user_id,
        "universe_scope": {
            "universe_id": "universe:b2-e2e",
            "capability_id": "cap:b2:execute",
            "scope_version": 1,
            "permissions": [
                "read_source",
                "execute_repo",
                "produce_patch",
                "produce_artifact",
            ],
        },
        "branch": {
            "branch_definition_id": "branch:b2-e2e",
            "branch_version_sha256": "1" * 64,
        },
        "node": {
            "node_id": "node:b2-e2e",
            "node_version_sha256": "2" * 64,
            "node_kind": "coding",
        },
        "base": {
            "vcs": "git",
            "object_format": "sha1",
            "commit": "3" * 40,
            "tree": "4" * 40,
        },
        "source_blob": {
            "ref": "blob:source:b2-e2e",
            "media_type": "application/vnd.tinyassets.git-bundle.v1",
            "content_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "transport_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "size_bytes": len(source_bytes),
            "manifest_sha256": hashlib.sha256(b"b2 source manifest").hexdigest(),
            "confidentiality": "public",
            "encryption": None,
            "producer": {
                "daemon_id": lease.daemon_id,
                "device_key_id": device_key_id,
                "signature_b64": base64.b64encode(
                    device_signing_key.sign(b"b2 source manifest").signature
                ).decode("ascii"),
            },
        },
        "execution_request": {
            "schema_version": 3,
            "ref": None,
            "inline": inline_request,
            "sha256": hashlib.sha256(request_bytes).hexdigest(),
            "size_bytes": len(request_bytes),
        },
        "allowed_capability": {
            "class": "repo",
            "repo_mode": "coding",
            "action_policy_id": "policy:actions:b2-e2e",
            "action_policy_sha256": "8" * 64,
            "runner_policy_sha256": "9" * 64,
            "image_digest": f"sha256:{'a' * 64}",
        },
        "model_broker_route": {
            "route_id": "route:model:b2-e2e",
            "route_version": 1,
            "policy_sha256": "b" * 64,
            "grant_ref": "grant:model:b2-e2e",
            "allowed_model_classes": ["coding"],
            "max_calls": 1,
            "max_input_tokens": 1_000,
            "max_output_tokens": 1_000,
            "expires_at": lease.expires_at,
        },
        "resource_limits": {
            "cpu_millis": 1_000,
            "memory_bytes": 256 * 1024**2,
            "pids": 32,
            "workspace_bytes": 64 * 1024**2,
            "workspace_inodes": 1_000,
            "tmpfs_bytes": 16 * 1024**2,
            "wall_time_seconds": 60,
            "stdout_bytes": 1_024,
            "stderr_bytes": 1_024,
            "patch_bytes": 1_024,
            "patch_files": 1,
            "patch_changed_lines": 10,
            "network": "none",
            "egress_policy_id": "policy:egress:b2-e2e",
            "egress_policy_sha256": "c" * 64,
        },
        "lease": {
            "lease_id": lease.lease_id,
            "fence": lease.fence,
            "issued_at": lease.issued_at,
            "expires_at": lease.expires_at,
        },
        "issued_at": lease.issued_at,
        "not_before": lease.issued_at,
        "expires_at": lease.expires_at,
    }


def _result_body(
    *,
    job_id: str,
    lease,
    daemon_id: str,
    device_key_id: str,
    artifact_ref: str,
    artifact_sha256: str,
    artifact_size: int,
    completed_at: str,
) -> dict:
    return {
        "schema_version": "execution-result/v1",
        "job_id": job_id,
        "capsule_id": lease.capsule.record_id,
        "capsule_sha256": lease.capsule.content_sha256,
        "lease_id": lease.lease_id,
        "fence": lease.fence,
        "outcome": "succeeded",
        "executor": {
            "daemon_id": daemon_id,
            "device_key_id": device_key_id,
            "capability_class": "repo",
            "backend": "linux-bwrap",
            "runner_policy_sha256": "9" * 64,
            "image_digest": f"sha256:{'a' * 64}",
        },
        "repo_patch": {
            "format": "git-diff-v1",
            "blob_ref": artifact_ref,
            "blob_sha256": artifact_sha256,
            "size_bytes": artifact_size,
            "base_commit": "3" * 40,
            "base_tree": "4" * 40,
            "resulting_tree": "5" * 40,
            "file_count": 1,
            "added_lines": 1,
            "deleted_lines": 0,
        },
        "source_output": None,
        "logs": [],
        "checks": [
            {
                "check_id": "artifact-created",
                "outcome": "passed",
                "exit_code": 0,
                "duration_ms": 1,
                "stdout_sha256": None,
                "stderr_sha256": None,
            }
        ],
        "usage": {
            "wall_time_ms": 1,
            "cpu_time_ms": 1,
            "peak_memory_bytes": 1,
            "model_calls": 0,
            "model_input_tokens": 0,
            "model_output_tokens": 0,
        },
        "revalidation": {
            "exact_base_verified": True,
            "patch_applies_cleanly": True,
            "path_policy_passed": True,
            "limits_passed": True,
            "resulting_tree": "5" * 40,
            "verifier_policy_sha256": "f" * 64,
        },
        "destruction": {
            "confirmed": True,
            "confirmed_at": completed_at,
            "backend_receipt_sha256": hashlib.sha256(
                b"minimal executor allocated no persistent workspace"
            ).hexdigest(),
        },
        "completed_at": completed_at,
    }


def test_b2_job_runs_end_to_end_through_real_authority_path(
    tmp_path: Path,
    monkeypatch,
    request,
) -> None:
    now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    owner_user_id = "owner:b2-e2e"
    run_root = tmp_path / "run-state"
    run_root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(run_root))

    oauth_provider = OAuthProvider(tmp_path / "oauth.sqlite3")
    oauth_client = oauth_provider.register_client({
        "client_name": "B2 end-to-end entry test",
        "redirect_uris": ["https://client.example/callback"],
    })
    code_verifier = "b2-entry-verifier"
    authorization_code = oauth_provider.create_authorization(
        oauth_client["client_id"],
        "https://client.example/callback",
        "tinyassets.extensions.costly",
        "b2-entry-state",
        _b64(hashlib.sha256(code_verifier.encode("utf-8")).digest()),
        "S256",
    )
    # The local OAuth provider has no login UI; this row is where that UI would
    # attach the authenticated subject to the otherwise-real PKCE flow.
    with sqlite3.connect(oauth_provider._db_path) as connection:
        connection.execute(
            "UPDATE authorization_codes SET user_id = ? WHERE code = ?",
            (owner_user_id, authorization_code),
        )
    oauth_tokens = oauth_provider.exchange_code(
        authorization_code,
        oauth_client["client_id"],
        "https://client.example/callback",
        code_verifier,
    )
    assert oauth_tokens is not None
    set_provider(oauth_provider)
    auth_middleware(oauth_tokens["access_token"])

    def reset_auth() -> None:
        set_provider(DevAuthProvider())
        auth_middleware(None)

    request.addfinalizer(reset_auth)

    universe_id = "universe-b2-e2e"
    universe_dir = run_root / universe_id
    universe_dir.mkdir()
    write_universe_config_fields(universe_dir, engine_source="host_daemon")
    ensure_universe_registered(
        run_root,
        universe_id=universe_id,
        universe_path=universe_dir,
    )
    ensure_universe_rules(run_root, universe_id=universe_id)
    grant_universe_access(
        run_root,
        universe_id=universe_id,
        actor_id=owner_user_id,
        permission="admin",
        granted_by=owner_user_id,
    )
    branch = BranchDefinition(
        branch_def_id="branch:b2-e2e",
        name="B2 end-to-end",
        author=owner_user_id,
        entry_point="execute",
        node_defs=[NodeDefinition(
            node_id="execute",
            display_name="Execute",
            prompt_template="write one executed artifact",
            output_keys=["result"],
        )],
        graph_nodes=[GraphNodeRef(id="execute", node_def_id="execute")],
        edges=[EdgeDefinition(from_node="execute", to_node="END")],
    )
    save_branch_definition(run_root, branch_def=branch.to_dict())

    entry_result = json.loads(run_graph(
        branch_def_id=branch.branch_def_id,
        inputs_json=json.dumps({"payload": "create one artifact"}),
        graph_id=universe_id,
    ))
    assert entry_result["status"] == "queued"
    run_id = entry_result["run_id"]
    job_id = entry_result["job_id"]
    wait_for(run_id, timeout=5)

    device_signing_key = SigningKey.generate()
    identity = DevicePublicIdentity(
        installation_id="installation:b2-e2e",
        ed25519_public_key=bytes(device_signing_key.verify_key),
        x25519_public_key=bytes(PrivateKey.generate().public_key),
        installation_nonce=os.urandom(32),
        key_backend="integration-test-memory",
        hardware_non_exportable=False,
    )
    enrollment_service = DaemonEnrollmentService(
        db_path=tmp_path / "daemon-auth.sqlite3",
        clock=lambda: now.timestamp(),
    )
    enrollment = enrollment_service.create_enrollment(identity)
    enrollment_service.approve_enrollment(
        enrollment.enrollment_id,
        owner_user_id=owner_user_id,
    )
    completed_enrollment = enrollment_service.complete_enrollment(
        enrollment.enrollment_id,
        installation_nonce=_b64(identity.installation_nonce),
        signature=_b64(
            device_signing_key.sign(
                canonical_enrollment_completion(
                    enrollment.enrollment_id,
                    identity.installation_nonce,
                )
            ).signature
        ),
    )
    challenge_nonce = "b2-e2e-challenge"
    challenge = enrollment_service.create_challenge(
        completed_enrollment.daemon_id,
        timestamp=int(now.timestamp()),
        nonce=challenge_nonce,
        signature=_b64(
            device_signing_key.sign(
                canonical_challenge_creation(
                    completed_enrollment.daemon_id,
                    int(now.timestamp()),
                    challenge_nonce,
                )
            ).signature
        ),
    )
    access_token = enrollment_service.issue_access_token(
        completed_enrollment.daemon_id,
        challenge.challenge,
        _b64(
            device_signing_key.sign(
                canonical_challenge(
                    completed_enrollment.daemon_id,
                    challenge.challenge,
                )
            ).signature
        ),
    )

    run = get_run(run_root, run_id)
    assert run is not None
    assert run["owner_user_id"] == owner_user_id
    assert "no_eligible_external_daemon" in run["error"]

    platform_key = SigningKey.generate()
    platform_signer = PlatformSigner(platform_key)
    record_verifier = RecordVerifier(platform_key.verify_key)
    lease_store = LeaseStore(
        run_root / "leases.sqlite3",
        clock=lambda: now,
        key_registry=enrollment_service,
        record_verifier=record_verifier,
    )
    job = lease_store.read_task(job_id)
    assert str(UUID(job.branch_task_id)) == job.branch_task_id
    assert job.source_run_id == run_id

    claim_body = json.dumps(
        {"job_id": job.branch_task_id}, separators=(",", ":")
    ).encode("utf-8")
    claim_path = f"/v1/execution/jobs/{job.branch_task_id}:claim"
    claim_timestamp = int(now.timestamp())
    claim_nonce = "b2-e2e-claim"
    claim_body_hash = request_body_hash(claim_body)
    signed_claim = SignedRequest(
        method="POST",
        path=claim_path,
        query="",
        signed_headers=(),
        body_hash=claim_body_hash,
        timestamp=claim_timestamp,
        nonce=claim_nonce,
        signature=_b64(
            device_signing_key.sign(
                canonical_request(
                    "POST",
                    claim_path,
                    "",
                    {},
                    claim_body_hash,
                    claim_timestamp,
                    claim_nonce,
                )
            ).signature
        ),
    )
    authenticated_daemon = enrollment_service.verify_request(
        access_token.value,
        signed_claim,
        claim_body,
        expected_owner_user_id=owner_user_id,
    )

    capsule_key = CapsuleVerificationKeyRecord(
        signing_key_id="platform-capsule:b2-e2e",
        verify_key=platform_key.verify_key,
        active=True,
    )
    issuer = LeaseGrantIssuer(
        platform_signer=platform_signer,
        capsule_key=capsule_key,
        supported_request_schema_versions={3},
    )

    def bind_capsule(lease) -> LeaseGrantCapsule:
        capsule = create_execution_capsule(
            _capsule_payload(
                lease,
                owner_user_id=owner_user_id,
                device_key_id=completed_enrollment.key_thumbprint,
                device_signing_key=device_signing_key,
            ),
            signing_key=platform_key,
            signing_key_id=capsule_key.signing_key_id,
        )
        return LeaseGrantCapsule(
            raw_capsule=json.dumps(capsule, separators=(",", ":")).encode("utf-8")
        )

    lease = grant_job_lease(
        lease_store,
        issuer,
        job_id=job.branch_task_id,
        authenticated_daemon=authenticated_daemon,
        bind_capsule=bind_capsule,
    )

    executed_artifact = (
        b"diff --git a/executed.txt b/executed.txt\n"
        b"new file mode 100644\n"
        b"--- /dev/null\n"
        b"+++ b/executed.txt\n"
        b"@@ -0,0 +1 @@\n"
        b"+B2 executed end to end\n"
    )
    artifact_sha256 = hashlib.sha256(executed_artifact).hexdigest()
    blob_store = BlobStore(tmp_path / "blobs")
    upload = blob_store.init_blob(
        {
            "sha256": artifact_sha256,
            "size_bytes": len(executed_artifact),
            "media_type": "application/vnd.tinyassets.git-diff.v1",
            "confidentiality": "public",
            "job_id": job.branch_task_id,
            "lease_id": lease.lease_id,
            "fence": lease.fence,
        },
        owner_user_id=owner_user_id,
        daemon_id=authenticated_daemon.daemon_id,
    )
    blob_store.write_upload(upload.upload_id, executed_artifact)
    artifact = blob_store.commit_blob(
        upload.upload_id,
        owner_user_id=owner_user_id,
        daemon_id=authenticated_daemon.daemon_id,
    )

    completed_at = (now + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    result = create_execution_result(
        _result_body(
            job_id=job.branch_task_id,
            lease=lease,
            daemon_id=authenticated_daemon.daemon_id,
            device_key_id=completed_enrollment.key_thumbprint,
            artifact_ref=artifact.ref,
            artifact_sha256=artifact_sha256,
            artifact_size=len(executed_artifact),
            completed_at=completed_at,
        ),
        signing_key=device_signing_key,
        device_key_id=completed_enrollment.key_thumbprint,
        repo_mode="coding",
    )
    raw_result = json.dumps(result, separators=(",", ":")).encode("utf-8")
    candidate_receipt = submit_candidate_result(
        lease_store,
        job_id=job.branch_task_id,
        raw_result=raw_result,
        verify_key=device_signing_key.verify_key,
        device_key_active=True,
        blob_store=blob_store,
        authenticated_daemon=authenticated_daemon,
        now=now,
    )
    completion_request = {
        "job_id": job.branch_task_id,
        "daemon_id": authenticated_daemon.daemon_id,
        "lease_id": lease.lease_id,
        "fence": lease.fence,
        "capsule_sha256": lease.capsule.content_sha256,
        "result_sha256": result["signature"]["result_sha256"],
    }
    completion_receipt = complete_job(
        lease_store,
        completion_request,
        blob_store=blob_store,
        now=now,
        completion_signer=platform_signer,
    )

    terminal_task = lease_store.read_task(job.branch_task_id)
    terminal_state = lease_store.read_result_state(job.branch_task_id)
    assert terminal_task.status == "succeeded"
    assert terminal_task.accepted_result_sha256 == result["signature"]["result_sha256"]
    assert terminal_state["candidate_result"] == result
    assert terminal_state["accepted_result_sha256"] == candidate_receipt.result_sha256
    assert completion_receipt.accepted_result_sha256 == candidate_receipt.result_sha256
    assert terminal_state["completion_receipt"] == completion_receipt.__dict__
    assert terminal_state["candidate_result"]["repo_patch"]["blob_ref"] == artifact.ref
    assert terminal_state["candidate_result"]["repo_patch"]["blob_sha256"] == artifact_sha256

    with sqlite3.connect(lease_store.db_path) as connection:
        attestation_count = connection.execute(
            "SELECT COUNT(*) FROM lease_completion_attestations WHERE task_id = ?",
            (job.branch_task_id,),
        ).fetchone()[0]
    assert attestation_count == 1
    assert complete_job(
        lease_store,
        completion_request,
        blob_store=blob_store,
        now=now,
        completion_signer=platform_signer,
    ) == completion_receipt
