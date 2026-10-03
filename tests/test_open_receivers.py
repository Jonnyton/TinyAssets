"""An owner opens one of their steps to ANY authenticated user, and is told who sent.

Drives the real canonical handles with two independently authenticated principals
who share no ACL: ``receiver`` owns the exposed step, ``outsider`` is a stranger
never named in ``allowed_senders``. Only the external provider is a double.

Why this exists: on 2026-09-26 a founder asked their universe, as a naive user, for
"a node that any user's universe can send to directly". The primitive could not
express it -- ``allowed_senders`` had to enumerate principals and empty meant
nobody -- so the agent minted a public webhook and published the URL, which is
anonymous content attached to no universe. These tests pin the three things that
were missing: opening, finding, and attribution.
"""
# ruff: noqa: F811 -- pytest resolves imported fixtures by parameter name

from __future__ import annotations

import json

import pytest

from tests.test_delivery_runtime import provider_probe  # noqa: F401
from tests.test_receiver_links import env  # noqa: F401
from tinyassets import runs
from tinyassets import universe_server as server
from tinyassets.branches import BranchDefinition, EdgeDefinition, GraphNodeRef, NodeDefinition
from tinyassets.daemon_server import save_branch_definition
from tinyassets.storage import deliveries
from tinyassets.storage import receiver_links as store


#: The receiving branch DECLARES both reserved attribution fields and its node
#: renders them into the prompt.
#:
#: ``defaults=True`` (the default here) gives each field a ``default_value``, which
#: matters for mutation sensitivity: a missing injection then produces a prompt
#: carrying the placeholder rather than a required-input refusal, so the assertion
#: that catches it is the rendered prompt itself and not an incidental preflight.
#: ``defaults=False`` is the handbook's exact declaration, which is the shape a real
#: agent will write -- see the test that uses it.
def _attributed_schema(defaults=True):
    attribution = [{"name": name, "type": "str"} for name in
                   ("delivery_sender_id", "delivery_sender_universe_id")]
    if defaults:
        for field, placeholder in zip(attribution, ("nobody", "nowhere")):
            field["default_value"] = placeholder
    return [
        {"name": "topic", "type": "str", "description": "Incoming topic"},
        *attribution,
        {"name": "result", "type": "str"},
        {"name": "extra", "type": "str"},
    ]


def _seed_attributed(base, defaults=True):
    """Re-save b-receiver so its node actually READS who sent the deliverable."""
    branch = BranchDefinition(
        branch_def_id="b-receiver",
        name="Private graph",
        author="receiver",
        visibility="private",
        node_defs=[
            NodeDefinition(
                node_id="definition",
                display_name="private node name",
                prompt_template=(
                    "private prompt {topic} from {delivery_sender_id} "
                    "at {delivery_sender_universe_id}"
                ),
                input_keys=["topic", "delivery_sender_id", "delivery_sender_universe_id"],
                output_keys=["result", "extra"],
            )
        ],
        graph_nodes=[GraphNodeRef(id="entry", node_def_id="definition")],
        edges=[EdgeDefinition("START", "entry"), EdgeDefinition("entry", "END")],
        entry_point="entry",
        state_schema=_attributed_schema(defaults),
    )
    save_branch_definition(base, branch_def=branch.to_dict())


@pytest.fixture
def two_users(env):
    base, authenticate = env

    def auth(owner):
        authenticate(owner, capabilities=[
            "tinyassets.extensions.read", "tinyassets.extensions.write",
            "tinyassets.extensions.costly",
        ])

    _seed_attributed(base)
    return base, auth


def _create(operation="create", **payload):
    args = {
        "branch_def_id": "b-receiver", "node_id": "entry",
        "input_keys": ["topic"], "allowed_senders": [], "description": "Send a topic",
    }
    args.update(payload)
    return json.loads(server.write_graph(
        target="receiver", operation=operation, graph_id="u-receiver",
        payload_json=json.dumps(args),
    ))


def _connect(receiver, *, graph="u-outsider", branch="b-outsider"):
    return json.loads(server.write_graph(
        target="output_link", operation="connect", graph_id=graph,
        payload_json=json.dumps({
            "branch_def_id": branch, "node_id": "entry",
            "receiver_id": receiver["receiver_id"],
            "expected_generation": receiver["generation"],
            "mapping": {"result": "topic"},
        }),
    ))


def _send(link, value="from a stranger 🍉", *, occurrence="one", graph="u-outsider"):
    return json.loads(server.run_graph(
        operation="deliver_output", graph_id=graph,
        inputs_json=json.dumps({
            "link_id": link["link_id"], "occurrence_id": occurrence,
            "outputs": {"result": value},
        }),
    ))


def _discover(graph, query=""):
    return json.loads(server.read_graph(target="receivers", graph_id=graph, query=query))


# ---------------------------------------------------------------------------
# Opening it
# ---------------------------------------------------------------------------


def test_an_opened_receiver_accepts_a_stranger_and_the_owner_sees_who_sent(
    two_users, provider_probe,
):
    """The whole ask in one flow: open, a stranger finds it, sends, owner is told who."""
    base, auth = two_users
    auth("receiver")
    receiver = _create(open_to_all=True, discoverable=True,
                       description="Accepts a topic from anyone")
    assert receiver["open_to_all"] is True
    assert receiver["allowed_senders"] == [], "opening is not an entry in the ACL"

    auth("outsider")
    # The stranger learns the id from discovery, not from being told it.
    found = _discover("u-outsider", query="anyone")["receivers"]
    assert [row["receiver_id"] for row in found] == [receiver["receiver_id"]]
    link = _connect(found[0])
    assert "link_id" in link, link
    sent = _send(link)
    assert "delivery_id" in sent, sent

    auth("receiver")
    own = json.loads(server.read_graph(
        target="delivery", graph_id="u-receiver", query=sent["delivery_id"],
    ))
    # Attribution on the receipt: the record always had it, nothing returned it.
    assert own["sender_id"] == "outsider"
    assert own["sender_universe_id"] == "u-outsider"
    runs.wait_for(own["run_id"], timeout=10)

    # Attribution in the RUN the owner's step executed -- the artefact, not the
    # absence of one: the rendered prompt the provider was called with.
    assert len(provider_probe) == 1
    assert "from outsider at u-outsider" in provider_probe[0]
    with deliveries.transaction(base) as conn:
        stored = json.loads(conn.execute(
            "SELECT inputs_json FROM runs WHERE run_id=?", (own["run_id"],),
        ).fetchone()[0])
    assert stored["delivery_sender_id"] == "outsider"
    assert stored["delivery_sender_universe_id"] == "u-outsider"
    assert stored["topic"] == "from a stranger 🍉"


def test_a_receiver_that_was_never_opened_refuses_a_stranger_and_is_not_findable(
    two_users, provider_probe,
):
    """The closed default, from the stranger's side: invisible and unreachable."""
    base, auth = two_users
    auth("receiver")
    closed = _create(description="Accepts a topic from anyone")
    assert closed["open_to_all"] is False
    assert closed["discoverable"] is False

    auth("outsider")
    assert _discover("u-outsider")["receivers"] == []
    assert _discover("u-outsider", query="anyone")["receivers"] == []
    # Not inspectable by id either, even holding the exact id.
    assert json.loads(server.read_graph(
        target="receiver", graph_id="u-outsider", query=closed["receiver_id"],
    ))["error"]
    assert _connect(closed)["error"]
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_output_links").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM graph_deliveries").fetchone()[0] == 0
    assert provider_probe == []


def test_closing_an_open_receiver_stops_a_sender_who_already_connected(
    two_users, provider_probe,
):
    """Exposure is revocable mid-flight: acceptance rechecks, not just connect."""
    base, auth = two_users
    auth("receiver")
    receiver = _create(open_to_all=True, discoverable=True, sender_rate_limit=3)
    auth("outsider")
    link = _connect(receiver)
    assert "link_id" in link, link

    auth("outsider")
    assert "delivery_id" in _send(link, occurrence="before-any-edit")

    auth("receiver")
    # An unrelated edit KEEPS the exposure declaration. It must not silently close
    # the receiver, and it must not reset a tightened rate limit back to the default
    # -- that would silently LOOSEN a bound the owner chose.
    edited = _create("update", receiver_id=receiver["receiver_id"],
                     expected_generation=1, description="same terms, new words")
    assert edited["generation"] == 2, edited
    assert (edited["open_to_all"], edited["discoverable"]) == (True, True)
    assert edited["sender_rate_limit"] == 3

    # Closing is an EXPLICIT false, never an omission.
    closed = _create("update", receiver_id=receiver["receiver_id"], expected_generation=2,
                     open_to_all=False, discoverable=False)
    assert closed["generation"] == 3, closed
    assert (closed["open_to_all"], closed["discoverable"]) == (False, False)
    auth("outsider")
    assert _discover("u-outsider")["receivers"] == []

    # And the gate is rechecked at ACCEPTANCE, not only at connect. Any update bumps
    # the generation, which invalidates a sender's link on its own, so proving the
    # gate itself needs the flag cleared WITHOUT a generation change -- otherwise
    # `receiver_generation_changed` would be the only thing this observed.
    auth("receiver")
    reopened = _create("update", receiver_id=receiver["receiver_id"],
                       expected_generation=3, open_to_all=True)
    auth("outsider")
    fresh = _connect(reopened)
    assert "link_id" in fresh, fresh
    with store.transaction(base) as conn:
        conn.execute(
            "UPDATE graph_receivers SET open_to_all=0 WHERE receiver_id=?",
            (receiver["receiver_id"],),
        )
    assert _send(fresh, occurrence="after-closing")["error"]
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_deliveries").fetchone()[0] == 1
    assert len(provider_probe) <= 1


@pytest.mark.parametrize("payload", [
    {"open_to_all": "true"},
    {"open_to_all": 1},
    {"discoverable": "false"},
    {"discoverable": 0},
    {"sender_rate_limit": -1},
    {"sender_rate_limit": True},
    {"sender_rate_limit": "60"},
    {"allowed_senders": ["*"]},
])
def test_a_near_miss_exposure_value_is_refused_not_coerced(two_users, payload):
    """A truthy string must never open a private node, and "*" is still not a name.

    `"false"` is refused too: an owner who meant to close something is told their
    value was not understood, rather than having it read as the closed default and
    appearing to have worked. `sender_rate_limit` accepts 0 now -- that is its
    default and means "no policy" -- so the near-miss for it is a negative number.
    """
    _, auth = two_users
    auth("receiver")
    response = _create(**payload)
    assert response["error"] == "invalid_delivery_request", response


def test_an_omitted_exposure_field_means_keep_not_close(two_users):
    """The sentinel's definition: null/absent is "unspecified", never "closed"."""
    _, auth = two_users
    auth("receiver")
    # Absent on create -> the private default.
    created = _create(sender_rate_limit=5)
    assert (created["open_to_all"], created["discoverable"]) == (False, False)
    assert created["sender_rate_limit"] == 5
    opened = _create("update", receiver_id=created["receiver_id"], expected_generation=1,
                     open_to_all=True, discoverable=True)
    # Explicit null on update -> keep, for every one of the three.
    kept = _create("update", receiver_id=created["receiver_id"], expected_generation=2,
                   open_to_all=None, discoverable=None, sender_rate_limit=None)
    assert (kept["open_to_all"], kept["discoverable"]) == (True, True)
    assert kept["sender_rate_limit"] == 5
    assert opened["generation"] == 2 and kept["generation"] == 3


def test_a_new_receiver_has_no_platform_sender_rate_limit(two_users):
    """The platform default of 60/hour is gone, and there is no ceiling.

    Founder, 2026-09-30: an account's only limits are cloud storage and concurrent
    agent seats. A per-sender bound on someone's own receiver is THEIR policy, off
    unless they set it. The old justification -- a stranger spending the owner's
    run admission budget -- described a budget that no longer exists; a delivered
    run queues for one of the owner's seats instead.
    """
    _, auth = two_users
    auth("receiver")
    created = _create(open_to_all=True)
    assert created["sender_rate_limit"] == store.NO_SENDER_RATE_LIMIT == 0
    assert not hasattr(store, "DEFAULT_SENDER_RATE_LIMIT")
    assert not hasattr(store, "MAX_SENDER_RATE_LIMIT")

    # No ceiling: a number far past the old 100_000 is accepted as-is.
    raised = _create("update", receiver_id=created["receiver_id"],
                     expected_generation=1, sender_rate_limit=10_000_000)
    assert raised["sender_rate_limit"] == 10_000_000
    # And it can be turned back off explicitly.
    off = _create("update", receiver_id=created["receiver_id"],
                  expected_generation=2, sender_rate_limit=0)
    assert off["sender_rate_limit"] == 0


def test_with_no_owner_policy_a_sender_is_never_rate_refused(two_users):
    """Past the old 60/hour, every send is accepted on a default receiver."""
    base, auth = two_users
    auth("receiver")
    receiver = _create(open_to_all=True)
    assert receiver["sender_rate_limit"] == 0
    auth("outsider")
    link = _connect(receiver)
    assert "link_id" in link, link
    for i in range(65):
        out = _send(link, occurrence=f"send-{i}")
        assert "delivery_id" in out, out
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_deliveries").fetchone()[0] == 65


def test_an_owner_who_sets_a_policy_still_has_it_enforced(two_users):
    """Removing the platform default must not remove the owner's own ability.

    Mutation-check on the same gate: with a limit of 3 the fourth send is refused
    by name, and the refusal says the limit belongs to the owner.
    """
    _, auth = two_users
    auth("receiver")
    receiver = _create(open_to_all=True, sender_rate_limit=3)
    auth("outsider")
    link = _connect(receiver)
    assert "link_id" in link, link
    for i in range(3):
        assert "delivery_id" in _send(link, occurrence=f"ok-{i}")
    refused = _send(link, occurrence="over")
    assert refused.get("error"), refused
    assert "receiver_sender_rate_limit_exceeded" in str(refused)


# ---------------------------------------------------------------------------
# Finding it
# ---------------------------------------------------------------------------


def test_discovery_lists_only_what_owners_opened_to_discovery(two_users):
    """Three receivers, one visibility rule, and search over description/owner."""
    _, auth = two_users
    auth("receiver")
    listed = _create(discoverable=True, open_to_all=True, description="Bug reports welcome")
    unlisted = _create(discoverable=False, open_to_all=True, description="Bug reports hidden")
    revoked = _create(discoverable=True, open_to_all=True, description="Bug reports retired")
    assert json.loads(server.write_graph(
        target="receiver", operation="revoke", graph_id="u-receiver",
        payload_json=json.dumps({
            "receiver_id": revoked["receiver_id"], "expected_generation": 1,
        }),
    ))["revoked"] is True

    auth("outsider")
    found = _discover("u-outsider", query="bug reports")["receivers"]
    assert [row["receiver_id"] for row in found] == [listed["receiver_id"]]
    # An open-but-unlisted receiver is still deliverable by id -- unlisted is not
    # closed -- it is simply absent from the directory.
    assert json.loads(server.read_graph(
        target="receiver", graph_id="u-outsider", query=unlisted["receiver_id"],
    ))["receiver_id"] == unlisted["receiver_id"]
    assert "link_id" in _connect(unlisted)
    assert _discover("u-outsider", query="no such text")["receivers"] == []


def test_a_discovered_row_carries_the_contract_and_none_of_the_owners_graph(two_users):
    """Sender view only: enough to decide to send, nothing about how it is handled."""
    _, auth = two_users
    auth("receiver")
    receiver = _create(discoverable=True, open_to_all=True, sender_rate_limit=7)
    auth("outsider")
    row = _discover("u-outsider")["receivers"][0]
    assert set(row) == {
        "receiver_id", "owner_id", "generation", "description", "contract",
        "revoked", "open_to_all", "discoverable", "sender_rate_limit",
    }
    assert row["owner_id"] == "receiver"
    assert row["sender_rate_limit"] == 7
    assert row["contract"] == [
        {"name": "topic", "type": "str", "required": True, "description": "Incoming topic"},
    ]
    # Nothing about the owner's universe, workflow, step, other senders or snapshot.
    serialized = json.dumps(row)
    for private in ("u-receiver", "b-receiver", "entry", "private prompt",
                    "private node name", "snapshot", "allowed_senders"):
        assert private not in serialized, private
    assert receiver["receiver_id"] == row["receiver_id"]


def test_discovery_is_attributable_and_bounded(two_users):
    """No anonymous directory read, and the result size is the caller's to bound."""
    _, auth = two_users
    auth("receiver")
    _create(discoverable=True, open_to_all=True)
    # A caller with no authenticated principal at all.
    auth(None)
    assert json.loads(server.read_graph(target="receivers", graph_id="u-outsider"))["error"]
    auth("outsider")
    # A universe the caller does not administer is not a footing to search from.
    assert json.loads(server.read_graph(target="receivers", graph_id="u-receiver"))["error"]
    assert _discover("u-outsider")["receivers"]
    assert store.discover_receivers.__doc__
    with pytest.raises(ValueError, match="limit"):
        store.discover_receivers(".", principal_id="outsider", limit=0)
    with pytest.raises(ValueError, match="limit"):
        store.discover_receivers(".", principal_id="outsider", limit=101)


# ---------------------------------------------------------------------------
# Attribution cannot be forged, and the sender learns nothing
# ---------------------------------------------------------------------------


def test_the_handbook_recipe_works_with_no_default_on_the_attribution_field(
    two_users, provider_probe,
):
    """The chapter's EXACT declaration, which had no `default_value` and did not work.

    `project_receiver_entry` preflights presence using the advertised contract plus
    schema defaults, so a node consuming `delivery_sender_id` could not become a
    receiver at all: the field is neither advertised (refused) nor defaulted. The
    schema used by the other tests here has defaults and hid it. Found by the
    cross-family review, 2026-09-26.
    """
    base, auth = two_users
    _seed_attributed(base, defaults=False)
    auth("receiver")
    receiver = _create(open_to_all=True, discoverable=True)
    assert "receiver_id" in receiver, receiver
    # And the contract still does NOT advertise them.
    assert [field["name"] for field in receiver["contract"]] == ["topic"]
    auth("outsider")
    sent = _send(_connect(receiver))
    assert "delivery_id" in sent, sent
    auth("receiver")
    own = json.loads(server.read_graph(
        target="delivery", graph_id="u-receiver", query=sent["delivery_id"],
    ))
    runs.wait_for(own["run_id"], timeout=10)
    assert "from outsider at u-outsider" in provider_probe[0]


@pytest.mark.parametrize("field", store.SENDER_ATTRIBUTION_FIELDS)
def test_a_legacy_receiver_advertising_an_attribution_field_cannot_receive(
    two_users, provider_probe, field,
):
    """The save-time guard only covers new receivers; acceptance closes the rest.

    A receiver predating the guard could advertise a reserved name, and for a FILE
    field `_run_inputs` would then replace the injected principal with the SENDER's
    own file reference -- forged provenance. Written by reaching past the API to the
    store, which is the only way such a row can exist. Refused loudly at acceptance,
    so the invariant is structural rather than contingent on create-time validation.
    """
    base, auth = two_users
    auth("receiver")
    receiver = _create(open_to_all=True, discoverable=True)
    auth("outsider")
    link = _connect(receiver)
    # Forge the row a pre-guard create could have produced.
    with store.transaction(base) as conn:
        contract = json.loads(conn.execute(
            "SELECT contract_json FROM graph_receivers WHERE receiver_id=?",
            (receiver["receiver_id"],),
        ).fetchone()[0])
        contract.append({"name": field, "type": "dict", "required": False,
                         "description": "legacy"})
        conn.execute(
            "UPDATE graph_receivers SET contract_json=? WHERE receiver_id=?",
            (json.dumps(contract), receiver["receiver_id"]),
        )
    refused = _send(link)
    assert refused["error"] == "invalid_delivery_request", refused
    assert field in refused["detail"]
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_deliveries").fetchone()[0] == 0
    assert provider_probe == []


@pytest.mark.parametrize("field", store.SENDER_ATTRIBUTION_FIELDS)
def test_a_receiver_cannot_advertise_an_attribution_field(two_users, field):
    """Keeping them out of the contract is WHY a sender cannot map onto them."""
    _, auth = two_users
    auth("receiver")
    response = _create(input_keys=["topic", field], open_to_all=True)
    assert response["error"] == "invalid_delivery_request"
    assert field in response["detail"]


@pytest.mark.parametrize("field", store.SENDER_ATTRIBUTION_FIELDS)
def test_a_sender_cannot_map_an_output_onto_an_attribution_field(two_users, field):
    """The structural consequence, driven from the sender's side.

    The reserved-field mapping is the ONLY reason this can be refused: `topic` is
    covered, so the contract's `required - mapped` check is already satisfied and
    only `mapped - accepted` can fire. The first version of this test mapped just
    the reserved field and left `topic` unmapped, so it passed with the guard
    deleted -- a surviving mutation the cross-family review found on 2026-09-26.
    """
    base, auth = two_users
    auth("receiver")
    receiver = _create(open_to_all=True, discoverable=True)
    auth("outsider")
    payload = {
        "branch_def_id": "b-outsider", "node_id": "entry",
        "receiver_id": receiver["receiver_id"], "expected_generation": 1,
        "mapping": {"result": "topic", "extra": field},
    }
    response = json.loads(server.write_graph(
        target="output_link", operation="connect", graph_id="u-outsider",
        payload_json=json.dumps(payload),
    ))
    assert response["error"] == "invalid_delivery_request", response
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_output_links").fetchone()[0] == 0
    # Control: the SAME call with a legitimate second target connects, so the
    # refusal above is attributable to the reserved name and nothing else.
    payload["mapping"] = {"result": "topic"}
    assert "link_id" in json.loads(server.write_graph(
        target="output_link", operation="connect", graph_id="u-outsider",
        payload_json=json.dumps(payload),
    ))


def test_a_retry_to_an_attributed_receiver_stays_the_same_delivery(
    two_users, provider_probe,
):
    """Attribution lands in inputs_json, so it lands in the replay digest.

    Found by the rate-limit test while writing this change: the replay paths
    recompute the sender's mapping to compare against what was stored, and a
    mapping WITHOUT the platform's attribution reads as changed content. Every
    retry to a receiver that declares an attribution field conflicted. A retry is
    the normal response to a timeout, so this is the difference between a resend
    being safe and it being refused.
    """
    base, auth = two_users
    auth("receiver")
    receiver = _create(open_to_all=True, discoverable=True)
    auth("outsider")
    link = _connect(receiver)
    first = _send(link, occurrence="retry-me")
    assert "delivery_id" in first, first
    for _ in range(2):
        again = _send(link, occurrence="retry-me")
        assert again["delivery_id"] == first["delivery_id"], again
    # Genuinely different content under the same occurrence id is still a conflict.
    changed = _send(link, "something else", occurrence="retry-me")
    assert "occurrence_conflict" in changed["detail"], changed
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_deliveries").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM graph_delivery_attempts").fetchone()[0] == 1
        stored = json.loads(conn.execute(
            "SELECT inputs_json FROM graph_deliveries",
        ).fetchone()[0])
    assert stored["delivery_sender_id"] == "outsider"


def test_the_sender_cannot_read_the_owners_workflow_step_or_run(two_users, provider_probe):
    """An accepted delivery grants the sender nothing inside the owner's universe."""
    base, auth = two_users
    auth("receiver")
    receiver = _create(open_to_all=True, discoverable=True)
    auth("outsider")
    link = _connect(receiver)
    sent = _send(link)
    assert "delivery_id" in sent, sent
    auth("receiver")
    owner_view = json.loads(server.read_graph(
        target="delivery", graph_id="u-receiver", query=sent["delivery_id"],
    ))
    receiver_run = owner_view["run_id"]
    runs.wait_for(receiver_run, timeout=10)

    auth("outsider")
    sender_view = json.loads(server.read_graph(
        target="delivery", graph_id="u-outsider", query=sent["delivery_id"],
    ))
    assert sender_view["status"] == "completed", sender_view
    assert "run_id" not in sender_view
    # The receiver's node returned "receiver-private" in an output field.
    assert "receiver-private" not in json.dumps(sender_view)
    # The owner's workflow, its step, and the run that processed the delivery.
    assert json.loads(server.read_graph(
        target="branch", graph_id="u-outsider", branch_id="b-receiver",
    )).get("error")
    for target in ("run", "run_output"):
        blocked = json.loads(server.read_graph(
            target=target, graph_id="u-outsider", run_id=receiver_run,
        ))
        assert "private prompt" not in json.dumps(blocked)
        assert "receiver-private" not in json.dumps(blocked)


# ---------------------------------------------------------------------------
# The abuse bound
# ---------------------------------------------------------------------------


def test_the_per_sender_rate_limit_trips_and_names_itself(two_users, provider_probe):
    """A usage bound on an open receiver, refused loudly and spending no budget."""
    base, auth = two_users
    auth("receiver")
    receiver = _create(open_to_all=True, discoverable=True, sender_rate_limit=2)
    auth("outsider")
    link = _connect(receiver)
    accepted = [_send(link, occurrence=f"send-{index}") for index in range(2)]
    assert all("delivery_id" in response for response in accepted), accepted

    refused = _send(link, occurrence="send-2")
    assert refused["error"] == "invalid_delivery_request"
    assert "receiver_sender_rate_limit_exceeded" in refused["detail"]
    # The reason is actionable: it names the limit and what the sender has sent.
    assert "2 deliveries per sender" in refused["detail"]

    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_deliveries").fetchone()[0] == 2
        # Refused before resource admission: no run reserved for the third send.
        assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 2

    # A retry of an ALREADY ACCEPTED occurrence is not new usage: at the limit it
    # still returns the original receipt rather than being refused.
    replay = _send(link, occurrence="send-0")
    assert replay["delivery_id"] == accepted[0]["delivery_id"]
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_deliveries").fetchone()[0] == 2


def test_the_limit_is_per_sender_not_per_receiver(two_users, provider_probe):
    """One sender exhausting its budget must not lock everyone else out."""
    base, auth = two_users
    auth("receiver")
    receiver = _create(open_to_all=True, discoverable=True, sender_rate_limit=1)
    auth("outsider")
    outsider_link = _connect(receiver)
    assert "delivery_id" in _send(outsider_link, occurrence="outsider-one")
    assert "receiver_sender_rate_limit_exceeded" in _send(
        outsider_link, occurrence="outsider-two",
    )["detail"]

    auth("sender")
    sender_link = _connect(receiver, graph="u-sender", branch="b-sender")
    assert "link_id" in sender_link, sender_link
    accepted = _send(sender_link, occurrence="sender-one", graph="u-sender")
    assert "delivery_id" in accepted, accepted
    with deliveries.transaction(base) as conn:
        senders = [row[0] for row in conn.execute(
            "SELECT sender_id FROM graph_deliveries ORDER BY accepted_at",
        )]
    assert senders == ["outsider", "sender"]


def test_the_limit_is_usage_and_applies_to_an_enumerated_sender_too(two_users):
    """One code path for every account: naming a sender does not exempt them.

    And it bounds traffic only -- an owner may hold any number of receivers, each
    with its own limit; nothing here caps structure.
    """
    base, auth = two_users
    auth("receiver")
    named = _create(allowed_senders=["sender"], sender_rate_limit=1)
    second = _create(allowed_senders=["sender"], sender_rate_limit=1)
    assert named["receiver_id"] != second["receiver_id"]
    auth("sender")
    first_link = _connect(named, graph="u-sender", branch="b-sender")
    assert "delivery_id" in _send(first_link, occurrence="a", graph="u-sender")
    assert "receiver_sender_rate_limit_exceeded" in _send(
        first_link, occurrence="b", graph="u-sender",
    )["detail"]
    # A separate receiver carries a separate budget, so the bound is per receiver
    # per sender, not a global cap on the sender.
    second_link = _connect(second, graph="u-sender", branch="b-sender")
    assert "delivery_id" in _send(second_link, occurrence="c", graph="u-sender")
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT count(*) FROM graph_deliveries").fetchone()[0] == 2


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_a_receiver_table_that_predates_the_exposure_columns_migrates_closed(
    tmp_path, monkeypatch,
):
    """An existing private receiver must not be opened by a schema upgrade."""
    import sqlite3

    from tinyassets.runs import runs_db_path

    base = tmp_path / "legacy"
    path = runs_db_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = sqlite3.connect(path)
    # Put the file in WAL mode HERE. `transaction()` sets it per connection, and
    # switching a rollback-journal database to WAL needs an exclusive lock that
    # ignores the busy timeout -- so several openers arriving at once on a
    # never-opened file fail in `PRAGMA journal_mode=WAL` before reaching anything
    # this test is about. Pre-existing, and not what the concurrency assertion below
    # is asking; with the mode already set, the openers contend only on the migration.
    legacy.execute("PRAGMA journal_mode=WAL")
    legacy.executescript(
        """CREATE TABLE graph_receivers (
            receiver_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
            universe_id TEXT NOT NULL, branch_def_id TEXT NOT NULL,
            node_id TEXT NOT NULL, generation INTEGER NOT NULL CHECK(generation > 0),
            description TEXT NOT NULL, contract_json TEXT NOT NULL,
            senders_json TEXT NOT NULL, snapshot_json TEXT NOT NULL,
            source_sha256 TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL,
            created_at REAL NOT NULL, revoked_at REAL);"""
    )
    legacy.execute(
        "INSERT INTO graph_receivers VALUES (?,?,?,?,?,1,?,?,?,?,?,?,?,NULL)",
        ("legacy-id", "receiver", "u-receiver", "b-receiver", "entry", "old",
         "[]", '["sender"]', "{}", "sha", "sha", 0.0),
    )
    legacy.commit()
    legacy.close()

    # Concurrent openers must serialize. `ALTER TABLE ADD COLUMN` has no
    # `IF NOT EXISTS`, so running the migration outside the write lock lets both
    # openers see the column missing and the loser raise `duplicate column name`
    # (reproduced by the cross-family review, 2026-09-26). Threads rather than
    # processes so they contend on one database file without a spawn cost.
    from concurrent.futures import ThreadPoolExecutor

    def open_and_read():
        with store.transaction(base) as conn:
            return conn.execute(
                "SELECT open_to_all, discoverable, sender_rate_limit FROM graph_receivers",
            ).fetchone()["sender_rate_limit"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        limits = [future.result() for future in
                  [pool.submit(open_and_read) for _ in range(6)]]
    # A migrated receiver inherits no platform policy: the added column defaults
    # to NO_SENDER_RATE_LIMIT, same as a freshly created one.
    assert limits == [store.NO_SENDER_RATE_LIMIT] * 6

    # The write-lock precondition is CHECKED, not just documented -- the race that
    # violating it opens is timing-dependent, so the threaded assertion above is
    # necessary but not sufficient on its own.
    outside = sqlite3.connect(path)
    try:
        assert not outside.in_transaction
        with pytest.raises(ValueError, match="write lock"):
            store.migrate_in_transaction(outside)
    finally:
        outside.close()

    with store.transaction(base) as conn:
        # The column exists exactly once, so no opener added a second one.
        names = [str(row[1]) for row in conn.execute("PRAGMA table_info(graph_receivers)")]
        for column in ("open_to_all", "discoverable", "sender_rate_limit"):
            assert names.count(column) == 1, column
        row = conn.execute("SELECT * FROM graph_receivers").fetchone()
        assert row["open_to_all"] == 0
        assert row["discoverable"] == 0
        assert row["sender_rate_limit"] == store.NO_SENDER_RATE_LIMIT
        with pytest.raises(store.ReceiverAccessDenied):
            store._permitted_receiver(conn, "legacy-id", "outsider")
        with pytest.raises(store.ReceiverAccessDenied):
            store._visible_receiver(conn, "legacy-id", "outsider")
        assert store._permitted_receiver(conn, "legacy-id", "sender")["receiver_id"] == "legacy-id"
    assert store.discover_receivers(base, principal_id="outsider") == {"receivers": []}
