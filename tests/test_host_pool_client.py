"""Track D Wave 1 tests — host_pool client + registration + heartbeat + bid poller.

Stdlib-only tests via a fake HTTP transport. No live Supabase call.
The fake transport records request method/URL/body and returns
scripted (status, body) tuples per request.
"""

from __future__ import annotations

import asyncio
import json
import re

import pytest

from tinyassets.host_pool import (
    BidPoller,
    HeartbeatLoop,
    HostPoolClient,
    HostPoolError,
    register_daemon,
)

# ---- fake HTTP transport --------------------------------------------------


class _FakeHttp:
    """Recording HTTP fake.

    Scripted responses: set ``responses`` to a list of (status, body-str)
    or dicts (auto-serialized to JSON). Each request pops the next
    response. Raise a ``HostPoolError`` on exhaustion to make test bugs
    visible.

    Records each request as a tuple (method, url, headers, body-bytes).
    """

    def __init__(self, responses=None):
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []
        self.responses = list(responses or [])

    def push(self, status, body):
        self.responses.append((status, body))

    def request(self, method, url, headers, body, timeout):  # noqa: ARG002 — timeout
        self.calls.append((method, url, dict(headers), body))
        if not self.responses:
            raise HostPoolError(0, "fake: no scripted response")
        status, resp_body = self.responses.pop(0)
        if isinstance(resp_body, (dict, list)):
            resp_body = json.dumps(resp_body)
        return status, resp_body


class _FakeAuth:
    def sign_headers(self, method, path, body):
        return {
            "Authorization": "Bearer daemon-token",
            "X-TinyAssets-Body-SHA256": "0" * 64,
            "X-TinyAssets-Timestamp": "1800000000",
            "X-TinyAssets-Nonce": "fresh-nonce",
            "X-TinyAssets-Signature": "signed-proof",
        }


@pytest.fixture
def client():
    http = _FakeHttp()
    c = HostPoolClient(
        control_plane_url="https://control.example",
        auth=_FakeAuth(),
        http=http,
        timeout=1.0,
    )
    # Expose the fake for assertions.
    c._fake = http  # type: ignore[attr-defined]
    return c


# ---- client configuration -------------------------------------------------


def test_missing_control_plane_url_raises(monkeypatch):
    monkeypatch.delenv("TINYASSETS_CONTROL_PLANE_URL", raising=False)
    with pytest.raises(HostPoolError) as ctx:
        HostPoolClient(auth=_FakeAuth())
    assert "TINYASSETS_CONTROL_PLANE_URL" in str(ctx.value)


def test_missing_daemon_auth_raises(monkeypatch):
    monkeypatch.setenv("TINYASSETS_CONTROL_PLANE_URL", "https://control.example")
    with pytest.raises(HostPoolError) as ctx:
        HostPoolClient()
    assert "enrolled daemon authentication" in str(ctx.value)


def test_env_fallback_picks_up_control_plane_url(monkeypatch):
    monkeypatch.setenv("TINYASSETS_CONTROL_PLANE_URL", "https://control.example/")
    c = HostPoolClient(auth=_FakeAuth(), http=_FakeHttp())
    # Trailing slash stripped.
    assert c._base == "https://control.example"


# ---- register + heartbeat + visibility + deregister ----------------------


def test_register_posts_payload_and_returns_row(client):
    client._fake.push(
        201,
        [{
            "host_id": "h-1",
            "owner_user_id": "u-1",
            "provider": "local",
            "capability_id": "goal_planner:claude-4-opus",
            "visibility": "self",
            "price_floor": None,
            "max_concurrent": 1,
            "always_active": False,
            "version": 1,
        }],
    )
    row = client.register(
        provider="local",
        capability_id="goal_planner:claude-4-opus",
    )
    assert row.host_id == "h-1"
    assert row.provider == "local"

    method, url, headers, body = client._fake.calls[-1]
    assert method == "POST"
    assert url == "https://control.example/v1/host-pool"
    assert "apikey" not in headers
    assert headers["Authorization"] == "Bearer daemon-token"
    assert headers["X-TinyAssets-Signature"] == "signed-proof"
    assert headers["Prefer"] == "return=representation"
    payload = json.loads(body)
    assert "owner_user_id" not in payload
    assert payload["capability_id"] == "goal_planner:claude-4-opus"
    # price_floor omitted when None.
    assert "price_floor" not in payload


def test_register_with_price_floor_passes_through(client):
    client._fake.push(201, [{
        "host_id": "h-2", "owner_user_id": "u-1",
        "provider": "claude", "capability_id": "c1",
        "visibility": "paid", "price_floor": 0.05,
        "max_concurrent": 2, "always_active": True, "version": 1,
    }])
    row = client.register(
        provider="claude", capability_id="c1",
        visibility="paid", price_floor=0.05, max_concurrent=2, always_active=True,
    )
    assert row.price_floor == 0.05
    payload = json.loads(client._fake.calls[-1][3])
    assert payload["price_floor"] == 0.05
    assert payload["always_active"] is True


def test_register_error_raises_host_pool_error(client):
    client._fake.push(400, '{"message":"violates foreign key"}')
    with pytest.raises(HostPoolError) as ctx:
        client.register(
            provider="local", capability_id="c",
        )
    assert ctx.value.status == 400


def test_heartbeat_posts_to_daemon_resource(client):
    client._fake.push(204, "")
    client.heartbeat("host-abc")
    method, url, _, body = client._fake.calls[-1]
    assert method == "PATCH"
    assert url == "https://control.example/v1/host-pool/host-abc:heartbeat"
    assert json.loads(body) == {"updated_at": "now()"}


def test_update_visibility_sends_correct_patch(client):
    client._fake.push(204, "")
    client.update_visibility("h-1", "paid")
    _, url, _, body = client._fake.calls[-1]
    assert url == "https://control.example/v1/host-pool/h-1"
    assert json.loads(body) == {"visibility": "paid"}


def test_update_capability_sends_correct_patch(client):
    client._fake.push(204, "")
    client.update_capability("h-1", "new_cap:llm-a")
    _, _, _, body = client._fake.calls[-1]
    assert json.loads(body) == {"capability_id": "new_cap:llm-a"}


def test_deregister_issues_delete(client):
    client._fake.push(204, "")
    client.deregister("h-1")
    method, url, _, body = client._fake.calls[-1]
    assert method == "DELETE"
    assert url == "https://control.example/v1/host-pool/h-1"
    assert body is None


def test_get_existing_row(client):
    client._fake.push(200, [{
        "host_id": "h-1", "owner_user_id": "u-1",
        "provider": "local", "capability_id": "c1",
        "visibility": "self", "price_floor": None,
        "max_concurrent": 1, "always_active": False, "version": 1,
    }])
    row = client.get("h-1")
    assert row is not None
    assert row.host_id == "h-1"


def test_get_missing_row_returns_none(client):
    client._fake.push(200, [])
    assert client.get("nope") is None


def test_ensure_capability_posts_with_ignore_duplicates(client):
    client._fake.push(201, [])
    client.ensure_capability(
        "goal_planner:claude-4-opus",
        node_type="goal_planner",
        llm_model="claude-4-opus",
    )
    method, url, headers, body = client._fake.calls[-1]
    assert method == "POST"
    assert url.endswith("/v1/capabilities")
    assert headers["Prefer"] == "resolution=ignore-duplicates"
    payload = json.loads(body)
    assert payload["capability_id"] == "goal_planner:claude-4-opus"
    assert payload["node_type"] == "goal_planner"


# ---- list_pending_requests -----------------------------------------------


def test_list_pending_requests_filters_and_orders(client):
    client._fake.push(200, [
        {"request_id": "r1", "capability_id": "c1", "created_at": "2026-04-20T00:00Z"},
    ])
    rows = client.list_pending_requests("c1", limit=10)
    assert len(rows) == 1
    _, url, _, _ = client._fake.calls[-1]
    # Check the filter params are in the query string.
    assert "state=eq.pending" in url
    assert "capability_id=eq.c1" in url
    assert re.search(r"visibility=in\.%28paid%2Cpublic%29|visibility=in.\(paid,public\)", url)
    assert "order=created_at.asc" in url
    assert "limit=10" in url


def test_list_pending_returns_empty_on_non_list_body(client):
    client._fake.push(200, "")
    assert client.list_pending_requests("c1") == []


# ---- registration flow ---------------------------------------------------


def test_register_daemon_ensures_capability_then_registers(client):
    # capabilities POST returns empty list (ignore-duplicates).
    client._fake.push(201, [])
    # host_pool POST returns the new row.
    client._fake.push(201, [{
        "host_id": "h-xyz", "owner_user_id": "u-1",
        "provider": "local", "capability_id": "goal_planner:claude-4-opus",
        "visibility": "self", "price_floor": None,
        "max_concurrent": 1, "always_active": False, "version": 1,
    }])
    reg = register_daemon(
        client,
        provider="local",
        capability_id="goal_planner:claude-4-opus",
    )
    assert reg.created is True
    assert reg.row.host_id == "h-xyz"

    # Verify call ordering: capabilities first, then host_pool.
    assert len(client._fake.calls) == 2
    assert client._fake.calls[0][1].endswith("/capabilities")
    assert client._fake.calls[1][1].endswith("/host-pool")


def test_register_daemon_splits_capability_id_on_colon(client):
    client._fake.push(201, [])
    client._fake.push(201, [{
        "host_id": "h-1", "owner_user_id": "u-1",
        "provider": "local", "capability_id": "research_paper_drafter:claude-4-opus",
        "visibility": "self", "price_floor": None,
        "max_concurrent": 1, "always_active": False, "version": 1,
    }])
    register_daemon(
        client, provider="local",
        capability_id="research_paper_drafter:claude-4-opus",
    )
    cap_body = json.loads(client._fake.calls[0][3])
    assert cap_body["node_type"] == "research_paper_drafter"
    assert cap_body["llm_model"] == "claude-4-opus"


def test_register_daemon_explicit_node_type_overrides_split(client):
    client._fake.push(201, [])
    client._fake.push(201, [{
        "host_id": "h-1", "owner_user_id": "u-1",
        "provider": "local", "capability_id": "a:b",
        "visibility": "self", "price_floor": None,
        "max_concurrent": 1, "always_active": False, "version": 1,
    }])
    register_daemon(
        client, provider="local",
        capability_id="a:b",
        capability_node_type="override_node",
        capability_llm_model="override_llm",
    )
    cap_body = json.loads(client._fake.calls[0][3])
    assert cap_body["node_type"] == "override_node"
    assert cap_body["llm_model"] == "override_llm"


# ---- heartbeat loop ------------------------------------------------------


def test_heartbeat_loop_rejects_too_fast_interval(client):
    with pytest.raises(ValueError):
        HeartbeatLoop(client, host_id="h-1", interval=10)


def test_heartbeat_loop_runs_and_stops():
    # Use a very short interval + sync fake executor. Drive the loop
    # via stop() after one heartbeat.
    http = _FakeHttp()
    http.push(204, "")  # first heartbeat
    http.push(204, "")  # spare
    c = HostPoolClient(
        control_plane_url="https://control.example",
        auth=_FakeAuth(), http=http, timeout=1.0,
    )

    async def run():
        loop = HeartbeatLoop(c, host_id="h-1", interval=30)
        task = asyncio.create_task(loop.run())
        await asyncio.sleep(0.05)  # let the first heartbeat fire
        loop.stop()
        await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(run())
    # First call should be a heartbeat PATCH to host_pool.
    assert http.calls, "loop should have heartbeated at least once"
    method, url, _, _ = http.calls[0]
    assert method == "PATCH"
    assert url == "https://control.example/v1/host-pool/h-1:heartbeat"


def test_heartbeat_loop_surfaces_errors_via_callback():
    http = _FakeHttp()
    http.push(500, "server error")
    c = HostPoolClient(
        control_plane_url="https://control.example",
        auth=_FakeAuth(), http=http, timeout=1.0,
    )
    errors = []

    async def run():
        loop = HeartbeatLoop(
            c, host_id="h-1", interval=30,
            on_error=lambda exc: errors.append(exc),
        )
        task = asyncio.create_task(loop.run())
        await asyncio.sleep(0.05)
        loop.stop()
        await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(run())
    assert errors, "on_error callback should have been invoked"
    assert isinstance(errors[0], HostPoolError)
    assert errors[0].status == 500


# ---- bid poller ----------------------------------------------------------


def test_bid_poller_tick_reports_only_new_requests(client):
    notified: list[list] = []

    client._fake.push(200, [
        {"request_id": "r1", "capability_id": "c1"},
        {"request_id": "r2", "capability_id": "c1"},
    ])
    poller = BidPoller(
        client, capability_id="c1",
        on_requests=lambda rows: notified.append(list(rows)),
    )
    new = poller._tick()
    assert [r["request_id"] for r in new] == ["r1", "r2"]

    # Second tick with same rows plus a new one — only the new one.
    client._fake.push(200, [
        {"request_id": "r1", "capability_id": "c1"},
        {"request_id": "r2", "capability_id": "c1"},
        {"request_id": "r3", "capability_id": "c1"},
    ])
    new = poller._tick()
    assert [r["request_id"] for r in new] == ["r3"]


def test_bid_poller_skips_rows_missing_request_id(client):
    client._fake.push(200, [
        {"request_id": None, "capability_id": "c1"},
        {"capability_id": "c1"},  # no request_id field
        {"request_id": "r4", "capability_id": "c1"},
    ])
    poller = BidPoller(
        client, capability_id="c1", on_requests=lambda _: None,
    )
    new = poller._tick()
    assert [r["request_id"] for r in new] == ["r4"]


def test_bid_poller_callback_exception_does_not_break_loop():
    http = _FakeHttp()
    http.push(200, [{"request_id": "r1"}])
    http.push(200, [{"request_id": "r2"}])
    c = HostPoolClient(
        control_plane_url="https://control.example",
        auth=_FakeAuth(), http=http, timeout=1.0,
    )

    seen: list[str] = []

    def flaky(rows):
        seen.extend(r["request_id"] for r in rows)
        raise RuntimeError("callback exploded")

    async def run():
        poller = BidPoller(
            c, capability_id="c1", on_requests=flaky, poll_interval=30,
        )
        task = asyncio.create_task(poller.run())
        await asyncio.sleep(0.05)
        poller.stop()
        await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(run())
    # Loop stayed alive even though callback raised; at least r1 seen.
    assert "r1" in seen
