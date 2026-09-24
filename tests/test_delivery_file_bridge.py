"""Cross-owner file bridge: refusal defaults, receiver-declared consent, topology.

Each test drives a real caller, not a helper in isolation. The two-owner byte-copy
acceptance path is root-owned integration; what is pinned here is every place the
bridge can silently GRANT something -- the unsourced RPC path, an undeclared
receiver field, an ad-hoc reference envelope, the dispatch-time rewrite, receiver
cleanup ordering, and the lock topology that forbids a cross-owner source fence.
"""
# ruff: noqa: F811 -- pytest resolves imported fixtures by their public names
import json
import sqlite3

import pytest

from tests.test_delivery_node_rpc import _prepare, _source, node_env  # noqa: F401
from tests.test_delivery_public import linked  # noqa: F401
from tests.test_receiver_links import env  # noqa: F401
from tests.test_run_file_capture import intake  # noqa: F401
from tinyassets import delivery_runtime, runs
from tinyassets.api import deliveries as api
from tinyassets.branches import BranchDefinition
from tinyassets.daemon_server import get_branch_definition, save_branch_definition
from tinyassets.storage import deliveries

REFERENCE = {
    "version": 1,
    "file_id": "a" * 32,
    "filename": "brief.txt",
    "media_type": "text/plain",
    "size_bytes": 11,
    "sha256": "b" * 64,
}


def _send(base, branch, link, outputs, *, occurrence="one"):
    run_id = _prepare(base, branch)
    runs.update_run_status(base, run_id, status="running")
    return api.deliver_node_output(
        base, source=_source(base, branch, run_id), link_id=link["link_id"],
        occurrence_id=occurrence, outputs=outputs, should_cancel=lambda: False,
    )


def _declare_receiver_file(base, auth, *, max_bytes=1024):
    """Receiver declares a file input on its OWN branch, then re-exposes it.

    The admitted snapshot governs, so the declaration has to exist before the
    receiver and link are created; editing the branch afterwards changes nothing
    about an already admitted contract.
    """
    from tinyassets import universe_server as server

    auth("receiver")
    branch = BranchDefinition.from_dict(get_branch_definition(base, branch_def_id="b-receiver"))
    definition = branch.to_dict()
    definition["state_schema"] = [
        {**field, "type": "dict"} if field.get("name") == "topic" else field
        for field in branch.state_schema
    ]
    definition["io_manifest"] = {"inputs": [
        {"name": "topic", "io_type": "file", "max_count": 1, "max_bytes": max_bytes},
    ]}
    save_branch_definition(base, branch_def=definition)
    receiver = json.loads(server.write_graph(
        target="receiver", operation="create", graph_id="u-receiver",
        payload_json=json.dumps({"branch_def_id": "b-receiver", "node_id": "entry",
                                 "input_keys": ["topic"], "allowed_senders": ["sender"]}),
    ))
    assert "receiver_id" in receiver, receiver
    auth("sender")
    link = json.loads(server.write_graph(
        target="output_link", operation="connect", graph_id="u-sender",
        payload_json=json.dumps({"branch_def_id": "b-sender", "node_id": "entry",
                                 "receiver_id": receiver["receiver_id"],
                                 "expected_generation": receiver["generation"],
                                 "mapping": {"result": "topic"}}),
    ))
    assert "link_id" in link, link
    return BranchDefinition.from_dict(definition), link


def test_unsourced_rpc_file_envelope_stays_refused(linked):
    """No trusted source run means nothing to resolve against: refuse the shape."""
    from tinyassets import universe_server as server

    base, auth, _, link = linked
    auth("sender")
    for envelope in (REFERENCE, {"type": "file", "id": "x"}, {"handle_id": "h"}):
        result = json.loads(server.run_graph(
            operation="deliver_output", graph_id="u-sender",
            inputs_json=json.dumps({"link_id": link["link_id"], "occurrence_id": "one",
                                    "outputs": {"result": envelope}}),
        ))
        assert result.get("error") == "invalid_delivery_request", result
        assert "delivery_file_transfer_not_implemented" in result["detail"]
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT COUNT(*) FROM graph_deliveries").fetchone()[0] == 0


def test_sourced_delivery_refuses_ad_hoc_reference_envelopes(node_env):
    """A trusted source admits the exact versioned reference shape and nothing
    adjacent: handle/artifact envelopes and declared file markers still refuse."""
    base, auth, _, _, branch, _ = node_env
    _, link = _declare_receiver_file(base, auth)
    for envelope in ({"handle_id": "h", "session_id": "s"}, {"type": "file_bundle"},
                     {**REFERENCE, "extra": 1}, {**REFERENCE, "version": 2}):
        with pytest.raises(ValueError) as caught:
            _send(base, branch, link, {"result": envelope})
        assert "file" in str(caught.value) or "reference" in str(caught.value), caught.value
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT COUNT(*) FROM graph_deliveries").fetchone()[0] == 0


def test_file_reference_needs_a_receiver_branch_declaration(node_env):
    """The receiver's branch, not the sender and not the contract, grants this.

    An undeclared field refuses on the DECLARATION, not on its contract type --
    measured, not assumed. ``topic`` is a ``str`` here, so a type mismatch was
    only ever the incidental second line; it says nothing about a field whose
    type admits a dict, which is what ``test_delivery_file_positions`` pins.
    """
    base, _, _, link, branch, _ = node_env
    with pytest.raises(ValueError) as caught:
        _send(base, branch, link, {"result": REFERENCE})
    assert "delivery_file_transfer_not_implemented" in str(caught.value)
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT COUNT(*) FROM graph_deliveries").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='graph_delivery_files'"
        ).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM graph_delivery_files").fetchone()[0] == 0


def test_declared_file_field_resolves_ownership_not_metadata(node_env):
    """Declaration is consent, never authority: an envelope the sender does not
    own under its trusted run resolves to nothing and no delivery is accepted."""
    base, auth, _, _, branch, _ = node_env
    _, link = _declare_receiver_file(base, auth)
    with pytest.raises(Exception) as caught:
        _send(base, branch, link, {"result": REFERENCE})
    assert "run_file_not_found" in str(caught.value), caught.value
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT COUNT(*) FROM graph_deliveries").fetchone()[0] == 0
        # Nothing was reserved or journalled: the custody schema was never even
        # created, which is the strongest available form of "no allocation".
        for table in ("run_file_operations", "run_file_allocations", "run_file_objects"):
            existing = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,),
            ).fetchone()[0]
            assert existing == 0 or conn.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608 -- fixed literal names
            ).fetchone()[0] == 0


def test_declared_limits_come_from_the_receiver_branch(node_env):
    """max_bytes/max_count are the receiver's declaration; no per-user quota exists."""
    base, auth, _, _, branch, _ = node_env
    _, link = _declare_receiver_file(base, auth, max_bytes=4)
    with pytest.raises(ValueError) as caught:
        _send(base, branch, link, {"result": REFERENCE})
    assert "receiver_file_declaration_refused" in str(caught.value)
    assert "manifest.invalid_reference" in str(caught.value)


def test_dispatch_rewrite_fails_closed_without_receiver_provenance(node_env):
    """Phase D resolves at the ACTING principal. With no receiver custody rows a
    sender reference surviving into inputs_json refuses at every dispatch."""
    base, auth, _, _, branch, _ = node_env
    receiver_branch, _ = _declare_receiver_file(base, auth)
    delivery = {
        "delivery_id": "d1", "receiver_owner_id": "receiver",
        "receiver_universe_id": "u-receiver",
    }
    with deliveries.transaction(base) as conn:
        with pytest.raises(ValueError) as caught:
            delivery_runtime.receiver_file_inputs(
                conn, delivery, receiver_branch, {"topic": REFERENCE}, "no-such-run",
            )
    assert "delivery_file_transfer_not_implemented" in str(caught.value)


def test_receiver_provenance_is_deleted_before_its_parent(linked):
    """Real cleanup, not an allowlist entry: the FK child precedes its parent, and
    the receiver's own bindings -- how it resolves its accepted input -- are not here."""
    from tinyassets import account_deletion

    base, _, _, _ = linked
    with deliveries.transaction(base) as conn:
        targets = [name for name, _, _ in account_deletion._delivery_deletion_targets(
            conn, principal="sender", home="u-sender",
        )]
    assert "graph_delivery_files" in targets
    assert targets.index("graph_delivery_files") < targets.index("graph_deliveries")
    assert not {"run_file_bindings", "run_file_objects"} & set(targets)


def test_cross_owner_source_fence_would_deadlock_on_the_runs_writer(intake):
    """Executable form of the argument that forces publication_check to exist: the
    publication writer is on .runs.db, so a source fence taking it cannot be had."""
    from tinyassets.run_file_capture import capture_authoring_files

    base, _, sources, _ = intake
    seen = {}

    def publication_check(conn, platform):
        second = sqlite3.connect(str(runs.runs_db_path(base)), timeout=0.2)
        try:
            with pytest.raises(sqlite3.OperationalError) as caught:
                second.execute("BEGIN IMMEDIATE")
            seen["error"] = str(caught.value)
        finally:
            second.close()

    import tinyassets.run_file_capture as capture

    original = capture._capture_files

    def patched(*args, **kwargs):
        kwargs["publication_check"] = publication_check
        return original(*args, **kwargs)

    capture._capture_files = patched
    try:
        refs = capture_authoring_files(base, owner_id="owner", universe_id="u",
                                       label="fence-topology", sources=sources)
    finally:
        capture._capture_files = original
    assert refs and "locked" in seen.get("error", "")
