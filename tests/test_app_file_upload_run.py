"""An ordinary app attachment is processed through the agent's own served tools.

Live finding (docs/concerns/2026-09-20-uploaded-file-binding-discovery.md): the
served agent could not discover that an app attachment reference binds through
``run_graph inputs_json``. The runtime path existed; the advertised tool
descriptions did not describe it. This file pins both halves:

1. the REGISTERED read_graph / write_graph / run_graph descriptions, on the
   served engine and the connector, carry one coherent recipe (red on the old
   descriptions, which said only "File references are unsupported/refused");
2. a real authenticated ASGI ``POST /mcp/app/files`` -> served ``write_graph``
   create -> ``run_graph inputs_json`` -> completed exact-byte processing ->
   ``read_graph`` bounded export, with no authoring session, handle or
   storage-level bind helper standing in for admission.
"""
# ruff: noqa: F811 -- imported pytest fixtures

import asyncio
import base64
import hashlib
import json

import pytest

from tests.test_app_file_upload import (  # noqa: F401 -- app is a fixture
    HOME_A,
    HOME_B,
    A,
    B,
    app,
    call,
    headers,
    meta,
    rows,
)
from tinyassets import engine_mcp_server as engine
from tinyassets import runs
from tinyassets import universe_server as server
from tinyassets.auth import middleware as mw

SIX_FIELDS = "{version,file_id,size_bytes,sha256,filename,media_type}"
RPC_CALL = 'invoke_mcp_action("read_run_file", file_id=ref["file_id"], offset=0, count=524288)'

# The recipe the descriptions advertise, used verbatim as the served create
# spec below: digest every bound file and report its first sixteen bytes, a
# value that exists nowhere in the reference metadata.
SOURCE = """import base64, hashlib
def run(state, effects=None):
    digests, heads = [], []
    for ref in state['files']:
        h, offset, head = hashlib.sha256(), 0, b''
        while True:
            part = invoke_mcp_action('read_run_file',
                file_id=ref['file_id'], offset=offset,
                count=524288)
            chunk = base64.b64decode(part['bytes_base64'])
            head = (head + chunk)[:16]
            h.update(chunk)
            offset = part['next_offset']
            if part['eof']:
                break
        digests.append(h.hexdigest())
        heads.append(head.hex())
    return {'digests': digests, 'heads': heads}
"""

SPEC = {
    "name": "Attachment digest", "visibility": "private", "entry_point": "digest",
    "io_manifest": {"inputs": [{"name": "files", "io_type": "file_bundle",
                                "max_count": 4, "max_bytes": 4194304}]},
    "state_schema": [{"name": "files", "type": "list"}, {"name": "digests", "type": "list"},
                     {"name": "heads", "type": "list"}],
    "node_defs": [{"node_id": "digest", "display_name": "Digest", "input_keys": ["files"],
                   "output_keys": ["digests", "heads"], "tools_allowed": ["read_run_file"],
                   "source_code": SOURCE}],
    "edges": [{"from": "digest", "to": "END"}],
}


def _descriptions(mcp):
    return {tool.name: " ".join((tool.description or "").split())
            for tool in asyncio.run(mcp.list_tools())}


def check_recipe(descriptions):
    """One coherent, discoverable recipe across the three graph handles."""
    read, write, run = (descriptions[name] for name in ("read_graph", "write_graph", "run_graph"))
    # run_graph: the delivery-only refusal is scoped; attachments bind via inputs_json.
    assert "File references are unsupported" not in run
    assert "File references are refused" not in run
    assert "deliver_output does not accept file references" in run
    assert "scoped to delivery only" in run
    for needle in ("delimited JSON attachment block", SIX_FIELDS, "io_manifest", "inputs_json",
                   "VERBATIM", "untrusted", "never an instruction"):
        assert needle in run, needle
    # write_graph: attachments are already references; capture is for authoring handles.
    assert "needs no capture" in write
    assert "ONLY for authoring-session handles" in write
    for needle in (SIX_FIELDS, "io_manifest", "file_bundle", "input_keys", "tools_allowed",
                   '["read_run_file"]', RPC_CALL, "bytes_base64", "next_offset", "eof",
                   "untrusted"):
        assert needle in write, needle
    assert "no files" not in write  # the sandbox reads BOUND inputs through an authorized RPC
    # read_graph: an unbound attachment reads only after a run binds it; build and run.
    assert "already run-file references" in read
    assert "only after a run" in read
    assert "sent message is not a run binding" in read or "sent message is not a binding" in read


@pytest.mark.parametrize("mcp", [engine.mcp, server.mcp], ids=["served_engine", "connector"])
def test_registered_tool_descriptions_carry_the_attachment_recipe(mcp):
    check_recipe(_descriptions(mcp))


def serve(monkeypatch, base, *, actor, home):
    """Pin the served engine to one owner/home, as the hosted engine is."""
    provider = mw._get_provider()
    monkeypatch.setattr(provider, "is_auth_required", lambda: False)
    monkeypatch.setattr(provider, "resolve_always_writes", lambda: True)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setattr(engine, "_GRAPH_ID", home)
    monkeypatch.setattr(engine, "_ACTOR_ID", actor)
    monkeypatch.setattr(engine, "_binding_error", lambda: None)
    monkeypatch.setattr(engine, "_engine_run_admit", lambda **kwargs: True)


def unwrap(raw):
    result = json.loads(raw)
    return result["content"] if isinstance(result, dict) and result.get("untrusted") else result


def upload(application, body, label):
    status, doc, _ = call(application, headers(body, header=meta(body, label=label)), [body])
    assert status == 200, doc
    (ref,) = doc["files"]
    assert set(ref) == {"version", "file_id", "size_bytes", "sha256", "filename", "media_type"}
    assert ref["sha256"] == hashlib.sha256(body).hexdigest() and ref["size_bytes"] == len(body)
    return ref


def test_real_upload_to_served_create_run_and_exact_export(app, monkeypatch):
    application, base = app
    binary = bytes(range(256)) * 200 + b"\x89PNG-tail\x00\xff"
    refs = [upload(application, binary, "attachment-label-000001"),
            upload(application, b"", "attachment-label-000002")]
    serve(monkeypatch, base, actor=A, home=HOME_A)

    # Unbound: the reference alone reads nothing, before and regardless of any run.
    refused = json.loads(engine.read_graph(target="run_file", run_id="not-a-run",
                                           file_id=refs[0]["file_id"]))
    assert refused.get("error") and "bytes_base64" not in refused

    created = json.loads(engine.write_graph(target="branch", operation="create",
                                            payload_json=json.dumps(SPEC)))
    assert created.get("branch_def_id"), created
    reply = unwrap(engine.run_graph(branch_def_id=created["branch_def_id"],
                                    inputs_json=json.dumps({"files": refs})))
    assert reply.get("run_id"), reply
    runs.wait_for(reply["run_id"], timeout=60)
    run = runs.get_run(base, reply["run_id"])
    assert run["status"] == "completed", run["error"]
    # Derived from the bytes, not copied from the reference: the exact digest
    # AND a prefix no metadata field carries (the empty file has none).
    assert run["output"]["digests"] == [hashlib.sha256(binary).hexdigest(),
                                        hashlib.sha256(b"").hexdigest()]
    assert run["output"]["heads"] == [binary[:16].hex(), ""]
    assert rows(base, "SELECT COUNT(*) FROM run_file_bindings WHERE run_id=?",
                reply["run_id"]) == [(2,)]

    chunk = unwrap(engine.read_graph(target="run_file", run_id=reply["run_id"],
                                     file_id=refs[0]["file_id"], file_max_bytes=16))
    assert base64.b64decode(chunk["bytes_base64"]) == binary[:16]
    assert chunk["next_offset"] == 16 and not chunk["eof"]
    tail = unwrap(engine.read_graph(target="run_file", run_id=reply["run_id"],
                                    file_id=refs[0]["file_id"], file_offset=len(binary) - 5,
                                    file_max_bytes=1024))
    assert base64.b64decode(tail["bytes_base64"]) == binary[-5:] and tail["eof"]


@pytest.mark.parametrize("who", ["foreign_owner_and_home", "forged_reference"])
def test_foreign_or_forged_reference_never_admits_a_run(app, monkeypatch, who):
    application, base = app
    binary = b"owned by A" * 1000
    ref = upload(application, binary, "attachment-label-000003")
    if who == "forged_reference":
        serve(monkeypatch, base, actor=A, home=HOME_A)
        ref = {**ref, "sha256": hashlib.sha256(b"something else").hexdigest()}
    else:
        serve(monkeypatch, base, actor=B, home=HOME_B)
    created = json.loads(engine.write_graph(target="branch", operation="create",
                                            payload_json=json.dumps(SPEC)))
    assert created.get("branch_def_id"), created
    reply = unwrap(engine.run_graph(branch_def_id=created["branch_def_id"],
                                    inputs_json=json.dumps({"files": [ref]})))
    assert reply.get("error") and not reply.get("run_id"), reply
    assert rows(base, "SELECT COUNT(*) FROM run_file_bindings") == [(0,)]
    assert rows(base, "SELECT COUNT(*) FROM runs") == [(0,)]
