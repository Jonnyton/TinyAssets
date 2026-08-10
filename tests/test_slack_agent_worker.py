"""The Slack agent as a deployed service.

`scripts/slack_live_test.py` proves the thing works but runs on somebody's
laptop. This module is the same agent as a container process, which is what the
Forever Rule actually requires — so the properties worth testing are the ones
that decide whether a droplet can hold it up unattended.
"""

from __future__ import annotations

import asyncio

import pytest

from tinyassets import slack_agent_worker as worker
from tinyassets.effectors.slack_agent_service import SlackAgentConfigError

TEAM = "T0BN5LK57FT"
APP = "A0BN1Q98MTQ"
APP_TOKEN = f"xapp-1-{APP}-1234567890123-exampleonly"
BOT_TOKEN = "xoxb-EXAMPLE-NOT-A-REAL-TOKEN"


@pytest.fixture
def universe(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = tmp_path / "u-worker"
    udir.mkdir()
    return udir


def _deposit(udir, connection="slack-main"):
    from tinyassets.credential_vault import write_credential_vault

    write_credential_vault(
        udir,
        [
            {
                "credential_type": "social",
                "service": "slack",
                "destination": connection,
                "bot_token": BOT_TOKEN,
                "app_token": APP_TOKEN,
            },
            # A second record so the write REPLACES rather than upserts.
            {
                "credential_type": "llm_subscription",
                "service": "claude",
                "claude_config_dir": str(udir / ".credentials" / "claude"),
            },
        ],
    )


# --- configuration ----------------------------------------------------------


def test_universes_come_from_the_environment(monkeypatch):
    monkeypatch.setenv(worker.UNIVERSES_ENV, " u-a , u-b ,, u-c ")

    assert worker.configured_universes() == ["u-a", "u-b", "u-c"]


def test_no_universes_configured_exits_nonzero(monkeypatch):
    monkeypatch.delenv(worker.UNIVERSES_ENV, raising=False)

    assert worker.main([]) == 1


def test_server_serving_state_enrolls_and_withdraws_a_universe(tmp_path, monkeypatch):
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.custom_agents import create_binding, publish_definition
    from tinyassets.provider_serving_binding import bind_serving_provider, set_serving

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = tmp_path / "u-dynamic"
    udir.mkdir()
    write_credential_vault(
        udir,
        [{
            "credential_type": "llm_subscription",
            "service": "codex",
            "auth_json_b64": "e30=",
        }],
    )
    definition = publish_definition(
        tmp_path,
        author_id="owner-dynamic",
        payload={
            "schema_version": 1,
            "name": "dynamic",
            "description": "test",
            "tags": ["test"],
            "components": {"identity": {"kind": "soul", "config": {}}},
        },
    )
    agent = create_binding(
        tmp_path,
        universe_id="u-dynamic",
        definition_id=definition["agent_definition_id"],
        created_by="owner-dynamic",
        payload={"schema_version": 1, "name": "dynamic", "role": "writer"},
    )
    connected = bind_serving_provider(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-dynamic",
        universe_id="u-dynamic",
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=1,
        provider="codex",
    )
    assert worker.dynamic_serving_universes() == []

    set_serving(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-dynamic",
        universe_id="u-dynamic",
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=connected["agent_binding"]["revision"],
        enabled=True,
    )
    assert worker.dynamic_serving_universes() == ["u-dynamic"]

    set_serving(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-dynamic",
        universe_id="u-dynamic",
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=connected["agent_binding"]["revision"],
        enabled=False,
    )
    assert worker.dynamic_serving_universes() == []


def test_credentials_are_never_read_from_the_environment(universe, monkeypatch):
    """One container serves several universes. If it took tokens from its own
    env, every universe would share one identity — the ambient-credential
    failure this platform has already been bitten by."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-AMBIENT-MUST-NOT-BE-USED")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-AMBIENT-MUST-NOT-BE-USED")

    with pytest.raises(SlackAgentConfigError) as exc:
        worker.build_config("u-worker", "slack-main")

    assert "no Slack bot token deposited" in str(exc.value)


def test_a_universe_with_no_deposit_is_skipped_not_fatal(universe, caplog):
    """One user's missing deposit must not silence everyone else's agent."""
    with caplog.at_level("ERROR"):
        asyncio.run(worker.serve_universe("u-worker", "slack-main"))

    assert "not started" in caplog.text
    assert "no Slack bot token deposited" in caplog.text


def test_the_config_is_built_from_the_vault_and_slack(universe, monkeypatch):
    _deposit(universe)
    monkeypatch.setattr(worker, "_identify", lambda _t: (TEAM, "U08BOT0001"))

    config = worker.build_config("u-worker", "slack-main")

    assert config.team_id == TEAM
    assert config.bot_user_id == "U08BOT0001"
    assert config.api_app_id == APP, "derived from the app token, not configured"
    assert config.universe_dir == universe


def test_a_rejected_bot_token_names_slacks_reason(universe, monkeypatch):
    _deposit(universe)
    monkeypatch.setattr(
        worker,
        "_identify",
        lambda _t: (_ for _ in ()).throw(
            SlackAgentConfigError("slack rejected the bot token: invalid_auth")
        ),
    )

    with pytest.raises(SlackAgentConfigError) as exc:
        worker.build_config("u-worker", "slack-main")

    assert "invalid_auth" in str(exc.value)
    assert BOT_TOKEN not in str(exc.value)


# --- lifetime ---------------------------------------------------------------


def test_a_permanently_failed_universe_does_not_kill_the_process(universe, monkeypatch, caplog):
    """A revoked token stops THAT universe. The container keeps serving the rest."""
    from tinyassets.effectors.slack_socket_runner import SocketModePermanentError

    _deposit(universe)
    monkeypatch.setattr(worker, "_identify", lambda _t: (TEAM, "U08BOT0001"))

    async def _boom(_config):
        raise SocketModePermanentError("slack refused the socket permanently: token_revoked")

    monkeypatch.setattr(worker, "run_slack_agent", _boom)

    with caplog.at_level("ERROR"):
        asyncio.run(worker.serve_universe("u-worker", "slack-main"))

    assert "stopped permanently" in caplog.text
    assert "token_revoked" in caplog.text


def test_serve_all_with_nothing_to_serve_reports_failure():
    assert asyncio.run(worker.serve_all([], "slack-main")) == 1


@pytest.mark.asyncio
async def test_one_universe_finishing_does_not_cancel_the_others(monkeypatch):
    """Cross-family review, HIGH: `wait(FIRST_COMPLETED)` over the individual
    tasks meant the first universe to finish — a missing deposit returns
    immediately — cancelled every other universe. One tenant could drop all of
    them, which is the opposite of what this module promises."""
    started: list[str] = []
    finished: list[str] = []

    async def _fake_serve(universe_id: str, _connection: str) -> None:
        started.append(universe_id)
        if universe_id == "u-fails-fast":
            return                      # e.g. no credentials deposited
        await asyncio.sleep(0.25)       # a healthy long-lived socket
        finished.append(universe_id)

    monkeypatch.setattr(worker, "serve_universe", _fake_serve)

    rc = await worker.serve_all(["u-fails-fast", "u-healthy-a", "u-healthy-b"], "c")

    assert rc == 0
    assert set(started) == {"u-fails-fast", "u-healthy-a", "u-healthy-b"}
    assert set(finished) == {"u-healthy-a", "u-healthy-b"}, (
        "the healthy universes must run to completion, not be cancelled by the "
        "one that returned first"
    )


@pytest.mark.asyncio
async def test_an_unexpected_failure_is_logged_not_swallowed(monkeypatch, caplog):
    """Fault isolation must not become fault silence.

    `gather(return_exceptions=True)` is what stops one universe cancelling the
    others, but it also eats whatever they raise. During the first real
    deployment a PermissionError reading a vault surfaced as a clean `exit 0`
    with nothing in the log — twice.
    """
    async def _boom(_uid, _conn):
        raise PermissionError("/data/u-x/.credential-vault.json")

    monkeypatch.setattr(worker, "serve_universe", _boom)

    with caplog.at_level("ERROR"):
        rc = await worker.serve_all(["u-x"], "slack-main")

    assert rc == 0, "the process still exits cleanly"
    assert "failed unexpectedly" in caplog.text
    assert "PermissionError" in caplog.text


@pytest.mark.asyncio
async def test_reconciler_adds_and_cancels_dynamic_serving_without_restart(monkeypatch):
    stop = asyncio.Event()
    states = [[], ["u-dynamic"], []]
    calls = 0
    started: list[str] = []
    cancelled: list[str] = []

    def _source():
        nonlocal calls
        state = states[min(calls, len(states) - 1)]
        calls += 1
        if calls >= 3:
            stop.set()
        return state

    async def _serve(uid, _connection):
        started.append(uid)
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(uid)

    monkeypatch.setattr(worker, "serve_universe", _serve)
    rc = await worker.serve_reconciling(
        [],
        "slack-main",
        enrollment_source=_source,
        poll_interval_s=0.001,
        stopping=stop,
        install_signal_handlers=False,
    )

    assert rc == 0
    assert started == ["u-dynamic"]
    assert cancelled == ["u-dynamic"]
