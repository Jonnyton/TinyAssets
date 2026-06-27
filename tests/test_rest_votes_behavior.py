"""Behavioral pins for the REST vote surface after commit 589e1fb.

The existing API regression tests exercise the happy
path end-to-end, but it does not pin two specific semantics from
589e1fb that matter if the REST surface ever goes public:

* ``POST /v1/votes/{vote_id}/resolve`` MUST always pass ``force=True``
  to ``daemon_server.resolve_vote_if_due``. A future patch that
  conditionalizes force (e.g., add an opt-in query flag but default
  to False) would silently regress the documented behavior.

* ``POST /v1/votes/{vote_id}/ballots`` and ``POST /v1/votes/{vote_id}/resolve``
  MUST return a response body shaped as ``{"vote": <result>}``. A
  future patch that unwraps (returning ``result`` directly) or renames
  the wrapper key breaks any public client parsing the shape.

Each test stands alone — no dependency on the full fork-vote flow.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fantasy_daemon.api import app, configure


@pytest.fixture(autouse=True)
def _configure_api(tmp_path):
    universe_dir = tmp_path / "test-universe"
    universe_dir.mkdir()
    (universe_dir / "universe.json").write_text(
        json.dumps(
            {
                "id": "test-universe",
                "name": "Test Universe",
                "created_at": "2026-04-04T00:00:00Z",
                "auto_name": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    configure(
        base_path=str(tmp_path),
        api_key="fa_host_sk_testing",
        daemon=None,
    )
    yield
    configure(base_path="", api_key="", daemon=None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _host_headers() -> dict[str, str]:
    return {"Authorization": "Bearer fa_host_sk_testing"}


def _user_session(client: TestClient, username: str) -> str:
    response = client.post(
        "/v1/sessions",
        headers=_host_headers(),
        json={"username": username},
    )
    assert response.status_code == 201
    return response.json()["token"]


def test_resolve_vote_always_passes_force_true(client: TestClient) -> None:
    """589e1fb pin: /resolve must always call resolve_vote_if_due with
    force=True. A future opt-in flag that defaults to False would
    silently break host-initiated resolution of still-open windows.
    """
    captured_kwargs: dict = {}

    def _capture(*args, **kwargs):
        captured_kwargs.update(kwargs)
        # Return a minimal resolve result shape so the endpoint's
        # downstream wrapping + 404-on-None path stays exercised.
        return {"vote_id": kwargs["vote_id"], "status": "resolved"}

    with patch(
        "tinyassets.daemon_server.resolve_vote_if_due",
        side_effect=_capture,
    ):
        response = client.post(
            "/v1/votes/any-vote-id/resolve",
            headers=_host_headers(),
        )

    assert response.status_code == 200
    assert captured_kwargs.get("force") is True, (
        f"/resolve must pass force=True; got kwargs={captured_kwargs!r}"
    )
    assert captured_kwargs.get("vote_id") == "any-vote-id"


def test_resolve_vote_response_is_vote_wrapped(client: TestClient) -> None:
    """589e1fb pin: /resolve returns {"vote": <result>}. Keep the
    wrapper — any unwrap would be a breaking change for REST clients.
    """
    sentinel = {"vote_id": "v-123", "status": "resolved", "result": {"ok": True}}
    with patch(
        "tinyassets.daemon_server.resolve_vote_if_due",
        return_value=sentinel,
    ):
        response = client.post(
            "/v1/votes/v-123/resolve",
            headers=_host_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"vote"}, (
        f"/resolve response must be wrapped as {{'vote': ...}}; got {body!r}"
    )
    assert body["vote"] == sentinel


def test_cast_vote_response_is_vote_wrapped(client: TestClient) -> None:
    """589e1fb pin: /ballots returns {"vote": <result>} (aligned with
    the /resolve wrapper shape). Unwrapping would diverge the two
    endpoints and break any client coded to the shared shape.
    """
    user_token = _user_session(client, "alice")
    sentinel = {"ballot_id": "b-7", "vote_id": "v-123", "choice": "yes"}

    with patch(
        "tinyassets.daemon_server.cast_vote",
        return_value=sentinel,
    ):
        response = client.post(
            "/v1/votes/v-123/ballots",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"choice": "yes"},
        )

    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {"vote"}, (
        f"/ballots response must be wrapped as {{'vote': ...}}; got {body!r}"
    )
    assert body["vote"] == sentinel


def test_resolve_vote_returns_404_when_not_found(client: TestClient) -> None:
    """When resolve_vote_if_due returns None, /resolve must 404."""
    with patch(
        "tinyassets.daemon_server.resolve_vote_if_due",
        return_value=None,
    ):
        response = client.post(
            "/v1/votes/nonexistent/resolve",
            headers=_host_headers(),
        )
    assert response.status_code == 404


def test_resolve_vote_forbidden_for_non_host(client: TestClient) -> None:
    """Non-host session token must not be able to resolve votes."""
    user_token = _user_session(client, "bob")
    response = client.post(
        "/v1/votes/any-vote-id/resolve",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 403


def test_cast_vote_requires_auth(client: TestClient) -> None:
    """Unauthenticated /ballots requests must be rejected."""
    response = client.post(
        "/v1/votes/v-123/ballots",
        json={"choice": "yes"},
    )
    assert response.status_code in (401, 403)


def test_cast_vote_accepts_choice_field(client: TestClient) -> None:
    """The /ballots body accepts the `choice` field (current schema)."""
    user_token = _user_session(client, "charlie")
    sentinel = {"ballot_id": "b-9", "vote_id": "v-456", "choice": "no"}

    with patch(
        "tinyassets.daemon_server.cast_vote",
        return_value=sentinel,
    ):
        response = client.post(
            "/v1/votes/v-456/ballots",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"choice": "no"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["vote"]["choice"] == "no"
