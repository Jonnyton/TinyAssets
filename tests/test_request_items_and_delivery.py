"""Requests carry answerable items, and a background run can raise one.

The requests system is already the "the universe asks its owner and waits"
primitive. Two things it never had: a request that holds several answerable
items, and delivery to the owner's devices. These drive the real handlers
against real stores -- nothing between the ask and the row is patched.

The first test here is a PREMISE check, not a feature: the whole design rests
on a background run being able to raise a request as its owner
(``permissions.owner_run_identity``), and nothing tested that.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets.api import visibility as vis
from tinyassets.auth import middleware as mw
from tinyassets.daemon_server import (
    claim_founder_home,
    ensure_universe_registered,
    grant_universe_access,
)

OWNER = "workos|owner-requests"
OTHER = "workos|other-requests"
UID = "u-requests-home"
OTHER_UID = "u-requests-other"


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    return root


def _home(base: Path, uid: str, owner: str) -> Path:
    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    (udir / "soul.md").write_text(f"# {uid}\n", encoding="utf-8")
    ensure_universe_registered(base, universe_id=uid, universe_path=udir)
    grant_universe_access(
        base, universe_id=uid, actor_id=owner, permission="admin", granted_by=owner,
    )
    claim_founder_home(base, owner, uid)
    vis.set_universe_visibility(uid, "private", source="default")
    return udir


def _ask(universe_id: str, **payload):
    from tinyassets.api.pending_requests import request_from_user

    document = {
        "kind": "TODO",
        "title": "Today",
        "action": {"type": "answer"},
        # `_validated_fields` requires at least one field today. A request whose
        # answerable parts are all in `items` has none at the top level, so
        # items have to satisfy that requirement -- see test_items_alone_...
        "fields": [{"name": "note", "type": "text", "label": "Reply"}],
    }
    document.update(payload)
    return request_from_user(universe_id=universe_id, payload=document)


# --- premise: a background run raises a request as its owner ------------------


def test_a_background_run_raises_a_request_as_its_owner(base, nobody):
    """A run binds nobody on its own thread; owner_run_identity is what makes
    the ask the owner's. Without this, an automation cannot reach its person at
    all -- which is the whole point of delivery."""
    from tinyassets.api.permissions import owner_run_identity
    from tinyassets.storage.pending_requests import list_pending

    udir = _home(base, UID, OWNER)
    assert mw.current_identity_or_none() is None

    with owner_run_identity(base, UID, OWNER) as bound:
        assert bound is True
        raised = _ask(UID, body="two things need you")

    assert "error" not in raised, raised
    assert raised["status"] == "pending"
    pending = list_pending(udir)
    assert [row["request_id"] for row in pending] == [raised["request_id"]]
    # The binding is scoped to the run; nothing leaks onto the thread.
    assert mw.current_identity_or_none() is None


def test_a_run_bound_to_another_user_raises_nothing_here(base, nobody):
    """A collaborator's run naming the owner's universe gets the uniform
    absent-resource refusal, and no row lands anywhere."""
    from tinyassets.api.permissions import owner_run_identity
    from tinyassets.storage.pending_requests import list_pending

    udir = _home(base, UID, OWNER)
    other_dir = _home(base, OTHER_UID, OTHER)

    with owner_run_identity(base, OTHER_UID, OTHER) as bound:
        assert bound is True
        refused = _ask(UID, body="asking in someone else's universe")

    # `_owner_gate` returns `http_connection._NOT_FOUND` verbatim, on purpose:
    # one uniform absent-resource envelope across every owner-gated surface, so
    # this one cannot be used to probe what exists.
    assert refused.get("error") == "not_found"
    assert list_pending(udir) == []
    assert list_pending(other_dir) == []
