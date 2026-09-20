"""The user-facing builder, not a storage fixture, must preserve file contracts."""
# ruff: noqa: F811 -- imported pytest fixtures

import base64
import copy
import hashlib
import json

import pytest

from tests.test_run_file_public import capture, direct_files, intake, public, rpc  # noqa: F401
from tinyassets import engine_mcp_server as engine
from tinyassets import runs
from tinyassets import universe_server as server


def file_spec(branch):
    nodes = [node.to_dict() for node in branch.node_defs]
    nodes[0]["node_id"] = "chosen-entry"
    nodes[1]["node_id"] = "downstream"
    return {
        "name": "User-built exact binary workflow", "visibility": "private",
        "entry_point": "chosen-entry", "node_defs": nodes,
        "edges": [{"from": "chosen-entry", "to": "downstream"},
                  {"from": "downstream", "to": "END"}],
        "state_schema": branch.state_schema, "io_manifest": branch.io_manifest,
    }


@pytest.fixture(params=[False, True])
def writer(request, public, monkeypatch):
    served = request.param
    if served:
        from tinyassets.auth.middleware import _get_provider

        # The hosted engine binds coarse least-privilege grants. Exercise the
        # production WorkOS resolve-always scope path, not the fixture's legacy
        # OAuth exact-scope mode; actual scope checks and owner ACLs remain on.
        provider = _get_provider()
        monkeypatch.setattr(provider, "is_auth_required", lambda: False)
        monkeypatch.setattr(provider, "resolve_always_writes", lambda: True)
        monkeypatch.setattr(engine, "_GRAPH_ID", "u")
        monkeypatch.setattr(engine, "_ACTOR_ID", "owner")
        monkeypatch.setattr(engine, "_binding_error", lambda: None)
        monkeypatch.setattr(engine, "_engine_run_admit", lambda **kwargs: True)
    return engine.write_graph if served else server.write_graph


def create(writer, spec, **kwargs):
    return json.loads(writer(target="branch", operation="create",
                             payload_json=json.dumps(spec), **kwargs))


def read(branch_id):
    return json.loads(server.read_graph(target="branch", branch_id=branch_id))


def patch(writer, branch_id, ops):
    kwargs = {"payload_json" if writer is engine.write_graph else "changes_json":
              json.dumps(ops)}
    return json.loads(writer(target="branch", operation="patch", branch_id=branch_id, **kwargs))


def unwrap(raw):
    result = json.loads(raw)
    return result["content"] if result.get("untrusted") else result


def test_actual_public_create_publish_capture_run_and_exact_export(direct_files, public, writer):
    from tinyassets.branch_versions import get_branch_version

    base, branch, _, bodies = direct_files
    _, sources, _, _ = public
    spec = file_spec(branch)
    created = json.loads(writer(target="branch", operation="create",
                                 payload_json=json.dumps(spec)))
    assert created.get("branch_def_id"), created
    branch_id = created["branch_def_id"]
    assert branch_id != branch.branch_def_id
    got = json.loads(server.read_graph(target="branch", branch_id=branch_id))
    assert got["graph"].get("io_manifest") == spec["io_manifest"], got
    published = json.loads(server.write_graph(target="branch", operation="publish",
                                              branch_id=branch_id))
    assert published.get("branch_version_id"), published
    version_id = published["branch_version_id"]
    assert get_branch_version(base, version_id).snapshot["io_manifest"] == spec["io_manifest"]
    edited = copy.deepcopy(spec["io_manifest"])
    edited["inputs"][0]["max_bytes"] = 1
    result = patch(writer, branch_id, [{"op": "set_io_manifest", "io_manifest": edited}])
    assert result["status"] == "patched", result
    assert read(branch_id)["graph"]["io_manifest"] == edited
    assert get_branch_version(base, version_id).snapshot["io_manifest"] == spec["io_manifest"]
    new_version = json.loads(server.write_graph(target="branch", operation="publish",
                                                branch_id=branch_id))["branch_version_id"]
    assert get_branch_version(base, new_version).snapshot["io_manifest"] == edited
    served = writer is engine.write_graph
    graph = {} if served else {"graph_id": "u"}
    refs = unwrap(writer(target="run_file", operation="capture", **graph,
                         payload_json=json.dumps({"label": "authored", "sources": sources})))[
        "files"]
    runner = engine.run_graph if served else server.run_graph
    reply = unwrap(runner(branch_version_id=version_id, **graph,
                          inputs_json=json.dumps({"files": refs})))
    assert reply.get("run_id"), reply
    runs.wait_for(reply["run_id"], timeout=30)
    run = runs.get_run(base, reply["run_id"])
    assert run["status"] == "completed", run["error"]
    assert run["output"]["second"] == [hashlib.sha256(body).hexdigest() for body in bodies]
    reader = engine.read_graph if served else server.read_graph
    chunk = unwrap(reader(target="run_file", **graph, run_id=run["run_id"],
                          file_id=refs[0]["file_id"], file_max_bytes=33))
    assert base64.b64decode(chunk["bytes_base64"]) == bodies[0][:33]


@pytest.mark.parametrize("invalid", ["missing", [], {"inputs": [{"name": "files",
                         "io_type": "file_bundle", "max_count": True}]},
                         {"inputs": [{"name": "absent", "io_type": "file"}]}])
def test_invalid_contract_patch_is_atomic(direct_files, public, writer, invalid):
    from tinyassets.branch_versions import list_branch_versions

    base, branch, _, _ = direct_files
    branch_id = create(writer, file_spec(branch))["branch_def_id"]
    before = read(branch_id)
    versions = list_branch_versions(base, branch_def_id=branch_id)
    operation = {"op": "set_io_manifest"}
    if invalid != "missing":
        operation["io_manifest"] = invalid
    result = patch(writer, branch_id, [{"op": "set_name", "name": "must not save"}, operation])
    assert result.get("status") == "rejected", result
    assert read(branch_id) == before
    assert list_branch_versions(base, branch_def_id=branch_id) == versions


def test_contract_clear_and_unrelated_edit(direct_files, public, writer):
    _, branch, _, _ = direct_files
    spec = file_spec(branch)
    branch_id = create(writer, spec)["branch_def_id"]
    assert patch(writer, branch_id, [{"op": "set_name", "name": "renamed"}])["status"] == "patched"
    assert read(branch_id)["graph"]["io_manifest"] == spec["io_manifest"]
    assert patch(writer, branch_id, [{"op": "set_io_manifest", "io_manifest": None}])[
        "status"] == "patched"
    assert "io_manifest" not in read(branch_id)["graph"]


def test_final_staged_state_and_contract_validated_together(direct_files, public, writer):
    _, branch, _, _ = direct_files
    branch_id = create(writer, file_spec(branch))["branch_def_id"]
    manifest = {"inputs": [{"name": "new_file", "io_type": "file"}]}
    result = patch(writer, branch_id, [
        {"op": "set_io_manifest", "io_manifest": manifest},
        {"op": "add_state_field", "name": "new_file", "type": "dict"},
    ])
    assert result["status"] == "patched", result
    assert read(branch_id)["graph"]["io_manifest"] == manifest


def test_foreign_actor_cannot_edit_file_contract(direct_files, public, writer, monkeypatch):
    _, branch, _, _ = direct_files
    _, _, _, auth = public
    branch_id = create(writer, file_spec(branch))["branch_def_id"]
    before = read(branch_id)
    auth("outsider")
    if writer is engine.write_graph:
        monkeypatch.setattr(engine, "_ACTOR_ID", "outsider")
    result = patch(writer, branch_id, [{"op": "set_io_manifest", "io_manifest": None}])
    assert result.get("error"), result
    auth("owner")
    assert read(branch_id) == before


def test_create_manifest_idempotency_and_invalid_refusal(direct_files, public, writer):
    _, branch, _, _ = direct_files
    spec = file_spec(branch)
    key = "public-file-build-key"
    original = create(writer, spec, idempotency_key=key)
    assert original.get("branch_def_id"), original
    changed = copy.deepcopy(spec)
    changed["io_manifest"]["inputs"][0]["max_bytes"] = 1
    result = create(writer, changed, idempotency_key=key)
    assert result.get("error") == "branch_idempotency_conflict", result
    assert "io_manifest" in result["conflicting_fields"]
    changed["io_manifest"]["inputs"][0]["max_count"] = True
    rejected = create(writer, changed)
    assert rejected.get("status") == "rejected", rejected


@pytest.mark.parametrize("override", ["inherit", None, {"inputs": []}])
def test_public_remix_inherits_or_explicitly_overrides_manifest(direct_files, public, override):
    _, branch, _, _ = direct_files
    spec = file_spec(branch)
    original = create(server.write_graph, spec)["branch_def_id"]
    version = json.loads(server.write_graph(target="branch", operation="publish",
                                            branch_id=original))["branch_version_id"]
    remix = {"name": "remixed file workflow", "fork_from": version}
    if override != "inherit":
        remix["io_manifest"] = override
    reply = json.loads(server.write_graph(target="branch", operation="remix",
                                          payload_json=json.dumps(remix)))
    assert reply.get("branch_def_id"), reply
    assert read(reply["branch_def_id"])["graph"].get("io_manifest") == (
        spec["io_manifest"] if override == "inherit" else override)


@pytest.mark.parametrize("clear", [False, True])
def test_canonical_nested_graph_manifest_and_explicit_top_level_null(direct_files, public, clear):
    _, branch, _, _ = direct_files
    spec = file_spec(branch)
    manifest = spec.pop("io_manifest")
    spec["graph"] = {"io_manifest": manifest}
    if clear:
        spec["io_manifest"] = None
    result = create(server.write_graph, spec)
    assert result.get("branch_def_id"), result
    assert read(result["branch_def_id"])["graph"].get("io_manifest") == (
        None if clear else manifest)
