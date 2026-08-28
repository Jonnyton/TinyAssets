"""resolve_connection — propose a connection policy from pasted credential shape.

Requirement source:
``openspec/changes/paste-anything-connection-deposit/specs/connection-inference/spec.md``.

Covers the guarantees that make a no-confirmation deposit defensible: the
operation never receives credential material, an ungroundable host is a refusal
rather than a guess, injected instructions in a paste cannot move the host, a
proposal cannot express a grant a hand-authored deposit could not, and the
owner gate matches the deposit it precedes.

Channel-agnostic on purpose: the model is stubbed, so these assert the fence
around inference, not the model's knowledge of any particular service.
"""

from __future__ import annotations

import json
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
    set_provider(
        _StaticAuthProvider(
            Identity(
                user_id=user_id,
                username=user_id,
                capabilities=["tinyassets.universe.write"],
            )
        )
    )
    auth_middleware("valid")


def _logout() -> None:
    set_provider(DevAuthProvider())
    auth_middleware(None)


@pytest.fixture(autouse=True)
def _reset_auth() -> Any:
    _logout()
    yield
    _logout()


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    return root


def _make_universe(base: Path, uid: str, *, admin: str = "", write: str = "") -> Path:
    from tinyassets.daemon_server import grant_universe_access

    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    if admin:
        grant_universe_access(
            base, universe_id=uid, actor_id=admin, permission="admin", granted_by=admin
        )
    if write:
        grant_universe_access(
            base, universe_id=uid, actor_id=write, permission="write", granted_by=admin
        )
    return udir


def _stub_model(monkeypatch: pytest.MonkeyPatch, reply: Any) -> list[str]:
    """Replace the engine call; return the list of prompts it was given."""
    seen: list[str] = []

    def _fake(udir, uid, *, shape, hints, intent):
        seen.append(json.dumps({"shape": shape, "hints": hints, "intent": intent}))
        return reply if isinstance(reply, str) else json.dumps(reply)

    monkeypatch.setattr(
        "tinyassets.api.connection_inference._run_model", _fake
    )
    return seen


def _resolve(uid: str, **doc: Any) -> dict[str, Any]:
    from tinyassets.api.connection_inference import resolve_connection

    return resolve_connection(universe_id=uid, payload=json.dumps(doc))


_GOOD = {
    "destination": "github",
    "auth_scheme": "bearer",
    "host": "api.github.com",
    "path_template": "/repos/o/r/pulls",
    "methods": ["POST"],
    "confidence": "high",
    "why": "a github_pat_ prefix and a github URL in the paste",
}


# --------------------------------------------------------------------------- #
# The credential never arrives here.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "doc",
    [
        {"secret": "sk-live-abc", "hints": ["api.example.com"]},
        {"token": "ghp_abc", "hints": ["api.example.com"]},
        {"shape": [{"label": "key", "value": "sk-live-abc"}]},
        {"shape": [{"label": "key", "api_key": "abc"}]},
    ],
)
def test_secret_bearing_payloads_are_refused_not_forwarded(
    base: Path, monkeypatch: pytest.MonkeyPatch, doc: dict
) -> None:
    """The no-transmission guarantee is enforced at the boundary.

    A caller that puts a credential in this payload has misunderstood the
    contract; quietly stripping it would let the next caller keep doing it.
    """
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    seen = _stub_model(monkeypatch, _GOOD)

    out = _resolve("u-1", **doc)

    assert out["error"] == "resolve_payload_invalid"
    assert seen == [], "a secret-bearing payload must never reach the model"


def test_only_a_public_prefix_is_accepted(base: Path, monkeypatch) -> None:
    """A public prefix ends at a delimiter; an arbitrary slice of a token does not.

    This is what makes "we only ever receive the identifying part" enforceable
    rather than promised.
    """
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    seen = _stub_model(monkeypatch, _GOOD)

    ok = _resolve(
        "u-1",
        shape=[{"label": "", "prefix": "github_pat_", "length": 93}],
        intent="open pull requests on github",
    )
    assert ok["resolved"] is True

    bad = _resolve("u-1", shape=[{"label": "", "prefix": "sk-abcdefgh", "length": 51}])
    assert bad["error"] == "resolve_payload_invalid"
    assert "public credential prefix" in bad["detail"]
    assert len(seen) == 1, "the rejected shape must not reach the model"


def test_hints_must_look_like_hosts_or_urls(base: Path, monkeypatch) -> None:
    """Anything else is a place credential material could hide."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _stub_model(monkeypatch, _GOOD)

    out = _resolve("u-1", hints=["here is my key sk-live-abcdef and it is secret"])
    assert out["error"] == "resolve_payload_invalid"


# --------------------------------------------------------------------------- #
# What the cut confirmation step used to catch.
# --------------------------------------------------------------------------- #


def test_an_ungroundable_host_is_a_refusal_not_a_guess(base: Path, monkeypatch) -> None:
    """Nothing human reviews the proposal, so a guessed host must not deposit."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _stub_model(monkeypatch, _GOOD)

    # Nothing the user supplied mentions github: the model alone grounds nothing.
    out = _resolve("u-1", shape=[{"label": "", "prefix": "ghp_", "length": 40}])

    assert out["resolved"] is False
    assert "could not tie this credential" in out["reason"]


def test_injected_instructions_cannot_move_the_host(base: Path, monkeypatch) -> None:
    """A pasted "use host X" line is data being read, never a direction."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    # A model that has been successfully steered by injected text.
    _stub_model(monkeypatch, {**_GOOD, "host": "api.evil.example"})

    out = _resolve(
        "u-1",
        shape=[{"label": "", "prefix": "github_pat_", "length": 93}],
        intent="open pull requests on github",
    )

    assert out["resolved"] is False, "a host the user never named must not deposit"


def test_low_confidence_never_proposes(base: Path, monkeypatch) -> None:
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _stub_model(monkeypatch, {**_GOOD, "confidence": "low"})

    out = _resolve("u-1", intent="something on github", hints=["api.github.com"])
    assert out["resolved"] is False


@pytest.mark.parametrize("path", ["/{rest+}", "/repos/{owner}/{repo}/pulls", "", "repos"])
def test_a_proposal_cannot_widen_beyond_a_hand_authored_deposit(
    base: Path, monkeypatch, path: str
) -> None:
    """The same allow-list validates a proposal and a manual deposit."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _stub_model(monkeypatch, {**_GOOD, "path_template": path})

    out = _resolve("u-1", intent="github", hints=["api.github.com"])
    assert out["resolved"] is False
    assert "one exact endpoint" in out["reason"]


# --------------------------------------------------------------------------- #
# Gate + purity.
# --------------------------------------------------------------------------- #


def test_non_owner_gets_the_uniform_absent_envelope(base: Path, monkeypatch) -> None:
    _make_universe(base, "u-1", admin="alice", write="bob")
    _login("bob")
    seen = _stub_model(monkeypatch, _GOOD)

    out = _resolve("u-1", intent="github", hints=["api.github.com"])
    assert out == {"error": "not_found", "resource": "connection"}
    assert seen == []


def test_anonymous_is_refused_before_any_inference(base: Path, monkeypatch) -> None:
    _make_universe(base, "u-1", admin="alice")
    seen = _stub_model(monkeypatch, _GOOD)

    out = _resolve("u-1", intent="github", hints=["api.github.com"])
    assert out["error"] == "authentication_required"
    assert seen == []


def test_resolving_writes_nothing(base: Path, monkeypatch) -> None:
    """It proposes; connect_http deposits. No vault, connection, or grant."""
    from tinyassets.credential_vault import load_credential_vault

    udir = _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _stub_model(monkeypatch, _GOOD)

    out = _resolve(
        "u-1",
        shape=[{"label": "", "prefix": "github_pat_", "length": 93}],
        intent="open pull requests on github",
    )

    assert out["resolved"] is True
    assert load_credential_vault(udir) == []
    assert not (base / "outbound.db").exists()


def test_a_resolved_proposal_carries_the_receipt_sentence(base: Path, monkeypatch) -> None:
    """The sentence the app shows AFTER depositing, built once, server-side."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _stub_model(monkeypatch, _GOOD)

    out = _resolve("u-1", intent="open pull requests on github",
                   hints=["https://github.com/o/r"])

    assert out["resolved"] is True
    assert out["receipt"] == (
        "This key may POST to api.github.com/repos/o/r/pulls - nothing else."
    )
    assert out["allowed_endpoints"] == [
        {"host": "api.github.com", "path_template": "/repos/o/r/pulls",
         "methods": ["POST"]}
    ]


def test_nothing_to_go_on_is_reported_not_guessed(base: Path, monkeypatch) -> None:
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    seen = _stub_model(monkeypatch, _GOOD)

    out = _resolve("u-1")
    assert out["resolved"] is False
    assert seen == []


def test_write_graph_dispatches_the_operation(base: Path, monkeypatch) -> None:
    """Reachable over the pinned write_graph handle, adding no advertised tool."""
    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _stub_model(monkeypatch, _GOOD)

    import importlib

    from tinyassets import universe_server as us

    importlib.reload(us)
    try:
        raw = us.write_graph(
            target="connection",
            operation="resolve_connection",
            graph_id="u-1",
            payload_json=json.dumps(
                {"intent": "github", "hints": ["api.github.com"]}
            ),
        )
        assert json.loads(raw)["resolved"] is True
    finally:
        importlib.reload(us)


def test_a_proposal_deposits_cleanly_through_connect_http(base: Path, monkeypatch) -> None:
    """The whole chain: resolve -> connect_http -> a usable connection.

    The unit tests above stop at the proposal, which would let a shape mismatch
    between what resolve returns and what the deposit accepts survive every test
    and only fail live. This is the founder's actual case end to end.
    """
    import json as _json

    from tinyassets.api.http_connection import connect_http

    _make_universe(base, "u-1", admin="alice")
    _login("alice")
    _stub_model(monkeypatch, _GOOD)

    proposal = _resolve(
        "u-1",
        shape=[{"label": "", "prefix": "github_pat_", "length": 93}],
        hints=["https://github.com/o/r"],
        intent="open pull requests",
    )
    assert proposal["resolved"] is True

    deposited = connect_http(
        universe_id="u-1",
        payload=_json.dumps(
            {
                "destination": proposal["destination"],
                "secret": "github_pat_" + "x" * 82,
                "allowed_endpoints": proposal["allowed_endpoints"],
                "auth_scheme": proposal["auth_scheme"],
            }
        ),
    )

    assert deposited.get("status") == "provisioned", deposited
    assert deposited["destination"] == "github"
    # The grant is exactly what the receipt promised — one method, one path.
    assert deposited["allowed_endpoints"] == [
        {"host": "api.github.com", "path_template": "/repos/o/r/pulls",
         "methods": ["POST"], "param_patterns": {}, "allowed_query": [],
         "query_patterns": {}, "required_query": []}
    ]
    assert deposited["auth_scheme"] == "bearer"
    assert deposited["connection_class"] == "http"
    # And no secret is echoed back anywhere in the projection.
    assert "github_pat_xxx" not in _json.dumps(deposited)


def test_no_serving_binding_degrades_to_the_manual_fields(base: Path, monkeypatch) -> None:
    """A universe with no serving binding must not turn the deposit into an error.

    Binding resolution used to sit outside the guard around the provider call, so
    a fresh universe — or one whose automation and serving providers disagree,
    which is the live state of the founder's own universe — raised out of the
    tool call instead of reporting that it could not identify the service.
    """
    _make_universe(base, "u-1", admin="alice")
    _login("alice")

    def _boom(*a, **k):
        raise PermissionError("connect your provider")

    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.resolve_serving_agent_binding", _boom
    )

    out = _resolve(
        "u-1",
        shape=[{"label": "", "prefix": "github_pat_", "length": 93}],
        intent="open pull requests on github",
    )

    assert out["resolved"] is False
    assert "error" not in out
