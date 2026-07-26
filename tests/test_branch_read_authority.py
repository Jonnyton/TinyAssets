"""Credential-bound branch read, provenance, and lineage authority."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity


class _CredentialProvider(AuthProvider):
    """Resolve each non-empty test bearer to a credential-backed subject."""

    def resolve_token(self, token: str) -> Identity | None:
        if not token:
            return None
        return Identity(
            user_id=token,
            username=f"{token}-display",
            capabilities=[
                "tinyassets.extensions.read",
                "tinyassets.extensions.write",
                "tinyassets.extensions.admin",
            ],
        )

    def is_auth_required(self) -> bool:
        return True

    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"client_id": "branch-authority-test", **metadata}

    def create_authorization(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        return "branch-authority-code"

    def exchange_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any] | None:
        return None


@pytest.fixture
def branch_authority_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Callable[[str | None], None]]:
    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "environment-owner")

    from tinyassets.daemon_server import initialize_author_server

    initialize_author_server(base)
    set_provider(_CredentialProvider())

    def authenticate(subject: str | None) -> None:
        auth_middleware(subject)

    authenticate(None)
    yield base, authenticate
    authenticate(None)
    set_provider(DevAuthProvider())


def _call_raw(action: str, **kwargs: Any) -> str:
    from tinyassets.api import branches

    return branches._dispatch_branch_action(
        action,
        branches._BRANCH_ACTIONS[action],
        kwargs,
    )


def _call(action: str, **kwargs: Any) -> dict[str, Any]:
    return json.loads(_call_raw(action, **kwargs))


def _seed_branch(
    base: Path,
    *,
    branch_def_id: str,
    author: str,
    visibility: str = "public",
    name: str | None = None,
    fork_from: str | None = None,
    node_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    from tinyassets.daemon_server import save_branch_definition

    node_defs = [
        {
            "node_id": node_id,
            "display_name": node_id.replace("_", " ").title(),
            "description": f"{node_id} reusable node",
            "phase": "custom",
            "input_keys": [],
            "output_keys": [],
            "prompt_template": f"Run {node_id}.",
            "author": author,
        }
        for node_id in node_ids
    ]
    return save_branch_definition(
        base,
        branch_def={
            "branch_def_id": branch_def_id,
            "name": name or branch_def_id,
            "description": "",
            "author": author,
            "domain_id": "workflow",
            "visibility": visibility,
            "fork_from": fork_from,
            "node_defs": node_defs,
            "graph_nodes": [
                {"id": node_id, "node_def_id": node_id, "position": index}
                for index, node_id in enumerate(node_ids)
            ],
            "edges": [],
            "conditional_edges": [],
            "state_schema": [],
            "entry_point": node_ids[0] if node_ids else "",
        },
    )


def _publish(base: Path, branch: dict[str, Any], publisher: str) -> str:
    from tinyassets.branch_versions import publish_branch_version

    return publish_branch_version(
        base,
        branch,
        publisher=publisher,
    ).branch_version_id


def test_anonymous_environment_actor_cannot_create_or_reach_ledger(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = branch_authority_env
    authenticate(None)

    response = _call(
        "create_branch",
        name="environment-forge",
        author="caller-forge",
    )

    assert response == {
        "error": "Authenticated branch subject required.",
    }
    assert not (base / "ledger.json").exists()


def test_create_and_build_bind_author_receipt_nodes_and_ledger_to_subject(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = branch_authority_env
    authenticate("credential-alice")

    created = _call(
        "create_branch",
        name="server-bound-create",
        author="caller-mallory",
    )
    built = _call(
        "build_branch",
        spec_json=json.dumps({
            "name": "server-bound-build",
            "author": "caller-mallory",
            "entry_point": "draft",
            "node_defs": [{
                "node_id": "draft",
                "display_name": "Draft",
                "prompt_template": "Draft.",
                "author": "caller-mallory",
            }],
            "edges": [
                {"from": "START", "to": "draft"},
                {"from": "draft", "to": "END"},
            ],
        }),
    )

    from tinyassets.daemon_server import get_branch_definition

    created_row = get_branch_definition(
        base,
        branch_def_id=created["branch_def_id"],
    )
    built_row = get_branch_definition(
        base,
        branch_def_id=built["branch_def_id"],
    )
    ledger = json.loads((base / "ledger.json").read_text(encoding="utf-8"))

    assert created_row["author"] == "credential-alice"
    assert built_row["author"] == "credential-alice"
    assert built_row["node_defs"][0]["author"] == "credential-alice"
    assert built["batch_receipt"]["actor"] == "credential-alice"
    assert [entry["actor"] for entry in ledger] == [
        "credential-alice",
        "credential-alice",
    ]
    encoded = json.dumps(ledger, sort_keys=True)
    assert "environment-owner" not in encoded
    assert "caller-mallory" not in encoded


def test_listing_uses_only_authenticated_viewer_and_mine_is_empty_for_anonymous(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = branch_authority_env
    _seed_branch(
        base,
        branch_def_id="public-row",
        author="bob",
    )
    _seed_branch(
        base,
        branch_def_id="alice-private",
        author="alice",
        visibility="private",
    )
    _seed_branch(
        base,
        branch_def_id="bob-private",
        author="bob",
        visibility="private",
    )
    _seed_branch(
        base,
        branch_def_id="environment-private",
        author="environment-owner",
        visibility="private",
    )

    authenticate(None)
    anonymous_all = _call("list_branches", scope="all")
    anonymous_mine = _call("list_branches", scope="mine")

    assert {row["branch_def_id"] for row in anonymous_all["branches"]} == {
        "public-row",
    }
    assert anonymous_all["count"] == 1
    assert anonymous_mine == {"branches": [], "count": 0}

    authenticate("alice")
    alice_rows = _call("list_branches", scope="all")
    assert {row["branch_def_id"] for row in alice_rows["branches"]} == {
        "public-row",
        "alice-private",
    }
    assert alice_rows["count"] == 2


def test_reusable_node_search_counts_only_public_and_own_private_candidates(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = branch_authority_env
    _seed_branch(
        base,
        branch_def_id="public-source",
        author="bob",
        node_ids=("shared_probe", "public_only"),
    )
    _seed_branch(
        base,
        branch_def_id="own-source",
        author="alice",
        visibility="private",
        node_ids=("shared_probe", "own_only"),
    )
    _seed_branch(
        base,
        branch_def_id="foreign-source",
        author="bob",
        visibility="private",
        node_ids=("shared_probe", "foreign_only"),
    )
    _seed_branch(
        base,
        branch_def_id="environment-source",
        author="environment-owner",
        visibility="private",
        node_ids=("shared_probe", "environment_only"),
    )

    authenticate("alice")
    all_results = _call("search_nodes")
    shared = _call("search_nodes", query="shared_probe")
    ids = {entry["node_id"] for entry in all_results["entries"]}

    assert ids == {"shared_probe", "public_only", "own_only"}
    assert all_results["count"] == 3
    assert shared["count"] == 1
    assert shared["entries"][0]["reuse_count"] == 2
    assert set(shared["entries"][0]["goal_ids"]) == set()


@pytest.mark.parametrize(
    "action",
    ["get_branch", "describe_branch", "validate_branch", "fork_tree"],
)
def test_private_id_and_missing_selector_have_byte_identical_read_envelopes(
    action: str,
    branch_authority_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = branch_authority_env
    _seed_branch(
        base,
        branch_def_id="private-selector",
        author="bob",
        visibility="private",
        node_ids=("secret_node",),
    )
    authenticate("alice")

    denied = _call_raw(action, branch_def_id="private-selector")

    from tinyassets.daemon_server import delete_branch_definition

    assert delete_branch_definition(
        base,
        branch_def_id="private-selector",
    )
    missing = _call_raw(action, branch_def_id="private-selector")

    expected = json.dumps({
        "error": "Branch 'private-selector' not found.",
    })
    assert denied == missing == expected


def test_environment_identity_cannot_resolve_private_name_to_canonical_id(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = branch_authority_env
    _seed_branch(
        base,
        branch_def_id="opaque-private-id",
        name="Guessed Private Name",
        author="environment-owner",
        visibility="private",
    )
    authenticate(None)

    response = _call(
        "get_branch",
        branch_def_id="Guessed Private Name",
    )

    assert response == {
        "error": "Branch 'Guessed Private Name' not found.",
    }
    assert "opaque-private-id" not in json.dumps(response)


def test_public_and_authenticated_owner_reads_remain_available(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = branch_authority_env
    _seed_branch(
        base,
        branch_def_id="public-readable",
        author="bob",
        node_ids=("public_node",),
    )
    _seed_branch(
        base,
        branch_def_id="owner-private",
        author="alice",
        visibility="private",
        node_ids=("owner_node",),
    )

    authenticate(None)
    assert _call(
        "get_branch",
        branch_def_id="public-readable",
    )["branch_def_id"] == "public-readable"

    authenticate("alice")
    assert _call(
        "get_branch",
        branch_def_id="owner-private",
    )["branch_def_id"] == "owner-private"


def test_unreadable_fork_pointer_and_ancestor_are_omitted(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = branch_authority_env
    private_parent = _seed_branch(
        base,
        branch_def_id="private-parent",
        author="bob",
        visibility="private",
        node_ids=("parent_node",),
    )
    parent_version = _publish(base, private_parent, publisher="bob")
    _seed_branch(
        base,
        branch_def_id="public-child",
        author="alice",
        fork_from=parent_version,
        node_ids=("child_node",),
    )
    authenticate("alice")

    got = _call("get_branch", branch_def_id="public-child")
    described = _call("describe_branch", branch_def_id="public-child")
    lineage = _call("fork_tree", branch_def_id="public-child")

    assert "fork_from" not in got
    assert "fork_from" not in described
    assert lineage["fork_from"] is None
    assert lineage["ancestors"] == []
    assert "private-parent" not in json.dumps(lineage)


def test_descendant_projection_includes_public_and_owner_private_only(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = branch_authority_env
    parent = _seed_branch(
        base,
        branch_def_id="lineage-root",
        author="bob",
        node_ids=("root_node",),
    )
    parent_version = _publish(base, parent, publisher="bob")
    _seed_branch(
        base,
        branch_def_id="public-descendant",
        author="carol",
        fork_from=parent_version,
    )
    _seed_branch(
        base,
        branch_def_id="owner-private-descendant",
        author="alice",
        visibility="private",
        fork_from=parent_version,
    )
    _seed_branch(
        base,
        branch_def_id="foreign-private-descendant",
        author="carol",
        visibility="private",
        fork_from=parent_version,
    )
    authenticate("alice")

    lineage = _call("fork_tree", branch_def_id="lineage-root")
    descendant_ids = {
        row["branch_def_id"] for row in lineage["descendants"]
    }

    assert descendant_ids == {
        "public-descendant",
        "owner-private-descendant",
    }
    assert lineage["descendant_count"] == 2
