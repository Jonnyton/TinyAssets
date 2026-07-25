"""Task #18 — MCP submit_request must reach the daemon.

Explorer flagged that `submit_request` wrote `requests.json` but nothing
under `domains/fantasy_daemon/` read it — every request was silently
discarded. This suite pins the wiring: submit_request → pending entry
→ materialize into a WorkTarget during authorial_priority_review →
daemon sees it.

Covers:
- materialize_pending_requests creates a ROLE_NOTES target.
- status flips pending → seen, stamped with seen_at + work_target_id.
- Idempotent: re-running the helper on a seen request does nothing.
- authorial_priority_review picks up the request within one cycle.
- Non-pending entries (already seen, malformed) are skipped gracefully.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import rfc8785

from domains.fantasy_daemon.phases.authorial_priority_review import (
    authorial_priority_review,
)
from tinyassets.auth.provider import Identity
from tinyassets.branch_tasks_v2 import (
    Epoch2BranchTaskAdapter,
    WorkerClaimDescriptor,
)
from tinyassets.daemon_server import (
    grant_universe_access,
    initialize_author_server,
)
from tinyassets.storage import db_path
from tinyassets.storage.request_admissions import RequestAdmissionStore
from tinyassets.work_targets import (
    ROLE_NOTES,
    load_work_targets,
    materialize_pending_requests,
    requests_path,
)


def _authorize_submitter(
    monkeypatch: pytest.MonkeyPatch,
    *,
    base: Path,
    universe_id: str,
    actor_id: str,
) -> None:
    identity = Identity(
        user_id=actor_id,
        username=actor_id,
        capabilities=["write"],
    )
    monkeypatch.setattr(
        "tinyassets.auth.middleware.current_identity",
        lambda: identity,
    )
    grant_universe_access(
        base,
        universe_id=universe_id,
        actor_id=actor_id,
        permission="write",
        granted_by=actor_id,
    )


@pytest.fixture
def universe_dir(tmp_path):
    d = tmp_path / "test-universe"
    d.mkdir()
    return d


def _write_requests(universe_dir, entries):
    requests_path(universe_dir).write_text(
        json.dumps(entries, indent=2), encoding="utf-8",
    )


def _read_requests(universe_dir):
    return json.loads(
        requests_path(universe_dir).read_text(encoding="utf-8"),
    )


def _declare_legacy_loop(universe_dir):
    (universe_dir / "PROGRAM.md").write_text(
        "Legacy fixture with an explicit compatibility Loop.",
        encoding="utf-8",
    )


def _commit_epoch2_request(base: Path, universe_id: str) -> dict:
    body = rfc8785.dumps({
        "branch_id": "",
        "directed_daemon_id": "",
        "directed_daemon_instruction": "",
        "pickup_incentive": "",
        "priority_weight": 25.0,
        "request_type": "scene_direction",
        "schema_version": "request-admission-v2",
        "text": "Make the market scene quieter.",
        "universe_id": universe_id,
    })
    return RequestAdmissionStore(base).commit_admission(
        tenant_id="tenant-a",
        actor_id="actor-a",
        universe_id=universe_id,
        idempotency_key_hash=(
            "hmac-sha256:"
            + hashlib.sha256(b"materialization-key").hexdigest()
        ),
        body_digest="sha256:" + hashlib.sha256(body).hexdigest(),
        body_digest_version="rfc8785-v1",
        request_type="scene_direction",
        text="Make the market scene quieter.",
        branch_id="",
        branch_def_id="fantasy_author:universe_cycle_wrapper",
        trigger_source="operator_request",
        accepted_priority_weight=25.0,
        policy_version="operator-priority-v1",
        grant_generation=1,
        receipt={
            "authority": "request-local",
            "grant_generation": 1,
            "priority_policy_version": "operator-priority-v1",
            "directed_assignment": {},
        },
        directed_daemon_id="",
        created_at="2026-07-24T10:00:00+00:00",
    )


def _claim_epoch2_request(base: Path, committed: dict) -> None:
    now = datetime.now(timezone.utc)
    descriptor = WorkerClaimDescriptor(
        queue_protocol_version=2,
        capabilities=frozenset({"operator_request_v1"}),
        worker_id="worker-a",
        runtime_instance_id="runtime-a",
        boot_id="boot-a",
        build_sha="a" * 40,
        config_hash="b" * 64,
        universe_id="test-universe",
        expires_at=(now + timedelta(seconds=60)).isoformat(),
    )
    claimed = Epoch2BranchTaskAdapter(
        base,
        clock=lambda: now,
    ).claim(
        committed["branch_task_id"],
        descriptor=descriptor,
        descriptor_reader=lambda _conn, _worker_id: descriptor,
        lease_seconds=90,
    )
    assert claimed is not None


def _epoch2_snapshot(base: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(db_path(base)) as conn:
        return {
            table: conn.execute(
                f"SELECT * FROM {table} ORDER BY rowid"  # noqa: S608
            ).fetchall()
            for table in (
                "user_requests",
                "request_admissions",
                "branch_tasks_v2",
                "request_admission_events",
            )
        }


# ─── materialize_pending_requests ──────────────────────────────────────


def test_materialize_creates_notes_target(universe_dir):
    _write_requests(universe_dir, [
        {
            "id": "req_1",
            "type": "scene_direction",
            "text": "Add a chase scene through the bazaar.",
            "branch_id": None,
            "status": "pending",
            "timestamp": "2026-04-14T12:00:00Z",
            "source": "alice",
        },
    ])
    created = materialize_pending_requests(universe_dir)
    assert len(created) == 1
    target = created[0]
    assert target.role == ROLE_NOTES
    assert "chase scene" in target.current_intent
    assert "user-request" in target.tags
    assert "scene_direction" in target.tags
    assert target.metadata["request_id"] == "req_1"
    assert target.metadata["request_source"] == "alice"


def test_materialize_flips_status_and_stamps_seen(universe_dir):
    _write_requests(universe_dir, [
        {"id": "req_2", "type": "revision", "text": "fix ch1",
         "status": "pending", "source": "bob"},
    ])
    materialize_pending_requests(universe_dir)
    reqs = _read_requests(universe_dir)
    assert reqs[0]["status"] == "seen"
    assert reqs[0]["seen_at"]
    assert reqs[0]["work_target_id"]


def test_materialize_is_idempotent_on_seen_requests(universe_dir):
    _write_requests(universe_dir, [
        {"id": "req_3", "type": "general", "text": "hi", "status": "pending"},
    ])
    first = materialize_pending_requests(universe_dir)
    second = materialize_pending_requests(universe_dir)
    assert len(first) == 1
    assert len(second) == 0
    # Only one target in registry.
    targets = [
        t for t in load_work_targets(universe_dir)
        if "user-request" in t.tags
    ]
    assert len(targets) == 1


def test_materialize_skips_malformed_entries(universe_dir):
    _write_requests(universe_dir, [
        "not a dict",
        {"id": "", "type": "x", "text": "no id", "status": "pending"},
        {"id": "req_4", "type": "general", "text": "ok", "status": "pending"},
        {"id": "req_5", "type": "general", "text": "already seen",
         "status": "seen"},
    ])
    created = materialize_pending_requests(universe_dir)
    assert len(created) == 1
    assert created[0].metadata["request_id"] == "req_4"


def test_materialize_missing_file_is_noop(universe_dir):
    # No requests.json on disk; should return [] without crashing.
    assert materialize_pending_requests(universe_dir) == []


def test_materialize_consumes_only_this_workers_live_epoch2_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    universe_dir = tmp_path / "test-universe"
    universe_dir.mkdir()
    initialize_author_server(tmp_path)
    committed = _commit_epoch2_request(tmp_path, universe_dir.name)
    _claim_epoch2_request(tmp_path, committed)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    monkeypatch.setattr(
        "tinyassets.branch_tasks_v2.EPOCH2_QUEUE_CONSUMER_READY",
        True,
    )
    before = _epoch2_snapshot(tmp_path)

    created = materialize_pending_requests(universe_dir)

    assert len(created) == 1
    target = created[0]
    assert target.current_intent == "Make the market scene quieter."
    assert target.metadata == {
        "request_id": committed["request_id"],
        "request_type": "scene_direction",
        "request_source": "actor-a",
        "request_timestamp": "2026-07-24T10:00:00+00:00",
        "branch_id": "",
        "queue_epoch": 2,
        "admission_id": committed["admission_id"],
        "branch_task_id": committed["branch_task_id"],
        "trigger_source": "operator_request",
        "accepted_priority_weight": 25.0,
        "claimed_by": "worker-a",
        "claimed_at": target.metadata["claimed_at"],
        "lease_expires_at": target.metadata["lease_expires_at"],
    }
    assert not requests_path(universe_dir).exists()
    assert _epoch2_snapshot(tmp_path) == before
    assert materialize_pending_requests(universe_dir) == []
    assert _epoch2_snapshot(tmp_path) == before


def test_materialize_leaves_unclaimed_or_not_ready_epoch2_work_inert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    universe_dir = tmp_path / "test-universe"
    universe_dir.mkdir()
    initialize_author_server(tmp_path)
    committed = _commit_epoch2_request(tmp_path, universe_dir.name)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    monkeypatch.setattr(
        "tinyassets.branch_tasks_v2.EPOCH2_QUEUE_CONSUMER_READY",
        True,
    )

    assert materialize_pending_requests(universe_dir) == []

    _claim_epoch2_request(tmp_path, committed)
    monkeypatch.setattr(
        "tinyassets.branch_tasks_v2.EPOCH2_QUEUE_CONSUMER_READY",
        False,
    )
    assert materialize_pending_requests(universe_dir) == []
    assert not requests_path(universe_dir).exists()


# ─── authorial_priority_review integration ─────────────────────────────


def test_authorial_review_surfaces_pending_request_within_one_cycle(
    universe_dir,
):
    """Core contract: submit_request → one review cycle → daemon sees it."""
    _write_requests(universe_dir, [
        {
            "id": "req_wiring",
            "type": "scene_direction",
            "text": "Insert a quiet moment in chapter 3.",
            "status": "pending",
            "source": "reader",
        },
    ])

    result = authorial_priority_review({
        "_universe_path": str(universe_dir),
        "workflow_instructions": {"premise": "Glass kingdom."},
    })

    # Daemon selected some target (the request or a seed — either is fine,
    # but the request must be in the candidate set).
    trace = result["quality_trace"][0]
    assert trace["materialized_request_count"] == 1

    # Request is now marked seen.
    reqs = _read_requests(universe_dir)
    assert reqs[0]["status"] == "seen"

    # A WorkTarget tagged user-request exists in the registry.
    targets = [
        t for t in load_work_targets(universe_dir)
        if "user-request" in t.tags
    ]
    assert len(targets) == 1
    assert targets[0].metadata["request_id"] == "req_wiring"


def test_authorial_review_no_requests_still_works(universe_dir):
    # Baseline: no requests.json should not disturb the existing flow.
    result = authorial_priority_review({
        "_universe_path": str(universe_dir),
        "workflow_instructions": {"premise": "Empty run."},
    })
    trace = result["quality_trace"][0]
    assert trace["materialized_request_count"] == 0


# ─── Hardening cluster (#22) ───────────────────────────────────────────


def test_corrupt_requests_json_warns_and_returns_empty(
    universe_dir, caplog,
):
    """Task #22.1: fail-loud on corrupt requests.json.

    Silent fallback made a scrambled file indistinguishable from no
    file — user requests vanished without trace. The read helper now
    emits a WARN so the host log surfaces the drop.
    """
    import logging

    requests_path(universe_dir).write_text(
        "not valid json {{{", encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="tinyassets.work_targets"):
        created = materialize_pending_requests(universe_dir)
    assert created == []
    assert any(
        "Failed to read JSON" in rec.message
        and str(requests_path(universe_dir)) in rec.message
        for rec in caplog.records
    )


def test_submit_request_rejects_oversize_text(tmp_path, monkeypatch):
    """Task #22.2: 8 KiB cap on submit_request.text.

    Prevents pasting full drafts into the request channel (add_canon is
    the right tool for long prose). Cap is UTF-8 byte length.
    """
    import importlib

    base = tmp_path / "output"
    base.mkdir()
    universe_dir = base / "test-universe"
    universe_dir.mkdir()
    _declare_legacy_loop(universe_dir)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    _authorize_submitter(
        monkeypatch,
        base=base,
        universe_id="test-universe",
        actor_id="tester",
    )
    from tinyassets.api import universe as us
    importlib.reload(us)
    try:
        oversize = "x" * (us._SUBMIT_REQUEST_MAX_BYTES + 1)
        result = json.loads(us._action_submit_request(
            universe_id="test-universe",
            text=oversize,
            request_type="general",
        ))
        assert "error" in result
        assert "exceeds" in result["error"]
        assert "add_canon" in result["error"]
        # No file should be created on rejection.
        assert not (base / "test-universe" / "requests.json").exists()
    finally:
        importlib.reload(us)


def test_submit_request_accepts_text_at_cap(tmp_path, monkeypatch):
    """Exactly _SUBMIT_REQUEST_MAX_BYTES bytes must still land."""
    import importlib

    base = tmp_path / "output"
    base.mkdir()
    universe_dir = base / "test-universe"
    universe_dir.mkdir()
    _declare_legacy_loop(universe_dir)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    _authorize_submitter(
        monkeypatch,
        base=base,
        universe_id="test-universe",
        actor_id="tester",
    )
    from tinyassets.api import universe as us
    importlib.reload(us)
    try:
        at_cap = "x" * us._SUBMIT_REQUEST_MAX_BYTES
        result = json.loads(us._action_submit_request(
            universe_id="test-universe",
            text=at_cap,
            request_type="general",
        ))
        assert "error" not in result
        assert result["status"] == "pending"
    finally:
        importlib.reload(us)


def test_submit_request_response_includes_queue_position(monkeypatch, tmp_path):
    """Response shape: queue_position + ahead_of_yours + what_happens_next.

    Replaces the opaque request_id-only response with information a user
    can act on: where they are in the queue and what to do next.
    """
    import importlib

    base = tmp_path / "uni"
    universe_dir = base / "test-universe"
    universe_dir.mkdir(parents=True)
    _declare_legacy_loop(universe_dir)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    _authorize_submitter(
        monkeypatch,
        base=base,
        universe_id="test-universe",
        actor_id="alice",
    )
    from tinyassets.api import universe as us
    importlib.reload(us)
    try:
        first = json.loads(us._action_submit_request(
            universe_id="test-universe", text="first", request_type="general"))
        assert first["queue_position"] == 1
        assert first["ahead_of_yours"] == 0
        assert "next in the daemon's queue" in first["what_happens_next"]
        assert "inspect" in first["what_happens_next"]

        second = json.loads(us._action_submit_request(
            universe_id="test-universe", text="second", request_type="general"))
        assert second["queue_position"] == 2
        assert second["ahead_of_yours"] == 1
        assert "1 other request is ahead" in second["what_happens_next"]
    finally:
        importlib.reload(us)


def test_submit_request_write_uses_centralized_filename_constant():
    """Task #22.3: write site imports REQUESTS_FILENAME, doesn't hardcode.

    Source-level check — ensures the two previously duplicated string
    literals now share the work_targets constant.
    """
    from pathlib import Path as _Path

    # Step 9 (decomp): _action_submit_request and _action_inspect_universe
    # moved to tinyassets/api/universe.py. Scan there now.
    src = _Path("tinyassets/api/universe.py").read_text(encoding="utf-8")
    # _action_submit_request and _action_inspect_universe should both
    # import REQUESTS_FILENAME rather than hardcoding "requests.json".
    # Two imports expected (one per action). Zero bare literals of the
    # filename allowed outside import statements.
    import_hits = src.count("from tinyassets.work_targets import REQUESTS_FILENAME")
    assert import_hits >= 2, (
        f"expected >=2 REQUESTS_FILENAME imports, found {import_hits}"
    )
    # No remaining bare "requests.json" strings in the module.
    assert "\"requests.json\"" not in src, (
        "still a hardcoded 'requests.json' literal after centralization"
    )
