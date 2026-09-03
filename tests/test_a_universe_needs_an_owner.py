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
import pathlib

import pytest

from tinyassets.daemon_server import (
    ensure_universe_registered,
    grant_universe_access,
    owned_universe_ids,
    universe_owners,
)
from tinyassets.universe_prune import INFRASTRUCTURE_DIRS


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
    # A directory that is neither owned nor infrastructure nor a universe: an
    # operational store nobody put on any list.
    _universe(data_root, "some-new-store-2027")

    by_name = {r.name: r for r in plan(data_root)}
    assert by_name["u-mine"].owners == ["workos|founder"]
    assert by_name["u-mine"].removable is False
    assert "soul.json" in by_name["u-mine"].notable_files

    assert by_name["_removed_universes_20260828"].owners == []
    assert by_name["_removed_universes_20260828"].removable is True
    assert by_name["_removed_universes_20260828"].byte_count == 100

    assert by_name["wiki"].is_infrastructure is True
    assert by_name["wiki"].removable is False

    # Unowned, on no list, and still not removable: the prune has no positive
    # reason to believe it was ever a universe (Codex code review 2026-09-02,
    # P0 -- `daemon_wikis` and `cloud-automation-inputs` were exactly this, and
    # a blanket --apply would have erased them).
    unknown = by_name["some-new-store-2027"]
    assert unknown.owners == []
    assert unknown.is_infrastructure is False
    assert unknown.universe_signal == ""
    assert unknown.removable is False

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
    (data_root / "u-late" / "soul.md").write_text("# late", encoding="utf-8")
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
    for leftover in ("_removed_universes_20260828", "_removed_legacy_20260829"):
        _universe(data_root, leftover)
    # A migration backup is NOT one of these. `docs/host-actions.md` says of
    # the seven existing ones "do not delete -- they are migration backups",
    # and `_backup` as a universe signal would have cut them (Codex code
    # review round 2, P0).
    backup = "_backup_subject_migration_20260829T055340Z"
    _universe(data_root, backup)

    prune(
        data_root,
        names=[r.name for r in plan(data_root) if r.removable],
        apply=True,
    )

    assert sorted(p.name for p in data_root.iterdir() if p.is_dir()) == [
        backup, "u-mine",
    ]
    refused = prune(data_root, names=[backup], apply=True)
    assert refused["removed"] == []
    assert refused["refused"][0]["reason"] == "not a universe directory"
    assert (data_root / backup).is_dir()
    listed = json.loads(_action_list_universes())
    assert [u["id"] for u in listed["universes"]] == ["u-mine"]
    # ...and running it again has nothing to do.
    assert [r for r in plan(data_root) if r.removable] == []


# --------------------------------------------------------------------------
# the list stays complete
# --------------------------------------------------------------------------


def test_every_platform_directory_under_the_data_root_is_named_infrastructure():
    """A directory the platform creates under the data root and nobody owns is
    removable, so a missing name here is a delete of real data.

    `founder_offers` was missing: `_founder_offers_path` creates
    ``data_dir()/founder_offers`` to hold every founder's stored offers, no ACL
    row ever names it, and `prune --apply` would have cut it. Reviewing the
    constant by eye is what missed it, so this reads the source instead.
    """
    import re

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    package = repo_root / "tinyassets"
    assert package.is_dir(), package

    # A universe directory, not infrastructure: it is subject to ownership like
    # any other, which is the whole point of the change.
    universe_dirs = {"default-universe"}

    # A directory-name shape only: this must not match prose like
    # ``data_dir() / "<name>"`` in a docstring.
    pattern = re.compile(r'data_dir\(\)\s*/\s*"([A-Za-z0-9_.-]+)"')
    found: dict[str, str] = {}
    for source in package.rglob("*.py"):
        for name in pattern.findall(source.read_text(encoding="utf-8")):
            # A name carrying an extension is a file, not a directory.
            if "." in name:
                continue
            found.setdefault(name, str(source.relative_to(repo_root)))

    assert found, "the scan found nothing -- it stopped testing what it claims"

    # ...and the roots named only through the environment. `community-pool` is
    # `TINYASSETS_REPO_ROOT: /data/community-pool` in `deploy/compose.yml` and
    # appears in no Python literal, which is why reading the source alone left
    # it out of the list and `reset(confirm=True)` would have removed it
    # (Codex code review round 2, P0).
    compose = repo_root / "deploy" / "compose.yml"
    if compose.is_file():
        for name in re.findall(r"/data/([A-Za-z0-9_-]+)", compose.read_text(encoding="utf-8")):
            found.setdefault(name, "deploy/compose.yml")

    missing = {
        name: where
        for name, where in found.items()
        if name not in INFRASTRUCTURE_DIRS and name not in universe_dirs
    }
    assert not missing, (
        "these directories are created under the data root but are neither "
        "platform infrastructure nor a universe, so a prune would delete "
        f"them: {missing}"
    )


def test_an_operational_store_is_never_cut_even_when_named(data_root):
    """Codex code review 2026-09-02, P0. Five live stores share the data root
    and nobody owns them: daemon_wikis (daemon memory), cloud-automation-inputs
    (retained user specifications), lancedb (the brain's vector store, which is
    not the protected `lance`), scratch (the workspace pool) and
    founder_offers. Under "unowned means garbage" a routine --apply erased all
    five.

    They are on the infrastructure list now, but a list that has to be complete
    to be safe is not a safety mechanism -- so this also names a directory on
    NO list and still expects a refusal.
    """
    from tinyassets.universe_prune import prune

    stores = ("daemon_wikis", "cloud-automation-inputs", "lancedb", "scratch")
    invented = "a-store-invented-after-this-was-written"
    for store in (*stores, invented):
        _universe(data_root, store)
        (data_root / store / "content.bin").write_text("real data", encoding="utf-8")

    result = prune(data_root, names=[*stores, invented], apply=True)
    assert result["removed"] == []
    reasons = {entry["name"]: entry["reason"] for entry in result["refused"]}
    assert reasons["daemon_wikis"] == "platform infrastructure"
    assert reasons[invented] == "not a universe directory"
    for store in (*stores, invented):
        assert (data_root / store / "content.bin").is_file(), store


@pytest.mark.parametrize("alias", ["WIKI", "Wiki", "wiki.", "wiki "])
def test_a_respelled_name_cannot_reach_a_protected_directory(data_root, alias):
    """Codex code review 2026-09-02, P1. On Windows WIKI, wiki. and 'wiki '
    all open the same directory as wiki, so a spelling the caller chose walked
    past both the infrastructure list and the ownership query, and the delete
    landed on the real directory."""
    from tinyassets.universe_prune import prune

    _universe(data_root, "wiki")
    (data_root / "wiki" / "page.md").write_text("# real", encoding="utf-8")

    result = prune(data_root, names=[alias], apply=True)
    assert result["removed"] == []
    assert (data_root / "wiki" / "page.md").is_file(), (
        f"{alias!r} deleted the protected directory"
    )
    # It is refused for the RIGHT reason: no child is spelled that way. The
    # signal check would also have caught this one, and asserting only
    # "refused" let the name guard be deleted with the test still green.
    assert result["refused"][0]["reason"] == (
        "no directory under the data root is spelled exactly that"
    ), result["refused"]


def test_a_recased_universe_directory_is_still_owned(data_root):
    """The same alias problem the other way round: a directory restored as
    U-Mine is the ACL's u-mine, and matching the id exactly called an owned
    universe unowned."""
    import os

    from tinyassets.universe_prune import prune

    _own(data_root, "u-mine")
    (data_root / "u-mine" / "soul.md").write_text("# mine", encoding="utf-8")

    try:
        os.rename(data_root / "u-mine", data_root / "U-Mine")
    except OSError:
        pass
    on_disk = next(p.name for p in data_root.iterdir() if p.name.lower() == "u-mine")

    result = prune(data_root, names=[on_disk], apply=True)
    assert result["removed"] == []
    assert result["refused"][0]["reason"] == "owned", result["refused"]
    assert (data_root / on_disk / "soul.md").is_file()


def test_ownership_is_re_read_for_each_directory_not_once(data_root, monkeypatch):
    """Codex code review 2026-09-02, P2. The earlier test granted ownership
    before calling prune, so an implementation that snapshotted all ownership
    at entry would still have passed.

    The claim has to land after the point a snapshot would have been taken, so
    it fires from the FIRST REMOVAL. A snapshot implementation read the second
    directory's ownership before any removal, saw nobody, and deleted a
    universe somebody had claimed in between -- which is what happened for real
    on 2026-08-26.
    """
    from tinyassets import universe_prune

    for name in ("_removed_first_20260828", "_removed_second_20260828"):
        _universe(data_root, name)

    real_rmtree = universe_prune.shutil.rmtree

    def _claiming_rmtree(path, *args, **kwargs):
        result = real_rmtree(path, *args, **kwargs)
        # The cut frees the id first, so what reaches rmtree is the staging
        # name `.pruning-<id>-<token>` (Codex code review round 2, P0: the
        # ownership read and the delete had to stop being two steps).
        if "_removed_first_20260828" in pathlib.Path(path).name:
            # Another request claims the second directory, now that the first
            # one is already gone.
            grant_universe_access(
                data_root, universe_id="_removed_second_20260828",
                actor_id="workos|racer", permission="admin", granted_by="test",
            )
        return result

    monkeypatch.setattr(universe_prune.shutil, "rmtree", _claiming_rmtree)
    result = universe_prune.prune(
        data_root,
        names=["_removed_first_20260828", "_removed_second_20260828"],
        apply=True,
    )

    assert result["removed"] == ["_removed_first_20260828"]
    refused = {entry["name"]: entry for entry in result["refused"]}
    assert refused["_removed_second_20260828"]["reason"] == "owned"
    assert refused["_removed_second_20260828"]["owners"] == ["workos|racer"]
    assert (data_root / "_removed_second_20260828").is_dir()


def test_creating_a_universe_claims_the_owner_before_the_directory_exists():
    """Codex code review 2026-09-02, P0. Explicit creation made and seeded the
    directory, did registry and visibility work, and granted ownership ~90
    lines later. A prune running in that window saw an unowned directory and
    removed it, while the create went on to write the ACL row and return
    "created"."""
    import inspect

    from tinyassets.api import universe as universe_api

    source = inspect.getsource(universe_api._action_create_universe)
    assert source.index("grant_universe_access(") < source.index("udir.mkdir("), (
        "the directory is created before its owner is claimed, which is the "
        "window a concurrent prune deletes into"
    )


def test_a_claim_landing_between_the_check_and_the_delete_is_not_lost(
    data_root, monkeypatch,
):
    """Codex code review round 2, P0. Reading owners and then calling rmtree
    left a window: a grant written in between went into the ground with the
    directory.

    The cut frees the id first -- the directory moves aside under a name
    nothing can grant on -- and reads ownership again. Here the claim lands
    during the FIRST read, which is the moment that window opened."""
    from tinyassets import universe_prune

    _universe(data_root, "_removed_racy_20260828")

    # The claim lands from the signal read, which happens after EVERY
    # pre-check and before the directory moves. Triggering it from the
    # ownership read instead would be caught by the pre-check itself, and the
    # test would pass without the second read existing at all.
    original_signal = universe_prune._universe_signal

    def _claim_then_answer(path):
        answer = original_signal(path)
        if path.name == "_removed_racy_20260828":
            grant_universe_access(
                data_root, universe_id="_removed_racy_20260828",
                actor_id="workos|racer", permission="admin", granted_by="test",
            )
        return answer

    # ...and the second ownership read must happen with the id ALREADY FREED.
    # Reading twice and then deleting the original would pass every assertion
    # below while leaving the window open (Codex code review round 3, P2), so
    # the read itself records whether the name was still occupied.
    from tinyassets import daemon_server

    real_owners = daemon_server.universe_owners
    occupied_at_read: list[bool] = []

    def _watch_owners(base, *, universe_id):
        if universe_id == "_removed_racy_20260828":
            occupied_at_read.append((data_root / universe_id).exists())
        return real_owners(base, universe_id=universe_id)

    monkeypatch.setattr(daemon_server, "universe_owners", _watch_owners)
    monkeypatch.setattr(universe_prune, "_universe_signal", _claim_then_answer)
    result = universe_prune.prune(
        data_root, names=["_removed_racy_20260828"], apply=True,
    )

    assert len(occupied_at_read) >= 2, occupied_at_read
    assert occupied_at_read[0] is True, "the first read ran after the move"
    assert occupied_at_read[-1] is False, (
        "the second ownership read ran while the id was still occupied, so the "
        "check-then-delete window is still open"
    )

    assert result["removed"] == [], "a universe claimed mid-cut was deleted"
    assert result["refused"][0]["reason"] == "owned"
    assert result["refused"][0]["owners"] == ["workos|racer"]
    assert (data_root / "_removed_racy_20260828").is_dir(), "it was not put back"
    assert [p.name for p in data_root.iterdir() if p.name.startswith(".pruning-")] == []


def test_reading_a_universe_by_id_needs_an_owner_too(data_root):
    """Codex code review round 2, P1, reproduced anonymously against
    production: filtering the enumeration was half the fix. Asking for the
    migration backup BY ID still answered with a full universe payload, so the
    graveyard stayed browsable -- which is what the founder reported."""
    from tinyassets.api.universe import (
        _action_inspect_universe,
        _action_switch_universe,
    )

    _own(data_root, "u-mine")
    for leftover in (
        "_backup_subject_migration_20260829T055340Z",
        "cloud-automation-inputs",
        "daemon_wikis",
    ):
        _universe(data_root, leftover)

    for leftover in (
        "_backup_subject_migration_20260829T055340Z",
        "cloud-automation-inputs",
        "daemon_wikis",
    ):
        inspected = json.loads(_action_inspect_universe(universe_id=leftover))
        assert "error" in inspected, (leftover, inspected)
        assert "not found" in inspected["error"]
        # ...and the refusal does not publish the graveyard either.
        assert inspected["available"] == ["u-mine"]

        switched = json.loads(_action_switch_universe(universe_id=leftover))
        assert "error" in switched, (leftover, switched)
        assert switched["available"] == ["u-mine"]

    owned = json.loads(_action_inspect_universe(universe_id="u-mine"))
    assert "error" not in owned, owned


def test_a_reset_clears_universes_and_leaves_what_it_does_not_recognise(data_root):
    """Codex code review round 3, P0. `reset(confirm=True)` cleared every
    directory that was not on the infrastructure list, so it destroyed
    `_backup_subject_migration_...` -- the one thing `docs/host-actions.md`
    says in as many words not to delete. The prune had learned the difference
    and the reset had not."""
    from tinyassets.reset import universe_dirs

    _own(data_root, "u-mine")
    (data_root / "u-mine" / "soul.md").write_text("# mine", encoding="utf-8")
    _universe(data_root, "_removed_universes_20260828")
    backup = "_backup_subject_migration_20260829T055340Z"
    _universe(data_root, backup)
    _universe(data_root, "wiki")
    _universe(data_root, "some-new-store-2027")

    cleared = {p.name for p in universe_dirs(data_root)}
    assert "u-mine" in cleared
    assert "_removed_universes_20260828" in cleared, (
        "a pile of universes a past prune left is exactly what a reset clears"
    )
    assert backup not in cleared, "the migration backup was cleared"
    assert "wiki" not in cleared
    assert "some-new-store-2027" not in cleared


def test_an_interrupted_cut_is_reported_rather_than_left_silent(data_root):
    """Codex code review round 3, P1. A crash between the move and the delete
    leaves the content under a dotted name that no listing, no prune, no reset
    and no filesystem sync will ever mention again."""
    from tinyassets.universe_prune import STAGING_PREFIX, interrupted_cuts, plan

    _own(data_root, "u-mine")
    assert interrupted_cuts(data_root) == []

    orphan = data_root / f"{STAGING_PREFIX}_removed_something-deadbeef1234"
    orphan.mkdir()
    (orphan / "work.md").write_text("# not lost", encoding="utf-8")

    reported = interrupted_cuts(data_root)
    assert reported == [str(orphan)]
    # ...and it is still invisible to everything else, which is why it needs
    # its own report.
    assert [r.name for r in plan(data_root)] == ["u-mine"]
    assert (orphan / "work.md").is_file()


def test_a_not_found_answer_does_not_publish_private_universes(data_root, monkeypatch):
    """Codex code review round 3, P1. Asking for an id that does not exist
    answered with every OWNED universe -- private and unlisted ones included --
    to any signed-in caller. The enumeration gate the listing applies was
    skipped by taking the error path."""
    from tinyassets.api import universe as universe_api
    from tinyassets.api import visibility

    _own(data_root, "u-public")
    _own(data_root, "u-private")

    def _only_public_is_discoverable(universe_id, capability):
        return universe_id == "u-public"

    monkeypatch.setattr(
        visibility, "visibility_permits", _only_public_is_discoverable,
    )
    answer = json.loads(universe_api._action_inspect_universe(universe_id="nope"))
    assert "not found" in answer["error"]
    assert answer["available"] == ["u-public"], answer


def test_an_unreadable_ownership_store_is_not_a_missing_universe(data_root, monkeypatch):
    """Codex code review round 3, P1. A transient SQLite lock during the
    ownership lookup reported that an existing universe does not exist. Fail
    closed AND loudly: still refused, for the reason that is true."""
    from tinyassets import daemon_server
    from tinyassets.api import universe as universe_api

    _own(data_root, "u-mine")

    def _store_is_down(base_path, name):
        raise OSError("database is locked")

    monkeypatch.setattr(daemon_server, "owned_universe_id", _store_is_down)

    answer = json.loads(universe_api._action_inspect_universe(universe_id="u-mine"))
    assert "not found" not in answer["error"], answer
    assert "Ownership store unavailable" in answer["error"]
    assert "database is locked" in answer["error"]
