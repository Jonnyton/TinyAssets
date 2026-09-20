"""Ordinary connector and pinned served handles expose the same owned file API."""
# ruff: noqa: F811 -- imported pytest fixtures

import base64
import hashlib
import json

import pytest

from tests.test_run_file_capture import intake  # noqa: F401
from tests.test_run_file_direct import direct_files, rpc  # noqa: F401
from tinyassets import engine_mcp_server as engine
from tinyassets import runs
from tinyassets import universe_server as server
from tinyassets.storage import _connect as author_connect
from tinyassets.storage import run_files


@pytest.fixture
def public(intake, monkeypatch, authenticate_request):  # noqa: F811
    base, _, sources, bodies = intake
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    def auth(owner="owner", write=True):
        authenticate_request(owner, capabilities=["tinyassets.extensions.read"] +
                             (["tinyassets.extensions.write", "tinyassets.extensions.costly"]
                              if write else []))
    auth()
    return base, sources, bodies, auth


def capture(sources, **extra):
    return json.loads(server.write_graph(target="run_file", operation="capture", graph_id="u",
                                        payload_json=json.dumps({"label": "public",
                                                                 "sources": sources, **extra})))


def test_public_capture_limits_exact_export_and_selective_release(public):
    base, sources, bodies, _ = public
    limits = json.loads(server.read_graph(target="run_file_limits", graph_id="u"))
    assert limits["capture_available"] and limits["unbound_retention_seconds"] == 3600
    refs = capture(sources)["files"]
    run_id = runs.create_run(base, branch_def_id="fixture", thread_id="", inputs={"files": refs},
                             actor="owner", owner_user_id="owner", queue_universe_id="u")
    with runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        run_files.bind_in_transaction(conn, run_id=run_id, owner_id="owner", universe_id="u",
                                      field_name="files", file_ids=[ref["file_id"] for ref in refs])
        conn.execute("UPDATE runs SET status='completed' WHERE run_id=?", (run_id,))
    chunk = json.loads(server.read_graph(target="run_file", graph_id="u", run_id=run_id,
                                        file_id=refs[0]["file_id"], file_max_bytes=123))
    assert base64.b64decode(chunk["bytes_base64"]) == bodies[0][:123]
    assert chunk["reference"] == refs[0] and chunk["next_offset"] == 123
    released = json.loads(server.write_graph(
        target="run_file", graph_id="u", operation="release",
        payload_json=json.dumps({"file_id": refs[0]["file_id"]}),
    ))
    assert released["state"] == "released"
    refused = json.loads(server.read_graph(target="run_file", graph_id="u", run_id=run_id,
                                          file_id=refs[0]["file_id"]))
    assert refused["error"]
    sibling = json.loads(server.read_graph(target="run_file", graph_id="u", run_id=run_id,
                                          file_id=refs[1]["file_id"]))
    assert sibling["bytes_base64"] == "" and sibling["eof"]


@pytest.mark.parametrize("selector", ["owner_id", "universe_id", "path", "url", "run_id"])
def test_public_capture_rejects_authority_and_path_selectors(public, selector):
    base, sources, _, _ = public
    assert capture(sources, **{selector: "forged"})["error"] == "file_request_invalid"
    with runs._connect(base) as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='run_file_operations'").fetchone():
            assert conn.execute("SELECT COUNT(*) FROM run_file_operations").fetchone()[0] == 0


def test_foreign_identity_and_read_only_scope_cannot_capture(public):
    _, sources, _, auth = public
    auth("outsider")
    assert capture(sources)["error"]
    auth(write=False)
    assert capture(sources)["error"]


def test_unconfigured_capture_reports_real_missing_capacity(public, monkeypatch):
    _, _, _, _ = public
    monkeypatch.delenv("TINYASSETS_RUN_FILE_CUSTODY_MAX_BYTES")
    result = json.loads(server.read_graph(target="run_file_limits", graph_id="u"))
    assert result == {"capture_available": False, "reason": "file_custody_not_configured"}


def test_served_agent_is_pinned_and_can_capture_without_other_user_scope(public, monkeypatch):
    _, sources, _, _ = public
    monkeypatch.setattr(engine, "_GRAPH_ID", "u")
    monkeypatch.setattr(engine, "_ACTOR_ID", "owner")
    monkeypatch.setattr(engine, "_binding_error", lambda: None)
    monkeypatch.setattr(engine, "_engine_run_admit", lambda **kwargs: True)
    result = engine.write_graph(target="run_file", operation="capture",
                                payload_json=json.dumps({"label": "served", "sources": sources}))
    assert "file_id" in result, result
    assert "capture_available" in engine.read_graph(target="run_file_limits")
    refused = engine.write_graph(target="run_file", operation="capture",
                                 payload_json=json.dumps({"label": "served", "sources": sources,
                                                          "universe_id": "other"}))
    assert "file_request_invalid" in refused


@pytest.mark.parametrize("versioned", [False, True])
def test_public_capture_to_run_graph_to_exact_export(direct_files, intake, monkeypatch,
                                                    authenticate_request, versioned):
    from tinyassets.branch_versions import publish_branch_version

    base, branch, _, bodies = direct_files
    _, _, sources, _ = intake
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    authenticate_request("owner", capabilities=["tinyassets.extensions.read",
                                                "tinyassets.extensions.write",
                                                "tinyassets.extensions.costly"])
    refs = capture(sources)["files"]
    selectors = {"branch_def_id": branch.branch_def_id}
    if versioned:
        version = publish_branch_version(base, branch.to_dict(), publisher="owner")
        selectors = {"branch_version_id": version.branch_version_id}
    reply = json.loads(server.run_graph(**selectors, graph_id="u",
                                       inputs_json=json.dumps({"files": refs})))
    assert reply.get("run_id"), reply
    runs.wait_for(reply["run_id"], timeout=30)
    run = runs.get_run(base, reply["run_id"])
    assert run["status"] == "completed", run["error"]
    assert run["output"]["second"] == [hashlib.sha256(body).hexdigest() for body in bodies]
    exported = json.loads(server.read_graph(target="run_file", graph_id="u", run_id=run["run_id"],
                                            file_id=refs[0]["file_id"], file_max_bytes=65))
    assert base64.b64decode(exported["bytes_base64"]) == bodies[0][:65]


@pytest.mark.parametrize("selector", [{"branch_def_id": "other"}, {"goal_id": "goal"},
                                     {"operation": "cancel"}, {"webhook_op": "mint"},
                                     {"operation": "deliver_output"}])
def test_version_selector_refuses_mixed_targets(public, selector):
    assert "error" in json.loads(server.run_graph(branch_version_id="version", **selector))


def test_private_version_is_not_exposed_through_either_public_handle(direct_files, public,
                                                                   monkeypatch):
    from tinyassets.branch_versions import publish_branch_version

    base, branch, _, _ = direct_files
    version = publish_branch_version(base, branch.to_dict(), publisher="owner")
    with author_connect(base) as conn:
        conn.execute("UPDATE branch_definitions SET author='other',visibility='private' "
                     "WHERE branch_def_id=?", (branch.branch_def_id,))
    monkeypatch.setattr(engine, "_GRAPH_ID", "u")
    monkeypatch.setattr(engine, "_ACTOR_ID", "owner")
    monkeypatch.setattr(engine, "_binding_error", lambda: None)
    monkeypatch.setattr(engine, "_engine_run_admit", lambda **kwargs: True)
    for handle in (server.run_graph, engine.run_graph):
        assert "Branch version not found" in handle(branch_version_id=version.branch_version_id)


def test_served_version_delegates_under_pinned_owner(direct_files, public, monkeypatch):
    from tinyassets.auth.middleware import current_identity
    from tinyassets.branch_versions import publish_branch_version

    base, branch, _, _ = direct_files
    version = publish_branch_version(base, branch.to_dict(), publisher="owner")
    monkeypatch.setattr(engine, "_GRAPH_ID", "u")
    monkeypatch.setattr(engine, "_ACTOR_ID", "owner")
    monkeypatch.setattr(engine, "_binding_error", lambda: None)
    monkeypatch.setattr(engine, "_engine_run_admit", lambda **kwargs: True)
    seen = []
    def dispatch(**kwargs):
        seen.append((current_identity().user_id, kwargs))
        return json.dumps({"run_id": "reserved", "status": "queued"})
    monkeypatch.setattr(server, "run_graph", dispatch)
    monkeypatch.setattr(engine, "_attach_run_admission", lambda *args: None)
    assert "reserved" in engine.run_graph(branch_version_id=version.branch_version_id)
    assert seen == [("owner", {"branch_def_id": "", "branch_version_id": version.branch_version_id,
                               "graph_id": "u", "run_name": "", "inputs_json": ""})]


def test_accepted_dispatch_failure_keeps_run_id_and_owner_only_uncertainty(direct_files, public,
                                                                        monkeypatch):
    from tinyassets import run_input_origins

    base, branch, refs, _ = direct_files
    _, _, _, auth = public
    def unavailable(*args, **kwargs):
        raise RuntimeError("executor unavailable")
    monkeypatch.setattr(run_input_origins, "dispatch_initial_run", unavailable)
    monkeypatch.setattr("tinyassets.api.runs._legacy_request_provider",
                        lambda *args: pytest.fail("provider bound before admitted CAS"))
    reply = json.loads(server.run_graph(branch_def_id=branch.branch_def_id, graph_id="u",
                                       inputs_json=json.dumps({"files": refs})))
    assert reply.get("run_id") and reply["status"] == "queued", reply
    assert "accepted durably" in reply["error"] and "do not submit" in reply["error"]
    run_id = reply["run_id"]
    with runs._connect(base) as conn:
        conn.execute("UPDATE run_input_admissions SET claim_token='ambiguous' WHERE run_id=?",
                     (run_id,))
    snapshot = json.loads(server.read_graph(target="run", graph_id="u", run_id=run_id))
    assert snapshot["phase"] == "recovery_required", snapshot
    assert snapshot["actions_may_have_occurred"] and not snapshot["automatic_replay"]
    assert runs.get_run(base, run_id)["status"] == "queued"
    with runs._connect(base) as conn:
        conn.execute("UPDATE run_input_admissions SET origin_kind='unknown' WHERE run_id=?",
                     (run_id,))
    snapshot = json.loads(server.read_graph(target="run", graph_id="u", run_id=run_id))
    assert snapshot["phase"] == "origin_unavailable"
    auth("outsider")
    snapshot = json.loads(server.read_graph(target="run", graph_id="u", run_id=run_id))
    assert "admission_state" not in snapshot
