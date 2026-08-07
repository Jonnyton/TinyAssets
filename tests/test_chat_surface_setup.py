"""Connecting a chat account and routing channels, from the chatbot.

This is the surface that makes recognition and routing *reachable*: before it,
neither `provision` nor `bind` had a user-facing caller, so no founder mapping
could exist in production and every channel routed to one universe.

Authority is the thing under test. Every operation names a universe and a
binding, and every one of those names is a request rather than a grant — the
tests that matter are the ones proving a caller cannot set up somebody else's
universe, or hand themselves a subject they are not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_founder_recognition import (
    APP_ID,
    FOUNDER_ID,
    STRANGER_ID,
    TEAM_ID,
    _founder_universe,
    _socket_event,
)
from tinyassets.api import chat_surface
from tinyassets.app_channel_routing import ChannelRouter
from tinyassets.founder_grant import FounderRecognizer, is_founder_grant

CHANNEL_ALPHA = "C0ALPHA0001"
SENDER = "U07HUM0001"


@pytest.fixture
def universe(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    target = _founder_universe(tmp_path, universe="u-work")
    monkeypatch.setattr(
        chat_surface, "current_request_actor_id", lambda: FOUNDER_ID
    )
    return target


def _as(monkeypatch, actor: str):
    monkeypatch.setattr(chat_surface, "current_request_actor_id", lambda: actor)


# --- authority --------------------------------------------------------------


def test_an_anonymous_caller_cannot_set_anything_up(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _as(monkeypatch, "anonymous")

    result = chat_surface.connect_account(
        universe_id="u-work",
        workspace_id=TEAM_ID,
        external_sender_id=SENDER,
        app_id=APP_ID,
    )

    assert result["error"] == "authentication_required"


def test_you_cannot_connect_an_account_to_someone_elses_universe(
    universe, monkeypatch
):
    """The universe id is a request, not a grant."""
    _as(monkeypatch, STRANGER_ID)

    result = chat_surface.connect_account(
        universe_id="u-work",
        workspace_id=TEAM_ID,
        external_sender_id=SENDER,
        app_id=APP_ID,
    )

    assert result["error"] == "not_your_universe"


def test_you_cannot_bind_a_channel_to_someone_elses_universe(universe, monkeypatch):
    _as(monkeypatch, STRANGER_ID)

    result = chat_surface.bind_channel(
        universe_id="u-work",
        workspace_id=TEAM_ID,
        channel_id=CHANNEL_ALPHA,
        app_id=APP_ID,
    )

    assert result["error"] == "not_your_universe"


def test_the_connected_subject_is_the_authenticated_caller_not_a_field(
    universe, monkeypatch
):
    """A caller cannot name the subject their account maps to. It is derived
    from the authenticated identity, so `subject_id` is not even accepted."""
    from tinyassets.universe_server import _chat_surface_payload

    payload = _chat_surface_payload(
        json.dumps(
            {
                "universe_id": "u-work",
                "workspace_id": TEAM_ID,
                "external_sender_id": SENDER,
                "subject_id": STRANGER_ID,
                "bound_by": STRANGER_ID,
            }
        )
    )

    assert "subject_id" not in payload
    assert "bound_by" not in payload
    assert payload["universe_id"] == "u-work"


# --- the flow ---------------------------------------------------------------


def test_connecting_an_account_makes_that_sender_the_founder(universe, tmp_path):
    """The whole point: after this call, messages from that Slack account are
    founder turns."""
    result = chat_surface.connect_account(
        universe_id="u-work",
        workspace_id=TEAM_ID,
        external_sender_id=FOUNDER_ID,
        app_id=APP_ID,
    )
    assert result["connected"] is True
    assert result["universe_id"] == "u-work"

    grant = FounderRecognizer(tmp_path).recognize(
        _socket_event(tmp_path, event_id="Ev00SETUP01")
    )

    assert is_founder_grant(grant), "recognition now succeeds for that account"
    assert grant.subject_id == FOUNDER_ID


def test_an_unconnected_sender_is_still_a_visitor(universe, tmp_path):
    """Connecting one account must not promote everyone in the workspace."""
    chat_surface.connect_account(
        universe_id="u-work",
        workspace_id=TEAM_ID,
        external_sender_id="U0SOMEONEELSE",
        app_id=APP_ID,
    )

    grant = FounderRecognizer(tmp_path).recognize(
        _socket_event(tmp_path, event_id="Ev00SETUP02")
    )

    assert grant is None


def test_binding_a_channel_routes_it(universe, tmp_path, monkeypatch):
    _founder_universe(tmp_path, universe="u-hobby")

    result = chat_surface.bind_channel(
        universe_id="u-hobby",
        workspace_id=TEAM_ID,
        channel_id=CHANNEL_ALPHA,
        app_id=APP_ID,
    )

    assert result["bound"] is True
    assert result["scope"] == "channel"
    routed = ChannelRouter(tmp_path).route(
        provider="slack",
        installation_id=f"{APP_ID}:{TEAM_ID}",
        workspace_id=TEAM_ID,
        channel_id=CHANNEL_ALPHA,
    )
    assert routed.universe_id == "u-hobby"


def test_an_empty_channel_binds_the_whole_workspace(universe, tmp_path):
    result = chat_surface.bind_channel(
        universe_id="u-work", workspace_id=TEAM_ID, app_id=APP_ID
    )

    assert result["scope"] == "workspace"


def test_unbinding_reports_the_resolved_routing(universe, tmp_path):
    _founder_universe(tmp_path, universe="u-hobby")
    chat_surface.bind_channel(
        universe_id="u-work", workspace_id=TEAM_ID, app_id=APP_ID
    )
    chat_surface.bind_channel(
        universe_id="u-hobby",
        workspace_id=TEAM_ID,
        channel_id=CHANNEL_ALPHA,
        app_id=APP_ID,
    )

    result = chat_surface.unbind_channel(
        universe_id="u-work",
        workspace_id=TEAM_ID,
        channel_id=CHANNEL_ALPHA,
        app_id=APP_ID,
    )

    assert result["unbound"] is True
    assert CHANNEL_ALPHA not in result["routing"], "it no longer routes anywhere"


# --- what the user is shown -------------------------------------------------


def test_a_write_reports_the_RESOLVED_routing_not_the_row_written(
    universe, tmp_path
):
    """"What I intended is what happens" is only checkable against the
    resolution. Confirming the row just written would confirm the wrong thing:
    a forgotten channel binding is exactly what makes the default surprising.
    """
    _founder_universe(tmp_path, universe="u-hobby")
    chat_surface.bind_channel(
        universe_id="u-hobby",
        workspace_id=TEAM_ID,
        channel_id=CHANNEL_ALPHA,
        app_id=APP_ID,
    )

    # Now bind the workspace default. The confirmation must still surface the
    # pre-existing channel override, not just the default just written.
    result = chat_surface.bind_channel(
        universe_id="u-work", workspace_id=TEAM_ID, app_id=APP_ID
    )

    assert "u-work" in result["routing"]
    assert CHANNEL_ALPHA in result["routing"], "the override the user forgot"
    assert "u-hobby" in result["routing"]


def test_describe_states_where_messages_go(universe, tmp_path):
    result = chat_surface.describe(
        universe_id="u-work", workspace_id=TEAM_ID, app_id=APP_ID
    )

    assert "Everywhere in this workspace" in result["routing"]
    assert result["universe_id"] == "u-work"


def test_describing_a_workspace_with_no_app_credential_says_so(universe, tmp_path):
    """Routing cannot be described for a workspace this universe has no app in
    — answering "nothing bound" would be a confident wrong answer."""
    result = chat_surface.describe(universe_id="u-work", workspace_id=TEAM_ID)

    assert result["error"] == "no_slack_app_credential_for_universe"


# --- reachable from the handle ----------------------------------------------


def test_the_mcp_handle_dispatches_setup(universe, tmp_path, monkeypatch):
    """Reachability is the feature. An unreachable setup path is what this
    whole change exists to fix."""
    from tinyassets import universe_server

    monkeypatch.setattr(universe_server, "write_gate_rejection", lambda _h: "")
    raw = universe_server.write_graph(
        target="chat_surface",
        operation="bind_channel",
        graph_id="u-work",
        payload_json=json.dumps(
            {"workspace_id": TEAM_ID, "channel_id": CHANNEL_ALPHA, "app_id": APP_ID}
        ),
    )

    assert json.loads(raw)["bound"] is True


def test_an_unknown_setup_operation_names_what_is_allowed(universe, monkeypatch):
    from tinyassets import universe_server

    monkeypatch.setattr(universe_server, "write_gate_rejection", lambda _h: "")
    result = json.loads(
        universe_server.write_graph(
            target="chat_surface", operation="do_something_else", graph_id="u-work"
        )
    )

    assert result["error"] == "unknown_chat_surface_operation"
    assert "bind_channel" in result["allowed_operations"]


def test_adding_setup_advertises_no_new_tool():
    """Hard rule 11: the live catalog is pinned to seven handles. Setup is an
    ACTION on an existing one precisely so it cannot drift."""
    import scripts.mcp_public_canary as canary

    assert "chat_surface" not in canary.CANONICAL_HANDLES
    assert canary.CANONICAL_HANDLES == frozenset(
        {
            "read_graph",
            "write_graph",
            "run_graph",
            "read_page",
            "write_page",
            "converse",
            "get_status",
        }
    )
