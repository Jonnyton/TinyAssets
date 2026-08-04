"""Spawned-process proof for the dark custom-agent activation boundary.

This is shaped local SQLite evidence. It does not represent a dark cloud
deployment, provider call, connector path, or production health proof.

Run directly with:
    python -m pytest tests/load/test_agent_runtime_activation_load.py -q -s
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from tests.test_agent_runtime_activation import _manifest, _persist_manifest
from tinyassets.execution_subject import agent_binding_automation_id
from tinyassets.storage import _connect, db_path
from tinyassets.storage.accounts import create_or_update_account, grant_capabilities
from tinyassets.storage.automation_activations import AutomationActivationStore

PROCESS_WORKERS = 8
PROCESS_REQUESTS = 64


def _activate_in_fresh_process(
    base_path: str,
    owner_user_id: str,
    manifest_id: str,
    evaluated_at: float,
    marker_dir: str,
) -> dict[str, object]:
    from tinyassets.agent_runtime_activation import (
        AgentRuntimeActivationBlocked,
        AgentRuntimeActivationService,
    )
    from tinyassets.agent_runtime_grants import (
        AccountCapabilityGrantSource,
        AgentRuntimeGrantResolver,
    )
    from tinyassets.storage.automation_activations import AutomationActivationExecutor

    root = Path(base_path)

    def issue_lease() -> str:
        lease_id = f"agent-lease-{os.getpid()}-{time.time_ns()}"
        Path(marker_dir, f"{lease_id}.minted").write_text(
            "server lease minted",
            encoding="utf-8",
        )
        return lease_id

    service = AgentRuntimeActivationService(
        root,
        authenticate_owner=lambda: owner_user_id,
        grant_resolver=AgentRuntimeGrantResolver(
            capability_source=AccountCapabilityGrantSource(root)
        ),
        executor_class=AutomationActivationExecutor.CLOUD,
        lease_factory=issue_lease,
        clock=lambda: evaluated_at,
    )
    try:
        activation = service.activate(manifest_id=manifest_id)
    except AgentRuntimeActivationBlocked as exc:
        return {"kind": "blocked", "code": exc.code.value}
    assert activation.subject is not None
    return {
        "kind": "active",
        "universe_id": activation.universe_id,
        "automation_id": activation.automation_id,
        "epoch": activation.epoch,
        "executor_class": activation.executor_class.value,
        "subject_kind": activation.subject.kind.value,
        "subject_ref": activation.subject.ref,
        "subject_digest": activation.subject.digest,
        "lease_id": activation.lease_id,
        "state": activation.state.value,
        "updated_at": activation.updated_at,
    }


def _run_wave(
    *,
    base_path: Path,
    owner_user_id: str,
    manifest_id: str,
    evaluated_at: float,
    marker_dir: Path,
) -> tuple[list[dict[str, object]], float]:
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=PROCESS_WORKERS) as pool:
        results = list(
            pool.map(
                _activate_in_fresh_process,
                [str(base_path)] * PROCESS_REQUESTS,
                [owner_user_id] * PROCESS_REQUESTS,
                [manifest_id] * PROCESS_REQUESTS,
                [evaluated_at] * PROCESS_REQUESTS,
                [str(marker_dir)] * PROCESS_REQUESTS,
            )
        )
    return results, time.perf_counter() - started


def test_cross_process_activation_restart_and_revocation_are_single_authority(
    tmp_path,
) -> None:
    account = create_or_update_account(tmp_path, username="alice")
    issued_at = time.time()
    grant_capabilities(
        tmp_path,
        user_id=account["user_id"],
        capabilities=["provider.invoke"],
        granted_by=account["user_id"],
        universe_id="universe_alice",
    )
    manifest = _manifest(
        owner_user_id=account["user_id"],
        capability_ids=("provider.invoke",),
    )
    _persist_manifest(tmp_path, manifest)
    marker_dir = tmp_path / "activation-lease-markers"
    marker_dir.mkdir()

    initial, initial_seconds = _run_wave(
        base_path=tmp_path,
        owner_user_id=account["user_id"],
        manifest_id=manifest.manifest_id,
        evaluated_at=issued_at + 1,
        marker_dir=marker_dir,
    )
    restarted, restart_seconds = _run_wave(
        base_path=tmp_path,
        owner_user_id=account["user_id"],
        manifest_id=manifest.manifest_id,
        evaluated_at=issued_at + 2,
        marker_dir=marker_dir,
    )

    assert {result["kind"] for result in initial} == {"active"}
    assert {json.dumps(result, sort_keys=True) for result in initial} == {
        json.dumps(initial[0], sort_keys=True)
    }
    assert {json.dumps(result, sort_keys=True) for result in restarted} == {
        json.dumps(initial[0], sort_keys=True)
    }
    assert len(tuple(marker_dir.glob("*.minted"))) == 1

    with _connect(tmp_path) as connection:
        connection.execute(
            """
            UPDATE capability_grants SET revoked_at = ?
            WHERE user_id = ? AND capability = ? AND scope = ?
            """,
            (
                issued_at + 3,
                account["user_id"],
                "provider.invoke",
                "universe_alice",
            ),
        )

    revoked, revoked_seconds = _run_wave(
        base_path=tmp_path,
        owner_user_id=account["user_id"],
        manifest_id=manifest.manifest_id,
        evaluated_at=issued_at + 4,
        marker_dir=marker_dir,
    )

    assert revoked == [{"kind": "blocked", "code": "grants_not_current"}] * PROCESS_REQUESTS
    assert len(tuple(marker_dir.glob("*.minted"))) == 1
    current = AutomationActivationStore(tmp_path).get(
        "universe_alice",
        agent_binding_automation_id("agent_binding_alice"),
    )
    assert current is not None
    assert current.epoch == 1
    assert current.lease_id == initial[0]["lease_id"]
    with sqlite3.connect(db_path(tmp_path)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity == "ok"

    evidence = {
        "classification": "shaped-local-sqlite",
        "process_workers": PROCESS_WORKERS,
        "requests_per_wave": PROCESS_REQUESTS,
        "initial_wall_seconds": initial_seconds,
        "restart_wall_seconds": restart_seconds,
        "revoked_wall_seconds": revoked_seconds,
        "activation_epoch": current.epoch,
        "server_lease_mints": len(tuple(marker_dir.glob("*.minted"))),
        "revoked_typed_denials": len(revoked),
        "sqlite_integrity": integrity,
    }
    print(json.dumps(evidence, sort_keys=True))

    assert initial_seconds < 30
    assert restart_seconds < 30
    assert revoked_seconds < 30
