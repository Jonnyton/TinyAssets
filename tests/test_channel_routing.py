"""Which universe answers where.

Users keep several universes — work, personal, hobby — and one Slack workspace
may need to reach more than one. The rule is deliberately singular: **most
specific wins**. A channel binding beats the workspace default, and with
neither, the universe whose vault opened the socket answers.

The tests worth having are the ones about what must NOT happen: routing into a
universe the binder no longer owns, a channel binding being shadowed by a
workspace default, and a routed message reading the wrong universe's grounding.
"""

from __future__ import annotations

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
from tinyassets.app_channel_routing import ChannelRouter, describe_routing
from tinyassets.app_principal_mapping import AppPrincipalMappingService
from tinyassets.daemon_server import revoke_universe_access
from tinyassets.founder_grant import FounderRecognizer, is_founder_grant
from tinyassets.storage.app_channel_bindings import (
    WORKSPACE_SCOPE,
    AppChannelBindingError,
    AppChannelBindingStore,
)

INSTALLATION = f"{APP_ID}:{TEAM_ID}"
CHANNEL_ALPHA = "C0ALPHA0001"
CHANNEL_BETA = "C0BETA00001"


def _store(base: Path) -> AppChannelBindingStore:
    return AppChannelBindingStore(base)


def _bind(base: Path, *, channel: str, target, by: str = FOUNDER_ID):
    return _store(base).bind(
        provider="slack",
        installation_id=INSTALLATION,
        workspace_id=TEAM_ID,
        channel_id=channel,
        universe_id=target.universe_id,
        agent_binding_id=target.agent_binding_id,
        binding_revision=target.binding_revision,
        bound_by=by,
    )


def _route(base: Path, *, channel: str, fallback: str = ""):
    return ChannelRouter(base).route(
        provider="slack",
        installation_id=INSTALLATION,
        workspace_id=TEAM_ID,
        channel_id=channel,
        fallback_universe_id=fallback,
    )


# --- the rule ---------------------------------------------------------------


def test_a_channel_binding_beats_the_workspace_default(tmp_path: Path) -> None:
    work = _founder_universe(tmp_path, universe="u-work")
    hobby = _founder_universe(tmp_path, universe="u-hobby")
    _bind(tmp_path, channel=WORKSPACE_SCOPE, target=work)
    _bind(tmp_path, channel=CHANNEL_ALPHA, target=hobby)

    assert _route(tmp_path, channel=CHANNEL_ALPHA).universe_id == "u-hobby"
    assert _route(tmp_path, channel=CHANNEL_BETA).universe_id == "u-work"


def test_the_matched_scope_is_reported(tmp_path: Path) -> None:
    """A confirmation has to be able to say WHY a message routes where it does."""
    work = _founder_universe(tmp_path, universe="u-work")
    hobby = _founder_universe(tmp_path, universe="u-hobby")
    _bind(tmp_path, channel=WORKSPACE_SCOPE, target=work)
    _bind(tmp_path, channel=CHANNEL_ALPHA, target=hobby)

    assert _route(tmp_path, channel=CHANNEL_ALPHA).matched_scope == "channel"
    assert _route(tmp_path, channel=CHANNEL_BETA).matched_scope == "workspace"
    assert _route(tmp_path, channel=CHANNEL_BETA, fallback="x").matched_scope == (
        "workspace"
    ), "a bound default must not be overridden by the connection fallback"


def test_with_nothing_bound_the_socket_host_answers(tmp_path: Path) -> None:
    """Zero configuration: install the app for one universe and it just works."""
    routed = _route(tmp_path, channel=CHANNEL_ALPHA, fallback="u-host")

    assert routed.universe_id == "u-host"
    assert routed.matched_scope == "connection"


def test_with_nothing_bound_and_no_host_the_answer_is_silence(tmp_path: Path) -> None:
    assert _route(tmp_path, channel=CHANNEL_ALPHA) is None


def test_rebinding_a_scope_replaces_it(tmp_path: Path) -> None:
    """"Point #alpha at my other universe" is an ordinary thing to want, and
    making the user unbind first would leave a window routing nowhere."""
    work = _founder_universe(tmp_path, universe="u-work")
    hobby = _founder_universe(tmp_path, universe="u-hobby")
    _bind(tmp_path, channel=CHANNEL_ALPHA, target=work)
    _bind(tmp_path, channel=CHANNEL_ALPHA, target=hobby)

    assert _route(tmp_path, channel=CHANNEL_ALPHA).universe_id == "u-hobby"
    assert len(_store(tmp_path).list_for_workspace(
        provider="slack", installation_id=INSTALLATION, workspace_id=TEAM_ID
    )) == 1, "replaced, not duplicated"


def test_unbinding_falls_back_to_the_default(tmp_path: Path) -> None:
    work = _founder_universe(tmp_path, universe="u-work")
    hobby = _founder_universe(tmp_path, universe="u-hobby")
    _bind(tmp_path, channel=WORKSPACE_SCOPE, target=work)
    _bind(tmp_path, channel=CHANNEL_ALPHA, target=hobby)

    removed = _store(tmp_path).unbind(
        provider="slack",
        installation_id=INSTALLATION,
        workspace_id=TEAM_ID,
        channel_id=CHANNEL_ALPHA,
    )

    assert removed is True
    assert _route(tmp_path, channel=CHANNEL_ALPHA).universe_id == "u-work"


# --- what must not happen ---------------------------------------------------


def test_a_binding_stops_routing_when_its_owner_loses_access(tmp_path: Path) -> None:
    """A binding is a claim, not a standing grant. Without re-derivation,
    revoking someone's access would leave their old binding routing messages
    into a universe they no longer own."""
    hobby = _founder_universe(tmp_path, universe="u-hobby")
    _bind(tmp_path, channel=CHANNEL_ALPHA, target=hobby)
    assert _route(tmp_path, channel=CHANNEL_ALPHA).universe_id == "u-hobby"

    revoke_universe_access(tmp_path, universe_id="u-hobby", actor_id=FOUNDER_ID)

    assert _route(tmp_path, channel=CHANNEL_ALPHA) is None, "silence, not fallback"


def test_a_stale_binding_does_not_fall_through_to_the_default(tmp_path: Path) -> None:
    """Falling back would answer as the workspace default in a channel the user
    deliberately pointed elsewhere — the surprising-outcome failure."""
    work = _founder_universe(tmp_path, universe="u-work")
    hobby = _founder_universe(tmp_path, universe="u-hobby")
    _bind(tmp_path, channel=WORKSPACE_SCOPE, target=work)
    _bind(tmp_path, channel=CHANNEL_ALPHA, target=hobby)

    revoke_universe_access(tmp_path, universe_id="u-hobby", actor_id=FOUNDER_ID)

    assert _route(tmp_path, channel=CHANNEL_ALPHA) is None


def test_a_binding_by_a_non_owner_routes_nowhere(tmp_path: Path) -> None:
    """Otherwise one user's workspace could route into another user's universe."""
    hobby = _founder_universe(tmp_path, universe="u-hobby")
    _bind(tmp_path, channel=CHANNEL_ALPHA, target=hobby, by=STRANGER_ID)

    assert _route(tmp_path, channel=CHANNEL_ALPHA) is None


def test_a_rotated_agent_binding_stops_routing(tmp_path: Path) -> None:
    from tinyassets.custom_agents import update_binding

    hobby = _founder_universe(tmp_path, universe="u-hobby")
    _bind(tmp_path, channel=CHANNEL_ALPHA, target=hobby)

    update_binding(
        tmp_path,
        universe_id="u-hobby",
        binding_id=hobby.agent_binding_id,
        updated_by=FOUNDER_ID,
        expected_revision=hobby.binding_revision,
        payload={"schema_version": 1, "name": "Rotated", "model": "other"},
    )

    assert _route(tmp_path, channel=CHANNEL_ALPHA) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("universe_id", ""),
        ("universe_id", "u-with space"),
        ("bound_by", ""),
        ("channel_id", " C0PAD "),
        ("binding_revision", 0),
        ("binding_revision", True),
    ],
)
def test_malformed_bindings_are_refused(tmp_path: Path, field, value) -> None:
    target = _founder_universe(tmp_path, universe="u-work")
    kwargs = dict(
        provider="slack",
        installation_id=INSTALLATION,
        workspace_id=TEAM_ID,
        channel_id=CHANNEL_ALPHA,
        universe_id=target.universe_id,
        agent_binding_id=target.agent_binding_id,
        binding_revision=target.binding_revision,
        bound_by=FOUNDER_ID,
    )
    kwargs[field] = value

    with pytest.raises(AppChannelBindingError):
        _store(tmp_path).bind(**kwargs)


# --- founder recognition follows the routing --------------------------------


def test_the_founder_is_recognized_on_the_ROUTED_universe(tmp_path: Path) -> None:
    """The point of the whole feature: one Slack identity, several universes.

    The mapping was created against u-work; the channel routes to u-hobby. The
    sender owns both, so they are the founder in both places.
    """
    work = _founder_universe(tmp_path, universe="u-work")
    hobby = _founder_universe(tmp_path, universe="u-hobby")
    service = AppPrincipalMappingService(tmp_path)
    service.provision(_socket_event(tmp_path), resolve_target=lambda _key: work)
    recognizer = FounderRecognizer(tmp_path, mapping=service)

    grant = recognizer.recognize(
        _socket_event(tmp_path, event_id="Ev00ROUTE01"),
        universe_id=hobby.universe_id,
        agent_binding_id=hobby.agent_binding_id,
        binding_revision=hobby.binding_revision,
    )

    assert is_founder_grant(grant)
    assert grant.universe_id == "u-hobby", "the grant follows the routing"


def test_routing_into_a_universe_you_do_not_own_grants_nothing(tmp_path: Path) -> None:
    """Being the founder of the socket's host universe says NOTHING about the
    one a channel binding pointed this message at."""
    work = _founder_universe(tmp_path, universe="u-work")
    other = _founder_universe(tmp_path, universe="u-not-mine", subject=STRANGER_ID)
    service = AppPrincipalMappingService(tmp_path)
    service.provision(_socket_event(tmp_path), resolve_target=lambda _key: work)
    recognizer = FounderRecognizer(tmp_path, mapping=service)

    grant = recognizer.recognize(
        _socket_event(tmp_path, event_id="Ev00ROUTE02"),
        universe_id=other.universe_id,
        agent_binding_id=other.agent_binding_id,
        binding_revision=other.binding_revision,
    )

    assert grant is None


def test_the_resolver_routes_and_reads_the_routed_universes_directory(
    tmp_path: Path, monkeypatch
) -> None:
    """A routed message must not read the socket host's grounding — that is the
    multi-universe version of answering as somebody else."""
    from tinyassets.effectors.slack_agent_service import SlackAgentConfig, build_resolver

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _founder_universe(tmp_path, universe="u-work")
    hobby = _founder_universe(tmp_path, universe="u-hobby")
    _bind(tmp_path, channel=CHANNEL_ALPHA, target=hobby)

    config = SlackAgentConfig(
        universe_id="u-work",
        connection_id="slack-main",
        team_id=TEAM_ID,
        bot_user_id="U08BOT0001",
        api_app_id=APP_ID,
    )
    resolve = build_resolver(config, recognize=lambda _e, _r=None: None)
    binding = resolve(
        {
            "type": "app_mention",
            "user": FOUNDER_ID,
            "text": "hi",
            "channel": CHANNEL_ALPHA,
            "team_id": TEAM_ID,
            "api_app_id": APP_ID,
            "event_id": "Ev00ROUTE03",
            "actor_team_id": TEAM_ID,
        }
    )

    assert binding is not None
    assert binding.universe_id == "u-hobby"
    assert binding.universe_dir.name == "u-hobby", (
        "the routed universe's own directory, not the socket host's"
    )


def test_routing_failing_silences_the_turn_rather_than_guessing(
    tmp_path: Path, monkeypatch
) -> None:
    """A routing outage must not reroute to the connection fallback: that would
    answer as the socket's host universe in a channel the user deliberately
    pointed somewhere else."""
    from tinyassets.effectors import slack_agent_service as svc
    from tinyassets.effectors.slack_agent_service import SlackAgentConfig

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _founder_universe(tmp_path, universe="u-work")
    monkeypatch.setattr(
        svc,
        "_route_universe",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("routing db down")),
    )

    config = SlackAgentConfig(
        universe_id="u-work",
        connection_id="slack-main",
        team_id=TEAM_ID,
        bot_user_id="U08BOT0001",
        api_app_id=APP_ID,
    )
    binding = svc.build_resolver(config, recognize=lambda _e, _r=None: None)(
        {
            "type": "app_mention",
            "user": FOUNDER_ID,
            "text": "hi",
            "channel": CHANNEL_ALPHA,
            "team_id": TEAM_ID,
            "api_app_id": APP_ID,
            "event_id": "Ev00ROUTE04",
            "actor_team_id": TEAM_ID,
        }
    )

    assert binding is None, "silence, not a guess at which universe answers"


# --- reading the routing back -----------------------------------------------


def test_describe_routing_states_the_resolved_answer(tmp_path: Path) -> None:
    """Expressiveness comes from the primitive; "what I intended happened"
    comes from showing the resolved result."""
    work = _founder_universe(tmp_path, universe="u-work")
    hobby = _founder_universe(tmp_path, universe="u-hobby")
    _bind(tmp_path, channel=WORKSPACE_SCOPE, target=work)
    _bind(tmp_path, channel=CHANNEL_ALPHA, target=hobby)

    text = describe_routing(
        ChannelRouter(tmp_path).effective_routing(
            provider="slack", installation_id=INSTALLATION, workspace_id=TEAM_ID
        )
    )

    assert "Everywhere in this workspace: u-work" in text
    assert f"except in {CHANNEL_ALPHA}: u-hobby" in text


def test_describe_routing_names_the_fallback_when_nothing_is_bound() -> None:
    assert "u-host" in describe_routing([], fallback_universe_id="u-host")


def test_describe_routing_says_silence_when_there_is_no_answer() -> None:
    assert "silent" in describe_routing([])
