"""S2 of docs/design-notes/2026-07-15-user-patch-loop-reference-design.md:
the connector remix/import/export path (G2). Proves a signed-in user's chatbot
can, through the canonical read_graph/write_graph handles:

  DISCOVER published designs -> IMPORT an artifact -> FORK/REMIX a published
  design by id (provenance recorded) -> BIND repo-blind params as a user act ->
  EXPORT any owned branch back to the same portable artifact (round-trips).

Plus the author-gating + published-only-remix + private-export invariants.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tinyassets.branch_designs import design_tag, seed_reference_designs
from tinyassets.universe_server import read_graph, write_graph


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch) -> Path:
    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    # Deterministic acting identity for author-gating assertions.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    return base


def _actor(monkeypatch, name: str) -> None:
    monkeypatch.setenv("UNIVERSE_SERVER_USER", name)


def _reference_bid(base: Path) -> str:
    from tinyassets.daemon_server import list_branch_definitions

    rows = list_branch_definitions(base, tag=design_tag("patch_loop_reference", 1))
    assert rows, "patch_loop_reference must be seeded"
    return rows[0]["branch_def_id"]


def _load(base: Path, bid: str):
    """Rebuild a BranchDefinition (deterministic topology, unlike the raw row)."""
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition

    return BranchDefinition.from_dict(get_branch_definition(base, branch_def_id=bid))


# ── DISCOVER ────────────────────────────────────────────────────────────────


def test_discover_lists_published_designs(data_dir):
    seed_reference_designs(data_dir)
    bid = _reference_bid(data_dir)

    listed = json.loads(read_graph(target="designs"))
    ids = {b["branch_def_id"] for b in listed["branches"]}
    assert bid in ids, listed
    # Every listed design carries a published version handle (remixable).
    entry = next(b for b in listed["branches"] if b["branch_def_id"] == bid)
    assert entry["published"] is True
    assert entry.get("branch_version_id")


def test_discover_hides_unpublished_branches(data_dir):
    # A freshly-built branch has no published version -> not discoverable.
    from tinyassets.api.branches import _ext_branch_build

    out = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "private wip",
        "entry_point": "a",
        "node_defs": [{"node_id": "a", "display_name": "A",
                       "prompt_template": "do a"}],
        "edges": [{"from": "START", "to": "a"}, {"from": "a", "to": "END"}],
    })}))
    assert out["status"] == "built"
    listed = json.loads(read_graph(target="designs"))
    assert out["branch_def_id"] not in {
        b["branch_def_id"] for b in listed["branches"]
    }


# ── REMIX (fork a published design by id) ──────────────────────────────────


def test_remix_forks_published_design_with_provenance(data_dir):
    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)

    out = json.loads(write_graph(target="remix", branch_id=parent))
    assert out["status"] == "remixed", out
    child = out["branch_def_id"]
    assert child and child != parent
    assert out["parent_branch_def_id"] == parent
    assert out["fork_from"]  # inherited the parent's published version
    # A record_remix provenance edge was written.
    assert out["provenance"]["status"] == "recorded"
    assert out["provenance"]["parent_branch_def_id"] == parent
    assert out["provenance"]["child_branch_def_id"] == child

    # The forked child inherited the repo-blind unbound params.
    branch = _load(data_dir, child)
    field_names = {f["name"] for f in branch.state_schema}
    assert {"target_repo", "credential_ref", "merge_policy"} <= field_names
    # ...and it is OWNED by the remixer.
    assert branch.author == "alice"
    assert branch.fork_from  # lineage pointer recorded on the definition too

    # It reads back through the canonical single-branch handle as well.
    seen = json.loads(read_graph(target="branch", branch_id=child))
    assert seen["branch_def_id"] == child


def test_remix_refuses_unpublished_source(data_dir):
    from tinyassets.api.branches import _ext_branch_build

    out = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "not published",
        "entry_point": "a",
        "node_defs": [{"node_id": "a", "display_name": "A",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "a"}, {"from": "a", "to": "END"}],
    })}))
    bid = out["branch_def_id"]
    remix = json.loads(write_graph(target="remix", branch_id=bid))
    assert remix["status"] == "rejected"
    assert "not a published design" in remix["error"]


# ── BIND (set repo-blind params as a user act) ─────────────────────────────


def test_bind_sets_defaults_and_is_author_gated(data_dir, monkeypatch):
    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)
    child = json.loads(write_graph(target="remix", branch_id=parent))["branch_def_id"]

    bind_ops = json.dumps([
        {"op": "set_state_field_default", "name": "target_repo",
         "default_value": "github.com/alice/game"},
        {"op": "set_state_field_default", "name": "credential_ref",
         "default_value": "vault://alice/gh-pat"},
        {"op": "set_state_field_default", "name": "merge_policy",
         "default_value": "manual"},
    ])

    # A DIFFERENT user cannot bind alice's branch (author gate — BUG-081).
    _actor(monkeypatch, "bob")
    denied = json.loads(write_graph(
        target="branch", branch_id=child, changes_json=bind_ops,
    ))
    assert denied["status"] == "rejected"
    assert "denied" in denied["error"]

    # The owner binds successfully; defaults land on the state fields.
    _actor(monkeypatch, "alice")
    ok = json.loads(write_graph(
        target="branch", branch_id=child, changes_json=bind_ops,
    ))
    assert ok["status"] == "patched", ok

    bound = _load(data_dir, child)
    defaults = {
        f["name"]: f.get("default_value") for f in bound.state_schema
    }
    assert defaults["target_repo"] == "github.com/alice/game"
    assert defaults["credential_ref"] == "vault://alice/gh-pat"
    assert defaults["merge_policy"] == "manual"


def test_bind_unknown_field_is_rejected(data_dir):
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_patch

    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "bind target",
        "entry_point": "a",
        "node_defs": [{"node_id": "a", "display_name": "A",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "a"}, {"from": "a", "to": "END"}],
    })}))["branch_def_id"]
    out = json.loads(_ext_branch_patch({
        "branch_def_id": bid,
        "changes_json": json.dumps([
            {"op": "set_state_field_default", "name": "nope",
             "default_value": "x"},
        ]),
    }))
    assert out["status"] == "rejected"
    assert "not found" in json.dumps(out)


# ── EXPORT + IMPORT round-trip ─────────────────────────────────────────────


def test_export_import_round_trips_equivalent_branch(data_dir):
    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)
    child = json.loads(write_graph(target="remix", branch_id=parent))["branch_def_id"]
    write_graph(target="branch", branch_id=child, changes_json=json.dumps([
        {"op": "set_state_field_default", "name": "target_repo",
         "default_value": "github.com/alice/game"},
        {"op": "set_state_field_default", "name": "merge_policy",
         "default_value": "timer"},
    ]))

    # EXPORT the owned (bound) branch to the portable artifact.
    exported = json.loads(read_graph(target="design", branch_id=child))
    assert exported["status"] == "exported"
    artifact = exported["artifact"]
    assert artifact["design_format"] == "tinyassets.branch_design/v1"
    assert artifact["spec"]["node_defs"]

    # IMPORT the artifact back -> a NEW owned branch.
    imported = json.loads(write_graph(
        target="design", artifact_json=exported["artifact_json"],
    ))
    assert imported["status"] == "imported", imported
    new_bid = imported["branch_def_id"]
    assert new_bid != child

    # Round-trip equivalence: same topology, entry point, and BOUND defaults.
    src = _load(data_dir, child)
    dst = _load(data_dir, new_bid)

    def _topology(b):
        return (
            sorted(n.node_id for n in b.node_defs),
            b.entry_point,
            sorted((e.from_node, e.to_node) for e in b.edges),
            sorted(
                (c.from_node, tuple(sorted(c.conditions.items())))
                for c in b.conditional_edges
            ),
        )

    assert _topology(src) == _topology(dst)
    dst_defaults = {
        f["name"]: f.get("default_value") for f in dst.state_schema
    }
    assert dst_defaults["target_repo"] == "github.com/alice/game"
    assert dst_defaults["merge_policy"] == "timer"
    # Import is a fresh branch, not a fork — no inherited lineage pointer.
    assert not dst.fork_from


def test_round_trip_preserves_requires_sandbox_and_enabled(data_dir):
    # Codex S2 adapt (finding 1): export -> import must be behavior-preserving.
    # requires_sandbox is S3's security flag; a lossy round-trip that flips it
    # True -> False silently strips sandboxing. Preservation is GENERIC (full
    # node_def passthrough), so enabled=False survives too.
    from tinyassets.api.branches import _ext_branch_build

    built = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "sandboxed loop",
        "entry_point": "coder",
        "node_defs": [{
            "node_id": "coder", "display_name": "Coder",
            "prompt_template": "write code",
            "requires_sandbox": True,
            "enabled": False,
        }],
        "edges": [{"from": "START", "to": "coder"},
                  {"from": "coder", "to": "END"}],
    })}))
    assert built["status"] == "built", built
    src_node = next(
        n for n in _load(data_dir, built["branch_def_id"]).node_defs
        if n.node_id == "coder"
    )
    # build_branch itself now persists the fields (generic passthrough).
    assert src_node.requires_sandbox is True
    assert src_node.enabled is False

    exported = json.loads(
        read_graph(target="design", branch_id=built["branch_def_id"]),
    )
    imported = json.loads(
        write_graph(target="design", artifact_json=exported["artifact_json"]),
    )
    assert imported["status"] == "imported", imported

    dst_node = next(
        n for n in _load(data_dir, imported["branch_def_id"]).node_defs
        if n.node_id == "coder"
    )
    assert dst_node.requires_sandbox is True, "requires_sandbox must survive round-trip"
    assert dst_node.enabled is False, "enabled must survive round-trip"


def test_extensions_public_entrypoint_accepts_artifact_json(data_dir):
    # Codex S2 adapt (finding 2): the public `extensions` MCP wrapper must
    # expose artifact_json so extensions(action="import_design", artifact_json=…)
    # works (and the MCP schema can advertise it) rather than raising TypeError.
    from tinyassets.universe_server import extensions

    spec = {
        "name": "via extensions wrapper",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    }
    out = json.loads(
        extensions(action="import_design", artifact_json=json.dumps(spec)),
    )
    assert out["status"] == "imported", out
    assert _load(data_dir, out["branch_def_id"]).name == "via extensions wrapper"


def test_import_accepts_raw_spec(data_dir):
    # A user can hand their chatbot a bare build_branch spec (no envelope).
    spec = {
        "name": "raw imported loop",
        "entry_point": "start_node",
        "node_defs": [{"node_id": "start_node", "display_name": "Start",
                       "prompt_template": "go"}],
        "edges": [{"from": "START", "to": "start_node"},
                  {"from": "start_node", "to": "END"}],
        "state_schema": [{"name": "target_repo", "type": "str"}],
    }
    out = json.loads(write_graph(target="design", artifact_json=json.dumps(spec)))
    assert out["status"] == "imported", out
    branch = _load(data_dir, out["branch_def_id"])
    assert branch.name == "raw imported loop"
    assert branch.author == "alice"


def test_import_rejects_malformed_artifact(data_dir):
    out = json.loads(write_graph(target="design", artifact_json="not json"))
    assert out["status"] == "rejected"
    assert "not valid JSON" in out["error"]

    empty = json.loads(write_graph(target="design", artifact_json=""))
    assert empty["status"] == "rejected"
    assert "required" in empty["error"]


# ── Author-gated export of a private branch ────────────────────────────────


def test_private_branch_export_is_author_gated(data_dir, monkeypatch):
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_patch

    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "alice secret loop",
        "entry_point": "a",
        "node_defs": [{"node_id": "a", "display_name": "A",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "a"}, {"from": "a", "to": "END"}],
    })}))["branch_def_id"]
    # alice marks it private.
    _ext_branch_patch({
        "branch_def_id": bid,
        "changes_json": json.dumps([
            {"op": "set_visibility", "visibility": "private"},
        ]),
    })

    # The owner can still export it.
    mine = json.loads(read_graph(target="design", branch_id=bid))
    assert mine["status"] == "exported"

    # A non-author gets the "not found" envelope (existence not leaked).
    _actor(monkeypatch, "bob")
    theirs = json.loads(read_graph(target="design", branch_id=bid))
    assert "not found" in theirs["error"].lower()


# ── Unknown target hygiene ─────────────────────────────────────────────────


def test_unknown_targets_report_new_options(data_dir):
    r = json.loads(read_graph(target="bogus"))
    assert r["error"] == "unknown_target"
    assert "designs" in r["allowed_targets"] and "design" in r["allowed_targets"]
    w = json.loads(write_graph(target="bogus"))
    assert w["error"] == "unknown_target"
    assert "design" in w["allowed_targets"] and "remix" in w["allowed_targets"]
