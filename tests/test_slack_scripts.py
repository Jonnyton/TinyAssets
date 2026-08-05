"""Regression tests for the two Slack scripts.

A reviewer's sharpest finding was not a bug in them but that they had NO
coverage: reverting either script's security fix left all 191 scoped tests
green. A fix nothing can turn red is a fix waiting to be undone.

Both scripts are loaded by path, since `scripts/` is not a package.
"""

from __future__ import annotations

import importlib.util
import traceback
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deposit = _load("deposit_slack_credentials")
runner = _load("run_slack_agent")

SECRET_APP = "xapp-1-A0BN1Q98MTQ-1234567890123-secretvalue"
SECRET_BOT = "xoxb-EXAMPLE-BOT-CREDENTIAL"


def _rendered(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


# --- token leaks through the scripts ----------------------------------------


@pytest.mark.parametrize("module_name", ["deposit", "runner"])
def test_a_network_failure_never_carries_the_token(module_name, monkeypatch):
    """`from None` inside the handler left the URLError on __context__."""
    import urllib.error

    module = {"deposit": deposit, "runner": runner}[module_name]

    def _boom(*_a, **_kw):
        raise urllib.error.URLError(f"Authorization: Bearer {SECRET_BOT}")

    monkeypatch.setattr(module.urllib.request, "urlopen", _boom)
    call = module._call if module_name == "deposit" else module.identify

    with pytest.raises(SystemExit) as exc:
        call(module.AUTH_TEST_URL, SECRET_BOT) if module_name == "deposit" else call(
            SECRET_BOT
        )

    assert SECRET_BOT not in _rendered(exc.value)
    assert SECRET_BOT not in repr(exc.value.args)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None


def test_an_inband_slack_error_cannot_echo_the_token_from_the_depositor(monkeypatch):
    """Slack reports failure with HTTP 200; `error` is upstream text."""
    monkeypatch.setattr(
        deposit, "_call", lambda *_a: {"ok": False, "error": f"invalid {SECRET_BOT}"}
    )

    with pytest.raises(SystemExit) as exc:
        deposit.verify_bot_token(SECRET_BOT)

    assert SECRET_BOT not in str(exc.value)
    assert "unknown_error" in str(exc.value)


def test_an_inband_slack_error_cannot_echo_the_token_from_the_runner(monkeypatch):
    import json as _json

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self):
            return _json.dumps(
                {"ok": False, "error": f"invalid {SECRET_BOT}"}
            ).encode()

    monkeypatch.setattr(runner.urllib.request, "urlopen", lambda *_a, **_k: _Response())

    with pytest.raises(SystemExit) as exc:
        runner.identify(SECRET_BOT)

    assert SECRET_BOT not in str(exc.value)
    assert "unknown_error" in str(exc.value)


# --- the depositor must not destroy or duplicate other connections ----------


def _deposit_into(tmp_path, connection, bot, app, monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", bot)
    monkeypatch.setenv("SLACK_APP_TOKEN", app)
    monkeypatch.setattr(
        "sys.argv",
        [
            "deposit",
            "--universe-dir",
            str(tmp_path),
            "--connection",
            connection,
            "--skip-verify",
        ],
    )
    deposit.main()


def test_depositing_a_second_connection_keeps_the_first(tmp_path, monkeypatch):
    """It used to DELETE it: the vault's single-record upsert keys on
    (type, service) and ignores the connection."""
    from tinyassets.credential_vault import resolve_slack_token

    _deposit_into(tmp_path, "conn-a", "xoxb-AAA", "xapp-1-A0AAAAAAAA-1-a", monkeypatch)
    _deposit_into(tmp_path, "conn-b", "xoxb-BBB", "xapp-1-A0BBBBBBBB-1-b", monkeypatch)

    assert resolve_slack_token(tmp_path, "conn-a") == "xoxb-AAA"
    assert resolve_slack_token(tmp_path, "conn-b") == "xoxb-BBB"


def test_a_whitespace_variant_connection_id_replaces_rather_than_duplicates(
    tmp_path, monkeypatch
):
    """Reviewer's counterexample: ` conn-b ` produced a duplicate record and the
    STALE token kept resolving, so a rotation silently kept the old bot."""
    from tinyassets.credential_vault import load_credential_vault, resolve_slack_token

    _deposit_into(tmp_path, "conn-b", "xoxb-OLD", "xapp-1-A0BBBBBBBB-1-b", monkeypatch)
    _deposit_into(
        tmp_path, "  conn-b  ", "xoxb-NEW", "xapp-1-A0BBBBBBBB-1-b", monkeypatch
    )

    destinations = [
        r.get("destination")
        for r in load_credential_vault(tmp_path)
        if r.get("credential_type") == "social"
    ]
    assert destinations == ["conn-b"], "no duplicate record"
    assert resolve_slack_token(tmp_path, "conn-b") == "xoxb-NEW", "rotation took effect"


def test_a_blank_connection_id_is_refused(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        _deposit_into(tmp_path, "   ", "xoxb-A", "xapp-1-A0AAAAAAAA-1-a", monkeypatch)


# --- token types are checked even with --skip-verify ------------------------


def test_skip_verify_still_refuses_a_user_token(tmp_path, monkeypatch):
    """It skipped the local checks along with the network round trip, so a
    deposit could 'succeed' with a token that posts under a person's name."""
    with pytest.raises(SystemExit) as exc:
        _deposit_into(
            tmp_path, "conn-a", "xoxp-USER", "xapp-1-A0AAAAAAAA-1-a", monkeypatch
        )

    assert "not a bot token" in str(exc.value)


def test_skip_verify_still_refuses_a_non_app_token(tmp_path, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _deposit_into(tmp_path, "conn-a", "xoxb-AAA", "xoxb-NOT-APP", monkeypatch)

    assert "app-level token" in str(exc.value)


# --- the app id is derived, not left opt-in ---------------------------------


def test_the_app_id_is_derived_from_the_app_token():
    """A reviewer found the api_app_id check was opt-in and production never
    set it — a field wired to nothing. It is derivable, so nothing to look up."""
    from tinyassets.effectors.slack_socket_mode import app_id_from_token

    assert app_id_from_token(SECRET_APP) == "A0BN1Q98MTQ"


@pytest.mark.parametrize(
    "token",
    ["xapp-EXAMPLE-NOT-A-REAL-TOKEN", "xapp-1", "xoxb-bot", "", None, "xapp-1-lower-2-3"],
)
def test_an_underivable_app_id_is_empty_rather_than_guessed(token):
    """Empty means the check is not applied — the position before it existed —
    rather than a wrong id that refuses every real event."""
    from tinyassets.effectors.slack_socket_mode import app_id_from_token

    assert app_id_from_token(token) == ""


def test_the_launcher_passes_the_derived_app_id_into_the_config(tmp_path, monkeypatch):
    """The wiring itself, since the field being present proves nothing."""
    from tinyassets.credential_vault import write_credential_vault

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = tmp_path / "u-wire"
    udir.mkdir()
    write_credential_vault(
        udir,
        [
            {
                "credential_type": "social",
                "service": "slack",
                "destination": "slack-main",
                "bot_token": SECRET_BOT,
                "app_token": SECRET_APP,
            }
        ],
    )

    captured = {}

    monkeypatch.setattr(
        runner, "identify", lambda _t: ("T0BN5LK57FT", "U08BOT0001", "Test")
    )

    async def _fake_run(config, **_kw):
        captured["api_app_id"] = config.api_app_id
        return 0

    monkeypatch.setattr(runner, "run_slack_agent", _fake_run)
    monkeypatch.setattr("sys.argv", ["run", "--universe-id", "u-wire"])

    runner.main()

    assert captured["api_app_id"] == "A0BN1Q98MTQ", "production must set it"
