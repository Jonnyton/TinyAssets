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


def test_seeded_reference_keeps_full_topology(data_dir):
    # Codex S1 review critical: the publish step must not drop the graph —
    # a raw row re-save emptied edges/conditional_edges, leaving a 7-node
    # graph with no wiring. Assert the seeded branch round-trips complete.
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition, list_branch_definitions

    seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    bdid = list_branch_definitions(data_dir, tag=tag)[0]["branch_def_id"]
    branch = BranchDefinition.from_dict(
        get_branch_definition(data_dir, branch_def_id=bdid)
    )
    artifact = next(
        a for a in load_design_artifacts()
        if a["design_id"] == "patch_loop_reference"
    )
    assert len(branch.node_defs) == len(artifact["spec"]["node_defs"])
    assert len(branch.edges) == len(artifact["spec"]["edges"])
    assert len(branch.conditional_edges) == len(
        artifact["spec"]["conditional_edges"]
    )
    assert branch.published is True


def test_seeded_reference_is_discoverable_in_published_listing(data_dir):
    # Codex S1 review critical: the published listing filters on published
    # BRANCH VERSIONS, not the bare flag — the seed must mint one or the
    # commons listing shows nothing to remix.
    from tinyassets.api.branches import _ext_branch_list
    from tinyassets.daemon_server import list_branch_definitions

    seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    bdid = list_branch_definitions(data_dir, tag=tag)[0]["branch_def_id"]
    listed = json.loads(_ext_branch_list({"scope": "published"}))
    ids = {b["branch_def_id"] for b in listed["branches"]}
    assert bdid in ids, listed


def test_seeded_reference_is_discoverable_as_sandbox_requiring(data_dir):
    # Codex S1 round-4 CRITICAL (Finding 2): the reference patch loop's
    # draft_patch node is a coding agent that MUST run sandboxed. The artifact
    # carries requires_sandbox=true and build_branch must thread it, so the
    # seeded reference surfaces under the requires_sandbox=any filter — and is
    # excluded by requires_sandbox=none (design-only branches).
    from tinyassets.api.branches import _ext_branch_list
    from tinyassets.daemon_server import list_branch_definitions

    seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    bdid = list_branch_definitions(data_dir, tag=tag)[0]["branch_def_id"]

    any_listed = json.loads(
        _ext_branch_list({"scope": "published", "requires_sandbox": "any"})
    )
    any_ids = {b["branch_def_id"] for b in any_listed["branches"]}
    assert bdid in any_ids, any_listed
    # The listing summary also reports the sandbox flag for this branch.
    summary = next(b for b in any_listed["branches"] if b["branch_def_id"] == bdid)
    assert summary["has_sandbox_nodes"] is True

    none_listed = json.loads(
        _ext_branch_list({"scope": "published", "requires_sandbox": "none"})
    )
    none_ids = {b["branch_def_id"] for b in none_listed["branches"]}
    assert bdid not in none_ids, none_listed


def test_seed_repairs_incomplete_prior_seed(data_dir):
    # Codex S1 review: a prior seed that crashed after branch build but before
    # publish leaves a tagged row that never appears in the published listing.
    # The next seed must REPAIR it in place, not skip it as "present".
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_list
    from tinyassets.branch_designs import REFERENCE_TAG
    from tinyassets.daemon_server import initialize_author_server, list_branch_definitions

    initialize_author_server(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    artifact = next(
        a for a in load_design_artifacts()
        if a["design_id"] == "patch_loop_reference"
    )
    # Simulate a crash-after-build: build + tag, but DO NOT publish a version.
    spec = dict(artifact["spec"])
    spec["tags"] = sorted(set(list(spec.get("tags") or []) + [REFERENCE_TAG, tag]))
    out = json.loads(_ext_branch_build({"spec_json": json.dumps(spec)}))
    assert out["status"] == "built"
    # Not in the published listing yet (no version) — the broken state.
    pre = json.loads(_ext_branch_list({"scope": "published"}))
    assert out["branch_def_id"] not in {b["branch_def_id"] for b in pre["branches"]}

    # Re-seed repairs it in place (same id, now published + versioned).
    results = seed_reference_designs(data_dir)
    assert tag in results["seeded"]              # repaired, not skipped as present
    rows = list_branch_definitions(data_dir, tag=tag)
    assert len(rows) == 1                        # no duplicate row minted
    assert rows[0]["branch_def_id"] == out["branch_def_id"]
    post = json.loads(_ext_branch_list({"scope": "published"}))
    assert out["branch_def_id"] in {b["branch_def_id"] for b in post["branches"]}


def test_content_drift_is_repaired_not_present(data_dir):
    # Codex S1 review critical: a same-count content drift (a corrupted prompt,
    # topology counts unchanged) must be REPAIRED on re-seed, never reported
    # `present`. A count-only health check would miss it.
    from tinyassets.api.branches import _ext_branch_list
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import (
        get_branch_definition,
        list_branch_definitions,
        save_branch_definition,
    )

    seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    bdid = list_branch_definitions(data_dir, tag=tag)[0]["branch_def_id"]

    # Corrupt one prompt in place — same size, same topology counts.
    branch = BranchDefinition.from_dict(
        get_branch_definition(data_dir, branch_def_id=bdid)
    )
    branch.node_defs[0].prompt_template = "CORRUPTED SAME-SIZED REFERENCE"
    save_branch_definition(data_dir, branch_def=branch.to_dict())

    results = seed_reference_designs(data_dir)
    assert tag in results["seeded"]              # repaired
    assert tag not in results["present"]         # NOT waved through
    healed = BranchDefinition.from_dict(
        get_branch_definition(data_dir, branch_def_id=bdid)
    )
    assert healed.node_defs[0].prompt_template != "CORRUPTED SAME-SIZED REFERENCE"
    rows = list_branch_definitions(data_dir, tag=tag)
    assert len(rows) == 1                        # repaired in place, no duplicate
    listed = json.loads(_ext_branch_list({"scope": "published"}))
    assert bdid in {b["branch_def_id"] for b in listed["branches"]}


def test_wiki_file_bug_goal_canonical_only_queues(data_dir, monkeypatch):
    # Codex S1 review critical: goal-canonical must resolve against the CANONICAL
    # root, so a root goal canonical queues an investigation on the real
    # _wiki_file_bug path with ONLY GOAL_ID set (no env fallback). Unmocked.
    from tinyassets.api.wiki import _wiki_file_bug
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.daemon_server import (
        initialize_author_server,
        save_branch_definition,
        save_goal,
        set_canonical_branch,
    )

    initialize_author_server(data_dir)
    handler = dict(
        branch_def_id="handler-live", name="handler-live", description="",
        author="host", graph_nodes=[], edges=[], state_schema=[],
        entry_point="", node_defs=[],
    )
    save_branch_definition(data_dir, branch_def=handler)     # exists at the root
    ver = publish_branch_version(
        data_dir, branch_dict=handler, notes="v1", publisher="host",
    )
    save_goal(data_dir, goal=dict(
        goal_id="g-inv", name="inv", description="",
        author="host", tags=[], visibility="public",
    ))
    set_canonical_branch(
        data_dir, goal_id="g-inv",
        branch_version_id=ver.branch_version_id, set_by="host",
    )
    monkeypatch.setenv("TINYASSETS_BUG_INVESTIGATION_GOAL_ID", "g-inv")
    monkeypatch.delenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", raising=False)

    out = json.loads(_wiki_file_bug(
        component="scheduler", severity="minor",
        title="goal-canonical queue probe",
        observed="root goal canonical", expected="queued", kind="bug",
    ))
    assert out["status"] == "filed"
    assert out["investigation"]["status"] == "queued"   # NOT skipped/no_canonical
    assert out["investigation"]["dispatcher_request_id"]


def test_reseed_after_healthy_is_present_not_reseeded(data_dir):
    seed_reference_designs(data_dir)
    again = seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    assert tag in again["present"]               # healthy -> present, no rework
    assert again["seeded"] == []


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


def test_stdio_startup_seeds_reference_designs(data_dir, monkeypatch):
    # Codex S1 round-4 CRITICAL (Finding 1): stdio/MCPB startup goes straight
    # to mcp.run() and never runs the Streamable-HTTP lifespan, so the seed
    # must live on a transport-agnostic startup seam (top of main()). Stub
    # mcp.run so the boot returns, then assert the reference IS seeded — a
    # stdio boot must NOT leave the commons with zero reference designs.
    from tinyassets import universe_server
    from tinyassets.daemon_server import list_branch_definitions

    ran: list[tuple] = []
    monkeypatch.setattr(
        universe_server.mcp, "run", lambda *a, **k: ran.append((a, k)),
    )

    universe_server.main(transport="stdio")

    assert ran, "stdio transport must reach mcp.run()"
    tag = design_tag("patch_loop_reference", 1)
    rows = list_branch_definitions(data_dir, tag=tag)
    assert len(rows) == 1, "stdio startup must seed the reference design"
    assert rows[0]["published"] is True


def test_seed_reference_designs_best_effort_survives_failure(monkeypatch, caplog):
    # The shared startup seam is best-effort: a seed crash logs loudly but
    # NEVER raises, so a broken seed can't take down server startup.
    from tinyassets import universe_server

    def _boom(*a, **k):
        raise RuntimeError("seed exploded")

    monkeypatch.setattr(
        "tinyassets.branch_designs.seed_reference_designs", _boom,
    )
    with caplog.at_level("ERROR"):
        results = universe_server._seed_reference_designs_best_effort()
    assert results == {"seeded": [], "present": [], "failed": []}
    assert any("seeding crashed" in r.message for r in caplog.records)


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


def test_dead_goal_canonical_does_not_fall_through_to_env(data_dir, monkeypatch):
    # Codex S1 review critical: if the goal-canonical (authoritative) handler
    # resolves to a DEAD branch, the trigger must FAIL — it must NOT silently
    # fall through to a live env fallback (which would run the wrong branch).
    from unittest.mock import patch

    from tinyassets.bug_investigation import resolve_investigation_handler_detail
    from tinyassets.daemon_server import list_branch_definitions, save_goal

    seed_reference_designs(data_dir)
    live = list_branch_definitions(
        data_dir, tag=design_tag("patch_loop_reference", 1),
    )[0]["branch_def_id"]

    # A goal whose canonical resolves to a DEAD branch def, plus a LIVE env
    # fallback. Stub the canonical resolver to return the dead ref (the goal's
    # canonical binding pointing at a since-deleted branch) so the test targets
    # the resolver's fall-through behavior, not goal/version plumbing.
    save_goal(data_dir, goal=dict(
        goal_id="g-inv", name="inv", description="",
        author="host", tags=[], visibility="public",
    ))
    with patch(
        "tinyassets.api.canonical_dispatch.resolve_canonical_for_run",
        return_value={"ok": True, "branch_def_id": "deadbranch000",
                      "branch_version_id": "deadversion", "source": "canonical"},
    ):
        monkeypatch.setenv("TINYASSETS_BUG_INVESTIGATION_GOAL_ID", "g-inv")
        monkeypatch.setenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", live)
        bdid, reason = resolve_investigation_handler_detail(data_dir)
    assert bdid == ""                             # fails, does NOT use live env
    assert reason.startswith("handler_not_found:")
    assert live not in reason


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
