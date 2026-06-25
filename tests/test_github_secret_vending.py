"""Centralized GitHub destination-scoped secret vending (auth provider).

Covers ``workflow.auth.provider.vend_github_destination_secret`` and the
``github_pr`` effector's adapted ``_read_capability`` resolution order
(per-universe vault first, then the env-vended ``push`` token with the
legacy ``WORKFLOW_GITHUB_PR_CAPABILITIES`` fallback).
"""

from __future__ import annotations

import json

import pytest

from workflow.auth.provider import (
    _load_destination_secret_map,
    vend_github_destination_secret,
)
from workflow.credential_vault import write_credential_vault
from workflow.effectors.github_pr import _read_capability

_DESTINATION = "Jonnyton/Workflow"

_GITHUB_SECRET_ENVS = (
    "WORKFLOW_GITHUB_PUSH_CAPABILITIES",
    "WORKFLOW_GITHUB_PR_CAPABILITIES",
    "WORKFLOW_GITHUB_READ_CAPABILITIES",
)


@pytest.fixture(autouse=True)
def _clean_github_secret_envs(monkeypatch):
    """Strip host-shell GitHub capability env state for isolated tests."""
    for name in _GITHUB_SECRET_ENVS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def universe_dir(tmp_path):
    universe = tmp_path / "u-test"
    universe.mkdir()
    return universe


# ---------------------------------------------------------------------------
# _load_destination_secret_map
# ---------------------------------------------------------------------------


def test_load_secret_map_parses_json_object(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PUSH_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-push", "octo/other": "tok-other"}),
    )
    parsed = _load_destination_secret_map("WORKFLOW_GITHUB_PUSH_CAPABILITIES")
    assert parsed == {_DESTINATION: "tok-push", "octo/other": "tok-other"}


def test_load_secret_map_unset_returns_empty():
    assert _load_destination_secret_map("WORKFLOW_GITHUB_PUSH_CAPABILITIES") == {}


def test_load_secret_map_malformed_json_returns_empty(monkeypatch):
    monkeypatch.setenv("WORKFLOW_GITHUB_PUSH_CAPABILITIES", "{not valid json}")
    assert _load_destination_secret_map("WORKFLOW_GITHUB_PUSH_CAPABILITIES") == {}


def test_load_secret_map_non_object_returns_empty(monkeypatch):
    for value in ("[]", '"a string"', "42", "null"):
        monkeypatch.setenv("WORKFLOW_GITHUB_PUSH_CAPABILITIES", value)
        assert _load_destination_secret_map("WORKFLOW_GITHUB_PUSH_CAPABILITIES") == {}


def test_load_secret_map_strips_and_drops_empty_entries(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PUSH_CAPABILITIES",
        json.dumps(
            {
                "  octo/real  ": "  tok-real  ",
                "octo/blank": "   ",
                "  ": "tok-no-key",
            }
        ),
    )
    parsed = _load_destination_secret_map("WORKFLOW_GITHUB_PUSH_CAPABILITIES")
    assert parsed == {"octo/real": "tok-real"}


# ---------------------------------------------------------------------------
# vend_github_destination_secret
# ---------------------------------------------------------------------------


def test_vend_push_uses_canonical_env(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PUSH_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-push"}),
    )
    vended = vend_github_destination_secret(destination=_DESTINATION, capability="push")
    assert vended["token"] == "tok-push"
    assert vended["capability"] == "push"
    assert vended["destination"] == _DESTINATION
    assert vended["source_env_var"] == "WORKFLOW_GITHUB_PUSH_CAPABILITIES"


def test_vend_push_falls_back_to_legacy_env(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PR_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-legacy"}),
    )
    vended = vend_github_destination_secret(destination=_DESTINATION, capability="push")
    assert vended["token"] == "tok-legacy"
    assert vended["source_env_var"] == "WORKFLOW_GITHUB_PR_CAPABILITIES"


def test_vend_push_canonical_env_wins_over_legacy(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PUSH_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-push"}),
    )
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PR_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-legacy"}),
    )
    vended = vend_github_destination_secret(destination=_DESTINATION, capability="push")
    assert vended["token"] == "tok-push"
    assert vended["source_env_var"] == "WORKFLOW_GITHUB_PUSH_CAPABILITIES"


def test_vend_read_uses_read_env_only(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_READ_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-read"}),
    )
    # A push token configured elsewhere must NOT leak into a read vend.
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PUSH_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-push"}),
    )
    vended = vend_github_destination_secret(destination=_DESTINATION, capability="read")
    assert vended["token"] == "tok-read"
    assert vended["source_env_var"] == "WORKFLOW_GITHUB_READ_CAPABILITIES"


def test_vend_missing_destination_returns_empty_token(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PUSH_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-push"}),
    )
    vended = vend_github_destination_secret(destination="never/set", capability="push")
    assert vended["token"] == ""


def test_vend_empty_destination_returns_empty_token():
    vended = vend_github_destination_secret(destination="", capability="push")
    assert vended["token"] == ""


def test_vend_unknown_capability_returns_empty_token(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PUSH_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-push"}),
    )
    vended = vend_github_destination_secret(destination=_DESTINATION, capability="bogus")
    assert vended["token"] == ""
    assert vended["source_env_var"] == ""


# ---------------------------------------------------------------------------
# github_pr._read_capability — adapted resolution order
# ---------------------------------------------------------------------------


def test_read_capability_uses_push_env_when_no_universe(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PUSH_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-push"}),
    )
    assert _read_capability(_DESTINATION) == "tok-push"


def test_read_capability_legacy_env_still_works(monkeypatch):
    """Backward compat: a host that has not migrated keeps real writes."""
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PR_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-legacy"}),
    )
    assert _read_capability(_DESTINATION) == "tok-legacy"


def test_read_capability_vault_beats_env(universe_dir, monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PUSH_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-push"}),
    )
    write_credential_vault(
        universe_dir,
        [
            {
                "credential_type": "vcs",
                "service": "github",
                "destination": _DESTINATION,
                "purpose": "write",
                "token": "vault-token",
            }
        ],
    )
    assert _read_capability(_DESTINATION, universe_dir) == "vault-token"


def test_read_capability_empty_vault_blocks_env(universe_dir, monkeypatch):
    """A bound-but-empty vault means 'not authorized', not 'fall to env'."""
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PUSH_CAPABILITIES",
        json.dumps({_DESTINATION: "tok-push"}),
    )
    write_credential_vault(universe_dir, [])
    assert _read_capability(_DESTINATION, universe_dir) == ""


def test_read_capability_empty_destination_returns_empty():
    assert _read_capability("") == ""
