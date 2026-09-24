"""Receiver-declared file positions must gate acceptance, not just execution.

The runtime already refuses a sender reference that survives into ``inputs_json``
(``receiver_file_inputs``), but that is a dispatch-time refusal: by then the
occurrence is accepted, a receiver run is reserved and the sender's ``file_id``
is persisted in receiver-owned inputs. What is pinned here is the same boundary
one phase earlier -- before any allocation, copy or acceptance -- for the case
the existing bridge tests could not reach, where the receiver's contract type
happens to admit a dict and so no type mismatch is raised.
"""
# ruff: noqa: F811 -- imported pytest fixtures
import json

import pytest

from tests.test_delivery_file_bridge import REFERENCE, _declare_receiver_file, _send
from tests.test_delivery_node_rpc import node_env  # noqa: F401
from tests.test_delivery_public import linked  # noqa: F401
from tests.test_receiver_links import env  # noqa: F401
from tinyassets import universe_server as server
from tinyassets.branches import BranchDefinition
from tinyassets.daemon_server import get_branch_definition, save_branch_definition
from tinyassets.storage import deliveries


def _receiver_branch(base, *, types, manifest=None):
    """Retype the receiver's OWN state fields, optionally declaring a file input."""
    definition = BranchDefinition.from_dict(
        get_branch_definition(base, branch_def_id="b-receiver")
    ).to_dict()
    definition["state_schema"] = [
        {**field, "type": types.get(field["name"], field["type"])}
        for field in definition["state_schema"]
    ]
    if manifest is None:
        definition.pop("io_manifest", None)
    else:
        definition["io_manifest"] = manifest
    save_branch_definition(base, branch_def=definition)
    return definition


def _link_receiver(auth, input_keys, mapping):
    """Create the receiver and the sender's link against the admitted snapshot.

    Each side acts as itself: the receiver exposes its own branch, the sender
    connects. The admitted snapshot is taken here, so a later branch edit is not
    what these tests are exercising.
    """
    auth("receiver")
    receiver = json.loads(server.write_graph(
        target="receiver", operation="create", graph_id="u-receiver",
        payload_json=json.dumps({"branch_def_id": "b-receiver", "node_id": "entry",
                                 "input_keys": input_keys, "allowed_senders": ["sender"]}),
    ))
    assert "receiver_id" in receiver, receiver
    auth("sender")
    link = json.loads(server.write_graph(
        target="output_link", operation="connect", graph_id="u-sender",
        payload_json=json.dumps({"branch_def_id": "b-sender", "node_id": "entry",
                                 "receiver_id": receiver["receiver_id"],
                                 "expected_generation": receiver["generation"],
                                 "mapping": mapping}),
    ))
    assert "link_id" in link, link
    return link


def _nothing_allocated(base):
    """No delivery, no attempt, and no custody row anywhere it could be written."""
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT COUNT(*) FROM graph_deliveries").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM graph_delivery_attempts").fetchone()[0] == 0
        for table in ("graph_delivery_files", "run_file_operations",
                      "run_file_allocations", "run_file_objects"):
            existing = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,),
            ).fetchone()[0]
            assert existing == 0 or conn.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608 -- fixed literal names
            ).fetchone()[0] == 0


@pytest.mark.parametrize("nested", [False, True])
def test_plain_json_input_cannot_accept_a_sender_file_reference(node_env, nested):
    """A dict contract field is an ordinary JSON position, not a file position.

    Type alone can never grant custody: the receiver declares no file input, so
    the reference is refused whether it arrives as the whole mapped value or
    buried in an ordinary object the contract type happily admits.
    """
    base, auth, _, _, branch, dispatched = node_env
    auth("receiver")
    _receiver_branch(base, types={"topic": "dict"})
    link = _link_receiver(auth, ["topic"], {"result": "topic"})
    value = {"attachment": REFERENCE} if nested else REFERENCE
    with pytest.raises(ValueError):
        _send(base, branch, link, {"result": value})
    assert dispatched == []
    _nothing_allocated(base)


def test_one_declared_file_does_not_open_the_other_mapped_fields(node_env):
    """Mixed payload: consent for `topic` is not consent for `extra`.

    The valid half would otherwise reach the copy phase, so this pins that a
    reference in an undeclared position refuses the WHOLE occurrence before any
    allocation -- not per-field, and not after the bytes are already moved.
    """
    base, auth, _, _, branch, dispatched = node_env
    auth("receiver")
    _receiver_branch(
        base, types={"topic": "dict", "extra": "dict"},
        manifest={"inputs": [
            {"name": "topic", "io_type": "file", "max_count": 1, "max_bytes": 1024},
        ]},
    )
    link = _link_receiver(auth, ["topic", "extra"], {"result": "topic", "receipts": "extra"})
    with pytest.raises(ValueError) as caught:
        _send(base, branch, link, {"result": REFERENCE, "receipts": {"attach": REFERENCE}})
    assert "delivery_file_transfer_not_implemented" in str(caught.value), caught.value
    assert dispatched == []
    _nothing_allocated(base)


def test_ordinary_json_including_key_and_token_fields_still_delivers(node_env):
    """Positive control: the guard is about reference envelopes, not key names.

    Structured user data -- nested objects, lists, fields literally named `key`
    and `token` -- stays exact data through an undeclared dict position.
    """
    base, auth, _, _, branch, dispatched = node_env
    auth("receiver")
    _receiver_branch(base, types={"topic": "dict"})
    link = _link_receiver(auth, ["topic"], {"result": "topic"})
    payload = {"key": "not a secret", "token": "ordinary 🍉", "version": 1,
               "items": [{"filename": "brief.txt", "size_bytes": 11}]}
    receipt = _send(base, branch, link, {"result": payload})
    assert "delivery_id" in receipt, receipt
    assert len(dispatched) == 1
    with deliveries.transaction(base) as conn:
        row = conn.execute("SELECT * FROM graph_deliveries").fetchone()
        assert json.loads(row["inputs_json"]) == {"topic": payload}
        assert conn.execute("SELECT COUNT(*) FROM graph_delivery_files").fetchone()[0] == 0


def test_a_declared_file_position_still_accepts_its_own_reference(node_env):
    """The declared path is untouched: it fails on OWNERSHIP, never on position."""
    base, auth, _, _, branch, _ = node_env
    _, link = _declare_receiver_file(base, auth)
    with pytest.raises(Exception) as caught:
        _send(base, branch, link, {"result": REFERENCE})
    assert "run_file_not_found" in str(caught.value), caught.value
    _nothing_allocated(base)
