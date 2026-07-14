"""Anonymous-write gate for mutating MCP handles (write_graph, write_page).

Founder decision 2026-07-13, restoring the production-mcp-sweep P0 gate
server-side: the old "gate" was only the chatbot client's approval prompt,
removed by openWorldHint=false (issue 3). Reads stay open in every auth
mode; OAuth-backed modes (``UNIVERSE_SERVER_AUTH=optional`` or gated)
reject anonymous writes with actionable guidance. Dev mode keeps writes
open so local flows and tests are unaffected.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tinyassets.auth.middleware import (
    auth_middleware,
    set_provider,
    write_gate_rejection,
)
from tinyassets.auth.provider import (
    AuthProvider,
    DevAuthProvider,
    Identity,
    create_provider,
)

_SUBJECT = Identity(
    user_id="oauth-subject-1", username="u", capabilities=["read", "write"],
)


class _FakeProvider(AuthProvider):
    """Resolves token 'valid' -> identity; write-gating is configurable."""

    def __init__(self, *, gates_writes: bool, identity: Identity | None) -> None:
        self._gates_writes = gates_writes
        self._identity = identity

    def resolve_token(self, token: str) -> Identity | None:
        return self._identity if token == "valid" else None

    def is_auth_required(self) -> bool:
        return False

    def writes_require_identity(self) -> bool:
        return self._gates_writes

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
def _reset_auth_context():
    set_provider(DevAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


# ── provider policy ─────────────────────────────────────────────────────────

def test_dev_provider_leaves_writes_open():
    assert DevAuthProvider().writes_require_identity() is False


def test_optional_mode_gates_writes(monkeypatch, tmp_path):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_AUTH", "optional")
    provider = create_provider()
    assert provider.is_auth_required() is False  # reads stay open
    assert provider.writes_require_identity() is True


def test_gated_mode_gates_writes(monkeypatch, tmp_path):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_AUTH", "true")
    assert create_provider().writes_require_identity() is True


def test_dev_mode_from_env_leaves_writes_open(monkeypatch, tmp_path):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_AUTH", "false")
    assert create_provider().writes_require_identity() is False


# ── write_gate_rejection envelope ───────────────────────────────────────────

def test_rejection_is_actionable_for_anonymous():
    set_provider(_FakeProvider(gates_writes=True, identity=_SUBJECT))
    auth_middleware(None)
    envelope = write_gate_rejection("write_graph")
    assert envelope is not None
    payload = json.loads(envelope)
    assert payload["status"] == "rejected"
    assert payload["auth_required"] is True
    assert payload["tool"] == "write_graph"
    # Actionable: says reads stay open and how to get write access.
    assert "OAuth" in payload["error"]
    assert "reads stay open" in payload["error"].lower()


def test_resolved_identity_passes_gate():
    set_provider(_FakeProvider(gates_writes=True, identity=_SUBJECT))
    auth_middleware("valid")
    assert write_gate_rejection("write_graph") is None


def test_non_gating_provider_passes_anonymous():
    set_provider(_FakeProvider(gates_writes=False, identity=_SUBJECT))
    auth_middleware(None)
    assert write_gate_rejection("write_graph") is None


# ── universe_server handle wiring ───────────────────────────────────────────
# target="__gate_probe__" is invalid on purpose: the gate check runs before
# target dispatch, so a gated call returns the auth envelope while an
# ungated call reaches the unknown-target error — no storage is touched.


def _payload(raw: str) -> dict[str, Any]:
    return json.loads(raw)


def test_universe_write_graph_rejects_anonymous_when_gated():
    from tinyassets import universe_server

    set_provider(_FakeProvider(gates_writes=True, identity=_SUBJECT))
    auth_middleware(None)
    payload = _payload(universe_server.write_graph(target="__gate_probe__"))
    assert payload.get("auth_required") is True


def test_universe_write_graph_passes_resolved_identity():
    from tinyassets import universe_server

    set_provider(_FakeProvider(gates_writes=True, identity=_SUBJECT))
    auth_middleware("valid")
    payload = _payload(universe_server.write_graph(target="__gate_probe__"))
    assert "auth_required" not in payload  # reached unknown-target handling


def test_universe_write_graph_open_in_dev_mode():
    from tinyassets import universe_server

    set_provider(DevAuthProvider())
    auth_middleware(None)
    payload = _payload(universe_server.write_graph(target="__gate_probe__"))
    assert "auth_required" not in payload


def test_universe_write_page_filing_rejects_anonymous_when_gated():
    from tinyassets import universe_server

    set_provider(_FakeProvider(gates_writes=True, identity=_SUBJECT))
    auth_middleware(None)
    # kind is a filing — always a real write, even with dry_run left True.
    payload = _payload(universe_server.write_page(kind="bug", title="x"))
    assert payload.get("auth_required") is True


def test_universe_write_page_mutating_write_rejects_anonymous(monkeypatch):
    from tinyassets import universe_server

    set_provider(_FakeProvider(gates_writes=True, identity=_SUBJECT))
    auth_middleware(None)
    payload = _payload(
        universe_server.write_page(
            page="p", content="c", dry_run=False,
        )
    )
    assert payload.get("auth_required") is True


def test_universe_write_page_dry_run_preview_stays_open(monkeypatch):
    from tinyassets import universe_server

    set_provider(_FakeProvider(gates_writes=True, identity=_SUBJECT))
    auth_middleware(None)
    seen: dict[str, Any] = {}

    def _fake_wiki(**kwargs: Any) -> str:
        seen.update(kwargs)
        return json.dumps({"status": "ok", "dry_run": True})

    monkeypatch.setattr(universe_server, "_wiki_impl", _fake_wiki)
    payload = _payload(
        universe_server.write_page(page="p", old_text="a", new_text="b")
    )
    assert payload == {"status": "ok", "dry_run": True}
    assert seen.get("dry_run") is True  # preview reached the wiki layer


# ── directory_server handle wiring ──────────────────────────────────────────

def test_directory_write_graph_rejects_anonymous_when_gated():
    from tinyassets import directory_server

    set_provider(_FakeProvider(gates_writes=True, identity=_SUBJECT))
    auth_middleware(None)
    payload = _payload(directory_server.write_graph(target="__gate_probe__"))
    assert payload.get("auth_required") is True


def test_directory_write_page_filing_rejects_anonymous_when_gated():
    from tinyassets import directory_server

    set_provider(_FakeProvider(gates_writes=True, identity=_SUBJECT))
    auth_middleware(None)
    payload = _payload(directory_server.write_page(kind="bug", title="x"))
    assert payload.get("auth_required") is True
