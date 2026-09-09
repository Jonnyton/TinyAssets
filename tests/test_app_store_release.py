from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parents[1] / "scripts" / "app_store_release.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("app_store_release", _SCRIPT)
assert _SPEC and _SPEC.loader
module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(module)


class FakeClient:
    def __init__(
        self, *, app_store_state="WAITING_FOR_REVIEW", release_type="MANUAL"
    ):
        self.app_store_state = app_store_state
        self.release_type = release_type
        self.calls = []

    def request(self, method, path, body=None, **kwargs):
        self.calls.append((method, path, body))
        if path.startswith("/apps/"):
            return {
                "data": [
                    {
                        "id": "version-id",
                        "attributes": {
                            "appStoreState": self.app_store_state,
                            "downloadable": self.app_store_state == "READY_FOR_SALE",
                            "releaseType": self.release_type,
                        },
                    }
                ]
            }
        if path.startswith("/reviewSubmissions/"):
            return {"data": {"attributes": {"state": "WAITING_FOR_REVIEW"}}}
        if path == "/appStoreVersionReleaseRequests":
            return {"data": {"id": "release-request-id"}}
        if path == "/appStoreVersions/version-id":
            self.release_type = body["data"]["attributes"]["releaseType"]
            return {
                "data": {"attributes": {"releaseType": self.release_type}}
            }
        raise AssertionError(path)


@pytest.fixture
def values():
    return {
        "APP_ID": "6808434444",
        "VERSION": "1.0",
        "SUBMISSION_ID": "submission-id",
    }


def test_release_status_reads_exact_version_and_submission(values):
    client = FakeClient()

    assert module.release_status(client, values) == (
        "version-id",
        "WAITING_FOR_REVIEW",
        False,
        "WAITING_FOR_REVIEW",
        "MANUAL",
    )
    assert client.calls[0][0] == "GET"
    assert "filter%5Bplatform%5D=IOS" in client.calls[0][1]
    assert "filter%5BversionString%5D=1.0" in client.calls[0][1]
    assert client.calls[1][:2] == (
        "GET",
        "/reviewSubmissions/submission-id",
    )


def test_request_release_uses_apple_release_request_shape():
    client = FakeClient(app_store_state="PENDING_DEVELOPER_RELEASE")

    assert module.request_release(client, "version-id") == "release-request-id"
    assert client.calls[-1] == (
        "POST",
        "/appStoreVersionReleaseRequests",
        {
            "data": {
                "type": "appStoreVersionReleaseRequests",
                "relationships": {
                    "appStoreVersion": {
                        "data": {"type": "appStoreVersions", "id": "version-id"}
                    }
                },
            }
        },
    )


def test_set_automatic_release_after_approval_uses_apple_update_shape():
    client = FakeClient()

    module.set_automatic_release_after_approval(client, "version-id")

    assert client.calls[-1] == (
        "PATCH",
        "/appStoreVersions/version-id",
        {
            "data": {
                "type": "appStoreVersions",
                "id": "version-id",
                "attributes": {"releaseType": "AFTER_APPROVAL"},
            }
        },
    )


@pytest.mark.parametrize(
    "raw, expected",
    [("true", True), ("YES", True), ("1", True), ("false", False), ("no", False), ("0", False)],
)
def test_boolean_accepts_explicit_values(raw, expected):
    assert module._boolean(raw, name="RELEASE_IF_APPROVED") is expected


def test_boolean_rejects_ambiguous_value():
    with pytest.raises(SystemExit, match="RELEASE_IF_APPROVED must be"):
        module._boolean("maybe", name="RELEASE_IF_APPROVED")


@pytest.mark.parametrize(
    "state, release_enabled, expected_release_calls",
    [
        ("WAITING_FOR_REVIEW", True, 0),
        ("IN_REVIEW", True, 0),
        ("PENDING_DEVELOPER_RELEASE", False, 0),
        ("PENDING_DEVELOPER_RELEASE", True, 1),
        ("READY_FOR_SALE", True, 0),
    ],
)
def test_main_releases_only_the_exact_approved_state(
    monkeypatch, values, state, release_enabled, expected_release_calls, capsys
):
    client = FakeClient(app_store_state=state)
    environment = {
        "API_KEY_ID": "key",
        "API_ISSUER_ID": "issuer",
        "API_KEY_B64": "encoded",
        **values,
        "RELEASE_IF_APPROVED": str(release_enabled).lower(),
        "AUTOMATIC_RELEASE_AFTER_APPROVAL": "false",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(module, "_token", lambda supplied: "token")
    monkeypatch.setattr(module, "AppStoreConnect", lambda token: client)
    monkeypatch.setattr(module, "us_storefront_listing", lambda app_id: (False, ""))

    module.main()

    release_calls = [
        call for call in client.calls if call[1] == "/appStoreVersionReleaseRequests"
    ]
    assert len(release_calls) == expected_release_calls
    assert f"app_store_state={state}" in capsys.readouterr().out


@pytest.mark.parametrize(
    "state, release_type, expected_patch_calls",
    [
        ("WAITING_FOR_REVIEW", "MANUAL", 1),
        ("IN_REVIEW", "MANUAL", 1),
        ("WAITING_FOR_REVIEW", "AFTER_APPROVAL", 0),
        ("PENDING_DEVELOPER_RELEASE", "MANUAL", 0),
        ("READY_FOR_SALE", "MANUAL", 0),
    ],
)
def test_main_sets_automatic_release_only_before_approval(
    monkeypatch, values, state, release_type, expected_patch_calls, capsys
):
    client = FakeClient(app_store_state=state, release_type=release_type)
    environment = {
        "API_KEY_ID": "key",
        "API_ISSUER_ID": "issuer",
        "API_KEY_B64": "encoded",
        **values,
        "RELEASE_IF_APPROVED": "true",
        "AUTOMATIC_RELEASE_AFTER_APPROVAL": "true",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(module, "_token", lambda supplied: "token")
    monkeypatch.setattr(module, "AppStoreConnect", lambda token: client)
    monkeypatch.setattr(module, "us_storefront_listing", lambda app_id: (False, ""))

    module.main()

    patch_calls = [call for call in client.calls if call[0] == "PATCH"]
    assert len(patch_calls) == expected_patch_calls
    output = capsys.readouterr().out
    expected_update = expected_patch_calls == 1
    assert f"automatic_release_updated={str(expected_update).lower()}" in output


def test_main_does_not_set_automatic_release_when_flag_is_false(
    monkeypatch, values
):
    client = FakeClient(app_store_state="WAITING_FOR_REVIEW", release_type="MANUAL")
    environment = {
        "API_KEY_ID": "key",
        "API_ISSUER_ID": "issuer",
        "API_KEY_B64": "encoded",
        **values,
        "RELEASE_IF_APPROVED": "true",
        "AUTOMATIC_RELEASE_AFTER_APPROVAL": "false",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(module, "_token", lambda supplied: "token")
    monkeypatch.setattr(module, "AppStoreConnect", lambda token: client)
    monkeypatch.setattr(module, "us_storefront_listing", lambda app_id: (False, ""))

    module.main()

    assert [call for call in client.calls if call[0] == "PATCH"] == []


def test_app_id_must_be_numeric():
    environ = {
        "API_KEY_ID": "key",
        "API_ISSUER_ID": "issuer",
        "API_KEY_B64": "encoded",
        "APP_ID": "../apps",
        "VERSION": "1.0",
        "SUBMISSION_ID": "submission-id",
    }

    with pytest.raises(SystemExit, match="digits only"):
        module._required_environment(environ)
