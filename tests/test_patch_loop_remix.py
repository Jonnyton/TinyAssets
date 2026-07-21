"""S2 of docs/design-notes/2026-07-15-user-patch-loop-reference-design.md:
the connector remix/import/export path (G2). Proves a signed-in user's chatbot
can, through the canonical read_graph/write_graph handles:

  DISCOVER published designs -> IMPORT an artifact -> FORK/REMIX a published
  design by id (provenance recorded) -> BIND repo-blind params as a user act ->
  EXPORT any owned branch back to the same portable artifact (round-trips).

Plus the author-gating + published-only-remix + private-export invariants.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tinyassets.branch_designs import design_tag, seed_reference_designs
from tinyassets.universe_server import read_graph, write_graph

_S3_SANDBOX_PRESENT = importlib.util.find_spec("tinyassets.sandbox_policy") is not None


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
    # target_repo + merge_policy are the reference's stable binding slots; we
    # avoid asserting credential_ref (S1 is removing it from the reference per
    # its own security gate) so this stays robust across the S1->S3->S2 rebase.
    assert {"target_repo", "merge_policy"} <= field_names
    # ...and it is OWNED by the remixer, PRIVATE by default (bindings stay the
    # owner's — finding 1b), with the lineage pointer recorded.
    assert branch.author == "alice"
    assert branch.visibility == "private"
    assert out["visibility"] == "private"
    assert branch.fork_from  # lineage pointer recorded on the definition too

    # It reads back through the canonical single-branch handle as well (owner).
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


def test_binding_a_value_is_refused_phase1(data_dir, monkeypatch):
    # Codex r11 re-scope / r13: the platform NEVER stores binding VALUES, so a
    # value-binding attempt is refused — values are bound host-side by an engine
    # through write_graph target=binding. The design carries
    # only the binding SCHEMA (is_binding slot, no value).
    _actor(monkeypatch, "alice")
    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)
    child = json.loads(write_graph(target="remix", branch_id=parent))["branch_def_id"]

    out = json.loads(write_graph(
        target="branch", branch_id=child, graph_id="u-alice",
        changes_json=json.dumps([
            {"op": "set_state_field_default", "name": "target_repo",
             "default_value": "github.com/alice/game"},
        ]),
    ))
    assert out["status"] == "rejected"
    lowered = json.dumps(out).lower()
    assert "not stored on the platform" in lowered
    assert "target=binding" in lowered
    assert "encrypted broker" in lowered
    # No value landed anywhere in the shared row.
    for field in _load(data_dir, child).state_schema:
        assert not field.get("default_value")

    # A DIFFERENT user still cannot patch alice's branch (author gate — BUG-081).
    _actor(monkeypatch, "bob")
    denied = json.loads(write_graph(
        target="branch", branch_id=child, changes_json=json.dumps([
            {"op": "set_description", "description": "bob edit"},
        ]),
    ))
    assert denied["status"] == "rejected"
    assert "denied" in denied["error"]


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


def test_export_import_round_trips_topology_and_binding_schema(data_dir):
    # The design (TOPOLOGY + field SCHEMA incl. is_binding slots) round-trips
    # through export -> import. Shared artifacts carry no binding VALUES at all.
    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)
    child = json.loads(write_graph(target="remix", branch_id=parent))["branch_def_id"]

    exported = json.loads(read_graph(target="design", branch_id=child))
    assert exported["status"] == "exported"
    artifact = exported["artifact"]
    assert artifact["design_format"] == "tinyassets.branch_design/v1"
    assert artifact["spec"]["node_defs"]
    # No binding value anywhere in the artifact.
    for field in artifact["spec"]["state_schema"]:
        assert "default_value" not in field or not field.get("is_binding")

    imported = json.loads(write_graph(
        target="design", artifact_json=exported["artifact_json"],
    ))
    assert imported["status"] == "imported", imported
    new_bid = imported["branch_def_id"]
    assert new_bid != child

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
    assert {f["name"] for f in src.state_schema} == {f["name"] for f in dst.state_schema}
    # Import is a fresh branch, not a fork — no inherited lineage pointer.
    assert not dst.fork_from
    # An imported working copy defaults PRIVATE until explicit publication.
    assert dst.visibility == "private"
    assert imported.get("visibility") == "private"


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


# ── Versioned envelope format gate (Codex S2 adapt round 4) ─────────────────


def test_import_rejects_unsupported_envelope_format(data_dir):
    # A future/foreign versioned envelope must be REJECTED loudly (naming the
    # received AND supported format), never slide into the raw-spec path.
    from tinyassets.branch_designs import DESIGN_FORMAT
    from tinyassets.daemon_server import list_branch_definitions

    bad = {
        "design_format": "tinyassets.branch_design/v999",
        "design_id": "future",
        "design_version": 999,
        "spec": {
            "name": "future envelope",
            "entry_point": "n",
            "node_defs": [{"node_id": "n", "display_name": "N",
                           "prompt_template": "x"}],
            "edges": [{"from": "START", "to": "n"},
                      {"from": "n", "to": "END"}],
        },
    }
    out = json.loads(write_graph(target="design", artifact_json=json.dumps(bad)))
    assert out["status"] == "rejected", out
    assert "tinyassets.branch_design/v999" in out["error"]  # received named
    assert DESIGN_FORMAT in out["error"]                    # supported named
    # Nothing persisted for the rejected future envelope.
    assert "future envelope" not in {
        b.get("name") for b in list_branch_definitions(data_dir)
    }


def test_import_accepts_supported_envelope_format(data_dir):
    from tinyassets.design_artifacts import wrap_spec_as_design_artifact

    artifact = wrap_spec_as_design_artifact(
        {
            "name": "supported envelope",
            "entry_point": "n",
            "node_defs": [{"node_id": "n", "display_name": "N",
                           "prompt_template": "x"}],
            "edges": [{"from": "START", "to": "n"},
                      {"from": "n", "to": "END"}],
        },
        design_id="supported",
        design_version=1,
    )
    out = json.loads(
        write_graph(target="design", artifact_json=json.dumps(artifact)),
    )
    assert out["status"] == "imported", out
    assert _load(data_dir, out["branch_def_id"]).name == "supported envelope"


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


# ── Hostile-typed imports are rejected loudly (Codex S2 adapt round 2, F1) ──


@pytest.mark.parametrize("bad_field,bad_value", [
    ("requires_sandbox", "false"),   # string, not a JSON bool (the repro)
    ("enabled", "no"),               # string, not a JSON bool
    ("retry_policy", "oops"),        # string, not a JSON object
    ("dependencies", "oops"),        # string, not a JSON array
    ("checkpoints", "oops"),         # string, not a JSON array
])
def test_hostile_typed_import_rejected_and_persists_nothing(
    data_dir, bad_field, bad_value,
):
    from tinyassets.daemon_server import list_branch_definitions

    spec = {
        "name": f"hostile {bad_field}",
        "entry_point": "n",
        "node_defs": [{
            "node_id": "n", "display_name": "N", "prompt_template": "x",
            bad_field: bad_value,
        }],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    }
    out = json.loads(write_graph(target="design", artifact_json=json.dumps(spec)))
    # Loud rejection that names the mis-typed field (hard rule 8).
    assert out["status"] == "rejected", out
    assert bad_field in json.dumps(out)
    # And NOTHING persisted — no partial branch row for the rejected import.
    assert f"hostile {bad_field}" not in {
        b.get("name") for b in list_branch_definitions(data_dir)
    }


def test_string_bool_does_not_masquerade_as_sandboxed(data_dir):
    # Direct guard for the exact regression: requires_sandbox="false" (a truthy
    # non-empty string) must NOT slip in and list as has_sandbox_nodes=true.
    from tinyassets.daemon_server import list_branch_definitions

    spec = {
        "name": "sneaky string bool",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x", "requires_sandbox": "false"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    }
    out = json.loads(write_graph(target="design", artifact_json=json.dumps(spec)))
    assert out["status"] == "rejected"
    assert "sneaky string bool" not in {
        b.get("name") for b in list_branch_definitions(data_dir)
    }


# ── Composite scope must not downgrade (Codex S2 adapt round 2, F2) ─────────


def test_remix_design_requires_costly_scope():
    from tinyassets.auth.provider import action_scope_for

    # remix_design internally calls record_remix (costly) -> must be costly.
    assert action_scope_for("extensions", "remix_design").effect == "costly"
    assert action_scope_for("extensions", "record_remix").effect == "costly"
    # Audited siblings: import_design composes build_branch (write) -> write;
    # export_design is read-only.
    assert action_scope_for("extensions", "import_design").effect == "write"
    assert action_scope_for("extensions", "export_design").effect == "read"


# ── Discovery visibility is per-viewer (Codex S2 adapt round 3, F2) ─────────


def test_designs_listing_is_per_viewer(data_dir, monkeypatch):
    # Contract check: you see PUBLIC published designs plus your OWN published
    # designs even when private; other users' private designs are never listed.
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_patch

    _actor(monkeypatch, "alice")
    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "alice private design",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    })}))["branch_def_id"]
    # Mark private (patch_branch also publishes a version -> it's a "design").
    _ext_branch_patch({
        "branch_def_id": bid,
        "changes_json": json.dumps([
            {"op": "set_visibility", "visibility": "private"},
        ]),
    })

    # Alice sees her OWN private (published) design.
    alice_ids = {
        b["branch_def_id"] for b in json.loads(read_graph(target="designs"))["branches"]
    }
    assert bid in alice_ids

    # Bob must NOT see Alice's private design (no cross-user private leak).
    _actor(monkeypatch, "bob")
    bob_ids = {
        b["branch_def_id"] for b in json.loads(read_graph(target="designs"))["branches"]
    }
    assert bid not in bob_ids


def test_published_designs_filter_by_author(data_dir, monkeypatch):
    # Codex r14 #4: read_graph(target=designs, author=X) must filter published
    # designs to author X INSIDE the SQL (before pagination), not silently
    # ignore the param. Two authors each publish a PUBLIC design; filtering by
    # one returns only theirs, and it composes with (never widens) visibility.
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_list, _ext_branch_patch

    def _publish_public(author: str, name: str) -> str:
        _actor(monkeypatch, author)
        bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
            "name": name,
            "author": author,
            "entry_point": "n",
            "node_defs": [{"node_id": "n", "display_name": "N",
                           "prompt_template": "x"}],
            "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        })}))["branch_def_id"]
        _ext_branch_patch({  # patch publishes a version -> discoverable design
            "branch_def_id": bid,
            "changes_json": json.dumps([
                {"op": "set_description", "description": "publish"},
            ]),
        })
        return bid

    alice_bid = _publish_public("alice", "alice pub")
    bob_bid = _publish_public("bob", "bob pub")

    # Filtering the published listing by author=alice returns ONLY alice's design
    # (the param was previously a silent no-op — both would have listed).
    listed = json.loads(_ext_branch_list({
        "scope": "published", "author": "alice", "limit": 1,
    }))
    ids = {b["branch_def_id"] for b in listed["branches"]}
    assert alice_bid in ids, listed
    assert bob_bid not in ids, listed
    # Sanity: unfiltered, both public designs list.
    both = {
        b["branch_def_id"]
        for b in json.loads(_ext_branch_list({"scope": "published"}))["branches"]
    }
    assert {alice_bid, bob_bid} <= both


# ── Remix guidance is honest about the sandbox gate (F1(i)) ─────────────────


def test_remix_guidance_warns_when_design_needs_sandbox(data_dir):
    # A design containing a sandbox-required (coding) node must NOT be sold as
    # "bind and run" — the guidance must say the coding node runs only on an
    # attested-sandbox host. Derived from node DATA, so it holds pre/post S3.
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_patch

    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "coding loop",
        "entry_point": "coder",
        "node_defs": [{"node_id": "coder", "display_name": "Coder",
                       "prompt_template": "write code", "requires_sandbox": True}],
        "edges": [{"from": "START", "to": "coder"},
                  {"from": "coder", "to": "END"}],
    })}))["branch_def_id"]
    _ext_branch_patch({  # publish a version so it is remixable
        "branch_def_id": bid,
        "changes_json": json.dumps([
            {"op": "set_description", "description": "publish"},
        ]),
    })

    out = json.loads(write_graph(target="remix", branch_id=bid))
    assert out["status"] == "remixed", out
    assert out.get("requires_attested_sandbox") is True
    low = out["text"].lower()
    assert "attested" in low and "sandbox" in low
    # Must NOT promise a plain bind-and-run.
    assert "then run it" not in low


def test_remix_guidance_plain_when_no_sandbox(data_dir):
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_patch

    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "prompt only loop",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    })}))["branch_def_id"]
    _ext_branch_patch({
        "branch_def_id": bid,
        "changes_json": json.dumps([
            {"op": "set_description", "description": "publish"},
        ]),
    })

    out = json.loads(write_graph(target="remix", branch_id=bid))
    assert out["status"] == "remixed"
    assert out.get("requires_attested_sandbox") is False
    # Binding-free + sandbox-free -> runnable now; no false bind instruction.
    assert "run it now" in out["text"].lower()
    assert "set_state_field_default" not in out["text"]


@pytest.mark.skipif(
    not _S3_SANDBOX_PRESENT,
    reason=(
        "S3 runtime sandbox enforcement (tinyassets.sandbox_policy) is not on "
        "this branch; this integration regression auto-activates after the "
        "S1->S3->S2 merge and locks the fail-closed invariant on main."
    ),
)
def test_remixed_reference_coding_node_fails_closed_integration(data_dir, monkeypatch):
    # Rebase-time integration lock (Codex S2 adapt round 3, F1(ii)): after the
    # S1->S3->S2 merge the seeded reference's coding node carries
    # requires_sandbox/node_kind=coding (S1) and the runtime gate (S3) must
    # FAIL it closed without TINYASSETS_OS_SANDBOX_ATTESTED. Remix -> run -> the
    # coding node must refuse, never complete an unattested coding step.
    from tinyassets.universe_server import run_graph as _run_graph

    monkeypatch.delenv("TINYASSETS_OS_SANDBOX_ATTESTED", raising=False)
    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)
    child = json.loads(write_graph(target="remix", branch_id=parent))["branch_def_id"]
    write_graph(target="branch", branch_id=child, changes_json=json.dumps([
        {"op": "remove_state_field", "name": "target_repo"},
        {"op": "remove_state_field", "name": "merge_policy"},
        {"op": "add_state_field", "name": "target_repo", "type": "str",
         "default": "github.com/example/repo"},
        {"op": "add_state_field", "name": "merge_policy", "type": "str",
         "default": "manual"},
    ]))

    result = json.loads(_run_graph(
        branch_def_id=child,
        inputs_json=json.dumps({"request_payload": "fix a bug"}),
    ))
    assert result.get("sandbox_blocked") is True, result
    assert "run_id" not in result, result
    assert "sandbox" in result.get("error", "").lower(), result


# ── Binding privacy: values never travel / leak (Codex latest-model F1) ─────


def test_binding_schema_travels_but_no_value_exists(data_dir, monkeypatch):
    # The is_binding SCHEMA (slot) travels through
    # export/import/fork, but NO value is ever stored platform-side. A bind
    # VALUE attempt is refused, and no value appears in any shared artifact.
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_patch

    _actor(monkeypatch, "alice")
    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "bound design",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "go"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        # An is_binding SLOT declared at design time — even with a value, Phase 1
        # stores no value; only the schema flag survives.
        "state_schema": [{"name": "target_repo", "type": "str",
                          "is_binding": True,
                          "default_value": "github.com/alice/SECRET"}],
    })}))["branch_def_id"]
    _ext_branch_patch({
        "branch_def_id": bid,
        "changes_json": json.dumps([
            {"op": "set_description", "description": "publish"},
        ]),
    })

    # No value in the shared row / export / published version.
    from tinyassets.branch_versions import list_branch_versions
    from tinyassets.daemon_server import get_branch_definition

    row_tr = next(f for f in _load(data_dir, bid).state_schema if f["name"] == "target_repo")
    assert row_tr.get("is_binding") and not row_tr.get("default_value")
    assert "SECRET" not in json.dumps(get_branch_definition(data_dir, branch_def_id=bid))
    exp = json.loads(read_graph(target="design", branch_id=bid))
    art_tr = {f["name"]: f for f in exp["artifact"]["spec"]["state_schema"]}["target_repo"]
    assert art_tr.get("is_binding")            # the SLOT travels
    assert "default_value" not in art_tr       # never a value
    assert "SECRET" not in json.dumps(exp)
    for v in list_branch_versions(data_dir, bid, limit=50):
        assert "SECRET" not in json.dumps(v.snapshot)

    # A remix inherits the SLOT (schema) to re-bind on a Phase-2 engine.
    _actor(monkeypatch, "bob")
    child = json.loads(write_graph(target="remix", branch_id=bid))["branch_def_id"]
    ctr = next(f for f in _load(data_dir, child).state_schema if f["name"] == "target_repo")
    assert ctr.get("is_binding") and not ctr.get("default_value")

    # A run-time bind VALUE attempt is refused.
    _actor(monkeypatch, "bob")
    refused = json.loads(write_graph(
        target="branch", branch_id=child, graph_id="u-bob",
        changes_json=json.dumps([
            {"op": "set_state_field_default", "name": "target_repo",
             "default_value": "github.com/bob/x"},
        ]),
    ))
    assert refused["status"] == "rejected"


def test_policy_budget_survive_publish_remix_rollback_export(data_dir):
    from tinyassets.api.branches import _ext_branch_build
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition
    from tinyassets.rollback import execute_rollback_set

    policy = {"preferred": {"provider": "codex", "model": "gpt-5"}}
    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "routed loop 2",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        "default_llm_policy": policy,
        "concurrency_budget": 3,
    })}))["branch_def_id"]
    v1 = publish_branch_version(
        data_dir, get_branch_definition(data_dir, branch_def_id=bid),
        publisher="alice",
    ).branch_version_id

    # publish -> remix preserves both (they now live in the snapshot).
    child = _load(data_dir, json.loads(
        write_graph(target="remix", branch_id=bid))["branch_def_id"])
    assert child.default_llm_policy == policy
    assert child.concurrency_budget == 3

    # active-version export preserves both.
    exp = json.loads(read_graph(target="design", branch_id=bid))
    assert exp["artifact"]["spec"]["default_llm_policy"] == policy
    assert exp["artifact"]["spec"]["concurrency_budget"] == 3

    # after rolling back a newer version, remix from the newest ACTIVE (v1)
    # still preserves both.
    b = BranchDefinition.from_dict(get_branch_definition(data_dir, branch_def_id=bid))
    b.state_schema.append({"name": "extra", "type": "str"})
    save_branch_definition(data_dir, branch_def=b.to_dict())
    v2 = publish_branch_version(
        data_dir, get_branch_definition(data_dir, branch_def_id=bid),
        publisher="alice",
    ).branch_version_id
    execute_rollback_set(data_dir, [v2], reason="bad", set_by="host")
    child2 = json.loads(write_graph(target="remix", branch_id=bid))
    assert child2["fork_from"] == v1
    cf2 = _load(data_dir, child2["branch_def_id"])
    assert cf2.default_llm_policy == policy
    assert cf2.concurrency_budget == 3


def _build_binding_design(data_dir, *, bid: str, author_field: str = "target_repo"):
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition
    from tinyassets.runs import initialize_runs_db

    initialize_author_server(data_dir)
    initialize_runs_db(data_dir)
    b = BranchDefinition(
        branch_def_id=bid, name=bid, author="alice",
        graph_nodes=[GraphNodeRef(id="n", node_def_id="n")],
        edges=[EdgeDefinition(from_node="n", to_node="END")],
        entry_point="n",
        node_defs=[NodeDefinition(node_id="n", display_name="N",
                                  prompt_template="go", strict_input_isolation=False)],
        state_schema=[{"name": author_field, "type": "str", "is_binding": True}],
    )
    save_branch_definition(data_dir, branch_def=b.to_dict())
    return b


def test_unbound_design_is_inert_top_level(data_dir):
    # Codex r12 #4: a design that declares binding slots is INERT in Phase 1 (no
    # binding plane) — the SHARED core refuses it, so injecting a value via
    # inputs can't run it either. Even the author's own run is refused.
    from tinyassets.runs import execute_branch

    b = _build_binding_design(data_dir, bid="bd-top")
    out = execute_branch(
        data_dir, branch=b, inputs={"target_repo": "github.com/attacker/x"},
        actor="alice", provider_call=lambda *a, **k: "ok",
    )
    assert out.status == "failed"
    assert "inert" in (out.error or "").lower()
    assert "github.com/attacker/x" not in (out.error or "")


def test_binding_field_not_settable_via_child_mapping(data_dir):
    # Item 2 (sub-branch): a parent that maps a value into a child's binding
    # field via inputs_mapping is rejected at the child's seed.
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )
    from tinyassets.daemon_server import save_branch_definition
    from tinyassets.runs import execute_branch

    _build_binding_design(data_dir, bid="bd-child")
    parent = BranchDefinition(
        branch_def_id="bd-parent", name="p", author="bob",
        graph_nodes=[GraphNodeRef(id="pn", node_def_id="pn")],
        edges=[EdgeDefinition(from_node="pn", to_node="END")],
        entry_point="pn",
        node_defs=[NodeDefinition(
            node_id="pn", display_name="I",
            invoke_branch_spec={
                "branch_def_id": "bd-child",
                # Map an attacker-controlled parent field into the child binding.
                "inputs_mapping": {"payload": "target_repo"},
                "output_mapping": {"seen": "target_repo"},
                "wait_mode": "blocking",
                "on_child_fail": "propagate",
            },
        )],
        state_schema=[{"name": "payload", "type": "str"},
                      {"name": "seen", "type": "str"}],
    )
    save_branch_definition(data_dir, branch_def=parent.to_dict())

    out = execute_branch(
        data_dir, branch=parent, inputs={"payload": "github.com/attacker/x"},
        actor="bob", provider_call=lambda *a, **k: "ok",
    )
    # The child run refused the injected binding value -> parent does not
    # complete with the attacker value.
    assert "github.com/attacker/x" not in json.dumps(out.output or {})


def test_directory_export_of_private_design_is_public_only(data_dir, monkeypatch):
    # F2: the unauthenticated directory host must use PUBLIC-ONLY viewer — never
    # UNIVERSE_SERVER_USER. A private design authored by that env id is still
    # not-found; public designs still list.
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_patch
    from tinyassets.directory_server import read_graph as dir_read

    _actor(monkeypatch, "author-x")  # the directory host's env identity
    priv = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "author-x private",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "secret prompt body"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    })}))["branch_def_id"]
    _ext_branch_patch({
        "branch_def_id": priv,
        "changes_json": json.dumps([
            {"op": "set_visibility", "visibility": "private"},
        ]),
    })

    # Even though UNIVERSE_SERVER_USER == the author, the directory is not-found.
    exp = json.loads(dir_read(target="design", branch_id=priv))
    assert "not found" in exp["error"].lower()
    assert "secret prompt body" not in json.dumps(exp)
    assert priv not in {
        b["branch_def_id"] for b in json.loads(dir_read(target="designs"))["branches"]
    }

    # A public design IS discoverable via the directory host.
    pub = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "public design",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    })}))["branch_def_id"]
    _ext_branch_patch({
        "branch_def_id": pub,
        "changes_json": json.dumps([
            {"op": "set_description", "description": "publish"},
        ]),
    })
    assert pub in {
        b["branch_def_id"] for b in json.loads(dir_read(target="designs"))["branches"]
    }


def test_directory_surface_designs_is_read_only(data_dir):
    # F3 decision: the directory host is the public DISCOVERY surface — discover
    # + export (READ) parity only. Remix/import (WRITE) is NOT offered here
    # (authenticated remix/bind lives on the OAuth-gated /mcp universe surface).
    from tinyassets.directory_server import read_graph as dir_read
    from tinyassets.directory_server import write_graph as dir_write

    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)

    # READ parity: discover + export work on the directory surface.
    listed = json.loads(dir_read(target="designs"))
    assert parent in {b["branch_def_id"] for b in listed["branches"]}
    exported = json.loads(dir_read(target="design", branch_id=parent))
    assert exported["status"] == "exported"
    r = json.loads(dir_read(target="bogus"))
    assert {"designs", "design"} <= set(r["allowed_targets"])

    # WRITE is deliberately absent: design/remix are unknown targets here.
    w = json.loads(dir_write(target="bogus"))
    assert set(w["allowed_targets"]) == {"goal", "request"}
    assert json.loads(dir_write(target="remix", branch_id=parent))["error"] == "unknown_target"


def test_unbound_design_run_refused_for_everyone(data_dir, monkeypatch):
    # Codex r12 #4: a design with binding slots is UNBOUND and INERT in Phase 1
    # (no universe binding selected). The author gets the actionable inert
    # failure; a non-author gets indistinguishable not-found so the binding
    # schema cannot become a branch-existence oracle.
    from tinyassets.api.branches import _ext_branch_build
    from tinyassets.api.runs import _action_run_branch

    _actor(monkeypatch, "alice")
    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "bound run design",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "go"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        "state_schema": [{"name": "target_repo", "type": "str", "is_binding": True}],
    })}))["branch_def_id"]

    _actor(monkeypatch, "bob")
    hidden = json.loads(_action_run_branch({
        "branch_def_id": bid, "inputs_json": json.dumps({}),
    }))
    assert "not found" in hidden["error"].lower(), hidden

    _actor(monkeypatch, "alice")
    refused = json.loads(_action_run_branch({
        "branch_def_id": bid, "inputs_json": json.dumps({}),
    }))
    assert refused.get("failure_class") == "binding_unbound_phase1", refused
    assert "inert" in refused["error"].lower()


def test_canonical_binding_plane_is_private_author_scoped_and_runnable(
    data_dir, monkeypatch, request, caplog,
):
    """r14 #2: bind repo/policy through write_graph without branch/run leakage."""
    from tinyassets.api.branches import _ext_branch_build
    from tinyassets.api.runs import _action_run_branch
    from tinyassets.auth.middleware import auth_middleware, set_provider
    from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity
    from tinyassets.daemon_server import grant_universe_access
    from tinyassets.runs import get_run, list_events, wait_for

    class _ActorProvider(AuthProvider):
        def resolve_token(self, token):
            return Identity(
                user_id=token,
                username=token,
                capabilities=["read", "write", "costly", "admin"],
            )

        def is_auth_required(self):
            return False

        def resolve_always_writes(self):
            return True

        def register_client(self, metadata):
            return {"client_id": "test", **metadata}

        def create_authorization(self, *_args, **_kwargs):
            return "code"

        def exchange_code(self, *_args, **_kwargs):
            return None

    def _reset_auth():
        set_provider(DevAuthProvider())
        auth_middleware(None)

    request.addfinalizer(_reset_auth)
    set_provider(_ActorProvider())
    auth_middleware("alice")

    universe = data_dir / "u-bind"
    universe.mkdir(parents=True)
    for actor_id in ("alice", "mallory"):
        grant_universe_access(
            data_dir,
            universe_id="u-bind",
            actor_id=actor_id,
            permission="write",
            granted_by="test",
        )
    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "privately bound design",
        "entry_point": "n",
        "node_defs": [{
            "node_id": "n",
            "display_name": "N",
            "prompt_template": "patch {target_repo} under {merge_policy}",
        }],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        "state_schema": [
            {"name": "target_repo", "type": "str", "is_binding": True},
            {"name": "merge_policy", "type": "str", "is_binding": True},
        ],
    })})) ["branch_def_id"]

    bound = json.loads(write_graph(
        target="binding",
        graph_id="u-bind",
        branch_id=bid,
        changes_json=json.dumps({
            "target_repo": "octo/private-repo",
            "merge_policy": "manual",
        }),
    ))
    assert bound.get("status") == "bound", bound
    assert bound["bound_fields"] == ["merge_policy", "target_repo"]
    assert "octo/private-repo" not in json.dumps(bound)

    exported = json.loads(read_graph(target="design", branch_id=bid))
    assert "octo/private-repo" not in json.dumps(exported)

    _actor(monkeypatch, "mallory")
    auth_middleware("mallory")
    denied = json.loads(write_graph(
        target="binding",
        graph_id="u-bind",
        branch_id=bid,
        changes_json=json.dumps({"target_repo": "mallory/repo"}),
    ))
    assert denied.get("status") == "rejected", denied
    denied_run = json.loads(_action_run_branch({
        "branch_def_id": bid,
        "universe_id": "u-bind",
        "inputs_json": "{}",
    }))
    assert denied_run == {"error": f"Branch '{bid}' not found."}

    _actor(monkeypatch, "alice")
    auth_middleware("alice")
    monkeypatch.setattr(
        "tinyassets.providers.call.call_provider",
        lambda *_args, **_kwargs: "provider-ok",
    )
    started = json.loads(_action_run_branch({
        "branch_def_id": bid,
        "universe_id": "u-bind",
        "inputs_json": "{}",
    }))
    assert started.get("failure_class") != "binding_unbound_phase1", started
    wait_for(started["run_id"], timeout=10)
    persisted = get_run(data_dir, started["run_id"])
    assert persisted is not None
    assert "octo/private-repo" not in json.dumps(persisted)
    events = list_events(data_dir, started["run_id"])
    assert "octo/private-repo" not in json.dumps(events)
    assert "manual" not in json.dumps(events)
    assert "[private binding]" in json.dumps(events)
    checkpoint_db = data_dir / ".langgraph_runs.db"
    assert not checkpoint_db.exists() or b"octo/private-repo" not in checkpoint_db.read_bytes()

    def _echo_private_prompt_failure(prompt, *_args, **_kwargs):
        raise RuntimeError(f"provider rejected prompt={prompt}")

    caplog.clear()
    monkeypatch.setattr(
        "tinyassets.providers.call.call_provider",
        _echo_private_prompt_failure,
    )
    failed_start = json.loads(_action_run_branch({
        "branch_def_id": bid,
        "universe_id": "u-bind",
        "inputs_json": "{}",
    }))
    wait_for(failed_start["run_id"], timeout=10)
    failed = get_run(data_dir, failed_start["run_id"])
    assert failed is not None and failed["status"] == "failed"
    assert "octo/private-repo" not in json.dumps(failed)
    assert "octo/private-repo" not in json.dumps(
        list_events(data_dir, failed_start["run_id"]),
    )
    assert "octo/private-repo" not in caplog.text


def test_binding_store_rejects_credential_shapes_and_token_bearing_repos(tmp_path):
    from tinyassets.branch_bindings import BranchBindingError, bind_branch_values

    universe = tmp_path / "u"
    universe.mkdir()
    with pytest.raises(BranchBindingError, match="unsupported binding fields"):
        bind_branch_values(
            universe,
            "b",
            [{"name": "pat", "type": "str", "is_binding": True}],
            {"pat": "ghp_private"},
            actor="alice",
        )
    for value in (
        "https://token@github.com/octo/private-repo",
        "octo/private-repo?token=secret",
        {"repo": "octo/private-repo", "token": "secret"},
    ):
        with pytest.raises(BranchBindingError, match="plain owner/repo"):
            bind_branch_values(
                universe,
                "b",
                [{"name": "target_repo", "type": "str", "is_binding": True}],
                {"target_repo": value},
                actor="alice",
            )


def test_concurrent_private_binding_load_has_no_loss_or_lock(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from tinyassets.branch_bindings import bind_branch_values, load_branch_values

    universe = tmp_path / "u"
    universe.mkdir()
    schema = [
        {"name": "target_repo", "type": "str", "is_binding": True},
        {"name": "merge_policy", "type": "str", "is_binding": True},
    ]

    def _bind(index: int) -> tuple[str, dict]:
        branch_id = f"b-{index}"
        bind_branch_values(
            universe,
            branch_id,
            schema,
            {"target_repo": f"octo/repo-{index}", "merge_policy": "manual"},
            actor="alice",
        )
        return branch_id, load_branch_values(universe, branch_id, schema)

    with ThreadPoolExecutor(max_workers=12) as pool:
        rows = list(pool.map(_bind, range(48)))

    assert len(rows) == 48
    for branch_id, values in rows:
        index = branch_id.removeprefix("b-")
        assert values == {
            "target_repo": f"octo/repo-{index}",
            "merge_policy": "manual",
        }


def test_concurrent_remix_load_converges_without_loss(data_dir, monkeypatch):
    """S2 §14 proof: concurrent public remix requests stay unique and complete."""
    from concurrent.futures import ThreadPoolExecutor

    from tinyassets.api.branches import _ext_branch_remix_design

    _actor(monkeypatch, "alice")
    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)

    def _remix(index: int) -> dict:
        return json.loads(_ext_branch_remix_design({
            "branch_def_id": parent,
            "name": f"load-remix-{index}",
        }))

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(_remix, range(32)))

    assert all(result.get("status") == "remixed" for result in results), results
    child_ids = [result["branch_def_id"] for result in results]
    assert len(set(child_ids)) == 32
    assert all(result.get("parent_branch_def_id") == parent for result in results)
    assert all(
        (result.get("provenance") or {}).get("status") == "recorded"
        for result in results
    )


def test_seeded_reference_binding_slots_are_inert(data_dir, monkeypatch):
    # Codex r13: the inert guard was only exercised against SYNTHETIC is_binding
    # branches; the REAL seeded reference must be pinned too, so the guard is
    # proven against what ships — not only a stand-in. S1 (head 8c34d27a) marks
    # target_repo + merge_policy `is_binding` and the marker round-trips through
    # the seed path (_apply_state_field_spec preserves it), so this now asserts
    # the shipped artifact is detected as binding-bearing AND refused at the run
    # guard. Keyed on the is_binding marker (via branch_has_bound_fields), NOT a
    # literal credential_ref name — S1 deliberately carries NO credential handle
    # in state (credentials resolve BY DESTINATION in the vault, never a handle
    # in a shared artifact; r10 F4a, host-confirmed).
    from tinyassets.api.runs import _action_run_branch
    from tinyassets.branch_versions import branch_has_bound_fields

    seed_reference_designs(data_dir)
    bid = _reference_bid(data_dir)
    ref = _load(data_dir, bid)

    # The reference is a REPO-BLIND design: it declares binding slots (target_repo
    # / merge_policy), or it would run unbound against an arbitrary repo.
    assert branch_has_bound_fields(ref.state_schema), (
        "seeded reference declares no is_binding slots — a repo-blind design "
        "would run unbound; S1 must mark target_repo / merge_policy is_binding"
    )
    bound = {f["name"] for f in ref.state_schema if f.get("is_binding")}
    assert {"target_repo", "merge_policy"} <= bound, bound

    # Public reference designs are templates to remix, not directly executable
    # by arbitrary users. Binding-bearing execution stays author-scoped.
    _actor(monkeypatch, "alice")
    hidden = json.loads(_action_run_branch({
        "branch_def_id": bid, "inputs_json": json.dumps({}),
    }))
    assert "not found" in hidden["error"].lower(), hidden


def test_designs_listing_paginates_at_db(data_dir):
    # Codex r11 #6: read_graph(target=designs) paginates at the DB boundary —
    # honors limit + exposes a next_offset cursor.
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_patch

    for i in range(3):
        bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
            "name": f"design {i}",
            "entry_point": "n",
            "node_defs": [{"node_id": "n", "display_name": "N",
                           "prompt_template": "x"}],
            "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        })}))["branch_def_id"]
        _ext_branch_patch({
            "branch_def_id": bid,
            "changes_json": json.dumps([
                {"op": "set_description", "description": "publish"},
            ]),
        })

    listed = json.loads(read_graph(target="designs", limit=1))
    assert len(listed["branches"]) <= 1
    # A full DB page implies more rows may follow -> a cursor is exposed.
    assert listed["truncated"] is True
    assert listed["next_offset"] == 1


def test_active_version_scan_finds_active_beyond_rolled_back(data_dir):
    # Codex S2 F3: the newest-active lookup must query by status directly, not
    # scan only the newest N — an old active version behind newer rolled-back
    # ones must still be found.
    from tinyassets.api.branches import _ext_branch_build
    from tinyassets.branch_versions import (
        get_newest_active_version,
        publish_branch_version,
    )
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition
    from tinyassets.rollback import execute_rollback_set

    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "many versions",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    })}))["branch_def_id"]
    v1 = publish_branch_version(
        data_dir, get_branch_definition(data_dir, branch_def_id=bid),
        publisher="alice",
    ).branch_version_id

    # Publish several NEWER versions and roll them all back.
    newer_ids = []
    for i in range(4):
        b = BranchDefinition.from_dict(get_branch_definition(data_dir, branch_def_id=bid))
        b.state_schema.append({"name": f"f{i}", "type": "str"})
        save_branch_definition(data_dir, branch_def=b.to_dict())
        newer_ids.append(publish_branch_version(
            data_dir, get_branch_definition(data_dir, branch_def_id=bid),
            publisher="alice",
        ).branch_version_id)
    execute_rollback_set(data_dir, newer_ids, reason="regress", set_by="host")

    # The only ACTIVE version is the oldest (v1) — direct-SQL lookup finds it.
    active = get_newest_active_version(data_dir, bid)
    assert active is not None
    assert active.branch_version_id == v1


def test_binding_free_public_branch_runs_for_any_actor(data_dir, monkeypatch):
    # A binding-FREE public branch is a pure TEMPLATE — anyone may run it.
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_patch
    from tinyassets.api.runs import _action_run_branch

    _actor(monkeypatch, "carol")
    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "free template",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "do {x}"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        "state_schema": [{"name": "x", "type": "str"}],
    })}))["branch_def_id"]
    _ext_branch_patch({
        "branch_def_id": bid,
        "changes_json": json.dumps([
            {"op": "set_visibility", "visibility": "public"},
        ]),
    })

    _actor(monkeypatch, "dave")
    ran = json.loads(_action_run_branch({
        "branch_def_id": bid,
        "inputs_json": json.dumps({"x": "1"}),
    }))
    # Not refused by the binding guard (no binding slots).
    assert ran.get("failure_class") != "binding_unbound_phase1", ran


def test_import_and_remix_never_write_a_public_row(data_dir, monkeypatch):
    # Codex r12 #1: private-by-default is ATOMIC — no save ever persists a
    # PUBLIC row for an import/remix, so a crash between saves cannot leave a
    # permanently public working copy.
    import tinyassets.daemon_server as ds

    real_save = ds.save_branch_definition
    seen = []

    def _spy(base_path, *, branch_def, **save_kwargs):
        seen.append((branch_def.get("name"), branch_def.get("visibility")))
        return real_save(base_path, branch_def=branch_def, **save_kwargs)

    monkeypatch.setattr(ds, "save_branch_definition", _spy)

    # Import.
    imp = json.loads(write_graph(target="design", artifact_json=json.dumps({
        "name": "atomic import",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N", "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    })))
    assert imp["status"] == "imported"
    assert _load(data_dir, imp["branch_def_id"]).visibility == "private"

    # Remix.
    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)
    rem = json.loads(write_graph(target="remix", branch_id=parent))
    assert rem["status"] == "remixed"
    assert _load(data_dir, rem["branch_def_id"]).visibility == "private"

    # NO save for the import/remix working copies was ever public.
    for name, vis in seen:
        if name in ("atomic import",) or (name or "").endswith("(remix)"):
            assert vis == "private", (name, vis)


def test_read_graph_designs_shows_published_behind_newer_drafts(data_dir):
    # Codex r12 #2: a published design behind newer DRAFTS must be reachable —
    # pagination filters the published surface BEFORE the page. Plus offset browse.
    from tinyassets.api.branches import _ext_branch_build, _ext_branch_patch

    published = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "older published",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N", "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    })}))["branch_def_id"]
    _ext_branch_patch({
        "branch_def_id": published,
        "changes_json": json.dumps([{"op": "set_description", "description": "pub"}]),
    })
    # Two NEWER unpublished drafts.
    for i in range(2):
        _ext_branch_build({"spec_json": json.dumps({
            "name": f"newer draft {i}",
            "entry_point": "n",
            "node_defs": [{"node_id": "n", "display_name": "N", "prompt_template": "x"}],
            "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        })})

    # Even with limit=1, the published design is on the page — drafts never
    # consume it (they have no active version, so aren't on the published surface).
    page = json.loads(read_graph(target="designs", limit=1))
    assert published in {b["branch_def_id"] for b in page["branches"]}
    assert len(page["branches"]) == 1
    # A second published design + offset browse reaches page 2.
    second = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "second published",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N", "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    })}))["branch_def_id"]
    _ext_branch_patch({
        "branch_def_id": second,
        "changes_json": json.dumps([{"op": "set_description", "description": "pub"}]),
    })
    p1 = json.loads(read_graph(target="designs", limit=1, offset=0))
    p2 = json.loads(read_graph(target="designs", limit=1, offset=p1["next_offset"]))
    seen = {p1["branches"][0]["branch_def_id"], p2["branches"][0]["branch_def_id"]}
    assert {published, second} <= seen


def test_build_time_binding_slot_stores_no_value(data_dir):
    # A binding slot declared at BUILD time (is_binding + a value) keeps
    # only the SCHEMA flag — the value is never stored (PLAN §4). The is_binding
    # flag DOES travel on export (schema), so a Phase-2 engine can fill it.
    from tinyassets.api.branches import _ext_branch_build
    from tinyassets.daemon_server import get_branch_definition

    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "prebound design",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        "state_schema": [{"name": "target_repo", "type": "str",
                          "default_value": "github.com/author/PREBOUND",
                          "is_binding": True}],
    })}))["branch_def_id"]
    # No value stored in the shared row.
    assert "PREBOUND" not in json.dumps(get_branch_definition(data_dir, branch_def_id=bid))

    exported = json.loads(read_graph(target="design", branch_id=bid))
    assert "PREBOUND" not in json.dumps(exported)
    art_field = next(
        f for f in exported["artifact"]["spec"]["state_schema"]
        if f["name"] == "target_repo"
    )
    assert "default_value" not in art_field
    assert art_field.get("is_binding")   # the SLOT schema travels


def test_active_export_uses_immutable_snapshot_policy(data_dir):
    # F5: publish A/3, then mutate the live row to B/9 -> active-version export
    # must return the SNAPSHOT (A/3), not the mutated row (B/9).
    from tinyassets.api.branches import _ext_branch_build
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition

    policy_a = {"preferred": {"provider": "codex", "model": "a"}}
    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "immutable policy",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        "default_llm_policy": policy_a,
        "concurrency_budget": 3,
    })}))["branch_def_id"]
    publish_branch_version(
        data_dir, get_branch_definition(data_dir, branch_def_id=bid),
        publisher="alice",
    )
    # Mutate the live row AFTER publishing.
    b = BranchDefinition.from_dict(get_branch_definition(data_dir, branch_def_id=bid))
    b.default_llm_policy = {"preferred": {"provider": "codex", "model": "b"}}
    b.concurrency_budget = 9
    save_branch_definition(data_dir, branch_def=b.to_dict())

    exported = json.loads(read_graph(target="design", branch_id=bid))
    assert exported["artifact"]["spec"]["default_llm_policy"] == policy_a  # A, not B
    assert exported["artifact"]["spec"]["concurrency_budget"] == 3          # 3, not 9


def test_bound_design_is_private_and_hidden_from_other_users(data_dir, monkeypatch):
    _actor(monkeypatch, "alice")
    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)
    # A remix is the caller's PRIVATE working copy until explicitly published.
    child = json.loads(write_graph(target="remix", branch_id=parent))["branch_def_id"]
    assert _load(data_dir, child).visibility == "private"

    _actor(monkeypatch, "bob")
    # Bob cannot DISCOVER Alice's private remix...
    listed = {
        b["branch_def_id"] for b in json.loads(read_graph(target="designs"))["branches"]
    }
    assert child not in listed
    # ...nor EXPORT it (author-gated "not found").
    exp = json.loads(read_graph(target="design", branch_id=child))
    assert "not found" in exp["error"].lower()


# ── Branch-level fields round-trip (Codex latest-model F2) ──────────────────


def test_branch_level_fields_round_trip(data_dir):
    from tinyassets.api.branches import _ext_branch_build

    policy = {"preferred": {"provider": "codex", "model": "gpt-5"}}
    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "routed loop",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        "default_llm_policy": policy,
        "concurrency_budget": 3,
    })}))["branch_def_id"]
    src = _load(data_dir, bid)
    assert src.default_llm_policy == policy
    assert src.concurrency_budget == 3

    exported = json.loads(read_graph(target="design", branch_id=bid))
    assert exported["artifact"]["spec"]["default_llm_policy"] == policy
    assert exported["artifact"]["spec"]["concurrency_budget"] == 3
    imported = json.loads(
        write_graph(target="design", artifact_json=exported["artifact_json"]),
    )
    assert imported["status"] == "imported", imported
    dst = _load(data_dir, imported["branch_def_id"])
    assert dst.default_llm_policy == policy
    assert dst.concurrency_budget == 3


def test_import_rejects_hostile_branch_level_types(data_dir):
    from tinyassets.daemon_server import list_branch_definitions

    base = {
        "name": "hostile budget",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        "concurrency_budget": "lots",  # not a positive integer
    }
    out = json.loads(write_graph(target="design", artifact_json=json.dumps(base)))
    assert out["status"] == "rejected"
    assert "concurrency_budget" in json.dumps(out)
    assert "hostile budget" not in {
        b.get("name") for b in list_branch_definitions(data_dir)
    }


@pytest.mark.parametrize(
    "field, value",
    [
        ("name", 123),            # r13: .strip() on int -> AttributeError
        ("description", 5),
        ("domain_id", 7),
        ("goal_id", []),
        ("entry_point", 12),
        ("tags", 5),              # r13: list(5) -> TypeError
        ("tags", ["ok", 9]),      # array, but a non-string element
        ("skills", 3),
        ("state_schema", [7]),    # r13: 7.get(...) -> AttributeError
        ("node_defs", [1, 2]),
        ("edges", "not-a-list"),
        ("conditional_edges", [42]),
        ("graph", 9),             # not a JSON object
    ],
)
def test_import_rejects_malformed_top_level_types(data_dir, field, value):
    # Codex r13 #2: valid JSON whose top-level field is wrong-typed previously
    # escaped as a raw AttributeError/TypeError (HTTP 500) from staging. It must
    # now be a STRUCTURED rejection at the public boundary that NAMES the field,
    # and persist NOTHING — never a partial row.
    from tinyassets.daemon_server import list_branch_definitions

    spec = {
        "name": "malformed top-level",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    }
    spec[field] = value
    out = json.loads(write_graph(target="design", artifact_json=json.dumps(spec)))
    assert out["status"] == "rejected", out
    assert field in json.dumps(out), out
    # No partial row persisted for the rejected import.
    assert "malformed top-level" not in {
        b.get("name") for b in list_branch_definitions(data_dir)
    }


# ── Rolled-back versions are not listed/remixed/exported (F3) ───────────────


def test_no_active_version_hides_and_refuses(data_dir):
    from tinyassets.api.branches import _ext_branch_build
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.daemon_server import get_branch_definition
    from tinyassets.rollback import execute_rollback_set

    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "rollback design",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    })}))["branch_def_id"]
    v1 = publish_branch_version(
        data_dir, get_branch_definition(data_dir, branch_def_id=bid),
        publisher="alice",
    ).branch_version_id

    # Discoverable + remixable while active.
    assert bid in {
        b["branch_def_id"] for b in json.loads(read_graph(target="designs"))["branches"]
    }

    res = execute_rollback_set(data_dir, [v1], reason="regression", set_by="host")
    assert res["status"] == "ok", res

    # Its only version was rolled back -> hidden, not remixable, not exportable.
    assert bid not in {
        b["branch_def_id"] for b in json.loads(read_graph(target="designs"))["branches"]
    }
    remix = json.loads(write_graph(target="remix", branch_id=bid))
    assert remix["status"] == "rejected"
    assert "no active published version" in remix["error"]
    export = json.loads(read_graph(target="design", branch_id=bid))
    assert export["status"] == "rejected"
    assert "no active published version" in export["error"]


def test_rollback_surfaces_newest_active_not_regressed(data_dir):
    from tinyassets.api.branches import _ext_branch_build
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition
    from tinyassets.rollback import execute_rollback_set

    bid = json.loads(_ext_branch_build({"spec_json": json.dumps({
        "name": "two version design",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    })}))["branch_def_id"]
    v1 = publish_branch_version(
        data_dir, get_branch_definition(data_dir, branch_def_id=bid),
        publisher="alice",
    ).branch_version_id
    # Change topology so v2 has a distinct content hash, then publish v2.
    b = BranchDefinition.from_dict(get_branch_definition(data_dir, branch_def_id=bid))
    b.state_schema.append({"name": "extra", "type": "str"})
    save_branch_definition(data_dir, branch_def=b.to_dict())
    v2 = publish_branch_version(
        data_dir, get_branch_definition(data_dir, branch_def_id=bid),
        publisher="alice",
    ).branch_version_id
    assert v2 != v1

    # Roll back the NEWEST (v2) — v1 is now the newest active.
    execute_rollback_set(data_dir, [v2], reason="bad", set_by="host")

    # Remix + listing surface v1 (the active one), NOT the regressed v2.
    remix = json.loads(write_graph(target="remix", branch_id=bid))
    assert remix["status"] == "remixed", remix
    assert remix["fork_from"] == v1
    entry = next(
        e for e in json.loads(read_graph(target="designs"))["branches"]
        if e["branch_def_id"] == bid
    )
    assert entry["branch_version_id"] == v1


# ── Provenance is atomic: no orphan child, no fake success (F4) ─────────────


def test_remix_provenance_returned_error_deletes_child(data_dir, monkeypatch):
    import tinyassets.api.market as market
    from tinyassets.daemon_server import list_branch_definitions

    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)
    before = {b["branch_def_id"] for b in list_branch_definitions(data_dir)}
    monkeypatch.setattr(
        market, "_action_record_remix",
        lambda kw: json.dumps({"error": "cycle detected: internal ledger node 7"}),
    )
    out = json.loads(write_graph(target="remix", branch_id=parent))
    assert out["status"] == "rejected"
    assert "provenance" in out["error"].lower()
    # Codex r14 #5: the internal reason must NOT leak to the chatbot user.
    assert "cycle detected" not in out["error"]
    assert "internal ledger node 7" not in out["error"]
    # The orphan child was removed — no new branch persisted (verified cleanup).
    assert {b["branch_def_id"] for b in list_branch_definitions(data_dir)} == before


def test_remix_provenance_exception_deletes_child(data_dir, monkeypatch):
    import tinyassets.api.market as market
    from tinyassets.daemon_server import list_branch_definitions

    def _boom(kw):
        raise RuntimeError("attribution db down at 10.0.0.5")

    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)
    before = {b["branch_def_id"] for b in list_branch_definitions(data_dir)}
    monkeypatch.setattr(market, "_action_record_remix", _boom)
    out = json.loads(write_graph(target="remix", branch_id=parent))
    assert out["status"] == "rejected"
    assert "provenance" in out["error"].lower()
    # The raw exception type/message must NOT leak (r14 #5, security).
    assert "RuntimeError" not in out["error"]
    assert "attribution db down" not in out["error"]
    assert "10.0.0.5" not in out["error"]
    assert {b["branch_def_id"] for b in list_branch_definitions(data_dir)} == before


def test_remix_provenance_cleanup_failure_reports_orphan_may_remain(
    data_dir, monkeypatch,
):
    # Codex r14 #5: when the compensating delete FAILS, the response must not
    # falsely claim the orphan was removed. It verifies the row still exists and
    # returns an opaque message noting a partial copy may remain (logged for
    # maintenance), never the raw internal cause.
    import tinyassets.api.market as market
    import tinyassets.daemon_server as ds

    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)

    def _boom(kw):
        raise RuntimeError("attribution db down")

    def _delete_fails(base_path, *, branch_def_id):
        raise RuntimeError("delete blocked: db locked")

    monkeypatch.setattr(market, "_action_record_remix", _boom)
    monkeypatch.setattr(ds, "delete_branch_definition", _delete_fails)
    out = json.loads(write_graph(target="remix", branch_id=parent))
    assert out["status"] == "rejected"
    assert "provenance" in out["error"].lower()
    # Honest about the failed cleanup, opaque about the cause.
    assert "may remain" in out["error"].lower()
    assert "host reconciliation" in out["error"].lower()
    assert "safely retry" not in out["error"].lower()
    assert "db locked" not in out["error"]
    assert "RuntimeError" not in out["error"]


# ── Envelope identity types (Codex latest-model F5) ─────────────────────────


def test_import_rejects_hostile_envelope_identity(data_dir):
    from tinyassets.daemon_server import list_branch_definitions

    base_spec = {
        "name": "identity probe",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N",
                       "prompt_template": "x"}],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
    }
    bad_id = {
        "design_format": "tinyassets.branch_design/v1",
        "design_id": [],               # not a non-empty string
        "design_version": 1,
        "spec": base_spec,
    }
    o1 = json.loads(write_graph(target="design", artifact_json=json.dumps(bad_id)))
    assert o1["status"] == "rejected"
    assert "design_id" in o1["error"]

    bad_ver = {
        "design_format": "tinyassets.branch_design/v1",
        "design_id": "ok",
        "design_version": {"not": "an integer"},  # not a positive int
        "spec": base_spec,
    }
    o2 = json.loads(write_graph(target="design", artifact_json=json.dumps(bad_ver)))
    assert o2["status"] == "rejected"
    assert "design_version" in o2["error"]

    # Nothing persisted for either hostile envelope.
    assert "identity probe" not in {
        b.get("name") for b in list_branch_definitions(data_dir)
    }


# ── Unknown target hygiene ─────────────────────────────────────────────────


def test_unknown_targets_report_new_options(data_dir):
    r = json.loads(read_graph(target="bogus"))
    assert r["error"] == "unknown_target"
    assert "designs" in r["allowed_targets"] and "design" in r["allowed_targets"]
    w = json.loads(write_graph(target="bogus"))
    assert w["error"] == "unknown_target"
    assert "design" in w["allowed_targets"] and "remix" in w["allowed_targets"]
