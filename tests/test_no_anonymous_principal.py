"""There is no anonymous principal (founder, 2026-09-02).

The rule, tested at every seam the change touched:

- identity is present or the call refuses (``current_identity`` raises, the
  dev provider needs a named operator, the stdio server binds one);
- the ONE unauthenticated read the daemon serves is ``GET /mcp/pulse`` and it
  names no universe and no user; everything else under ``/mcp`` is 401;
- writes carry their principal explicitly (a run needs an actor, a git author
  needs an identity, a hook records its owner and hands it to the event).

Change: ``openspec/changes/no-anonymous-principal``.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from tinyassets.auth import middleware as mw
from tinyassets.auth.provider import CANARY, DEV_USER_ENV, DevAuthProvider, Identity


@pytest.fixture(autouse=True)
def _reset_auth():
    # Named explicitly: several tests below delete UNIVERSE_SERVER_DEV_USER to
    # prove the provider refuses without it, and teardown must not depend on it.
    mw.set_provider(DevAuthProvider(user_id="dev-tests"))
    mw.auth_middleware(None)
    yield
    mw.set_provider(DevAuthProvider(user_id="dev-tests"))
    mw.auth_middleware(None)


# --------------------------------------------------------------------------
# identity is present or the call refuses
# --------------------------------------------------------------------------


def test_nothing_bound_means_nobody_not_anonymous():
    mw.auth_middleware(None)
    assert mw.current_identity_or_none() is None
    with pytest.raises(PermissionError, match="Authentication required"):
        mw.current_identity()


def test_there_is_no_anonymous_sentinel_left_in_the_provider_module():
    from tinyassets.auth import provider

    assert not hasattr(provider, "ANONYMOUS")
    assert CANARY.user_id == "canary"
    assert CANARY.capabilities == []


def test_an_invalid_bearer_resolves_to_nobody_in_every_mode():
    class _Refuses(DevAuthProvider):
        def resolve_token(self, token: str) -> Identity | None:
            return None

    mw.set_provider(_Refuses(user_id="op"))
    assert mw.auth_middleware("garbage") is None
    assert mw.current_identity_or_none() is None


def test_dev_provider_refuses_to_exist_without_a_named_operator(monkeypatch):
    monkeypatch.delenv(DEV_USER_ENV, raising=False)
    with pytest.raises(RuntimeError, match=DEV_USER_ENV):
        DevAuthProvider()
    monkeypatch.setenv(DEV_USER_ENV, "   ")
    with pytest.raises(RuntimeError, match=DEV_USER_ENV):
        DevAuthProvider()


def test_dev_provider_resolves_any_bearer_to_the_named_operator_and_none_to_nobody(monkeypatch):
    monkeypatch.setenv(DEV_USER_ENV, "operator-9")
    provider = DevAuthProvider()
    assert provider.resolve_token("anything").user_id == "operator-9"
    assert provider.resolve_token("") is None


def test_stdio_binds_the_local_operator_from_env(monkeypatch):
    monkeypatch.setenv(DEV_USER_ENV, "operator-stdio")
    bound = mw.bind_local_operator_identity()
    assert bound.user_id == "operator-stdio"
    assert mw.current_identity().user_id == "operator-stdio"


def test_stdio_falls_back_to_the_os_account_never_to_nobody(monkeypatch):
    import getpass

    monkeypatch.delenv(DEV_USER_ENV, raising=False)
    monkeypatch.setattr(getpass, "getuser", lambda: "os-account")
    assert mw.bind_local_operator_identity().user_id == "os-account"

    monkeypatch.setattr(getpass, "getuser", lambda: "")
    with pytest.raises(RuntimeError, match=DEV_USER_ENV):
        mw.bind_local_operator_identity()


# --------------------------------------------------------------------------
# the one unauthenticated read, through the real app
# --------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path):
    from starlette.testclient import TestClient

    from tinyassets.universe_server import create_streamable_http_app

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DEV_USER_ENV, "operator-app")
    with TestClient(create_streamable_http_app()) as test_client:
        yield test_client


def test_pulse_is_served_without_a_bearer_and_names_nothing(client, tmp_path):
    (tmp_path / "release-state.json").write_text(
        json.dumps({
            "receipt_available": True,
            "git_sha": "abc123def4567890",
            "image_tag": "ghcr.io/x/y:abc123def456",
            "deployed_at": "2026-09-02T10:00:00.000000Z",
            "actor": "someone",
            "extra": {"active_git_sha": "abc123def4567890"},
        }),
        encoding="utf-8",
    )
    response = client.get("/mcp/pulse")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"git_sha", "image_tag", "deployed_at", "uptime_seconds"}
    assert body["git_sha"] == "abc123def4567890"
    assert body["image_tag"] == "ghcr.io/x/y:abc123def456"
    assert body["deployed_at"] == "2026-09-02T10:00:00.000000Z"
    assert isinstance(body["uptime_seconds"], int)
    assert "actor" not in response.text
    assert "universe" not in response.text


def test_pulse_without_a_receipt_reports_empty_facts_not_an_error(client):
    response = client.get("/mcp/pulse")
    assert response.status_code == 200
    body = response.json()
    assert body["git_sha"] == "" and body["image_tag"] == "" and body["deployed_at"] == ""


def test_pulse_is_exact_and_get_only(client):
    assert client.post("/mcp/pulse").status_code in (401, 405)
    assert client.get("/mcp/pulse/extra").status_code == 401


def test_initialize_without_a_bearer_is_challenged_through_the_app(client):
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "t", "version": "1"}},
        },
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer ")
    assert response.json() == {"error": "authentication_required"}


def test_browser_get_of_the_endpoint_is_challenged_too(client):
    # The discovery HTML used to be served to anybody. It is under /mcp and
    # carries no named authentication of its own, so it is challenged like
    # every other /mcp path; the public website is the place for prose.
    assert client.get("/mcp", headers={"Accept": "text/html"}).status_code == 401


# --------------------------------------------------------------------------
# writes carry their principal
# --------------------------------------------------------------------------


def test_create_run_refuses_an_empty_actor(tmp_path):
    from tinyassets.runs import create_run, initialize_runs_db

    initialize_runs_db(tmp_path)
    with pytest.raises(ValueError, match="actor"):
        create_run(tmp_path, branch_def_id="b-1", thread_id="t-1", inputs={}, actor="")
    with pytest.raises(ValueError, match="actor"):
        create_run(tmp_path, branch_def_id="b-1", thread_id="t-1", inputs={}, actor="   ")


def test_git_author_needs_an_identity_or_an_explicit_actor(monkeypatch):
    from tinyassets.identity import git_author

    monkeypatch.delenv("TINYASSETS_GIT_AUTHOR", raising=False)
    mw.auth_middleware(None)
    with pytest.raises(PermissionError, match="authenticated actor"):
        git_author()
    assert git_author("Some Body") == "TinyAssets User <some-body@users.noreply.tinyassets.local>"
    subject = Identity(user_id="workos|abc", username="workos-abc", capabilities=["read"])
    with mw.identity_context(subject):
        assert "@users.noreply.tinyassets.local>" in git_author()
        assert "anonymous" not in git_author()


def test_a_hook_records_its_owner_and_hands_it_back(tmp_path):
    from tinyassets.storage import webhook_hooks

    token = webhook_hooks.mint(
        tmp_path, universe_id="u-1", branch_def_id="b-1", owner_principal_id="owner-7",
    )
    resolved = webhook_hooks.resolve(tmp_path, token=token)
    assert resolved is not None
    assert resolved["owner_principal_id"] == "owner-7"
    with pytest.raises(TypeError):
        webhook_hooks.mint(tmp_path, universe_id="u-1", branch_def_id="b-2")  # type: ignore[call-arg]


def test_a_scheduler_event_carries_its_owner():
    from tinyassets.scheduler import SchedulerEvent

    event = SchedulerEvent(event_type="source.fired", payload={}, owner_principal_id="owner-3")
    assert event.owner_principal_id == "owner-3"
    assert SchedulerEvent(event_type="x").owner_principal_id == ""


# --------------------------------------------------------------------------
# the platform-wide activity field the probes read instead of a universe
# --------------------------------------------------------------------------


def test_platform_last_activity_at_reads_the_root_ledger(monkeypatch, tmp_path):
    from tinyassets.api.status import _platform_last_activity_at
    from tinyassets.runs import create_run, initialize_runs_db, runs_db_path

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    assert _platform_last_activity_at() is None            # no ledger yet

    initialize_runs_db(tmp_path)
    assert _platform_last_activity_at() is None            # ledger, no run

    create_run(tmp_path, branch_def_id="b-1", thread_id="t-1", inputs={}, actor="u-1")
    stamp = _platform_last_activity_at()
    assert isinstance(stamp, str) and stamp.endswith("+00:00")

    conn = sqlite3.connect(runs_db_path(tmp_path))
    try:
        conn.execute("UPDATE runs SET finished_at = ?", (1_800_000_000.0,))
        conn.commit()
    finally:
        conn.close()
    assert _platform_last_activity_at() == "2027-01-15T08:00:00+00:00"


def test_get_status_carries_the_daemon_block(monkeypatch, tmp_path):
    from tinyassets.api.status import get_status

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(DEV_USER_ENV, "operator-status")
    mw.auth_middleware("any")
    payload: dict[str, Any] = json.loads(get_status())
    assert "daemon" in payload
    assert set(payload["daemon"]) == {"last_activity_at"}
