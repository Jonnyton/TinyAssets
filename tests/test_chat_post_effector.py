"""Delivery as an effect a user's branch declares."""

from __future__ import annotations

from tinyassets.effectors.chat_post import run_chat_post_effector


class _Receipt:
    provider_receipt_ref = "1700000000.000100"


def _transport(calls):
    def _post(destination, body, *, thread_ts=""):
        calls.append({"destination": destination, "body": body})
        return _Receipt()

    return _post


def test_it_delivers_the_node_output():
    calls: list = []
    result = run_chat_post_effector(
        node_id="deliver", output_keys=["brief"],
        run_state={"brief": "here is your niche brief", "channel_id": "D123",
                   "universe_id": "u-a"},
        transport=_transport(calls),
    )
    assert result["delivered"] is True
    assert calls[0]["body"] == "here is your niche brief"
    assert calls[0]["destination"].address == "D123"


def test_no_destination_is_actionable_not_silent():
    result = run_chat_post_effector(
        node_id="deliver", output_keys=["brief"],
        run_state={"brief": "text", "universe_id": "u-a"},
        transport=_transport([]),
    )
    assert result["error_kind"] == "no_destination"
    assert "channel_id" in result["error"]


def test_nothing_to_deliver_is_reported_not_posted():
    """A 'delivered' receipt for an empty post is worse than a visible failure."""
    calls: list = []
    result = run_chat_post_effector(
        node_id="deliver", output_keys=["brief"],
        run_state={"brief": "   ", "channel_id": "D123", "universe_id": "u-a"},
        transport=_transport(calls),
    )
    assert result["error_kind"] == "nothing_to_deliver"
    assert calls == []


def test_a_transport_failure_becomes_evidence_not_a_raise():
    """It runs on the completion path; a failed delivery must not kill a run
    whose actual work already succeeded."""
    def _boom(*a, **k):
        raise RuntimeError("slack is down")

    result = run_chat_post_effector(
        node_id="deliver", output_keys=["brief"],
        run_state={"brief": "text", "channel_id": "D123", "universe_id": "u-a"},
        transport=_boom,
    )
    assert result["error_kind"] == "delivery_failed"


def test_dry_run_posts_nothing():
    calls: list = []
    result = run_chat_post_effector(
        node_id="deliver", output_keys=["brief"],
        run_state={"brief": "text", "channel_id": "D123", "universe_id": "u-a"},
        dry_run=True, transport=_transport(calls),
    )
    assert result["dry_run"] is True and calls == []


def test_the_destination_can_come_from_any_declared_key():
    for key in ("channel_id", "chat_channel_id", "deliver_to"):
        calls: list = []
        run_chat_post_effector(
            node_id="deliver", output_keys=["brief"],
            run_state={"brief": "text", key: "D999", "universe_id": "u-a"},
            transport=_transport(calls),
        )
        assert calls[0]["destination"].address == "D999", key


def test_it_is_dispatched_for_a_declaring_node():
    """The registry wiring, not just the function."""
    from types import SimpleNamespace

    from tinyassets.effectors import run_effects_for_branch

    branch = SimpleNamespace(node_defs=[
        SimpleNamespace(node_id="deliver", output_keys=["brief"],
                        effects=["chat_post"])
    ])
    evidence = run_effects_for_branch(
        branch=branch,
        run_state={"brief": "text", "universe_id": "u-a"},
        dry_run=True,
    )
    assert "chat_post" in evidence.get("deliver", {})
