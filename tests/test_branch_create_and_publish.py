"""Branch create, staging and publish through the public write_graph.

These lived in tests/test_cloud_automation_api.py, which was deleted with the
fleet-era cloud-automation API (dark-code deletion plan Tier A). They test the
live branch surface, not that API, so they move here unchanged.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401

pytestmark = pytest.mark.usefixtures("cloud_runtime")


def test_branch_staging_preserves_explicit_private_visibility() -> None:
    from tinyassets.api.branches import _staged_branch_from_spec

    branch, errors, notices = _staged_branch_from_spec(
        {"name": "Private repository loop", "visibility": "private"}
    )

    assert errors == []
    # `notices` (2026-09-30) carries adjustments that do NOT refuse the build,
    # so a clean spec must produce none of either.
    assert notices == []
    assert branch.visibility == "private"


def test_non_owner_cannot_publish_private_branch(tmp_path, monkeypatch) -> None:
    from tinyassets import universe_server as server
    from tinyassets.api import permissions
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    initialize_author_server(tmp_path)
    save_branch_definition(
        tmp_path,
        branch_def=BranchDefinition(
            branch_def_id="branch_alice_private",
            name="Alice private workflow",
            author="acct_alice",
            visibility="private",
        ).to_dict(),
    )
    actor = {"id": "acct_mallory"}
    monkeypatch.setattr(
        permissions,
        "current_request_actor_id",
        lambda: actor["id"],
    )

    denied = json.loads(
        server.write_graph(
            target="branch",
            operation="publish",
            branch_id="branch_alice_private",
        )
    )
    actor["id"] = "acct_alice"
    published = json.loads(
        server.write_graph(
            target="branch",
            operation="publish",
            branch_id="branch_alice_private",
        )
    )

    assert denied == {"error": "Branch 'branch_alice_private' not found."}
    assert published["branch_version_id"].startswith("branch_alice_private@")
    assert published["publisher"] == "acct_alice"


def test_phone_branch_create_replays_one_idempotent_definition(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets import universe_server as server
    from tinyassets.api import permissions
    from tinyassets.daemon_server import initialize_author_server

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        permissions,
        "current_request_actor_id",
        lambda: "acct_alice",
    )
    initialize_author_server(tmp_path)
    spec = {
        "name": "Repository loop",
        "entry_point": "ready",
        "node_defs": [
            {
                "node_id": "ready",
                "display_name": "Ready",
                "prompt_template": "Apply one accepted specification slice.",
            }
        ],
        "edges": [
            {"from": "START", "to": "ready"},
            {"from": "ready", "to": "END"},
        ],
        "state_schema": [{"name": "result", "type": "str"}],
    }

    first = json.loads(
        server.write_graph(
            target="branch",
            operation="create",
            payload_json=json.dumps(spec),
            idempotency_key="request_phone_branch_0001",
        )
    )
    replay = json.loads(
        server.write_graph(
            target="branch",
            operation="create",
            payload_json=json.dumps(spec),
            idempotency_key="request_phone_branch_0001",
        )
    )
    changed = dict(spec)
    changed["description"] = "Different definition under the same request key."
    conflict = json.loads(
        server.write_graph(
            target="branch",
            operation="create",
            payload_json=json.dumps(changed),
            idempotency_key="request_phone_branch_0001",
        )
    )

    assert "branch_def_id" in replay, replay
    assert replay["branch_def_id"] == first["branch_def_id"]
    assert replay["batch_receipt"]["idempotent_replay"] is True
    assert conflict["error"] == "branch_idempotency_conflict"


def test_concurrent_phone_branch_create_has_one_definition_winner(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets import universe_server as server
    from tinyassets.api import permissions
    from tinyassets.daemon_server import initialize_author_server

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        permissions,
        "current_request_actor_id",
        lambda: "acct_alice",
    )
    initialize_author_server(tmp_path)
    base = {
        "name": "Repository loop",
        "entry_point": "ready",
        "node_defs": [
            {
                "node_id": "ready",
                "display_name": "Ready",
                "prompt_template": "Apply one accepted specification slice.",
            }
        ],
        "edges": [
            {"from": "START", "to": "ready"},
            {"from": "ready", "to": "END"},
        ],
        "state_schema": [{"name": "result", "type": "str"}],
    }
    candidates = [
        {**base, "description": description}
        for description in ("definition-a", "definition-b")
        for _index in range(4)
    ]

    # A pool worker starts with an EMPTY context, so the bound caller is not
    # there and every create refuses before the idempotency race is exercised.
    from tinyassets.auth import middleware as _mw

    _caller = _mw.current_identity_or_none()

    def create(spec: dict[str, object]) -> dict[str, object]:
        _mw._current_identity.set(_caller)
        return json.loads(
            server.write_graph(
                target="branch",
                operation="create",
                payload_json=json.dumps(spec),
                idempotency_key="request_phone_branch_concurrent_0001",
            )
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(create, candidates))

    built = [result for result in results if result.get("status") == "built"]
    conflicts = [
        result
        for result in results
        if result.get("error") == "branch_idempotency_conflict"
    ]
    assert len(built) == 4
    assert len(conflicts) == 4
