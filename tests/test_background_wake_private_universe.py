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


# --- the WHOLE owner run, not just its persona -------------------------------
#
# Founder 2026-09-27: an agent the owner's universe sets up is "pretty much the
# same as itself". Every in-run read of its own private universe must see what
# the owner's live conversation sees, and nobody else's run gains anything.


def _in_run_reads(uid: str, udir: Path) -> dict:
    """What a node reads mid-run, through the real readers and resolvers."""
    from tinyassets.api import interlocutor, permissions

    who = interlocutor.resolve_interlocutor_tier(uid)
    out = {
        "actor": permissions.current_request_actor_id(),
        "tier": who.tier,
        "read_content": vis.visibility_permits(uid, "read_content"),
        "persona": "",
    }
    try:
        out["persona"] = _build_persona_system_prompt(udir, universe_id=uid, tier=who.tier)
    except PermissionError as exc:
        out["persona"] = f"REFUSED: {exc}"
    return out


def _claimed_task(uid: str, actor: str):
    from tinyassets.branch_tasks_v2 import Epoch2BranchTask

    return Epoch2BranchTask(
        branch_task_id="bt2_" + "a" * 32,
        branch_def_id="branch-a",
        universe_id=uid,
        admission_id="adm_" + "c" * 32,
        request_id="req_" + "d" * 32,
        actor_id=actor,
        automation_id="automation-a",
        automation_branch_version="branch-version-a",
        automation_subject_ref="branch-version-a",
        automation_subject_digest="sha256:" + "b" * 64,
        inputs={},
    )


def _run_claimed(base: Path, uid: str, actor: str, udir: Path, monkeypatch) -> dict:
    from types import SimpleNamespace

    from tinyassets.runtime.claimed_branch_execution import (
        ClaimedBranchExecutorIdentity,
        execute_claimed_branch_task,
    )

    seen: dict = {}

    def execute(_base, *, branch_version_id, **_kwargs):
        seen.update(_in_run_reads(uid, udir))
        return SimpleNamespace(run_id="run-a", status="completed", output={}, error="")

    monkeypatch.setattr("tinyassets.runs.get_run_by_branch_task_id", lambda *_a, **_k: None)
    monkeypatch.setattr("tinyassets.runs.execute_branch_version", execute)
    ok, error, _detail = execute_claimed_branch_task(
        base, _claimed_task(uid, actor), ClaimedBranchExecutorIdentity(daemon_id="d"), object(),
    )
    assert ok, error
    return seen


def test_the_owners_background_run_reads_its_own_private_universe_mid_run(
    base, nobody, monkeypatch,
):
    udir = _home(base, UID, OWNER)

    seen = _run_claimed(base, UID, OWNER, udir, monkeypatch)

    assert seen["actor"] == OWNER
    assert seen["tier"] == "T2"
    assert seen["read_content"] is True
    assert SECRET in seen["persona"]
    assert mw.current_identity_or_none() is None


def test_a_background_run_whose_actor_does_not_own_the_universe_reads_nothing(
    base, nobody, monkeypatch,
):
    udir = _home(base, UID, OWNER)
    _home(base, "u-other-home", OTHER)

    seen = _run_claimed(base, UID, OTHER, udir, monkeypatch)

    assert seen["actor"] == ""
    assert seen["read_content"] is False
    assert seen["persona"].startswith("REFUSED")
    assert SECRET not in seen["persona"]


def _fire_trigger(base: Path, uid: str, principal: str, udir: Path, monkeypatch) -> dict:
    from types import SimpleNamespace

    from tinyassets.api import runs as api_runs

    seen: dict = {}

    def execute_async(_base, **_kwargs):
        # The real one submits `copy_context().run`, so this is the context the
        # run's worker executes in.
        seen.update(_in_run_reads(uid, udir))
        return SimpleNamespace(run_id="run-t")

    monkeypatch.setattr("tinyassets.runs.execute_branch_async", execute_async)
    monkeypatch.setattr("tinyassets.api.branches._resolve_branch_id", lambda bid, _b: bid)
    monkeypatch.setattr(
        "tinyassets.daemon_server.get_branch_definition", lambda *_a, **_k: {},
    )
    monkeypatch.setattr(
        "tinyassets.branches.BranchDefinition.from_dict",
        staticmethod(lambda _d: SimpleNamespace(validate=lambda: [])),
    )
    monkeypatch.setattr(api_runs, "_bind_run_provider_call", lambda *_a, **_k: None)
    api_runs.enqueue_universe_branch_run(
        base, universe_id=uid, branch_def_id="branch-a", inputs={}, principal_id=principal,
    )
    return seen


def test_the_owners_scheduled_run_reads_its_own_private_universe(base, nobody, monkeypatch):
    udir = _home(base, UID, OWNER)

    seen = _fire_trigger(base, UID, OWNER, udir, monkeypatch)

    assert seen["actor"] == OWNER
    assert SECRET in seen["persona"]


def test_a_trigger_naming_a_non_owner_principal_reads_nothing(base, nobody, monkeypatch):
    udir = _home(base, UID, OWNER)

    seen = _fire_trigger(base, UID, OTHER, udir, monkeypatch)

    assert seen["actor"] == ""
    assert seen["read_content"] is False
    assert SECRET not in seen["persona"]


# --- the binding itself -------------------------------------------------------


def test_a_write_collaborator_is_not_bound_as_the_owner(base, nobody):
    from tinyassets.api.permissions import owner_run_identity

    _home(base, UID, OWNER)
    grant_universe_access(
        base, universe_id=UID, actor_id=OTHER, permission="write", granted_by=OWNER,
    )
    with owner_run_identity(base, UID, OTHER) as bound:
        assert bound is False
        assert mw.current_identity_or_none() is None


def test_an_owner_already_bound_is_not_narrowed(base, signed_in):
    from tinyassets.api.permissions import owner_run_identity

    _home(base, UID, OWNER)
    live = signed_in(OWNER)
    with owner_run_identity(base, UID, OWNER) as bound:
        assert bound is True
        assert mw.current_identity_or_none() is live
