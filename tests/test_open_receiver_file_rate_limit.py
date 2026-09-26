"""A rate-limited sender copies no bytes into the receiving owner's storage.

Separate module because it needs the real file-delivery rig: sender-owned custody
captured from real authoring handles, a running sender run those files are bound
to, and the in-node RPC entry (`deliver_node_output`) that is the only caller able
to move bytes. Nothing is stubbed -- the custody copy runs for real when it runs.

Why it exists: the cross-family review of PR #4018 found that `_transfer_files`
runs ABOVE every acceptance fence, so the acceptance-time per-sender rate check
could not stop a sender from varying occurrence ids and causing copy after copy
that acceptance then refused, leaving the committed custody objects behind. The
check now also runs inside the copy's own pre-flight transaction, and this is the
test that it does.
"""
# ruff: noqa: F811 -- pytest resolves imported fixtures by their public names
import json

import pytest

from tests.test_delivery_file_transfer import (  # noqa: F401
    custody_capacity,
    deliver,
    running_sender_run,
    sender_custody,
)
from tests.test_delivery_node_rpc import _prepare, _source, node_env  # noqa: F401
from tests.test_delivery_public import linked  # noqa: F401
from tests.test_receiver_links import env  # noqa: F401
from tinyassets import universe_server as server
from tinyassets.branches import BranchDefinition
from tinyassets.daemon_server import get_branch_definition, save_branch_definition
from tinyassets.storage import deliveries, run_files


def _receiver_owned_objects(base):
    """Custody objects the RECEIVER owns -- the artefact a refused copy must not leave."""
    with deliveries.transaction(base) as conn:
        for statement in run_files._SCHEMA:
            conn.execute(statement)
        return conn.execute(
            "SELECT count(*) FROM run_file_objects WHERE owner_id=? AND universe_id=?",
            ("receiver", "u-receiver"),
        ).fetchone()[0]


def _file_receiver(base, auth, *, sender_rate_limit):
    """A receiver declaring one file input, with the owner's per-sender limit set."""
    auth("receiver")
    branch = BranchDefinition.from_dict(get_branch_definition(base, branch_def_id="b-receiver"))
    definition = branch.to_dict()
    definition["state_schema"] = [
        {**field, "type": "dict"} if field.get("name") == "topic" else field
        for field in branch.state_schema
    ]
    definition["io_manifest"] = {"inputs": [
        {"name": "topic", "io_type": "file", "max_count": 1, "max_bytes": 1 << 20},
    ]}
    save_branch_definition(base, branch_def=definition)
    receiver = json.loads(server.write_graph(
        target="receiver", operation="create", graph_id="u-receiver",
        payload_json=json.dumps({
            "branch_def_id": "b-receiver", "node_id": "entry", "input_keys": ["topic"],
            "allowed_senders": ["sender"], "sender_rate_limit": sender_rate_limit,
        }),
    ))
    assert receiver.get("sender_rate_limit") == sender_rate_limit, receiver
    auth("sender")
    link = json.loads(server.write_graph(
        target="output_link", operation="connect", graph_id="u-sender",
        payload_json=json.dumps({
            "branch_def_id": "b-sender", "node_id": "entry",
            "receiver_id": receiver["receiver_id"],
            "expected_generation": receiver["generation"],
            "mapping": {"result": "topic"},
        }),
    ))
    assert "link_id" in link, link
    return BranchDefinition.from_dict(definition), link


def test_a_rate_limited_sender_copies_no_bytes_into_the_receivers_storage(env):
    base, authenticate = env

    def auth(owner):
        authenticate(owner, capabilities=[
            "tinyassets.extensions.read", "tinyassets.extensions.write",
            "tinyassets.extensions.costly",
        ])

    _, link = _file_receiver(base, auth, sender_rate_limit=1)
    auth("sender")
    sender_branch = BranchDefinition.from_dict(
        get_branch_definition(base, branch_def_id="b-sender")
    )
    _, refs = sender_custody(base, [b"first body", b"second body"])
    run_id = running_sender_run(base, sender_branch, refs)

    accepted = deliver(base, sender_branch, link, {"result": refs[0]}, run_id,
                       occurrence="one")
    assert "delivery_id" in accepted, accepted
    after_accept = _receiver_owned_objects(base)
    assert after_accept == 1, "the accepted delivery must own exactly its own copy"

    # Same sender, NEW occurrence id, now past the owner's limit. The refusal has to
    # land before the copy, not after it.
    with pytest.raises(ValueError, match="receiver_sender_rate_limit_exceeded"):
        deliver(base, sender_branch, link, {"result": refs[1]}, run_id, occurrence="two")
    assert _receiver_owned_objects(base) == after_accept, (
        "a refused sender left a receiver-owned custody object behind"
    )
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_deliveries").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM graph_delivery_files").fetchone()[0] == 1

    # A RETRY of the accepted occurrence is not new usage, and must still replay
    # rather than being refused or copying a second time.
    replay = deliver(base, sender_branch, link, {"result": refs[0]}, run_id,
                     occurrence="one")
    assert replay["delivery_id"] == accepted["delivery_id"], replay
    assert _receiver_owned_objects(base) == after_accept
