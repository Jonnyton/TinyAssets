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
    # (the credential vault + binding plane, an active lane). The design carries
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
    assert "engine" in lowered
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
    # through export -> import. Phase 1 carries no binding VALUES at all.
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
        {"op": "set_state_field_default", "name": "target_repo",
         "default_value": "github.com/example/repo"},
    ]))

    result = json.loads(_run_graph(
        branch_def_id=child,
        inputs_json=json.dumps({"request_payload": "fix a bug"}),
    ))
    blob = json.dumps(result).lower()
    # The coding node must fail closed: either an explicit sandbox/attestation
    # refusal surfaces, or the run does not reach clean success (it never
    # completes an unattested coding step).
    failed_closed = (
        "sandbox" in blob or "attest" in blob
        or result.get("status") not in ("completed", "succeeded", "success")
    )
    assert failed_closed, (
        "remixed reference coding node must fail closed without "
        f"TINYASSETS_OS_SANDBOX_ATTESTED; got {result}"
    )


# ── Binding privacy: values never travel / leak (Codex latest-model F1) ─────


def test_binding_schema_travels_but_no_value_exists(data_dir, monkeypatch):
    # Phase 1 (Codex r11 re-scope): the is_binding SCHEMA (slot) travels through
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
    # (no binding plane) — refused for the AUTHOR and for a non-owner alike.
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

    for who in ("bob", "alice"):
        _actor(monkeypatch, who)
        refused = json.loads(_action_run_branch({
            "branch_def_id": bid, "inputs_json": json.dumps({}),
        }))
        assert refused.get("failure_class") == "binding_unbound_phase1", (who, refused)
        assert "inert" in refused["error"].lower()


@pytest.mark.xfail(
    strict=False,
    reason=(
        "S1 is adding is_binding markers to the reference's binding slots "
        "(target_repo / merge_policy). Until S1 marks them and S2 re-syncs the "
        "reference JSON verbatim, the shipped artifact declares no is_binding "
        "slot so the guard cannot fire — S2 does NOT mark the fields itself "
        "(Codex r13)."
    ),
)
def test_seeded_reference_binding_slots_are_inert(data_dir, monkeypatch):
    # Codex r13: the inert guard was only exercised against SYNTHETIC is_binding
    # branches; the REAL seeded reference bypassed it because the shipped JSON
    # does not (yet) mark target_repo / merge_policy is_binding. Pin the actual
    # artifact so the guard is proven against what ships — not only a stand-in.
    from tinyassets.api.runs import _action_run_branch
    from tinyassets.branch_versions import branch_has_bound_fields

    seed_reference_designs(data_dir)
    bid = _reference_bid(data_dir)
    ref = _load(data_dir, bid)

    # The reference is a REPO-BLIND design: it must declare binding slots, or it
    # would run unbound against an arbitrary repo. (Fails until S1 marks them.)
    assert branch_has_bound_fields(ref.state_schema), (
        "seeded reference declares no is_binding slots — a repo-blind design "
        "would run unbound; S1 must mark target_repo / merge_policy is_binding"
    )

    _actor(monkeypatch, "alice")
    refused = json.loads(_action_run_branch({
        "branch_def_id": bid, "inputs_json": json.dumps({}),
    }))
    assert refused.get("failure_class") == "binding_unbound_phase1", refused
    assert "inert" in (refused.get("error") or "").lower()


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

    def _spy(base_path, *, branch_def):
        seen.append((branch_def.get("name"), branch_def.get("visibility")))
        return real_save(base_path, branch_def=branch_def)

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
    # Phase 1: a binding slot declared at BUILD time (is_binding + a value) keeps
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
        lambda kw: json.dumps({"error": "cycle detected"}),
    )
    out = json.loads(write_graph(target="remix", branch_id=parent))
    assert out["status"] == "rejected"
    assert "provenance" in out["error"].lower()
    # The orphan child was removed — no new branch persisted.
    assert {b["branch_def_id"] for b in list_branch_definitions(data_dir)} == before


def test_remix_provenance_exception_deletes_child(data_dir, monkeypatch):
    import tinyassets.api.market as market
    from tinyassets.daemon_server import list_branch_definitions

    def _boom(kw):
        raise RuntimeError("attribution db down")

    seed_reference_designs(data_dir)
    parent = _reference_bid(data_dir)
    before = {b["branch_def_id"] for b in list_branch_definitions(data_dir)}
    monkeypatch.setattr(market, "_action_record_remix", _boom)
    out = json.loads(write_graph(target="remix", branch_id=parent))
    assert out["status"] == "rejected"
    assert "provenance" in out["error"].lower()
    assert {b["branch_def_id"] for b in list_branch_definitions(data_dir)} == before


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
