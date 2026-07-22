"""Private Goal confidentiality through the canonical anonymous read handle."""

from __future__ import annotations

import json

from tinyassets.auth.provider import DevAuthProvider, Identity


class _SignedIdentityProvider(DevAuthProvider):
    def resolve_token(self, token: str) -> Identity | None:
        if token != "valid":
            return None
        return Identity(
            user_id="alice",
            username="Alice",
            capabilities=["tinyassets.goals.read"],
        )

    def is_auth_required(self) -> bool:
        return True


def test_anonymous_read_graph_does_not_disclose_private_goal(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.auth.middleware import auth_middleware
    from tinyassets.daemon_server import save_goal
    from tinyassets.universe_server import read_graph

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    # Matching the stored author must not grant authority without a signed
    # request identity.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    auth_middleware(None)

    private_goal = save_goal(tmp_path, goal={
        "name": "Acquisition plan",
        "description": "confidential-acquisition-details",
        "author": "alice",
        "tags": ["confidential-acquisition-tag"],
        "visibility": "private",
    })

    listed = json.loads(read_graph(target="goals"))
    searched = json.loads(read_graph(
        target="goals",
        query="confidential-acquisition-details",
    ))
    fetched = json.loads(read_graph(
        target="goal",
        goal_id=private_goal["goal_id"],
    ))

    assert listed["goals"] == []
    assert listed["count"] == 0
    assert searched["goals"] == []
    assert searched["count"] == 0
    assert fetched == {
        "status": "rejected",
        "error": f"Goal '{private_goal['goal_id']}' not found.",
    }


def test_signed_viewer_can_read_only_own_private_goal(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.auth.middleware import auth_middleware, set_provider
    from tinyassets.daemon_server import save_goal
    from tinyassets.universe_server import read_graph

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    alice_goal = save_goal(tmp_path, goal={
        "name": "Alice private plan",
        "description": "aliceprivatesearchtoken",
        "author": "alice",
        "visibility": "private",
    })
    bob_goal = save_goal(tmp_path, goal={
        "name": "Bob private plan",
        "description": "bobprivatesearchtoken",
        "author": "bob",
        "visibility": "private",
    })

    set_provider(_SignedIdentityProvider())
    auth_middleware("valid")
    try:
        listed = json.loads(read_graph(target="goals"))
        alice_search = json.loads(read_graph(
            target="goals",
            query="aliceprivatesearchtoken",
        ))
        bob_search = json.loads(read_graph(
            target="goals",
            query="bobprivatesearchtoken",
        ))
        alice_get = json.loads(read_graph(
            target="goal",
            goal_id=alice_goal["goal_id"],
        ))
        bob_get = json.loads(read_graph(
            target="goal",
            goal_id=bob_goal["goal_id"],
        ))
    finally:
        set_provider(DevAuthProvider())
        auth_middleware(None)

    assert [goal["goal_id"] for goal in listed["goals"]] == [
        alice_goal["goal_id"],
    ]
    assert [goal["goal_id"] for goal in alice_search["goals"]] == [
        alice_goal["goal_id"],
    ]
    assert bob_search["goals"] == []
    assert alice_get["goal"]["goal_id"] == alice_goal["goal_id"]
    assert bob_get == {
        "status": "rejected",
        "error": f"Goal '{bob_goal['goal_id']}' not found.",
    }
