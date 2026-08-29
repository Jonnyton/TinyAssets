"""The app's refresh-token store is sealed, handle-bound, and rotates.

Every assertion here observes an outcome the PLAINTEXT store failed:

- it wrote the raw WorkOS refresh token to a JSON file any reader of the data dir
  could open (``{"rt": ...}``), so a record was portable between handles;
- the token endpoint filed the token under a handle the CALLER chose;
- the handle never changed, so one capture lasted the full 7-day TTL;
- the seal key, once introduced, would have been inherited by every provider
  subprocess spawned from this process.

The endpoint harness is imported from ``test_onboarding_session_refresh`` rather
than rebuilt -- a second copy of the AuthKit fake is a second thing to drift.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import time

import httpx
import pytest

from tests.test_onboarding_session_refresh import _drive, _ok
from tinyassets import onboarding
from tinyassets.onboarding import session_store

CODE_EXCHANGE = {
    "code": "c",
    "code_verifier": "v",
    "redirect_uri": "https://tinyassets.io/mcp/app",
}


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """A fresh data dir AND a fresh key singleton for every test.

    Without the reset the first test's ephemeral key seals records the next test
    cannot open, and the one-time legacy discard would run for the first tmp dir
    only.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv(session_store.SEAL_KEY_ENV, raising=False)
    session_store._reset_for_tests()
    yield tmp_path
    session_store._reset_for_tests()


def _records() -> list:
    return sorted(session_store.store_dir().glob("*.json"))


# --- 1. sealed at rest --------------------------------------------------------


def test_the_stored_token_is_nowhere_in_the_file():
    """The plaintext store wrote `{"rt": "<the token>"}`. Nothing may carry it."""
    token = "RT-" + secrets.token_urlsafe(24)
    handle = session_store.mint(token)
    files = _records()
    assert len(files) == 1, files
    blob = files[0].read_bytes()
    assert token.encode("utf-8") not in blob, "the refresh token is on disk in clear"
    record = json.loads(blob.decode("utf-8"))
    assert "rt" not in record, record
    assert set(record) == {"v", "nonce", "ct", "exp", "superseded_by", "grace_until"}
    assert token not in json.dumps(record)
    # ...and it still opens for its own handle.
    assert session_store.read(handle) == (token, handle)


def test_no_file_under_the_store_contains_the_token_bytes():
    """Belt and braces: scan the whole directory, including any stray temp file."""
    token = "RT-" + secrets.token_urlsafe(24)
    handle = session_store.mint(token)
    session_store.rotate(handle, token + "-next")
    for path in session_store.store_dir().iterdir():
        assert token.encode("utf-8") not in path.read_bytes(), path


# --- 2. handle binding --------------------------------------------------------


def test_a_record_copied_onto_another_handle_does_not_open():
    """AAD is the handle. Without it, moving the file moves the session."""
    victim_token = "RT-victim"
    victim = session_store.mint(victim_token)
    attacker = secrets.token_urlsafe(32)
    assert session_store.valid_handle(attacker)
    source = session_store._record_path(victim)
    target = session_store._record_path(attacker)
    target.write_bytes(source.read_bytes())
    assert session_store.read(attacker) == ("", "")
    # The victim's own handle is untouched by the failed theft.
    assert session_store.read(victim) == (victim_token, victim)


# --- 3. fixation --------------------------------------------------------------


def test_a_signin_never_stores_under_the_handle_the_caller_sent(monkeypatch, tmp_path):
    planted = secrets.token_urlsafe(32)
    status, doc, _, _ = _drive(
        dict(CODE_EXCHANGE, session_ref=planted),
        monkeypatch=monkeypatch,
        upstream=lambda f: _ok("a1", "RT1"),
        data_dir=str(tmp_path),
    )
    assert status == 200
    assert doc["session_ref"] != planted
    assert not session_store._record_path(planted).exists()
    assert session_store.read(planted) == ("", "")
    # The minted handle is the only live session.
    assert session_store.read(doc["session_ref"])[0] == "RT1"
    assert len(_records()) == 1


def test_a_refresh_that_succeeded_off_the_cookie_does_not_adopt_the_handle(
    monkeypatch, tmp_path
):
    """The 2026-08-28 correction, restated against the new store: the presented
    handle resolved to nothing, so the rotated token must not land under it."""
    planted = secrets.token_urlsafe(32)
    status, doc, _, _ = _drive(
        {"grant_type": "refresh_token", "session_ref": planted},
        cookie="ta_rt=COOKIE-RT",
        monkeypatch=monkeypatch,
        upstream=lambda f: _ok("a1", "RT-NEW"),
        data_dir=str(tmp_path),
    )
    assert status == 200
    assert doc["session_ref"] != planted
    assert not session_store._record_path(planted).exists()


# --- 4. rotation and grace ----------------------------------------------------


def test_a_refresh_rotates_the_handle_and_the_old_one_lives_only_in_grace(
    monkeypatch, tmp_path
):
    dd = str(tmp_path)
    _, doc, _, _ = _drive(
        CODE_EXCHANGE,
        monkeypatch=monkeypatch,
        upstream=lambda f: _ok("a1", "RT1"),
        data_dir=dd,
    )
    first = doc["session_ref"]
    assert len(_records()) == 1

    status, doc, _, calls = _drive(
        {"grant_type": "refresh_token", "session_ref": first},
        monkeypatch=monkeypatch,
        upstream=lambda f: _ok("a2", "RT2"),
        data_dir=dd,
    )
    assert status == 200
    assert calls[0]["refresh_token"] == "RT1"
    second = doc["session_ref"]
    assert second != first, "the handle must not survive a rotation unchanged"

    assert session_store.read(second) == ("RT2", second)
    # The old handle follows ONE hop during grace -- and resolves to the SUCCESSOR
    # handle, so the next rotation starts from the live record, not the stale one.
    assert session_store.read(first) == ("RT2", second)
    # Exactly two records: the grace tombstone and the live one. A third would
    # mean the grace read minted instead of following.
    assert len(_records()) == 2

    later = time.time() + session_store.GRACE_SECONDS + 1
    monkeypatch.setattr(session_store.time, "time", lambda: later)
    assert session_store.read(first) == ("", "")
    assert session_store.read(second) == ("RT2", second)


def test_the_old_handle_is_dead_at_the_endpoint_once_grace_expires(
    monkeypatch, tmp_path
):
    """Past grace, presenting the old handle must not renew anyone's session."""
    dd = str(tmp_path)
    _, doc, _, _ = _drive(
        CODE_EXCHANGE,
        monkeypatch=monkeypatch,
        upstream=lambda f: _ok("a1", "RT1"),
        data_dir=dd,
    )
    first = doc["session_ref"]
    _drive(
        {"grant_type": "refresh_token", "session_ref": first},
        monkeypatch=monkeypatch,
        upstream=lambda f: _ok("a2", "RT2"),
        data_dir=dd,
    )
    later = time.time() + session_store.GRACE_SECONDS + 1
    monkeypatch.setattr(session_store.time, "time", lambda: later)

    def _boom(_form):
        raise AssertionError("a dead handle must not reach AuthKit")

    status, doc, _, calls = _drive(
        {"grant_type": "refresh_token", "session_ref": first},
        monkeypatch=monkeypatch,
        upstream=_boom,
        data_dir=dd,
    )
    assert (status, doc, calls) == (401, {"error": "no_refresh_token"}, [])


def test_logout_kills_the_successor_too(monkeypatch, tmp_path):
    """Otherwise signing out leaves the CURRENT session renewable."""
    dd = str(tmp_path)
    _, doc, _, _ = _drive(
        CODE_EXCHANGE,
        monkeypatch=monkeypatch,
        upstream=lambda f: _ok("a1", "RT1"),
        data_dir=dd,
    )
    first = doc["session_ref"]
    _, doc, _, _ = _drive(
        {"grant_type": "refresh_token", "session_ref": first},
        monkeypatch=monkeypatch,
        upstream=lambda f: _ok("a2", "RT2"),
        data_dir=dd,
    )
    second = doc["session_ref"]
    # A tab that never saw the rotation signs out with the OLD handle.
    _drive(
        {"grant_type": "logout", "session_ref": first},
        monkeypatch=monkeypatch,
        upstream=lambda f: httpx.Response(500),
        data_dir=dd,
    )
    assert session_store.read(first) == ("", "")
    assert session_store.read(second) == ("", "")
    assert _records() == []


def test_authkit_returning_no_new_token_reuses_the_current_handle_without_writing(
    monkeypatch, tmp_path
):
    dd = str(tmp_path)
    _, doc, _, _ = _drive(
        CODE_EXCHANGE,
        monkeypatch=monkeypatch,
        upstream=lambda f: _ok("a1", "RT1"),
        data_dir=dd,
    )
    first = doc["session_ref"]
    before = session_store._record_path(first).read_bytes()
    status, doc, _, _ = _drive(
        {"grant_type": "refresh_token", "session_ref": first},
        monkeypatch=monkeypatch,
        upstream=lambda f: httpx.Response(
            200, json={"access_token": "a2", "expires_in": 300}
        ),
        data_dir=dd,
    )
    assert (status, doc["session_ref"]) == (200, first)
    assert session_store._record_path(first).read_bytes() == before
    assert len(_records()) == 1


# --- 5. key hygiene -----------------------------------------------------------


def test_the_seal_key_is_removed_from_the_environment_on_load(monkeypatch):
    """Provider children get a COPY of os.environ. A key left here is a key in
    every `claude -p` / `codex exec` subprocess the daemon starts."""
    from tinyassets.providers import base as provider_base

    raw = base64.urlsafe_b64encode(b"K" * 32).decode("ascii")
    monkeypatch.setenv(session_store.SEAL_KEY_ENV, raw)
    monkeypatch.delenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", raising=False)
    assert os.environ.get(session_store.SEAL_KEY_ENV) == raw

    assert session_store.seal_key() == b"K" * 32

    assert session_store.SEAL_KEY_ENV not in os.environ
    child_env = provider_base.subprocess_env_without_api_keys()
    assert isinstance(child_env, dict), "api-key providers must be disabled here"
    assert session_store.SEAL_KEY_ENV not in child_env
    assert session_store.SEAL_KEY_ENV not in provider_base._safe_provider_child_base_env()
    # And the key really is the configured one, not a fresh ephemeral.
    handle = session_store.mint("RT-configured")
    session_store._key = None
    monkeypatch.setenv(session_store.SEAL_KEY_ENV, raw)
    assert session_store.read(handle) == ("RT-configured", handle)


def test_a_hex_seal_key_is_accepted_too(monkeypatch):
    monkeypatch.setenv(session_store.SEAL_KEY_ENV, ("ab" * 32))
    assert session_store.seal_key() == bytes.fromhex("ab" * 32)
    assert session_store.SEAL_KEY_ENV not in os.environ


def test_a_malformed_seal_key_is_reported_and_never_left_in_the_environment(
    monkeypatch, caplog
):
    monkeypatch.setenv(session_store.SEAL_KEY_ENV, "not-a-key")
    with caplog.at_level(logging.WARNING, logger="tinyassets.onboarding"):
        key = session_store.seal_key()
    assert len(key) == 32
    assert session_store.SEAL_KEY_ENV not in os.environ
    assert any(r.levelno == logging.ERROR for r in caplog.records), caplog.records
    handle = session_store.mint("RT-x")
    assert session_store.read(handle) == ("RT-x", handle)


# --- 6. ephemeral key ---------------------------------------------------------


def test_an_unconfigured_key_warns_once_and_still_round_trips(monkeypatch, caplog):
    monkeypatch.delenv(session_store.SEAL_KEY_ENV, raising=False)
    with caplog.at_level(logging.WARNING, logger="tinyassets.onboarding"):
        handle = session_store.mint("RT-ephemeral")
        assert session_store.read(handle) == ("RT-ephemeral", handle)
        session_store.rotate(handle, "RT-ephemeral-2")
    warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and session_store.SEAL_KEY_ENV in r.getMessage()
    ]
    assert len(warnings) == 1, [r.getMessage() for r in caplog.records]
    assert "restart" in warnings[0].getMessage()


def test_records_sealed_with_a_lost_ephemeral_key_are_unreadable(monkeypatch):
    """The honest cost of no configured key: a restart ends every session.

    Not a silent degradation to plaintext, and not a crash -- the handle simply
    stops resolving and the app re-logs-in. What is left behind is sealed and no
    longer addressable (the filename digest is keyed too); it ages out at its TTL.
    """
    handle = session_store.mint("RT-ephemeral")
    session_store._reset_for_tests()  # a new process = a new ephemeral key
    assert session_store.read(handle) == ("", "")
    orphans = _records()
    assert len(orphans) == 1
    assert b"RT-ephemeral" not in orphans[0].read_bytes()


# --- 7. legacy plaintext store ------------------------------------------------


def test_the_legacy_plaintext_store_is_destroyed_never_migrated(tmp_path, caplog):
    from tinyassets.storage import data_dir

    legacy = data_dir() / "app_refresh_sessions"
    legacy.mkdir(parents=True, exist_ok=True)
    handle = secrets.token_urlsafe(32)
    (legacy / f"{handle}.json").write_text(
        json.dumps({"rt": "RT-LEGACY", "exp": int(time.time()) + 10_000}),
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="tinyassets.onboarding"):
        assert session_store.read(handle) == ("", "")
    assert not legacy.exists(), "the plaintext store must be removed, not migrated"
    assert any("legacy plaintext" in r.getMessage() for r in caplog.records)
    # Nothing was carried across.
    assert _records() == []


def test_the_legacy_store_is_gone_before_the_endpoint_can_serve_anyone(
    monkeypatch, tmp_path
):
    from tinyassets.storage import data_dir

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    legacy = data_dir() / "app_refresh_sessions"
    legacy.mkdir(parents=True, exist_ok=True)
    stale = secrets.token_urlsafe(32)
    (legacy / f"{stale}.json").write_text(
        json.dumps({"rt": "RT-LEGACY", "exp": int(time.time()) + 10_000}),
        encoding="utf-8",
    )

    def _boom(_form):
        raise AssertionError("a legacy handle must not reach AuthKit")

    status, doc, _, calls = _drive(
        {"grant_type": "refresh_token", "session_ref": stale},
        monkeypatch=monkeypatch,
        upstream=_boom,
        data_dir=str(tmp_path),
    )
    assert (status, doc, calls) == (401, {"error": "no_refresh_token"}, [])
    assert not legacy.exists()


# --- the store is where the endpoint actually reads and writes -----------------


def test_the_endpoint_has_no_write_under_a_caller_handle_primitive():
    """`_write_refresh_session(handle, token)` was the bug's shape. It must not
    exist for a future caller to reach for."""
    assert not hasattr(onboarding, "_write_refresh_session")
    import pathlib

    src = pathlib.Path(onboarding.__file__).read_text(encoding="utf-8")
    assert "_write_refresh_session" not in src


def test_the_endpoint_rotates_from_the_store_handle_not_the_request_body():
    import pathlib

    src = pathlib.Path(onboarding.__file__).read_text(encoding="utf-8")
    guard = src.split("may_reuse_handle = ")[1].split("\n")[0]
    assert "current_handle" in guard and "session_ref" not in guard, guard
    assert "_session_store.rotate(current_handle, refresh_token)" in src
