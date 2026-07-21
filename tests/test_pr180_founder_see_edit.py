"""PR-180: a founder can SEE and EDIT their own graph via the live /mcp
connector — within the PR-178 five-handle invariant (no new handles; the
capability is added as new *targets* on read_graph / write_graph).

SEE half:  read_graph(target="run", run_id=...) -> get_run snapshot
           (terminal status + result + structured failure reason).
EDIT half: write_graph(target="branch", branch_id=..., changes_json=...) ->
           the existing transactional, author-gated patch_branch handler.

Precedent: write_graph already carries a non-first-class target (persona),
so adding targets keeps the advertised handle set at exactly five (+status)
and the PR-178 ``mcp_public_canary --assert-handles`` guard stays green.
"""
from __future__ import annotations

import asyncio
import contextlib
import importlib
import json

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity

# The actually-advertised handle set on this branch. The five canonical graph/page
# handles + get_status are the PR-178 invariant; `converse` is a pre-existing handle
# added by the founder-identity relay work (b91a6b07, on origin/main) — NOT by this
# S5 change (round-12 #7: align the expected set with reality; the separate
# assert-handles canary allowlist for converse is tracked outside this branch).
# The invariant THIS file guards: adding read_graph/write_graph *targets* (run,
# branch, engine, …) adds NO new handle.
_CANONICAL_HANDLES = {
    "read_graph",
    "write_graph",
    "run_graph",
    "read_page",
    "write_page",
    "get_status",
}
ADVERTISED = _CANONICAL_HANDLES | {"converse"}

_BASIC_SPEC = {
    "name": "Founder branch",
    "entry_point": "ready",
    "node_defs": [{
        "node_id": "ready",
        "display_name": "Ready",
        "prompt_template": "Do the work.",
    }],
    "edges": [
        {"from": "START", "to": "ready"},
        {"from": "ready", "to": "END"},
    ],
    "state_schema": [{"name": "x", "type": "str"}],
}


@pytest.fixture
def server_env(tmp_path, monkeypatch):
    """Live /mcp surface (tinyassets.universe_server) on an isolated data dir."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "founder")
    from tinyassets import universe_server as us

    importlib.reload(us)
    yield us
    importlib.reload(us)


# ── PR-178 invariant: the new targets add NO new handles ────────────────────

def test_five_handles_unchanged_after_new_targets(server_env):
    us = server_env
    advertised = {t.name for t in asyncio.run(us.mcp.list_tools(run_middleware=True))}
    assert advertised == ADVERTISED


# ── SEE half: read_graph target=run ─────────────────────────────────────────

def test_read_graph_run_routes_to_get_run(server_env):
    """target=run reaches the get_run handler (not unknown_target)."""
    us = server_env
    payload = json.loads(us.read_graph(target="run", run_id="no-such-run"))
    assert payload.get("error") != "unknown_target"
    # get_run's own not-found error proves the route reached the handler.
    assert "not found" in payload.get("error", "").lower()


def test_read_graph_run_listed_in_allowed_targets(server_env):
    us = server_env
    payload = json.loads(us.read_graph(target="bogus"))
    assert payload["error"] == "unknown_target"
    assert "run" in payload["allowed_targets"]
    assert "runs" in payload["allowed_targets"]


# ── EDIT half: write_graph target=branch ────────────────────────────────────

def test_write_graph_branch_routes_to_patch_branch(server_env):
    """target=branch reaches the patch_branch handler (not unknown_target)."""
    us = server_env
    payload = json.loads(us.write_graph(target="branch", branch_id="", changes_json=""))
    assert payload.get("error") != "unknown_target"
    # patch_branch's own field validation proves the route reached the handler
    # (it rejects on a missing required field rather than unknown_target).
    assert "required" in payload.get("error", "")


def test_write_graph_branch_listed_in_allowed_targets(server_env):
    us = server_env
    payload = json.loads(us.write_graph(target="bogus"))
    assert payload["error"] == "unknown_target"
    assert "branch" in payload["allowed_targets"]


def test_founder_edits_own_branch_round_trip(server_env):
    """End-to-end: build a branch, then EDIT it via the connector handle as
    the founder (author == UNIVERSE_SERVER_USER), and confirm the edit lands.
    """
    us = server_env
    built = json.loads(us.extensions(action="build_branch", spec_json=json.dumps(_BASIC_SPEC)))
    bid = built["branch_def_id"]

    patched = json.loads(us.write_graph(
        target="branch",
        branch_id=bid,
        changes_json=json.dumps([{"op": "set_published", "published": True}]),
    ))
    assert "error" not in patched, patched
    assert patched.get("status") != "rejected", patched

    # The edit persisted on the founder's own branch.
    listing = json.loads(us.extensions(action="list_branches", scope="all"))
    summary = next(b for b in listing["branches"] if b["branch_def_id"] == bid)
    assert summary["published"] is True


def test_patch_branch_is_author_gated_via_connector(server_env, monkeypatch):
    """A non-author cannot edit someone else's branch through the handle
    (inherits patch_branch's BUG-081 author gate). force=true is required to
    bypass, so the default connector path stays safe."""
    us = server_env
    built = json.loads(us.extensions(action="build_branch", spec_json=json.dumps(_BASIC_SPEC)))
    bid = built["branch_def_id"]

    # Switch identity to a different user, reload so the actor changes.
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "intruder")
    importlib.reload(us)

    blocked = json.loads(us.write_graph(
        target="branch",
        branch_id=bid,
        changes_json=json.dumps([{"op": "set_published", "published": True}]),
    ))
    # Author gate fires: either an error or a rejected status, never a clean apply.
    assert blocked.get("status") == "rejected" or "error" in blocked, blocked


# ── ENGINE half: write_graph target=engine (round-11 #1) ─────────────────────
# The legacy `universe` fat tool is hidden from tools/list (PR-178 drift guard),
# so `universe action=set_engine` was a dead end for real chatbot users. Engine
# declaration now routes through the VISIBLE write_graph handle — no new handle.
#
# The universe write ACL deliberately ignores UNIVERSE_SERVER_USER (an env var
# must never confer universe write authority); it requires a real authenticated
# request identity. These tests bind one the way the live /mcp path does.


class _StaticAuthProvider(AuthProvider):
    """Auth-required provider resolving the bearer token "ok" to one identity."""

    def __init__(self, identity: Identity | None) -> None:
        self.identity = identity

    def resolve_token(self, token: str) -> Identity | None:
        return self.identity if token == "ok" else None

    def is_auth_required(self) -> bool:
        return True

    def register_client(self, metadata: dict) -> dict:
        return {"client_id": "test-client", **metadata}

    def create_authorization(self, *a, **k) -> str:
        return "test-code"

    def exchange_code(self, *a, **k) -> dict | None:
        return None


_FOUNDER_SCOPES = [
    "tinyassets.universe.read",
    "tinyassets.universe.write",
    "tinyassets.universe.admin",
    "tinyassets.universe.costly",
]


@contextlib.contextmanager
def _founder_session(user_id: str):
    """Bind an authenticated founder request identity, then restore dev auth."""
    set_provider(_StaticAuthProvider(
        Identity(user_id=user_id, username=user_id, capabilities=list(_FOUNDER_SCOPES))
    ))
    auth_middleware("ok")
    try:
        yield
    finally:
        set_provider(DevAuthProvider())
        auth_middleware(None)


def test_write_graph_engine_listed_in_allowed_targets(server_env):
    us = server_env
    payload = json.loads(us.write_graph(target="bogus"))
    assert payload["error"] == "unknown_target"
    assert "engine" in payload["allowed_targets"]


def test_write_graph_engine_declares_lane_end_to_end(server_env):
    """Authenticated tools/list -> tools/call: the DOCUMENTED path works end to
    end. write_graph is advertised while the legacy `universe` tool is hidden,
    and target=engine declares a non-secret lane on the founder's own universe.
    """
    us = server_env
    advertised = {t.name for t in asyncio.run(us.mcp.list_tools(run_middleware=True))}
    assert "write_graph" in advertised  # reachable canonical handle
    assert "universe" not in advertised  # PR-178: no new/legacy fat handle

    with _founder_session("founder"):
        # Birth the founder's universe through the visible handle, then DECLARE
        # its engine lane through the same handle (founder owns it -> write ACL).
        born = json.loads(us.write_graph(target="universe", text=""))
        uid = born["universe_id"]
        assert born["status"] == "born"

        declared = json.loads(us.write_graph(
            target="engine",
            graph_id=uid,
            changes_json=json.dumps({
                "engine_source": "self_hosted_endpoint",
                "endpoint": "https://ollama.example.com",
            }),
        ))
    # Reached set_engine (not unknown_target) and produced an honest declaration.
    assert declared.get("error") != "unknown_target", declared
    assert declared["engine_source"] == "self_hosted_endpoint"
    assert declared["status"] == "engine_declared"
    assert declared["executable"] is False


def test_write_graph_engine_never_accepts_raw_key(server_env):
    """Defense-in-depth at the connector boundary: a raw API key routed through
    the visible handle is REFUSED by the handler (Phase-2 is an out-of-chat
    deposit, C3) — even for an authenticated, authorized founder."""
    us = server_env
    with _founder_session("founder"):
        born = json.loads(us.write_graph(target="universe", text=""))
        uid = born["universe_id"]
        out = json.loads(us.write_graph(
            target="engine",
            graph_id=uid,
            changes_json=json.dumps({
                "engine_source": "byo_api_key",
                "service": "anthropic",
                "api_key": "sk-ant-api03-" + "A" * 40,
            }),
        ))
    assert "error" in out and out.get("status") != "engine_set"
