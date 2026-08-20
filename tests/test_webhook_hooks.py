"""Tests for the per-branch inbound webhook token store (Floor 1)."""

from __future__ import annotations

import pytest

from tinyassets.storage import webhook_hooks as hooks


def test_mint_then_resolve_returns_the_binding(tmp_path):
    token = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    assert isinstance(token, str) and len(token) >= 32
    got = hooks.resolve(tmp_path, token=token)
    assert got == {"universe_id": "u-a", "branch_def_id": "b-1"}


def test_tokens_are_unguessable_and_unique(tmp_path):
    t1 = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    t2 = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    assert t1 != t2


def test_unknown_revoked_and_empty_tokens_all_resolve_to_none(tmp_path):
    assert hooks.resolve(tmp_path, token="nope") is None
    assert hooks.resolve(tmp_path, token="") is None
    token = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    assert hooks.revoke(tmp_path, token=token) is True
    assert hooks.resolve(tmp_path, token=token) is None      # revoked -> None (indistinct)
    assert hooks.revoke(tmp_path, token=token) is False      # already revoked


def test_a_token_binds_exactly_one_universe_and_branch(tmp_path):
    ta = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-a")
    tb = hooks.mint(tmp_path, universe_id="u-b", branch_def_id="b-b")
    assert hooks.resolve(tmp_path, token=ta)["universe_id"] == "u-a"
    assert hooks.resolve(tmp_path, token=tb)["universe_id"] == "u-b"


def test_list_is_scoped_to_one_universe(tmp_path):
    hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-2")
    hooks.mint(tmp_path, universe_id="u-b", branch_def_id="b-3")
    a = hooks.list_for_universe(tmp_path, universe_id="u-a")
    assert {r["branch_def_id"] for r in a} == {"b-1", "b-2"}
    assert all("token" in r for r in a)


def test_mint_rejects_empty_or_overlong_ids(tmp_path):
    with pytest.raises(ValueError):
        hooks.mint(tmp_path, universe_id="", branch_def_id="b")
    with pytest.raises(ValueError):
        hooks.mint(tmp_path, universe_id="u", branch_def_id="x" * (hooks.MAX_ID_LEN + 1))
