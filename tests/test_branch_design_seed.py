"""S1 of docs/design-notes/2026-07-15-user-patch-loop-reference-design.md:
the durable reference patch-loop design — portable artifact validity,
repo-blindness, idempotent seeding, and the G4 dead-handler fail-loud guard
(loud on the trigger, never the filing).
"""

from __future__ import annotations

import json
import os
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
    assert {"target_repo", "merge_policy"} <= field_names
    # Codex S1 latest-model Finding 4a: credentials are NOT part of the design.
    # The real github effector resolves the push credential from the universe
    # vault BY DESTINATION and never exposes a handle to the model, so
    # credential_ref must appear NOWHERE — not as state, not in any prompt.
    assert "credential_ref" not in field_names
    assert "credential_ref" not in raw


def test_binding_fields_marked_and_survive_into_branch_version(data_dir):
    # Codex S1 r15 addendum A: the execution-gating binding surfaces must be
    # marked is_binding so S2's branch-version guard can keep a remix INERT
    # until the owner binds them. The marker must SURVIVE the build/seed path
    # into the persisted BranchDefinition (that is what branch_versions reads),
    # not just live in the raw artifact.
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import (
        get_branch_definition,
        list_branch_definitions,
    )

    artifact = next(
        a for a in load_design_artifacts()
        if a["design_id"] == "patch_loop_reference"
    )
    by_name = {f["name"]: f for f in artifact["spec"]["state_schema"]}
    # target_repo (destination) MUST be marked — it execution-gates the loop.
    assert by_name["target_repo"].get("is_binding") is True
    # merge_policy is the owner's merge-authority preference — marked binding
    # so no silent default can auto-merge to the owner's repo unbound.
    assert by_name["merge_policy"].get("is_binding") is True

    # r15 addendum A / r10 Finding 4a reconciliation: there is NO separate
    # credential binding field. The credential is resolved BY DESTINATION at
    # write time (never a handle in state or prompts), so binding target_repo
    # IS binding the credential-lookup key; a missing credential fails closed
    # at the effector. A credential_ref binding would be redundant with
    # target_repo AND reintroduce the forbidden handle, so none is added.
    assert all(
        not (f.get("is_binding") and "credential" in f["name"].lower())
        for f in artifact["spec"]["state_schema"]
    )

    # The marker must round-trip into the persisted branch S2's guard reads.
    seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    bdid = list_branch_definitions(data_dir, tag=tag)[0]["branch_def_id"]
    branch = BranchDefinition.from_dict(
        get_branch_definition(data_dir, branch_def_id=bdid)
    )
    persisted = {f.get("name"): f for f in branch.state_schema}
    assert persisted["target_repo"].get("is_binding") is True
    assert persisted["merge_policy"].get("is_binding") is True


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
    # Codex S1 review: a prior seed that crashed AFTER overwrite but BEFORE
    # publish leaves the reserved-id row with content but no published version —
    # it never appears in the published listing. The next seed must REPAIR it in
    # place (publish), not skip it as "present", and never mint a duplicate.
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_list
    from tinyassets.branch_designs import (
        REFERENCE_TAG,
        _overwrite_reference_content,
        _reference_branch_id,
    )
    from tinyassets.daemon_server import (
        delete_branch_definition,
        initialize_author_server,
        list_branch_definitions,
    )

    initialize_author_server(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)
    artifact = next(
        a for a in load_design_artifacts()
        if a["design_id"] == "patch_loop_reference"
    )
    # Copy authoritative content onto the RESERVED fixed id but do NOT publish a
    # version — the crash-after-overwrite state. (Build a scaffold temp for the
    # content, then discard it so only the reserved fixed-id row carries the tag.)
    spec = dict(artifact["spec"])
    spec["tags"] = sorted(set(list(spec.get("tags") or []) + [REFERENCE_TAG, tag]))
    out = json.loads(_ext_branch_build({"spec_json": json.dumps(spec)}))
    assert out["status"] == "built"
    _overwrite_reference_content(data_dir, fixed_id, out["branch_def_id"])
    delete_branch_definition(data_dir, branch_def_id=out["branch_def_id"])
    # Reserved row exists at the fixed id but has no published version yet.
    pre = json.loads(_ext_branch_list({"scope": "published"}))
    assert fixed_id not in {b["branch_def_id"] for b in pre["branches"]}

    # Re-seed repairs it in place (same fixed id, now published + versioned).
    results = seed_reference_designs(data_dir)
    assert tag in results["seeded"]              # repaired, not skipped as present
    rows = list_branch_definitions(data_dir, tag=tag)
    assert len(rows) == 1                        # no duplicate row minted
    assert rows[0]["branch_def_id"] == fixed_id
    post = json.loads(_ext_branch_list({"scope": "published"}))
    assert fixed_id in {b["branch_def_id"] for b in post["branches"]}


def test_rolled_back_content_is_quarantined_not_reactivated(data_dir):
    # Codex r11 #1 (CRITICAL): a rolled-back version is a deliberate
    # security/regression decision. Re-publishing the SAME content as a fresh
    # active version (r10's approach) functionally RESURRECTS the rolled-back
    # reference at restart. So same-hash rolled-back content is QUARANTINED: the
    # seed reports it unhealthy (a <quarantined-rolled-back-content:...> marker),
    # NEVER reactivates it, and leaves the rolled-back audit intact — until the
    # artifact content actually changes (a new hash).
    from tinyassets.branch_designs import _reference_branch_id
    from tinyassets.branch_versions import _connect, list_branch_versions
    from tinyassets.daemon_server import list_branch_definitions

    seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)
    versions = list_branch_versions(data_dir, fixed_id, limit=50)
    assert len(versions) == 1 and versions[0].status == "active"
    rolled_id = versions[0].branch_version_id

    # Roll back the only version WITH audit fields — as the rollback engine does.
    with _connect(data_dir) as conn:
        conn.execute(
            "UPDATE branch_versions SET status='rolled_back', "
            "rolled_back_at='2026-07-15T00:00:00Z', rolled_back_by='security', "
            "rolled_back_reason='regression detected' WHERE branch_version_id=?",
            (rolled_id,),
        )

    results = seed_reference_designs(data_dir)
    # QUARANTINED — reported unhealthy, NOT seeded/present.
    assert "<quarantined-rolled-back-content:patch_loop_reference>" in results["failed"]
    assert tag not in results["seeded"]
    assert tag not in results["present"]

    after = list_branch_versions(data_dir, fixed_id, limit=50)
    # The rolled-back version is UNTOUCHED and NOT reactivated; NO active version.
    rolled = next(v for v in after if v.branch_version_id == rolled_id)
    assert rolled.status == "rolled_back"
    assert rolled.rolled_back_by == "security"
    assert rolled.rolled_back_reason == "regression detected"
    assert rolled.rolled_back_at == "2026-07-15T00:00:00Z"
    assert not any(v.status == "active" for v in after)   # NOT resurrected
    # Still exactly one reference branch row.
    rows = list_branch_definitions(data_dir, tag=tag)
    assert len(rows) == 1


def test_changed_artifact_after_rollback_seeds_fresh_active(data_dir, tmp_path, monkeypatch):
    # Codex r11 #1: only a genuinely DIFFERENT artifact (a new content hash = a
    # real fix / version bump) re-activates after a rollback. The rolled-back
    # (old-hash) version stays rolled_back; a NEW active version is minted.
    import tinyassets.branch_designs as bd
    from tinyassets.branch_designs import _reference_branch_id
    from tinyassets.branch_versions import _connect, list_branch_versions

    seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)
    old_version_id = list_branch_versions(data_dir, fixed_id, limit=50)[0].branch_version_id

    with _connect(data_dir) as conn:
        conn.execute(
            "UPDATE branch_versions SET status='rolled_back', rolled_back_by='sec' "
            "WHERE branch_version_id=?", (old_version_id,),
        )

    # Point the package at a CHANGED artifact (new content hash = a real fix).
    orig = next(
        a for a in bd.load_design_artifacts()
        if a["design_id"] == "patch_loop_reference"
    )
    changed = json.loads(json.dumps(orig))
    changed["spec"]["node_defs"][0]["prompt_template"] += " (v1.0.1 fix)"
    designs = tmp_path / "designs2"
    designs.mkdir()
    (designs / "patch_loop_reference.json").write_text(
        json.dumps(changed), encoding="utf-8",
    )
    monkeypatch.setattr(bd, "DESIGNS_DIR", designs)

    results = seed_reference_designs(data_dir)
    assert tag in results["seeded"]              # new hash -> fresh active
    after = list_branch_versions(data_dir, fixed_id, limit=50)
    # The old (rolled-back) version stays rolled_back; a NEW active exists.
    assert any(v.branch_version_id == old_version_id and v.status == "rolled_back" for v in after)
    active = [v for v in after if v.status == "active"]
    assert len(active) == 1
    assert active[0].branch_version_id != old_version_id


def test_multi_version_rollback_not_reported_present(data_dir):
    # Codex r12 #1 (CRITICAL): health must require an ACTIVE version whose content
    # matches the AUTHORITATIVE hash. "Any active version" was bypassable — roll
    # back the authoritative version while a DIFFERENT active version exists and
    # the row keeps serving rolled-back content, yet health reported present.
    import uuid
    from datetime import datetime, timezone

    from tinyassets.branch_designs import _reference_branch_id
    from tinyassets.branch_versions import _connect, list_branch_versions

    seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)
    auth_version = list_branch_versions(data_dir, fixed_id, limit=50)[0]

    # Roll back the AUTHORITATIVE version, and inject a DIFFERENT active version
    # (a stale content at a non-authoritative hash).
    with _connect(data_dir) as conn:
        conn.execute(
            "UPDATE branch_versions SET status='rolled_back', rolled_back_by='sec' "
            "WHERE branch_version_id=?", (auth_version.branch_version_id,),
        )
        conn.execute(
            "INSERT INTO branch_versions (branch_version_id, branch_def_id, "
            "content_hash, snapshot_json, notes, publisher, published_at, "
            "parent_version_id, status, watch_window_seconds) "
            "VALUES (?,?,?,?,?,?,?,?, 'active', ?)",
            (
                f"{fixed_id}@stale-{uuid.uuid4().hex[:8]}", fixed_id,
                "stale_hash_" + uuid.uuid4().hex, "{}", "stale", "x",
                datetime.now(timezone.utc).isoformat(), None, 86400,
            ),
        )
    # A DIFFERENT active version exists — but NOT at the authoritative hash.
    assert any(v.status == "active" for v in list_branch_versions(data_dir, fixed_id, limit=50))

    results = seed_reference_designs(data_dir)
    # NOT present (the old bug); quarantined because the authoritative content
    # is the rolled-back one with no active version at its hash.
    assert tag not in results["present"], results
    assert "<quarantined-rolled-back-content:patch_loop_reference>" in results["failed"]


def test_rolled_back_reference_vanishes_from_published_discovery(data_dir):
    # Codex r15 #1 (CRITICAL): quarantine must remove the reference from
    # DISCOVERY too. scope=published took the NEWEST version regardless of
    # status, so a rolled-back reference still showed as published/remixable.
    # After rolling back the only version, discovery must return EMPTY (the
    # discovery query filters for ACTIVE versions).
    from tinyassets.api.branches import _ext_branch_list
    from tinyassets.branch_designs import _reference_branch_id
    from tinyassets.branch_versions import _connect, list_branch_versions

    seed_reference_designs(data_dir)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)
    pre = json.loads(_ext_branch_list({"scope": "published"}))
    assert fixed_id in {b["branch_def_id"] for b in pre["branches"]}   # listed while active

    with _connect(data_dir) as conn:
        conn.execute(
            "UPDATE branch_versions SET status='rolled_back' WHERE branch_def_id=?",
            (fixed_id,),
        )
    assert not any(
        v.status == "active" for v in list_branch_versions(data_dir, fixed_id, limit=50)
    )

    post = json.loads(_ext_branch_list({"scope": "published"}))
    assert fixed_id not in {b["branch_def_id"] for b in post["branches"]}, post


def test_multi_version_rollback_vanishes_from_discovery(data_dir):
    # Codex r16 #3: DISCOVERY (not just health) must be content-consistent. The
    # r15 #1 fix picked the newest ACTIVE version regardless of content, so with
    # the authoritative version rolled back and an UNRELATED older version still
    # active, scope=published returned the rolled-back reference paired with the
    # stale active version id — an inconsistent (branch, version) pair that kept
    # the rolled-back reference remixable. Require content consistency: no active
    # version matching the branch's current content => it must vanish.
    import uuid
    from datetime import datetime, timezone

    from tinyassets.api.branches import _ext_branch_list
    from tinyassets.branch_designs import _reference_branch_id
    from tinyassets.branch_versions import _connect, list_branch_versions

    seed_reference_designs(data_dir)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)
    pre = json.loads(_ext_branch_list({"scope": "published"}))
    assert fixed_id in {b["branch_def_id"] for b in pre["branches"]}

    auth_version = list_branch_versions(data_dir, fixed_id, limit=50)[0]
    # Roll back the AUTHORITATIVE version and inject a DIFFERENT active version at
    # a NON-authoritative content hash (the multi-version rollback shape).
    with _connect(data_dir) as conn:
        conn.execute(
            "UPDATE branch_versions SET status='rolled_back', rolled_back_by='sec' "
            "WHERE branch_version_id=?", (auth_version.branch_version_id,),
        )
        conn.execute(
            "INSERT INTO branch_versions (branch_version_id, branch_def_id, "
            "content_hash, snapshot_json, notes, publisher, published_at, "
            "parent_version_id, status, watch_window_seconds) "
            "VALUES (?,?,?,?,?,?,?,?, 'active', ?)",
            (
                f"{fixed_id}@stale-{uuid.uuid4().hex[:8]}", fixed_id,
                "stale_hash_" + uuid.uuid4().hex, "{}", "stale", "x",
                datetime.now(timezone.utc).isoformat(), None, 86400,
            ),
        )
    # A DIFFERENT active version exists — but NOT at the authoritative content.
    assert any(
        v.status == "active"
        for v in list_branch_versions(data_dir, fixed_id, limit=50)
    )
    # Discovery must NOT surface the reference paired with the unrelated active
    # version — the (branch, version) pair would be content-inconsistent.
    post = json.loads(_ext_branch_list({"scope": "published"}))
    assert fixed_id not in {b["branch_def_id"] for b in post["branches"]}, post


def test_interrupted_publication_mismatched_active_is_repaired(data_dir):
    # Codex r12 #1: an ACTIVE version whose content != the authoritative artifact
    # (interrupted / mismatched publication) must FAIL health and be repaired.
    from tinyassets.branch_designs import _reference_branch_id
    from tinyassets.branch_versions import _connect, list_branch_versions

    seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)
    auth_id = list_branch_versions(data_dir, fixed_id, limit=50)[0].branch_version_id

    # Corrupt the active version's content_hash so it no longer matches the
    # authoritative artifact (a mismatched/interrupted publication).
    with _connect(data_dir) as conn:
        conn.execute(
            "UPDATE branch_versions SET content_hash='mismatched_hash' "
            "WHERE branch_version_id=?", (auth_id,),
        )

    results = seed_reference_designs(data_dir)
    # Detected as unhealthy and REPAIRED (a fresh active version at the
    # authoritative hash), not reported present.
    assert tag in results["seeded"], results
    assert tag not in results["present"]
    healthy = [
        v for v in list_branch_versions(data_dir, fixed_id, limit=50)
        if v.status == "active" and v.content_hash != "mismatched_hash"
    ]
    assert healthy, "a fresh active version at the authoritative hash must exist"


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


def test_publish_failure_after_overwrite_leaves_no_duplicate(data_dir, monkeypatch):
    # Codex S1 round-6 Finding 2: if _publish_reference raises AFTER
    # _overwrite_reference_content during repair, the temp authoritative build
    # must STILL be cleaned up. Otherwise correct_id stays tagged and the next
    # healthy seed reports `present` while TWO design:...@v1 rows exist.
    import tinyassets.branch_designs as bd
    from tinyassets.branch_versions import list_branch_versions
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import (
        get_branch_definition,
        list_branch_definitions,
        save_branch_definition,
    )

    seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    bdid = list_branch_definitions(data_dir, tag=tag)[0]["branch_def_id"]

    # Drift the row so the next seed takes the REPAIR path (overwrite+publish).
    branch = BranchDefinition.from_dict(
        get_branch_definition(data_dir, branch_def_id=bdid)
    )
    branch.node_defs[0].prompt_template = "CORRUPTED SAME-SIZED REFERENCE"
    save_branch_definition(data_dir, branch_def=branch.to_dict())

    # Make publish blow up AFTER the in-place overwrite step.
    def _boom(*a, **k):
        raise RuntimeError("publish exploded mid-repair")

    monkeypatch.setattr(bd, "_publish_reference", _boom)
    results = seed_reference_designs(data_dir)

    assert tag in results["failed"]                  # loud, contained
    # The temp build was cleaned up in the finally — exactly one tagged row.
    rows = list_branch_definitions(data_dir, tag=tag)
    assert len(rows) == 1, [r["branch_def_id"] for r in rows]
    assert rows[0]["branch_def_id"] == bdid

    # Un-patch: the next seed reconciles cleanly — the content was already
    # repaired in place before publish raised, so the row is healthy — and it
    # must NEVER report present-with-duplicates. Exactly one tagged row.
    monkeypatch.undo()
    healed = seed_reference_designs(data_dir)
    assert tag not in healed["failed"], healed
    rows2 = list_branch_definitions(data_dir, tag=tag)
    assert len(rows2) == 1
    assert rows2[0]["branch_def_id"] == bdid
    # The single surviving row is healthy: it carries a published version.
    assert list_branch_versions(data_dir, bdid, limit=1)


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


def test_seed_honors_explicit_base_path_over_env(tmp_path, monkeypatch):
    # Codex S1 round-5 REQUIRED: the seeder reconciles/lists/deletes against the
    # EXPLICIT base_path arg, but the composite build (_ext_branch_build)
    # resolves the GLOBAL TINYASSETS_DATA_DIR. When the two differ the build
    # split-brained — result failed, explicit registry empty, a stray row in
    # the env registry, then a KeyError on the built id. The seed must honor
    # the passed base_path end to end.
    from tinyassets.daemon_server import (
        initialize_author_server,
        list_branch_definitions,
    )

    explicit = tmp_path / "explicit"
    explicit.mkdir()
    env_dir = tmp_path / "env"
    env_dir.mkdir()
    initialize_author_server(env_dir)          # empty schema so a stray row shows
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(env_dir))

    tag = design_tag("patch_loop_reference", 1)
    results = seed_reference_designs(explicit)

    # Seeded (NOT failed) into the EXPLICIT registry, published + versioned.
    assert tag in results["seeded"], results
    assert results["failed"] == []
    explicit_rows = list_branch_definitions(explicit, tag=tag)
    assert len(explicit_rows) == 1
    assert explicit_rows[0]["published"] is True

    # The env registry got NO stray rows — the build didn't leak there.
    assert list_branch_definitions(env_dir, tag=tag) == []

    # The seed left the process's data-dir resolution untouched.
    assert os.environ["TINYASSETS_DATA_DIR"] == str(env_dir)


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


def test_seed_crash_stays_up_and_reports_unhealthy(monkeypatch, caplog):
    # Codex r13 #3 (REVERSES r12 #3): a seed crash — even leaving the REQUIRED
    # design unseeded — must NOT take down the MCP service. The startup seam
    # NEVER raises; it logs loudly + stashes the failure so get_status reports
    # unhealthy. Feature-health, not process-critical (Forever Rule / Hard Rule 4).
    from tinyassets import universe_server

    def _boom(*a, **k):
        raise RuntimeError("seed exploded")

    monkeypatch.setattr(
        "tinyassets.branch_designs.seed_reference_designs", _boom,
    )
    with caplog.at_level("ERROR"):
        results = universe_server._seed_reference_designs_best_effort()  # must NOT raise
    assert results == {"seeded": [], "present": [], "failed": ["<seed-crashed>"]}
    assert any("seeding crashed" in r.message for r in caplog.records)
    # Loud + checkable: stashed, and the packaged design shows as unhealthy.
    assert universe_server.last_seed_result() == results
    from tinyassets.branch_designs import unhealthy_packaged_designs
    assert "patch_loop_reference" in unhealthy_packaged_designs(results)


def test_seed_failure_is_loud_but_contained(data_dir, monkeypatch, caplog):
    # A broken seed (a raise on the critical build path) must be recorded +
    # logged loudly, never propagate (startup survives; the canary/logs surface
    # it). Failure on one design is contained to that design's tag.
    import tinyassets.branch_designs as bd

    def _boom(*a, **k):
        raise RuntimeError("registry exploded")

    monkeypatch.setattr(bd, "_build_reference_branch", _boom)
    with caplog.at_level("ERROR"):
        results = bd.seed_reference_designs(data_dir)
    assert results["seeded"] == []
    assert results["failed"], "failure must be recorded"
    assert any("CRASHED" in r.message for r in caplog.records)


# ── Finding 1: reserved seed identity never touches user data ──────────────


def test_reseed_never_overwrites_or_deletes_user_remix(data_dir):
    # Codex S1 latest-model Finding 1 (CRITICAL data-loss): a user forks the
    # reference (the fork INHERITS the design tag). Reconciling by tag would
    # then treat the remix as "the reference row" and overwrite/delete it. The
    # reserved-identity model (fixed id + reserved author) must leave the remix
    # UNTOUCHED — a fork records the FORKING user as author, not the reserved one.
    from tinyassets.branch_designs import _reference_branch_id
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import (
        get_branch_definition,
        list_branch_definitions,
        save_branch_definition,
    )

    seed_reference_designs(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)

    ref = BranchDefinition.from_dict(
        get_branch_definition(data_dir, branch_def_id=fixed_id)
    )
    fork = ref.fork(new_name="my remix", author="alice")
    node0 = fork.node_defs[0].node_id
    fork.node_defs[0].prompt_template = "MY CUSTOM REMIX PROMPT"
    saved_fork = save_branch_definition(data_dir, branch_def=fork.to_dict())
    fork_id = saved_fork["branch_def_id"]
    assert fork_id != fixed_id
    assert tag in saved_fork["tags"]              # fork inherited the design tag
    assert saved_fork["author"] == "alice"        # fork records the forking user

    seed_reference_designs(data_dir)              # reseed must not touch the remix

    healed_fork = get_branch_definition(data_dir, branch_def_id=fork_id)
    assert healed_fork is not None                # not deleted
    fork_node = next(
        n for n in healed_fork["node_defs"] if n["node_id"] == node0
    )
    assert fork_node["prompt_template"] == "MY CUSTOM REMIX PROMPT"  # not overwritten
    assert healed_fork["author"] == "alice"
    # The reference itself is still healthy at its own reserved id.
    ref_rows = [
        r for r in list_branch_definitions(data_dir, tag=tag)
        if r["branch_def_id"] == fixed_id
    ]
    assert len(ref_rows) == 1


def test_reseed_ignores_hostile_user_tagged_branch(data_dir):
    # A user manually tags their own branch with the reserved design tag. The
    # seeder must neither overwrite nor delete it (its author is not reserved and
    # its id is not the reserved fixed id).
    from tinyassets.branch_designs import _reference_branch_id
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )
    from tinyassets.daemon_server import (
        get_branch_definition,
        initialize_author_server,
        save_branch_definition,
    )

    initialize_author_server(data_dir)
    tag = design_tag("patch_loop_reference", 1)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)

    hostile = BranchDefinition(
        name="hostile", author="mallory", entry_point="only",
        tags=[tag, "reference-design"],
        node_defs=[NodeDefinition(
            node_id="only", display_name="Only", prompt_template="HOSTILE {x}",
        )],
        graph_nodes=[GraphNodeRef(id="only", node_def_id="only")],
        edges=[
            EdgeDefinition(from_node="START", to_node="only"),
            EdgeDefinition(from_node="only", to_node="END"),
        ],
        state_schema=[{"name": "x", "type": "str"}],
    )
    saved = save_branch_definition(data_dir, branch_def=hostile.to_dict())
    hostile_id = saved["branch_def_id"]
    assert hostile_id != fixed_id

    seed_reference_designs(data_dir)

    still = get_branch_definition(data_dir, branch_def_id=hostile_id)
    assert still is not None                             # not deleted
    assert still["author"] == "mallory"                  # not restamped
    assert still["node_defs"][0]["prompt_template"] == "HOSTILE {x}"  # not overwritten
    # The real reference was seeded at its own reserved id under reserved author.
    ref = get_branch_definition(data_dir, branch_def_id=fixed_id)
    assert ref["author"] == "reference-designs"


def test_staged_build_strips_reserved_author(data_dir):
    # Finding 1c: a user cannot smuggle the reserved seed author onto a branch
    # via build — the user-facing build path strips it.
    from tinyassets.api.branches import _staged_branch_from_spec

    branch, errors = _staged_branch_from_spec({
        "name": "smuggle", "author": "reference-designs", "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N", "prompt_template": "x {y}"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        "state_schema": [{"name": "y", "type": "str"}],
    })
    assert errors == [], errors
    assert branch.author != "reference-designs"


def test_yaml_import_strips_reserved_seed_author():
    # Codex r15 addendum B: reserved identity is unforgeable on the IMPORT path
    # too — a YAML payload claiming author="reference-designs" must be stripped,
    # else the next seed's reserved-author stray-row prune would DELETE the
    # imported branch (identity forgery + griefing deletion).
    from tinyassets.catalog.serializer import branch_from_yaml_payload

    branch = branch_from_yaml_payload({
        "name": "Imported", "author": "reference-designs",
    })
    assert branch.author != "reference-designs"
    assert branch.author == "anonymous"


# ── Codex r13 #2: reserved seed is undeletable/immutable via public mutation ──


def test_reserved_seed_undeletable_via_public_delete(data_dir):
    # Codex r13 #2: an ordinary caller reproduced deleting the authoritative
    # seed via delete_branch (no ownership check). Every public mutation path
    # must refuse; the seed SURVIVES.
    from tinyassets.api.branches import _ext_branch_delete
    from tinyassets.branch_designs import _reference_branch_id
    from tinyassets.daemon_server import get_branch_definition

    seed_reference_designs(data_dir)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)

    out = json.loads(_ext_branch_delete({"branch_def_id": fixed_id}))
    assert "error" in out
    assert "protected reference-design seed" in out["error"], out
    # Seed row untouched.
    assert get_branch_definition(
        data_dir, branch_def_id=fixed_id,
    )["author"] == "reference-designs"


def test_reserved_seed_immutable_via_patch_force(data_dir):
    # Codex r13 #2: patch_branch(force=true) bypassed ownership. The guard runs
    # before ops apply.
    from tinyassets.api.branches import _ext_branch_patch
    from tinyassets.branch_designs import _reference_branch_id

    seed_reference_designs(data_dir)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)

    out = json.loads(_ext_branch_patch({
        "branch_def_id": fixed_id,
        "changes_json": json.dumps([{"op": "set_tags", "tags": ["hijacked"]}]),
        "force": True,
    }))
    assert out.get("status") == "rejected"
    assert "protected reference-design seed" in out["error"], out


def test_reserved_seed_immutable_via_atomic_add_node(data_dir):
    # Codex r13 #2: atomic node-mutation paths were unguarded too.
    from tinyassets.api.branches import _ext_branch_add_node
    from tinyassets.branch_designs import _reference_branch_id
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition

    seed_reference_designs(data_dir)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)
    before = len(BranchDefinition.from_dict(
        get_branch_definition(data_dir, branch_def_id=fixed_id)
    ).node_defs)

    out = json.loads(_ext_branch_add_node({
        "branch_def_id": fixed_id, "node_id": "evil",
        "display_name": "Evil", "prompt_template": "x {intake_source}",
    }))
    assert "error" in out
    assert "protected reference-design seed" in out["error"], out
    after = len(BranchDefinition.from_dict(
        get_branch_definition(data_dir, branch_def_id=fixed_id)
    ).node_defs)
    assert after == before   # no node added


def test_reserved_seed_immutable_via_approve_source_code(data_dir):
    # Codex r15 #6: approve_source_code SAVES the branch, so it is a mutation
    # path and must honor the reserved-seed guard too. The seed has no
    # source_code nodes, but the guard must still refuse (fires before node
    # resolution) so the "every public mutation path" invariant holds.
    from tinyassets.api.branches import _ext_branch_approve_source_code
    from tinyassets.branch_designs import _reference_branch_id

    seed_reference_designs(data_dir)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)

    out = json.loads(_ext_branch_approve_source_code({
        "branch_def_id": fixed_id, "node_id": "draft_patch",
    }))
    assert out.get("status") == "rejected"
    assert "protected reference-design seed" in out["error"], out


# ── Finding 5: concurrent seed + loud crash ────────────────────────────────


def test_concurrent_seed_no_duplicate_no_crash(data_dir):
    # Codex S1 latest-model Finding 5: two threads seeding the same base_path
    # (multi-worker boots exist) must converge on ONE row (fixed-id upsert), not
    # mint duplicates, and never crash.
    import threading

    from tinyassets.daemon_server import initialize_author_server, list_branch_definitions

    initialize_author_server(data_dir)   # schema ready so threads don't race init
    tag = design_tag("patch_loop_reference", 1)
    errors: list[Exception] = []

    def _seed():
        try:
            seed_reference_designs(data_dir)
        except Exception as exc:  # noqa: BLE001 - record for the assertion
            errors.append(exc)

    threads = [threading.Thread(target=_seed) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    rows = list_branch_definitions(data_dir, tag=tag)
    assert len(rows) == 1, [r["branch_def_id"] for r in rows]


def test_multiprocess_concurrent_seed_converges_to_one_row(tmp_path):
    # Codex F3: multi-PROCESS (not just multi-thread) concurrent boots — the
    # real multi-worker deploy shape — must converge to ONE reference row via
    # the fixed-id INSERT OR REPLACE upsert (cross-process, not just a thread
    # lock).
    import os as _os
    import subprocess
    import sys

    from tinyassets.daemon_server import (
        initialize_author_server,
        list_branch_definitions,
    )

    data = tmp_path / "data"
    data.mkdir()
    # Pre-migrate the schema ONCE in the parent so the subprocesses race only on
    # the SEED reconcile (the F3 property), not on initialize_author_server's
    # ALTER TABLE migration — that schema-init step is a separate daemon_server
    # concern not made concurrency-safe cross-process (in-process lock only).
    initialize_author_server(data)
    repo_root = Path(__file__).resolve().parents[1]
    prog = (
        "import os, sys;"
        f"sys.path.insert(0, {str(repo_root)!r});"
        "from tinyassets.branch_designs import seed_reference_designs;"
        "seed_reference_designs(os.environ['TINYASSETS_DATA_DIR'])"
    )
    env = dict(
        _os.environ,
        TINYASSETS_DATA_DIR=str(data),
        TINYASSETS_STORAGE_BACKEND="sqlite_only",
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", prog], env=env)
        for _ in range(2)
    ]
    rcs = [p.wait(timeout=180) for p in procs]
    assert all(rc == 0 for rc in rcs), rcs

    tag = design_tag("patch_loop_reference", 1)
    rows = list_branch_definitions(data, tag=tag)
    assert len(rows) == 1, [r["branch_def_id"] for r in rows]


# ── Finding 4b: artifact validation + semantic round-trip ──────────────────


def test_load_design_artifacts_rejects_unknown_top_level_field(tmp_path, monkeypatch):
    # Finding 4b: an unknown TOP-LEVEL field (typo / unsupported forward-compat)
    # must fail loudly, not be silently accepted.
    import tinyassets.branch_designs as bd

    bad = {
        "design_format": bd.DESIGN_FORMAT, "design_id": "x", "design_version": 1,
        "spec": {"name": "x", "entry_point": "n", "node_defs": [], "edges": []},
        "design_verison": "typo",
    }
    (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(bd, "DESIGNS_DIR", tmp_path)
    with pytest.raises(ValueError, match="unknown top-level"):
        bd.load_design_artifacts()


def test_load_design_artifacts_rejects_missing_and_bad_format(tmp_path, monkeypatch):
    import tinyassets.branch_designs as bd

    # Missing envelope key.
    (tmp_path / "a.json").write_text(
        json.dumps({"design_format": bd.DESIGN_FORMAT}), encoding="utf-8",
    )
    monkeypatch.setattr(bd, "DESIGNS_DIR", tmp_path)
    with pytest.raises(ValueError, match="missing envelope keys"):
        bd.load_design_artifacts()


def test_empty_package_fails_loud_on_packaged_design(data_dir, tmp_path, monkeypatch):
    # Codex r10 #4: an EMPTY designs dir (or a package that dropped a packaged
    # artifact) must FAIL LOUD, not look healthy. The packaged-design manifest
    # makes the seed report the missing packaged id in `failed`.
    import tinyassets.branch_designs as bd

    empty = tmp_path / "empty_designs"
    empty.mkdir()
    monkeypatch.setattr(bd, "DESIGNS_DIR", empty)

    results = bd.seed_reference_designs(data_dir)
    assert results["seeded"] == []
    assert results["present"] == []
    assert "<missing-packaged-design:patch_loop_reference>" in results["failed"], results


def test_missing_packaged_design_stays_up_reports_unhealthy(data_dir, tmp_path, monkeypatch):
    # Codex r13 #3 + r15 #4: a PACKAGED design missing from the package must NOT
    # take down the server — the startup seam stays UP (no raise) and reports
    # unhealthy so a canary / get_status reader detects it. "Refuse to SHIP
    # broken" is the CI gate (test_packaged_reference_design_is_valid_and_seedable),
    # not runtime death. The reference is OPTIONAL for startup (r15 #4).
    import tinyassets.branch_designs as bd
    from tinyassets import universe_server

    empty = tmp_path / "empty_designs_startup"
    empty.mkdir()
    monkeypatch.setattr(bd, "DESIGNS_DIR", empty)
    results = universe_server._seed_reference_designs_best_effort()  # must NOT raise
    assert "<missing-packaged-design:patch_loop_reference>" in results["failed"]
    assert "patch_loop_reference" in bd.unhealthy_packaged_designs(results)


def test_packaged_reference_design_is_valid_and_seedable(data_dir):
    # Codex r13 #3: "refuse to SHIP broken" belongs in CI, not runtime. This is
    # that gate — the PACKAGED reference artifact must parse, carry the packaged
    # design, build through the real user path, and seed HEALTHY. A broken commit
    # to the packaged seed fails CI here rather than degrading a running server.
    from tinyassets.branch_designs import (
        PACKAGED_DESIGN_IDS,
        load_design_artifacts,
        unhealthy_packaged_designs,
    )

    artifacts = load_design_artifacts()          # raises on a malformed artifact
    ids = {a["design_id"] for a in artifacts}
    assert PACKAGED_DESIGN_IDS <= ids, (PACKAGED_DESIGN_IDS, ids)

    results = seed_reference_designs(data_dir)    # builds + publishes for real
    assert unhealthy_packaged_designs(results) == [], results
    for design_id in PACKAGED_DESIGN_IDS:
        assert any(
            t.startswith(f"design:{design_id}@v")
            for t in (results["seeded"] + results["present"])
        ), (design_id, results)


def test_optional_design_failure_keeps_server_ready(data_dir, tmp_path, monkeypatch):
    # Codex r12 #3: an OPTIONAL design failing to seed stays best-effort — the
    # server stays READY (no raise) as long as every REQUIRED design seeded.
    import tinyassets.branch_designs as bd
    from tinyassets import universe_server

    required = next(
        a for a in bd.load_design_artifacts()
        if a["design_id"] == "patch_loop_reference"
    )
    designs = tmp_path / "designs_mixed"
    designs.mkdir()
    (designs / "patch_loop_reference.json").write_text(
        json.dumps(required), encoding="utf-8",
    )
    # An OPTIONAL artifact whose spec fails to build (entry_point -> missing node).
    optional = {
        "design_format": bd.DESIGN_FORMAT, "design_id": "optional_broken",
        "design_version": 1,
        "spec": {
            "name": "broken", "entry_point": "ghost",
            "node_defs": [], "edges": [], "state_schema": [],
        },
    }
    (designs / "optional_broken.json").write_text(
        json.dumps(optional), encoding="utf-8",
    )
    monkeypatch.setattr(bd, "DESIGNS_DIR", designs)

    results = universe_server._seed_reference_designs_best_effort()  # must NOT raise
    healthy = set(results["seeded"]) | set(results["present"])
    assert any(t.startswith("design:patch_loop_reference@v") for t in healthy), results
    assert "design:optional_broken@v1" in results["failed"], results


def test_artifact_semantic_fields_survive_build(data_dir):
    # Finding 4b: the safety-critical artifact fields must survive the build ->
    # persist -> reload round trip: routing output keys, the sandbox flag, the
    # scalar conditional fallback, and the routing state fields.
    from tinyassets.branch_designs import _reference_branch_id
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition

    seed_reference_designs(data_dir)
    fixed_id = _reference_branch_id("patch_loop_reference", 1)
    branch = BranchDefinition.from_dict(
        get_branch_definition(data_dir, branch_def_id=fixed_id)
    )
    verify = next(n for n in branch.node_defs if n.node_id == "verify")
    assert verify.output_keys[:1] == ["verdict"]     # routing key is output_keys[0]
    draft = next(n for n in branch.node_defs if n.node_id == "draft_patch")
    assert draft.requires_sandbox is True            # sandbox flag survives
    present = next(n for n in branch.node_defs if n.node_id == "present")
    assert present.effects == ["github_pull_request"]  # effect declaration survives
    verify_ce = next(c for c in branch.conditional_edges if c.from_node == "verify")
    gate_ce = next(c for c in branch.conditional_edges if c.from_node == "owner_gate")
    assert verify_ce.fallback == "send_back"          # safe scalar fallback survives
    assert gate_ce.fallback == "reject"
    field_names = {f["name"] for f in branch.state_schema}
    # Canonical gate-convention routing state survives.
    assert {"verdict", "verdict_evidence"} <= field_names


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
