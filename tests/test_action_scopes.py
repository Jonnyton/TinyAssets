"""PR-139 slice 8 action-scope registry and checkpoint tests."""

from __future__ import annotations

import json
from typing import Any

import pytest

from workflow.auth.middleware import auth_middleware, require_action_scope, set_provider
from workflow.auth.provider import (
    AuthProvider,
    DevAuthProvider,
    Identity,
    PermissionAction,
    build_action_scope_registry,
)


class StaticAuthProvider(AuthProvider):
    def __init__(self, identity: Identity | None) -> None:
        self.identity = identity

    def resolve_token(self, token: str) -> Identity | None:
        return self.identity if token == "ok" else None

    def is_auth_required(self) -> bool:
        return True

    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"client_id": "test-client", **metadata}

    def create_authorization(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        return "test-code"

    def exchange_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any] | None:
        return None


@pytest.fixture(autouse=True)
def _reset_auth_provider() -> None:
    set_provider(DevAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


def test_action_scope_registry_is_derived_from_internal_dispatch_tables() -> None:
    registry = build_action_scope_registry()

    assert registry["universe.inspect"].oauth_scope == "workflow.universe.read"
    assert registry["universe.inspect"].effect == "read"
    assert "UNIVERSE_ACTIONS" in registry["universe.inspect"].source

    assert registry["universe.daemon_banish"].oauth_scope == "workflow.universe.admin"
    assert registry["universe.daemon_banish"].effect == "admin"

    assert registry["wiki.read"].oauth_scope == "workflow.wiki.read"
    assert registry["wiki.write"].oauth_scope == "workflow.wiki.write"

    assert registry["extensions.run_branch"].oauth_scope == "workflow.extensions.costly"
    assert registry["gates.list"].oauth_scope == "workflow.gates.read"

    assert all("schema" not in row.source.lower() for row in registry.values())


def test_money_escrow_writes_require_write_scope_not_read() -> None:
    """slice1a review CRITICAL 2: the money WRITE actions must derive a write
    (or costlier) scope, never read. A read classification would let an
    authenticated reader fund / set-wallet / withdraw."""
    registry = build_action_scope_registry()

    # These mutate balances / move funds out — must NOT be read-scoped.
    money_writes = (
        "escrow_fund",
        "escrow_set_wallet",
        "escrow_withdraw",
        "escrow_release",
    )
    for action in money_writes:
        row = registry[f"extensions.{action}"]
        assert row.effect != "read", (
            f"{action} derived read-scope ({row.oauth_scope}); money writes "
            f"must require write authorization"
        )
        assert row.effect in ("write", "costly", "admin"), row.effect
        assert row.oauth_scope != "workflow.extensions.read", action


def test_action_scope_status_self_audit_reports_table_and_caveats() -> None:
    from workflow.api.extensions import _extensions_impl

    payload = json.loads(_extensions_impl(action="get_action_scope_status"))

    assert payload["source"] == "internal_dispatch_action_registries"
    assert "not raw MCP tool schemas" in payload["scope_derivation"]
    assert "workflow.universe.admin" in payload["oauth_scopes"]
    assert payload["counts"]["actions"] >= 80
    assert any(
        row["action_name"] == "universe.daemon_banish"
        and row["oauth_scope"] == "workflow.universe.admin"
        for row in payload["actions"]
    )
    assert payload["caveats"]


def test_permission_action_requires_named_scope_when_present() -> None:
    identity = Identity(
        user_id="user::operator",
        username="operator",
        capabilities=["workflow.universe.write"],
    )

    verdict = identity.can(
        PermissionAction(
            name="universe.submit_request",
            required_scope="workflow.universe.write",
        )
    )
    assert verdict.allowed is True
    assert verdict.required_scope == "workflow.universe.write"

    legacy_only = Identity(
        user_id="user::legacy",
        username="legacy",
        capabilities=["universe.submit_request"],
    )
    assert legacy_only.can(
        PermissionAction(
            name="universe.submit_request",
            required_scope="workflow.universe.write",
        )
    ).allowed is False


def test_action_scope_checkpoint_enforces_only_when_auth_is_enabled() -> None:
    set_provider(StaticAuthProvider(Identity(
        user_id="user::operator",
        username="operator",
        capabilities=["workflow.universe.admin"],
    )))
    auth_middleware("ok")
    require_action_scope("universe", "daemon_banish")

    set_provider(StaticAuthProvider(Identity(
        user_id="user::reader",
        username="reader",
        capabilities=["workflow.universe.read"],
    )))
    auth_middleware("ok")
    with pytest.raises(PermissionError, match="workflow.universe.admin"):
        require_action_scope("universe", "daemon_banish")

    set_provider(DevAuthProvider())
    auth_middleware(None)
    require_action_scope("universe", "daemon_banish")
