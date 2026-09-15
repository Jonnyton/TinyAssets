"""Real authenticated bootstrap ingress; hosted exchange uses synthetic keys."""

import asyncio

import httpx
import pytest
from starlette.applications import Starlette

from tests.test_hosted_model_auth import CHALLENGE, VERIFIER
from tests.test_model_bootstrap import rig  # noqa: F401 - shared real-store fixture
from tinyassets import onboarding
from tinyassets.onboarding import hosted_model_auth as hosted

pytestmark = pytest.mark.usefixtures("rig")


@pytest.fixture(autouse=True)
def ingress(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ONBOARDING_APP", "1")
    monkeypatch.setattr(onboarding, "app_config", lambda: {"resource": "https://tinyassets.io/mcp"})
    monkeypatch.setattr(onboarding, "_read_home", lambda identity, **kw: "u-owner")
    with hosted._lock:
        hosted._pending.clear()
    yield
    with hosted._lock:
        hosted._pending.clear()


def post(operation, data, *, origin="https://tinyassets.io"):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(
            app=Starlette(routes=onboarding.onboarding_routes())), base_url="https://tinyassets.io",
        ) as client:
            return await client.post("/mcp/app/model-connect/" + operation,
                                     json=data, headers={"Origin": origin})
    return asyncio.run(run())


def begin():
    return post("begin", {"preset_id": "openrouter_user_models_v1", "code_challenge": CHALLENGE})


def test_begin_exchange_and_resume_real_store_composition(monkeypatch):
    first = begin()
    assert first.status_code == 200, first.text
    assert first.headers["cache-control"] == "no-store"
    calls = []
    async def exchange(**kwargs):
        calls.append(kwargs)
        return "synthetic-oauth-key"
    monkeypatch.setattr(hosted, "exchange_key", exchange)
    payload = {"flow": first.json()["flow"], "code": "synthetic-code", "code_verifier": VERIFIER}
    result = post("exchange", payload)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "confirmation_required"
    assert "synthetic-oauth-key" not in result.text
    assert len(calls) == 1
    replay = post("exchange", payload)
    assert replay.status_code == 409
    assert len(calls) == 1
    resume = post("resume", {"preset_id": "openrouter_user_models_v1"})
    assert resume.status_code == 200, resume.text
    assert resume.json()["request_id"] == result.json()["request_id"]


@pytest.mark.parametrize("origin", ["", "http://tinyassets.io", "https://elsewhere.invalid",
    "https://tinyassets.io/path", "https://tinyassets.io?query=1"])
def test_begin_requires_exact_canonical_origin_before_state_changes(origin):
    response = post("begin", {"preset_id": "openrouter_user_models_v1",
                              "code_challenge": CHALLENGE}, origin=origin)
    assert response.status_code == 403
    assert not hosted._pending


def test_foreign_home_cannot_redeem_or_start(monkeypatch):
    from tinyassets.auth.middleware import identity_context
    from tinyassets.auth.provider import Identity

    first = begin()
    async def forbidden(**kwargs):
        raise AssertionError("must not contact provider")
    monkeypatch.setattr(hosted, "exchange_key", forbidden)
    stranger = Identity(user_id="stranger", username="stranger", capabilities=["write"])
    with identity_context(stranger):
        result = post("exchange", {"flow": first.json()["flow"], "code": "code",
                                   "code_verifier": VERIFIER})
        assert result.status_code == 409
        assert begin().status_code == 409
    assert first.json()["flow"] in hosted._pending


def test_only_callback_shell_is_exempt_from_bearer_challenge():
    from tinyassets.auth.middleware import _auth_challenge_path

    assert not _auth_challenge_path(hosted.CALLBACK_PREFIX + "a" * 43)
    assert _auth_challenge_path(hosted.CALLBACK_PREFIX + "a" * 42)
    assert _auth_challenge_path(hosted.CALLBACK_PREFIX + "a" * 43 + "/exchange")
    assert _auth_challenge_path("/mcp/app/model-connect/begin")
    assert _auth_challenge_path("/mcp/app/model-connect/exchange")


def test_bad_challenge_does_not_bootstrap_a_home(monkeypatch):
    monkeypatch.setattr(onboarding, "_read_home", lambda *a, **kw: "")
    def forbidden(*args):
        raise AssertionError("invalid begin must not provision home")
    monkeypatch.setattr(onboarding, "_bootstrap_home", forbidden)
    result = post("begin", {"preset_id": "openrouter_user_models_v1", "code_challenge": "bad"})
    assert result.status_code == 400
    assert result.json()["error"] == "invalid_pkce_challenge"


def test_preset_change_during_exchange_cannot_deposit(monkeypatch):
    from dataclasses import replace

    from tinyassets.onboarding import model_bootstrap

    first = begin()
    preset = hosted.load_preset("openrouter_user_models_v1")
    async def exchange(**kwargs):
        monkeypatch.setattr(hosted, "load_preset", lambda _: replace(preset, digest="changed"))
        return "synthetic-key"
    def forbidden(**kwargs):
        raise AssertionError("must not deposit against changed preset")
    monkeypatch.setattr(hosted, "exchange_key", exchange)
    monkeypatch.setattr(model_bootstrap, "complete_bootstrap", forbidden)
    response = post("exchange", {"flow": first.json()["flow"], "code": "synthetic-code",
                                 "code_verifier": VERIFIER})
    assert response.status_code == 409
    assert response.json()["error"] == "model_connection_preset_changed"
