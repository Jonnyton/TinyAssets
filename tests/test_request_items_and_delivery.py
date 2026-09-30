"""Requests carry answerable items, and a background run can raise one.

The requests system is already the "the universe asks its owner and waits"
primitive. Two things it never had: a request that holds several answerable
items, and delivery to the owner's devices. These drive the real handlers
against real stores -- nothing between the ask and the row is patched.

The first test here is a PREMISE check, not a feature: the whole design rests
on a background run being able to raise a request as its owner
(``permissions.owner_run_identity``), and nothing tested that.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets.api import visibility as vis
from tinyassets.auth import middleware as mw
from tinyassets.daemon_server import (
    claim_founder_home,
    ensure_universe_registered,
    grant_universe_access,
)

OWNER = "workos|owner-requests"
OTHER = "workos|other-requests"
UID = "u-requests-home"
OTHER_UID = "u-requests-other"


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    return root


def _home(base: Path, uid: str, owner: str) -> Path:
    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    (udir / "soul.md").write_text(f"# {uid}\n", encoding="utf-8")
    ensure_universe_registered(base, universe_id=uid, universe_path=udir)
    grant_universe_access(
        base, universe_id=uid, actor_id=owner, permission="admin", granted_by=owner,
    )
    claim_founder_home(base, owner, uid)
    vis.set_universe_visibility(uid, "private", source="default")
    return udir


def _ask(universe_id: str, **payload):
    from tinyassets.api.pending_requests import request_from_user

    document = {
        "kind": "TODO",
        "title": "Today",
        "action": {"type": "answer"},
        "fields": [{"name": "note", "type": "text", "label": "Reply"}],
    }
    document.update(payload)
    return request_from_user(universe_id=universe_id, payload=document)


def _items(*ids: str) -> list[dict]:
    return [
        {"item_id": i, "title": f"Do {i}",
         "fields": [{"name": "note", "type": "text", "label": "Reply"}]}
        for i in ids
    ]


def _answer(universe_id: str, **payload):
    from tinyassets.api.pending_requests import answer_request

    return answer_request(universe_id=universe_id, payload=dict(payload))


# --- premise: a background run raises a request as its owner ------------------


def test_a_background_run_raises_a_request_as_its_owner(base, nobody):
    """A run binds nobody on its own thread; owner_run_identity is what makes
    the ask the owner's. Without this, an automation cannot reach its person at
    all -- which is the whole point of delivery."""
    from tinyassets.api.permissions import owner_run_identity
    from tinyassets.storage.pending_requests import list_pending

    udir = _home(base, UID, OWNER)
    assert mw.current_identity_or_none() is None

    with owner_run_identity(base, UID, OWNER) as bound:
        assert bound is True
        raised = _ask(UID, body="two things need you")

    assert "error" not in raised, raised
    assert raised["status"] == "pending"
    pending = list_pending(udir)
    assert [row["request_id"] for row in pending] == [raised["request_id"]]
    # The binding is scoped to the run; nothing leaks onto the thread.
    assert mw.current_identity_or_none() is None


def test_a_run_bound_to_another_user_raises_nothing_here(base, nobody):
    """A collaborator's run naming the owner's universe gets the uniform
    absent-resource refusal, and no row lands anywhere."""
    from tinyassets.api.permissions import owner_run_identity
    from tinyassets.storage.pending_requests import list_pending

    udir = _home(base, UID, OWNER)
    other_dir = _home(base, OTHER_UID, OTHER)

    with owner_run_identity(base, OTHER_UID, OTHER) as bound:
        assert bound is True
        refused = _ask(UID, body="asking in someone else's universe")

    # `_owner_gate` returns `http_connection._NOT_FOUND` verbatim, on purpose:
    # one uniform absent-resource envelope across every owner-gated surface, so
    # this one cannot be used to probe what exists.
    assert refused.get("error") == "not_found"
    assert list_pending(udir) == []
    assert list_pending(other_dir) == []


# --- items ---------------------------------------------------------------------


def test_one_request_holds_several_answerable_items(base, signed_in):
    signed_in(OWNER)
    _home(base, UID, OWNER)

    raised = _ask(UID, items=_items("a", "b", "c"))

    assert "error" not in raised, raised
    assert [i["item_id"] for i in raised["items"]] == ["a", "b", "c"]
    assert {k: v["status"] for k, v in raised["item_answers"].items()} == {
        "a": "pending", "b": "pending", "c": "pending",
    }


def test_items_alone_satisfy_the_at_least_one_field_rule(base, signed_in):
    """A note whose answerable parts are all items has no top-level field."""
    signed_in(OWNER)
    _home(base, UID, OWNER)

    raised = _ask(UID, fields=[], items=_items("a"))

    assert "error" not in raised, raised
    assert raised["fields"] == []
    assert [i["item_id"] for i in raised["items"]] == ["a"]


def test_an_itemless_request_still_needs_a_field(base, signed_in):
    """The relaxation is scoped to items; it does not remove the rule."""
    signed_in(OWNER)
    _home(base, UID, OWNER)

    assert _ask(UID, fields=[]).get("error") == "request_invalid"


def test_answering_one_item_leaves_the_others_waiting(base, signed_in):
    from tinyassets.storage.pending_requests import get_request

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    raised = _ask(UID, items=_items("a", "b", "c"))

    result = _answer(UID, request_id=raised["request_id"], item_id="a",
                     values={"note": "done"})

    assert result["status"] == "answered"
    assert result["request_status"] == "pending"
    assert result["remaining"] == 2
    row = get_request(udir, raised["request_id"])
    assert row["status"] == "pending"
    assert row["item_answers"]["a"]["answer"] == {"note": "done"}
    assert row["item_answers"]["b"]["status"] == "pending"


def test_the_same_item_cannot_be_answered_twice(base, signed_in):
    from tinyassets.storage.pending_requests import get_request

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    raised = _ask(UID, items=_items("a", "b"))
    _answer(UID, request_id=raised["request_id"], item_id="a",
            values={"note": "first"})

    again = _answer(UID, request_id=raised["request_id"], item_id="a",
                    values={"note": "second"})

    assert again.get("error") == "item_already_resolved"
    row = get_request(udir, raised["request_id"])
    assert row["item_answers"]["a"]["answer"] == {"note": "first"}


def test_the_last_item_closes_the_request(base, signed_in):
    from tinyassets.storage.pending_requests import get_request

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    raised = _ask(UID, items=_items("a", "b"))
    _answer(UID, request_id=raised["request_id"], item_id="a",
            values={"note": "one"})

    last = _answer(UID, request_id=raised["request_id"], item_id="b",
                   values={"note": "two"})

    assert last["request_status"] == "answered"
    assert last["remaining"] == 0
    row = get_request(udir, raised["request_id"])
    assert row["status"] == "answered"
    assert row["answer"]["items"]["a"]["answer"] == {"note": "one"}
    assert row["answer"]["items"]["b"]["answer"] == {"note": "two"}


def test_a_whole_request_answer_does_not_fabricate_item_answers(base, signed_in):
    from tinyassets.storage.pending_requests import get_request

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    raised = _ask(UID, items=_items("a", "b", "c"))
    _answer(UID, request_id=raised["request_id"], item_id="a",
            values={"note": "only this one"})

    closed = _answer(UID, request_id=raised["request_id"], values={"note": "enough"})

    assert closed["status"] == "answered"
    row = get_request(udir, raised["request_id"])
    assert row["status"] == "answered"
    assert {k: v["status"] for k, v in row["item_answers"].items()} == {
        "a": "answered", "b": "unanswered", "c": "unanswered",
    }
    assert row["answer"]["items"]["a"]["answer"] == {"note": "only this one"}
    assert "b" not in row["answer"]["items"]


def test_an_unknown_item_id_is_not_found(base, signed_in):
    signed_in(OWNER)
    _home(base, UID, OWNER)
    raised = _ask(UID, items=_items("a"))

    missing = _answer(UID, request_id=raised["request_id"], item_id="zz",
                      values={"note": "x"})

    assert missing.get("error") == "not_found"
    assert missing.get("resource") == "request_item"


def test_the_store_itself_refuses_an_item_id_that_is_not_on_the_request(
    base, signed_in,
):
    """The API layer refuses this too, so the store's own check is defence in
    depth -- which a mutation test found staying green. `resolve_item` is a
    public store function another surface can call, so the invariant is pinned
    at BOTH layers rather than only at whichever one happens to run first."""
    from tinyassets.storage.pending_requests import get_request, resolve_item

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    raised = _ask(UID, items=_items("a"))

    refused = resolve_item(
        udir, raised["request_id"], "not-on-this-request", status="answered",
        answer={"note": "x"},
    )

    assert refused == {"error": "not_found", "resource": "request_item"}
    row = get_request(udir, raised["request_id"])
    assert row["status"] == "pending"
    assert row["item_answers"]["a"]["status"] == "pending"


def test_the_store_refuses_an_item_on_an_already_resolved_request(base, signed_in):
    from tinyassets.storage.pending_requests import resolve_item

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    raised = _ask(UID, items=_items("a", "b"))
    _answer(UID, request_id=raised["request_id"], values={"note": "closing"})

    refused = resolve_item(
        udir, raised["request_id"], "a", status="answered", answer={"note": "late"},
    )

    assert refused.get("error") == "already_resolved"


def test_the_store_refuses_a_status_that_is_neither_answered_nor_dismissed(
    base, signed_in,
):
    from tinyassets.storage.pending_requests import resolve_item

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    raised = _ask(UID, items=_items("a"))

    refused = resolve_item(udir, raised["request_id"], "a", status="withdrawn")

    assert refused.get("error") == "item_status_invalid"


def test_an_item_cannot_be_answered_with_a_field_it_never_asked_for(base, signed_in):
    signed_in(OWNER)
    _home(base, UID, OWNER)
    raised = _ask(UID, items=_items("a"))

    refused = _answer(UID, request_id=raised["request_id"], item_id="a",
                      values={"note": "ok", "smuggled": "value"})

    assert refused.get("error") == "request_invalid"
    assert "smuggled" in refused["detail"]


def test_malformed_items_are_refused_and_nothing_is_stored(base, signed_in):
    from tinyassets.storage.pending_requests import MAX_ITEMS, list_pending

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    cases = {
        "too many": _items(*[f"i{n}" for n in range(MAX_ITEMS + 1)]),
        "duplicate id": _items("a") + _items("a"),
        "bad id": [{"item_id": "Not Valid", "title": "x"}],
        "no id": [{"title": "x"}],
        "no title": [{"item_id": "a"}],
        "not an object": ["a"],
        "not a list": {"item_id": "a", "title": "x"},
    }
    for label, items in cases.items():
        refused = _ask(UID, items=items)
        assert refused.get("error") == "request_invalid", f"{label}: {refused}"
    assert list_pending(udir) == []


# --- the boundary that keeps "however he likes" safe ---------------------------


def test_an_item_can_never_carry_a_secret_field(base, signed_in):
    from tinyassets.storage.pending_requests import list_pending

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)

    refused = _ask(UID, items=[{
        "item_id": "a", "title": "Paste it",
        "fields": [{"name": "key", "type": "secret", "label": "API key"}],
    }])

    assert refused.get("error") == "request_invalid"
    assert "secret" in refused["detail"]
    assert list_pending(udir) == []


_NON_ANSWER_ACTIONS = [
    {"type": "connect_http", "destination": "api.example.com",
     "auth_scheme": "bearer"},
    {"type": "connect", "destination": "api.example.com"},
    {"type": "remove_http", "connection_id": "conn_x"},
    {"type": "extend_http", "connection_id": "conn_x"},
    {"type": "rotate_http", "connection_id": "conn_x"},
    {"type": "bind_model_access"},
    {"type": "grant_workspace_consent", "connection_id": "conn_x"},
]


@pytest.mark.parametrize("action", _NON_ANSWER_ACTIONS)
def test_the_validator_refuses_items_on_any_action_but_answer(action):
    """The rule itself, on the pure validator: an action-bearing ask is ONE
    decision, never a checklist. This is what stops an item from becoming the
    thing that deposits a key, so it is asserted directly rather than through
    whichever validator happens to refuse a malformed action first."""
    from tinyassets.api.pending_requests import _validated_items

    with pytest.raises(ValueError, match="answer"):
        _validated_items(_items("a"), action)


@pytest.mark.parametrize("action", _NON_ANSWER_ACTIONS)
def test_no_itemised_credential_request_ever_lands(base, signed_in, action):
    """Whichever validator refuses first, the row must not exist."""
    from tinyassets.storage.pending_requests import list_pending

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)

    refused = _ask(UID, action=action, items=_items("a"))

    assert refused.get("error"), action
    assert list_pending(udir) == []


def test_dont_ask_again_cannot_be_hung_on_one_item(base, signed_in):
    from tinyassets.storage.pending_requests import list_suppressions

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    raised = _ask(UID, items=_items("a", "b"))

    refused = _answer(UID, request_id=raised["request_id"], item_id="a",
                      values={"note": "x"}, dont_ask_again=True)

    assert refused.get("error") == "request_invalid"
    assert list_suppressions(udir) == []


def test_answering_an_item_keeps_the_row_reproducing_what_was_shown(base, signed_in):
    """`displayed_row_matches` pins the tuple the tab rendered from. Folding
    answers into `items` would make one item's answer un-execute the rest."""
    from tinyassets.api.pending_requests import displayed_row_matches
    from tinyassets.storage.pending_requests import get_request

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    raised = _ask(UID, items=_items("a", "b"))

    assert displayed_row_matches(get_request(udir, raised["request_id"]))
    _answer(UID, request_id=raised["request_id"], item_id="a", values={"note": "x"})
    assert displayed_row_matches(get_request(udir, raised["request_id"]))


def test_a_rewritten_itemised_row_stops_reproducing_itself(base, signed_in):
    """The pin has to still bite: an item edited into the row after it was
    rendered must fail the check, or items would be outside the binding."""
    from tinyassets.api.pending_requests import displayed_row_matches
    from tinyassets.storage.pending_requests import get_request

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    raised = _ask(UID, items=_items("a"))
    row = get_request(udir, raised["request_id"])

    row["items"] = _items("a", "sneaked-in")

    assert not displayed_row_matches(row)


def test_a_daily_note_is_not_deduped_onto_yesterdays(base, signed_in):
    """Same kind, title and body every day: only the items differ. Without
    items in the dedupe key today's note IS yesterday's row, so no new request
    lands and nothing is ever delivered."""
    from tinyassets.storage.pending_requests import list_pending

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)

    first = _ask(UID, fields=[], items=_items("mon-1", "mon-2"))
    second = _ask(UID, fields=[], items=_items("tue-1", "tue-2"))

    assert first["request_id"] != second["request_id"]
    assert len(list_pending(udir)) == 2


def test_an_itemless_requests_identity_is_unchanged_by_items_existing(
    base, signed_in,
):
    """Appending an empty list to every dedupe key changed the identity of
    every request that already existed: live pending rows stopped
    deduplicating and every standing "don't ask again" stopped matching, so a
    settled question was asked again (gpt-6-astra, 2026-09-29). Items only
    extend the identity of requests that HAVE items."""
    import json as _json

    from tinyassets.storage.pending_requests import get_request

    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    raised = _ask(UID)
    row = get_request(udir, raised["request_id"])

    assert row["dedupe_key"] == _json.dumps(
        [row["kind"], row["title"], row["body"], row["fields"], row["action"]],
        sort_keys=True, separators=(",", ":"),
    )
    assert _json.loads(row["dedupe_key"]) == _json.loads(row["dedupe_key"])[:5]


def test_a_settled_decision_still_matches_the_same_itemless_ask(base, signed_in):
    """The end-to-end shape of the same finding: dismiss with "don't ask me
    this again", then ask identically. It must be refused, not re-raised."""
    signed_in(OWNER)
    udir = _home(base, UID, OWNER)
    first = _ask(UID)
    _answer(UID, request_id=first["request_id"], dismiss=True,
            dont_ask_again=True, feedback="not interested")

    again = _ask(UID)

    assert again.get("status") == "settled"
    assert again.get("decision") == "declined"
    from tinyassets.storage.pending_requests import list_pending

    assert list_pending(udir) == []


def test_an_itemised_ask_is_a_different_identity_from_the_itemless_one(
    base, signed_in,
):
    signed_in(OWNER)
    udir = _home(base, UID, OWNER)

    itemless = _ask(UID)
    itemised = _ask(UID, items=_items("a"))

    assert itemless["request_id"] != itemised["request_id"]
    from tinyassets.storage.pending_requests import list_pending

    assert len(list_pending(udir)) == 2


def test_the_created_marker_never_reaches_the_agent(base, signed_in):
    signed_in(OWNER)
    _home(base, UID, OWNER)

    first = _ask(UID, items=_items("a"))
    repeat = _ask(UID, items=_items("a"))

    assert "created" not in first
    assert "created" not in repeat
    assert repeat["request_id"] == first["request_id"]


# The item-answer EVENT is proved in tests/test_automation_events.py, through
# the real register_automation + emitter + pump that every other event uses.
