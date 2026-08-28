"""Approving source_code is the authority to run arbitrary Python in the daemon.

`graph_compiler` executes an approved node with `exec()` and full builtins; the pattern
denylist blocks a handful of substrings and leaves `open`, `os.environ`, sockets and
ordinary imports available. So whoever can approve can read every credential the process
holds -- the live Stripe key, the webhook secret, the session-store digest key, every
per-universe vault, every other user's refresh token -- and write any database under the
data dir, including the one that decides who has paid.

The owner gate on that route is PER-UNIVERSE, and every user owns their own universe. On
its own it therefore authorises every user to do all of that. This is the allowlist that
stops it, and it is dark by default.
"""

from __future__ import annotations

import pytest

from tinyassets.api.source_channel import (
    source_approval_allowed,
    source_approval_allowlist,
    source_approval_refusal,
)


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("TINYASSETS_SOURCE_APPROVAL_UNIVERSES", raising=False)


def test_it_is_dark_by_default():
    """A deployment that has not thought about this must not hand out execution."""
    assert source_approval_allowlist() == frozenset()
    assert source_approval_allowed("u-anything") is False


def test_only_a_listed_universe_is_allowed(monkeypatch):
    monkeypatch.setenv("TINYASSETS_SOURCE_APPROVAL_UNIVERSES", "u-founder")
    assert source_approval_allowed("u-founder") is True
    assert source_approval_allowed("u-someone-else") is False


def test_the_list_takes_several_and_tolerates_spacing(monkeypatch):
    monkeypatch.setenv(
        "TINYASSETS_SOURCE_APPROVAL_UNIVERSES", " u-a , u-b ,, u-c "
    )
    assert source_approval_allowlist() == {"u-a", "u-b", "u-c"}


@pytest.mark.parametrize("bad", ["", "   ", ",", " , "])
def test_a_blank_or_punctuation_only_value_allows_nobody(bad, monkeypatch):
    monkeypatch.setenv("TINYASSETS_SOURCE_APPROVAL_UNIVERSES", bad)
    assert source_approval_allowlist() == frozenset()
    assert source_approval_allowed("u-a") is False


def test_an_empty_universe_id_is_never_allowed(monkeypatch):
    """Never let a missing id fall through as 'matches nothing, so fine'."""
    monkeypatch.setenv("TINYASSETS_SOURCE_APPROVAL_UNIVERSES", "u-a")
    assert source_approval_allowed("") is False


def test_the_refusal_says_what_was_refused_and_who_can_change_it():
    body = source_approval_refusal("u-x")
    assert body["failure_class"] == "source_approval_not_allowlisted"
    assert body["actionable_by"] == "host"
    assert body["universe_id"] == "u-x"
    assert "arbitrary Python" in body["error"], "name the capability, not a code"
    assert "TINYASSETS_SOURCE_APPROVAL_UNIVERSES" in body["remediation"]


def test_the_gate_is_enforced_at_the_write_that_grants_execution():
    """Not at the route edge: the line that turns text into something the daemon runs.

    Asserted against the source because the check guards a branch, and a helper-level
    test would stay green while the approval path stopped calling it.
    """
    import pathlib

    from tinyassets.api import source_channel

    src = pathlib.Path(source_channel.__file__).read_text(encoding="utf-8")
    approve = src.split("def _approve(")[1]
    gate_at = approve.index("source_approval_allowed(uid)")
    write_at = approve.index("target_node.approved_source_hash = source_hash")
    assert gate_at < write_at, (
        "the allowlist must be consulted BEFORE the approval hash is written"
    )


def test_the_other_approval_path_still_requires_a_distinct_approver():
    """extensions.py is not self-approve, and this records that difference.

    If that four-eyes check ever goes, that path becomes a second self-approve route
    to the same capability and needs this allowlist too.
    """
    import pathlib

    from tinyassets.api import extensions

    src = pathlib.Path(extensions.__file__).read_text(encoding="utf-8")
    assert "node_approval_requires_distinct_actor" in src
