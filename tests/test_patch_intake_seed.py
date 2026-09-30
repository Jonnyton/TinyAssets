"""The one connection the platform offers: reporting gaps to a TinyAssets intake.

Founder, 2026-09-30: *"for new users the request that enables connection to the
tinyassets universe for patch requests should be already there when they first
login just like the connect another llm one is already there from the start."*

What made it necessary (live, free account `u-01ky3zh1arr8qth8jee7zx63pq`): with
no connection and nothing telling it one existed, the universe invented a
pending request asking its user for a bearer token -- a credential field for an
address that needs no credential, plus a 404 help link.

Every test here drives the real surfaces: the rail read that seeds, the answer
that grants, and the delivery path the grant authorizes. Two independently
authenticated principals who share no ACL, so the cross-user floor is asserted
rather than assumed.
"""
# ruff: noqa: F811 -- pytest resolves imported fixtures by parameter name

from __future__ import annotations

import json
import logging

import pytest

from tests.test_delivery_runtime import provider_probe  # noqa: F401
from tests.test_receiver_links import env  # noqa: F401
from tinyassets import patch_intake
from tinyassets import universe_server as server
from tinyassets.api import pending_requests as api
from tinyassets.storage import effector_consents
from tinyassets.storage import pending_requests as store

_CAPS = [
    "tinyassets.extensions.read",
    "tinyassets.extensions.write",
    "tinyassets.extensions.costly",
    "tinyassets.universe.write",
]


@pytest.fixture
def world(env, monkeypatch):
    """Two owners with real ACLs, real universe directories, and no intake yet.

    The directory matters: ``_owner_gate`` refuses a universe id with no
    directory behind it, so a fixture that only writes ACL rows would make every
    rail read here return the absent-resource envelope and the tests would pass
    for the wrong reason.
    """
    base, authenticate = env
    for owner in ("receiver", "sender", "outsider"):
        (base / ("u-" + owner)).mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv(patch_intake.RECEIVER_ID_VAR, raising=False)
    monkeypatch.delenv(patch_intake.LABEL_VAR, raising=False)

    def auth(owner):
        authenticate(owner, capabilities=_CAPS)

    return base, auth


def _offer(monkeypatch, receiver_id, label=None):
    monkeypatch.setenv(patch_intake.RECEIVER_ID_VAR, receiver_id)
    if label is not None:
        monkeypatch.setenv(patch_intake.LABEL_VAR, label)


def _offered(monkeypatch, **kw):
    """Create an intake receiver AND configure the platform to offer it."""
    intake = _intake(**kw)
    _offer(monkeypatch, intake["receiver_id"])
    return intake


def _rail(graph="u-sender"):
    return api.list_requests(universe_id=graph)


def _seeded(rail):
    """The one platform-seeded intake ask in a rail reply, or None."""
    found = [
        row for row in rail["pending"]
        if (row.get("action") or {}).get("type") == patch_intake.ACTION_TYPE
    ]
    assert len(found) <= 1, found
    return found[0] if found else None


def _answer(request_id, *, graph="u-sender", **extra):
    return api.answer_request(
        universe_id=graph,
        payload=json.dumps({"request_id": request_id, **extra}),
    )


def _grants(base, graph="u-sender"):
    return effector_consents.list_consents(
        base / graph, sink=patch_intake.PATCH_INTAKE_SINK
    )


def _all_grants(base, graph="u-sender"):
    return effector_consents.list_consents(base / graph)


# ---------------------------------------------------------------------------
# It is there at first sign-in, and it is asked exactly once
# ---------------------------------------------------------------------------


def _intake(open_to_all=True, discoverable=True, description="Send TinyAssets a gap"):
    return json.loads(server.write_graph(
        target="receiver", operation="create", graph_id="u-receiver",
        payload_json=json.dumps({
            "branch_def_id": "b-receiver", "node_id": "entry",
            "input_keys": ["topic"], "allowed_senders": [],
            "open_to_all": open_to_all, "discoverable": discoverable,
            "description": description,
        }),
    ))


def test_the_ask_is_in_the_very_first_rail_read(world, monkeypatch):
    """No sign-in hook and no migration: the rail read every surface makes."""
    base, auth = world
    auth("receiver")
    intake = _offered(monkeypatch)

    auth("sender")
    row = _seeded(_rail())
    assert row is not None, "a new universe was offered nothing"
    assert row["status"] == "pending"
    assert row["origin"] == "platform", "the agent must not be able to withdraw it"
    assert row["fields"] == [], "there is nothing to paste"
    assert row["action"]["receiver_id"] == intake["receiver_id"]
    # The sentence the owner reads before tapping names the scope, and promises
    # no secret.
    assert "nothing else of yours" in row["grant_sentence"]
    assert "Nothing to paste" in row["grant_sentence"]


def test_reading_the_rail_again_does_not_duplicate_it(world, monkeypatch):
    base, auth = world
    auth("receiver")
    _offered(monkeypatch)
    auth("sender")
    first = _seeded(_rail())
    for _ in range(3):
        again = _seeded(_rail())
        assert again["request_id"] == first["request_id"]
    rows = store.find_by_action_type(base / "u-sender", patch_intake.ACTION_TYPE)
    assert len(rows) == 1, rows


def test_nothing_is_seeded_when_no_intake_is_configured(world):
    """Unset is a legitimate deployment: offer nothing, claim nothing."""
    _base, auth = world
    auth("sender")
    rail = _rail()
    assert _seeded(rail) is None
    assert "patch_intake" not in rail


def test_a_misconfigured_intake_seeds_nothing_and_says_so(world, monkeypatch, caplog):
    """Present-but-invalid is an operator error, never a silent 'unset'."""
    _base, auth = world
    monkeypatch.setenv(patch_intake.RECEIVER_ID_VAR, "no spaces allowed here")
    auth("sender")
    with caplog.at_level(logging.ERROR, logger="tinyassets.patch_intake"):
        rail = _rail()
    assert _seeded(rail) is None
    assert "patch_intake" not in rail
    assert any("misconfigured" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    "answer_kwargs",
    [
        {"decision": "declined", "values": {}},
        {"dismiss": True},
        {"dismiss": True, "dont_ask_again": True},
    ],
    ids=["denied", "cleared", "cleared-and-muted"],
)
def test_an_answered_ask_is_never_re_seeded(world, monkeypatch, answer_kwargs):
    base, auth = world
    auth("receiver")
    _offered(monkeypatch)
    auth("sender")
    row = _seeded(_rail())
    assert _answer(row["request_id"], **answer_kwargs).get("error") is None

    assert _seeded(_rail()) is None, "the user already decided this"
    assert not _grants(base), "a refusal must not leave a grant behind"


def test_rewording_the_ask_does_not_re_ask_someone_who_declined(world, monkeypatch):
    """MUTATION CHECK on the idempotence key: it is the address, not the text.

    The request's ``dedupe_key`` is a hash of ``[kind, title, body, fields,
    action]``, so if that were the key, changing the label -- which rewords the
    title AND the body AND the action -- would re-ask a user who said no on the
    next deploy. Keyed on the intake's ``receiver_id``, the decision survives.
    """
    base, auth = world
    auth("receiver")
    intake = _offered(monkeypatch)
    auth("sender")
    row = _seeded(_rail())
    assert _answer(row["request_id"], decision="declined", values={}).get("error") is None

    _offer(monkeypatch, intake["receiver_id"], label="TinyAssets Labs")
    assert _seeded(_rail()) is None
    # ...and the same intake under a DIFFERENT address is a different decision,
    # so that one is legitimately offered.
    auth("receiver")
    other = _intake(description="A second intake")
    auth("sender")
    _offer(monkeypatch, other["receiver_id"])
    fresh = _seeded(_rail())
    assert fresh is not None
    assert fresh["action"]["receiver_id"] == other["receiver_id"]


# ---------------------------------------------------------------------------
# Approving it creates exactly one grant
# ---------------------------------------------------------------------------


def test_approval_records_exactly_one_grant_naming_only_that_intake(world, monkeypatch):
    base, auth = world
    auth("receiver")
    intake = _offered(monkeypatch)
    auth("sender")
    row = _seeded(_rail())
    result = _answer(row["request_id"], values={})

    assert result["status"] == "answered"
    assert result["decision"] == "allowed"
    assert result["receiver_id"] == intake["receiver_id"]
    # The contract comes back, so the universe can wire a step in the same turn
    # rather than going looking for the id again.
    assert [field["name"] for field in result["contract"]] == ["topic"]
    # EXACTLY one consent row in the whole universe, and it names the intake.
    assert _all_grants(base) == [{
        "sink": patch_intake.PATCH_INTAKE_SINK,
        "destination": intake["receiver_id"],
        "granted_at": pytest.approx(result["grant"] and _grants(base)[0]["granted_at"]),
        "granted_by": "sender",
        "revoked_at": None,
    }]
    # And the ask leaves the rail.
    assert _seeded(_rail()) is None


def test_the_ask_takes_no_values_and_carries_no_secret_field(world, monkeypatch):
    """A fieldless confirmation. Submitting values is refused, not ignored."""
    _base, auth = world
    auth("receiver")
    _offered(monkeypatch)
    auth("sender")
    row = _seeded(_rail())
    refused = _answer(row["request_id"], values={"secret": "sk-live-not-a-thing"})
    assert refused["error"] == "request_invalid"
    assert "nothing to paste" in refused["detail"]


def test_the_action_refuses_anything_beyond_an_address_and_a_label():
    """No endpoint, scheme or secret can ride on the row the answer executes."""
    with pytest.raises(ValueError, match="nothing else"):
        api._validated_action({
            "type": patch_intake.ACTION_TYPE,
            "receiver_id": "a" * 32,
            "auth_scheme": "bearer",
        })
    with pytest.raises(ValueError, match="receiver_id must be"):
        api._validated_action({"type": patch_intake.ACTION_TYPE, "receiver_id": "*"})


def test_approval_is_refused_when_the_intake_does_not_accept_this_sender(
    world, monkeypatch,
):
    """A discoverable-but-closed intake lets a sender READ its terms only.

    Granting against one would hand the owner a connection that cannot send, so
    the yes is not consumed: the request stays pending with the reason.
    """
    base, auth = world
    auth("receiver")
    closed = _intake(open_to_all=False, discoverable=True)
    auth("sender")
    _offer(monkeypatch, closed["receiver_id"])
    row = _seeded(_rail())
    refused = _answer(row["request_id"], values={})

    assert refused["error"] == "patch_intake_closed"
    assert refused["request_pending"] is True
    assert not _grants(base)
    assert _seeded(_rail())["request_id"] == row["request_id"], "still waiting"


def test_an_explicitly_enumerated_sender_can_approve_and_send(
    world, monkeypatch, provider_probe,
):
    """An intake need not be open to the world to be offered to named senders.

    This is the case a permission check reconstructed from the SENDER-facing
    receiver view gets wrong: that view omits ``allowed_senders`` on purpose, so
    ``open_to_all or actor in allowed_senders`` reads False and the owner is told
    the intake is closed -- while delivery would in fact have succeeded. The
    authority has to be the same question delivery asks.
    """
    base, auth = world
    auth("receiver")
    named = json.loads(server.write_graph(
        target="receiver", operation="create", graph_id="u-receiver",
        payload_json=json.dumps({
            "branch_def_id": "b-receiver", "node_id": "entry",
            "input_keys": ["topic"], "allowed_senders": ["sender"],
            "open_to_all": False, "discoverable": False,
            "description": "Invited senders only",
        }),
    ))
    auth("sender")
    _offer(monkeypatch, named["receiver_id"])
    row = _seeded(_rail())
    result = _answer(row["request_id"], values={})

    assert result.get("status") == "answered", result
    assert [g["destination"] for g in _grants(base)] == [named["receiver_id"]]
    assert "delivery_id" in _send(_link(named), occurrence="invited")


def test_a_misconfigured_intake_gates_no_delivery_at_all(
    world, monkeypatch, provider_probe, caplog,
):
    """Nothing is offered, so nothing is fenced -- and ordinary work still runs.

    Not a fail-open: an invalid value means no universe was handed an address by
    the platform and no grant exists under it. Refusing every delivery instead
    would break unrelated cross-user work over a typo in one variable.
    """
    base, auth = world
    auth("receiver")
    somebody = _intake(description="Reached by discovery, not by the platform")
    auth("sender")
    link = _link(somebody)
    monkeypatch.setenv(patch_intake.RECEIVER_ID_VAR, "not a receiver id")
    with caplog.at_level(logging.ERROR, logger="tinyassets.patch_intake"):
        sent = _send(link, occurrence="ordinary-under-misconfig")

    assert "delivery_id" in sent, sent
    assert not _grants(base), "and no grant was invented to let it through"
    assert any("misconfigured" in record.message for record in caplog.records)


def test_approval_is_refused_when_the_offered_intake_changed(world, monkeypatch):
    """A stored row outlives the configuration it was created under."""
    base, auth = world
    auth("receiver")
    _offered(monkeypatch)
    auth("sender")
    row = _seeded(_rail())
    _offer(monkeypatch, "b" * 32)
    refused = _answer(row["request_id"], values={})

    assert refused["error"] == "patch_intake_changed"
    assert refused["request_pending"] is True
    assert not _grants(base)


def test_another_owner_cannot_read_or_answer_this_universes_ask(world, monkeypatch):
    """Cross-user floor: the rail and its answers are the owner's alone."""
    _base, auth = world
    auth("receiver")
    _offered(monkeypatch)
    auth("sender")
    row = _seeded(_rail())

    auth("outsider")
    assert _rail("u-sender").get("error") == "not_found"
    assert _answer(row["request_id"], graph="u-sender", values={})["error"] == "not_found"


# ---------------------------------------------------------------------------
# The grant is what lets a delivery through -- to that intake and nothing else
# ---------------------------------------------------------------------------


def _link(receiver, *, graph="u-sender", branch="b-sender"):
    return json.loads(server.write_graph(
        target="output_link", operation="connect", graph_id=graph,
        payload_json=json.dumps({
            "branch_def_id": branch, "node_id": "entry",
            "receiver_id": receiver["receiver_id"],
            "expected_generation": receiver["generation"],
            "mapping": {"result": "topic"},
        }),
    ))


def _send(link, value="the branch editor refuses my own node", *, occurrence="one",
          graph="u-sender"):
    return json.loads(server.run_graph(
        operation="deliver_output", graph_id=graph,
        inputs_json=json.dumps({
            "link_id": link["link_id"], "occurrence_id": occurrence,
            "outputs": {"result": value},
        }),
    ))


def _approve(monkeypatch, intake):
    _offer(monkeypatch, intake["receiver_id"])
    row = _seeded(_rail())
    result = _answer(row["request_id"], values={})
    assert result.get("status") == "answered", result
    return result


def test_the_grant_lets_a_patch_request_reach_the_intake(
    world, monkeypatch, provider_probe,
):
    """End to end, the way a universe files one: approve, connect, send."""
    _base, auth = world
    auth("receiver")
    intake = _intake()

    auth("sender")
    _approve(monkeypatch, intake)
    sent = _send(_link(intake))
    assert "delivery_id" in sent, sent

    auth("receiver")
    receipt = json.loads(server.read_graph(
        target="delivery", graph_id="u-receiver", query=sent["delivery_id"],
    ))
    # The intake owner sees WHO sent and WHAT they sent -- and nothing else of
    # the sender's: attribution is platform-filled, never sender-supplied.
    assert receipt["sender_id"] == "sender"
    assert receipt["sender_universe_id"] == "u-sender"


def test_without_the_grant_the_same_send_is_refused_and_writes_nothing(
    world, monkeypatch, provider_probe,
):
    """MUTATION CHECK on the fence: only the grant differs from the test above."""
    from tinyassets.storage import deliveries

    base, auth = world
    auth("receiver")
    intake = _intake()

    auth("sender")
    _offer(monkeypatch, intake["receiver_id"])   # offered, NOT approved
    link = _link(intake)
    refused = _send(link)

    assert refused.get("error") == "invalid_delivery_request", refused
    assert "patch_intake_consent_required" in refused["detail"]
    assert not _grants(base)
    with deliveries.transaction(base) as conn:
        assert conn.execute("SELECT COUNT(*) FROM graph_deliveries").fetchone()[0] == 0


def test_revoking_the_grant_stops_the_next_send(world, monkeypatch, provider_probe):
    base, auth = world
    auth("receiver")
    intake = _intake()

    auth("sender")
    _approve(monkeypatch, intake)
    link = _link(intake)
    assert "delivery_id" in _send(link, occurrence="one")

    effector_consents.revoke_consent(
        base / "u-sender",
        sink=patch_intake.PATCH_INTAKE_SINK,
        destination=intake["receiver_id"],
    )
    later = _send(link, value="a second gap", occurrence="two")
    assert "patch_intake_consent_required" in later.get("detail", ""), later
    # A retry of the ALREADY-ACCEPTED occurrence is refused too: a withdrawn
    # consent must not be honoured by replaying what it used to allow.
    assert "patch_intake_consent_required" in _send(link, occurrence="one").get(
        "detail", ""
    )


def test_the_grant_authorizes_only_the_intake_it_names(
    world, monkeypatch, provider_probe,
):
    """Send-only access to THAT one intake. A second intake is not covered."""
    _base, auth = world
    auth("receiver")
    first = _intake(description="First intake")
    second = _intake(description="Second intake")
    assert first["receiver_id"] != second["receiver_id"]

    auth("sender")
    _approve(monkeypatch, first)
    # Now the platform offers the SECOND one. The grant the owner gave names the
    # first, so it does not carry over.
    _offer(monkeypatch, second["receiver_id"])
    refused = _send(_link(second), occurrence="second-intake")
    assert "patch_intake_consent_required" in refused.get("detail", ""), refused


def test_a_receiver_the_platform_never_offered_needs_no_patch_intake_grant(
    world, monkeypatch, provider_probe,
):
    """Every other receiver is one the universe found itself.

    There the receiving owner's own exposure is the whole authority and the
    platform holds no consent, so the fence must not touch it -- otherwise
    configuring an intake would quietly break ordinary cross-user delivery.
    """
    _base, auth = world
    auth("receiver")
    ordinary = _intake(description="Nothing to do with patch requests")
    other = _intake(description="The configured intake")

    auth("sender")
    _offer(monkeypatch, other["receiver_id"])   # configured, never granted
    sent = _send(_link(ordinary), occurrence="ordinary")
    assert "delivery_id" in sent, sent


# ---------------------------------------------------------------------------
# What the universe is told
# ---------------------------------------------------------------------------


def test_the_rail_points_an_ungranted_universe_at_the_seeded_ask(world, monkeypatch):
    """The failure this change exists to stop: inventing a credential ask."""
    _base, auth = world
    auth("receiver")
    intake = _offered(monkeypatch)
    auth("sender")
    rail = _rail()

    view = rail["patch_intake"]
    assert view["granted"] is False
    assert view["receiver_id"] == intake["receiver_id"]
    assert "already waiting in their rail" in view["how"]
    assert "Do NOT raise a connection or credential request" in view["how"]
    assert "token" in view["how"]


def test_the_rail_tells_a_granted_universe_how_to_send(world, monkeypatch):
    _base, auth = world
    auth("receiver")
    intake = _intake()
    auth("sender")
    _approve(monkeypatch, intake)

    view = _rail()["patch_intake"]
    assert view["granted"] is True
    assert "deliver_output" in view["how"]
    assert "output_link" in view["how"]
    assert "No credential" in view["how"]


def test_the_handbook_chapter_says_a_patch_request_needs_no_token():
    """Served guidance, from the shipped chapter the agent can actually read."""
    from tinyassets.engine_mcp_server import SERVED_TOOL_CHAPTERS

    chapter = SERVED_TOOL_CHAPTERS["write_graph"]["delivering"]
    assert "patch request" in chapter.lower()
    assert "NO credential" in chapter
    assert "patch_intake" in chapter
    assert "patch_intake_consent_required" in chapter
    # And it names the wrong move explicitly, because that is what happened.
    assert "connect_http" in chapter
