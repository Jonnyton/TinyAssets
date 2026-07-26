"""Credential-bound branch mutation and deletion authority."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity


class _CredentialProvider(AuthProvider):
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
        return {"client_id": "branch-mutation-test", **metadata}

    def create_authorization(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        return "branch-mutation-code"

    def exchange_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any] | None:
        return None


@pytest.fixture
def mutation_env(
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
    source_code: bool = False,
) -> dict[str, Any]:
    from tinyassets.daemon_server import save_branch_definition

    first_body = (
        {
            "source_code": "def run(state):\n    return state\n",
            "prompt_template": "",
            "approved": False,
            "approved_by": "",
            "approved_at": "",
            "approved_source_hash": "",
            "approval_reason": "",
        }
        if source_code
        else {
            "source_code": "",
            "prompt_template": "First prompt.",
        }
    )
    return save_branch_definition(
        base,
        branch_def={
            "branch_def_id": branch_def_id,
            "name": name or branch_def_id,
            "description": "",
            "author": author,
            "domain_id": "workflow",
            "visibility": visibility,
            "entry_point": "source_node",
            "tags": ["original"],
            "node_defs": [
                {
                    "node_id": "source_node",
                    "display_name": "Source Node",
                    "description": "original source",
                    "phase": "custom",
                    "input_keys": [],
                    "output_keys": [],
                    "tools_allowed": [],
                    "author": author,
                    **first_body,
                },
                {
                    "node_id": "second_node",
                    "display_name": "Second Node",
                    "description": "original second",
                    "phase": "custom",
                    "input_keys": [],
                    "output_keys": [],
                    "tools_allowed": [],
                    "prompt_template": "Second prompt.",
                    "author": author,
                },
            ],
            "graph_nodes": [
                {
                    "id": "source_node",
                    "node_def_id": "source_node",
                    "position": 0,
                },
                {
                    "id": "second_node",
                    "node_def_id": "second_node",
                    "position": 1,
                },
            ],
            "edges": [
                {"from_node": "START", "to_node": "source_node"},
                {"from_node": "source_node", "to_node": "second_node"},
                {"from_node": "second_node", "to_node": "END"},
            ],
            "conditional_edges": [],
            "state_schema": [],
        },
    )


def _stored_bytes(base: Path, branch_def_id: str) -> bytes:
    from tinyassets.daemon_server import get_branch_definition

    return json.dumps(
        get_branch_definition(base, branch_def_id=branch_def_id),
        sort_keys=True,
        default=str,
    ).encode()


def _kwargs_for(action: str, selector: str) -> dict[str, Any]:
    cases: dict[str, dict[str, Any]] = {
        "add_node": {
            "branch_def_id": selector,
            "node_id": "added_node",
            "display_name": "Added Node",
            "prompt_template": "Added.",
        },
        "connect_nodes": {
            "branch_def_id": selector,
            "from_node": "source_node",
            "to_node": "END",
        },
        "set_entry_point": {
            "branch_def_id": selector,
            "node_id": "second_node",
        },
        "add_state_field": {
            "branch_def_id": selector,
            "field_name": "new_state",
            "field_type": "str",
        },
        "update_node": {
            "branch_def_id": selector,
            "node_id": "source_node",
            "description": "changed",
        },
        "patch_nodes": {
            "branch_def_id": selector,
            "field": "description",
            "value": "changed in batch",
            "node_ids": "",
        },
        "approve_source_code": {
            "branch_def_id": selector,
            "node_id": "source_node",
            "reason": "reviewed",
            "approved_by": "caller-forge",
        },
        "patch_branch": {
            "branch_def_id": selector,
            "publisher": "caller-forge",
            "author": "caller-forge",
            "changes_json": json.dumps([{
                "op": "set_tags",
                "tags": ["changed"],
            }]),
        },
    }
    return cases[action]


_GENERIC_DENIAL = json.dumps({
    "error": "Authenticated branch author required.",
})


@pytest.mark.parametrize(
    "action",
    ["add_node", "connect_nodes", "set_entry_point", "add_state_field"],
)
def test_structural_mutation_denies_non_author_without_state_change(
    action: str,
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    _seed_branch(base, branch_def_id="public-target", author="bob")
    authenticate("alice")
    before = _stored_bytes(base, "public-target")

    response = _call_raw(action, **_kwargs_for(action, "public-target"))

    assert response == _GENERIC_DENIAL
    assert _stored_bytes(base, "public-target") == before
    assert "bob" not in response
    assert "force" not in response.lower()


@pytest.mark.parametrize(
    "action",
    ["add_node", "connect_nodes", "set_entry_point", "add_state_field"],
)
def test_structural_mutation_owner_control_still_changes_state(
    action: str,
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    _seed_branch(base, branch_def_id="owner-target", author="alice")
    authenticate("alice")
    before = _stored_bytes(base, "owner-target")

    response = _call(action, **_kwargs_for(action, "owner-target"))

    assert "error" not in response
    assert _stored_bytes(base, "owner-target") != before


@pytest.mark.parametrize("selector_kind", ["id", "name"])
def test_foreign_private_structural_selector_matches_missing_exactly(
    selector_kind: str,
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    selector = (
        "private-structural-id"
        if selector_kind == "id"
        else "Private Structural Name"
    )
    _seed_branch(
        base,
        branch_def_id="private-structural-id",
        name="Private Structural Name",
        author="bob",
        visibility="private",
    )
    authenticate("alice")

    denied = _call_raw("add_node", **_kwargs_for("add_node", selector))

    from tinyassets.daemon_server import delete_branch_definition

    assert delete_branch_definition(
        base,
        branch_def_id="private-structural-id",
    )
    missing = _call_raw("add_node", **_kwargs_for("add_node", selector))

    expected = json.dumps({"error": f"Branch '{selector}' not found."})
    assert denied == missing == expected


def test_environment_only_actor_cannot_mutate_matching_public_author(
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    _seed_branch(
        base,
        branch_def_id="environment-authored",
        author="environment-owner",
    )
    authenticate(None)
    before = _stored_bytes(base, "environment-authored")

    response = _call_raw(
        "set_entry_point",
        **_kwargs_for("set_entry_point", "environment-authored"),
    )

    assert response == _GENERIC_DENIAL
    assert _stored_bytes(base, "environment-authored") == before
    assert not (base / "ledger.json").exists()


def test_new_node_and_ledger_actor_are_server_bound_to_authenticated_subject(
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    _seed_branch(base, branch_def_id="attribution-target", author="alice")
    authenticate("alice")
    kwargs = _kwargs_for("add_node", "attribution-target")
    kwargs["author"] = "caller-forge"

    response = _call("add_node", **kwargs)

    from tinyassets.daemon_server import get_branch_definition

    branch = get_branch_definition(
        base,
        branch_def_id="attribution-target",
    )
    node = next(
        item for item in branch["node_defs"]
        if item["node_id"] == response["node_id"]
    )
    ledger = json.loads((base / "ledger.json").read_text(encoding="utf-8"))
    assert node["author"] == "alice"
    assert ledger[-1]["actor"] == "alice"
    assert "caller-forge" not in json.dumps(node)
    assert "environment-owner" not in json.dumps(ledger)


@pytest.mark.parametrize(
    "action",
    ["update_node", "patch_nodes", "approve_source_code"],
)
def test_node_mutation_denies_non_author_before_expansion_or_provenance_change(
    action: str,
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    _seed_branch(
        base,
        branch_def_id="node-public-target",
        author="bob",
        source_code=action == "approve_source_code",
    )
    authenticate("alice")
    before = _stored_bytes(base, "node-public-target")

    response = _call_raw(
        action,
        **_kwargs_for(action, "node-public-target"),
    )

    assert response == _GENERIC_DENIAL
    assert _stored_bytes(base, "node-public-target") == before


@pytest.mark.parametrize(
    "action",
    ["update_node", "patch_nodes", "approve_source_code"],
)
def test_node_mutation_private_and_missing_responses_are_identical(
    action: str,
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    _seed_branch(
        base,
        branch_def_id="node-private-target",
        author="bob",
        visibility="private",
        source_code=action == "approve_source_code",
    )
    authenticate("alice")

    denied = _call_raw(
        action,
        **_kwargs_for(action, "node-private-target"),
    )

    from tinyassets.daemon_server import delete_branch_definition

    assert delete_branch_definition(
        base,
        branch_def_id="node-private-target",
    )
    missing = _call_raw(
        action,
        **_kwargs_for(action, "node-private-target"),
    )

    expected = json.dumps({
        "error": "Branch 'node-private-target' not found.",
    })
    assert denied == missing == expected


@pytest.mark.parametrize(
    "action",
    ["update_node", "patch_nodes", "approve_source_code"],
)
def test_node_mutation_owner_controls_and_approval_attribution(
    action: str,
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    _seed_branch(
        base,
        branch_def_id="node-owner-target",
        author="alice",
        source_code=action == "approve_source_code",
    )
    authenticate("alice")
    before = _stored_bytes(base, "node-owner-target")

    response = _call(
        action,
        **_kwargs_for(action, "node-owner-target"),
    )

    assert "error" not in response
    assert _stored_bytes(base, "node-owner-target") != before
    if action == "approve_source_code":
        assert response["approved_by"] == "alice"
        assert "caller-forge" not in json.dumps(response)


def test_patch_branch_non_author_denial_is_generic_and_force_cannot_bypass(
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    _seed_branch(base, branch_def_id="public-patch-target", author="bob")
    authenticate("alice")
    before = _stored_bytes(base, "public-patch-target")
    kwargs = _kwargs_for("patch_branch", "public-patch-target")

    denied = _call_raw("patch_branch", **kwargs)
    forced = _call_raw("patch_branch", force=True, **kwargs)

    assert denied == forced == _GENERIC_DENIAL
    assert _stored_bytes(base, "public-patch-target") == before
    assert "bob" not in denied
    assert "force" not in denied.lower()


def test_patch_branch_private_and_missing_responses_are_identical(
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    _seed_branch(
        base,
        branch_def_id="private-patch-target",
        author="bob",
        visibility="private",
    )
    authenticate("alice")
    kwargs = _kwargs_for("patch_branch", "private-patch-target")

    denied = _call_raw("patch_branch", **kwargs)

    from tinyassets.daemon_server import delete_branch_definition

    assert delete_branch_definition(base, branch_def_id="private-patch-target")
    missing = _call_raw("patch_branch", **kwargs)

    expected = json.dumps({
        "error": "Branch 'private-patch-target' not found.",
    })
    assert denied == missing == expected


@pytest.mark.parametrize("force", [False, True])
def test_patch_branch_author_keeps_authorized_conflict_recovery_path(
    force: bool,
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    _seed_branch(
        base,
        branch_def_id=f"owner-patch-{force}",
        author="alice",
    )
    authenticate("alice")

    response = _call(
        "patch_branch",
        force=force,
        **_kwargs_for("patch_branch", f"owner-patch-{force}"),
    )

    assert response["status"] == "patched"
    assert response["batch_receipt"]["actor"] == "alice"
    from tinyassets.branch_versions import list_branch_versions

    versions = list_branch_versions(base, f"owner-patch-{force}")
    assert versions
    assert {version.publisher for version in versions} == {"alice"}
    assert "caller-forge" not in json.dumps(response)


def test_delete_denies_public_non_author_and_preserves_branch_and_versions(
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    branch = _seed_branch(
        base,
        branch_def_id="public-delete-target",
        author="bob",
    )
    from tinyassets.branch_versions import (
        get_branch_version,
        publish_branch_version,
    )

    version_id = publish_branch_version(
        base,
        branch,
        publisher="bob",
    ).branch_version_id
    authenticate("alice")
    before = _stored_bytes(base, "public-delete-target")

    response = _call_raw(
        "delete_branch",
        branch_def_id="public-delete-target",
    )

    assert response == _GENERIC_DENIAL
    assert _stored_bytes(base, "public-delete-target") == before
    assert get_branch_version(base, version_id) is not None


def test_delete_private_and_missing_responses_are_identical(
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    _seed_branch(
        base,
        branch_def_id="private-delete-target",
        author="bob",
        visibility="private",
    )
    authenticate("alice")

    denied = _call_raw(
        "delete_branch",
        branch_def_id="private-delete-target",
    )

    from tinyassets.daemon_server import delete_branch_definition

    assert delete_branch_definition(base, branch_def_id="private-delete-target")
    missing = _call_raw(
        "delete_branch",
        branch_def_id="private-delete-target",
    )

    expected = json.dumps({
        "error": "Branch 'private-delete-target' not found.",
    })
    assert denied == missing == expected


def test_delete_author_control_still_removes_branch(
    mutation_env: tuple[Path, Callable[[str | None], None]],
) -> None:
    base, authenticate = mutation_env
    _seed_branch(base, branch_def_id="owner-delete-target", author="alice")
    authenticate("alice")

    response = _call(
        "delete_branch",
        branch_def_id="owner-delete-target",
    )

    from tinyassets.daemon_server import get_branch_definition

    assert response == {
        "branch_def_id": "owner-delete-target",
        "status": "deleted",
    }
    with pytest.raises(KeyError):
        get_branch_definition(base, branch_def_id="owner-delete-target")


def test_branch_action_scope_defense_in_depth_stays_fail_closed() -> None:
    from tinyassets.auth.middleware import require_action_scope
    from tinyassets.auth.provider import action_scope_for

    write_actions = {
        "create_branch",
        "build_branch",
        "add_node",
        "connect_nodes",
        "set_entry_point",
        "add_state_field",
        "update_node",
        "patch_nodes",
        "patch_branch",
    }
    for action in write_actions:
        metadata = action_scope_for("extensions", action)
        assert metadata is not None
        assert metadata.effect == "write"

    for action in {"approve_source_code", "delete_branch"}:
        metadata = action_scope_for("extensions", action)
        assert metadata is not None
        assert metadata.effect == "admin"

    set_provider(_CredentialProvider())
    auth_middleware("alice")
    with pytest.raises(PermissionError, match="No action-scope metadata"):
        require_action_scope("extensions", "missing_branch_action")
