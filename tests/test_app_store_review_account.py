from __future__ import annotations

import importlib.util
import urllib.error
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "app_store_review_account.py"
_SPEC = importlib.util.spec_from_file_location("app_store_review_account", _SCRIPT)
assert _SPEC and _SPEC.loader
module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(module)


class FakeClient:
    def __init__(self, review):
        self.review = review
        self.calls = []

    def request(self, method, path, body=None, **kwargs):
        self.calls.append((method, path, body))
        if path.startswith("/apps/"):
            return {"data": [{"id": "version-id"}]}
        if path.endswith("/appStoreReviewDetail"):
            return {"data": self.review}
        attributes = body["data"]["attributes"]
        return {
            "data": {
                "id": "review-id",
                "attributes": {
                    "demoAccountName": attributes["demoAccountName"],
                    "demoAccountRequired": attributes["demoAccountRequired"],
                },
            }
        }


@pytest.fixture
def values():
    return {
        "APP_ID": "6808434444",
        "VERSION": "1.0",
        "REVIEW_USERNAME": "review@example.com",
        "REVIEW_PASSWORD": "not-logged",
    }


def test_existing_review_detail_is_patched_without_replacing_contact_fields(values):
    client = FakeClient({"id": "review-id"})

    result = module.save_review_account(client, values)

    assert result == ("version-id", "review-id")
    method, path, body = client.calls[-1]
    assert method == "PATCH"
    assert path == "/appStoreReviewDetails/review-id"
    assert body["data"]["attributes"] == {
        "demoAccountName": "review@example.com",
        "demoAccountPassword": "not-logged",
        "demoAccountRequired": True,
    }
    assert "contactEmail" not in body["data"]["attributes"]


def test_missing_review_detail_is_created_for_the_selected_version(values):
    client = FakeClient(None)

    module.save_review_account(client, values)

    method, path, body = client.calls[-1]
    assert method == "POST"
    assert path == "/appStoreReviewDetails"
    assert body["data"]["relationships"]["appStoreVersion"]["data"] == {
        "type": "appStoreVersions",
        "id": "version-id",
    }


def test_ambiguous_version_fails_closed(values):
    class AmbiguousClient(FakeClient):
        def request(self, method, path, body=None, **kwargs):
            return {"data": []}

    with pytest.raises(SystemExit, match="expected one iOS 1.0 version, found 0"):
        module.save_review_account(AmbiguousClient(None), values)


def test_review_detail_404_is_the_only_allowed_not_found(monkeypatch):
    def missing(*args, **kwargs):
        raise urllib.error.HTTPError("https://example.test", 404, "missing", {}, None)

    monkeypatch.setattr(module.urllib.request, "urlopen", missing)
    client = module.AppStoreConnect("token")

    assert client.request("GET", "/review", not_found_ok=True) is None
    with pytest.raises(SystemExit, match=r"HTTP 404 for GET /review"):
        client.request("GET", "/review")


def test_app_id_must_be_numeric():
    environ = {
        "API_KEY_ID": "key",
        "API_ISSUER_ID": "issuer",
        "API_KEY_B64": "encoded",
        "REVIEW_USERNAME": "review@example.com",
        "REVIEW_PASSWORD": "password",
        "APP_ID": "../apps",
        "VERSION": "1.0",
    }

    with pytest.raises(SystemExit, match="digits only"):
        module._required_environment(environ)
