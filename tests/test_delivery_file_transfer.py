"""Actual two-owner file delivery: sender bytes -> receiver-owned copy -> read.

The refusal/topology surface lives in ``test_delivery_file_bridge``. This module
proves the positive path the bridge exists for, end to end through the real
callers: sender custody bound to a running sender run, one delivery, receiver-
owned bytes the receiver reads through its OWN run binding. Nothing is stubbed --
the custody copy and the dispatch-time input rewrite both run for real.
"""
# ruff: noqa: F811 -- pytest resolves imported fixtures by their public names
import base64
import hashlib
import json
from contextlib import contextmanager

import pytest

from tests.test_delivery_node_rpc import _prepare, _source, node_env  # noqa: F401
from tests.test_delivery_public import linked  # noqa: F401
from tests.test_receiver_links import env  # noqa: F401
from tinyassets import delivery_runtime, runs
from tinyassets.api import deliveries as api
from tinyassets.authoring import service
from tinyassets.authoring.store import AuthoringStore
from tinyassets.branches import BranchDefinition
from tinyassets.daemon_server import get_branch_definition, save_branch_definition
from tinyassets.run_file_capture import capture_authoring_files
from tinyassets.run_file_reader import read_bound_file
from tinyassets.storage import deliveries
from tinyassets.storage import run_files as store

SENDER = ("sender", "u-sender")
RECEIVER = ("receiver", "u-receiver")


@pytest.fixture(autouse=True)
def custody_capacity(monkeypatch):
    """Cross-owner delivery needs the operational custody ceiling configured.

    Without it EVERY file delivery refuses ``file_custody_not_configured``: this
    env var is a real deployment prerequisite for the feature, not test scaffolding.
    """
    monkeypatch.setenv("TINYASSETS_RUN_FILE_CUSTODY_MAX_BYTES", str(64 * 1024 * 1024))


def receiver_file_link(base, auth, *, io_type="file", max_count=1, max_bytes=1 << 20):
    """Receiver declares a file input on its OWN branch, then exposes a link.

    The admitted snapshot governs, so the declaration must exist before the
    receiver and link are created.
    """
    from tinyassets import universe_server as server

    auth("receiver")
    branch = BranchDefinition.from_dict(get_branch_definition(base, branch_def_id="b-receiver"))
    definition = branch.to_dict()
    expected = "list" if io_type == "file_bundle" else "dict"
    definition["state_schema"] = [
        {**field, "type": expected} if field.get("name") == "topic" else field
        for field in branch.state_schema
    ]
    definition["io_manifest"] = {"inputs": [
        {"name": "topic", "io_type": io_type, "max_count": max_count, "max_bytes": max_bytes},
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


def sender_custody(base, bodies, *, label="delivery source"):
    """Real sender-owned custody objects captured from real authoring handles."""
    authoring = AuthoringStore(base)
    authoring.initialize()
    session = service.start_session(
        actor_id="sender", artifact_kind="node", sketch="files", store=authoring,
    )["session_id"]
    sources = []
    for index, body in enumerate(bodies):
        handle = authoring.put_file_handle(
            session_id=session, owner_id="sender", input_name=f"file{index}",
            filename=f"brief-{index}.txt", media_type="text/plain",
            content=body, lifetime_seconds=3600,
        )
        sources.append({"session_id": session, "handle_id": handle["handle_id"]})
    refs = capture_authoring_files(
        base, owner_id=SENDER[0], universe_id=SENDER[1], label=label, sources=sources,
    )
    return authoring, refs


def running_sender_run(base, branch, refs, *, field="attachment"):
    """A running sender run with the captured files bound to it -- the trusted source."""
    run_id = _prepare(base, branch)
    with runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        store.bind_in_transaction(
            conn, run_id=run_id, owner_id=SENDER[0], universe_id=SENDER[1],
            field_name=field, file_ids=[ref["file_id"] for ref in refs],
        )
    runs.update_run_status(base, run_id, status="running")
    return run_id


def deliver(base, branch, link, outputs, run_id, *, occurrence="one", cancel=lambda: False):
    return api.deliver_node_output(
        base, source=_source(base, branch, run_id), link_id=link["link_id"],
        occurrence_id=occurrence, outputs=outputs, should_cancel=cancel,
    )


def transfer_rows(base, delivery_id):
    with deliveries.transaction(base) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM graph_delivery_files WHERE delivery_id=? ORDER BY field_name, ordinal",
            (delivery_id,),
        )]


def receiver_run_id(base, delivery_id):
    with deliveries.transaction(base) as conn:
        row = conn.execute(
            "SELECT run_id FROM graph_delivery_attempts WHERE delivery_id=? AND attempt=1",
            (delivery_id,),
        ).fetchone()
    assert row is not None, "acceptance must create the receiver's own run"
    return row["run_id"]


def read_all(base, run_id, file_id, *, owner=RECEIVER):
    """Read a bound file the ordinary way -- through the owner's own run binding."""
    body = b""
    offset = 0
    while True:
        chunk = read_bound_file(
            base, owner_id=owner[0], universe_id=owner[1], run_id=run_id,
            file_id=file_id, offset=offset, count=1 << 16,
        )
        body += base64.b64decode(chunk["bytes_base64"])
        offset = chunk["next_offset"]
        if chunk["eof"]:
            return body


def custody_rows(base, owner):
    with runs._connect(base) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM run_file_objects WHERE owner_id=? AND universe_id=?", owner,
        )]


def test_single_file_delivery_copies_exact_bytes_into_receiver_custody(node_env):
    """The promised path: sender bytes -> receiver-owned copy -> receiver read.

    Every assertion is on a value the receiver can actually reach, and the sender
    file id must appear nowhere the receiver can see.
    """
    base, auth, _, _, branch, _ = node_env
    _, link = receiver_file_link(base, auth)
    body = ("exact 🍉 payload " * 400).encode()
    _, refs = sender_custody(base, [body])
    run_id = running_sender_run(base, branch, refs)

    receipt = deliver(base, branch, link, {"result": refs[0]}, run_id)

    assert "delivery_id" in receipt, receipt
    rows = transfer_rows(base, receipt["delivery_id"])
    assert len(rows) == 1
    record = rows[0]
    assert record["sender_file_id"] == refs[0]["file_id"]
    # A receiver-owned COPY, never the sender's row re-pointed.
    assert record["receiver_file_id"] != refs[0]["file_id"]
    assert record["sha256"] == hashlib.sha256(body).hexdigest()
    assert record["size_bytes"] == len(body)

    owned = custody_rows(base, RECEIVER)
    assert [row["file_id"] for row in owned] == [record["receiver_file_id"]]
    assert owned[0]["state"] == "ready"
    assert custody_rows(base, SENDER)[0]["file_id"] == refs[0]["file_id"]

    run = receiver_run_id(base, receipt["delivery_id"])
    assert read_all(base, run, record["receiver_file_id"]) == body
    # The receiver's own run inputs carry its own reference and no sender value.
    with runs._connect(base) as conn:
        inputs = json.loads(conn.execute(
            "SELECT inputs_json FROM runs WHERE run_id=?", (run,)
        ).fetchone()[0])
    assert inputs["topic"]["file_id"] == record["receiver_file_id"]
    assert refs[0]["file_id"] not in json.dumps(inputs)
    assert refs[0]["file_id"] not in json.dumps(receipt)


def test_bundle_delivery_preserves_order_and_each_body(node_env):
    """A declared bundle copies every member, in the sender's order, byte-exact."""
    base, auth, _, _, branch, _ = node_env
    _, link = receiver_file_link(base, auth, io_type="file_bundle", max_count=3)
    bodies = [b"first body", bytes(range(256)) * 40, b"third \xf0\x9f\x8d\x89 body"]
    _, refs = sender_custody(base, bodies)
    run_id = running_sender_run(base, branch, refs)

    receipt = deliver(base, branch, link, {"result": refs}, run_id)

    rows = transfer_rows(base, receipt["delivery_id"])
    assert [row["ordinal"] for row in rows] == [0, 1, 2]
    assert [row["sender_file_id"] for row in rows] == [ref["file_id"] for ref in refs]
    run = receiver_run_id(base, receipt["delivery_id"])
    for row, body in zip(rows, bodies):
        assert read_all(base, run, row["receiver_file_id"]) == body
    with runs._connect(base) as conn:
        inputs = json.loads(conn.execute(
            "SELECT inputs_json FROM runs WHERE run_id=?", (run,)
        ).fetchone()[0])
    assert [item["file_id"] for item in inputs["topic"]] == [
        row["receiver_file_id"] for row in rows
    ]


def test_identical_replay_returns_the_same_copy_and_a_changed_one_conflicts(node_env):
    """Occurrence identity is the receiver occurrence: no second copy either way."""
    base, auth, _, _, branch, _ = node_env
    _, link = receiver_file_link(base, auth)
    _, refs = sender_custody(base, [b"one body", b"other body"])
    run_id = running_sender_run(base, branch, refs)

    first = deliver(base, branch, link, {"result": refs[0]}, run_id)
    again = deliver(base, branch, link, {"result": refs[0]}, run_id)
    assert again["delivery_id"] == first["delivery_id"]
    assert len(custody_rows(base, RECEIVER)) == 1

    with pytest.raises(Exception) as caught:
        deliver(base, branch, link, {"result": refs[1]}, run_id)
    assert "occurrence" in type(caught.value).__name__.lower() or "conflict" in str(caught.value)
    # The conflicting replay allocated nothing: still exactly one receiver copy.
    assert len(custody_rows(base, RECEIVER)) == 1
    assert len(transfer_rows(base, first["delivery_id"])) == 1


def test_receiver_copy_survives_sender_release_and_run_completion(node_env):
    """Receiver readability never depends on sender retention -- erasure independence."""
    from tinyassets.run_file_release import release_owned_file

    base, auth, _, _, branch, _ = node_env
    _, link = receiver_file_link(base, auth)
    body = b"durable receiver bytes"
    _, refs = sender_custody(base, [body])
    run_id = running_sender_run(base, branch, refs)
    receipt = deliver(base, branch, link, {"result": refs[0]}, run_id)
    run = receiver_run_id(base, receipt["delivery_id"])

    sender_blob = base / ".run-file-custody" / (custody_rows(base, SENDER)[0]["storage_key"]
                                                + ".body")
    assert sender_blob.read_bytes() == body
    receiver_row = custody_rows(base, RECEIVER)[0]
    receiver_blob = base / ".run-file-custody" / (receiver_row["storage_key"] + ".body")
    # Separate physical objects, not a shared/deduplicated blob: erasing one
    # cannot reach the other.
    assert receiver_blob != sender_blob

    runs.update_run_status(base, run_id, status="completed")
    released = release_owned_file(
        base, owner_id=SENDER[0], universe_id=SENDER[1], file_id=refs[0]["file_id"],
    )
    assert released["state"] == "released", released
    assert not sender_blob.exists()
    assert [row["state"] for row in custody_rows(base, SENDER)] == ["released"]

    # The receiver's copy is untouched and still readable through its own run.
    assert receiver_blob.read_bytes() == body
    assert read_all(base, run, transfer_rows(base, receipt["delivery_id"])[0]
                    ["receiver_file_id"]) == body


def test_dispatch_rewrite_hands_the_receiver_its_own_references(node_env):
    """Phase D on real provenance: the sender envelope becomes the receiver's own."""
    base, auth, _, _, branch, _ = node_env
    receiver_branch, link = receiver_file_link(base, auth)
    body = b"rewritten at dispatch"
    _, refs = sender_custody(base, [body])
    run_id = running_sender_run(base, branch, refs)
    receipt = deliver(base, branch, link, {"result": refs[0]}, run_id)
    run = receiver_run_id(base, receipt["delivery_id"])

    with deliveries.transaction(base) as conn:
        delivery = dict(conn.execute(
            "SELECT * FROM graph_deliveries WHERE delivery_id=?", (receipt["delivery_id"],),
        ).fetchone())
    with runs._connect(base) as conn:
        conn.execute("BEGIN")
        rewritten = delivery_runtime.receiver_file_inputs(
            conn, delivery, receiver_branch, {"topic": refs[0]}, run,
        )
    expected = transfer_rows(base, receipt["delivery_id"])[0]["receiver_file_id"]
    assert rewritten["topic"]["file_id"] == expected
    assert refs[0]["file_id"] not in json.dumps(rewritten)
    assert rewritten["topic"]["sha256"] == hashlib.sha256(body).hexdigest()


def _hook_after_last_read(monkeypatch, action):
    """Run ``action`` after the final source read, before the publication fence.

    ``run_file_crossowner`` imports ``_capture_files`` by name, so BOTH bindings
    are patched: patching only the defining module would leave the cross-owner
    path untouched and quietly make this test vacuous. The hook records its own
    firing and every test asserts it fired.
    """
    import tinyassets.run_file_capture as capture
    import tinyassets.run_file_crossowner as crossowner

    original = capture._capture_files
    fired = []

    def patched(*args, **kwargs):
        inner_open = kwargs["open_source"]

        @contextmanager
        def opened(index, current, cancelled):
            with inner_open(index, current, cancelled) as chunks:
                yield chunks
            # The stream is closed and no platform writer is held: a concurrent
            # change commits HERE, strictly after the final source read and
            # strictly before the publication fence is taken.
            fired.append(index)
            action()

        kwargs["open_source"] = opened
        return original(*args, **kwargs)

    monkeypatch.setattr(capture, "_capture_files", patched)
    monkeypatch.setattr(crossowner, "_capture_files", patched)
    return fired


def test_sender_grant_revoked_after_the_last_read_publishes_nothing(node_env, monkeypatch):
    """Publication revalidates the SENDER's authority, not only the receiver's.

    A grant revoked after the final streamed read must stop the bytes from ever
    becoming receiver-owned custody -- refusing later at acceptance is too late,
    because the receiver would already hold a usable copy.
    """
    from tinyassets.daemon_server import revoke_universe_access

    base, auth, _, _, branch, _ = node_env
    _, link = receiver_file_link(base, auth)
    _, refs = sender_custody(base, [b"revoked before publication"])
    run_id = running_sender_run(base, branch, refs)
    fired = _hook_after_last_read(monkeypatch, lambda: revoke_universe_access(
        base, universe_id=SENDER[1], actor_id=SENDER[0],
    ))

    with pytest.raises(store.FileCustodyRefused) as caught:
        deliver(base, branch, link, {"result": refs[0]}, run_id)
    assert fired == [0], "the revoke must land after the read, or this proves nothing"
    assert "run_file_access_denied" in str(caught.value)

    # No usable receiver copy exists in ANY form: no custody object, no binding,
    # no delivery, and nothing to read.
    assert custody_rows(base, RECEIVER) == []
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT COUNT(*) FROM graph_deliveries").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM graph_delivery_files").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM run_file_bindings b JOIN runs r USING(run_id) "
            "WHERE r.owner_user_id=?", (RECEIVER[0],),
        ).fetchone()[0] == 0


def test_the_same_delivery_succeeds_when_the_grant_is_left_alone(node_env, monkeypatch):
    """Mutation control: the hook itself must not be what refuses.

    Identical wiring, no revoke -- so the refusal above is attributable to the
    revoked grant and to nothing about the instrumentation.
    """
    base, auth, _, _, branch, _ = node_env
    _, link = receiver_file_link(base, auth)
    body = b"grant left alone"
    _, refs = sender_custody(base, [body])
    run_id = running_sender_run(base, branch, refs)
    fired = _hook_after_last_read(monkeypatch, lambda: None)

    receipt = deliver(base, branch, link, {"result": refs[0]}, run_id)
    assert fired == [0]
    run = receiver_run_id(base, receipt["delivery_id"])
    assert read_all(base, run, transfer_rows(base, receipt["delivery_id"])[0]
                    ["receiver_file_id"]) == body


def test_source_binding_released_after_the_copy_refuses_at_acceptance(node_env, monkeypatch):
    """Acceptance freshly resolves the sender bindings in its own transaction.

    The copy runs above every acceptance fence, so the sender can still change
    underneath it. Acceptance is the last moment a refusal costs the receiver
    nothing, and it must not create a delivery on a vanished source binding.
    """
    import tinyassets.run_file_crossowner as crossowner

    base, auth, _, _, branch, _ = node_env
    _, link = receiver_file_link(base, auth)
    _, refs = sender_custody(base, [b"unbound after the copy"])
    run_id = running_sender_run(base, branch, refs)
    original = crossowner.copy_owned_custody_file
    fired = []

    def copying(*args, **kwargs):
        copies = original(*args, **kwargs)
        # The publication fence has already passed and its writers are released:
        # acceptance is now the only remaining checkpoint.
        with runs._connect(base) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM run_file_bindings WHERE run_id=?", (run_id,))
        fired.append(True)
        return copies

    monkeypatch.setattr(crossowner, "copy_owned_custody_file", copying)
    with pytest.raises(store.FileCustodyRefused) as caught:
        deliver(base, branch, link, {"result": refs[0]}, run_id)
    assert fired == [True], "the copy must have completed, or this proves nothing"
    assert "run_file_not_found" in str(caught.value)
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT COUNT(*) FROM graph_deliveries").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM graph_delivery_files").fetchone()[0] == 0


def test_sender_account_erasure_leaves_the_receiver_its_bytes(node_env):
    """Real erasure, not a target-list assertion: run the deletion and measure.

    The sender's custody rows and physical bytes go; the receiver's accepted copy,
    its binding and its file on disk stay readable. Provenance rows are removed
    ahead of their parent under enforced foreign keys.
    """
    from tinyassets import account_deletion

    base, auth, _, _, branch, _ = node_env
    _, link = receiver_file_link(base, auth)
    body = b"receiver keeps this after the sender is gone"
    _, refs = sender_custody(base, [body])
    run_id = running_sender_run(base, branch, refs)
    receipt = deliver(base, branch, link, {"result": refs[0]}, run_id)
    run = receiver_run_id(base, receipt["delivery_id"])
    receiver_file = transfer_rows(base, receipt["delivery_id"])[0]["receiver_file_id"]
    sender_blob = base / ".run-file-custody" / (custody_rows(base, SENDER)[0]["storage_key"]
                                                + ".body")
    receiver_blob = base / ".run-file-custody" / (custody_rows(base, RECEIVER)[0]["storage_key"]
                                                  + ".body")
    assert sender_blob.exists() and receiver_blob.exists()

    # Erasure settles owned custody first, so the sender's run must not be live.
    runs.update_run_status(base, run_id, status="completed")
    account_deletion.write_tombstone(base, SENDER[0])
    counts = {}
    account_deletion._delete_satellite_rows(
        runs.runs_db_path(base), principal=SENDER[0], home=SENDER[1],
        counts=counts, label="runs",
    )

    assert custody_rows(base, SENDER) == []
    assert not sender_blob.exists()
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT COUNT(*) FROM graph_deliveries").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM graph_delivery_files").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert counts.get("runs:graph_delivery_files") == 1

    # The receiver still owns and can read its copy through its own run binding.
    assert [row["file_id"] for row in custody_rows(base, RECEIVER)] == [receiver_file]
    assert receiver_blob.read_bytes() == body
    assert read_all(base, run, receiver_file) == body
