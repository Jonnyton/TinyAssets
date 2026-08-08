"""Are you sure — consent, distinct from authority."""

from __future__ import annotations

import pytest

from tinyassets.storage.action_approvals import (
    ActionApprovalStore,
    ApprovalError,
)


@pytest.fixture
def store(tmp_path):
    from tinyassets.daemon_server import initialize_author_server

    initialize_author_server(str(tmp_path))
    return ActionApprovalStore(tmp_path)


def test_nothing_is_approved_by_default(store):
    assert not store.consume_if_granted(universe_id="u-a", action_key="branch.run")


def test_a_granted_approval_lets_it_through(store):
    store.decide(universe_id="u-a", action_key="branch.run", granted=True,
                 decided_by="user_1")
    assert store.consume_if_granted(universe_id="u-a", action_key="branch.run")


def test_one_yes_covers_one_run(store):
    """A single-use yes that keeps working is a standing grant never given."""
    store.decide(universe_id="u-a", action_key="branch.run", granted=True,
                 decided_by="user_1")
    assert store.consume_if_granted(universe_id="u-a", action_key="branch.run")
    assert not store.consume_if_granted(universe_id="u-a", action_key="branch.run")


def test_standing_consent_persists(store):
    store.decide(universe_id="u-a", action_key="branch.run", granted=True,
                 decided_by="user_1", standing=True)
    for _ in range(3):
        assert store.consume_if_granted(universe_id="u-a", action_key="branch.run")


def test_a_denial_blocks(store):
    store.decide(universe_id="u-a", action_key="branch.run", granted=False,
                 decided_by="user_1")
    assert not store.consume_if_granted(universe_id="u-a", action_key="branch.run")


def test_approval_does_not_cross_universes(store):
    store.decide(universe_id="u-a", action_key="branch.run", granted=True,
                 decided_by="user_1")
    assert not store.consume_if_granted(universe_id="u-b", action_key="branch.run")


def test_approval_does_not_cross_actions(store):
    """Yes to the niche watcher is not yes to the thing that opens PRs."""
    store.decide(universe_id="u-a", action_key="branch.run:safe123", granted=True,
                 decided_by="user_1")
    assert not store.consume_if_granted(
        universe_id="u-a", action_key="branch.run:repo999"
    )


def test_a_request_does_not_grant_anything(store):
    store.request(universe_id="u-a", action_key="branch.run", detail="probe")
    assert not store.consume_if_granted(universe_id="u-a", action_key="branch.run")
    assert [a.action_key for a in store.pending_for(universe_id="u-a")] == ["branch.run"]


def test_requesting_cannot_downgrade_an_existing_grant(store):
    """Otherwise a re-request silently revokes the founder's yes."""
    store.decide(universe_id="u-a", action_key="branch.run", granted=True,
                 decided_by="user_1", standing=True)
    store.request(universe_id="u-a", action_key="branch.run")
    assert store.consume_if_granted(universe_id="u-a", action_key="branch.run")


def test_stale_pending_asks_drop_off(store):
    store.request(universe_id="u-a", action_key="branch.run", now=1_000_000)
    assert store.pending_for(universe_id="u-a", now=1_000_100)
    assert not store.pending_for(universe_id="u-a", now=1_000_000 + 90_000)


@pytest.mark.parametrize("bad", ["", "  ", "UPPER SPACE", "x", "!!"])
def test_malformed_keys_are_refused(store, bad):
    with pytest.raises(ApprovalError):
        store.decide(universe_id="u-a", action_key=bad, granted=True,
                     decided_by="user_1")
