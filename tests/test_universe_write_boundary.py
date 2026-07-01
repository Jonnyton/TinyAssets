"""Executable acceptance gate for the founder/universe write boundary (D0a).

Encodes the invariant from the founder/universe identity design — see
``docs/design-notes/2026-06-26-founder-and-universe-identity.md`` (decision
D0a) and ``openspec/changes/universe-creation`` requirement *"MCP writes are
scoped to the founder's own universe"*:

    A universe created through ``universe action=create_universe`` is OWNED by
    the founder who created it. Another authenticated founder — even one
    holding the ``tinyassets.universe.write`` scope — MUST NOT be able to
    write that universe's brain.

Status (Claude, 2026-06-30 — ACL-synthesis slice): the invariant is now
ENFORCED. ``_action_create_universe`` grants the authenticated founder an
``admin`` ACL row on create (D0a founder-grant-on-create), and the single ACL
path in ``tinyassets.api.permissions`` denies writes to any actor without a
``write``/``admin`` grant. The two cross-founder gates below therefore now
PASS as permanent regression guards; their prior ``xfail(strict=True)`` markers
were removed once D0a landed (as their design note prescribed — an xpass under
strict was the signal to promote them to hard guards).

The anonymous guard is satisfied by the scope gate, which blocks all anonymous
writes when auth is required; it has always been a plain green guard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tinyassets.api.universe as us
from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity
from tinyassets.daemon_server import universe_access_permission


class _StaticAuthProvider(AuthProvider):
    """Auth-required provider that resolves the bearer token ``"ok"`` to a
    fixed identity, mirroring tests/test_universe_server_isolation.py."""

    def __init__(self, identity: Identity | None) -> None:
        self.identity = identity

    def resolve_token(self, token: str) -> Identity | None:
        return self.identity if token == "ok" else None

    def is_auth_required(self) -> bool:
        return True

    def register_client(self, metadata: dict) -> dict:
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
    ) -> dict | None:
        return None


# Full founder scope set: read + write + admin + costly (create_universe is a
# costly action, so the creating founder needs the costly scope).
_FOUNDER_SCOPES = [
    "tinyassets.universe.read",
    "tinyassets.universe.write",
    "tinyassets.universe.admin",
    "tinyassets.universe.costly",
]


@pytest.fixture
def universe_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    return base


@pytest.fixture(autouse=True)
def _reset_auth_provider() -> None:
    set_provider(DevAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


def _authenticate(user_id: str, scopes: list[str]) -> None:
    identity = Identity(
        user_id=user_id,
        username=user_id,
        capabilities=list(scopes),
    )
    set_provider(_StaticAuthProvider(identity))
    auth_middleware("ok")


def _authenticate_anonymous() -> None:
    """Auth REQUIRED, but no valid token → identity resolves to ANONYMOUS."""
    set_provider(_StaticAuthProvider(None))
    auth_middleware(None)


def _create_universe_as(founder: str, uid: str, text: str = "A founder seed.") -> dict:
    _authenticate(founder, _FOUNDER_SCOPES)
    return json.loads(us._universe_impl(
        action="create_universe",
        universe_id=uid,
        text=text,
    ))


class TestFounderWriteBoundary:
    """A founder owns the universe they create; other founders cannot write it."""

    def test_created_universe_not_writable_by_other_founder(self, universe_base):
        created = _create_universe_as("alice", "u-acceptance-alice")
        assert created.get("status") == "created", created
        target = created["universe_id"]

        # A *different* authenticated founder, holding the write scope but with
        # no grant on alice's universe, must be denied.
        _authenticate("mallory", ["tinyassets.universe.write"])
        out = json.loads(us._universe_impl(
            action="set_premise",
            universe_id=target,
            text="Hostile cross-founder overwrite.",
        ))

        assert out.get("error") == "universe_access_denied", out
        assert out.get("required_permission") == "write"

    def test_create_universe_grants_founder_owner_acl(self, universe_base):
        created = _create_universe_as("alice", "u-acceptance-owner")
        assert created.get("status") == "created", created
        target = created["universe_id"]

        # The founder must hold an owner-grade (write/admin) ACL on their own
        # created universe — the mechanism that makes the write boundary real.
        # On a zero-ACL universe this returns the public "read" convention.
        perm = universe_access_permission(
            universe_base,
            universe_id=target,
            actor_id="alice",
        )
        assert perm in {"write", "admin"}, (
            f"founder 'alice' has permission {perm!r} on her own created "
            "universe; expected an owner (write/admin) grant"
        )

    def test_created_universe_rejects_anonymous_write(self, universe_base):
        # Green guard: already enforced on origin/main in auth-required mode —
        # the scope gate blocks every anonymous write regardless of ownership.
        created = _create_universe_as("alice", "u-acceptance-anon")
        assert created.get("status") == "created", created
        target = created["universe_id"]

        _authenticate_anonymous()
        out = json.loads(us._universe_impl(
            action="set_premise",
            universe_id=target,
            text="Anonymous overwrite.",
        ))

        assert "error" in out, out
        # Denied — never an accepted write.
        assert out.get("status") != "updated", out
