"""Manual acquisition composes the real bootstrap without inference or OAuth."""
# ruff: noqa: F811 -- imported shared pytest fixture is requested by name

import asyncio
import json

import httpx
import pytest
from starlette.applications import Starlette

from tests.test_model_bootstrap import rig  # noqa: F401
from tests.test_onboarding_model_connect import ingress, post  # noqa: F401
from tinyassets import onboarding
from tinyassets.auth.middleware import identity_context
from tinyassets.auth.provider import Identity
from tinyassets.onboarding import hosted_model_auth as hosted

pytestmark = pytest.mark.usefixtures("rig", "ingress")
PRESET = "openrouter_user_models_v1"


def deposit(key="synthetic-private-key", **kwargs):
    return post("deposit_key", {"preset_id": PRESET, "key": key}, **kwargs)


def test_manual_owner_reaches_existing_approval_then_connects(rig, monkeypatch):
    from tinyassets.api.pending_requests import answer_request
    from tinyassets.credential_vault import load_credential_vault
    from tinyassets.onboarding.model_setup import model_setup_state
    from tinyassets.provider_assignment import load_provider_assignment

    async def forbidden(**kwargs):
        raise AssertionError("manual acquisition must not exchange OAuth")
    monkeypatch.setattr(hosted, "exchange_key", forbidden)
    response = deposit()
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    result = response.json()
    assert result["status"] == "confirmation_required"
    assert result["request"]["action"]["type"] == "bind_model_access"
    assert "synthetic-private-key" not in response.text
    assert load_provider_assignment(rig, universe_id="u-owner") is None
    assert load_credential_vault(rig / "u-owner")[0]["token"] == "synthetic-private-key"
    resumed = post("resume", {"preset_id": PRESET})
    assert resumed.json()["request_id"] == result["request_id"]
    answered = answer_request(universe_id="u-owner", payload={
        "request_id": result["request_id"], "values": {},
    })
    assert not answered.get("error"), answered
    assert model_setup_state(rig, universe=rig / "u-owner", uid="u-owner",
                             owner="owner") == "connected"


@pytest.mark.parametrize("data", [
    {}, {"preset_id": PRESET, "key": ""}, {"preset_id": PRESET, "key": 123},
    {"preset_id": PRESET, "key": "a" * 2049}, {"preset_id": PRESET, "key": "has space"},
    {"preset_id": PRESET, "key": "key\n"}, {"preset_id": PRESET, "key": "é"},
    {"preset_id": PRESET, "key": "key", "model": "paid-model"},
    {"preset_id": "future-installed-preset", "key": "key"},
    {"preset_id": PRESET, "key": "key", "owner": "another-owner"},
])
def test_manual_invalid_input_refused_before_preset_or_home(data, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid input cannot load or bootstrap")
    monkeypatch.setattr(hosted, "load_preset", forbidden)
    monkeypatch.setattr(onboarding, "_bootstrap_home", forbidden)
    response = post("deposit_key", data)
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_model_connection"}


@pytest.mark.parametrize("origin", ["", "http://tinyassets.io", "https://foreign.invalid"])
def test_manual_wrong_origin_has_no_vault(rig, origin):
    from tinyassets.credential_vault import load_credential_vault

    assert deposit(origin=origin).status_code == 403
    assert load_credential_vault(rig / "u-owner") == []


@pytest.mark.parametrize("principal", [None, "collaborator"])
def test_manual_requires_authenticated_home_owner(rig, principal):
    from tinyassets.credential_vault import load_credential_vault

    identity = (Identity(user_id=principal, username=principal, capabilities=["write"])
                if principal else None)
    with identity_context(identity):
        assert deposit().status_code == (409 if principal else 401)
    assert load_credential_vault(rig / "u-owner") == []


def test_manual_does_not_replace_existing_setup(rig):
    from tinyassets.credential_vault import load_credential_vault

    assert deposit("first-key").status_code == 200
    response = deposit("replacement-key")
    assert response.status_code == 409
    assert response.json()["error"] == "model_setup_changed"
    assert load_credential_vault(rig / "u-owner")[0]["token"] == "first-key"


def test_manual_unexpected_error_never_echoes_or_logs_secret(monkeypatch, caplog):
    from tinyassets.onboarding import model_bootstrap

    def broken(**kwargs):
        raise RuntimeError(kwargs["key"])
    monkeypatch.setattr(model_bootstrap, "complete_bootstrap", broken)
    response = deposit()
    assert response.status_code == 503
    assert response.json() == {"error": "model_connection_incomplete"}
    assert "synthetic-private-key" not in response.text + caplog.text


@pytest.mark.parametrize("content,content_type,expected", [
    ("{bad json", "application/json", 400),
    (json.dumps({"preset_id": PRESET, "key": "x" * 9000}), "application/json", 400),
    ("secret-text", "text/plain", 403),
])
def test_manual_bounded_json(content, content_type, expected):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(
            app=Starlette(routes=onboarding.onboarding_routes())), base_url="https://tinyassets.io",
        ) as client:
            return await client.post("/mcp/app/model-connect/deposit_key", content=content,
                                     headers={"Origin": "https://tinyassets.io",
                                              "Content-Type": content_type})
    assert asyncio.run(run()).status_code == expected


def test_manual_full_2048_printable_key_is_accepted():
    assert deposit("x" * 2048).status_code == 200


def test_manual_deleted_account_cannot_deposit(rig):
    from tinyassets.account_deletion import write_tombstone
    from tinyassets.credential_vault import load_credential_vault

    write_tombstone(rig, "owner")
    response = deposit()
    assert response.status_code == 409
    assert load_credential_vault(rig / "u-owner") == []


@pytest.mark.parametrize("free", [True, False])
def test_manual_catalogue_never_selects_paid_model(monkeypatch, free):
    from tests.test_model_bootstrap_candidate import row
    from tinyassets.providers import discovery_http
    from tinyassets.providers.definition import get_definition, list_definitions

    models = [row("paid-first", "1")]
    if free:
        models.append(row("eligible-free", "0"))
    monkeypatch.setattr(discovery_http, "read_granted_discovery_document",
                        lambda **kwargs: {"data": models})
    response = deposit()
    if not free:
        assert response.status_code == 409
        assert response.json()["error"] == "no_eligible_free_agent_model"
        assert not list_definitions("u-owner")
    else:
        assert response.status_code == 200, response.text
        did = response.json()["request"]["action"]["provider"]
        assert get_definition("u-owner", did).model == "eligible-free"
