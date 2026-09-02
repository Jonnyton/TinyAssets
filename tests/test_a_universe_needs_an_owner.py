"""A universe is a directory somebody owns, and a prune cuts.

Founder, 2026-09-02: *"a universe should only exist if it belongs to a user"*
and *"leaving old folders is not a prune, a prune cuts bad branches off. this
made the branches unconnected but still sitting in the tree."*

Production had 12 "universes": the founder's one, three old test universes,
and five directories that were never universes at all -- a migration backup,
three archives left by past prunes, and `scratch`. The definition was "any
directory under the data root that is not one of four hardcoded names", so
every operational directory became a universe, and a prune that renamed a
universe aside created one.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.daemon_server import (
    ensure_universe_registered,
    grant_universe_access,
    owned_universe_ids,
    universe_owners,
)


def _universe(base, name: str) -> None:
    (base / name).mkdir(parents=True, exist_ok=True)


def _own(base, name: str, actor: str = "workos|founder") -> None:
    _universe(base, name)
    ensure_universe_registered(
        base, universe_id=name, universe_path=base / name, display_name=name,
    )
    grant_universe_access(
        base, universe_id=name, actor_id=actor, permission="admin",
        granted_by="test",
    )


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    return tmp_path


# --------------------------------------------------------------------------
# the definition
# --------------------------------------------------------------------------


def test_an_unowned_directory_is_not_a_universe(data_root):
    _own(data_root, "u-mine")
    for leftover in (
        "_removed_universes_20260828",
        "_removed_legacy_20260829",
        "_backup_subject_migration_20260829T055340Z",
        "scratch",
        "cloud-automation-inputs",
        "daemon_wikis",
        "paper-notes",
    ):
        _universe(data_root, leftover)

    owned = owned_universe_ids(data_root)
    assert owned == {"u-mine"}

    from tinyassets.api.universe import _action_list_universes

    listed = json.loads(_action_list_universes())
    assert [u["id"] for u in listed["universes"]] == ["u-mine"]
    assert listed["count"] == 1


def test_a_home_binding_counts_as_ownership(data_root):
    """First contact binds the home before any grant is written. A universe
    with a live founder must not depend on which landed first."""
    from tinyassets.daemon_server import claim_founder_home

    _universe(data_root, "u-home")
    ensure_universe_registered(
        data_root, universe_id="u-home", universe_path=data_root / "u-home",
    )
    claim_founder_home(data_root, "workos|founder", "u-home")

    assert "u-home" in owned_universe_ids(data_root)
    assert universe_owners(data_root, universe_id="u-home") == ["workos|founder"]


def test_the_definition_needs_no_denylist(data_root):
    """The four hardcoded operational names are not special any more -- they
    are unowned, like every other directory nobody made."""
    from tinyassets.api import universe as universe_api

    assert not hasattr(universe_api, "_TOP_LEVEL_OPERATIONAL_DATA_DIRS")
    for infra in ("wiki", "lance", "runs", "output"):
        _universe(data_root, infra)
    assert owned_universe_ids(data_root) == set()


def test_indexing_a_directory_does_not_make_it_a_universe(data_root):
    """`sync_universes_from_filesystem` indexes every directory by path, on
    purpose: a self-hoster restoring from a backup needs it indexed before
    anything can grant on it. Indexed is not owned, and only owned is a
    universe -- so the archive is in the path table and in nobody's list."""
    import json as _json

    from tinyassets.api.universe import _action_list_universes
    from tinyassets.daemon_server import _connect, sync_universes_from_filesystem

    _own(data_root, "u-mine")
    _universe(data_root, "_removed_universes_20260829")
    sync_universes_from_filesystem(data_root)

    with _connect(data_root) as conn:
        indexed = {
            str(row["universe_id"])
            for row in conn.execute("SELECT universe_id FROM universes")
        }
    assert {"u-mine", "_removed_universes_20260829"} <= indexed

    listed = _json.loads(_action_list_universes())
    assert [u["id"] for u in listed["universes"]] == ["u-mine"]
    assert owned_universe_ids(data_root) == {"u-mine"}


# --------------------------------------------------------------------------
# the cut
# --------------------------------------------------------------------------


def test_the_plan_reports_before_anything_is_removed(data_root):
    from tinyassets.universe_prune import plan

    _own(data_root, "u-mine")
    (data_root / "u-mine" / "soul.json").write_text("{}", encoding="utf-8")
    _universe(data_root, "_removed_universes_20260828")
    (data_root / "_removed_universes_20260828" / "note.txt").write_text(
        "x" * 100, encoding="utf-8",
    )
    _universe(data_root, "wiki")

    by_name = {r.name: r for r in plan(data_root)}
    assert by_name["u-mine"].owners == ["workos|founder"]
    assert by_name["u-mine"].removable is False
    assert "soul.json" in by_name["u-mine"].notable_files

    assert by_name["_removed_universes_20260828"].owners == []
    assert by_name["_removed_universes_20260828"].removable is True
    assert by_name["_removed_universes_20260828"].byte_count == 100

    assert by_name["wiki"].is_infrastructure is True
    assert by_name["wiki"].removable is False

    # A plan changes nothing.
    assert (data_root / "_removed_universes_20260828").is_dir()


def test_the_cut_removes_the_unowned_and_refuses_the_rest(data_root):
    from tinyassets.universe_prune import prune

    _own(data_root, "u-mine")
    _universe(data_root, "_removed_universes_20260828")
    _universe(data_root, "wiki")

    dry = prune(
        data_root,
        names=["u-mine", "_removed_universes_20260828", "wiki"],
        apply=False,
    )
    assert dry["removed"] == ["_removed_universes_20260828"]
    assert (data_root / "_removed_universes_20260828").is_dir(), "a dry run cut something"

    result = prune(
        data_root,
        names=["u-mine", "_removed_universes_20260828", "wiki"],
        apply=True,
    )
    assert result["removed"] == ["_removed_universes_20260828"]
    assert not (data_root / "_removed_universes_20260828").exists()
    assert (data_root / "u-mine").is_dir(), "an owned universe was cut"
    assert (data_root / "wiki").is_dir(), "infrastructure was cut"

    reasons = {entry["name"]: entry["reason"] for entry in result["refused"]}
    assert reasons["u-mine"] == "owned"
    assert reasons["wiki"] == "platform infrastructure"


def test_ownership_is_read_inside_the_cut_not_from_the_caller(data_root):
    """The failure this ordering prevents: on 2026-08-26 a live user's bound
    universe was archived off an inventory taken earlier. A caller that read
    the plan before the claim must not be able to delete the claimed
    universe."""
    from tinyassets.universe_prune import plan, prune

    _universe(data_root, "u-late")
    ensure_universe_registered(
        data_root, universe_id="u-late", universe_path=data_root / "u-late",
    )
    stale = {r.name: r for r in plan(data_root)}
    assert stale["u-late"].removable is True          # unowned at plan time

    # ...and then somebody claims it.
    grant_universe_access(
        data_root, universe_id="u-late", actor_id="workos|late",
        permission="admin", granted_by="test",
    )

    result = prune(data_root, names=["u-late"], apply=True)
    assert result["removed"] == []
    assert result["refused"][0]["reason"] == "owned"
    assert result["refused"][0]["owners"] == ["workos|late"]
    assert (data_root / "u-late").is_dir()


@pytest.mark.parametrize(
    "name",
    ["..", ".", "", "../escape", "sub/dir", "sub\\dir", ".hidden"],
)
def test_the_cut_refuses_anything_that_is_not_a_plain_child(data_root, name):
    from tinyassets.universe_prune import prune

    result = prune(data_root, names=[name], apply=True)
    assert result["removed"] == []
    assert result["refused"], name


def test_a_prune_leaves_nothing_behind_to_prune(data_root):
    """The property the founder named: after a cut, the count is what they
    expect. The old shape renamed a universe aside and the pile was itself
    listed, so the next prune had more to look at than the last."""
    from tinyassets.api.universe import _action_list_universes
    from tinyassets.universe_prune import plan, prune

    _own(data_root, "u-mine")
    for leftover in ("_removed_universes_20260828", "_removed_legacy_20260829", "scratch"):
        _universe(data_root, leftover)

    prune(
        data_root,
        names=[r.name for r in plan(data_root) if r.removable],
        apply=True,
    )

    assert sorted(p.name for p in data_root.iterdir() if p.is_dir()) == ["u-mine"]
    listed = json.loads(_action_list_universes())
    assert [u["id"] for u in listed["universes"]] == ["u-mine"]
    # ...and running it again has nothing to do.
    assert [r for r in plan(data_root) if r.removable] == []
