"""The founder's 24/7 shape: a background run delivers to an OPEN receiver.

The intersection two existing suites cover only separately. `test_delivery_node_rpc`
proves the in-node path needs no request identity, but its sender is ENUMERATED in
`allowed_senders`. `test_open_receivers` proves `open_to_all` admits a stranger, but
every one of its sends carries an authenticated request identity. Neither drives
both at once, which is exactly the shape the founder asked for: universes run in
the cloud with nobody signed in, and the 24/7 loop is a user-built node.

So this module drives `deliver_node_output` under `identity_context(None)`, from a
principal that is not in `allowed_senders`, to a receiver whose owner opened it --
and asserts the attribution lands in the receiving owner's run inputs.
"""
# ruff: noqa: F811 -- pytest resolves imported fixtures by their public names

from __future__ import annotations

import json

import pytest

from tests.test_open_receivers import _seed_attributed
from tests.test_receiver_links import env  # noqa: F401
from tinyassets import runs
from tinyassets import universe_server as server
from tinyassets.api import deliveries as api
from tinyassets.auth.middleware import identity_context
from tinyassets.branches import BranchDefinition
from tinyassets.daemon_server import get_branch_definition
from tinyassets.storage import deliveries

STRANGER = ("outsider", "u-outsider")


@pytest.fixture
def offline_env(env, monkeypatch):
    """Two principals sharing no ACL, and no receiver worker.

    `dispatch_accepted_delivery` is stubbed because this module asks what
    ACCEPTANCE recorded, not what the receiver's graph then did -- there is no
    provider bound here. The stub is the same seam `test_delivery_node_rpc` uses.
    """
    base, authenticate = env

    def auth(owner):
        authenticate(owner, capabilities=[
            "tinyassets.extensions.read", "tinyassets.extensions.write",
            "tinyassets.extensions.costly",
        ])

    _seed_attributed(base)
    dispatched = []
    monkeypatch.setattr(api.delivery_runtime, "dispatch_accepted_delivery",
                        lambda *args, **kwargs: dispatched.append(kwargs))
    return base, auth, dispatched


def _receiver(auth, *, open_to_all):
    auth("receiver")
    created = json.loads(server.write_graph(
        target="receiver", operation="create", graph_id="u-receiver",
        payload_json=json.dumps({
            "branch_def_id": "b-receiver", "node_id": "entry", "input_keys": ["topic"],
            # Deliberately EMPTY: the stranger is admitted by the owner's exposure
            # choice alone, never by an entry naming it.
            "allowed_senders": [], "open_to_all": open_to_all,
            "description": "open to anyone",
        }),
    ))
    assert created.get("open_to_all") is open_to_all, created
    assert created["allowed_senders"] == []
    return created


def _link(auth, receiver):
    auth(STRANGER[0])
    link = json.loads(server.write_graph(
        target="output_link", operation="connect", graph_id=STRANGER[1],
        payload_json=json.dumps({
            "branch_def_id": "b-outsider", "node_id": "entry",
            "receiver_id": receiver["receiver_id"],
            "expected_generation": receiver["generation"],
            "mapping": {"result": "topic"},
        }),
    ))
    return link


def _running_background_run(base):
    """A run owned by the stranger with NO request behind it -- a scheduled shape.

    `actor` is `universe:<id>` exactly as `automations` sets it
    (`tinyassets/automations.py` `execute_branch_async(actor=f"universe:{...}")`),
    while the delivery principal is the run's `owner_user_id`. Those differing is
    the caveat this test also pins.
    """
    branch = BranchDefinition.from_dict(get_branch_definition(base, branch_def_id="b-outsider"))
    run_id = runs._prepare_run(
        base, branch=branch, inputs={}, run_name="automation:nightly",
        actor=f"universe:{STRANGER[1]}", owner_user_id=STRANGER[0],
        queue_universe_id=STRANGER[1],
    )
    runs.update_run_status(base, run_id, status="running")
    return branch, run_id


def _source(branch, run_id):
    return api.NodeDeliverySource(
        owner_user_id=STRANGER[0], universe_id=STRANGER[1],
        actor=f"universe:{STRANGER[1]}", run_id=run_id,
        branch_def_id=branch.branch_def_id, node_id="entry",
        output_keys=tuple(branch.node_defs[0].output_keys),
    )


def _deliver_with_no_session(base, branch, run_id, link, *, occurrence="nightly-1"):
    # The whole point: no request identity exists on this thread, as on a
    # scheduled/webhook execution thread in production.
    with identity_context(None):
        return api.deliver_node_output(
            base, source=_source(branch, run_id), link_id=link["link_id"],
            occurrence_id=occurrence, outputs={"result": "filed while nobody was signed in"},
            should_cancel=lambda: False,
        )


def test_a_background_run_delivers_to_an_open_receiver_with_nobody_signed_in(offline_env):
    base, auth, dispatched = offline_env
    receiver = _receiver(auth, open_to_all=True)
    link = _link(auth, receiver)
    assert "link_id" in link, link
    branch, run_id = _running_background_run(base)

    receipt = _deliver_with_no_session(base, branch, run_id, link)
    assert "delivery_id" in receipt, receipt
    assert receipt["receiver_id"] == receiver["receiver_id"]

    with deliveries.transaction(base) as conn:
        row = dict(conn.execute("SELECT * FROM graph_deliveries").fetchone())
        attempt = dict(conn.execute(
            "SELECT * FROM graph_delivery_attempts WHERE delivery_id=?",
            (row["delivery_id"],),
        ).fetchone())
        receiver_run = dict(conn.execute(
            "SELECT * FROM runs WHERE run_id=?", (attempt["run_id"],),
        ).fetchone())
    # The delivery is attributed to the run's OWNER, and sourced to its run.
    assert (row["sender_id"], row["sender_universe_id"]) == STRANGER
    assert row["source_run_id"] == run_id
    assert row["receiver_owner_id"] == "receiver"

    # The artefact the owner's graph reads: the receiving RUN's own inputs.
    inputs = json.loads(receiver_run["inputs_json"])
    assert inputs["delivery_sender_id"] == STRANGER[0]
    assert inputs["delivery_sender_universe_id"] == STRANGER[1]
    assert inputs["topic"] == "filed while nobody was signed in"
    # And the receiving run belongs to the receiver, not the sender.
    assert receiver_run["owner_user_id"] == "receiver"
    assert receiver_run["actor"] == "universe:u-receiver"
    assert len(dispatched) == 1


def test_the_owners_exposure_choice_is_what_admitted_it(offline_env):
    """Control for the test above: identical call, receiver never opened.

    Without this the passing test proves only "a background delivery works", which
    is already covered elsewhere -- it would not show that `open_to_all` is what
    let a non-enumerated principal through.
    """
    base, auth, dispatched = offline_env
    closed = _receiver(auth, open_to_all=False)
    auth(STRANGER[0])
    refused_link = json.loads(server.write_graph(
        target="output_link", operation="connect", graph_id=STRANGER[1],
        payload_json=json.dumps({
            "branch_def_id": "b-outsider", "node_id": "entry",
            "receiver_id": closed["receiver_id"],
            "expected_generation": closed["generation"], "mapping": {"result": "topic"},
        }),
    ))
    # A closed receiver cannot even be connected to, so there is no link to send on.
    assert refused_link["error"] == "receiver_or_link_not_found", refused_link
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_output_links").fetchone()[0] == 0
    assert dispatched == []


def test_closing_the_receiver_stops_the_background_sender_at_acceptance(offline_env):
    """Exposure is revocable against a link that already exists, with no session."""
    base, auth, dispatched = offline_env
    receiver = _receiver(auth, open_to_all=True)
    link = _link(auth, receiver)
    branch, run_id = _running_background_run(base)
    assert "delivery_id" in _deliver_with_no_session(base, branch, run_id, link)

    # Clear the flag WITHOUT a generation bump: any update bumps the generation and
    # would invalidate the link on its own, which would prove the wrong thing.
    from tinyassets.storage import receiver_links as store

    with store.transaction(base) as conn:
        conn.execute("UPDATE graph_receivers SET open_to_all=0 WHERE receiver_id=?",
                     (receiver["receiver_id"],))
    with pytest.raises(PermissionError, match="receiver_or_link_not_found"):
        _deliver_with_no_session(base, branch, run_id, link, occurrence="nightly-2")
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_deliveries").fetchone()[0] == 1
    assert len(dispatched) == 1
