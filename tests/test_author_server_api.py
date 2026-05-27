"""Tests for the multiplayer Author-server API surface."""

from __future__ import annotations

import json

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
        ) + "\n",
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
def host_client():
    return TestClient(app)


def _host_headers() -> dict[str, str]:
    return {"Authorization": "Bearer fa_host_sk_testing"}


def _create_session(client: TestClient, username: str) -> str:
    response = client.post(
        "/v1/sessions",
        headers=_host_headers(),
        json={"username": username},
    )
    assert response.status_code == 201
    return response.json()["token"]


def test_session_creation_and_me_endpoint(host_client: TestClient):
    token = _create_session(host_client, "alice")

    response = host_client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "alice"
    assert "submit_request" in body["capabilities"]
    assert ("is" + "_host") not in body


def test_author_fork_vote_creates_new_author(host_client: TestClient):
    user_token = _create_session(host_client, "alice")
    authors = host_client.get(
        "/v1/authors",
        headers={"Authorization": f"Bearer {user_token}"},
    ).json()["authors"]
    parent_author_id = authors[0]["author_id"]

    proposal = host_client.post(
        f"/v1/authors/{parent_author_id}/fork-proposals",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "universe_id": "test-universe",
            "display_name": "Alice Branch Author",
            "soul_text": "A branch-minded author with a taste for divergence.",
            "vote_seconds": 30,
            "reason": "Test fork flow",
        },
    )
    assert proposal.status_code == 201
    vote_id = proposal.json()["vote"]["vote_id"]

    ballot = host_client.post(
        f"/v1/votes/{vote_id}/ballots",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"choice": "yes"},
    )
    assert ballot.status_code == 201

    resolved = host_client.post(
        f"/v1/votes/{vote_id}/resolve",
        headers=_host_headers(),
    )
    assert resolved.status_code == 200
    created_author_id = resolved.json()["vote"]["result"]["created_author_id"]

    author = host_client.get(
        f"/v1/authors/{created_author_id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert author.status_code == 200
    assert author.json()["author"]["display_name"] == "Alice Branch Author"


def test_branch_request_runtime_and_ledger_flow(host_client: TestClient):
    user_token = _create_session(host_client, "alice")
    authors = host_client.get(
        "/v1/authors",
        headers={"Authorization": f"Bearer {user_token}"},
    ).json()["authors"]
    author_id = authors[0]["author_id"]

    branch = host_client.post(
        "/v1/universes/test-universe/branches",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"name": "side-path"},
    )
    assert branch.status_code == 201
    branch_id = branch.json()["branch"]["branch_id"]

    request_item = host_client.post(
        "/v1/universes/test-universe/requests",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "request_type": "author_preference",
            "text": "Prefer the house author for this branch.",
            "branch_id": branch_id,
            "preferred_author_id": author_id,
        },
    )
    assert request_item.status_code == 201

    runtime = host_client.post(
        "/v1/universes/test-universe/runtime",
        headers=_host_headers(),
        json={
            "author_id": author_id,
            "provider_name": "codex",
            "model_name": "gpt-5.4",
            "branch_id": branch_id,
        },
    )
    assert runtime.status_code == 201

    ledger = host_client.get(
        "/v1/universes/test-universe/ledger",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert ledger.status_code == 200
    action_types = [entry["action_type"] for entry in ledger.json()["actions"]]
    assert "create_branch" in action_types
    assert "submit_request" in action_types
    assert "spawn_runtime_capacity" in action_types


def test_configure_bootstraps_universes_from_filesystem(tmp_path):
    """``configure`` must call ``sync_universes_from_filesystem`` so a
    universe directory dropped on disk is registered in the daemon_server
    DB. Regression guard for the missing bootstrap call — without it,
    downstream branch/request/runtime endpoints 404 on un-synced universes.
    """
    import workflow.daemon_server as daemon_server
    from fantasy_daemon.api import configure

    # Fresh base dir with a universe directory (no prior configure).
    base = tmp_path / "fresh_base"
    base.mkdir()
    uni = base / "my-new-universe"
    uni.mkdir()
    (uni / "universe.json").write_text(
        json.dumps({"id": "my-new-universe", "name": "Fresh"}),
        encoding="utf-8",
    )

    try:
        configure(base_path=str(base), api_key="fa_host_sk_x", daemon=None)
        # sync_universes_from_filesystem registers the dir in the DB.
        record = daemon_server.get_universe(
            str(base), universe_id="my-new-universe",
        )
        assert record["universe_id"] == "my-new-universe"
    finally:
        configure(base_path="", api_key="", daemon=None)


def test_votes_ballots_returns_vote_shape(host_client: TestClient):
    """Concern 3 / 589e1fb: POST /votes/{id}/ballots returns {"vote": ...}.

    Pre-589e1fb the ballot endpoint returned a bare dict. Clients now
    unwrap via response["vote"]; a regression would drop the outer key
    and silently break every ballot-casting call site.
    """
    user_token = _create_session(host_client, "alice")
    authors = host_client.get(
        "/v1/authors",
        headers={"Authorization": f"Bearer {user_token}"},
    ).json()["authors"]
    parent_author_id = authors[0]["author_id"]

    proposal = host_client.post(
        f"/v1/authors/{parent_author_id}/fork-proposals",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "universe_id": "test-universe",
            "display_name": "Alice Branch",
            "soul_text": "Branch author.",
            "vote_seconds": 30,
            "reason": "Pin ballots response shape",
        },
    )
    assert proposal.status_code == 201
    vote_id = proposal.json()["vote"]["vote_id"]

    ballot = host_client.post(
        f"/v1/votes/{vote_id}/ballots",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"choice": "yes"},
    )
    assert ballot.status_code == 201
    body = ballot.json()
    assert "vote" in body, (
        "Ballot response must wrap the result in a top-level 'vote' key "
        "for parity with the resolve-vote shape (589e1fb contract)."
    )
    assert body["vote"]["vote_id"] == vote_id


def test_votes_resolve_forces_close_before_duration_elapses(host_client: TestClient):
    """Concern 3 / 589e1fb: POST /votes/{id}/resolve passes force=True.

    Pre-589e1fb the resolve endpoint would short-circuit to `get_vote`
    when `closes_at > now()`, returning status=open. After the fix,
    the host-only resolve call passes force=True so the vote closes
    immediately regardless of the configured duration. This test pins
    that contract using a long vote duration that would otherwise be
    non-elapsed.
    """
    user_token = _create_session(host_client, "alice")
    authors = host_client.get(
        "/v1/authors",
        headers={"Authorization": f"Bearer {user_token}"},
    ).json()["authors"]
    parent_author_id = authors[0]["author_id"]

    # Long vote_seconds that will NOT elapse during the test run.
    proposal = host_client.post(
        f"/v1/authors/{parent_author_id}/fork-proposals",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "universe_id": "test-universe",
            "display_name": "Alice Forced Branch",
            "soul_text": "Forced-resolve branch author.",
            "vote_seconds": 3600,
            "reason": "Pin resolve force=True contract",
        },
    )
    assert proposal.status_code == 201
    vote_id = proposal.json()["vote"]["vote_id"]

    host_client.post(
        f"/v1/votes/{vote_id}/ballots",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"choice": "yes"},
    )

    # Host resolves the vote while closes_at is still ~1 hour in the future.
    # force=True is required for this to actually close; without it the
    # endpoint would return status=open and this assertion would fail.
    resolved = host_client.post(
        f"/v1/votes/{vote_id}/resolve",
        headers=_host_headers(),
    )
    assert resolved.status_code == 200
    vote = resolved.json()["vote"]
    assert vote["status"] == "resolved", (
        "/votes/{id}/resolve must pass force=True so host-only resolution "
        "closes the vote regardless of remaining duration (589e1fb)."
    )
    assert "result" in vote


def test_votes_resolve_requires_resolve_vote_capability(host_client: TestClient):
    """Regular sessions get 403 from /votes/{id}/resolve."""
    user_token = _create_session(host_client, "alice")
    authors = host_client.get(
        "/v1/authors",
        headers={"Authorization": f"Bearer {user_token}"},
    ).json()["authors"]
    parent_author_id = authors[0]["author_id"]

    proposal = host_client.post(
        f"/v1/authors/{parent_author_id}/fork-proposals",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "universe_id": "test-universe",
            "display_name": "Alice Guarded Branch",
            "soul_text": "Guard-mode branch.",
            "vote_seconds": 30,
            "reason": "Pin host-only resolve",
        },
    )
    assert proposal.status_code == 201
    vote_id = proposal.json()["vote"]["vote_id"]

    # Non-host user cannot force-resolve.
    resolved = host_client.post(
        f"/v1/votes/{vote_id}/resolve",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resolved.status_code == 403


def test_propose_author_fork_signature_regression():
    """Regression guard for the /fork-proposals TypeError.

    The api.py call site must use ``universe_id=`` / ``author_id=`` /
    ``duration_seconds=`` — the legacy ``parent_author_id=`` /
    ``vote_seconds=`` names produced a TypeError at runtime. Exercising
    ``daemon_server.propose_author_fork`` directly pins the kwargs."""
    import inspect

    import workflow.daemon_server as daemon_server

    sig = inspect.signature(daemon_server.propose_author_fork)
    params = sig.parameters
    # Signature must accept these exact kwargs:
    for required in (
        "universe_id", "author_id", "display_name", "soul_text",
        "proposed_by", "duration_seconds",
    ):
        assert required in params, (
            f"propose_author_fork missing kwarg {required!r} — api.py "
            f"fork-proposals endpoint will TypeError if this drifts"
        )
    # And must NOT require the legacy names:
    assert "parent_author_id" not in params
    assert "vote_seconds" not in params
