"""A four-box ask must deposit all four values.

The credential ask became one field per value so the owner never has to work out
what goes where. The answer path had not caught up: it took the FIRST secret
field and silently discarded the rest —

    secret = next((values.get(n) for n in secret_names if values.get(n)), "")

— which was harmless while an ask was one unlabelled box and broken the moment
it stopped being. An OAuth 1.0a owner would fill four boxes, three would vanish,
and the deposit would refuse a malformed bundle with nothing to say which box
had been thrown away.

This is the seam between "ask for four things" and "deposit one credential", and
it is exactly the kind of place the last six gates lived: each side correct, the
join never exercised.
"""
from __future__ import annotations

import json

import pytest

from tests.test_pending_requests import (  # noqa: F401 - fixtures
    _answer,
    _ask,
    _login,
    _make_universe,
)


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Declared here rather than imported: a fixture whose name is also every
    test's parameter name reads to the linter as a redefinition at each use."""
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    return root

_OAUTH1A = [
    {"name": "api_key", "type": "secret", "label": "API Key",
     "help": "Developer portal -> your app -> Keys and tokens",
     "url": "https://developer.example.com/portal"},
    {"name": "api_secret", "type": "secret", "label": "API Key Secret"},
    {"name": "access_token", "type": "secret", "label": "Access Token"},
    {"name": "access_token_secret", "type": "secret", "label": "Access Token Secret"},
]

_VALUES = {
    "api_key": "ck-value",
    "api_secret": "cs-value",
    "access_token": "at-value",
    "access_token_secret": "ats-value",
}


def _four_box_ask(uid: str):
    return _ask(
        uid,
        fields=_OAUTH1A,
        action={
            "type": "connect_http",
            "destination": "some-service",
            "host": "api.example.com",
            "path_template": "/v2/post",
            "methods": ["POST"],
            "auth_scheme": "oauth1a",
        },
    )


def test_all_four_values_reach_the_deposit(base) -> None:
    """The headline: fill four boxes, all four are stored."""
    udir = _make_universe(base, "u-1", admin="founder")
    _login("founder")
    asked = _four_box_ask("u-1")

    out = _answer("u-1", request_id=asked["request_id"], values=dict(_VALUES))
    assert out.get("status") == "answered", out

    from tinyassets.credential_vault import load_credential_vault

    [record] = [
        r for r in load_credential_vault(udir)
        if str(r.get("credential_type") or "").lower() == "http"
    ]
    stored = json.loads(record["token"])
    assert stored == _VALUES, "a value the owner typed did not reach the vault"


def test_a_missing_box_is_refused_rather_than_deposited_short(base) -> None:
    """Partial is worse than refused.

    A bundle short one value deposits a credential that cannot sign, and the
    owner finds out later from a failing call with no idea which box was empty.
    """
    udir = _make_universe(base, "u-2", admin="founder")
    _login("founder")
    asked = _four_box_ask("u-2")

    short = dict(_VALUES)
    del short["access_token_secret"]
    out = _answer("u-2", request_id=asked["request_id"], values=short)

    assert "missing" in json.dumps(out).lower(), out
    assert "access_token_secret" in json.dumps(out)

    from tinyassets.credential_vault import load_credential_vault

    assert load_credential_vault(udir) == [], "nothing may be deposited"


def test_the_refusal_names_the_empty_box(base) -> None:
    """The owner has to know WHICH one, or they are guessing again."""
    _make_universe(base, "u-3", admin="founder")
    _login("founder")
    asked = _four_box_ask("u-3")

    out = _answer(
        "u-3",
        request_id=asked["request_id"],
        values={"api_key": "ck", "api_secret": "cs", "access_token": "at"},
    )
    assert "access_token_secret" in json.dumps(out)


def test_a_single_box_ask_is_unchanged(base) -> None:
    """The ordinary bearer case must not have grown a JSON wrapper."""
    udir = _make_universe(base, "u-4", admin="founder")
    _login("founder")
    asked = _ask("u-4")  # the shared fixture: one secret field

    out = _answer("u-4", request_id=asked["request_id"],
                  values={"secret": "ghp_" + "x" * 36})
    assert out.get("status") == "answered", out

    from tinyassets.credential_vault import load_credential_vault

    [record] = [
        r for r in load_credential_vault(udir)
        if str(r.get("credential_type") or "").lower() == "http"
    ]
    assert record["token"] == "ghp_" + "x" * 36, "a bare token must stay bare"


def test_no_secret_at_all_is_still_refused(base) -> None:
    _make_universe(base, "u-5", admin="founder")
    _login("founder")
    asked = _four_box_ask("u-5")

    out = _answer("u-5", request_id=asked["request_id"], values={})
    assert "required" in json.dumps(out).lower() or "missing" in json.dumps(out).lower()


def test_the_bundle_keys_are_the_field_names(base) -> None:
    """The agent chooses the field names, and for a scheme with a fixed bundle
    shape it must use that scheme's names — so the join is name-for-name and
    nothing here has to know which service it is."""
    udir = _make_universe(base, "u-6", admin="founder")
    _login("founder")
    asked = _four_box_ask("u-6")
    _answer("u-6", request_id=asked["request_id"], values=dict(_VALUES))

    from tinyassets.credential_vault import load_credential_vault

    [record] = [
        r for r in load_credential_vault(udir)
        if str(r.get("credential_type") or "").lower() == "http"
    ]
    assert sorted(json.loads(record["token"])) == sorted(f["name"] for f in _OAUTH1A)
