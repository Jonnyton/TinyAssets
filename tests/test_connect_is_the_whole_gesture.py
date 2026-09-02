"""Connecting a subscription is the whole gesture: it deposits AND serves.

Live, 2026-09-01. The founder pasted a Codex credential through the app. The
deposit succeeded and chat worked on it, and every run failed:

    Connect your provider before running this universe.
    permission_denied:provider_not_bound

`get_status` said `no_serving_runtime` -- "registering a provider is not
selecting it". The deposit result carried `next: bind_serving_provider` as a
hint, to a surface where nobody reads hints. Tiny, from inside: "provider
registration and provider selection must not be separable in a way that
leaves me runnable-on-paper but dead in practice."

Two halves, both pinned here:

* the SERVER: a deposit into a universe that serves on nothing serves on it;
  a universe that already serves keeps its explicit choice;
* the APP: the pasted-credential path finishes the gesture, and the heartbeat
  heals a universe that has a mind deposited but nothing serving on it.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity


class _StaticAuthProvider(AuthProvider):
    def __init__(self, identity: Identity | None) -> None:
        self.identity = identity

    def resolve_token(self, token: str) -> Identity | None:
        return self.identity if token == "valid" else None

    def is_auth_required(self) -> bool:
        return True

    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"client_id": "test-client", **metadata}

    def create_authorization(self, *a: Any, **k: Any) -> str:
        return "test-code"

    def exchange_code(self, *a: Any, **k: Any) -> dict[str, Any] | None:
        return None


def _login(user_id: str) -> None:
    set_provider(_StaticAuthProvider(Identity(
        user_id=user_id, username=user_id, capabilities=["tinyassets.universe.write"],
    )))
    auth_middleware("valid")


@pytest.fixture(autouse=True)
def _reset_auth():
    set_provider(DevAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    monkeypatch.delenv("TINYASSETS_ALLOW_CLAUDE_SERVING", raising=False)
    return root


def _universe(base: Path, uid: str, admin: str) -> Path:
    from tinyassets.daemon_server import grant_universe_access

    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    grant_universe_access(
        base, universe_id=uid, actor_id=admin, permission="admin", granted_by=admin,
    )
    return udir


def _deposit(uid: str, service: str, material: str) -> dict[str, Any]:
    from tinyassets.api.llm_deposit import connect_llm

    b64 = base64.b64encode(material.encode("utf-8")).decode("ascii")
    return connect_llm(
        universe_id=uid,
        payload=json.dumps({"service": service, "auth_material_b64": b64}),
    )


_CODEX_BUNDLE = json.dumps({"tokens": {
    "access_token": "a", "refresh_token": "r", "account_id": "acct-1",
}})


def _serving_bindings(base: Path, uid: str) -> list[dict[str, Any]]:
    from tinyassets.custom_agents import list_bindings

    return [
        b for b in list_bindings(base, universe_id=uid, limit=100)
        if b.get("status") == "serving"
    ]


# --------------------------------------------------------------- the server


def test_a_deposit_into_a_universe_serving_on_NOTHING_serves_on_it(base):
    """THE regression. Before: `status: deposited`, `next: bind_serving_provider`,
    and a universe whose chat worked while every run said provider_not_bound."""
    _universe(base, "u-1", "founder")
    _login("founder")

    result = _deposit("u-1", "codex", _CODEX_BUNDLE)

    assert result["status"] == "deposited"
    assert result["serving"]["status"] == "serving", result
    assert result["serving"]["provider"] == "codex"
    assert "next" not in result, "the hint nobody reads is still the only path"
    [binding] = _serving_bindings(base, "u-1")
    assert binding["agent_binding_id"] == result["agent_binding_id"]
    assert result["expected_revision"] == binding["revision"]


def test_a_universe_that_ALREADY_serves_keeps_its_choice(base):
    """Write-only where write-only was chosen for a reason: re-pointing a
    serving universe is an explicit decision, and a re-deposit does not make
    it silently."""
    _universe(base, "u-1", "founder")
    _login("founder")
    first = _deposit("u-1", "codex", _CODEX_BUNDLE)
    assert first["serving"]["status"] == "serving"
    [before] = _serving_bindings(base, "u-1")

    again = _deposit("u-1", "codex", _CODEX_BUNDLE.replace("acct-1", "acct-1"))

    assert again["status"] == "deposited"
    assert again["serving"] == {
        "status": "unchanged",
        "reason": "already_serving",
        "agent_binding_id": before["agent_binding_id"],
    }
    assert again["next"].startswith("write_graph target=agent_binding")
    [after] = _serving_bindings(base, "u-1")
    assert after["revision"] == before["revision"], "a re-deposit re-pointed serving"


def test_a_HELD_bind_never_turns_a_successful_deposit_into_a_failure(base):
    """Claude serving is held behind an operator opt-in. The deposit still
    lands and is reported as such; the hold is reported beside it, with the
    explicit path left open."""
    _universe(base, "u-1", "founder")
    _login("founder")

    result = _deposit("u-1", "claude", "sk-ant-oat-token")

    assert result["status"] == "deposited"
    assert result["serving"]["status"] == "held", result
    assert result["next"].startswith("write_graph target=agent_binding")
    assert _serving_bindings(base, "u-1") == []


def test_the_bind_is_actually_WIRED_into_the_deposit(base, monkeypatch):
    """Testing the helper is not testing that the deposit calls it."""
    import tinyassets.api.llm_deposit as mod

    calls: list[str] = []

    def _spy(base_, *, universe_id, universe_dir, actor, service):
        calls.append(f"{universe_id}:{actor}:{service}")
        return {"status": "held", "reason": "spy"}

    monkeypatch.setattr(mod, "_serve_if_nothing_does", _spy)
    _universe(base, "u-1", "founder")
    _login("founder")

    result = _deposit("u-1", "codex", _CODEX_BUNDLE)

    assert calls == ["u-1:founder:codex"]
    assert result["serving"] == {"status": "held", "reason": "spy"}


# ------------------------------------------------------------------ the app


@pytest.fixture
def app_html() -> str:
    from tinyassets.onboarding import render_app_html

    html, _csp = render_app_html()
    return html


def test_the_pasted_credential_path_finishes_the_gesture(app_html):
    """The generic connect form deposited and printed the receipt. It now points
    the universe at the deposit and says, in words, whether that worked."""
    deposit = app_html.index("await MCP.connectLLM(service,b64)")
    serve = app_html.index("serveOn(service)", deposit)
    assert serve - deposit < 600, "the serve step is not in the paste path"
    assert "servingSentence(service, sv)" in app_html


def test_the_heartbeat_heals_a_universe_with_a_mind_but_nothing_serving(app_html):
    """The founder's exact state: deposited, chatting, `no_serving_runtime`.
    Healed on the next status poll, once per page, with no re-paste."""
    poll = app_html.index("async function pollStatus()")
    heal = app_html.index("healServing(s)", poll)
    assert heal - poll < 1200, "the heal is not on the heartbeat"
    assert 'p.reason==="no_serving_runtime"' in app_html
    assert re.search(r"if\(servingHealAttempted\) return;", app_html), (
        "the heal must run at most once per page"
    )
    assert '"/mcp/app/serving/bind"' in app_html
