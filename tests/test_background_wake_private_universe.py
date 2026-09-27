"""A universe's own background wake reads its own brain on a PRIVATE universe.

Live 2026-09-27: after private-by-default (2026-09-26) flipped every universe,
the founder's background wake failed every time with "no authorized content to
assemble a persona prompt for tier T2". The shared-self turn passed the founder
tier, but the disclosure ceiling reads the REQUEST actor and a background wake
has none bound -- a public universe had hidden that.

These drive the real `prepare_shared_self_turn` against real storage and the
real visibility layer: nothing between the wake and the refusal is patched.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets.api import visibility as vis
from tinyassets.api.interlocutor import T1
from tinyassets.auth import middleware as mw
from tinyassets.daemon_server import (
    claim_founder_home,
    ensure_universe_registered,
    grant_universe_access,
)
from tinyassets.shared_self import prepare_shared_self_turn
from tinyassets.universe_intelligence import _build_persona_system_prompt

OWNER = "workos|owner-wake"
OTHER = "workos|other-user"
UID = "u-private-home"
SECRET = "the owner's private founder grounding"


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    # Production switches the shared-self engine tools on per deploy.
    monkeypatch.setenv("TINYASSETS_ENGINE_MCP_TOOLS", "1")
    return root


def _home(base: Path, uid: str, owner: str) -> Path:
    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    (udir / "soul.md").write_text(f"# {uid}\n", encoding="utf-8")
    (udir / "founder.md").write_text(SECRET, encoding="utf-8")
    ensure_universe_registered(base, universe_id=uid, universe_path=udir)
    grant_universe_access(
        base, universe_id=uid, actor_id=owner, permission="admin", granted_by=owner,
    )
    claim_founder_home(base, owner, uid)
    vis.set_universe_visibility(uid, "private", source="default")
    return udir


def _prepare(base: Path, principal: str):
    return prepare_shared_self_turn(base, UID, principal, "wake: do the next thing")


def test_the_owners_background_wake_assembles_its_persona_on_a_private_universe(
    base, nobody,
):
    _home(base, UID, OWNER)
    assert not vis.universe_visibility(UID).permits("read_content")
    assert mw.current_identity_or_none() is None  # a background wake binds nobody

    _prompt, system, _config = _prepare(base, OWNER)

    assert SECRET in system
    # The owner identity is scoped to the assembly; nothing leaks onto the thread.
    assert mw.current_identity_or_none() is None


def test_a_bound_visitor_does_not_change_whose_brain_the_wake_reads(base, signed_in):
    """The persona is read as the verified principal, not as the ambient caller."""
    _home(base, UID, OWNER)
    visitor = signed_in(OTHER)

    _prompt, system, _config = _prepare(base, OWNER)

    assert SECRET in system
    assert mw.current_identity_or_none() is visitor


def test_a_wake_for_a_different_user_on_a_private_universe_is_refused(base, nobody):
    _home(base, UID, OWNER)
    with pytest.raises(PermissionError, match="shared_self_requires_current_founder"):
        _prepare(base, OTHER)


def test_another_users_own_home_does_not_open_this_one(base, nobody):
    """OTHER owns a home too; naming this universe still refuses them."""
    _home(base, UID, OWNER)
    _home(base, "u-other-home", OTHER)
    with pytest.raises(PermissionError, match="shared_self_requires_current_founder"):
        _prepare(base, OTHER)


def test_a_visitor_turn_on_a_private_universe_is_still_withheld(base, signed_in):
    udir = _home(base, UID, OWNER)
    signed_in(OTHER)
    with pytest.raises(PermissionError, match="withholds content"):
        _build_persona_system_prompt(udir, universe_id=UID, tier=T1)
