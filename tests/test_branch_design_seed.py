"""S1 of docs/design-notes/2026-07-15-user-patch-loop-reference-design.md:
the durable reference patch-loop design — portable artifact validity,
repo-blindness, idempotent seeding, and the G4 dead-handler fail-loud guard
(loud on the trigger, never the filing).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tinyassets.branch_designs import (
    DESIGN_FORMAT,
    REFERENCE_TAG,
    design_tag,
    load_design_artifacts,
    seed_reference_designs,
)


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch) -> Path:
    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    return base


# ── Artifact contract ──────────────────────────────────────────────────────


def test_artifacts_load_and_carry_envelope():
    artifacts = load_design_artifacts()
    assert artifacts, "at least the patch_loop_reference artifact must ship"
    ids = [a["design_id"] for a in artifacts]
    assert "patch_loop_reference" in ids
    for artifact in artifacts:
        assert artifact["design_format"] == DESIGN_FORMAT
        assert int(artifact["design_version"]) >= 1
        spec = artifact["spec"]
        assert spec["name"] and spec["node_defs"] and spec["edges"]


def test_patch_loop_reference_is_repo_blind():
    # The reference must carry NO repository identity anywhere — binding a
    # repo/credential is a user act at remix time (host steer 2026-07-15).
    raw = json.dumps(
        next(
            a for a in load_design_artifacts()
            if a["design_id"] == "patch_loop_reference"
        )
    ).lower()
    for forbidden in ("github.com/", "jonnyton", "tinyassets.git", "git@"):
        assert forbidden not in raw, f"repo identity leaked: {forbidden}"
    # Binding surfaces exist as unbound state fields, not baked values.
    artifact = next(
        a for a in load_design_artifacts()
        if a["design_id"] == "patch_loop_reference"
    )
    field_names = {f["name"] for f in artifact["spec"]["state_schema"]}
    assert {"target_repo", "credential_ref", "merge_policy"} <= field_names


def test_patch_loop_reference_builds_through_user_path(data_dir):
    # The artifact's spec must pass the SAME composite build_branch validation
    # a user's chatbot goes through — the reference is an ordinary user build.
    from tinyassets.api.branches import _ext_branch_build

    artifact = next(
        a for a in load_design_artifacts()
        if a["design_id"] == "patch_loop_reference"
    )
    out = json.loads(_ext_branch_build({
        "spec_json": json.dumps(artifact["spec"]),
    }))
    assert out.get("status") == "built", out
    assert out["branch_def_id"]


# ── Seeder ────────────────────────────────────────────────────────────────


def test_seed_reference_designs_seeds_and_publishes(data_dir):
    from tinyassets.daemon_server import list_branch_definitions

    results = seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    assert tag in results["seeded"]
    assert results["failed"] == []

    rows = list_branch_definitions(data_dir, tag=tag)
    assert len(rows) == 1
    row = rows[0]
    assert row["published"] is True
    assert REFERENCE_TAG in row["tags"]


def test_seed_reference_designs_is_idempotent(data_dir):
    from tinyassets.daemon_server import list_branch_definitions

    first = seed_reference_designs(data_dir)
    second = seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    assert tag in first["seeded"]
    assert tag in second["present"]          # not re-seeded
    assert second["seeded"] == []
    rows = list_branch_definitions(data_dir, tag=tag)
    assert len(rows) == 1                    # exactly one, never duplicated


def test_seed_failure_is_loud_but_contained(data_dir, monkeypatch, caplog):
    # A broken seed must be recorded + logged loudly, never raise (startup
    # survives; the canary/logs surface it).
    import tinyassets.branch_designs as bd

    def _boom(*a, **k):
        raise RuntimeError("registry exploded")

    monkeypatch.setattr(
        "tinyassets.daemon_server.list_branch_definitions", _boom,
    )
    with caplog.at_level("ERROR"):
        results = bd.seed_reference_designs(data_dir)
    assert results["seeded"] == []
    assert results["failed"], "failure must be recorded"
    assert any("CRASHED" in r.message for r in caplog.records)


# ── G4: dead-handler fail-loud guard ──────────────────────────────────────


def test_resolver_refuses_dead_handler_ref(data_dir, monkeypatch):
    from tinyassets.bug_investigation import (
        _resolve_investigation_handler,
        resolve_investigation_handler_detail,
    )

    monkeypatch.delenv("TINYASSETS_BUG_INVESTIGATION_GOAL_ID", raising=False)
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "deadbeef0000",
    )
    bdid, reason = resolve_investigation_handler_detail(data_dir)
    assert bdid == ""
    assert reason == "handler_not_found:deadbeef0000"
    assert _resolve_investigation_handler(data_dir) == ""


def test_resolver_accepts_existing_handler(data_dir, monkeypatch):
    from tinyassets.bug_investigation import resolve_investigation_handler_detail

    seed_reference_designs(data_dir)
    from tinyassets.daemon_server import list_branch_definitions

    bdid = list_branch_definitions(
        data_dir, tag=design_tag("patch_loop_reference", 1),
    )[0]["branch_def_id"]

    monkeypatch.delenv("TINYASSETS_BUG_INVESTIGATION_GOAL_ID", raising=False)
    monkeypatch.setenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", bdid)
    resolved, reason = resolve_investigation_handler_detail(data_dir)
    assert resolved == bdid
    assert reason == "ok"


def test_resolver_not_configured(data_dir, monkeypatch):
    from tinyassets.bug_investigation import resolve_investigation_handler_detail

    monkeypatch.delenv("TINYASSETS_BUG_INVESTIGATION_GOAL_ID", raising=False)
    monkeypatch.delenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", raising=False,
    )
    assert resolve_investigation_handler_detail(data_dir) == ("", "not_configured")


def test_file_bug_dead_handler_fails_trigger_keeps_filing(data_dir, monkeypatch):
    # End-to-end G4: filing with a dead handler ref surfaces an explicit
    # failed trigger, enqueues NOTHING, and the filing itself persists.
    from tinyassets.api.wiki import _wiki_file_bug
    from tinyassets.branch_tasks import read_queue

    monkeypatch.delenv("TINYASSETS_BUG_INVESTIGATION_GOAL_ID", raising=False)
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "deadbeef0000",
    )
    out = json.loads(_wiki_file_bug(
        component="scheduler",
        severity="minor",
        title="G4 regression probe",
        observed="dead handler ref",
        expected="explicit failed trigger; filing persists",
        kind="bug",
    ))
    assert out["status"] == "filed"                    # the filing PERSISTS
    assert out["investigation"]["status"] == "failed"  # loud on the trigger
    assert out["investigation"]["error"] == "handler_not_found"
    # Nothing was enqueued against the dead ref.
    universe_dirs = [
        p for p in data_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ]
    for udir in universe_dirs:
        assert all(
            t.branch_def_id != "deadbeef0000" for t in read_queue(udir)
        )
    # The trigger receipt records the dead ref for audit.
    trigger = out.get("trigger") or {}
    assert trigger.get("status") == "failed"
    assert "handler_not_found" in (trigger.get("error") or {}).get("class", "")


def test_file_bug_with_live_handler_still_queues(data_dir, monkeypatch):
    # Regression guard: G4 must not break the healthy path — an EXISTING
    # handler still enqueues exactly as before.
    from tinyassets.api.wiki import _wiki_file_bug

    seed_reference_designs(data_dir)
    from tinyassets.daemon_server import list_branch_definitions

    bdid = list_branch_definitions(
        data_dir, tag=design_tag("patch_loop_reference", 1),
    )[0]["branch_def_id"]
    monkeypatch.delenv("TINYASSETS_BUG_INVESTIGATION_GOAL_ID", raising=False)
    monkeypatch.setenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", bdid)

    out = json.loads(_wiki_file_bug(
        component="scheduler",
        severity="minor",
        title="G4 healthy-path probe",
        observed="live handler",
        expected="queued investigation",
        kind="bug",
    ))
    assert out["status"] == "filed"
    assert out["investigation"]["status"] == "queued"
    assert out["investigation"]["dispatcher_request_id"]
