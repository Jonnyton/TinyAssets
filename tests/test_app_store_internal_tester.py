from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "app_store_internal_tester.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("app_store_internal_tester", _SCRIPT)
assert _SPEC and _SPEC.loader
module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(module)


class FakeClient:
    def __init__(self, *, in_group=False, existing_global=False):
        self.in_group = in_group
        self.existing_global = existing_global
        self.calls = []

    @staticmethod
    def _tester():
        return {
            "type": "betaTesters",
            "id": "tester-id",
            "attributes": {
                "email": "holder@example.com",
                "inviteType": "EMAIL",
                "state": "ACCEPTED",
            },
        }

    def request(self, method, path, body=None, **kwargs):
        self.calls.append((method, path, body))
        if path.startswith("/users?"):
            return {
                "data": [
                    {
                        "type": "users",
                        "id": "holder-id",
                        "attributes": {
                            "username": "holder@example.com",
                            "firstName": "Tiny",
                            "lastName": "Assets",
                            "roles": ["ACCOUNT_HOLDER"],
                        },
                    }
                ]
            }
        if path.startswith("/apps/"):
            return {
                "data": [
                    {
                        "type": "betaGroups",
                        "id": "group-id",
                        "attributes": {"name": "Internal", "isInternalGroup": True},
                    }
                ]
            }
        if path.startswith("/betaGroups/"):
            return {"data": [self._tester()] if self.in_group else []}
        if method == "GET" and path.startswith("/betaTesters?"):
            return {"data": [self._tester()] if self.existing_global else []}
        if method == "POST" and path == "/betaTesters":
            self.in_group = True
            self.existing_global = True
            return {"data": self._tester()}
        if method == "POST" and "/relationships/betaGroups" in path:
            self.in_group = True
            return {}
        raise AssertionError((method, path, body))


def test_inventory_finds_one_account_holder_and_exact_internal_group():
    client = FakeClient()

    holder = module.account_holder(client)
    group = module.internal_group(client, "6808434444", group_name="Internal")

    assert holder["id"] == "holder-id"
    assert group["id"] == "group-id"
    assert all("holder@example.com" not in path for _, path, _ in client.calls)


def test_add_creates_missing_tester_with_group_relationship():
    client = FakeClient()
    holder = module.account_holder(client)
    group = module.internal_group(client, "6808434444", group_name="Internal")

    tester_id, changed = module.add_account_holder(
        client, holder=holder, group=group
    )

    assert (tester_id, changed) == ("tester-id", True)
    create = next(call for call in client.calls if call[0:2] == ("POST", "/betaTesters"))
    assert create[2]["data"]["relationships"]["betaGroups"]["data"] == [
        {"type": "betaGroups", "id": "group-id"}
    ]


def test_add_links_existing_global_tester_without_recreating():
    client = FakeClient(existing_global=True)
    holder = module.account_holder(client)
    group = module.internal_group(client, "6808434444", group_name="Internal")

    assert module.add_account_holder(client, holder=holder, group=group) == (
        "tester-id",
        True,
    )
    assert not any(call[0:2] == ("POST", "/betaTesters") for call in client.calls)
    assert any("/relationships/betaGroups" in call[1] for call in client.calls)
    assert all("holder@example.com" not in call[1] for call in client.calls)


def test_add_is_idempotent_when_account_holder_is_already_in_group():
    client = FakeClient(in_group=True, existing_global=True)
    holder = module.account_holder(client)
    group = module.internal_group(client, "6808434444", group_name="Internal")

    assert module.add_account_holder(client, holder=holder, group=group) == (
        "tester-id",
        False,
    )
    assert all(call[0] == "GET" for call in client.calls)


@pytest.mark.parametrize(
    "resources,description",
    [([], "account holder"), ([{"id": "one"}, {"id": "two"}], "group")],
)
def test_ambiguous_resources_fail_closed(resources, description):
    with pytest.raises(SystemExit, match=f"expected one {description}"):
        module._one_resource(resources, description=description)


def test_environment_rejects_non_numeric_app_id():
    with pytest.raises(SystemExit, match="digits only"):
        module._required_environment(
            {
                "API_KEY_ID": "key",
                "API_ISSUER_ID": "issuer",
                "API_KEY_B64": "encoded",
                "APP_ID": "../apps",
            }
        )


def test_main_defaults_to_read_only_and_never_prints_identity(monkeypatch, capsys):
    client = FakeClient()
    environment = {
        "API_KEY_ID": "key",
        "API_ISSUER_ID": "issuer",
        "API_KEY_B64": "encoded",
        "APP_ID": "6808434444",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("APPLY", raising=False)
    monkeypatch.setattr(module, "_token", lambda values: "token")
    monkeypatch.setattr(module, "AppStoreConnect", lambda token: client)

    module.main()

    output = capsys.readouterr().out
    assert "apply=false" in output
    assert "changed=false" in output
    assert "holder@example.com" not in output
    assert "Tiny" not in output
    assert all(call[0] == "GET" for call in client.calls)


def test_main_apply_adds_and_verifies_account_holder(monkeypatch, capsys):
    client = FakeClient()
    environment = {
        "API_KEY_ID": "key",
        "API_ISSUER_ID": "issuer",
        "API_KEY_B64": "encoded",
        "APP_ID": "6808434444",
        "APPLY": "true",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(module, "_token", lambda values: "token")
    monkeypatch.setattr(module, "AppStoreConnect", lambda token: client)

    module.main()

    output = capsys.readouterr().out
    assert "apply=true" in output
    assert "changed=true" in output
    assert "tester_id=tester-id" in output
    assert "holder@example.com" not in output
